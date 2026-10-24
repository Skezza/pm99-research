"""Private source-bound Berkovic/Ostenstad/Etuhu two-carrier candidate.

The proposal exchanges the two current person identities while keeping their
carrier/club links fixed. It is source preparation only; it never writes a
registered game or invokes a release build.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_opening_order_repair_v1 import native_owners

SCHEMA = "pm99-source-bound-blackburn-ostenstad-etuhu-atomic-v1"
MODE = "r220a-two-carrier-ostenstad-egil-etuhu-youth-pro-admission-v1"
SEASON = "2000-01"
PARENT = "sourced-woolley-mcloughlin-opening-20261024-r220a"
ROOT = registry.ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/blackburn-berkovic-city-replacement-research-v1"
INPUT = registry.ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/blackburn-berkovic-city-atomic-v1/blackburn-ostenstad-etuhu-input-v1.json"
FILENAME = "blackburn-ostenstad-etuhu-source-exchange-v1.json"
SOURCE_PLAN_FILENAME = "blackburn-ostenstad-etuhu-native-plan-v1.json"
ARTIFACT_ID = "blackburn-ostenstad-etuhu-source-v1"
ETUHU_PATH = "Dickson Etuhu Football Player Statistics | 11v11.com"
ETUHU_SHA = "74470b8a3231294d580f0af88399f4624850f5066ec7fea03aba8f78c3154c4a"
CITY_OFFICIAL_PATH = "mancity_etuhu_graduate.html"
CITY_OFFICIAL_SHA = "729708072c17a12b3ea45da427cb35468d30afd261e8e371561cccb847c461c6"
WEB_RECEIPT_PATH = ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/blackburn-berkovic-city-replacement-research-v1/capture-receipt.json"
WEB_RECEIPT_SHA = "2e65edc7a36263abd0cce120b7e8e84ecb4e0e8884e103a8028e2f44d80c6f81"
ORIGINALS_INDEX_PATH = ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/four-crossclub-replacement-web-v2/http-capture-index.json"
ORIGINALS_INDEX_SHA = "eff7d76ad834a01293755b029e4a1f5f32821437d64f831451bdf96313220dd7"
STPATS_PATH = ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/four-crossclub-replacement-web-v2/blackburn_stpats_2000_friendly.html"
STPATS_SHA = "2639e1ed3a4a5642248de5289e953da2998551f72d01db36838b136bf03b2ebe"
SKY_TRANSFER_PATH = ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/four-crossclub-replacement-web-v2/sky_egil_transfer_history.html"
SKY_TRANSFER_SHA = "8f2186914e37bfaed2aacf6ae25b83832a1b4d5464435db6a730b2b1c08f36a7"
BERKOVIC_LOAN_PATH = ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/crossclub-first20-career-web-v1/berkovic_blackburn_loan.html"
BERKOVIC_LOAN_SHA = "6d6dc6dfcfef875f62cd9f6d2a012c077ffc8a0fdec7e06ccc74f6ee2fdd858f"
REQUIRED = ("JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI", "MINIFOTO.PKF")
_CACHE: dict[str, dict[str, Any]] = {}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return registry.sha256_file(path)


def _read_rel(path: str, expected: str) -> bytes:
    p = (registry.ROOT / path).resolve()
    registry.relative_workspace_path(p)
    if p.is_symlink() or not p.is_file() or _file_sha(p) != expected:
        raise ValueError(f"retained source binding changed: {path}")
    return p.read_bytes()


def _source_bindings() -> list[dict[str, str]]:
    request = pipeline.read_json_file(INPUT)
    expected_allocation={"blackburn_9501":"Egil Ostenstad identity and exact retained facts/ratings from City 9184",
        "manchester_city_9184":"Dickson Etuhu source identity; editorial rating/fine-role projection",
        "preserve":["Celtic Berkovic carrier 7878","all club membership/order/owners","all managers","all opaque tactics","all nonselected players and assets"],
        "portraits":"native-no-photo on both selected identities; no borrowed portrait"}
    expected_links={"etuhu_11v11":"https://www.11v11.com/players/dickson-etuhu-8123/",
        "etuhu_city_retrospective":"https://www.mancity.com/news/academy/academy-news/archive/2011/october/the-graduates-no-4-dickson-etuhu",
        "blackburn_transfer_context":"https://stpatsfc.com/report.php?report=914",
        "city_transfer_context":"https://www.skysports.com/football/player/27497/egil-ostenstad"}
    if (set(request)!={"schema","mode","season","parent_release_id","selected_carriers","etuhu",
            "allocation","source_links","publication_approved"}
            or request.get("schema") != SCHEMA + "-input" or request.get("mode") != MODE
            or request.get("season") != SEASON or request.get("parent_release_id") != PARENT
            or request.get("selected_carriers") != {"blackburn":9501,"manchester_city":9184}
            or request.get("etuhu") != {"source_id":"11v11-8123","name":"Dickson Etuhu",
                "birth_date":"1982-06-08","nationality":"NGA","position":"M",
                "height_cm":188,"weight_kg":83,"membership_scope":"youth/pro only; not opening XI or appearance"}
            or request.get("allocation") != expected_allocation or request.get("source_links") != expected_links
            or request.get("publication_approved") is not False):
        raise ValueError("typed input schema, parent, carrier allocation, or Etuhu source facts differ")
    rows = [
        (registry.relative_workspace_path(INPUT), _file_sha(INPUT)),
        (registry.relative_workspace_path(ROOT / "dickson_etuhu_11v11.html"), ETUHU_SHA),
        (registry.relative_workspace_path(ROOT / CITY_OFFICIAL_PATH), CITY_OFFICIAL_SHA),
        (WEB_RECEIPT_PATH, WEB_RECEIPT_SHA),
        (STPATS_PATH, STPATS_SHA),
        (SKY_TRANSFER_PATH, SKY_TRANSFER_SHA),
        (ORIGINALS_INDEX_PATH, ORIGINALS_INDEX_SHA),
        (BERKOVIC_LOAN_PATH, BERKOVIC_LOAN_SHA),
    ]
    for path, digest in rows:
        p = (registry.ROOT / path).resolve()
        registry.relative_workspace_path(p)
        if p.is_symlink() or not p.is_file() or _file_sha(p) != digest:
            raise ValueError(f"source binding changed: {path}")
    return [dict(path=p, sha256=d) for p, d in sorted(set(rows))]


def _parent(base) -> dict[str, Any]:
    if (base.season, base.release_id) != (SEASON, PARENT):
        raise ValueError("exact registered r220a parent required")
    package_sha = _file_sha(base.package_path)
    native = {name: _file_sha(base.game_path / "DBDAT" / name) for name in REQUIRED}
    if package_sha != "4aca2400661e840448b01baf546070ba55a50c908d4c3335577970772812dcd0":
        raise ValueError("r220a package bytes changed")
    expected_native = {"JUG98030.FDI":"a4ab67efe97233530d00a83b203989f9e33d35348dcd02ffa5f057850bb6cb86",
        "EQ98030.FDI":"da3f2c447acd208792f08ca0f86cc4cf93674fbbffafa7e30a37712026fe2bb4",
        "ENT98030.FDI":"38735d0dc323340d6e8d282ee746fadf2246ee10ded333f3c315d687a877b981",
        "MINIFOTO.PKF":"765b2c9870423878eaaba541ede7ed402958163d5be040ad3a320f3c9d6e4849"}
    if native != expected_native:
        raise ValueError("r220a four-file native preimages differ")
    return dict(season=base.season, release_id=base.release_id,
        manifest_sha256=base.manifest_sha256,
        package_path=registry.relative_workspace_path(base.package_path),
        package_sha256=package_sha,
        native_files=native)


def _implementations() -> list[dict[str, str]]:
    from app import indexed_jug_roles
    paths = {"adapter":Path(__file__).resolve(),
        "native_delta":Path(delta.__file__).resolve(),
        "package_schema":Path(packages.__file__).resolve(),
        "rating_calibration":Path(__import__("scripts.season_rating_calibration_v3",fromlist=["x"]).__file__).resolve(),
        "indexed_native_writer":Path(indexed_jug_roles.__file__).resolve()}
    return [dict(name=name,path=registry.relative_workspace_path(path),sha256=_file_sha(path))
        for name,path in sorted(paths.items())]


def _verify_sources() -> dict[str, Any]:
    loan = _read_rel(BERKOVIC_LOAN_PATH, BERKOVIC_LOAN_SHA)
    loan_text = " ".join(BeautifulSoup(loan, "html.parser").get_text(" ", strip=True).split())
    if not all(anchor in loan_text for anchor in (
            "Thu Feb 08 2001", "signing of Celtic midfielder Eyal Berkovic",
            "on loan until the end of the season")):
        raise ValueError("Berkovic original dated Blackburn loan source differs")
    etuhu = _read_rel(registry.relative_workspace_path(ROOT / "dickson_etuhu_11v11.html"), ETUHU_SHA)
    official = _read_rel(registry.relative_workspace_path(ROOT / CITY_OFFICIAL_PATH), CITY_OFFICIAL_SHA)
    stpats = _read_rel(STPATS_PATH, STPATS_SHA)
    transfer = _read_rel(SKY_TRANSFER_PATH, SKY_TRANSFER_SHA)
    receipt = json.loads(_read_rel(WEB_RECEIPT_PATH, WEB_RECEIPT_SHA))
    index = json.loads(_read_rel(ORIGINALS_INDEX_PATH, ORIGINALS_INDEX_SHA))
    etuhu_receipts = [row for row in receipt.get("captures", [])
        if row.get("path", "").endswith("/dickson_etuhu_11v11.html")]
    city_receipts = [row for row in receipt.get("captures", [])
        if row.get("path", "").endswith("/mancity_etuhu_graduate.html")]
    if (len(etuhu_receipts)!=1 or etuhu_receipts[0].get("sha256")!=ETUHU_SHA
            or etuhu_receipts[0].get("requested_url")!="https://www.11v11.com/players/dickson-etuhu-8123/"
            or etuhu_receipts[0].get("http_status")!=200
            or len(city_receipts)!=1 or city_receipts[0].get("sha256")!=CITY_OFFICIAL_SHA
            or city_receipts[0].get("final_url")!="https://www.mancity.com/news/academy/academy-news/archive/2011/october/the-graduates-no-4-dickson-etuhu"):
        raise ValueError("captured original source receipt does not bind Etuhu sources")
    indexed = {row.get("path"):row for row in index.get("captures", [])}
    for path, digest, url in ((STPATS_PATH,STPATS_SHA,"https://stpatsfc.com/report.php?report=914"),
        (SKY_TRANSFER_PATH,SKY_TRANSFER_SHA,"https://www.skysports.com/football/player/27497/egil-ostenstad")):
        row=indexed.get(path)
        if not row or (row.get("sha256"),row.get("url"))!=(digest,url):
            raise ValueError("retained original source index does not bind transfer chronology body")
    text = " ".join(BeautifulSoup(etuhu, "html.parser").get_text(" ", strip=True).split())
    for anchor in ("Dickson Etuhu", "Date of birth 08 June 1982", "Nationality Nigerian",
                   "Weight 83 kg", "Height 1.88 m", "Position Midfielder",
                   "A product of the youth academy at Manchester City",
                   "signed professional forms in July 2000", "Manchester City 23 Dec 1999 24 Jan 2002"):
        if anchor not in text:
            raise ValueError(f"11v11 original no longer contains required Etuhu evidence: {anchor}")
    official_text = " ".join(BeautifulSoup(official, "html.parser").get_text(" ", strip=True).split())
    if "Dickson Etuhu" not in official_text or "academy" not in official_text.casefold():
        raise ValueError("Manchester City retained academy retrospective no longer identifies Etuhu")
    stpats_text = " ".join(BeautifulSoup(stpats, "html.parser").get_text(" ", strip=True).split())
    if not all(v in stpats_text for v in ("05/08/2000", "Blackburn", "St Pat", "Oystenstad")):
        raise ValueError("retained Blackburn/St Pat's report does not bind the Aug 5 transfer-date bridge")
    transfer_text = " ".join(BeautifulSoup(transfer, "html.parser").get_text(" ", strip=True).split())
    if not all(v in transfer_text for v in ("Blackburn", "05 Feb 2001", "Man City")):
        raise ValueError("retained Sky history does not bind the Feb 5 City arrival")
    return {"berkovic_wrong_opening_owner_source": {
            "path": BERKOVIC_LOAN_PATH, "sha256": BERKOVIC_LOAN_SHA,
            "url": "https://www.irishtimes.com/news/berkovic-completes-blackburn-loan-move-1.373972",
            "date": "2001-02-08", "claim": "Celtic to Blackburn loan after the August 2000 opening"},
        "etuhu_identity": {"name": "Dickson Etuhu", "birth_date": "1982-06-08",
            "nationality_label": "Nigerian", "native_country_code": "NGA", "position": "M",
            "height_cm": 188, "weight_kg": 83, "membership": "documented youth academy and professional forms July 2000; not opening-XI/appearance evidence"},
        "etuhu_11v11_sha256": ETUHU_SHA,
        "etuhu_11v11_url":"https://www.11v11.com/players/dickson-etuhu-8123/",
        "manchester_city_retrospective_sha256": CITY_OFFICIAL_SHA,
        "blackburn_august_transfer_bridge_sha256": STPATS_SHA,
        "city_february_transfer_bridge_sha256": SKY_TRANSFER_SHA}


def _records(package: dict) -> dict[int, dict]:
    records = {p["carrier_id"]: p for p in package["players"]}
    if len(records) != len(package["players"]):
        raise ValueError("duplicate package player carriers")
    return records


def _native_facts(jug: bytes, carrier: int) -> dict:
    from scripts.season_within_club_reserve_repair_v1 import native_facts
    return native_facts(jug, carrier)


def _compile(base, expected=None) -> dict:
    parent = _parent(base)
    source_bindings = _source_bindings()
    implementations = _implementations()
    cache_key = _sha(packages.canonical_json_bytes({"schema":SCHEMA,"mode":MODE,
        "parent":parent,"source_bindings":source_bindings,"implementation_bindings":implementations}))
    if cache_key in _CACHE:
        cached = _CACHE[cache_key]
        if expected is not None and cached["plan"] != expected:
            raise ValueError("source/native cached plan does not reproduce exact expected plan")
        return copy.deepcopy(cached)
    source_evidence = _verify_sources()
    package = pipeline.read_json_file(base.package_path)
    jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    records = _records(package)
    egil, berkovic = records[9184], records[9501]
    if (egil["name"], egil["source_name"], egil["club_id"], egil["facts"]["birth_date"]) != (
            "Egil Ostenstad", "Egil Ostenstad", "english-club-311", "1972-01-02"):
        raise ValueError("exact r220 City/Egil recipe preimage required")
    if (berkovic["name"], berkovic["source_name"], berkovic["facts"]["birth_date"]) != (
            "Eyal Berkovic", "Eyal Berkovic", "1972-04-02"):
        raise ValueError("exact r220 Blackburn/Berkovic recipe preimage required")
    if records[7878]["name"] != "Eyal Berkovic" or records[7878]["club_id"] != "club-1252":
        raise ValueError("Celtic Berkovic preservation sentinel changed")
    all_identity = {(p["name"].casefold(), json.dumps(p["facts"].get("birth_date"),sort_keys=True))
        for p in package["players"]}
    if ("dickson etuhu", json.dumps("1982-06-08")) in all_identity:
        raise ValueError("Etuhu already exists in the exact parent package")
    owners = native_owners(eq)
    if owners.get(9184) != {311} or owners.get(9501) != {321} or owners.get(7878) != {1252}:
        raise ValueError("exact City/Blackburn/Celtic native owners differ")
    before_native = {carrier: _native_facts(jug, carrier) for carrier in (9184, 9501)}
    if before_native[9184]["name"].casefold() != "egil ostenstad" or before_native[9501]["name"].casefold() != "eyal berkovic":
        raise ValueError("native carrier names differ from package preimage")
    before_players = {carrier: copy.deepcopy(records[carrier]) for carrier in (9184, 9501)}

    moved = copy.deepcopy(egil)
    for field in ("id", "carrier_id", "carrier_family", "club_id"):
        moved[field] = berkovic[field]
    moved["facts"]["shirt_number"] = {"policy":"preserve-existing-mode1"}
    moved["proof"] = {"artifact_id": ARTIFACT_ID, "grade": "source-receipt"}
    moved["fact_fallbacks"] = [f for f in copy.deepcopy(moved.get("fact_fallbacks", []))
        if f.get("field") != "shirt_number"]
    moved["fact_fallbacks"].append({"field":"shirt_number","method":"preserve-existing-mode1",
        "proof":{"artifact_id":ARTIFACT_ID,"grade":"source-receipt"},
        "value":{"policy":"preserve-existing-mode1"},
        "reason":"No source-bound Blackburn shirt number is claimed; preserve the destination carrier byte."})

    etuhu = copy.deepcopy(egil)
    etuhu.update(person_id="person-source-11v11-dickson-etuhu-1982-06-08",
        name="Dickson Etuhu", source_name="Dickson Etuhu",
        facts={"birth_date":"1982-06-08","nationality":"NGA","primary_position":"M",
            "fine_roles":[9],"height_cm":188,"weight_kg":83,
            "shirt_number":{"policy":"preserve-existing-mode1"}},
        proof={"artifact_id":ARTIFACT_ID,"grade":"source-receipt"},
        fact_fallbacks=[{"field":"shirt_number","method":"preserve-existing-mode1",
            "proof":{"artifact_id":ARTIFACT_ID,"grade":"source-receipt"},
            "value":{"policy":"preserve-existing-mode1"},
            "reason":"No target-opening shirt number is supported; preserve the carrier byte."}])
    from scripts import season_rating_calibration_v3 as ratings
    city_quality = round(sum(p["ratings"]["values"]["quality"] for p in package["players"]
        if p["club_id"] == "english-club-311") / max(1, sum(p["club_id"] == "english-club-311" for p in package["players"])))
    rating_values = ratings.editorial(etuhu, city_quality, "opening_squad", dt.date(2000, 8, 1))
    etuhu["ratings"] = {"profile":"pm99-visible-skills-v1","values":rating_values,
        "provenance":{"method":"identity-club-role-age-optional-editorial-calibration-v3",
            "proof_grade":"reviewed-editorial","source_ids":[ratings.SOURCE_ID]}}
    records[9501].clear(); records[9501].update(moved)
    records[9184].clear(); records[9184].update(etuhu)
    package["players"].sort(key=lambda p:p["id"])
    package["assets"]["portraits"] = [p for p in package["assets"]["portraits"]
        if p["player_id"] not in ("english-player-9501", "english-player-9184")]
    package["assets"]["portraits"].extend([
        {"player_id":"english-player-9501","status":"native-no-photo","proof":{"artifact_id":ARTIFACT_ID,"grade":"source-receipt"},"review_reason":"Egil identity moved to this carrier; no sourced portrait is supplied."},
        {"player_id":"english-player-9184","status":"native-no-photo","proof":{"artifact_id":ARTIFACT_ID,"grade":"source-receipt"},"review_reason":"Etuhu identity admitted without a sourced portrait."}])
    package["assets"]["portraits"].sort(key=lambda p:p["player_id"])
    inner = {"schema":SCHEMA+"-native-proof-v1","mode":MODE,
        "season":SEASON,"release_id":PARENT,"parent":parent,
        "source_bindings":source_bindings,"source_evidence":source_evidence,
        "carrier_changes":[{"carrier_id":9501,"owner":"Blackburn Rovers","before":before_players[9501],"after":copy.deepcopy(records[9501])},
            {"carrier_id":9184,"owner":"Manchester City","before":before_players[9184],"after":copy.deepcopy(records[9184])}],
        "membership_scope":"Etuhu's dated City youth/pro membership is positive; no 19 Aug XI, bench, or first-team appearance claim.",
        "nonclaims":["Etuhu is not asserted to have appeared in the 19 Aug 2000 fixture.","Ratings/fine role are editorial projection, not source facts.","No photos, shirts, lineup, order, manager, club, tactic, or roster-link changes."],
        "native_preimages":{"JUG98030.FDI":_sha(jug),"EQ98030.FDI":_sha(eq)},
        "players_written":2}
    inner["transaction_id"] = _sha(packages.canonical_json_bytes(inner))[:24]
    artifact_path = SOURCE_PLAN_FILENAME
    package["artifacts"] = sorted(package["artifacts"] + [{"id":ARTIFACT_ID,"kind":"season-input",
        "sha256":_sha(packages.canonical_json_bytes(inner)),"media_type":"application/json","relative_path":artifact_path}],key=lambda a:a["id"])
    package["sources"] = sorted(package["sources"] + [{"id":"source-"+ARTIFACT_ID,
        "title":"11v11 Etuhu profile, Manchester City academy retrospective, and dated Blackburn/City transfer context",
        "uri":"https://www.11v11.com/players/dickson-etuhu-8123/","proof_grade":"source-receipt",
        "evidence_artifact_id":ARTIFACT_ID}],key=lambda a:a["id"])
    package["proofs"] = sorted(package["proofs"] + [{"id":"proof-"+ARTIFACT_ID,"artifact_id":ARTIFACT_ID,
        "grade":"source-receipt","covers":["dated-City-youth-professional-membership","Egil-identity-relocated-to-Blackburn","Celtic-Berkovic-preserved"]}],key=lambda a:a["id"])
    packages.validate_package(package, strict=False)
    changed_ids={"english-player-9184","english-player-9501"}
    codes=delta.compiler._extract_country_codes_from_textos(base.game_path/"DBDAT/TEXTOS.PKF")
    post_jug=delta.compile_players(jug,package,changed_ids,codes)
    post_eq=eq
    native={"JUG98030.FDI":post_jug,"EQ98030.FDI":post_eq,
        "ENT98030.FDI":(base.game_path/"DBDAT/ENT98030.FDI").read_bytes(),
        "MINIFOTO.PKF":(base.game_path/"DBDAT/MINIFOTO.PKF").read_bytes()}
    cleared_archive, cleared_offsets = delta.no_photo_archive(native["MINIFOTO.PKF"], {9184, 9501})
    if cleared_archive != native["MINIFOTO.PKF"] or any(cleared_offsets.values()):
        raise ValueError("selected identity unexpectedly has an archive portrait; explicit removal review required")
    for carrier in (9184, 9501):
        loose = base.game_path / "DBDAT/MINIFOTO" / f"J96{carrier:05d}.BMP"
        if loose.exists() or loose.is_symlink():
            raise ValueError("selected identity unexpectedly has a loose portrait")
    # Record-level locality and required Etuhu readback are checked before a plan is exposed.
    old_ix,new_ix=IndexedFDIFile.from_bytes(jug),IndexedFDIFile.from_bytes(post_jug)
    old_rows={e.record_id:e for e in old_ix.entries}; new_rows={e.record_id:e for e in new_ix.entries}
    if old_rows.keys()!=new_rows.keys(): raise ValueError("native player writer changed carrier inventory")
    for cid,old in old_rows.items():
        if cid not in (9184,9501) and old.decode_payload(jug)!=new_rows[cid].decode_payload(post_jug):
            raise ValueError(f"unselected JUG record changed: {cid}")
    facts_read=_native_facts(post_jug,9184)
    if facts_read["name"].casefold()!="dickson etuhu" or facts_read["birth_date"]!="1982-06-08" or facts_read["position"]!="M":
        raise ValueError("Etuhu native identity/date/position readback failed")
    # The package may not alter any club or manager; explicit parent equality is also in the planned checks.
    if package["clubs"]!=pipeline.read_json_file(base.package_path)["clubs"]:
        raise ValueError("player exchange altered club rows, orders, owners, or opening links")
    plan={"schema":SCHEMA,"mode":MODE,"season":SEASON,"release_id":PARENT,
        "parent":parent,"source_bindings":source_bindings,"implementation_bindings":implementations,
        "inner_source_plan":inner,"inner_source_plan_sha256":_sha(packages.canonical_json_bytes(inner)),
        "inner_source_plan_filename":SOURCE_PLAN_FILENAME,"package_postimage_sha256":_sha(packages.canonical_json_bytes(package)),
        "native_postimages":{name:_sha(raw) for name,raw in native.items()},
        "players_written":2,
        "changed_jug_carriers":[9184,9501],"changed_eq_records":[],"scope":inner["scope"] if "scope" in inner else inner["membership_scope"],
        "publication_approved":False}
    plan["transaction_id"]=_sha(packages.canonical_json_bytes(plan))[:24]
    if expected is not None and plan!=expected: raise ValueError("r220a source/native prepare did not reproduce exact plan")
    result={"plan":plan,"package":package,"native":native,
        "before":{"JUG98030.FDI":jug,"EQ98030.FDI":eq,
            "ENT98030.FDI":(base.game_path/"DBDAT/ENT98030.FDI").read_bytes(),
            "MINIFOTO.PKF":(base.game_path/"DBDAT/MINIFOTO.PKF").read_bytes()}}
    _CACHE[cache_key]=copy.deepcopy(result)
    return result


def prepare(base, input_path=INPUT) -> dict:
    if Path(input_path).resolve()!=INPUT.resolve(): raise ValueError("exact typed input path required")
    return copy.deepcopy(_compile(base)["plan"])


def verify(base, plan: dict) -> None:
    if plan.get("schema")!=SCHEMA or plan.get("mode")!=MODE or plan.get("publication_approved") is not False:
        raise ValueError("exact private schema/mode and nonpublishing plan required")
    _compile(base, expected=plan)


def bind(package: dict, plan: dict) -> dict:
    base=registry.load_registered_release(SEASON,PARENT); verify(base,plan)
    cache=_compile(base,expected=plan)
    before=pipeline.read_json_file(base.package_path)
    if package not in (before,cache["package"]): raise ValueError("bind accepts exact whole package preimage or postimage")
    return copy.deepcopy(cache["package"])


def apply(jug: bytes, eq: bytes, plan: dict) -> tuple[bytes,bytes]:
    base=registry.load_registered_release(SEASON,PARENT); verify(base,plan)
    cache=_compile(base,expected=plan); before=cache["before"]; after=cache["native"]
    if (jug,eq) not in ((before["JUG98030.FDI"],before["EQ98030.FDI"]),
                        (after["JUG98030.FDI"],after["EQ98030.FDI"])):
        raise ValueError("native apply accepts complete paired JUG/EQ preimage or postimage only")
    return after["JUG98030.FDI"],after["EQ98030.FDI"]


def apply_ent(ent: bytes, plan: dict) -> bytes:
    base=registry.load_registered_release(SEASON,PARENT); verify(base,plan); cache=_compile(base,expected=plan)
    if ent!=cache["before"]["ENT98030.FDI"]: raise ValueError("ENT must equal exact unchanged preimage")
    return cache["native"]["ENT98030.FDI"]


def apply_minifoto(data: bytes, plan: dict) -> bytes:
    base=registry.load_registered_release(SEASON,PARENT); verify(base,plan); cache=_compile(base,expected=plan)
    if data!=cache["before"]["MINIFOTO.PKF"]: raise ValueError("photo archive must equal exact unchanged preimage")
    return cache["native"]["MINIFOTO.PKF"]


def selected_carriers(plan: dict) -> set[int]:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE:
        raise ValueError("selected portrait carriers require exact source schema and mode")
    return {9184, 9501}


def source_artifact(plan: dict) -> dict[str, Any]:
    base=registry.load_registered_release(SEASON,PARENT); verify(base,plan)
    document=copy.deepcopy(plan["inner_source_plan"]); digest=_sha(packages.canonical_json_bytes(document))
    if digest!=plan.get("inner_source_plan_sha256") or plan.get("inner_source_plan_filename")!=SOURCE_PLAN_FILENAME:
        raise ValueError("inner artifact canonical digest or filename mismatch")
    return {"filename":SOURCE_PLAN_FILENAME,"document":document,"sha256":digest}


def filename(plan: dict) -> str:
    if plan.get("schema")!=SCHEMA or plan.get("mode")!=MODE: raise ValueError("typed filename needs exact schema/mode")
    return FILENAME


def artifact_id(plan: dict) -> str:
    if plan.get("schema")!=SCHEMA or plan.get("mode")!=MODE: raise ValueError("typed artifact needs exact schema/mode")
    return ARTIFACT_ID


def reject_factory_recipe(package: dict) -> None:
    if any(a.get("relative_path")==SOURCE_PLAN_FILENAME for a in package.get("artifacts",[])):
        raise ValueError("Berkovic/Ostenstad/Etuhu identity exchange requires source-bound reconstruction")


def reconstruction(previous, release_id: str):
    """Publisher SOURCE hook; called only by the registered source replay path."""
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if receipt.get("compilation_mode") != MODE:
        return None
    relative = previous.locator.get("sourced_profile_assignment_plan_path")
    if not relative:
        raise ValueError("Blackburn/City SOURCE receipt lacks its typed assignment plan path")
    path = (registry.ROOT / relative).resolve()
    plan = pipeline.read_json_file(path)
    base = registry.load_registered_release(SEASON, PARENT)
    verify(base, plan)
    if (path != (previous.package_path.parent / filename(plan)).resolve()
            or _file_sha(path) != receipt.get("original_profile_assignment_plan_sha256")):
        raise ValueError("Blackburn/City SOURCE outer plan path/hash differs")
    inner = source_artifact(plan)
    if _file_sha(previous.package_path.parent / inner["filename"]) != inner["sha256"]:
        raise ValueError("Blackburn/City SOURCE inner source artifact differs")
    expected_package = bind(pipeline.read_json_file(base.package_path), plan)
    previous_bytes = previous.package_path.read_bytes()
    if (pipeline.read_json_file(previous.package_path) != expected_package
            or previous_bytes != packages.canonical_json_bytes(expected_package)):
        raise ValueError("Blackburn/City SOURCE recipe bytes differ from exact canonical postimage")
    previous_inventory = pipeline.read_json_file(previous.inventory_path)
    pipeline.assert_tree_matches_inventory(previous.game_path, previous_inventory)
    descriptor = previous.package_path.parent / "role-delta-input.json"
    expected_descriptor = dict(season=SEASON, release_id=PARENT,
        package_sha256=plan["parent"]["package_sha256"],
        jug_sha256=plan["parent"]["native_files"]["JUG98030.FDI"],updates=[],unresolved=[])
    if pipeline.read_json_file(descriptor) != expected_descriptor:
        raise ValueError("Blackburn/City SOURCE role descriptor is not the exact inert input")
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(SEASON, descriptor, release_id=release_id, source_release_id=PARENT,
        profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(SEASON,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, previous_inventory)
    if (pipeline.read_json_file(rebuilt.package_path) != expected_package
            or rebuilt.package_path.read_bytes() != previous_bytes):
        raise ValueError("Blackburn/City whole SOURCE recipe bytes differ")
    return dict(season=SEASON,release_id=release_id,
        complete_game_inventory_identical=True,complete_recipe_identical=True,compilation_mode=MODE)
