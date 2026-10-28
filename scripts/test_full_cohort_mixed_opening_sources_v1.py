import copy
import hashlib
import json

import pytest

from scripts import season_historical_club_label_full_cohort_optin_v2 as cohort
from scripts import review_profile_addition_duplicate_assignments_v1 as evidence


def mixed_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(cohort.registry, 'ROOT', tmp_path)
    selector = dict(country_catalog='denmark', competition_catalog='supliga',
        club_name='Silkeborg', source_path='silke.txt', source_sha256='a' * 64)
    annual = dict(source_row_index=0, facts=dict(name='Annual Person', birth_date='1979-01-01'))
    added = dict(source_row_index=1, facts=dict(name='Source Person', birth_date='1980-02-03'),
        opening_xi_origin='profiled-first-fixture-addition', opening_source_player_id='123',
        opening_xi_order=1)
    source = dict(players=[annual, added], opening_fixture_date='2019-08-01')
    (tmp_path / 'opening-lineups.json').write_text(json.dumps(dict(clubs=[dict(
        source_selector=selector, source_competition_code='DK1')])))
    raw = b'<h1 class="data-header__headline-wrapper">Source Person</h1><span itemprop="birthDate">03/02/1980</span>'
    cache = tmp_path / 'person-cache'
    cache.mkdir()
    (cache / '123.html').write_bytes(raw)
    url = 'https://www.transfermarkt.co.uk/source-person/profil/spieler/123'
    receipt = dict(url=url, cache_path='123.html', sha256=hashlib.sha256(raw).hexdigest())
    (tmp_path / 'opening-lineup-person-evidence.json').write_text(json.dumps(
        dict(source=dict(cache_files=[receipt]))))
    opening = dict(date='2019-08-01', starting_xi={str(i): str(i) for i in range(123, 134)})
    monkeypatch.setattr(evidence.opening, 'verify_opening', lambda *args: copy.deepcopy(opening))
    seen = []

    def annual_reparse(season, selected, rows):
        assert season == '2019-20' and selected == selector
        assert rows['players'] == [annual]
        seen.append(copy.deepcopy(rows['players']))
        return dict(method='verified-original-annual-fixture')

    monkeypatch.setattr(cohort, '_reparse_source_cohort', annual_reparse)
    return selector, source, opening, seen


def test_mixed_pool_keeps_annual_and_actual_profile_proofs_separate(tmp_path, monkeypatch):
    selector, source, _, seen = mixed_fixture(tmp_path, monkeypatch)
    proof = cohort._reparse_bound_source_cohort('2019-20', selector, source, source_dir=tmp_path)
    assert len(seen) == 1
    assert proof['annual_row_count'] == proof['opening_addition_count'] == 1
    assert proof['original_profile_additions'][0]['published_birth_date'] == '1980-02-03'
    assert proof['original_profile_additions'][0]['verified_fields'] == ['name', 'birth_date']
    assert json.loads(json.dumps(proof)) == proof


@pytest.mark.parametrize('problem', ['body-tamper', 'wrong-name', 'wrong-dob', 'missing-dob',
    'not-in-xi', 'short-xi', 'wrong-fixture-date', 'future-year', 'wrong-club',
    'duplicate-profile', 'duplicate-row', 'missing-profile-receipt'])
def test_mixed_pool_rejects_unproved_person_membership_or_source_drift(tmp_path, monkeypatch, problem):
    selector, source, opening, _ = mixed_fixture(tmp_path, monkeypatch)
    added = source['players'][1]
    if problem == 'body-tamper':
        (tmp_path / 'person-cache/123.html').write_bytes(b'modified')
    if problem == 'wrong-name':
        added['facts']['name'] = 'Someone Else'
    if problem == 'wrong-dob':
        added['facts']['birth_date'] = '1980-03-02'
    if problem == 'missing-dob':
        added['facts']['birth_date'] = None
    if problem == 'not-in-xi':
        added['opening_source_player_id'] = '999'
    if problem == 'short-xi':
        opening['starting_xi'].pop('124')
    if problem == 'wrong-fixture-date':
        source['opening_fixture_date'] = '2019-08-02'
    if problem == 'future-year':
        opening['date'] = source['opening_fixture_date'] = '2020-08-01'
    if problem == 'wrong-club':
        selector['club_name'] = 'Another Club'
    if problem == 'duplicate-profile':
        source['players'].append(dict(added, source_row_index=2))
    if problem == 'duplicate-row':
        added['source_row_index'] = 0
    if problem == 'missing-profile-receipt':
        (tmp_path / 'opening-lineup-person-evidence.json').write_text('{"source":{"cache_files":[]}}')
    with pytest.raises(ValueError):
        cohort._reparse_bound_source_cohort('2019-20', selector, source, source_dir=tmp_path)


def test_annual_only_witness_uses_original_verifier_without_new_fixture_files(tmp_path, monkeypatch):
    result = {'old': 'proof'}
    monkeypatch.setattr(cohort, '_reparse_source_cohort', lambda *args: result)
    assert cohort._reparse_bound_source_cohort('2019-20', {}, {'players': []},
        source_dir=tmp_path) is result
