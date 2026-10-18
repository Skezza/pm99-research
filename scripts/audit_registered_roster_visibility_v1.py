#!/usr/bin/env python3
"""Read-only inventory of flag-one rows in authored English mode-0 rosters.

The two-byte 2007 Stoke control shows these rows absent from the rendered squad;
do not call the flag a loan/injury or silently clear it in other clubs. Bind each
finding to the exact current native bytes and recipe identity for a later repair.
"""
import argparse
import collections
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import season_package_compiler_v2
from scripts import season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_pipeline_v2 as pipeline
from app.fdi_indexed import IndexedFDIFile
from app.eq_jug_linked import parse_eq_external_team_roster_payload


def audit(output):
    if output.exists():raise ValueError('visibility evidence is immutable')
    seasons=[]
    for season in registry.supported_seasons():
        release=registry.load_preferred_release(season)
        eq_path=release.game_path/'DBDAT/EQ98030.FDI';eq=eq_path.read_bytes()
        records={e.record_id:e for e in IndexedFDIFile.from_bytes(eq).entries}
        findings=[];layers=[];club_count=0
        for label,package,path in planner.package_layers(release):
            layers.append({'layer':label,'path':registry.relative_workspace_path(path),'sha256':registry.sha256_file(path)})
            players={p['id']:p for p in package['players']}
            for club in package['clubs']:
                if not club['id'].startswith('english-club-'):continue
                e=records[club['carrier_id']]
                roster=parse_eq_external_team_roster_payload(eq[e.payload_offset:e.payload_offset+e.payload_length],{})
                if roster is None or roster.mode_byte!=0:raise ValueError('authored English roster cannot be parsed as mode zero')
                club_count+=1
                by_carrier={players[id]['carrier_id']:players[id] for id in club['roster_player_ids']}
                starters=set(club.get('opening',{}).get('starting_xi_player_ids',[]))
                for row in roster.rows:
                    if row.flag==0:continue
                    player=by_carrier.get(row.player_record_id)
                    if player is None:raise ValueError('native nonzero-flag row lacks exact authored player identity')
                    findings.append({'club_id':club['id'],'club':club['name'],'club_carrier_id':club['carrier_id'],
                        'player_id':player['id'],'carrier_id':row.player_record_id,'flag':row.flag,
                        'source_name':player.get('source_name') or player['name'],'birth_date':player['facts'].get('birth_date'),
                        'layer':label,'declared_starting_xi':player['id'] in starters,
                        'native_flag_offset':e.payload_offset+row.raw_row_offset,
                        'interpretation':'runtime-exclusion-observed-in-Stoke-pilot' if row.flag==1 else 'unproven-nonzero-flag'})
        seasons.append({'season':season,'release_id':release.release_id,'layers':layers,
            'eq_sha256':registry.sha256_file(eq_path),'jug_sha256':registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
            'authored_English_clubs_checked':club_count,'nonzero_flags':len(findings),
            'declared_starters_impacted':sum(r['declared_starting_xi'] for r in findings),'findings':findings})
        print(json.dumps({k:seasons[-1][k] for k in ('season','nonzero_flags','declared_starters_impacted')}),flush=True)
    result={'schema_version':'pm99-authored-English-roster-visibility-audit-v1','native_writes':0,
        'scope':'nonzero encoded roster flags; does not certify each club runtime or historical eligibility',
        'seasons':seasons,'nonzero_flag_rows':sum(s['nonzero_flags'] for s in seasons),
        'declared_starters_impacted':sum(s['declared_starters_impacted'] for s in seasons),
        'flag_counts':dict(collections.Counter(str(r['flag']) for s in seasons for r in s['findings']))}
    pipeline.write_canonical_json(output,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit(a.output);print(json.dumps({k:v for k,v in r.items() if k!='seasons'}),flush=True)
