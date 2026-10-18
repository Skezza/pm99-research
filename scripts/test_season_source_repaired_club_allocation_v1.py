import copy
import json
import pytest
from scripts import season_source_repaired_club_allocation_v1 as allocation
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts.test_season_duplicate_ownership_delta_v1 import fixture
from scripts.test_season_package_compiler_v2 import _indexed_fdi, _dd6361_player_payload


def desired(id, existing=(), sources=True):
    return {'source_player_id': id, 'existing_club_player_ids': list(existing),
        'source_person': {'source_player_id': id, 'birth_date': '1990-01-01'},
        'historical_fact_sources': [{'source_player': {'name': 'New Player', 'birth_date': '1990-01-01', 'position': 'D'},
                                    'raw_evidence': {'status': 'raw-source-reparsed'}}] if sources else [],
        'source_broad_position_unambiguous': True}


def test_existing_real_player_with_explicit_dob_correction_keeps_their_slot():
    plan = {'desired_matchday_people': [desired(1, ['existing-1'], False), desired(2, (), False), desired(3)]}
    before = copy.deepcopy(plan)
    existing, new = allocation.existing_and_new(plan, {2: 'corrected-existing-2'})
    assert existing == {1: 'existing-1', 2: 'corrected-existing-2'}
    assert [r['source_person']['source_player_id'] for r in new] == [3]
    assert plan == before


@pytest.mark.parametrize('problem', ['double-local', 'double-person', 'double-slot', 'missing-facts', 'conflicting-DOB'])
def test_ambiguous_roster_identity_never_allocates_new_slot(problem):
    plan = {'desired_matchday_people': [desired(1, ['existing-1']), desired(2)]}
    if problem == 'double-local': plan['desired_matchday_people'][0]['existing_club_player_ids'].append('existing-2')
    if problem == 'double-person': plan['desired_matchday_people'][1]['source_player_id'] = 1
    if problem == 'double-slot': plan['desired_matchday_people'][1]['existing_club_player_ids'] = ['existing-1']
    if problem == 'missing-facts': plan['desired_matchday_people'][1]['historical_fact_sources'] = []
    if problem == 'conflicting-DOB': plan['desired_matchday_people'][1]['source_person']['birth_date'] = '1991-01-01'
    with pytest.raises(ValueError): allocation.existing_and_new(plan, {})


def test_slot_assignment_is_exact_capacity_deterministic_and_keeper_safe():
    package, plan = fixture('dd6361')
    player = copy.deepcopy(package['players'][1])
    keeper = copy.deepcopy(player); keeper.update(id='keeper-slot', carrier_id=1)
    keeper['facts']['primary_position'] = 'G'
    player['facts']['primary_position'] = 'D'
    replacement = copy.deepcopy(plan['updates'][0]['replacement'])
    new_keeper = copy.deepcopy(replacement)
    new_keeper['source_person']['source_player_id'] = 100
    new_keeper['source_player'].update(name='Another King', position='G')
    original = _indexed_fdi([(1, '', _dd6361_player_payload(1)), (2, '', _dd6361_player_payload(2))])
    displaced, new = [player, keeper], [new_keeper, replacement]
    before = copy.deepcopy((displaced, new))
    result = allocation.fit_slots(original, displaced, new, {})
    assert allocation.fit_slots(original, list(reversed(displaced)), list(reversed(new)), {}) == result
    assert result[0]['carrier_id'] == 1 and result[0]['replacement']['source_player']['position'] == 'G'
    assert result[1]['carrier_id'] == 2 and result[1]['replacement']['source_player']['position'] == 'D'
    assert (displaced, new) == before
    with pytest.raises(ValueError, match='exact fixed capacity'):
        allocation.fit_slots(original, displaced, new[:1], {})


