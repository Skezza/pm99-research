"""Independent adversarial checks: queue movement must never become fake closure."""
import copy
import json

import pytest

from scripts import season_milestone_progress_v1 as progress


def candidate(identity=None):
    return {'identity': identity or ['published-person', '123'], 'players': [
        {'carrier_id': 1, 'club_id': 'club-a', 'player_id': 'player-a',
         'source_name': 'Example Player', 'birth_date': '1980-01-01'},
        {'carrier_id': 2, 'club_id': 'club-b', 'player_id': 'player-b',
         'source_name': 'Example Player', 'birth_date': '1980-01-01'}]}


def audit_document(groups=None):
    groups = [candidate()] if groups is None else groups
    return {'schema_version': progress.AUDIT_SCHEMA, 'policy': 'fixed identity policy',
            'snapshot': {'path': 'snapshot.duckdb', 'sha256': 'a' * 64,
                         'pinned_receipt_path': 'receipt.json',
                         'pinned_receipt_sha256': 'e' * 64,
                         'project_url': 'https://example.org/source', 'version': 'pinned'},
            'public_person_supplement': {'path': 'supplement.json', 'sha256': 'b' * 64,
                                        'policy': 'fixed-alias-policy', 'merge_refusals': []},
            'cross_club_candidate_groups': len(groups),
            'seasons': [{'season': season, 'release_id': 'test-release',
                         'package_sha256': 'c' * 64,
                         'layers': [{'layer': 'main', 'path': season + '/package.json',
                                     'sha256': 'c' * 64}],
                         'cross_club_candidate_groups': len(groups) if i == 0 else 0,
                         'candidates': copy.deepcopy(groups) if i == 0 else []}
                        for i, season in enumerate(progress.SEASONS)]}


def save(path, value):
    path.write_bytes(progress.canonical(value))
    return path


@pytest.fixture
def frozen(tmp_path):
    original = save(tmp_path / 'original.json', audit_document())
    baseline = tmp_path / 'baseline.json'
    progress.freeze(original, baseline)
    return baseline, progress.digest(baseline)


def run(tmp_path, frozen, value, label='report', previous=None):
    current = save(tmp_path / (label + '-audit.json'), value)
    return progress.report(*frozen, current, tmp_path / (label + '.json'),
                           previous, progress.digest(previous) if previous else None)


def test_remove_every_candidate_does_not_complete_milestone(tmp_path, frozen):
    result = run(tmp_path, frozen, audit_document([]))
    assert result['queue_net_reduction_percent'] == 100
    assert result['baseline_absent_awaiting_verification'] == 1
    assert result['verified_completed_count'] == 0
    assert result['verified_completion_percent'] is None
    assert result['proven_fix_regression_count'] is None


def test_identity_laundering_cannot_be_reported_as_a_fix(tmp_path, frozen):
    result = run(tmp_path, frozen, audit_document([candidate(['published-person', '456'])]))
    assert result['baseline_absent_awaiting_verification'] == 1
    assert result['new_discovery_count'] == 1
    assert result['queue_net_reduction_percent'] == 0
    assert result['verified_completed_count'] == 0


def test_candidate_recurrence_is_not_proven_fix_regression(tmp_path, frozen):
    run(tmp_path, frozen, audit_document([]), 'absent')
    result = run(tmp_path, frozen, audit_document(), 'returned', tmp_path / 'absent.json')
    assert result['candidate_reappeared_count'] == 1
    assert result['proven_fix_regression_count'] is None
    assert result['baseline_present'] == 1


def test_reordered_members_do_not_inflate_change_counts(tmp_path, frozen):
    document = audit_document()
    document['seasons'][0]['candidates'][0]['players'].reverse()
    assert run(tmp_path, frozen, document)['membership_changes'] == []


def test_move_same_carrier_to_third_club_is_visible(tmp_path, frozen):
    document = audit_document()
    document['seasons'][0]['candidates'][0]['players'][1]['club_id'] = 'club-c'
    result = run(tmp_path, frozen, document)
    assert result['new_discovery_count'] == 0
    assert result['membership_changes'][0]['members_added'] == 1
    assert result['membership_changes'][0]['members_removed'] == 1


