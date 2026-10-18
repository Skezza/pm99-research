import copy
import json
from types import SimpleNamespace
import pytest
from scripts import season_common_date_ownership_v1 as policy


def inputs():
    players = [{'id': 'p1', 'club_id': 'owner'}, {'id': 'p2', 'club_id': 'displaced'}]
    sources = {key: {'source_club_id': n, 'date': '2005-08-13',
        'match_page_date_independently_published': True,
        'starting_xi': {str(i): 'Published Name' for i in range(start, start + 11)},
        'substitutes': {}} for key, n, start in [('owner', 1, 10), ('displaced', 2, 100)]}
    return players, sources, {'source_player_id': 10}, []


def test_positive_playing_squad_at_identical_date_does_not_need_complete_transfer_dataset():
    players, sources, person, events = inputs()
    assert policy.decide(players, sources, person, events)[0] == players[0]
    assert policy.decide(list(reversed(players)), sources, person, events)[0] == players[0]


@pytest.mark.parametrize('problem', ['different-date', 'unpublished-date', 'missing-source',
    'same-real-club', 'incomplete-xi', 'two-positive-squads', 'bench-only', 'missing-person', 'known-transfer-conflict'])
def test_common_date_policy_refuses_each_missing_or_conflicting_proof(problem):
    players, sources, person, events = inputs()
    if problem == 'different-date': sources['displaced']['date'] = '2005-08-14'
    if problem == 'unpublished-date': sources['displaced']['match_page_date_independently_published'] = False
    if problem == 'missing-source': del sources['displaced']
    if problem == 'same-real-club': sources['displaced']['source_club_id'] = 1
    if problem == 'incomplete-xi': sources['displaced']['starting_xi'].pop('100')
    if problem == 'two-positive-squads': sources['displaced']['substitutes']['10'] = 'Published Name'
    if problem == 'bench-only':
        sources['owner']['starting_xi'].pop('10')
        sources['owner']['starting_xi']['21'] = 'Other Person'
        sources['owner']['substitutes']['10'] = 'Published Name'
    if problem == 'missing-person': person = None
    if problem == 'known-transfer-conflict':
        events = [{'date': '2004-07-01', 'from_club_id': 3, 'to_club_id': 2,
                   'from_club': 'Previous', 'to_club': 'Displaced'},
                  {'date': '2006-07-01', 'from_club_id': 2, 'to_club_id': 4,
                   'from_club': 'Displaced', 'to_club': 'Next'}]
    assert policy.decide(players, sources, person, events)[0] is None


def bound_claim(tmp_path, monkeypatch, third=False):
    from scripts import season_duplicate_ownership_plan_v1 as planner
    from scripts import season_release_registry_v1 as registry
    players, sources, person, events = inputs()
    person.update(name='Published Name', birth_date='1980-01-01')
    for player in players:
        player.update(name='Published Name', facts={'birth_date': '1980-01-01'})
    if third:
        players.append({'id': 'p3', 'club_id': 'third'})
        sources['third'] = copy.deepcopy(sources['owner'])
        sources['third']['source_club_id'] = 3
    clubs = [{'id': p['club_id'], 'carrier_id': i, 'name': p['club_id']}
             for i, p in enumerate(players)]
    opening = {'clubs': [{'carrier_id': c['carrier_id'], 'club': c['name'],
        'status': 'original-first-fixture-reparsed', 'evidence': sources[c['id']]} for c in clubs]}
    (tmp_path / 'opening.json').write_text(json.dumps(opening))
    monkeypatch.setattr(registry, 'ROOT', tmp_path)
    monkeypatch.setattr(planner, 'package_layers', lambda _: [('main', {'clubs': clubs, 'players': players}, None)])
    monkeypatch.setattr(policy.transfer, 'unique_person', lambda p, people: person)
    pin = {'path': 'snapshot', 'pinned_receipt_path': 'receipt'}
    monkeypatch.setattr(policy.transfer, 'load_snapshot', lambda *args: ({}, {10: events}, {}, pin))
    row = {'ownership_basis': policy.BASIS, 'duplicate_source_person': person,
        'retained_owner_player_id': 'p1', 'club_id': 'displaced',
        'owner_evidence': sources['owner'], 'replacement_opening_evidence': sources['displaced']}
    return {'updates': [row], 'bindings': {'snapshot': pin, 'opening_path': 'opening.json'}}, pin


