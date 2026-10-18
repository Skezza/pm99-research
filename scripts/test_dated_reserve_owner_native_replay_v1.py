"""Native-write gate must reproduce the positive annual ownership witness."""
import copy
import json
from types import SimpleNamespace
import pytest
from scripts import season_common_date_ownership_v1 as checker
from scripts import season_dated_reserve_owner_v1 as reserve
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_person_supplement_v1 as supplement
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts.test_season_common_date_ownership_v1 import supplemented_claim


def bound_reserve_plan(tmp_path, monkeypatch):
    plan = supplemented_claim(tmp_path, monkeypatch)
    doc = json.loads((tmp_path / 'opening.json').read_text())
    owner, displaced = doc['clubs']
    owner['evidence']['starting_xi'].pop('10')
    owner['evidence']['starting_xi']['21'] = 'Other Player'
    displaced['evidence']['date'] = '2005-08-14'
    (tmp_path / 'opening.json').write_text(json.dumps(doc))
    events = [{'date': '2004-07-01', 'from_club_id': 3, 'to_club_id': 1,
               'from_club': 'Previous', 'to_club': 'Owner'},
              {'date': '2006-07-01', 'from_club_id': 1, 'to_club_id': 4,
               'from_club': 'Owner', 'to_club': 'Next'}]
    monkeypatch.setattr(public, 'merge_bound', lambda people, old, bindings: (people, {10: events}, {}))
    layers = planner.package_layers(None)
    clubs = {c['id']: c for _, layer, _ in layers for c in layer['clubs']}
    for c in clubs.values():
        c['division'] = 'Premier League'
    candidates = [p for _, layer, _ in layers for p in layer['players']]
    captures = [{'club_name': 'owner', 'country_catalog': 'eng', 'source_path': 'annual.json',
        'source_sha256': 'annualsha', 'players': [{'name': 'Published Name', 'birth_date': '1980-01-01'}]}]
    verifier = SimpleNamespace(verify=lambda _: {'status': 'raw-source-reparsed',
        'local_path': 'original-annual.html', 'source_sha256': 'originalsha'})
    monkeypatch.setattr(roster, 'load_sources', lambda _: (captures, []))
    monkeypatch.setattr(roster, 'SourceVerifier', lambda *args: verifier)
    people, _ = supplement.extend(None, None, None, None, None)
    evidence = {'owner': owner['evidence'], 'displaced': displaced['evidence']}
    row = plan['updates'][0]
    winner, basis, witness = reserve.decide(candidates, evidence, row['duplicate_source_person'],
        events, clubs, captures, verifier, people)
    assert winner['id'] == 'p1' and basis == reserve.BASIS
    row.update(ownership_basis=basis, retained_owner_squad_membership=witness,
        owner_evidence=owner['evidence'], replacement_opening_evidence=displaced['evidence'])
    plan.update(allow_dated_reserve_owners=True)
    plan['bindings'].update(dated_reserve_owner_policy=reserve.POLICY,
        published_person_supplement={'path': 'bound-original-persons'},
        published_transfer_supplement={'path': 'bound-original-histories'})
    return plan, captures


def test_positive_annual_witness_is_reconstructed_before_native_write(tmp_path, monkeypatch):
    plan, _ = bound_reserve_plan(tmp_path, monkeypatch)
    checker.verify_plan_claims(None, plan)


@pytest.mark.parametrize('field', ['source_player', 'source_person', 'raw_evidence', 'opening_dates', 'source_club_id'])
def test_each_forged_annual_witness_field_is_rejected(tmp_path, monkeypatch, field):
    plan, _ = bound_reserve_plan(tmp_path, monkeypatch)
    plan['updates'][0]['retained_owner_squad_membership'][field] = 'forged'
    with pytest.raises(ValueError, match='annual owner witness'):
        checker.verify_plan_claims(None, plan)


def test_removing_the_original_membership_invalidates_saved_owner_claim(tmp_path, monkeypatch):
    plan, captures = bound_reserve_plan(tmp_path, monkeypatch)
    captures[0]['players'].clear()
    with pytest.raises(ValueError, match='every original club claim'):
        checker.verify_plan_claims(None, plan)


def test_witness_without_opt_in_never_bypasses_original_matchday_policy(tmp_path, monkeypatch):
    plan, _ = bound_reserve_plan(tmp_path, monkeypatch)
    del plan['allow_dated_reserve_owners']
    with pytest.raises(ValueError, match='explicit bound original'):
        checker.verify_plan_claims(None, plan)


def test_opt_in_still_requires_bound_source_inputs_before_planning():
    with pytest.raises(ValueError, match='dated reserve owners require'):
        planner.plan('2005-06', {}, {}, {}, None, None, allow_dated_reserve_owners=True)
