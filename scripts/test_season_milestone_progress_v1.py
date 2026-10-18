import copy
import json
from pathlib import Path
import pytest
from scripts import season_milestone_progress_v1 as progress


def candidate(number=1, third=False):
    rows = [{'carrier_id': number*10+i, 'player_id': f'player-{number*10+i}',
             'club_id': f'club-{i}', 'club': f'Club {i}', 'source_name': f'Person {number}',
             'birth_date': '1980-01-01'} for i in range(1, 4 if third else 3)]
    return {'identity': ['published-person', number], 'players': rows}


def document(candidates):
    return {'schema_version': progress.AUDIT_SCHEMA, 'policy': 'fixed-test-policy',
            'snapshot': {'path': 'snapshot.db', 'sha256': 'a'*64,
                         'pinned_receipt_path': 'snapshot.json', 'pinned_receipt_sha256': 'd'*64,
                         'project_url': 'https://example.org/source', 'version': 'fixed'},
            'public_person_supplement': {'path': 'supplement.json', 'sha256': 'b'*64,
                                         'policy': 'fixed', 'merge_refusals': []},
            'cross_club_candidate_groups': len(candidates), 'seasons': [
                {'season': season, 'release_id': 'test-v1', 'package_sha256': 'c'*64,
                 'layers': [{'layer': 'main', 'path': f'{season}/package.json', 'sha256': 'c'*64}],
                 'candidates': copy.deepcopy(candidates) if i == 0 else [],
                 'cross_club_candidate_groups': len(candidates) if i == 0 else 0}
                for i, season in enumerate(progress.SEASONS)]}


def write(path, value):
    path.write_bytes(progress.canonical(value))
    return path


def setup(tmp_path, candidates=None):
    source = write(tmp_path/'initial.json', document(candidates or [candidate()]))
    base = tmp_path/'baseline.json'
    progress.freeze(source, base)
    return source, base, progress.digest(base)


def test_identical_inputs_produce_byte_identical_reports(tmp_path):
    source, base, sha = setup(tmp_path)
    first, second = tmp_path/'first.json', tmp_path/'second.json'
    progress.report(base, sha, source, first)
    progress.report(base, sha, source, second)
    assert first.read_bytes() == second.read_bytes()


def test_missing_previous_report_cannot_claim_zero_recurrences(tmp_path):
    source, base, sha = setup(tmp_path)
    result = progress.report(base, sha, source, tmp_path/'report.json')
    assert result['candidate_reappeared_count'] is None
    assert 'recurrence not assessed' in result['history_mode']


def test_absence_is_not_completed_and_new_discovery_is_separate(tmp_path):
    _, base, sha = setup(tmp_path)
    current = write(tmp_path/'current.json', document([candidate(2)]))
    report = progress.report(base, sha, current, tmp_path/'report.json')
    assert report['baseline_total'] == 1
    assert report['baseline_absent_awaiting_verification'] == 1
    assert report['new_discovery_count'] == 1
    assert report['verified_completed_count'] == 0
    assert report['verified_completion_percent'] is None
    assert report['queue_net_reduction_percent'] == 0


def test_reappearing_candidate_is_flagged(tmp_path):
    original, base, sha = setup(tmp_path)
    empty = write(tmp_path/'empty.json', document([]))
    first = tmp_path/'first.json'
    progress.report(base, sha, empty, first)
    second = progress.report(base, sha, original, tmp_path/'second.json', first, progress.digest(first))
    assert second['candidate_reappeared_count'] == 1
    assert second['proven_fix_regression_count'] is None


def test_new_discovery_remains_tracked_after_absence_and_reappears(tmp_path):
    original, base, sha = setup(tmp_path)
    new = write(tmp_path/'new.json', document([candidate(), candidate(2)]))
    first, second = tmp_path/'first.json', tmp_path/'second.json'
    progress.report(base, sha, new, first)
    progress.report(base, sha, original, second, first, progress.digest(first))
    third = progress.report(base, sha, new, tmp_path/'third.json', second, progress.digest(second))
    assert third['baseline_total'] == 1
    assert third['discovered_total'] == 1
    assert third['new_discovery_count'] == 0
    assert third['candidate_reappeared_count'] == 1


