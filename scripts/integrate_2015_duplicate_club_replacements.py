#!/usr/bin/env python3
"""Rebind duplicate club carriers to distinct same-country dated squads."""

from __future__ import annotations

import argparse, hashlib, json, sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.reconcile_2015_world_source_player_facts import _read_fifa_rows, build_reconciliation

GROUP_COUNTRY = {"english-non-league": "eng"}

def canonical_bytes(v: Any) -> bytes: return (json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))+"\n").encode()
def digest(v: Any) -> str: return hashlib.sha256(canonical_bytes(v)).hexdigest()

def integrate(registry, capture, draft, replacements, fifa_csv):
    clubs = [dict(x) for x in capture["clubs"]] + [dict(x) for x in replacements["clubs"]]
    replacement_by_id = {int(x["candidate_carrier_id"]): x for x in replacements["clubs"]}
    # Boston's acquired squad was incorrectly bound to Bishop Auckland. Rebind
    # that exact dated selector to the native Boston carrier, while Stockport
    # takes the vacated slot.
    boston = next(x for x in capture["clubs"] if int(x.get("candidate_carrier_id", -1)) == 3326 and x["club_name"] == "Boston United")
    replacement_by_id[3328] = boston
    proposals=[]
    for old in draft["proposals"]:
        row=dict(old); cid=int(row["carrier_id"]); club=replacement_by_id.get(cid)
        if club:
            expected=GROUP_COUNTRY.get(str(row.get("group")), str(row.get("group")))
            if expected != club["country_catalog"]: raise ValueError(f"country crossing at {cid}")
            if len(club["players"]) < int(row["fixed_roster_slot_count"]): raise ValueError(f"short replacement at {cid}")
            selector={k:club[k] for k in ("country_catalog","competition_catalog","club_name","source_path","source_sha256")}
            row.update(source_country_catalog=club["country_catalog"], source_competition_catalogs=[club["competition_catalog"]], source_selector=selector,
                       source_club_name=club["club_name"], source_player_row_count=len(club["players"]), allocation_method="explicit-same-country-duplicate-closeout",
                       status="source-squad-ready", source_note="Distinct dated 2015 club; fixed country and carrier topology preserved")
        proposals.append(row)
    # A source squad may drive only one final carrier.
    keys=[tuple((p.get("source_selector") or {}).get(k) for k in ("country_catalog","competition_catalog","club_name","source_path","source_sha256")) for p in proposals if p.get("source_selector")]
    if len(keys)!=len(set(keys)): raise ValueError("final proposal selectors are not unique")
    capture2={"schema_version":capture["schema_version"],"source":{"title":"2015 sources with duplicate-club closeout","inputs":{"base_capture_sha256":digest(capture),"replacement_capture_sha256":digest(replacements)}},"season":capture["season"],"clubs":clubs,
              "summary":{"club_count":len(clubs),"player_count":sum(len(x.get("players",[])) for x in clubs)}}
    draft2={"schema_version":draft["schema_version"],"policy":draft["policy"]+"; distinct-same-country-club-identities", "registry_sha256":digest(registry),"source_capture_sha256":digest(capture2),
            "coverage":{"carrier_count":len(proposals),"status_counts":dict(sorted(Counter(str(x.get("status")) for x in proposals).items())),"source_squad_ready_slot_count":sum(int(x["fixed_roster_slot_count"]) for x in proposals if x.get("status")=="source-squad-ready")},"proposals":sorted(proposals,key=lambda x:int(x["carrier_id"]))}
    fifa,sha=_read_fifa_rows(fifa_csv); recon=build_reconciliation(registry=registry,draft=draft2,source_capture=capture2,fifa_rows=fifa,fifa_sha256=sha)
    recon["duplicate_club_closeout"]={"replacement_carrier_ids":sorted(replacement_by_id),"policy":"same-country fixed-size rebinding; dated squads only"}
    return capture2,draft2,recon

def main():
    ap=argparse.ArgumentParser();
    for n in ("registry","base-capture","base-draft","replacement-capture","fifa16-player-csv","capture-output","draft-output","reconciliation-output"): ap.add_argument("--"+n,type=Path,required=True)
    a=ap.parse_args(); load=lambda p:json.loads(p.read_text()); vals=integrate(load(a.registry),load(a.base_capture),load(a.base_draft),load(a.replacement_capture),a.fifa16_player_csv)
    for p,v in zip((a.capture_output,a.draft_output,a.reconciliation_output),vals): p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(canonical_bytes(v))
    print(json.dumps({"draft":vals[1]["coverage"],"reconciliation":vals[2]["coverage"]},sort_keys=True)); return 0

if __name__=="__main__": raise SystemExit(main())
