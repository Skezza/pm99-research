#!/usr/bin/env python3
"""Rebase reviewed portrait clone targets to compiler-materialised JUG IDs."""
from __future__ import annotations
try:
    from scripts import json_storage_io_v1 as storage_io
except ModuleNotFoundError:
    import sys as _storage_sys
    from pathlib import Path as _StoragePath
    _storage_sys.path.insert(0, str(next(p for p in _StoragePath(__file__).resolve().parents if (p / 'scripts/json_storage_io_v1.py').is_file())))
    from scripts import json_storage_io_v1 as storage_io

import argparse, hashlib, json
from pathlib import Path
from typing import Any

SCHEMA="pm99-world-2015-asset-candidate-manifest-v1"
def canonical(v:Any)->bytes:return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--manifest",type=Path,required=True);ap.add_argument("--projection-receipt",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args()
 m=json.loads(storage_io.read_text(a.manifest));r=json.loads(storage_io.read_text(a.projection_receipt))
 if m.get("schema_version")!=SCHEMA:raise ValueError("wrong asset manifest schema")
 rows=r["coverage"]["recycle_clone_id_rebase"]
 mapping={int(x["candidate_clone_carrier_id"]):int(x["materialised_clone_carrier_id"]) for x in rows}
 if len(mapping)!=37 or len(set(mapping.values()))!=37:raise ValueError("projection must contain37 unique clone rebase rows")
 changed=[]
 for club in m["clubs"]:
  for p in club["players"]:
   allocation=p.get("recycle_allocation")
   if not allocation:continue
   old=int(allocation["appended_mode0_clone_carrier_id"])
   if old not in mapping:raise ValueError(f"clone {old} absent from projection")
   allocation["appended_mode0_clone_carrier_id"]=mapping[old]
   changed.append({"candidate_clone_carrier_id":old,"materialised_clone_carrier_id":mapping[old],"recycle_target_carrier_id":int(p["player_carrier_id"]),"team_carrier_id":int(club["carrier_id"])})
 if len(changed)!=37:raise ValueError(f"expected37 asset clone rows, got {len(changed)}")
 m.setdefault("sources",{})["clone_id_projection"]={"path":str(storage_io.resolve(a.projection_receipt)),"sha256":hashlib.sha256(storage_io.read_bytes(a.projection_receipt)).hexdigest()}
 m["clone_id_rebase"]={"count":37,"minimum":min(mapping.values()),"maximum":max(mapping.values()),"rows":sorted(changed,key=lambda x:x["materialised_clone_carrier_id"])}
 storage_io.write_bytes(a.output, canonical(m));print(json.dumps({"clone_count":37,"minimum":min(mapping.values()),"maximum":max(mapping.values())}));return 0
if __name__=="__main__":raise SystemExit(main())
