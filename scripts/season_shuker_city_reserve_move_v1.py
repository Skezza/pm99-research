"""Source-bound Shuker Macc-to-City ownership/order correction.

Uses the existing package bind, native startup-order writer, and indexed EQ
roster writer. The 11v11 chronology establishes City membership, not a City
first-team appearance. No registered game is written here.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from bs4 import BeautifulSoup

from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, patch_initial_orders, read_initial_order
from app.xor import xor_encode, xor_decode
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_package_compiler_v2 as compiler
from scripts.season_opening_order_repair_v1 import native_owners
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA="pm99-source-bound-shuker-city-reserve-move-v1"
MODE="same-player-macc-to-city-order-and-six-person-bench-correction-v1"
SEASON="2000-01"
PARENT="sourced-woolley-mcloughlin-opening-20261024-r220a"
PREFIX="shuker-city-reserve-move-v1-"
WEB_ROOT=registry.ROOT/".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/blackburn-berkovic-city-replacement-research-v1"
PROFILE=WEB_ROOT/"chris_shuker_11v11.html"
RECEIPT=WEB_ROOT/"capture-receipt.json"
PROFILE_SHA="d268e1bfd8b4cd0421677c5d0a9ea7d1d7ff662ae2dfe79960b1de875fe5be85"
RECEIPT_SHA="2e65edc7a36263abd0cce120b7e8e84ecb4e0e8884e103a8028e2f44d80c6f81"
INPUT=registry.ROOT/".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/shuker-ownership-move-v1/shuker-city-move-input-v2.json"
CLUB_CITY=311
CLUB_MACC=382
PLAYER=32945
_CACHE: dict[str,dict[str,Any]]={}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sha_file(path: Path) -> str:
    return registry.sha256_file(path)


def _parent(base) -> dict[str, Any]:
    return {"season":base.season,"release_id":base.release_id,
        "manifest_sha256":base.manifest_sha256,
        "package_sha256":_sha_file(base.package_path),
        "jug_sha256":_sha_file(base.game_path/"DBDAT/JUG98030.FDI"),
        "eq_sha256":_sha_file(base.game_path/"DBDAT/EQ98030.FDI")}


def _implementations():
    from app import player_initial_order, eq_jug_linked
    return [dict(name=name,path=registry.relative_workspace_path(path),sha256=_sha_file(path))
        for name,path in sorted({"adapter":Path(__file__).resolve(),
            "package_schema":Path(packages.__file__).resolve(),
            "order_writer":Path(player_initial_order.__file__).resolve(),
            "eq_roster_codec":Path(eq_jug_linked.__file__).resolve()}.items())]


def _sources() -> dict[str, Any]:
    for path, expected in ((PROFILE,PROFILE_SHA),(RECEIPT,RECEIPT_SHA)):
        if path.is_symlink() or not path.is_file() or _sha_file(path)!=expected:
            raise ValueError("retained Shuker source or receipt changed")
    receipt=pipeline.read_json_file(RECEIPT)
    rows=[r for r in receipt.get("captures",[]) if r.get("path","").endswith("/chris_shuker_11v11.html")]
    if (len(rows)!=1 or rows[0].get("sha256")!=PROFILE_SHA or rows[0].get("http_status")!=200
        or rows[0].get("requested_url")!="https://www.11v11.com/players/chris-shuker-8124/"):
        raise ValueError("Shuker captured-source receipt does not bind exact provider profile")
    raw=PROFILE.read_bytes()
    text=" ".join(BeautifulSoup(raw,"html.parser").get_text(" ",strip=True).split())
    anchors=("Chris Shuker","Date of birth 09 May 1982","Nationality English",
        "Manchester City 21 Sep 1999 17 Mar 2004","Macclesfield Town 22 Mar 2001 05 May 2001 L",
        "2000-01 Macclesfield Town League Division 3")
    if any(anchor not in text for anchor in anchors):
        raise ValueError("Shuker original biography/career chronology no longer supports admission")
    # The two source intervals are deliberately read as chronology, not match
    # appearance claims. August 2000 is within City membership and before Macc.
    if not ("21 Sep 1999" in text and "19 Aug 2000" not in text):
        raise ValueError("Shuker City chronology not retained")
    return {"profile":{"path":registry.relative_workspace_path(PROFILE),"sha256":PROFILE_SHA,
            "url":rows[0]["requested_url"],"provider_id":"8124"},
        "receipt":{"path":registry.relative_workspace_path(RECEIPT),"sha256":RECEIPT_SHA},
        "positive_membership":{"club":"Manchester City","from":"1999-09-21","through":"2004-03-17",
            "target_date":"2000-08-19","basis":"target date falls inside source-reported City tenure"},
        "negative_competing_owner":{"club":"Macclesfield Town","from":"2001-03-22","through":"2001-05-05",
            "basis":"source-reported Macc loan begins after target date"},
        "scope":"period club membership only; no claim of 19 Aug 2000 first-team appearance"}


def _read_request(input_path) -> tuple[Path,dict]:
    p=Path(input_path)
    if not p.is_absolute(): p=registry.ROOT/p
    p=p.resolve()
    registry.relative_workspace_path(p)
    if p.is_symlink() or not p.is_file(): raise ValueError("typed Shuker input must be retained regular file")
    request=pipeline.read_json_file(p)
    if (set(request)!={"schema","mode","season","release_id","parent","case_id","actor","source_scope"}
        or request.get("schema")!=SCHEMA+"-input" or request.get("mode")!=MODE
        or request.get("season")!=SEASON or request.get("release_id")!=request.get("parent",{}).get("release_id")
        or request.get("case_id")!="ef44711c99bae4bd72a93e2db07cfb58697bef13a372b94d64c352a1d35033be"
        or request.get("actor")!={"carrier_id":PLAYER,"player_id":"english-player-32945",
            "name":"Chris Shuker","birth_date":"1982-05-09","from_club_carrier":CLUB_MACC,
            "to_club_carrier":CLUB_CITY,"native_city_shirt":{"policy":"preserve-existing-mode1"}}
        or request.get("source_scope")!="positive City membership 21 Sep 1999 to 17 Mar 2004; Macc loan begins 22 Mar 2001; not a City opening appearance"):
        raise ValueError("exact Shuker typed source request required; unknown request fields are rejected")
    return p,request


def _club(package, carrier):
    rows=[c for c in package["clubs"] if c["carrier_id"]==carrier]
    if len(rows)!=1: raise ValueError("one exact club carrier required")
    return rows[0]


def _actor(package):
    rows=[p for p in package["players"] if p["carrier_id"]==PLAYER]
    if len(rows)!=1: raise ValueError("one exact Shuker player carrier required")
    return rows[0]


def _postimages(base, request, input_path, expected=None):
    parent=_parent(base)
    if (base.season,base.release_id)!=(SEASON,request.get("release_id")) or parent!=request["parent"]:
        raise ValueError("registered parent files do not match the typed request")
    sources=_sources()
    implementations=_implementations()
    input_sha=digest(input_path.read_bytes())
    cache_key=digest(packages.canonical_json_bytes({"parent":parent,"input_sha256":input_sha,
        "sources":sources,"implementations":implementations,"schema":SCHEMA,"mode":MODE}))
    if cache_key in _CACHE:
        cached=_CACHE[cache_key]
        if expected is not None and cached["plan"]!=expected:
            keys=sorted(k for k in set(cached["plan"])|set(expected) if cached["plan"].get(k)!=expected.get(k))
            raise ValueError("cached Shuker plan does not reproduce exact expected plan: "+repr(keys))
        return cached
    package=pipeline.read_json_file(base.package_path)
    jug=(base.game_path/"DBDAT/JUG98030.FDI").read_bytes()
    eq=(base.game_path/"DBDAT/EQ98030.FDI").read_bytes()
    city,macc=_club(package,CLUB_CITY),_club(package,CLUB_MACC)
    actor=_actor(package)
    if (city["name"],macc["name"],actor["id"],actor["name"],actor["source_name"],
        actor["facts"]["birth_date"],actor["club_id"]) != (
        "Manchester City","Macclesfield Town","english-player-32945","Chris Shuker","Chris Shuker",
        "1982-05-09",macc["id"]):
        raise ValueError("r220a Shuker identity/current owner preimage differs")
    if (len(city["roster_player_ids"]),len(macc["roster_player_ids"]))!=(24,25):
        raise ValueError("exact City24/Macc25 roster counts required")
    if (macc["roster_player_ids"].count(actor["id"])!=1 or actor["id"] in city["roster_player_ids"]
        or macc.get("opening",{}).get("substitute_player_ids",[]).count(actor["id"])!=1):
        raise ValueError("Shuker must be the single Macc reserve/declared-substitute row and absent from City")
    if (actor["id"] in macc.get("opening",{}).get("starting_xi_player_ids",[])
        or actor["id"] in city.get("opening",{}).get("starting_xi_player_ids",[])
        or actor["id"] in city.get("opening",{}).get("substitute_player_ids",[])
        or len(macc.get("opening",{}).get("substitute_player_ids",[]))!=7):
        raise ValueError("Shuker must be Macc bench-only preimage; City and Macc XI/bench evidence differs")
    if any(a.get("id","").startswith(PREFIX) for a in package.get("artifacts",[])):
        raise ValueError("parent already contains a Shuker move artifact; do not double-apply")
    owners=native_owners(eq)
    if owners.get(PLAYER)!={CLUB_MACC}: raise ValueError("exact Macc native owner preimage required")
    ix=IndexedFDIFile.from_bytes(jug); entries={e.record_id:e for e in ix.entries}
    player_by_id={p["id"]:p for p in package["players"]}
    order_by_club={}
    for club in (city,macc):
        carriers=[player_by_id[pid]["carrier_id"] for pid in club["roster_player_ids"]]
        orders={carrier:read_initial_order(entries[carrier].decode_payload(jug)).order for carrier in carriers}
        if sorted(orders.values())!=list(range(1,len(carriers)+1)):
            raise ValueError(f"{club['name']} startup order is not contiguous before move")
        order_by_club[club["carrier_id"]]=orders
    if order_by_club[CLUB_MACC][PLAYER]!=13:
        raise ValueError("approved Macc slot 13 preimage differs")
    before_actor=copy.deepcopy(actor)
    before_city=copy.deepcopy(city["roster_player_ids"])
    before_macc=copy.deepcopy(macc["roster_player_ids"])
    before_subs=copy.deepcopy(macc["opening"]["substitute_player_ids"])
    source_order_changes=[]
    for carrier,old in order_by_club[CLUB_MACC].items():
        if carrier==PLAYER: continue
        new=old-1 if old>13 else old
        if new!=old:
            source_order_changes.append({"carrier_id":carrier,
                "name":read_initial_order(entries[carrier].decode_payload(jug)).name,
                "before":old,"after":new})
    source_order_changes.append({"carrier_id":PLAYER,
        "name":read_initial_order(entries[PLAYER].decode_payload(jug)).name,
        "before":13,"after":25})
    # Keep one row per changed carrier: Shuker moves to City25; Macc14..25 compact.
    if len({r["carrier_id"] for r in source_order_changes})!=13:
        raise ValueError("expected Shuker plus twelve compacted Macc startup-order records")
    result=copy.deepcopy(package)
    out_city,out_macc=_club(result,CLUB_CITY),_club(result,CLUB_MACC)
    out_actor=_actor(result)
    out_macc["roster_player_ids"].remove(out_actor["id"])
    out_city["roster_player_ids"].append(out_actor["id"])
    out_macc["opening"]["substitute_player_ids"].remove(out_actor["id"])
    out_actor["club_id"]=out_city["id"]
    out_actor["facts"]["shirt_number"]={"policy":"preserve-existing-mode1"}
    out_actor["fact_fallbacks"]=[f for f in out_actor.get("fact_fallbacks",[]) if f.get("field")!="shirt_number"]
    aid=PREFIX+"proposal"; proof={"artifact_id":aid,"grade":"source-receipt"}
    out_actor["proof"]=copy.deepcopy(proof)
    out_actor["fact_fallbacks"].append({"field":"shirt_number","method":"preserve-existing-mode1",
        "proof":copy.deepcopy(proof),"value":{"policy":"preserve-existing-mode1"},
        "reason":"The native value 7 is the former Macc carrier number; no City shirt number is sourced."})
    result["artifacts"]=[a for a in result["artifacts"] if a.get("id")!=aid]
    plan={"schema":SCHEMA,"mode":MODE,"season":SEASON,"release_id":base.release_id,
        "source_input":{"path":registry.relative_workspace_path(input_path),"sha256":digest(input_path.read_bytes())},
        "request":request,"parent":parent,"source_evidence":sources,"implementation_bindings":implementations,
        "actor_before":before_actor,"city_roster_before":before_city,"macc_roster_before":before_macc,
        "macc_substitutes_before":before_subs,
        "city_roster_after":copy.deepcopy(out_city["roster_player_ids"]),
        "macc_roster_after":copy.deepcopy(out_macc["roster_player_ids"]),
        "macc_substitutes_after":copy.deepcopy(out_macc["opening"]["substitute_player_ids"]),
        "startup_order_changes":source_order_changes,
        "roster_counts":{"before":{"City311":24,"Macc382":25},"after":{"City311":25,"Macc382":24}},
        "appearance_claim":"No City first-team appearance is claimed; source supports dated roster ownership only.",
        "scope":"Move unchanged Shuker identity Macc382→City311 reserve order25; compact remaining Macc orders14..25→13..24; remove him from Macc declared substitutes. Preserve City XI/bench, Macc XI, player identity/skills, portrait bytes, managers, tactics, and every unrelated record; replace the former Macc shirt number with an explicit native-preserve fallback."}
    plan["transaction_id"]=digest(packages.canonical_json_bytes(plan))[:24]
    aid=artifact_id(plan);proof={"artifact_id":aid,"grade":"source-receipt"}
    out_actor["proof"]=copy.deepcopy(proof)
    for fallback in out_actor["fact_fallbacks"]:
        if fallback.get("field")=="shirt_number": fallback["proof"]=copy.deepcopy(proof)
    out_actor["fact_fallbacks"].sort(key=lambda f:f["field"])
    result["artifacts"].append({"id":aid,"kind":"season-input","sha256":digest(_artifact_bytes(plan),),
        "media_type":"application/json","relative_path":filename(plan)})
    result["artifacts"].sort(key=lambda a:a["id"])
    sid="source-"+aid
    result["sources"].append({"id":sid,"title":"Dated Chris Shuker Manchester City tenure and later Macclesfield loan chronology",
        "uri":sources["profile"]["url"],"proof_grade":"source-receipt","evidence_artifact_id":aid})
    result["sources"].sort(key=lambda s:s["id"])
    result["proofs"].append({"id":"proof-"+aid,"artifact_id":aid,"grade":"source-receipt",
        "covers":["City-tenure-includes-2000-opening-date","Macc-loan-starts-2001","same-person-owner-and-order-move"]})
    result["proofs"].sort(key=lambda p:p["id"])
    packages.validate_package(result,strict=False)
    replacements=[OrderReplacement(r["carrier_id"],r["name"],r["before"],r["after"]) for r in source_order_changes]
    post_jug=patch_initial_orders(jug,replacements)
    post_ix=IndexedFDIFile.from_bytes(post_jug); post_entries={e.record_id:e for e in post_ix.entries}
    post_orders={}
    for c in (out_city,out_macc):
        post_orders[c["carrier_id"]]=sorted(read_initial_order(
            post_entries[player_by_id[pid]["carrier_id"]].decode_payload(post_jug)).order for pid in c["roster_player_ids"])
    if post_orders!={CLUB_CITY:list(range(1,26)),CLUB_MACC:list(range(1,25))}:
        raise ValueError("native City/Macc postorder must be contiguous 1..25 and 1..24")
    # Existing indexed EQ codec rewrites only the two selected roster rows.
    eqix=IndexedFDIFile.from_bytes(eq); eq_entries={e.record_id:e for e in eqix.entries}; changed={}
    for c in (out_city,out_macc):
        e=eq_entries[c["carrier_id"]]
        decoded=e.decode_payload(eq)
        metadata=compiler.extract_indexed_team_payload_metadata(xor_encode(decoded))
        if int(metadata["record_mode"])!=0:
            raise ValueError("City and Macc require the existing mode0 linked-roster writer")
        carriers=[player_by_id[pid]["carrier_id"] for pid in c["roster_player_ids"]]
        changed[c["carrier_id"]]=xor_decode(compiler._rewrite_roster_tail(xor_encode(decoded),carriers))
    post_eq=compiler._rebuild_indexed(eq,eqix,changed)
    out_eqix=IndexedFDIFile.from_bytes(post_eq);out_entries={e.record_id:e for e in out_eqix.entries}
    for c in (out_city,out_macc):
        e=out_entries[c["carrier_id"]]
        payload=post_eq[e.payload_offset:e.payload_offset+e.payload_length]
        parsed=compiler.parse_eq_external_team_roster_payload(payload,{})
        expected_ids=[player_by_id[pid]["carrier_id"] for pid in c["roster_player_ids"]]
        if parsed is None or parsed.mode_byte!=0 or [r.player_record_id for r in parsed.rows]!=expected_ids:
            raise ValueError("native EQ roster does not match complete requested recipe order")
    preserve_other_records(jug,post_jug,{r["carrier_id"] for r in source_order_changes})
    preserve_other_records(eq,post_eq,{CLUB_CITY,CLUB_MACC})
    owners_after=native_owners(post_eq)
    if owners_after.get(PLAYER)!={CLUB_CITY}:
        raise ValueError("post-move native owner must be City311 only")
    # Opening semantics: City XI/bench unmodified; Macc XI exact and Shuker removed from its subs.
    if out_city.get("opening")!=city.get("opening"):
        raise ValueError("City XI/bench metadata changed")
    if out_macc.get("opening",{}).get("starting_xi_player_ids")!=macc.get("opening",{}).get("starting_xi_player_ids"):
        raise ValueError("Macc opening XI metadata changed")
    if len(out_macc["opening"]["substitute_player_ids"])!=6:
        raise ValueError("Macc declared substitute count should fall from seven to six")
    if (before_actor["ratings"]!=out_actor["ratings"]
        or before_actor["person_id"]!=out_actor["person_id"]
        or before_actor["facts"]["fine_roles"]!=out_actor["facts"]["fine_roles"]):
        raise ValueError("player person identity, ratings, and fine roles must remain exact")
    plan["native_postimages"]={"JUG98030.FDI":digest(post_jug),"EQ98030.FDI":digest(post_eq)}
    # Native postimage proof is part of the stable outer plan; transaction ID is
    # recomputed after those facts, then artifact/source/proof IDs are rebound.
    plan["transaction_id"]=digest(packages.canonical_json_bytes({k:v for k,v in plan.items() if k!="transaction_id"}))[:24]
    aid=artifact_id(plan); proof={"artifact_id":aid,"grade":"source-receipt"}
    result["artifacts"]=[a for a in result["artifacts"] if not a.get("id","").startswith(PREFIX)]
    result["sources"]=[s for s in result["sources"] if not s.get("id","").startswith("source-"+PREFIX)]
    result["proofs"]=[p for p in result["proofs"] if not p.get("id","").startswith("proof-"+PREFIX)]
    result["artifacts"].append({"id":aid,"kind":"season-input","sha256":digest(_artifact_bytes(plan)),
        "media_type":"application/json","relative_path":filename(plan)})
    result["sources"].append({"id":"source-"+aid,"title":"Dated Chris Shuker Manchester City tenure and later Macclesfield loan chronology",
        "uri":sources["profile"]["url"],"proof_grade":"source-receipt","evidence_artifact_id":aid})
    result["proofs"].append({"id":"proof-"+aid,"artifact_id":aid,"grade":"source-receipt",
        "covers":["City-tenure-includes-2000-opening-date","Macc-loan-starts-2001","same-person-owner-and-order-move"]})
    result["artifacts"].sort(key=lambda a:a["id"]);result["sources"].sort(key=lambda s:s["id"]);result["proofs"].sort(key=lambda p:p["id"])
    out_actor["proof"]=copy.deepcopy(proof)
    for fallback in out_actor["fact_fallbacks"]:
        if fallback.get("field")=="shirt_number": fallback["proof"]=copy.deepcopy(proof)
    packages.validate_package(result,strict=False)
    before_players={p["id"]:p for p in package["players"]};after_players={p["id"]:p for p in result["players"]}
    if before_players.keys()!=after_players.keys() or any(before_players[k]!=after_players[k]
        for k in before_players if k!="english-player-32945"):
        raise ValueError("unselected player recipe records changed")
    old_actor=before_players["english-player-32945"];new_actor=after_players["english-player-32945"]
    if any(new_actor[k]!=old_actor[k] for k in ("id","carrier_id","carrier_family","name","source_name","person_id","ratings")):
        raise ValueError("Shuker person identity, name, or ratings changed")
    if result["assets"]!=package["assets"] or result.get("managers")!=package.get("managers"):
        raise ValueError("Shuker transaction altered photos or managers")
    clubs_before={c["carrier_id"]:c for c in package["clubs"]};clubs_after={c["carrier_id"]:c for c in result["clubs"]}
    if any(clubs_before[k]!=clubs_after[k] for k in clubs_before if k not in (CLUB_CITY,CLUB_MACC)):
        raise ValueError("unselected clubs or tactics changed")
    for cid in (CLUB_CITY,CLUB_MACC):
        left=copy.deepcopy(clubs_before[cid]);right=copy.deepcopy(clubs_after[cid])
        left.pop("roster_player_ids",None);right.pop("roster_player_ids",None)
        if cid==CLUB_MACC:
            left["opening"]["substitute_player_ids"]=[];right["opening"]["substitute_player_ids"]=[]
        if left!=right:
            raise ValueError("selected club opening/tactics changed outside approved roster/substitute rows")
    # Plan includes all explicit pre/post recipe targets, while native outputs
    # are deterministically regenerated from its guarded arrays and parent.
    result_bundle={"plan":plan,"package":result,"jug":post_jug,"eq":post_eq,
        "before":{"package":package,"jug":jug,"eq":eq}}
    if expected is not None and plan!=expected:
        keys=sorted(k for k in set(plan)|set(expected) if plan.get(k)!=expected.get(k))
        raise ValueError("Shuker source/native plan does not reproduce exactly: "+repr(keys))
    _CACHE[cache_key]=result_bundle
    return result_bundle


def _artifact_bytes(plan):
    return packages.canonical_json_bytes(plan)


def filename(plan):
    _validate_plan_shape(plan)
    return PREFIX+plan["transaction_id"]+".json"


def artifact_id(plan):
    _validate_plan_shape(plan)
    return PREFIX+plan["transaction_id"]


def _validate_plan_shape(plan):
    if plan.get("schema")!=SCHEMA or plan.get("mode")!=MODE:
        raise ValueError("exact Shuker schema/mode required")


def prepare(base,input_path=INPUT):
    path,request=_read_request(input_path)
    if base.season!=SEASON or base.release_id!=request["release_id"]: raise ValueError("request names another registered parent")
    return copy.deepcopy(_postimages(base,request,path)["plan"])


def rebase_request(base,input_path=INPUT):
    """Rebind retained source claims to an exact later registered 2000-01 child."""
    path,request=_read_request(input_path)
    if base.season!=SEASON: raise ValueError("Shuker source request only supports its reviewed 2000-01 season")
    result=copy.deepcopy(request)
    result["release_id"]=base.release_id
    result["parent"]=_parent(base)
    return result


def verify(base,plan):
    _validate_plan_shape(plan)
    path=registry.ROOT/plan["source_input"]["path"]
    if digest(path.read_bytes())!=plan["source_input"]["sha256"] or _postimages(base,pipeline.read_json_file(path),path,expected=plan)["plan"]!=plan:
        raise ValueError("Shuker retained source/current parent no longer reproduces exact plan")


def bind(package,plan):
    base=registry.load_registered_release(SEASON,plan["release_id"]);verify(base,plan)
    input_path=registry.ROOT/plan["source_input"]["path"]
    before=pipeline.read_json_file(base.package_path); post=_postimages(base,pipeline.read_json_file(input_path),input_path)["package"]
    if package not in (before,post): raise ValueError("bind accepts exact r220a package preimage or postimage only")
    return copy.deepcopy(post)


def apply(jug,eq,plan):
    base=registry.load_registered_release(SEASON,plan["release_id"]);verify(base,plan)
    input_path=registry.ROOT/plan["source_input"]["path"]
    out=_postimages(base,pipeline.read_json_file(input_path),input_path)
    if (jug,eq) not in ((out["before"]["jug"],out["before"]["eq"]),(out["jug"],out["eq"])):
        raise ValueError("apply requires complete native JUG/EQ preimage or complete postimage")
    return out["jug"],out["eq"]


def source_artifact(plan):
    base=registry.load_registered_release(SEASON,plan["release_id"]);verify(base,plan)
    raw=_artifact_bytes(plan)
    return {"filename":filename(plan),"document":copy.deepcopy(plan),"sha256":digest(raw),"bytes":raw}


def reject_factory_recipe(package):
    if any(a.get("id","").startswith(PREFIX) for a in package.get("artifacts",[])):
        raise ValueError("Shuker ownership move requires source-bound reconstruction")


def reconstruction(previous,release_id):
    """Source-bound publisher hook; it is not invoked by this private QA run."""
    receipt_path=getattr(previous,"compiler_receipt_path",None)
    if receipt_path is None:return None
    receipt=pipeline.read_json_file(receipt_path)
    if receipt.get("compilation_mode")!=MODE:return None
    relative=getattr(previous,"locator",{}).get("sourced_profile_assignment_plan_path")
    if not relative: raise ValueError("Shuker SOURCE receipt lacks assignment-plan locator")
    path=(registry.ROOT/relative).resolve()
    registry.relative_workspace_path(path)
    plan=pipeline.read_json_file(path)
    _validate_plan_shape(plan)
    if path!=(previous.package_path.parent/filename(plan)).resolve() or digest(path.read_bytes())!=receipt.get("original_profile_assignment_plan_sha256"):
        raise ValueError("Shuker SOURCE plan path/SHA differs from compiler receipt")
    base=registry.load_registered_release(SEASON,plan["release_id"])
    verify(base,plan)
    artifact=source_artifact(plan)
    if _sha_file(previous.package_path.parent/artifact["filename"])!=artifact["sha256"]:
        raise ValueError("Shuker SOURCE artifact bytes differ from bound plan")
    expected_package=bind(pipeline.read_json_file(base.package_path),plan)
    expected_raw=packages.canonical_json_bytes(expected_package)
    if previous.package_path.read_bytes()!=expected_raw:
        raise ValueError("Shuker SOURCE recipe is not byte-identical to complete expected package")
    descriptor=previous.package_path.parent/"role-delta-input.json"
    expected_descriptor={"season":SEASON,"release_id":base.release_id,
        "package_sha256":plan["parent"]["package_sha256"],
        "jug_sha256":plan["parent"]["jug_sha256"],"updates":[],"unresolved":[]}
    if pipeline.read_json_file(descriptor)!=expected_descriptor:
        raise ValueError("Shuker SOURCE role descriptor differs from exact inert input")
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(SEASON,descriptor,release_id=release_id,source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(SEASON,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=expected_raw:
        raise ValueError("Shuker complete SOURCE recipe replay differs")
    return {"season":SEASON,"release_id":release_id,
        "complete_game_inventory_identical":True,"complete_recipe_identical":True,
        "compilation_mode":MODE}
