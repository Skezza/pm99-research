#!/usr/bin/env python3
"""Remove rejected recycle rows and preserve native shared-carrier portraits."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from typing import Any
def canonical(v:Any)->bytes:return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument('--manifest',type=Path,required=True);ap.add_argument('--role-demand',type=Path,required=True);ap.add_argument('--projection-receipt',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 m=json.loads(a.manifest.read_text());d=json.loads(a.role_demand.read_text());r=json.loads(a.projection_receipt.read_text())
 c=r['coverage']
 if c.get('recycle_edge_count')!=0 or c.get('recycle_fallback_slot_count')!=37:raise ValueError('projection is not clone-free37 fallback')
 preserved={int(x['player_carrier_id']) for x in d['demands']}
 if len(preserved)!=37:raise ValueError('role demand does not identify37 native carriers')
 removed=[];marked=[]
 for club in m['clubs']:
  keep=[]
  for p in club['players']:
   if p.get('recycle_allocation'):
    removed.append({'team_carrier_id':int(club['carrier_id']),'slot_index':int(p['slot_index']),'rejected_recycle_target_carrier_id':int(p['player_carrier_id'])})
    continue
   if int(p['player_carrier_id']) in preserved:
    p['portrait']={'status':'preserve-native-carrier-portrait','source_policy':'v11 clone-free native shared-carrier preservation'}
    marked.append(int(p['player_carrier_id']))
   keep.append(p)
  club['players']=keep
 if len(removed)!=37 or len(set(marked))!=36:raise ValueError(f'unexpected clone-free portrait partition removed={len(removed)} preserved={len(set(marked))}')
 m['coverage']['recycled_player_carrier_count']=0;m['coverage']['clone_free_removed_recycle_row_count']=37;m['coverage']['clone_free_preserved_shared_portrait_count']=36
 m.setdefault('sources',{})['clone_free_projection']={'path':str(a.projection_receipt.resolve()),'sha256':hashlib.sha256(a.projection_receipt.read_bytes()).hexdigest()}
 m['clone_free_disposition']={'recycle_operation_count':0,'removed_rejected_recycle_rows':removed,'native_preserve_carrier_ids':sorted(preserved),'preserve_manifest_row_count':len(set(marked)),'note':'37th invalid native carrier has no remaining source-manifest row; leaving it absent preserves its native portrait'}
 a.output.write_bytes(canonical(m));print(json.dumps({'removed':37,'native_preserve_carriers':37,'manifest_preserve_rows':36,'clone_operations':0}));return 0
if __name__=='__main__':raise SystemExit(main())