def test_plan_verifier_reconstructs_bound_original_evidence(tmp_path, monkeypatch):
    plan, _ = bound_claim(tmp_path, monkeypatch)
    policy.verify_plan_claims(SimpleNamespace(), plan)


def test_plan_verifier_detects_hidden_third_positive_club(tmp_path, monkeypatch):
    plan, _ = bound_claim(tmp_path, monkeypatch, third=True)
    with pytest.raises(ValueError, match='every original club claim'):
        policy.verify_plan_claims(SimpleNamespace(), plan)


def test_plan_verifier_refuses_rewritten_opening_claim(tmp_path, monkeypatch):
    plan, _ = bound_claim(tmp_path, monkeypatch)
    plan['updates'][0]['owner_evidence'] = dict(plan['updates'][0]['owner_evidence'], date='2005-08-14')
    with pytest.raises(ValueError, match='declared evidence differs'):
        policy.verify_plan_claims(SimpleNamespace(), plan)


def test_plan_verifier_refuses_changed_snapshot_receipt(tmp_path, monkeypatch):
    plan, pin = bound_claim(tmp_path, monkeypatch)
    monkeypatch.setattr(policy.transfer, 'load_snapshot', lambda *args: ({}, {}, {}, dict(pin, path='different')))
    with pytest.raises(ValueError, match='snapshot binding differs'):
        policy.verify_plan_claims(SimpleNamespace(), plan)


def test_old_transfer_bracket_plans_do_not_require_common_date_snapshot(monkeypatch):
    monkeypatch.setattr(policy.transfer, 'load_snapshot', lambda *args: pytest.fail('old plan acquired new inputs'))
    policy.verify_plan_claims(None, {'updates': [{'ownership_basis': 'positive-opening-membership-and-consistent-dated-transfer-brackets'}]})


def supplemented_claim(tmp_path, monkeypatch):
    from scripts import season_opening_person_supplement_v1 as supplement
    from scripts import season_historical_roster_audit_v1 as roster
    real_unique = policy.transfer.unique_person
    plan, _ = bound_claim(tmp_path, monkeypatch)
    monkeypatch.setattr(policy.transfer, 'unique_person', real_unique)
    plan['season'] = '2005-06'
    plan['bindings'].update(opening_person_supplement_policy=supplement.POLICY,
                            captures=[], review_path='review.json')
    (tmp_path / 'review.json').write_text('{}')
    reserve = {'source_player_id': 99, 'name': 'Reserve Person', 'birth_date': '1985-01-01'}
    row = plan['updates'][0]
    row['replacement'] = {'source_player': {'name': 'Reserve Person', 'birth_date': '1985-01-01'},
                          'source_person': reserve}
    index = {('publishedname', '1980-01-01'): {10: row['duplicate_source_person']},
             ('reserveperson', '1985-01-01'): {99: reserve}}
    monkeypatch.setattr(roster, 'load_sources', lambda _: ([], []))
    monkeypatch.setattr(roster, 'SourceVerifier', lambda *args: SimpleNamespace())
    monkeypatch.setattr(supplement, 'extend', lambda *args: (index, {}))
    return plan


def test_supplemented_identity_joins_are_reconstructed_before_ownership_write(tmp_path, monkeypatch):
    plan = supplemented_claim(tmp_path, monkeypatch)
    policy.verify_plan_claims(None, plan)


def test_supplemented_plan_refuses_an_invented_replacement_identity(tmp_path, monkeypatch):
    plan = supplemented_claim(tmp_path, monkeypatch)
    plan['updates'][0]['replacement']['source_person'] = {'source_player_id': 999}
    with pytest.raises(ValueError, match='replacement identity does not reproduce'):
        policy.verify_plan_claims(None, plan)


def test_supplemented_plan_refuses_other_capture_bindings(tmp_path, monkeypatch):
    plan = supplemented_claim(tmp_path, monkeypatch)
    plan['bindings']['captures'] = [{'path': 'other', 'sha256': 'changed'}]
    with pytest.raises(ValueError, match='captures differ'):
        policy.verify_plan_claims(None, plan)


def test_supplemented_plan_refuses_an_unknown_identity_policy(tmp_path, monkeypatch):
    plan = supplemented_claim(tmp_path, monkeypatch)
    plan['bindings']['opening_person_supplement_policy'] = 'unknown-v2'
    with pytest.raises(ValueError, match='unsupported opening identity'):
        policy.verify_plan_claims(None, plan)


