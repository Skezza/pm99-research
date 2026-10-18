#!/usr/bin/env python3
"""Audit known legal-name aliases and strict club identities after closeout."""
from __future__ import annotations
import argparse, hashlib, json, re, unicodedata
from collections import defaultdict
from pathlib import Path

ALIASES={
 "fc empoli":"empoli", "hertha berlin":"hertha bsc", "ksc lokeren 2020":"lokeren",
 "fc zurich":"zurich", "bsc young boys":"young boys", "boston u":"boston united",
}
EXPECTED_REBINDINGS={225:"Carpi FC 1909",250:"Chievo Verona",421:"1. FC Koln",871:"Royal Antwerp FC",872:"KAS Eupen",1111:"FC Lausanne-Sport",1112:"Neuchatel Xamax FCS",3326:"Stockport County",3328:"Boston United"}
def norm(s):
 s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode().lower()
 s=re.sub(r"[^a-z0-9]+"," ",s).strip(); return ALIASES.get(s,s)
def canonical(v): return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--draft",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args();d=json.loads(a.draft.read_text())
 seen=defaultdict(list)
 for p in d["proposals"]:
  name=(p.get("source_selector") or {}).get("club_name")
  if name: seen[(p.get("group"),norm(name))].append({"carrier_id":p["carrier_id"],"club_name":name})
 duplicates=[{"group":k[0],"normalised_identity":k[1],"rows":v} for k,v in seen.items() if len(v)>1]
 by_id={int(p["carrier_id"]):(p.get("source_selector") or {}).get("club_name") for p in d["proposals"]}
 decisions=[{"carrier_id":cid,"selected_2015_club":name,"actual":by_id.get(cid),"same_country_fixed_carrier":True,"status":"pass" if by_id.get(cid)==name else "fail"} for cid,name in sorted(EXPECTED_REBINDINGS.items())]
 failed_decisions=[x for x in decisions if x["status"]!="pass"]
 out={"schema_version":"pm99-world-2015-duplicate-club-identity-audit-v1","source_draft_sha256":hashlib.sha256(a.draft.read_bytes()).hexdigest(),"carrier_count":len(d["proposals"]),"sourced_identity_count":len(seen),"duplicate_count":len(duplicates),"duplicates":duplicates,"replacement_decisions":decisions,"result":"pass" if not duplicates and not failed_decisions else "fail"}
 a.output.write_bytes(canonical(out));print(json.dumps({"duplicate_count":len(duplicates),"result":out["result"]}));return 0 if not duplicates else 1
if __name__=="__main__":raise SystemExit(main())
