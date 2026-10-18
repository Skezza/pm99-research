"""Independent actual-native semantic readback for each ten-skill update."""
import gzip
import hashlib
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_package_compiler_v2 as compiler,season_historical_roster_audit_v1 as roster
from scripts import season_quality_only_delta_v1 as layer
from scripts.build_all_rating_calibrations_20261011 import ROOT,release_id
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from app.fdi_indexed import IndexedFDIFile

def audit(season,root=None,release_name=None):
    root=ROOT/season if root is None else root
    release=registry.load_registered_release(season,release_name or release_id(season))
    plan=pipeline.read_json_file(root/'quality-plan.json');base=registry.load_registered_release(season,plan['release_id'])
    raw=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes();old=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    index=IndexedFDIFile.from_bytes(raw);entries={e.record_id:e for e in index.entries}
    old_index=IndexedFDIFile.from_bytes(old);old_entries={e.record_id:e for e in old_index.entries}
    if set(entries)!=set(old_entries):raise ValueError('actual native directory changed')
    package=pipeline.read_json_file(release.package_path);before=pipeline.read_json_file(base.package_path)
    if plan['kind']=='season-rating-calibration-2015-english-v3':
        from scripts import season_2015_english_rating_calibration_v3 as english
        package=english.overlay(release)[0];before=english.overlay(base)[0]
    players={p['carrier_id']:p for p in package['players']};before_players={p['carrier_id']:p for p in before['players']}
    expected={r['carrier_id']:r for r in plan['updates']};readback=[]
    for carrier,entry in entries.items():
        payload=entry.decode_payload(raw);previous=old_entries[carrier].decode_payload(old)
        if carrier not in expected:
            if payload!=previous:raise ValueError('unselected actual player changed')
            continue
        identity=roster.native_player(payload,carrier);old_identity=roster.native_player(previous,carrier)
        if identity!=old_identity:raise ValueError('rating update changed native identity/position/role')
        if identity['family']=='dd6360':
            fields=compiler._read_native_dd6360_fields(payload,compiler._native_dd6360_role_start(payload))
            values=dict(zip(compiler.SKILLS,fields['skills']));values['handling']=fields['handling']
        elif identity['family']=='dd6361':
            values=dict(zip(compiler.SKILLS,[b^0x61 for b in payload[-16:-7]]));values['handling']=payload[-7]^0x61
        else:raise ValueError('unproved actual native rating family')
        if values!=players[carrier]['ratings']['values'] or values!=expected[carrier]['ratings']['values']:
            raise ValueError('actual ten native ability readback differs from recipe/source')
        unchanged={k:v for k,v in players[carrier].items() if k!='ratings'}
        if unchanged!={k:v for k,v in before_players[carrier].items() if k!='ratings'}:raise ValueError('non-rating recipe fields changed')
        position=players[carrier]['facts']['primary_position']
        if position!='G' and values['handling']>20:raise ValueError('outfield keeper handling regression')
        readback.append(dict(carrier_id=carrier,native_name=identity['name'],position=position,values=values))
    if len(readback)!=len(expected):raise ValueError('missing actual rated carriers')
    for key in before:
        if key not in ('players','artifacts','sources') and before[key]!=package[key]:raise ValueError('non-rating recipe section changed')
    for player in package['players']:
        if player['carrier_id'] not in expected and player!=before_players[player['carrier_id']]:raise ValueError('unselected recipe player changed')
    encoded=pipeline.canonical_json_bytes(readback);detail=root/'native-skill-readback-rows.json.gz'
    if detail.exists():
        if gzip.decompress(detail.read_bytes())!=encoded:raise ValueError('retained native readback detail differs')
    else:detail.write_bytes(gzip.compress(encoded,mtime=0))
    retained(root/'all-updated-players-native-readback.json',dict(season=season,release_id=release.release_id,
        manifest_sha256=release.manifest_sha256,actual_JUG_sha256=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
        all_selected_ten_skills_match_recipe=True,all_unselected_native_records_identical=True,
        non_rating_recipe_fields_identical=True,outfield_handling_guard_passed=True,updated_player_count=len(readback),
        players_path=registry.relative_workspace_path(detail),players_sha256=hashlib.sha256(encoded).hexdigest(),
        players_gzip_sha256=registry.sha256_file(detail)))
    return dict(season=season,updated_players=len(readback),actual_native_readback_passed=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('season');args=parser.parse_args()
    for s in registry.supported_seasons() if args.season=='all' else [args.season]:print(audit(s),flush=True)
