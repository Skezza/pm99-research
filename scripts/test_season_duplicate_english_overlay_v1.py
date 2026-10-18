import copy
from types import SimpleNamespace
import pytest
from scripts import season_duplicate_english_overlay_v1 as overlay
from scripts import season_package_v2 as package
from scripts import season_release_registry_v1 as registry


def fixture(tmp_path,monkeypatch):
    from scripts.test_season_duplicate_ownership_delta_v1 import fixture as normal
    english,plan=normal('dd6361');path=tmp_path/'english.json';path.write_bytes(package.canonical_json_bytes(english))
    main={'players':[],'clubs':[]};layers=[('main',main,tmp_path/'main.json'),('english',english,path)]
    monkeypatch.setattr(registry,'ROOT',tmp_path)
    monkeypatch.setattr(overlay.planner,'package_layers',lambda release:layers)
    monkeypatch.setattr(overlay.soccerbase,'native_starters',lambda *args:(set(),{}))
    release=SimpleNamespace(season='2015-16',game_path=tmp_path)
    row=plan['updates'][0];row.update(layer='english',club_id=row['before']['club_id'])
    plan['allow_english_overlay_replacements']=True
    plan['bindings'].update(english_overlay=overlay.binding(release),
        published_person_supplement={'path':'original-people'},published_transfer_supplement={'path':'original-transfers'},
        opening_person_supplement_policy='original-identity-policy',soccerbase_opening_sources={'original':'bound'})
    return release,plan,english,main


def test_current_exclusive_modern_English_reserve_can_be_explicitly_bound_without_mutation(tmp_path,monkeypatch):
    release,plan,english,main=fixture(tmp_path,monkeypatch)
    before=copy.deepcopy((plan,english,main));overlay.validate_binding(release,plan)
    assert (plan,english,main)==before


@pytest.mark.parametrize('problem',['no-opt-in','wrong-season','changed-hash','wrong-path','wrong-artifact',
    'missing-people','missing-history','missing-native-guard','changed-prior-row','other-club',
    'changed-carrier','shared-main-carrier','wrong-layout','declared-starter','actual-starter'])
def test_English_overlay_gate_never_waives_source_identity_shared_carrier_or_starting_guards(tmp_path,monkeypatch,problem):
    release,plan,english,main=fixture(tmp_path,monkeypatch);row=plan['updates'][0]
    if problem=='no-opt-in':plan['allow_english_overlay_replacements']=False
    if problem=='wrong-season':release.season='2014-15'
    if problem=='changed-hash':plan['bindings']['english_overlay']['sha256']='changed'
    if problem=='wrong-path':plan['bindings']['english_overlay']['path']='elsewhere.json'
    if problem=='wrong-artifact':plan['bindings']['english_overlay']['artifact_id']='wrong'
    if problem=='missing-people':del plan['bindings']['published_person_supplement']
    if problem=='missing-history':del plan['bindings']['published_transfer_supplement']
    if problem=='missing-native-guard':del plan['bindings']['soccerbase_opening_sources']
    if problem=='changed-prior-row':row['before']['facts']['birth_date']='1980-01-01'
    if problem=='other-club':row['club_id']='different'
    if problem=='changed-carrier':row['carrier_id']=9999
    if problem=='shared-main-carrier':main['players'].append(copy.deepcopy(english['players'][1]))
    if problem=='wrong-layout':
        english['players'][1]['carrier_family']='dd6360';row['before']['carrier_family']='dd6360'
    if problem=='declared-starter':english['clubs'][0]['opening']['starting_xi_player_ids']=[row['player_id']]
    if problem=='actual-starter':monkeypatch.setattr(overlay.soccerbase,'native_starters',lambda *args:({row['carrier_id']},{}))
    with pytest.raises(ValueError):overlay.validate_binding(release,plan)


def test_main_only_legacy_plan_needs_no_English_binding():
    overlay.validate_binding(None,{'updates':[{'layer':'main'}],'bindings':{}})
