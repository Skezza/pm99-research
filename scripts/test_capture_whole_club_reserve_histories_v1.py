import pytest
from scripts import capture_whole_club_reserve_histories_v1 as capture


def fixture(monkeypatch):
    annual = {'club_name': 'Weymouth', 'country_catalog': 'eng', 'source_path': 'eng/weymouth.txt',
        'players': [{'name': 'Exact Name', 'birth_date': '1990-01-01', 'position': 'D'},
                    {'name': 'Unknown Name', 'birth_date': None, 'position': 'M'}]}
    monkeypatch.setattr(capture.whole.roster, 'load_sources', lambda s: ([annual], None))
    class Verifier:
        def __init__(self, s): pass
        def verify(self, c): return {'status': 'raw-source-reparsed', 'sha256': 'original'}
    monkeypatch.setattr(capture.whole.roster, 'SourceVerifier', Verifier)
    monkeypatch.setattr(capture.whole.transfer, 'unique_person', lambda p, ps:
        {'source_player_id': 123, 'name': 'Exact Name', 'birth_date': '1990-01-01'}
        if p['name'] == 'Exact Name' else None)
    return annual


def test_annual_exact_identity_is_only_query_scope_not_opening_approval(monkeypatch):
    fixture(monkeypatch)
    result = capture.discover({'bindings': {'pinned': 'original'}}, '2021-22', ['Weymouth'], {}, {})
    assert result['query_player_ids'] == [123]
    assert len(result['witnesses']) == 1
    assert result['native_writes'] == 0 and result['opening_ownership_approved'] is False


@pytest.mark.parametrize('problem', ['wrong-club', 'unparsed', 'unknown-person', 'ambiguous-squad'])
def test_originals_and_unique_identity_are_mandatory(monkeypatch, problem):
    annual = fixture(monkeypatch)
    if problem == 'wrong-club': annual['club_name'] = 'Another'
    if problem == 'unparsed':
        class Verifier:
            def __init__(self, s): pass
            def verify(self, c): return {'status': 'source-gap'}
        monkeypatch.setattr(capture.whole.roster, 'SourceVerifier', Verifier)
    if problem == 'unknown-person':
        monkeypatch.setattr(capture.whole.transfer, 'unique_person', lambda *a: None)
    if problem == 'ambiguous-squad':
        monkeypatch.setattr(capture.whole.roster, 'load_sources', lambda s: ([annual, annual], None))
    with pytest.raises(ValueError):
        capture.discover({'bindings': {}}, '2021-22', ['Weymouth'], {}, {})
