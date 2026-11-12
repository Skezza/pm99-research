import json
import re

import pytest

from scripts import pm99_season_report_v1 as report
from scripts import season_amendment_candidates_v1 as candidates
from scripts import season_release_registry_v1 as registry


def text_of(result):
    return report.markdown(result)


def checklist(version, findings=(), complete=False):
    return dict(schema='x', utc='2026-01-01T00:00:00+00:00', all_required_work_complete=complete, allowed_gaps=['Missing portraits'],
                not_automatically_allowed=['Wrong or unsourced managers'], remaining_cross_club_cases=7,
                cross_club_case_file='scan.json', additional_confirmed_findings=list(findings),
                cross_club_dispositions=[dict(season='2000-01', case_id='c1', state='confirmed-fault-repaired-current-game')],
                within_club_cases=[dict(season='2000-01', status='x')], accepted_editorial_exceptions=[dict(season='2000-01', id='exc-1')],
                additional_runtime_review_candidates=[dict(case_id='2000-01:42:nationality-review', observation='o')])


def test_newest_checklist_is_discovered_numerically_and_split_per_season(tmp_path, monkeypatch):
    monkeypatch.setattr(report, 'ROOT', tmp_path)
    for version in (9, 10, 298):
        folder = tmp_path / '.local/consolidated-audit-a'
        folder.mkdir(parents=True, exist_ok=True)
        data = checklist(version, findings=[dict(season='2000-01', id=f'f{version}', state='open-dated-conflict')])
        (folder / f'release-delivery-checklist-v{version}.json').write_text(json.dumps(data))
    (tmp_path / 'scan.json').write_text(json.dumps(dict(seasons=[dict(season='2000-01', candidates=[1, 2, 3])])))
    meta, by_season = report.load_checklist()
    assert meta['path'].endswith('-v298.json') and meta['work_complete_flag'] is False
    assert meta['scan_counts'] == {'2000-01': 3} and meta['baseline_unclassified_candidates'] == 7
    facts = by_season['2000-01']
    assert [f['id'] for f in facts['findings']] == ['f298']
    assert len(facts['dispositions']) == 1 and facts['runtime_candidates'][0]['case_id'].startswith('2000-01:')


def test_finding_states_use_an_explicit_vocabulary_and_unknown_wording_is_never_closed():
    assert report.classify_state('repaired-and-runtime-verified') == 'closed'
    assert report.classify_state('confirmed-not-delivered') == 'open'
    assert report.classify_state('open-dated-annual-broad-position-conflict') == 'open'
    for novel in ('partial delivery; 2000/01 corrected; 2001/02 exact-identity occurrence remains open',
                  'country-JPN-delivered-native-SOURCE-runner-verified-birthday-choice-still-explicitly-disputed',
                  'closed; Seedorf scoped occurrences delivered', 'SERIOUS-new-state', 'delivered-but-regressed'):
        assert report.classify_state(novel) == 'needs-reading'      # looks closed/open-ish, but is surfaced for a human


def test_checklist_state_vocabulary_is_reported_with_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(report, 'ROOT', tmp_path)
    folder = tmp_path / '.local/consolidated-audit-a'
    folder.mkdir(parents=True)
    findings = [dict(season='2000-01', id='a', state='repaired-and-runtime-verified'), dict(season='2000-01', id='b', state='brand-new-state')]
    (folder / 'release-delivery-checklist-v1.json').write_text(json.dumps(checklist(1, findings)))
    meta, by_season = report.load_checklist()
    assert meta['state_vocabulary']['brand-new-state'] == dict(count=1, classified_as='needs-reading')
    assert meta['state_vocabulary']['repaired-and-runtime-verified']['classified_as'] == 'closed'


def test_report_for_a_real_season_separates_declared_from_actual_and_has_no_percentages(monkeypatch, tmp_path):
    try:
        registry.load_preferred_release('2022-23')
    except Exception as exc:
        pytest.skip(f'local release unavailable: {exc}')
    monkeypatch.setattr(candidates, 'BUILDS_ROOT', tmp_path / 'builds')
    candidates.record_candidate('2022-23', dict(release_id='edited-2022-23-x', parent_release_id='p', change_count=2, play_command='./pm99-season play 2022-23 --release-id edited-2022-23-x', summary=[]))
    result = report.build_report(['2022-23'])
    row = result['seasons'][0]
    assert row['play_command'] == './pm99-season play 2022-23'
    assert row['release_id'] == registry.load_preferred_release('2022-23').release_id
    assert set(row) >= {'declared', 'actual', 'known_issues', 'unreviewed_candidates', 'edited_candidates', 'recipe'}
    assert row['actual']['playable_validation']['valid'] is True and 'valid' in row['actual']['runtime_attestation']
    assert row['edited_candidates'][0]['release_id'] == 'edited-2022-23-x'
    cap = row['recipe']['players_with_field_editable']
    assert cap['rating'] > cap['broad_position'] > 0 and row['recipe']['managers_renamable'] > 0
    # Foreign/preserved players are not declared wholly uneditable: ratings stay editable where a rating is stored.
    assert cap['rating'] > row['recipe']['players'] - row['recipe']['whole_record_preserved_players'] - 1000
    assert 'cached' in text_of(result).lower() and 'per field' in text_of(result)
    text = text_of(result)
    assert '%' not in text and not re.search(r'complete(?:d|ion)?\s*[:=]?\s*\d', text, re.I)
    assert 'NOT confirmed bugs' in text and 'cached' in text
    if result['checklist']:
        assert result['checklist']['work_complete_flag'] in (True, False, None)
