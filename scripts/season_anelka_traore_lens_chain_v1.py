"""Private, source-bound opening ownership transaction for 2001-02.

The transaction changes identities only within their original native carrier
families: Liverpool's dd6361 carrier 8080 becomes Djimi Traore and Lens's
dd6360 carrier 31819 becomes Bruno Rodriguez. PSG carrier 12616 remains
Nicolas Anelka. The module returns bytes and never writes native game files.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_shirt_number import rewrite_indexed_native_shirt_numbers
from app.player_initial_order import OrderReplacement, patch_initial_orders, read_initial_order
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_delta_v1 as ownership_delta
from scripts.season_opening_order_repair_v1 import native_owners

MODE = "source-bound-anelka-traore-lens-chain-v2"
SCHEMA = "pm99-source-bound-anelka-traore-lens-chain-v2"
INPUT_SCHEMA = SCHEMA + "-input"
PREFIX = "source-bound-anelka-traore-lens-chain-v2-"
INPUT_PATH = ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/anelka-traore-lens-private-v3/transaction-input-v2.json"

LIVERPOOL = 305
LENS = 504
PSG = 502
ANELKA_CARRIER = 8080
TRAORE_CARRIER = 31819
PSG_ANELKA_CARRIER = 12616
LENS_XI_CARRIER_MAP = {
    "3552": 3227, "3886": 3229, "3574": 3237, "155753": 3239,
    "3794": 3240, "5483": 3918, "3906": 7729, "5487": 8193,
    "5484": 8195, "8318": 12440, "3604": 12539,
}
LENS_BENCH_CARRIERS = (19449, 12613, 19441, 31819)
LENS_FIFTH_FALLBACK_CARRIER = 19448  # S. Chabbert: season roster only; no opener appearance claim.


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _path(relative: str) -> Path:
    path = (registry.ROOT / relative).resolve()
    if not path.is_relative_to(registry.ROOT.resolve()) or path.is_symlink() or not path.is_file():
        raise ValueError("source path is not a retained regular workspace file")
    return path


def _binding(row: dict) -> dict:
    path = _path(row["path"])
    raw = path.read_bytes()
    if digest(raw) != row["sha256"]:
        raise ValueError("retained source SHA differs: " + row["path"])
    return {"path": registry.relative_workspace_path(path), "sha256": digest(raw)}


def _hashes(base) -> dict:
    return {
        "manifest_sha256": base.manifest_sha256,
        "package_sha256": registry.sha256_file(base.package_path),
        "jug_sha256": registry.sha256_file(base.game_path / "DBDAT/JUG98030.FDI"),
        "eq_sha256": registry.sha256_file(base.game_path / "DBDAT/EQ98030.FDI"),
        "minifoto_sha256": registry.sha256_file(base.game_path / "DBDAT/MINIFOTO.PKF"),
    }


def filename(plan: dict) -> str:
    return PREFIX + plan["transaction_id"] + ".json"


def artifact_id(plan: dict) -> str:
    return PREFIX + plan["transaction_id"]


def selected_carriers(plan: dict) -> set[int]:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE:
        raise ValueError("transaction schema/mode differs")
    return {ANELKA_CARRIER, TRAORE_CARRIER}


def _require_bench_rows(page: str, hrefs: tuple[str, ...]) -> None:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page, "lxml")
    for href in hrefs:
        rows = {str(node.find_parent("tr")) for node in soup.find_all("a", href=href)
                if node.find_parent("tr") is not None
                and any("ersatzbank" in (parent.get("class") or []) for parent in node.parents)}
        if len(rows) != 1:
            raise ValueError("exact substitute bench row missing or ambiguous: " + href)


def _read_sources(request: dict) -> tuple[dict, dict, dict]:
    bindings = request["source_bindings"]
    actual = {}
    for key, row in bindings.items():
        if "path" not in row:
            continue
        actual[key] = _binding(row)
        if row.get("receipt_path") and row.get("representation"):
            receipt_path = _path(row["receipt_path"])
            receipt_bytes = receipt_path.read_bytes()
            if digest(receipt_bytes) != row.get("receipt_sha256"):
                raise ValueError("retained source receipt SHA differs: " + key)
            receipt = pipeline.read_json_file(receipt_path)
            if (receipt.get("source_url") != row.get("url")
                    or receipt.get("representation") != row.get("representation")
                    or receipt.get("body_path") != row.get("path")
                    or receipt.get("body_sha256") != row.get("sha256")):
                raise ValueError("source receipt does not bind exact URL/body/representation: " + key)
            actual[key].update({"receipt_path":registry.relative_workspace_path(receipt_path),
                "receipt_sha256":digest(receipt_bytes),"url":row["url"],
                "representation":row["representation"]})

    lp = _path(bindings["liverpool_opening_fixture"]["path"]).read_text(encoding="utf-8", errors="replace")
    lens = _path(bindings["lens_opening_fixture"]["path"]).read_text(encoding="utf-8", errors="replace")
    if "<title>Liverpool FC - West Ham United, 18/08/2001 - Premier League - Match sheet | Transfermarkt</title>" not in lp:
        raise ValueError("Liverpool retained fixture title/date differs")
    if "<title>RC Lens - Olympique Lyon, 28/07/2001 - Ligue 1 - Match sheet | Transfermarkt</title>" not in lens:
        raise ValueError("Lens retained fixture title/date differs")
    if "Starting Line-up: 4-4-2" not in lp or "Starting Line-up: 4-4-2" not in lens:
        raise ValueError("both retained opening fixtures must publish the bound 4-4-2 formation")
    uefa = _path(bindings["anelka_december_transfer"]["path"]).read_text(encoding="utf-8", errors="replace")
    if ("Liverpool swoop for Anelka" not in uefa
            or "Friday, December 21, 2001" not in uefa
            or "Liverpool FC have signed French international Nicolas Anelka on loan" not in uefa
            or "Paris Saint-Germain FC striker" not in uefa):
        raise ValueError("UEFA Anelka transfer source does not bind the Dec 21 PSG-to-Liverpool move")
    sky = _path(bindings["traore_lens_transfer"]["path"]).read_text(encoding="utf-8", errors="replace")
    if ("<span itemprop=\"name\">Djimi Traore</span>" not in sky
            or "<strong>Liverpool</strong>" not in sky or "<strong>RC Lens</strong>" not in sky
            or 'data-short-text="31/08/01">31 Aug 2001' not in sky):
        raise ValueError("Sky Traore transfer source does not bind the Aug 31 Liverpool-to-Lens move")
    for anchor in (
        'href="/djimi-traore/profil/spieler/3598">Djimi Traoré</a>',
        'href="/nick-barmby/profil/spieler/3222">Nick Barmby</a>',
        'href="/john-arne-riise/profil/spieler/3220">John Arne Riise</a>',
        'href="/jamie-redknapp/profil/spieler/3424">Jamie Redknapp</a>',
        'href="/jorgen-nielsen/profil/spieler/23085">Jørgen Nielsen</a>',
    ):
        if anchor not in lp:
            raise ValueError("Liverpool exact matchday substitute/profile link missing: " + anchor)
    for anchor in (
        'href="/bruno-rodriguez/profil/spieler/5742">Bruno Rodriguez</a>',
        'href="/yoann-lachor/profil/spieler/5479">Yoann Lachor</a>',
        'href="/eric-sikora/profil/spieler/5481">Eric Sikora</a>',
        'href="/daniel-moreira/profil/spieler/5494">Daniel Moreira</a>',
    ):
        if anchor not in lens:
            raise ValueError("Lens exact matchday substitute/profile link missing: " + anchor)
    _require_bench_rows(lp, (
        "/djimi-traore/profil/spieler/3598", "/nick-barmby/profil/spieler/3222",
        "/john-arne-riise/profil/spieler/3220", "/jamie-redknapp/profil/spieler/3424",
        "/jorgen-nielsen/profil/spieler/23085"))
    _require_bench_rows(lens, (
        "/bruno-rodriguez/profil/spieler/5742", "/yoann-lachor/profil/spieler/5479",
        "/eric-sikora/profil/spieler/5481", "/daniel-moreira/profil/spieler/5494"))
    def row_text(page: str, href: str) -> str:
        rows=[re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",m.group(1))).strip()
              for m in re.finditer(r"<tr[^>]*>(.*?)</tr>",page,re.S) if href in m.group(1)]
        if len(rows)!=1:
            raise ValueError("expected one fixture row for linked source player " + href)
        return rows[0]
    traore_row_text=row_text(lp,"/djimi-traore/profil/spieler/3598")
    bruno_row_text=row_text(lens,"/bruno-rodriguez/profil/spieler/5742")
    if not all(s in traore_row_text for s in ["30","Djimi Traoré","CB"]):
        raise ValueError("Liverpool source does not prove Traore shirt/role row")
    if not all(s in bruno_row_text for s in ["23","Bruno Rodriguez","CF"]):
        raise ValueError("Lens source does not prove Bruno shirt/role row")

    pre = pipeline.read_json_file(_path(bindings["opening_preallocation"]["path"]))
    liverpool_pre = next(c for c in pre["source_clubs"] if c.get("selector", {}).get("club_name") == "Liverpool")
    lens_pre = next(c for c in pre["source_clubs"] if c.get("selector", {}).get("club_name") == "Lens")
    if (liverpool_pre["opening_fixture_date"], liverpool_pre["opening_source_match_id"]) != ("2001-08-18", "988858"):
        raise ValueError("Liverpool source preallocation no longer binds the dated opener")
    if (lens_pre["opening_fixture_date"], lens_pre["opening_source_match_id"]) != ("2001-07-28", "1002374"):
        raise ValueError("Lens source preallocation no longer binds the dated opener")
    if (lens_pre["selector"].get("source_path"),lens_pre["selector"].get("source_sha256")) != (
            bindings["lens_source_roster"]["source_path"],bindings["lens_source_roster"]["source_sha256"]):
        raise ValueError("Lens annual roster source binding differs from preallocation")
    for source_id, carrier in LENS_XI_CARRIER_MAP.items():
        if not any(str(p.get("opening_source_player_id")) == source_id and p.get("opening_xi_order") for p in lens_pre["players"]):
            raise ValueError("Lens opener XI source ID/order missing: " + source_id)
        if not carrier:
            raise ValueError("invalid Lens XI mapping")
    traore_row = next(p for p in lens_pre["players"] if p.get("source_row_index") == 17)
    if (traore_row.get("source_row_sha256") != bindings["lens_source_roster"]["row_sha256"]
            or traore_row.get("facts", {}).get("name") != "Djimi Traore"):
        raise ValueError("Lens annual Traore row proof differs")
    chabbert = next(p for p in lens_pre["players"] if p.get("facts", {}).get("name") == "Sébastien Chabbert")
    if chabbert.get("opening_xi_order") is not None:
        raise ValueError("fallback goalkeeper unexpectedly appears in Lens opener XI")

    metz_path = _path(bindings["bruno_official_club_profile"]["path"])
    metz = metz_path.read_text(encoding="utf-8", errors="replace")
    for anchor in ("<title>Bruno RODRIGUEZ | FC Metz</title>", "BRUNO RODRIGUEZ", "Attaquant", "25/11/1972", "180 m", "79 kg"):
        if anchor not in metz:
            raise ValueError("FC Metz official profile source anchor missing: " + anchor)
    receipt_path = _path(bindings["bruno_official_club_profile"]["receipt_path"])
    receipt = pipeline.read_json_file(receipt_path)
    if (digest(receipt_path.read_bytes()) != bindings["bruno_official_club_profile"]["receipt_sha256"]
            or receipt.get("url") != bindings["bruno_official_club_profile"]["url"]
            or receipt.get("sha256") != bindings["bruno_official_club_profile"]["sha256"]
            or receipt.get("representation") != "raw-html via curl -L"):
        raise ValueError("FC Metz raw body receipt differs")
    ff = pipeline.read_json_file(_path(bindings["bruno_france_football_corroboration"]["path"]))
    pl = pipeline.read_json_file(_path(bindings["bruno_premier_league_corroboration"]["path"]))
    sky = pipeline.read_json_file(_path(bindings["bruno_sky_dob_conflict"]["path"]))
    if not all(token in ff["extracted_text"] for token in ["25 novembre 1972", "France", "1m80", "79 kg", "Attaquant"]):
        raise ValueError("France Football corroboration does not reproduce")
    if not all(token in pl["extracted_text"] for token in ["25/11/1972", "France", "Forward", "175cm"]):
        raise ValueError("Premier League corroboration does not reproduce")
    if "25/10/1972" not in sky["extracted_text"]:
        raise ValueError("Sky DOB conflict evidence missing")
    actual["lens_source_roster"] = {"preallocation_path": bindings["opening_preallocation"]["path"],
        "source_path": bindings["lens_source_roster"]["source_path"],
        "source_sha256": bindings["lens_source_roster"]["source_sha256"],
        "row_index": 17, "row_sha256": traore_row["source_row_sha256"]}
    return actual, {"liverpool": liverpool_pre, "lens": lens_pre}, {
        "fcmetz_receipt": receipt, "france_football": ff, "premier_league": pl, "sky_conflict": sky,
    }


def _new_bruno_id() -> str:
    return "person-source-" + digest(b"fcmetz-player-29|transfermarkt-player-5742")


def _id_for(package: dict, carrier: int) -> dict:
    rows = [p for p in package["players"] if p.get("carrier_id") == carrier]
    if len(rows) != 1:
        raise ValueError("expected exactly one package actor for native carrier " + str(carrier))
    return rows[0]


def _club(package: dict, carrier: int) -> dict:
    rows = [c for c in package["clubs"] if c.get("carrier_id") == carrier]
    if len(rows) != 1:
        raise ValueError("expected exactly one club carrier " + str(carrier))
    return rows[0]


def _actor_order_map(package: dict, jug: bytes) -> dict[int, int]:
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    return {carrier: read_initial_order(entries[carrier].decode_payload(jug)).order for carrier in entries}


def _desired_carrier_order(package: dict, club: dict, opening_ids: list[str], order_map: dict[int, int]) -> list[str]:
    players = {p["id"]: p for p in package["players"]}
    current = list(club["roster_player_ids"])
    if len(current) != len(set(current)) or len(opening_ids) != len(set(opening_ids)) or not set(opening_ids) <= set(current):
        raise ValueError("opening source selection has duplicate or non-roster actor")
    rest = sorted((pid for pid in current if pid not in set(opening_ids)), key=lambda pid: order_map[players[pid]["carrier_id"]])
    return opening_ids + rest


def _parent_checks(base, request: dict) -> tuple[dict, dict, bytes, bytes, bytes]:
    if base.season != request.get("season") or base.release_id != request.get("release_id"):
        raise ValueError("request must name the exact registered season release")
    actual = _hashes(base)
    if actual != request.get("parent"):
        raise ValueError("explicit manifest/package/JUG/EQ/photo parent hashes differ")
    package = pipeline.read_json_file(base.package_path)
    jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    photo = (base.game_path / "DBDAT/MINIFOTO.PKF").read_bytes()
    if package["season"]["label"] != "2001/02":
        raise ValueError("wrong package season")
    return actual, package, jug, eq, photo


def prepare(base, input_path=INPUT_PATH) -> dict:
    path = Path(input_path)
    if not path.is_absolute():
        path = registry.ROOT / path
    path = path.resolve()
    if not path.is_relative_to(registry.ROOT.resolve()) or path.is_symlink() or not path.is_file():
        raise ValueError("input must be a retained regular workspace file")
    request = pipeline.read_json_file(path)
    if request.get("schema") != INPUT_SCHEMA:
        raise ValueError("wrong exact transaction input schema")
    _parent_hashes, package, jug, eq, photo = _parent_checks(base, request)
    source_bindings, preallocations, source_profiles = _read_sources(request)
    actors = {p["carrier_id"]: p for p in package["players"]}
    clubs = {c["carrier_id"]: c for c in package["clubs"]}
    liverpool = clubs[LIVERPOOL]
    lens = clubs[LENS]
    psg = clubs[PSG]
    anelka = actors[ANELKA_CARRIER]
    traore = actors[TRAORE_CARRIER]
    psg_anelka = actors[PSG_ANELKA_CARRIER]
    if (anelka["name"], anelka["club_id"], anelka["facts"]["birth_date"]) != ("Nicolas Anelka", liverpool["id"], "1979-10-14"):
        raise ValueError("Liverpool Anelka carrier preimage differs")
    if (traore["name"], traore["club_id"], traore["facts"]["birth_date"]) != ("Djimi Traore", lens["id"], "1980-03-01"):
        raise ValueError("Lens Traore carrier preimage differs")
    if (psg_anelka["name"], psg_anelka["club_id"], psg_anelka["facts"]["birth_date"]) != ("Nicolas Anelka", psg["id"], "1979-10-14"):
        raise ValueError("PSG Anelka actor differs")
    if psg_anelka != copy.deepcopy(_id_for(package, PSG_ANELKA_CARRIER)):
        raise ValueError("PSG preservation sanity check failed")
    if any(p.get("person_id") == _new_bruno_id() for p in package["players"]):
        raise ValueError("Bruno source person is already represented")
    owners = native_owners(eq)
    if owners.get(ANELKA_CARRIER) != {LIVERPOOL} or owners.get(TRAORE_CARRIER) != {LENS} or owners.get(PSG_ANELKA_CARRIER) != {PSG}:
        raise ValueError("exclusive native team ownership differs")
    order_map = _actor_order_map(package, jug)
    liverpool_xi = list(liverpool["opening"]["starting_xi_player_ids"])
    liverpool_bench = ["english-player-8083", "english-player-8080", "english-player-8147", "english-player-8081", "english-player-8192"]
    if len(liverpool_xi) != 11 or liverpool_xi != [
        "english-player-8058", "english-player-8059", "english-player-8062", "english-player-8064",
        "english-player-8065", "english-player-8066", "english-player-8067", "english-player-8068",
        "english-player-8069", "english-player-8070", "english-player-8071"]:
        raise ValueError("Liverpool original XI must stay exact")
    lens_xi = []
    for source_row in sorted((x for x in preallocations["lens"]["players"] if x.get("opening_xi_order")), key=lambda x:x["opening_xi_order"]):
        source_id = str(source_row["opening_source_player_id"])
        carrier = LENS_XI_CARRIER_MAP[source_id]
        actor = actors[carrier]
        if actor["club_id"] != lens["id"] or actor["facts"]["birth_date"] != source_row["facts"]["birth_date"]:
            raise ValueError("Lens source XI actor/preimage differs at carrier " + str(carrier))
        lens_xi.append(actor["id"])
    if len(lens_xi) != 11:
        raise ValueError("complete Lens source XI required")
    lens_bench = [_id_for(package, carrier)["id"] for carrier in LENS_BENCH_CARRIERS]
    fallback = _id_for(package, LENS_FIFTH_FALLBACK_CARRIER)
    if fallback["name"] != "S. Chabbert" or fallback["club_id"] != lens["id"]:
        raise ValueError("declared Lens fifth goalkeeper fallback differs")
    if len(liverpool["roster_player_ids"]) != 24 or len(lens["roster_player_ids"]) != 25:
        raise ValueError("Liverpool/Lens source roster counts differ")
    for club_carrier, club in ((LIVERPOOL,liverpool),(LENS,lens)):
        carriers=[next(p["carrier_id"] for p in package["players"] if p["id"]==pid)
                  for pid in club["roster_player_ids"]]
        if len(carriers)!=len(set(carriers)) or any(owners.get(c)!={club_carrier} for c in carriers):
            raise ValueError("target club roster lacks unique exclusive native ownership")
        roster_orders=sorted(order_map[c] for c in carriers)
        if roster_orders!=list(range(1,len(carriers)+1)):
            raise ValueError("target club current native orders are not a complete unique permutation")

    # Transfer only the same person's proven facts/ratings from his existing
    # record; set Liverpool's fixture-proven shirt, not Anelka's old #9.
    native_roles = __import__("app.indexed_jug_roles", fromlist=["read_indexed_native_roles"])
    current_traore_roles = native_roles.read_indexed_native_roles(
        {e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}[TRAORE_CARRIER].decode_payload(jug),
        TRAORE_CARRIER)[1]
    traore_after = copy.deepcopy(anelka)
    traore_after.update({"source_name":"Djimi Traore", "name":"Djimi Traore", "person_id":traore["person_id"], "club_id":liverpool["id"]})
    traore_after["facts"] = copy.deepcopy(traore["facts"])
    traore_after["facts"]["fine_roles"] = [r for r in current_traore_roles if r != 98]
    traore_after["facts"]["shirt_number"] = 30
    traore_after["fact_fallbacks"] = copy.deepcopy(traore.get("fact_fallbacks", []))
    traore_after["facts"]["nationality"] = "FRA"  # existing same-person native country code; not a sourced citizenship claim.
    for fallback_row in traore_after["fact_fallbacks"]:
        if fallback_row.get("field") == "nationality":
            fallback_row["value"] = "FRA"
            fallback_row["reason"] = "Retain the same person's existing native France code; the admitted dated sources do not establish citizenship."
    traore_after["fact_fallbacks"] = [x for x in traore_after.get("fact_fallbacks", []) if x.get("field") != "shirt_number"]
    traore_after["ratings"] = copy.deepcopy(traore["ratings"])

    bruno_before = copy.deepcopy(traore)
    bruno_after = copy.deepcopy(traore)
    bruno_after.update({"source_name":"Bruno Rodriguez", "name":"Rodriguez", "person_id":_new_bruno_id(), "club_id":lens["id"]})
    bruno_after["facts"] = {
        "birth_date":"1972-11-25", "fine_roles":[12], "height_cm":180,
        "nationality":"FRA", "primary_position":"F",
        "shirt_number":{"policy":"preserve-existing-mode1"}, "weight_kg":79,
    }
    source_proof_placeholder = {"artifact_id":"PLAN_ARTIFACT", "grade":"source-receipt"}
    bruno_after["fact_fallbacks"] = [{
        "field":"shirt_number", "method":"preserve-existing-mode1", "proof":source_proof_placeholder,
        "value":{"policy":"preserve-existing-mode1"},
        "reason":"The Lens match sheet records #23; compact dd6360 carrier has no supported native shirt writer, so source number remains evidence only.",
    }]
    bruno_after["proof"] = source_proof_placeholder
    bruno_after["source_name"] = "Bruno Rodriguez"

    from scripts import season_rating_calibration_v3 as rating_model
    model_path = registry.ROOT / "scripts/season_rating_calibration_v3.py"
    model_sha = registry.sha256_file(model_path)
    from statistics import median
    rating_strength = median(p["ratings"]["values"]["quality"] for p in package["players"]
                            if p["club_id"] == lens["id"] and p["carrier_id"] != TRAORE_CARRIER)
    rating_player_input = copy.deepcopy(bruno_after)
    rating_player_input.pop("ratings", None)
    rating_player_input.pop("proof", None)
    rating_player_input.pop("fact_fallbacks", None)
    rating_input = {"player":rating_player_input, "strength":rating_strength, "state":"unknown", "snapshot":"2001-08-01", "model_sha256":model_sha}
    rating_output = rating_model.editorial(bruno_after, rating_strength, "unknown", dt.date(2001,8,1))
    rating_output["handling"] = max(1,min(20,rating_output["handling"]))
    rating_audit = {"model_sha256":model_sha, "input_sha256":digest(packages.canonical_json_bytes(rating_input)),
                    "output_sha256":digest(packages.canonical_json_bytes(rating_output)), "proof_grade":"reviewed-editorial",
                    "preserves_displaced_stats":False}
    bruno_after["ratings"] = {"profile":"pm99-visible-skills-v1", "values":rating_output,
        "provenance":{"method":"identity-club-role-age-optional-editorial-calibration-v3",
            "proof_grade":"reviewed-editorial", "source_ids":["source-bound-rating-calibration-v3"]}}
    # Both package orders are made explicit, with exact XI first and source
    # bench next. Lens's fifth member is declared fallback, never source-proven.
    liverpool_opening_ids = liverpool_xi + liverpool_bench
    lens_opening_ids = lens_xi + lens_bench + [fallback["id"]]
    lpool_order = _desired_carrier_order(package,liverpool,liverpool_opening_ids,order_map)
    lens_order = _desired_carrier_order(package,lens,lens_opening_ids,order_map)
    order_rows=[]
    for club_carrier, sequence in ((LIVERPOOL,lpool_order),(LENS,lens_order)):
        for target, pid in enumerate(sequence,1):
            actor=next(p for p in package["players"] if p["id"]==pid)
            carrier=actor["carrier_id"]
            before=order_map[carrier]
            if before != target:
                old_entry={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}[carrier]
                old_name=read_initial_order(old_entry.decode_payload(jug)).name
                after_name=("Djimi TRAORE" if carrier==ANELKA_CARRIER else ("Rodriguez" if carrier==TRAORE_CARRIER else old_name))
                order_rows.append({"club_carrier_id":club_carrier,"carrier_id":carrier,"before_name":old_name,"after_name":after_name,"before":before,"after":target})
    # Compile/package proofs avoid pinning a global editor or compiler hash.
    bindings = {"input":{"path":registry.relative_workspace_path(path),"sha256":digest(path.read_bytes())},
        "sources":source_bindings}
    update_rows=[
        {"carrier_id":ANELKA_CARRIER,"before":copy.deepcopy(anelka),"after":traore_after,
         "identity_source_person_id":traore["person_id"],"membership":"Liverpool 18 Aug 2001 fixture substitute #30; subsequent Lens loan is dated 31 Aug"},
        {"carrier_id":TRAORE_CARRIER,"before":copy.deepcopy(bruno_before),"after":bruno_after,
         "identity_source_person_id":_new_bruno_id(),"membership":"Lens 28 Jul 2001 opener substitute #23; later Rayo loan begins 28 Aug"},
    ]
    plan={"schema":SCHEMA,"mode":MODE,"season":base.season,"release_id":base.release_id,
        "source_input":bindings["input"],"parent":request["parent"],"source_bindings":source_bindings,
        "source_choice":{"bruno_dob":"1972-11-25","decision_status":"private proposed source selection for root review; not a claim of unanimous evidence or final release adjudication",
            "basis":"Per root direction, choose FC Metz official former-player profile, corroborated by Premier League and France Football extracted profiles; Sky 25 Oct 1972 conflict retained, not unanimous.",
            "bruno_height_cm":180,"height_policy":"FC Metz/France Football selected over Premier League 175cm; profile value, not dated 2001 measurement.",
            "bruno_weight_kg":79,"bruno_nationality":"FRA","bruno_position":"F/striker; fine role 12 is broad-role editorial mapping.",
            "ratings":rating_audit,"rating_input":rating_input,"rating_output":rating_output},
        "updates":update_rows,
        "opening":{"liverpool":{"fixture_date":"2001-08-18","opponent":"West Ham United","starting_xi_player_ids":liverpool_xi,"source_substitute_ids":["english-player-8083","english-player-8080","english-player-8147","english-player-8081","english-player-8192"],"source_bench_order":[8083,8080,8147,8081,8192]},
            "lens":{"fixture_date":"2001-07-28","opponent":"Olympique Lyon","source_formation":"4-4-2 (source fixture listing; witness only)","starting_xi_player_ids":lens_xi,"source_substitute_ids":lens_bench,"fifth_fallback_player_id":fallback["id"],"fifth_fallback_reason":"S. Chabbert is in retained Lens annual squad capture as a reserve goalkeeper; the 28 July report does not list him. This fallback is not an appearance claim.","order_ids":lens_opening_ids}},
        "order_changes":order_rows,
        "no_photo":{"carriers":[ANELKA_CARRIER,TRAORE_CARRIER],"policy":"remove both stale portraits with existing indexed native-no-photo writer; all other active portrait flags/pixels preserved"},
        "scope":"Replace only the Liverpool Anelka identity at carrier8080 with existing Traore facts/skills, corrected Liverpool #30 shirt and native role values; replace the Lens Traore identity at carrier31819 with sourced Bruno facts and deterministic versioned ratings. Keep carrier families, clubs, roster counts and PSG Anelka unchanged. Correct Liverpool source bench to its exact five names. Record Lens first-fixture XI, its four named substitutes and one explicitly unsourced fifth goalkeeper fallback as plan witnesses only. Reorder only Liverpool and Lens native startup bytes to XI, selected subs, then reserves. Preserve the complete pre-existing Lens opening object, including its mode-1 policy; do not synthesize formation tactics or claim source deployment in package fields.",
        "limitations":["UEFA's 21 Dec 2001 report establishes the later PSG-to-Liverpool loan date; by itself it does not prove Anelka's absence from an earlier squad. The retained opening fixture and approved ownership disposition provide the separate opening-date context.","Sky's 31 Aug 2001 Traore transfer row establishes the later Liverpool-to-Lens move; it does not by itself establish exact 18 Aug matchday availability.","Bruno source DOB selection is France Football/FC Metz, corroborated by Premier League; Sky lists a conflicting October date, so disagreement remains documented.","Bruno source shirt23 is evidence only because compact dd6360 shirt write is unsupported.","Lens fifth substitute is a declared roster fallback, not source-confirmed matchday appearance.","This opening snapshot does not model Bruno's later Rayo loan or certify later season assignment."]}
    plan["transaction_id"]=digest(packages.canonical_json_bytes(plan))[:24]
    return plan


def _expected_source_plan(base, plan):
    if plan.get("schema")!=SCHEMA or plan.get("mode")!=MODE:
        raise ValueError("unique transaction schema/mode mismatch")
    path=_path(plan["source_input"]["path"])
    if digest(path.read_bytes())!=plan["source_input"]["sha256"]:
        raise ValueError("transaction input source SHA differs")
    actual=prepare(base,path)
    if actual!=plan:
        raise ValueError("source/native request does not reproduce exact plan")


def verify(base, plan):
    _expected_source_plan(base,plan)


def _set_proof(actor, proof):
    actor["proof"]=copy.deepcopy(proof)
    for fallback in actor.get("fact_fallbacks",[]):
        fallback["proof"]=copy.deepcopy(proof)


def bind(package, plan):
    base=registry.load_registered_release(plan["season"],plan["release_id"])
    verify(base,plan)
    source_package=pipeline.read_json_file(base.package_path)
    if package!=source_package or digest(packages.canonical_json_bytes(package))!=plan["parent"]["package_sha256"]:
        raise ValueError("bind requires exact complete parent package preimage")
    result=copy.deepcopy(package)
    players={p["carrier_id"]:p for p in result["players"]}
    clubs={c["carrier_id"]:c for c in result["clubs"]}
    artifact=artifact_id(plan); proof={"artifact_id":artifact,"grade":"source-receipt"}
    source_id="source-"+artifact
    for row in plan["updates"]:
        actor=players[row["carrier_id"]]
        if actor!=row["before"]:
            raise ValueError("identity actor preimage differs")
        replacement=copy.deepcopy(row["after"])
        # Remove prototype placeholder in the only explicit compact fallback.
        for f in replacement.get("fact_fallbacks",[]):
            f["proof"]=copy.deepcopy(proof)
        replacement["proof"]=copy.deepcopy(proof)
        actor.clear(); actor.update(replacement)
    from scripts import season_rating_calibration_v3 as rating_model
    model_path=registry.ROOT/"scripts/season_rating_calibration_v3.py"
    if registry.sha256_file(model_path)!=plan["source_choice"]["ratings"]["model_sha256"]:
        raise ValueError("Bruno editorial rating model changed")
    from statistics import median
    strength=median(p["ratings"]["values"]["quality"] for p in result["players"]
                    if p["club_id"]==clubs[LENS]["id"] and p["carrier_id"]!=TRAORE_CARRIER)
    bruno=players[TRAORE_CARRIER]
    rating_player=copy.deepcopy(bruno)
    rating_player.pop("ratings",None); rating_player.pop("proof",None); rating_player.pop("fact_fallbacks",None)
    rating_input={"player":rating_player,"strength":strength,"state":"unknown","snapshot":"2001-08-01",
                  "model_sha256":plan["source_choice"]["ratings"]["model_sha256"]}
    vals=rating_model.editorial(bruno,strength,"unknown",dt.date(2001,8,1))
    vals["handling"]=max(1,min(20,vals["handling"]))
    if (digest(packages.canonical_json_bytes(rating_input))!=plan["source_choice"]["ratings"]["input_sha256"]
            or digest(packages.canonical_json_bytes(vals))!=plan["source_choice"]["ratings"]["output_sha256"]
            or vals!=plan["source_choice"]["rating_output"]):
        raise ValueError("Bruno deterministic rating input/output differs")
    bruno["ratings"]={"profile":"pm99-visible-skills-v1","values":vals,
        "provenance":{"method":"identity-club-role-age-optional-editorial-calibration-v3",
            "proof_grade":"reviewed-editorial","source_ids":["source-bound-rating-calibration-v3"]}}
    liverpool=clubs[LIVERPOOL]; lens=clubs[LENS]
    opening=plan["opening"]
    liverpool["roster_player_ids"]=_ids_from_carriers(result,plan["order_changes"],LIVERPOOL,opening["liverpool"]["starting_xi_player_ids"]+opening["liverpool"]["source_substitute_ids"])
    lens["roster_player_ids"]=_ids_from_carriers(result,plan["order_changes"],LENS,opening["lens"]["order_ids"])
    liverpool["opening"]["substitute_player_ids"]=list(opening["liverpool"]["source_substitute_ids"])
    liverpool["opening"]["proof"]=copy.deepcopy(proof)
    # Keep the exact pre-existing mode-1 Lens opening object. Source XI, bench,
    # and listed formation remain in the source plan witness only; this adapter
    # does not author package tactics/deployment fields for Lens.
    # A true fixed-size native no-photo state is established by the publisher
    # using package assets and the same selected carrier set.
    portraits=result["assets"]["portraits"]
    selected={players[ANELKA_CARRIER]["id"],players[TRAORE_CARRIER]["id"]}
    portraits[:]=[p for p in portraits if p.get("player_id") not in selected]
    portraits.extend({"player_id":pid,"status":"native-no-photo","proof":copy.deepcopy(proof),
        "review_reason":"The carrier's previous identity portrait was removed during identity replacement; no new portrait source was admitted."} for pid in sorted(selected))
    portraits.sort(key=lambda p:p["player_id"])
    result["artifacts"].append({"id":artifact,"kind":"season-input","sha256":digest(packages.canonical_json_bytes(plan)),"media_type":"application/json","relative_path":filename(plan)})
    result["artifacts"].sort(key=lambda a:a["id"])
    result["sources"].append({"id":source_id,"title":"Dated Anelka/Traore/Lens opening ownership correction","uri":"https://www.fcmetz.com/fr/Squad/Player?id=29","proof_grade":"source-receipt","evidence_artifact_id":artifact})
    result["sources"].sort(key=lambda x:x["id"])
    result["proofs"].append({"id":"proof-"+artifact,"artifact_id":artifact,"grade":"source-receipt","covers":["Liverpool-Anelka-December-arrival-excluded-from-opening","Liverpool-Traore-18-Aug-matchday-bench","Lens-Bruno-28-Jul-matchday-bench","PSG-Anelka-preserved","exact-five-Liverpool-bench","four-Lens-bench-and-declared-fallback"]})
    result["proofs"].sort(key=lambda x:x["id"])
    packages.validate_package(result,strict=False)
    return result


def _ids_from_carriers(package, order_rows, club_carrier, opening_ids):
    club=_club(package,club_carrier)
    # The transaction changes no membership count. Order all members by the
    # explicit native order postimage stored in the plan.
    actor_by_id={p["id"]:p for p in package["players"]}
    ids=list(club["roster_player_ids"])
    selected=set(opening_ids)
    rest=[pid for pid in ids if pid not in selected]
    changed={row["carrier_id"]:row["after"] for row in order_rows if row["club_carrier_id"]==club_carrier}
    base=registry.load_registered_release("2001-02","sourced-keeper-profile-countries-20261023-r182a")
    jug=(base.game_path/"DBDAT/JUG98030.FDI").read_bytes()
    order_by_carrier=_actor_order_map(package,jug)
    for carrier,target in changed.items(): order_by_carrier[carrier]=target
    rest.sort(key=lambda pid:order_by_carrier[actor_by_id[pid]["carrier_id"]])
    return [*opening_ids,*rest]


def source_artifact(plan):
    verify(registry.load_registered_release(plan["season"],plan["release_id"]),plan)
    data=packages.canonical_json_bytes(plan)
    if data.count(b"\n")<1 or not data.endswith(b"\n") or data.endswith(b"\n\n"):
        raise ValueError("source plan artifact must have exactly one terminal LF")
    return {"filename":filename(plan),"document":copy.deepcopy(plan),"sha256":digest(data),"bytes":data}


def apply_photo_archive(minifoto: bytes, plan: dict) -> tuple[bytes, dict]:
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    verify(base, plan)
    original = (base.game_path / "DBDAT/MINIFOTO.PKF").read_bytes()
    if digest(original) != plan["parent"]["minifoto_sha256"]:
        raise ValueError("registered portrait archive differs from the exact parent")
    from scripts.season_duplicate_ownership_delta_v1 import no_photo_archive
    result, places = no_photo_archive(original, selected_carriers(plan))
    if minifoto not in (original, result):
        raise ValueError("portrait transaction requires its exact parent or exact postimage")
    return result, copy.deepcopy(places)


def apply(jug: bytes, eq: bytes, plan: dict) -> tuple[bytes,bytes]:
    base=registry.load_registered_release(plan["season"],plan["release_id"])
    verify(base,plan)
    original_jug=(base.game_path/"DBDAT/JUG98030.FDI").read_bytes()
    original_eq=(base.game_path/"DBDAT/EQ98030.FDI").read_bytes()
    if (digest(original_jug),digest(original_eq))!=(plan["parent"]["jug_sha256"],plan["parent"]["eq_sha256"]):
        raise ValueError("registered native preimage differs")
    pre=(digest(original_jug),digest(original_eq)); supplied=(digest(jug),digest(eq))
    package=bind(pipeline.read_json_file(base.package_path),plan)
    codes=compiler._extract_country_codes_from_textos(base.game_path/"DBDAT/TEXTOS.PKF")
    changed_ids={_id_for(package,ANELKA_CARRIER)["id"],_id_for(package,TRAORE_CARRIER)["id"]}
    compiler_package=copy.deepcopy(package)
    # The shared replacement compiler intentionally preserves mode-1 shirt
    # bytes. Target carrier8080 is full dd6361 and is updated with the
    # separately guarded one-byte API below.
    _id_for(compiler_package,ANELKA_CARRIER)["facts"]["shirt_number"]={"policy":"preserve-existing-mode1"}
    candidate=ownership_delta.compile_players(original_jug,compiler_package,changed_ids,codes)
    shirt_updates={ANELKA_CARRIER:{"native_name":read_initial_order({e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}[ANELKA_CARRIER].decode_payload(candidate)).name,
                                    "before_number":9,"number":30}}
    candidate,shirt_changes=rewrite_indexed_native_shirt_numbers(candidate,shirt_updates)
    if not shirt_changes and (candidate!=original_jug):
        # Idempotent source replay produces no shirt diff; otherwise record the
        # expected actual change in plan metadata and retain byte checks below.
        pass
    replacements=[]
    candidate_entries={e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
    for row in plan["order_changes"]:
        replacements.append(OrderReplacement(row["carrier_id"],row["after_name"],row["before"],row["after"]))
    # Caller preflight above proves every selected mode-1 Lens carrier is
    # exclusively owned and both full club rosters have valid permutations.
    candidate=patch_initial_orders(candidate,replacements,allow_compact=True)
    # Validate only target clubs' sequences; every XI stays in positions 1-11.
    final_orders=_actor_order_map(package,candidate)
    expected_openings={
        LIVERPOOL:plan["opening"]["liverpool"]["starting_xi_player_ids"]+plan["opening"]["liverpool"]["source_substitute_ids"],
        LENS:plan["opening"]["lens"]["order_ids"],
    }
    for club_carrier, player_ids in expected_openings.items():
        for index, pid in enumerate(player_ids,1):
            actor=next(p for p in package["players"] if p["id"]==pid)
            if final_orders[actor["carrier_id"]]!=index:
                raise ValueError("source XI/bench is not first in the bounded native startup order")
    for club_carrier in (LIVERPOOL,LENS):
        club=_club(package,club_carrier)
        values=sorted(final_orders[_id_for(package,carrier)["carrier_id"]] for carrier in [p["carrier_id"] for p in package["players"] if p["id"] in club["roster_player_ids"]])
        if values!=list(range(1,len(club["roster_player_ids"])+1)):
            raise ValueError("target roster startup orders are not contiguous")
    candidate_eq=original_eq
    from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
    changed_carriers={row["carrier_id"] for row in plan["order_changes"]}|{ANELKA_CARRIER,TRAORE_CARRIER}
    preserve_other_records(original_jug,candidate,changed_carriers)
    if candidate_eq!=original_eq:
        raise ValueError("transaction must preserve every EQ byte")
    if supplied not in (pre,(digest(candidate),digest(candidate_eq))):
        raise ValueError("only exact complete original or complete postimage JUG/EQ pair accepted")
    return candidate,candidate_eq


def reject_factory_recipe(package):
    if any(a.get("id","").startswith(PREFIX) for a in package.get("artifacts",[])):
        raise ValueError("Anelka/Traore/Lens transaction requires exact source-bound reconstruction")


def reconstruction(previous,release_id):
    # MODE is checked before accessing inherited receipt/locator fields, which
    # may be absent or unsafe on a different recipe chain.
    receipt_path=getattr(previous,"compiler_receipt_path",None)
    if receipt_path is None:
        return None
    receipt=pipeline.read_json_file(receipt_path)
    if receipt.get("compilation_mode")!=MODE:
        return None
    relative=getattr(previous,"locator",{}).get("sourced_profile_assignment_plan_path")
    if not relative:
        raise ValueError("owned chain receipt lacks exact source plan locator")
    path=(registry.ROOT/relative).resolve()
    if not path.is_relative_to(registry.ROOT.resolve()):
        raise ValueError("source-bound plan escaped workspace")
    plan=pipeline.read_json_file(path)
    if plan.get("schema")!=SCHEMA or plan.get("mode")!=MODE:
        raise ValueError("receipt points to another transaction schema/mode")
    base=registry.load_registered_release(plan["season"],plan["release_id"])
    verify(base,plan)
    expected=(previous.package_path.parent/filename(plan)).resolve()
    if path!=expected or digest(path.read_bytes())!=receipt.get("original_profile_assignment_plan_sha256"):
        raise ValueError("receipt plan path or raw SHA differs")
    expected_package=bind(pipeline.read_json_file(base.package_path),plan)
    if pipeline.read_json_file(previous.package_path)!=expected_package:
        raise ValueError("source recipe fails full package replay")
    descriptor=previous.package_path.parent/"role-delta-input.json"
    expected_descriptor={"season":base.season,"release_id":base.release_id,
        "package_sha256":plan["parent"]["package_sha256"],"jug_sha256":plan["parent"]["jug_sha256"],
        "updates":[],"unresolved":[]}
    if pipeline.read_json_file(descriptor)!=expected_descriptor:
        raise ValueError("SOURCE inert role descriptor differs from the exact parent")
    prior_inventory=pipeline.read_json_file(previous.inventory_path)
    pipeline.assert_tree_matches_inventory(previous.game_path,prior_inventory)
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,prior_inventory)
    if (pipeline.read_json_file(rebuilt.package_path)!=expected_package
            or rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes()):
        raise ValueError("complete SOURCE replay recipe bytes differ")
    return {"season":plan["season"],"release_id":release_id,"complete_game_inventory_identical":True,
            "complete_recipe_identical":True,"compilation_mode":MODE}
