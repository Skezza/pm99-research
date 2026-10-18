"""Independent six-byte-only role proof, retaining the original first XI."""
import copy
import json
from app.fdi_indexed import IndexedFDIFile
from scripts import season_tff_sourced_opening_xi_v1 as source
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


def verify(season,release_id,plan_path,output):
    if output.exists():raise ValueError('role proof is immutable')
    plan=json.loads(plan_path.read_text());base=registry.load_registered_release(season,plan['release_id'])
    release=registry.load_registered_release(season,release_id);source.verify_broad_roles(base,plan)
    saved=registry.ROOT/release.locator['historical_role_plan_path']
    if json.loads(saved.read_text())!=plan:raise ValueError('saved source role plan differs')
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();after=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    if len(before)!=len(after):raise ValueError('role delta changed native container length')
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(before).entries};allowed=set()
    for row in plan['updates']:
        e=entries[row['carrier_id']];old=audit.native_player(e.decode_payload(before),row['carrier_id'])
        start=e.payload_offset+old['name_end']+2
        if after[start:start+6]!=bytes([row['fine_roles'][0]+1,0,0,0,0,0]):
            raise ValueError('native role vector differs from source-bound editorial fallback')
        allowed.update(range(start,start+6))
    changed={i for i,(a,b) in enumerate(zip(before,after)) if a!=b}
    if not changed<=allowed:raise ValueError('role delta changed other native bytes')
    original=json.loads(base.package_path.read_text());package=json.loads(release.package_path.read_text())
    people=copy.deepcopy(original['players']);updates={r['player_id']:r for r in plan['updates']}
    for p in people:
        if p['id'] in updates:p['facts']['fine_roles']=updates[p['id']]['fine_roles']
    if package['players']!=people:raise ValueError('role delta changed other player facts/ratings')
    for key in original.keys()-{'players','artifacts','proofs'}:
        if package[key]!=original[key]:raise ValueError('role delta changed other recipe collections')
    diff=pipeline.inventory_difference(pipeline.build_tree_inventory(base.game_path),pipeline.build_tree_inventory(release.game_path))
    if diff['only_left'] or diff['only_right'] or [r['path'] for r in diff['changed']]!=['DBDAT/JUG98030.FDI']:
        raise ValueError('role delta changed another game/kit/photo/manager file')
    from scripts.season_package_compiler_v2 import _extract_country_codes_from_textos
    eq=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes();countries=_extract_country_codes_from_textos(release.game_path/'DBDAT/TEXTOS.PKF')
    replayed,changes=source.replay(after,eq,package,release.package_path,countries)
    if replayed!=after or len(changes)!=1:raise ValueError('first-XI recipe replay loses corrected labels')
    opening=json.loads((registry.ROOT/plan['opening_plan_path']).read_text())
    index={e.record_id:e for e in IndexedFDIFile.from_bytes(after).entries}
    for row in opening['starting_xi']:
        native=audit.native_player(index[row['carrier_id']].decode_payload(after),row['carrier_id'])
        if source.conservative_role(row['source']['position'],native['roles'][0]) is not None:
            raise ValueError('source first XI still has a contradictory role label')
    result={'schema_version':'pm99-source-XI-broad-role-independent-byte-proof-v1','season':season,'release_id':release_id,
        'source_release_id':base.release_id,'corrected_labels':len(plan['updates']),'native_bytes_changed':len(changed),
        'all_other_native_bytes_identical':True,'other_recipe_facts_ratings_identical':True,
        'whole_game_only_JUG_changed':True,'durable_first_XI_replay':True,
        'plan_sha256':registry.sha256_file(saved),'package_sha256':registry.sha256_file(release.package_path),
        'JUG_sha256':registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
        'scope':'source broad-position contradictions only; conservative central labels are editorial, not precise role sources'}
    pipeline.write_canonical_json(output,result);return result