@pytest.mark.parametrize('change', ['missing-season', 'duplicate-season', 'policy', 'snapshot',
                                   'supplement', 'top-count', 'season-count', 'duplicate-identity',
                                   'duplicate-carrier', 'one-club', 'namespace'])
def test_malformed_or_changed_audit_refused(tmp_path, change):
    _, base, sha = setup(tmp_path)
    value = document([candidate()])
    row = value['seasons'][0]
    if change == 'missing-season': value['seasons'].pop()
    elif change == 'duplicate-season': value['seasons'][-1] = copy.deepcopy(row)
    elif change == 'policy': value['policy'] = 'changed'
    elif change == 'snapshot': value['snapshot']['sha256'] = 'd'*64
    elif change == 'supplement': value['public_person_supplement']['sha256'] = 'd'*64
    elif change == 'top-count': value['cross_club_candidate_groups'] = 999
    elif change == 'season-count': row['cross_club_candidate_groups'] = 999
    elif change == 'duplicate-identity':
        row['candidates'].append(copy.deepcopy(row['candidates'][0]))
        row['cross_club_candidate_groups'] = value['cross_club_candidate_groups'] = 2
    elif change == 'duplicate-carrier': row['candidates'][0]['players'][1]['carrier_id'] = 11
    elif change == 'one-club': row['candidates'][0]['players'][1]['club_id'] = 'club-1'
    else: row['candidates'][0]['identity'][0] = 'invented'
    bad = write(tmp_path/'bad.json', value)
    with pytest.raises(ValueError):
        progress.report(base, sha, bad, tmp_path/'report.json')
    assert not (tmp_path/'report.json').exists()


def test_same_identity_third_club_is_visible_not_a_new_item(tmp_path):
    _, base, sha = setup(tmp_path)
    current = write(tmp_path/'current.json', document([candidate(third=True)]))
    result = progress.report(base, sha, current, tmp_path/'report.json')
    assert result['new_discovery_count'] == 0
    assert result['membership_changes'][0]['members_added'] == 1


def test_member_order_does_not_create_change(tmp_path):
    _, base, sha = setup(tmp_path)
    d = document([candidate()]); d['seasons'][0]['candidates'][0]['players'].reverse()
    current = write(tmp_path/'current.json', d)
    assert progress.report(base, sha, current, tmp_path/'report.json')['membership_changes'] == []


def test_external_pin_and_immutable_outputs(tmp_path):
    source, base, sha = setup(tmp_path)
    with pytest.raises(ValueError, match='external pin'):
        progress.report(base, '0'*64, source, tmp_path/'report.json')
    with pytest.raises(FileExistsError): progress.freeze(source, base)
    output = tmp_path/'report.json'; progress.report(base, sha, source, output)
    with pytest.raises(FileExistsError): progress.report(base, sha, source, output)


def test_previous_report_cannot_hide_absence_even_when_rehashed(tmp_path):
    original, base, sha = setup(tmp_path)
    empty = write(tmp_path/'empty.json', document([]))
    first = tmp_path/'first.json'; progress.report(base, sha, empty, first)
    d = progress.read(first); d['absent_item_ids'] = []
    write(first, d)
    with pytest.raises(ValueError, match='independently reproduce'):
        progress.report(base, sha, original, tmp_path/'second.json', first, progress.digest(first))


def test_changed_previous_audit_is_refused(tmp_path):
    original, base, sha = setup(tmp_path)
    empty = write(tmp_path/'empty.json', document([]))
    first = tmp_path/'first.json'; progress.report(base, sha, empty, first)
    write(empty, document([candidate(2)]))
    with pytest.raises(ValueError, match='hash changed'):
        progress.report(base, sha, original, tmp_path/'second.json', first, progress.digest(first))


def test_changed_measurement_implementation_requires_new_baseline(tmp_path, monkeypatch):
    source, base, sha = setup(tmp_path)
    substitute = tmp_path/'other-code.py'; substitute.write_bytes(b'changed')
    monkeypatch.setattr(progress, '__file__', str(substitute))
    with pytest.raises(ValueError, match='implementation changed'):
        progress.report(base, sha, source, tmp_path/'report.json')


def test_duplicate_json_key_is_refused(tmp_path):
    source = tmp_path/'bad.json'; source.write_bytes(b'{"x":1,"x":2}')
    with pytest.raises(ValueError, match='duplicate JSON key'): progress.read(source)
