from scripts import audit_published_player_identities_v1 as audit


def test_header_variants_join_same_exact_published_person_not_display_initials():
    index = {('kevinlong', '1990-08-18'): {42: {'source_player_id': 42}}}
    def player(name):
        return {'name': name, 'facts': {'birth_date': '1990-08-18'}}
    assert audit.key(player('#13 Kevin Long'), index) == audit.key(player('#4 Kevin Long'), index) == ('published-person', 42)
    assert audit.key(player('K. Long'), index)[0] == 'full-source-name-dob-candidate'


def test_missing_dataset_person_is_candidate_not_invented_source_id():
    p = {'name': '#16 Real Fullname', 'facts': {'birth_date': '1980-01-01'}}
    assert audit.key(p, {}) == ('full-source-name-dob-candidate', 'realfullname', '1980-01-01')
    assert audit.key({'name': 'Missing Date', 'facts': {}}, {}) is None


def test_identity_count_uses_same_pinned_people_without_rebuilding_unused_appearances(monkeypatch):
    from scripts import season_duplicate_source_context_v1 as source
    people={('exactfullname','1980-01-01'):{42:{'source_player_id':42}}}
    binding={'sha256':'pinned-original','version':1}
    calls=[]
    def load(database,receipt):
        calls.append((database,receipt));return people,{'unused':'transfers'},binding
    monkeypatch.setattr(source,'load_snapshot',load)
    monkeypatch.setattr(audit.transfer,'load_snapshot',lambda *a: (_ for _ in ()).throw(
        AssertionError('the appearance join is not used by an identity count')))
    assert audit.load_identity_snapshot()==(people,binding)
    assert calls==[(audit.DB,audit.SNAPSHOT)]


def test_published_short_name_joins_only_when_it_is_an_explicit_source_alias(tmp_path, monkeypatch):
    from scripts import season_published_person_identity_v1 as public
    from scripts.test_original_public_supplement_merges_v1 import people_document
    monkeypatch.setattr(public, 'ROOT', tmp_path)
    enriched, _ = public.merge({}, people_document(tmp_path))
    short = {'name': 'R. Player', 'facts': {'birth_date': '1960-01-02'}}
    full = {'name': 'Retired Player', 'facts': {'birth_date': '1960-01-02'}}
    assert audit.key(short, {})[0] == 'full-source-name-dob-candidate'
    assert audit.key(short, enriched) == audit.key(full, enriched) == ('published-person', 10)
    other = {'name': 'R. Player', 'facts': {'birth_date': '1960-01-03'}}
    assert audit.key(other, enriched)[0] == 'full-source-name-dob-candidate'
