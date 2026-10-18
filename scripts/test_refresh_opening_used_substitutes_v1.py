import copy
import pytest
from scripts import refresh_opening_used_substitutes_v1 as refresh


def document():
    return {'clubs': [{'carrier_id': 300, 'status': 'original-first-fixture-reparsed',
        'evidence': {'source_club_id': 1, 'date': '2005-08-06', 'starting_xi': {'10': 'Starter'},
            'substitutes': {}, 'match_page_date_independently_published': True,
            'source_url': 'https://source/report', 'raw_sources': [{'path': 'original.html',
                'sha256': 'original', 'url': 'https://source/report'}]}}]}


def test_raw_event_refresh_preserves_all_original_context(monkeypatch):
    before = document()
    saved = copy.deepcopy(before)
    monkeypatch.setattr(refresh.opening, 'match_team', lambda *a: {
        'starting_xi': {'10': 'Starter'}, 'match_page_date_independently_published': True})
    monkeypatch.setattr(refresh.substitutes, 'parse', lambda *a: {
        'used_substitutes': {'20': 'Reserve'}, 'unresolved_events': []})
    result, receipt = refresh.refresh(before, lambda _: b'original')
    assert before == saved
    assert result['clubs'][0]['evidence']['substitutes'] == {'20': 'Reserve'}
    result['clubs'][0]['evidence']['substitutes'] = {}
    assert result == before
    assert receipt['added_positive_used_substitutes'] == 1


def test_changed_original_starting_eleven_is_not_silently_replaced(monkeypatch):
    monkeypatch.setattr(refresh.opening, 'match_team', lambda *a: {
        'starting_xi': {'99': 'Different'}, 'match_page_date_independently_published': True})
    with pytest.raises(ValueError, match='original XI'):
        refresh.refresh(document(), lambda _: b'changed')