def test_outfield_change_is_allowed_only_as_explicit_whole_club_assignment():
    package, plan = fixture('dd6361')
    player = copy.deepcopy(package['players'][1]); player['facts']['primary_position'] = 'D'
    replacement = copy.deepcopy(plan['updates'][0]['replacement']); replacement['source_player']['position'] = 'F'
    original = _indexed_fdi([(2, '', _dd6361_player_payload(2))])
    result = allocation.fit_slots(original, [player], [replacement], {})
    assert result[0]['broad_role_change'] == {'before': 'D', 'after': 'F'}
    replacement['source_player']['position'] = 'G'
    with pytest.raises(ValueError, match='cannot fit'):
        allocation.fit_slots(original, [player], [replacement], {})


def grid():
    points = [(1,80,40),(2,63,28),(3,61,73),(4,61,7.5),(5,63,52.5),
              (6,43,52),(7,43,28),(8,23,40),(9,18,15),(10,18,65),(11,3,40)]
    items = ''.join(f'<div class="formation-player-container" style="top:{top}%;left:{left}%;">'
                   f'<a href="/x/profil/spieler/{id}">Player</a></div>' for id,top,left in points)
    return f'<div class="large-6"><a href="/x/startseite/verein/11">Club</a>{items}</div>'.encode()


def test_source_pitch_membership_mirrors_lateral_order_not_team_number_prefix():
    roles = allocation.source_grid(grid(), 11, range(1,12), '4-2-3-1')
    assert {id:r[0] for id,r in roles.items()} == {
        1:'GK',3:'RB',5:'RCB',2:'LCB',4:'LB',6:'DM',7:'DM',10:'RW',8:'AM',9:'LW',11:'ST'}
    with pytest.raises(ValueError, match='exact club'):
        allocation.source_grid(grid(), 1, range(1,12), '4-2-3-1')


@pytest.mark.parametrize('problem', ['person', 'missing-style', 'duplicate-lane', 'line-tie', 'range'])
def test_uncertain_source_deployment_stays_unallocated(problem):
    raw = grid()
    if problem == 'person': raw = raw.replace(b'/spieler/11',b'/spieler/12')
    if problem == 'missing-style': raw = raw.replace(b'left:40%;',b'')
    if problem == 'duplicate-lane': raw = raw.replace(b'left:52.5%;',b'left:28%;')
    if problem == 'line-tie': raw = raw.replace(b'top:43%;',b'top:61%;')
    if problem == 'range': raw = raw.replace(b'left:40%;',b'left:110%;')
    with pytest.raises(ValueError): allocation.source_grid(raw,11,range(1,12),'4-2-3-1')


def test_biography_is_replayed_and_cannot_be_rebound_to_another_slot(tmp_path, monkeypatch):
    monkeypatch.setattr(allocation.registry,'ROOT',tmp_path)
    page=tmp_path/'original.html'
    page.write_text('<h1>Ben White</h1><table class="infobox"><tr><td class="bday">1997-10-08</td></tr></table>')
    url='https://en.wikipedia.org/wiki/Ben_White'; sha=allocation.registry.sha256_file(page)
    receipt=tmp_path/'original.source.json';receipt.write_text(json.dumps({'url':url,'sha256':sha}))
    claim={'source_player_id':335721,'source_name':'Ben White','player_id':'existing-white','carrier_id':9109,
           'before':'1997-11-08','after':'1997-10-08'}
    evidence={'schema_version':'pm99-bounded-named-DOB-corroboration-v1','rows':[{**claim,
        'corroboration':{'provider':'wikipedia','url':url,'path':page.name,'sha256':sha,
            'receipt_path':receipt.name,'observed_birth_date':'1997-10-08'}}]}
    plan={'local_DOB_conflicts':[claim]}
    assert allocation.corroborated_dates(plan,evidence)=={335721:'existing-white'}
    changed=copy.deepcopy(evidence);changed['rows'][0]['carrier_id']=100
    with pytest.raises(ValueError,match='different existing slot'):
        allocation.corroborated_dates(plan,changed)
    page.write_text(page.read_text().replace('1997-10-08','1998-10-08'))
    with pytest.raises(ValueError,match='biography changed'):
        allocation.corroborated_dates(plan,evidence)