def test_public_history_replay_proves_different_opening_dates_before_native_write(tmp_path, monkeypatch):
    from scripts import season_duplicate_ownership_plan_v1 as planner
    from scripts import season_public_identity_and_history_inputs_v1 as binder
    from scripts import season_published_transfer_history_v1 as history
    from scripts.test_original_public_supplement_merges_v1 import raw
    from scripts.test_season_published_transfer_history_v1 import fixture

    plan = supplemented_claim(tmp_path, monkeypatch)
    document = json.loads((tmp_path / 'opening.json').read_text())
    owner, displaced = document['clubs']
    owner['evidence']['source_club_id'] = 2
    displaced['evidence'].update(source_club_id=4, date='2005-08-14')
    (tmp_path / 'opening.json').write_text(json.dumps(document))
    row = plan['updates'][0]
    row.update(owner_evidence=owner['evidence'], replacement_opening_evidence=displaced['evidence'],
               ownership_basis='positive-opening-membership-and-consistent-dated-transfer-brackets')
    candidates = [{'id': 'p1', 'club_id': 'owner'}, {'id': 'p2', 'club_id': 'displaced'}]
    evidence = {'owner': owner['evidence'], 'displaced': displaced['evidence']}
    assert planner.decide_owner(candidates, evidence, row['duplicate_source_person'], [])[0] is None

    published = fixture()
    second = copy.deepcopy(published['data']['history']['terminated'][0])
    second.update(id='21', relativeUrl='/player/transfers/spieler/10/transfer_id/21')
    second['transferSource']['clubId'] = '2'
    second['transferDestination']['clubId'] = '3'
    second['details']['date'] = '2006-07-01T00:00:00+02:00'
    published['data']['history']['terminated'].append(second)
    supplement = {'schema_version': history.SCHEMA, 'policy': history.POLICY, 'players': [dict(
        raw(tmp_path, published, history.BASE + '10'), status='raw-history-parsed',
        player_id=10, events=history.parse(published, 10))]}
    monkeypatch.setattr(history, 'ROOT', tmp_path)
    path = tmp_path / 'transfer-supplement.json'
    path.write_text(json.dumps(supplement))
    plan['bindings']['published_transfer_supplement'] = binder.binding(path, history.POLICY)
    policy.verify_plan_claims(None, plan)

    # A changed raw chronology is not allowed just because a plan says it passed.
    (tmp_path / 'original.json').write_text('{}')
    with pytest.raises(ValueError, match='original public transfer response changed'):
        policy.verify_plan_claims(None, plan)


@pytest.mark.parametrize('forged', [False, True])
def test_new_reserve_position_is_replayed_from_independently_reparsed_source(tmp_path, monkeypatch, forged):
    from scripts import season_duplicate_ownership_plan_v1 as planner
    from scripts import season_public_identity_and_history_inputs_v1 as public
    from scripts import season_sourced_reserve_role_policy_v1 as roles
    plan = supplemented_claim(tmp_path, monkeypatch)
    plan.update(resolution_policy=roles.RESOLUTION, allow_sourced_outfield_reserve_role_changes=True)
    plan['bindings'].update(reserve_role_policy=roles.POLICY,
        published_person_supplement={'path': 'fixture-people'},
        published_transfer_supplement={'path': 'fixture-transfers'})
    # Binder replay is tested against real original-response fixtures in its
    # own lane; this fixture isolates the native gate's sourced-position check.
    monkeypatch.setattr(public, 'merge_bound', lambda people, events, bindings: (people, events, {}))
    opening = json.loads((tmp_path / 'opening.json').read_text())
    opening['clubs'][1]['evidence']['substitutes']['99'] = 'Reserve Person'
    (tmp_path / 'opening.json').write_text(json.dumps(opening))
    row = plan['updates'][0]
    row.update(player_id='p2', before={'facts': {'primary_position': 'D'}},
        replacement_opening_evidence=opening['clubs'][1]['evidence'],
        reserve_role_change={'before': 'D', 'after': 'M', 'policy': roles.POLICY})
    row['replacement']['source_player']['position'] = 'M'
    row['replacement']['opening_eligibility'] = {'method': 'positive-first-fixture-substitute-id'}
    trusted = copy.deepcopy(row['replacement'])
    monkeypatch.setattr(planner, 'verified_replacements', lambda *args: [trusted])
    if forged:
        row['replacement']['source_player']['position'] = 'F'
        row['reserve_role_change']['after'] = 'F'
        with pytest.raises(ValueError, match='position do not reproduce'):
            policy.verify_plan_claims(None, plan)
    else:
        policy.verify_plan_claims(None, plan)