@pytest.mark.parametrize('mutation', ['repeated-season', 'missing-season', 'wrong-count',
                                      'duplicate-identity', 'single-club'])
def test_malformed_inputs_cannot_shrink_denominator(tmp_path, frozen, mutation):
    document = audit_document()
    if mutation == 'repeated-season':
        document['seasons'][-1]['season'] = document['seasons'][0]['season']
    elif mutation == 'missing-season':
        document['seasons'].pop()
    elif mutation == 'wrong-count':
        document['seasons'][0]['cross_club_candidate_groups'] = 0
    elif mutation == 'duplicate-identity':
        document = audit_document([candidate(), candidate()])
    else:
        document['seasons'][0]['candidates'][0]['players'][1]['club_id'] = 'club-a'
    with pytest.raises(ValueError):
        run(tmp_path, frozen, document)
    assert not (tmp_path / 'report.json').exists()


def test_tampered_previous_statuses_refused_even_with_new_hash_pin(tmp_path, frozen):
    run(tmp_path, frozen, audit_document([]), 'absent')
    previous = tmp_path / 'absent.json'
    value = json.loads(previous.read_text())
    value['absent_item_ids'] = []
    save(previous, value)
    with pytest.raises(ValueError, match='independently reproduce'):
        run(tmp_path, frozen, audit_document(), 'returned', previous)


def test_tampered_previous_audit_refused(tmp_path, frozen):
    run(tmp_path, frozen, audit_document([]), 'absent')
    save(tmp_path / 'absent-audit.json', audit_document())
    with pytest.raises(ValueError, match='evidence hash changed'):
        run(tmp_path, frozen, audit_document(), 'returned', tmp_path / 'absent.json')


def test_previous_baseline_mismatch_refused(tmp_path, frozen):
    run(tmp_path, frozen, audit_document(), 'previous')
    previous = tmp_path / 'previous.json'
    value = json.loads(previous.read_text())
    value['baseline']['sha256'] = 'd' * 64
    save(previous, value)
    with pytest.raises(ValueError, match='another baseline'):
        run(tmp_path, frozen, audit_document(), 'current', previous)


def test_identical_inputs_yield_identical_report_bytes(tmp_path, frozen):
    current = save(tmp_path / 'current.json', audit_document())
    progress.report(*frozen, current, tmp_path / 'a.json')
    progress.report(*frozen, current, tmp_path / 'b.json')
    assert (tmp_path / 'a.json').read_bytes() == (tmp_path / 'b.json').read_bytes()


def test_output_cannot_overwrite_existing_evidence(tmp_path, frozen):
    run(tmp_path, frozen, audit_document())
    output = tmp_path / 'report.json'
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        run(tmp_path, frozen, audit_document())
    assert output.read_bytes() == before


@pytest.mark.parametrize('mutation', ['empty-snapshot', 'empty-supplement',
                                      'missing-layers', 'wrong-main-sha', 'blank-identity'])
def test_unbound_or_weak_audits_cannot_be_frozen(tmp_path, mutation):
    document = audit_document()
    if mutation == 'empty-snapshot':
        document['snapshot'] = {}
    elif mutation == 'empty-supplement':
        document['public_person_supplement'] = {}
    elif mutation == 'missing-layers':
        document['seasons'][0]['layers'] = []
    elif mutation == 'wrong-main-sha':
        document['seasons'][0]['layers'][0]['sha256'] = 'f' * 64
    else:
        document['seasons'][0]['candidates'][0]['identity'] = ['published-person', ' ']
    source = save(tmp_path / 'weak.json', document)
    with pytest.raises((ValueError, KeyError)):
        progress.freeze(source, tmp_path / 'baseline.json')
    assert not (tmp_path / 'baseline.json').exists()


def test_current_audit_changes_after_binding_are_refused(tmp_path, frozen, monkeypatch):
    current = save(tmp_path / 'current.json', audit_document())
    original_binding = progress.binding

    def mutate_after_binding(path):
        result = original_binding(path)
        if path == current:
            save(current, audit_document([]))
        return result

    monkeypatch.setattr(progress, 'binding', mutate_after_binding)
    with pytest.raises(ValueError):
        progress.report(*frozen, current, tmp_path / 'report.json')
    assert not (tmp_path / 'report.json').exists()
