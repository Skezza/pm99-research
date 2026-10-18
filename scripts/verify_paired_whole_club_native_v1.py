"""Independent read-only facts, starters and preservation check for a pair."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts import prepare_paired_whole_club_dispositions_v1 as paired
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from app.editor_actions import _read_native_dd6360_fields


def verify(candidate, output):
    if output.exists():raise ValueError('paired independent proof is immutable')
    receipt=json.loads((candidate/'candidate-receipt.json').read_text())
    pair=json.loads(native.original(receipt['source_pair']).read_text())
    proposals=[json.loads(native.original(b).read_text()) for b in pair['proposals']]
    if paired.source_guard(pair,proposals)!=pair['source_guard']:raise ValueError('coupled source guard changed')
    base=registry.load_registered_release(pair['season'],pair['release_id'])
    package=json.loads((candidate/'season-package.json').read_text())
    native.package_v2.validate_package(package)
    data={n:(candidate/'game/DBDAT'/n).read_bytes() for n in receipt['native_hashes']}
    if any(registry.sha256_file(candidate/'game/DBDAT'/n)!=sha for n,sha in receipt['native_hashes'].items()):
        raise ValueError('paired native candidate hashes changed')
    jug=data['JUG98030.FDI'];eq=data['EQ98030.FDI'];ent=data['ENT98030.FDI']
    entries={e.record_id:e for e in native.IndexedFDIFile.from_bytes(jug).entries}
    countries=native.delta.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    players={p['id']:p for p in package['players']};clubs={c['id']:c for c in package['clubs']}
    rows=[];club_rows=[]
    for p in proposals:
        club=clubs[p['before_club']['id']];carrier=club['carrier_id']
        e=next(e for e in native.IndexedFDIFile.from_bytes(eq).entries if e.record_id==carrier)
        roster=native.parse_eq_external_team_roster_payload(eq[e.payload_offset:e.payload_offset+e.payload_length],{})
        if (roster is None or roster.mode_byte!=1 or roster.short_name!=p['new_club'] or roster.full_club_name!=p['new_club']
                or [(r.flag,r.player_record_id) for r in roster.rows]!=[(0,players[id]['carrier_id']) for id in club['roster_player_ids']]):
            raise ValueError('paired actual native club/roster readback differs from recipe')
        ordered=[]
        for r in p['allocation']:
            player=players[r['player_id']];raw=entries[r['carrier_id']].decode_payload(jug)
            actual=native.source.roster.native_player(raw,r['carrier_id']);end=actual['name_end']
            fields=_read_native_dd6360_fields(raw,end)
            expected_order=r.get('native_startup_order_after',r['native_startup_order_before'])
            if (actual['name'].casefold()!=player['name'].casefold() or actual['position']!=player['facts']['primary_position']
                    or {v for v in actual['roles'] if v!=98}!=set(player['facts']['fine_roles'])
                    or (raw[end]^0x61)!=expected_order):
                raise ValueError('paired native name, role or actual startup order differs from recipe')
            date=f"{fields['birth_year']:04d}-{fields['birth_month']:02d}-{fields['birth_day']:02d}"
            if date!=player['facts']['birth_date']:raise ValueError('paired native DOB differs from original/recipe')
            country=player['facts']['nationality']
            if fields['visible_nationality_code']!=native.delta.compiler._country_code(country,dict(countries)):
                raise ValueError('paired nationality differs from the actual runtime catalogue')
            for name in ('height_cm','weight_kg'):
                desired=player['facts'].get(name)
                if isinstance(desired,int) and fields[{'height_cm':'height_cm','weight_kg':'weight_kg'}[name]]!=desired:
                    raise ValueError('paired native secondary fact differs from recipe')
            rating=player['ratings']['values']
            if fields['skills'] != [rating[field] for field in native.delta.compiler.SKILLS] or fields['handling']!=rating['handling']:
                raise ValueError('paired native visible skills differ from deterministic recipe')
            if 1<=expected_order<=11:ordered.append((expected_order,r['carrier_id'],actual['name'],actual['position']))
            rows.append({'carrier_id':r['carrier_id'],'name':actual['name'],'source_name':player['source_name'],
                'birth_date':date,'position':actual['position'],'startup_order':expected_order,'native_facts_match':True})
        ordered.sort()
        source_XI={r['carrier_id'] for r in p['allocation'] if r['replacement']['membership']=='starting_xi'}
        if {r[1] for r in ordered}!=source_XI or len(ordered)!=11 or ordered[0][3]!='G' or sum(r[3]=='G' for r in ordered)!=1:
            raise ValueError('paired actual native XI does not contain the complete one-keeper original XI')
        club_rows.append({'carrier_id':carrier,'club':club['name'],'actual_native_XI':ordered,'roster_count':len(roster.rows)})
    allowed={'JUG98030.FDI':{r['carrier_id'] for p in proposals for r in p['allocation']},
        'EQ98030.FDI':{p['before_club']['carrier_id'] for p in proposals},
        'ENT98030.FDI':{m['manager_carrier_id'] for m in receipt['managers']}}
    for name,carriers in allowed.items():native.preserve_other_records((base.game_path/'DBDAT'/name).read_bytes(),data[name],carriers)
    proof={'schema_version':'pm99-independent-paired-native-readback-v1','season':pair['season'],
        'candidate':registry.relative_workspace_path(candidate),'candidate_receipt_sha256':registry.sha256_file(candidate/'candidate-receipt.json'),
        'players':rows,'clubs':club_rows,'all_unselected_native_records_identical':True,
        'registered':False,'runtime_proof':False,'historical_clearance':False}
    output.parent.mkdir(parents=True,exist_ok=True);pipeline.write_canonical_json(output,proof)
    return proof


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=verify(a.candidate,a.output)
    print(json.dumps({'native_players_verified':len(r['players']),'clubs':len(r['clubs']),'registered':False}),flush=True)
