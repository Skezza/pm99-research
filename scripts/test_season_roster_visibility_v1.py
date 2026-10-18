import copy
import json
import sys
from pathlib import Path

import pytest

from scripts import season_roster_visibility_v1 as visibility
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'upstream/pm99-skezmod-db-editor/tests'))
from test_eq_roster_visibility import native


def layer():
    return {'schema_version': visibility.SCHEMA, 'policy': visibility.POLICY,
        'season': '2015-16', 'clubs': [{'club_id': 'english-club-a', 'carrier_id': 351,
            'expected_rows': [[11, 1], [12, 0], [13, 1]],
            'players': [{'carrier_id': 11}, {'carrier_id': 13}]}]}


def test_exact_scope_idempotent_recipe_replay_and_immutable_preimage():
    old = native(); plan = layer(); before = copy.deepcopy(plan)
    new, changes = visibility.apply(old, plan, exact_before=True)
    assert sum(a!=b for a,b in zip(old,new)) == 2
    assert len(changes) == 2 and plan == before
    assert visibility.apply(new, plan) == (new, [])
    with pytest.raises(ValueError, match='preimage'):
        visibility.apply(new, plan, exact_before=True)


@pytest.mark.parametrize('problem', ['foreign', 'order', 'new-player', 'flag', 'unselected', 'duplicate-club'])
def test_changed_membership_order_flags_policy_or_scope_refused(problem):
    plan = layer(); data = native()
    if problem == 'foreign': data = native(mode=1)
    elif problem == 'order': plan['clubs'][0]['expected_rows'].reverse()
    elif problem == 'new-player': plan['clubs'][0]['players'][0]['carrier_id'] = 99
    elif problem == 'flag': plan['clubs'][0]['expected_rows'][0][1] = 2
    elif problem == 'unselected': plan['clubs'][0]['players'].pop()
    elif problem == 'duplicate-club': plan['clubs'] *= 2
    with pytest.raises(ValueError): visibility.apply(data, plan)


def test_artifact_replay_hash_season_and_path_are_bound(tmp_path):
    plan = layer(); path = tmp_path/'visibility.json'
    pipeline.write_canonical_json(path, plan)
    recipe = {'season': {'start_year': 2015, 'end_year': 2016}, 'artifacts': [{
        'id': visibility.PREFIX+'2015-16', 'relative_path': 'visibility.json',
        'sha256': visibility.registry.sha256_file(path)}]}
    old = native(); new, changes = visibility.replay(old, recipe, tmp_path/'package.json')
    assert len(changes) == 2 and new != old
    recipe['season']['start_year'] = 2014
    with pytest.raises(ValueError, match='another season'): visibility.replay(old, recipe, tmp_path/'package.json')
    recipe['season']['start_year'] = 2015
    recipe['artifacts'][0]['relative_path'] = '../visibility.json'
    with pytest.raises(ValueError, match='unsafe'): visibility.replay(old, recipe, tmp_path/'package.json')
    recipe['artifacts'][0]['relative_path'] = 'visibility.json'
    path.write_text('{}')
    with pytest.raises(ValueError, match='hash'): visibility.replay(old, recipe, tmp_path/'package.json')


def test_recipe_binding_does_not_change_people_clubs_or_other_artifacts():
    from scripts.test_season_package_compiler_v2 import _native_package
    package = _native_package(); old = copy.deepcopy(package)
    result = visibility.bind(package, layer())
    assert package == old
    for key in old.keys()-{'artifacts','proofs'}: assert result[key] == old[key]
    assert all(a in result['artifacts'] for a in old['artifacts'])


def test_actual_compiler_replays_visibility_before_context_and_rejects_bad_input_before_writes(tmp_path):
    from scripts.test_season_package_compiler_v2 import _write_fixture_base, _copy_base
    from scripts.season_package_compiler_v2 import compile_package_to_tree
    base, recipe = _write_fixture_base(tmp_path)
    package = json.loads(recipe.read_text())
    carrier = package['clubs'][0]['carrier_id']
    rows = visibility.native_rows((base/'DBDAT/EQ98030.FDI').read_bytes(), carrier)
    # The synthetic clean base has no excluded rows. Bind the policy to a
    # synthetic excluded source row, then prove the actual compiler clears it.
    data = bytearray((base/'DBDAT/EQ98030.FDI').read_bytes())
    from app.fdi_indexed import IndexedFDIFile
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    e = next(e for e in IndexedFDIFile.from_bytes(data).entries if e.record_id==carrier)
    parsed = parse_eq_external_team_roster_payload(bytes(data[e.payload_offset:e.payload_offset+e.payload_length]), {})
    data[e.payload_offset+parsed.rows[0].raw_row_offset] = 1
    (base/'DBDAT/EQ98030.FDI').write_bytes(data)
    # Compilation reconstructs its authored roster IDs in this exact order.
    people = {p['id']:p['carrier_id'] for p in package['players']}
    ids = [people[id] for id in package['clubs'][0]['roster_player_ids']]
    plan = layer(); plan['clubs'] = [{'club_id':'english-club-synthetic', 'carrier_id':carrier,
        'expected_rows':[[id, int(i==0)] for i,id in enumerate(ids)], 'players':[{'carrier_id':ids[0]}]}]
    package = visibility.bind(package,plan)
    pipeline.write_canonical_json(recipe.parent/'roster-visibility.json',plan)
    packages.write_canonical_package(recipe,package)
    output = _copy_base(base,tmp_path/'output')
    receipt = compile_package_to_tree(package_path=recipe,base_tree=base,materialisation_tree=output)
    assert len(receipt['authored_roster_visibility_changes']) == 1
    assert all(flag==0 for _,flag in visibility.native_rows((output/'DBDAT/EQ98030.FDI').read_bytes(),carrier))
    (recipe.parent/'roster-visibility.json').write_text('{}')
    rejected = _copy_base(base,tmp_path/'rejected'); before = pipeline.build_tree_inventory(rejected)
    with pytest.raises(ValueError,match='hash'):
        compile_package_to_tree(package_path=recipe,base_tree=base,materialisation_tree=rejected)
    assert pipeline.build_tree_inventory(rejected)==before


