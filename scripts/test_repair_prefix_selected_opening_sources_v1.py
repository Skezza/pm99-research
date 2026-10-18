import hashlib
import pytest
from scripts import repair_prefix_selected_opening_sources_v1 as repair
from scripts.test_season_historical_opening_review_v1 import report, schedule


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(repair.registry, 'ROOT', tmp_path)


def original(tmp_path):
    pages = {'schedule': schedule([('01/08/2000', 'GB1', '7')]), 'report': report()}
    receipts = []
    for url, payload in pages.items():
        p = tmp_path / (url + '.html')
        p.write_bytes(payload)
        receipts.append({'url': url, 'cache_path': p.name, 'sha256': hashlib.sha256(payload).hexdigest()})
    row = {'source_selector': {'club_name': 'Example', 'transfermarkt_club_id': 14},
        'schedule_url': 'schedule', 'lineup_source_url': 'report', 'first_league_fixture_date': '2000-08-01',
        'source_match_id': '7', 'source_competition_code': 'GB1',
        'starting_xi': [{'source_player_id': str(i)} for i in range(100, 111)],
        'substitutes': [], 'declared_manager': 'Wrong Coach'}
    return row, {'source': {'cache_files': receipts}}


def test_two_exact_club_parsers_correct_original_capture_without_mutating_it(tmp_path):
    row, document = original(tmp_path)
    corrected, evidence, unresolved = repair.replay(row, document, tmp_path)
    assert {p['source_player_id'] for p in corrected['starting_xi']} == {str(i) for i in range(11)}
    assert corrected['declared_manager'] == 'Right Coach'
    assert row['declared_manager'] == 'Wrong Coach'
    assert evidence['date'] == '2000-08-01' and not unresolved


def test_original_wrong_date_or_match_cannot_be_changed_by_source_replay(tmp_path):
    row, doc = original(tmp_path)
    row['source_match_id'] = '9'
    with pytest.raises(ValueError, match='earliest fixture'):
        repair.replay(row, doc, tmp_path)


def test_correct_original_xi_is_not_rewritten_as_a_side_repair(tmp_path):
    row, doc = original(tmp_path)
    row['starting_xi'] = [{'source_player_id': str(i)} for i in range(11)]
    with pytest.raises(ValueError, match='not an original captured'):
        repair.replay(row, doc, tmp_path)


def test_original_raw_receipt_changes_are_a_hard_refusal(tmp_path):
    row, doc = original(tmp_path)
    (tmp_path / 'report.html').write_bytes(report(manager='Invented Coach'))
    with pytest.raises(ValueError, match='source hash changed'):
        repair.replay(row, doc, tmp_path)
