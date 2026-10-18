"""Independent literal readback and unchanged-data proof for five countries."""
import copy
from scripts import season_source_verified_player_changes_v1 as changes
from scripts.publish_confirmed_country_changes_20261017 import FOLDER,RELEASE
from scripts.season_within_club_reserve_repair_v1 import native_facts


def main():
    actual=changes.registry.load_registered_release('2013-14',RELEASE)
    plan_path=changes.registry.ROOT/actual.locator['sourced_profile_assignment_plan_path']
    plan=changes.pipeline.read_json_file(plan_path)
    base=changes.registry.load_registered_release('2013-14',plan['release_id'])
    changes.verify(base,plan)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    offsets=[i for i,(a,b) in enumerate(zip(before,after)) if a!=b]
    assert len(before)==len(after) and len(offsets)==5
    assert set(offsets)=={r['native_mask']['file_offset'] for r in plan['updates']}
    old=changes.pipeline.read_json_file(base.package_path)
    new=changes.pipeline.read_json_file(actual.package_path)
    reverted=copy.deepcopy(new)
    selected={r['carrier_id']:r for r in plan['updates']}
    observations=[]
    for actor in reverted['players']:
        if actor['carrier_id'] not in selected:continue
        row=selected[actor['carrier_id']]
        assert actor['facts']['nationality']==row['nationality']=='ENG'
        raw=native_facts(after,actor['carrier_id'])
        index=changes.IndexedFDIFile.from_bytes(after)
        entry=next(e for e in index.entries if e.record_id==actor['carrier_id'])
        payload=entry.decode_payload(after)
        end=changes.native_player(payload,actor['carrier_id'])['name_end']
        codes=changes.compiler._extract_country_codes_from_textos(actual.game_path/'DBDAT/TEXTOS.PKF')
        assert payload[end+8]^0x61==changes.compiler._country_code('ENG',codes)
        assert raw['birth_date']==row['before']['facts']['birth_date']
        observations.append(dict(carrier_id=actor['carrier_id'],country='ENG',birth_date=raw['birth_date']))
        actor['facts']['nationality']=row['before']['facts']['nationality']
        if 'fact_fallbacks' in row['before']:actor['fact_fallbacks']=row['before']['fact_fallbacks']
    reverted['artifacts']=[a for a in reverted['artifacts'] if a['id']!=changes.artifact_id(plan)]
    assert reverted==old
    difference=changes.pipeline.inventory_difference(
        changes.pipeline.build_tree_inventory(base.game_path),
        changes.pipeline.build_tree_inventory(actual.game_path))
    assert not difference['only_left'] and not difference['only_right']
    assert [r['path'] for r in difference['changed']]==['DBDAT/JUG98030.FDI']
    changes.pipeline.assert_tree_matches_inventory(base.game_path,changes.pipeline.read_json_file(base.inventory_path))
    result=dict(release_id=RELEASE,source_plan=changes.binding(plan_path),
        actual_manifest_sha256=actual.manifest_sha256,observations=observations,
        native_changed_bytes=5,all_other_game_files_identical=True,
        all_other_recipe_data_identical=True,parent_inventory_unchanged=True,
        preferred_still_parent=changes.registry.load_preferred_release('2013-14').release_id==base.release_id)
    changes.pipeline.write_canonical_json(FOLDER/'independent-native-recipe-proof.json',result)
    print(result,flush=True)


if __name__=='__main__':main()