def test_flag_only_delta_is_not_skipped_and_preserves_all_other_files(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from scripts import publish_historical_role_delta_v1 as publish
    from scripts.test_season_package_compiler_v2 import _native_package, _indexed_fdi, _dd6361_player_payload
    monkeypatch.setattr(publish,'ROOT',tmp_path)
    monkeypatch.setattr(publish.registry,'ROOT',tmp_path)
    monkeypatch.setattr(publish.registry,'LOCAL_ROOT',tmp_path/'registry')
    game = tmp_path/'old-game'
    for name in publish.registry.REQUIRED_GAME_FILES:
        p=game/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'unchanged synthetic asset')
    (game/'DBDAT/JUG98030.FDI').write_bytes(_indexed_fdi([(2,'',_dd6361_player_payload(2,role=3))]))
    old_eq=native();(game/'DBDAT/EQ98030.FDI').write_bytes(old_eq)
    package=_native_package(); recipe=tmp_path/'old-package.json'
    packages.write_canonical_package(recipe,package)
    inv=pipeline.build_tree_inventory(game)
    inv_path=tmp_path/'old-inventory.json';pipeline.write_canonical_json(inv_path,inv)
    chain=tmp_path/'old-chain.json';receipt=tmp_path/'old-receipt.json'
    pipeline.write_canonical_json(chain,{'synthetic':True});pipeline.write_canonical_json(receipt,{'synthetic':True})
    manifest_path=tmp_path/'old-manifest.json'
    manifest=pipeline.create_release_manifest(season='2015-16',
        verified_base=pipeline.make_verified_base_descriptor(base_id='test-base',tree=game),
        season_document=pipeline.canonical_json_document_descriptor(recipe,document_id='season-package'),output_inventory=inv)
    pipeline.write_canonical_json(manifest_path,manifest)
    release=SimpleNamespace(season='2015-16',release_id='old',game_path=game,package_path=recipe,
        inventory_path=inv_path,build_chain_path=chain,compiler_receipt_path=receipt,
        release_manifest_path=manifest_path,manifest_sha256=publish.registry.sha256_file(manifest_path),
        locator={'game_inventory_fingerprint':inv['files_fingerprint']})
    monkeypatch.setattr(publish.registry,'load_preferred_release',lambda s:release)
    monkeypatch.setattr(visibility,'verify_bound',lambda r,p:None)
    plan={'season':'2015-16','release_id':'old','package_sha256':publish.registry.sha256_file(recipe),
        'jug_sha256':publish.registry.sha256_file(game/'DBDAT/JUG98030.FDI'),'updates':[],'unresolved':[]}
    plan_path=tmp_path/'empty-role-plan.json';pipeline.write_canonical_json(plan_path,plan)
    vis_path=tmp_path/'vis.json';pipeline.write_canonical_json(vis_path,layer())
    result=publish.publish('2015-16',plan_path,release_id='test-visibility',visibility_plan_path=vis_path)
    new=Path(result['game']); assert result['changed_players']==0
    after=pipeline.build_tree_inventory(new); difference=pipeline.inventory_difference(inv,after)
    assert [p['path'] for p in difference['changed']]==['DBDAT/EQ98030.FDI']
    assert difference['only_left']==difference['only_right']==[]
    assert (game/'DBDAT/EQ98030.FDI').read_bytes()==old_eq
    assert (new/'DBDAT/EQ98030.FDI').stat().st_ino != (game/'DBDAT/EQ98030.FDI').stat().st_ino
    assert (new/'DBDAT/JUG98030.FDI').stat().st_ino == (game/'DBDAT/JUG98030.FDI').stat().st_ino
    compiled=json.loads((new.parent/'role-delta-compiler.json').read_text())
    assert len(compiled['visibility_changes'])==2
    assert compiled['compilation_mode']=='known-good-baseline-authored-roster-visibility-delta'
    assert json.loads((new.parent/'season-package.json').read_text())==visibility.bind(package,layer())
    with pytest.raises(ValueError,match='already exists'):
        publish.publish('2015-16',plan_path,release_id='test-visibility',visibility_plan_path=vis_path)
