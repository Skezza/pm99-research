"""Private source-bound 2001 Altrincham whole-club adapter.

The adapter is an isolated prototype. It composes one dated 18-player source
roster onto the existing mode-1 carrier by using the already reviewed Alty
player compiler, source-person composer, EQ label writer, existing order and
roster writers, existing ENT manager writer, and the no-photo archive helper.
It never writes a game tree.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import tempfile
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from app.editor_actions import _patch_indexed_eq_team_string_payload, edit_team_roster_eq_jug_linked
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, patch_initial_orders, read_initial_order
from app import indexed_jug_roles
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_editorial_ratings_v1 as ratings
from scripts import season_historical_roster_audit_v1 as roster_reader
from scripts import season_manager_display_repair_v1 as manager_display
from scripts import season_package_v2 as package_v2
from scripts import season_release_registry_v1 as registry


HERE = Path(__file__).resolve().parent
INPUT_PATH = (registry.ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/"
              "resume-qa/altrincham-2001-adapter-v2/altrincham-2001-02-opening-18-input-v2.json")
INPUT_SHA256 = "24c57d6cd17047a14a2da6ed5dd13b3729e7cf3a9bd847441cd7fb980ce93a02"
RECEIPT_PATH = (registry.ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/"
                "resume-qa/altrincham-2001-adapter-v2/altrincham-2001-02-source-receipts-v2.json")
RECEIPT_SHA256 = "f9a112d1dbfd8e78f1d68565da846c8a515d23ab5b24383ef3648451cc0216f0"

# Import only the three already-reviewed Alty helper functions used below.
# The helper module is pinned in implementation_bindings; its old-parent
# orchestration is never called from this adapter.
_HELPER_PATH = registry.ROOT / "scripts/season_altrincham_joint_native_v1.py"
from scripts import season_altrincham_joint_native_v1 as _HELPER

SCHEMA = "pm99-source-bound-altrincham-2001-whole-club-exchange-v2"
MODE = "exact-source-2001-08-11-altrincham-18-mode1-whole-club-v2"
SEASON = "2001-02"
FILENAME = "altrincham-2001-whole-club-exchange-v2.json"
SOURCE_PLAN_FILENAME = "altrincham-2001-whole-club-source-plan-v2.json"
REQUIRED_NATIVE = ("JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI", "MINIFOTO.PKF")
READ_ONLY_NATIVE = ("TEXTOS.PKF",)
_CACHE: dict[str, dict[str, Any]] = {}

_ROLE_FINE = {"G": [0], "D": [4], "M": [9], "F": [12]}
_EXPECTED_NAMES = [
    "Stuart Coburn", "Steve Hawes", "Chris Adams", "Mark Maddox", "Mark Sertori",
    "Jason Gallagher", "Kevin Hulme", "Ian Craney", "Carl Furlong", "Rod Thornley",
    "Danny Murphy", "Jeremy Illingworth", "Dale Newbrook", "Gary Scott", "Lee Poland",
    "Terry Bowker", "Dave Swannick", "Keith Mairs",
]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return registry.sha256_file(path)


def _verify_source_identity_keys(data: dict) -> None:
    for row in data["players"]:
        slug = re.sub(r"[^a-z0-9]+", "-", row["source_name"].casefold()).strip("-")
        if (row.get("source_provider") != "altrincham-aug11-source-row"
                or row.get("source_person_id") != f"altrincham-aug11-source-row:2001-08-11:{slug}"
                or row.get("source_identity_policy") != "original-altrincham-2001-08-11-friendly-full-name-row-v2"):
            raise ValueError(f"source identity key/policy is not bound to the 2001-08-11 row: {row['source_name']}")


def _read_input() -> dict:
    raw = INPUT_PATH.read_bytes()
    if _sha(raw) != INPUT_SHA256:
        raise ValueError("Altrincham 2001 typed input bytes changed")
    receipt_raw = RECEIPT_PATH.read_bytes()
    if _sha(receipt_raw) != RECEIPT_SHA256:
        raise ValueError("Altrincham 2001 source receipt bytes changed")
    data, receipt = json.loads(raw), json.loads(receipt_raw)
    if (data.get("schema") != "pm99-altrincham-2001-02-opening-18-data-proposal-v2"
            or receipt.get("schema") != "pm99-altrincham-2001-02-source-input-receipts-v2"
            or receipt.get("source_bindings") != data.get("source_bindings")):
        raise ValueError("Altrincham 2001 typed input/receipt schema or bindings differ")
    if [p.get("source_name") for p in data.get("players", [])] != _EXPECTED_NAMES:
        raise ValueError("Altrincham typed source rows differ from the approved 18-name order")
    if [p.get("source_order") for p in data["players"]] != list(range(1, 19)):
        raise ValueError("Altrincham source-order sequence must be exactly 1..18")
    if data.get("players_written") != 18:
        raise ValueError("Altrincham source input must contain exactly 18 roster rows")
    _verify_source_identity_keys(data)
    return data


def _source_body(data: dict, source_id: str) -> bytes:
    rows = [x for x in data["source_bindings"] if x.get("id") == source_id]
    if len(rows) != 1:
        raise ValueError(f"expected one source binding for {source_id}")
    row = rows[0]
    if row.get("kind") != "raw-source-body" or not row.get("path"):
        raise ValueError(f"source {source_id} is not a retained raw body")
    path = registry.ROOT / row["path"]
    registry.relative_workspace_path(path)
    body = path.read_bytes()
    if _sha(body) != row.get("sha256"):
        raise ValueError(f"source body hash changed for {source_id}")
    return body


def _verify_sources(data: dict) -> dict:
    # Every retained raw body, including the official manager-history page, is re-read and hashed.
    for row in data["source_bindings"]:
        if row.get("kind") == "raw-source-body":
            _source_body(data, row["id"])
        elif row.get("kind") == "source-receipt":
            path = registry.ROOT / row["path"]
            if _file_sha(path) != row["sha256"]:
                raise ValueError(f"source receipt changed: {row['id']}")
        else:
            raise ValueError(f"unverified/non-body Altrincham source binding kind: {row.get('kind')}")

    report = BeautifulSoup(_source_body(data, "aug11-report"), "lxml")
    report_text = " ".join(report.get_text(" ", strip=True).split())
    if ("ALTRINCHAM (2) 3 NORTHWICH VICTORIA (1) 2" not in report_text
            or "Friendly Match, played on Saturday, 11th August 2001" not in report_text
            or "Moss Lane" not in report_text):
        raise ValueError("11-Aug original report does not reproduce fixture/date/venue")
    # Reparse the two-column squad table in alternating home/away row order.
    lines = [x.strip() for x in report.get_text("\n").splitlines() if x.strip()]
    try:
        start = next(i for i, x in enumerate(lines) if x == "TEAMS:")
        end = next(i for i in range(start + 1, len(lines)) if lines[i] == "BACKGROUND")
    except StopIteration as exc:
        raise ValueError("11-Aug original report has no delimited team sheet") from exc
    sheet = lines[start:end]
    number_positions = [i for i, line in enumerate(sheet)
                        if re.fullmatch(r"\d{1,2}\.?", line)]
    if len(number_positions) < 36:
        raise ValueError("11-Aug original report does not list both 18-player teams")
    home_names = []
    for index, pos in enumerate(number_positions):
        if index % 2 == 0:
            if pos + 1 >= len(sheet):
                raise ValueError("malformed original team-sheet row")
            name = re.sub(r"\s*\([^)]*\)\s*$", "", sheet[pos + 1]).strip()
            home_names.append(name)
    normalise = lambda value: " ".join(value.casefold().split())
    if [normalise(x) for x in home_names] != [normalise(x) for x in _EXPECTED_NAMES]:
        raise ValueError("11-Aug original Altrincham team sheet differs from typed 18 names/order")
    if [p["membership"] for p in data["players"][:11]] != ["listed_starting_xi"] * 11:
        raise ValueError("first 11 source rows must remain the report's starting XI")
    if [p["membership"] for p in data["players"][11:]] != ["listed_reserve"] * 7:
        raise ValueError("last 7 source rows must remain listed reserves")

    role_text = report_text.casefold()
    role_phrases = ("4-4-2 formation", "furlong and thornley at the striking end",
        "hawes and adams at full-back", "maddox at centre-back", "sertori", 
        "gallagher on the right", "murphy on the left", "craney and hulme in the centre")
    if any(part not in role_text for part in role_phrases):
        raise ValueError("11-Aug original report no longer supports the 4-4-2 role map")

    next_report = BeautifulSoup(_source_body(data, "aug14-report"), "lxml")
    next_text = " ".join(next_report.get_text(" ", strip=True).split())
    for text in ("WITTON ALBION (1) 1 ALTRINCHAM (1) 3", "played on Tuesday, 14th August 2001",
                 "Bernard Taylor", "Graham Heathcote", "Dale Newbrook", "Gary Scott",
                 "Lee Poland", "Terry Bowker", "Moss Lane"):
        if text not in next_text:
            raise ValueError(f"14-Aug original Altrincham report lacks corroborating text: {text}")
    manager = BeautifulSoup(_source_body(data, "manager-history"), "lxml")
    manager_rows = {}
    for row in manager.select(".am-row[role='row']"):
        cells = [" ".join(cell.get_text(" ", strip=True).split()) for cell in row.select("[role='cell']")]
        if len(cells) == 2:
            manager_rows[cells[0]] = cells[1]
    if manager_rows.get("2000–01") != "Mark Ward" or manager_rows.get("2001–02") != "Bernard Taylor":
        raise ValueError("official manager-history exact period/manager rows differ")
    if data["club_facts"].get("manager_name") != manager_rows["2001–02"]:
        raise ValueError("2001-02 Altrincham manager does not match the official exact period row")

    appearance = BeautifulSoup(_source_body(data, "season-appearances"), "lxml")
    appearance_text = " ".join(appearance.get_text(" ", strip=True).split())
    if "all players named in the first team squad for matches played this season" not in appearance_text:
        raise ValueError("2001-02 official appearance page no longer states first-team squad scope")
    for name in _EXPECTED_NAMES:
        if name.casefold() not in appearance_text.casefold():
            # A few pre-season-only reserves need not appear in the seasonal
            # league/cup summary; their 11-Aug source row remains the evidence.
            continue

    profile = BeautifulSoup(_source_body(data, "2000-profile-cross-season"), "lxml")
    profile_text = " ".join(profile.get_text(" ", strip=True).split()).casefold()
    if "steve hawes (d.o.b. 17 july 1978" not in profile_text:
        raise ValueError("exact Hawes 2000-01 Alty biography DOB binding changed")
    if "jason gallagher (d.o.b. 25 march 1972)" not in profile_text:
        raise ValueError("exact Gallagher 2000-01 Alty biography DOB binding changed")
    # The old source's Coburn date is deliberately not consumed because its
    # counterclaim remains open. Do not silently link Maddix to Maddox.
    hawes = BeautifulSoup(_source_body(data, "hawes-11v11"), "lxml")
    hawes_text = " ".join(hawes.get_text(" ", strip=True).split())
    title = hawes.title.get_text(" ", strip=True) if hawes.title else ""
    if (title != "Steve Hawes Football Player Statistics | 11v11.com"
            or not all(x in hawes_text for x in ("Steve Hawes", "Date of birth 17 July 1978",
                "Nationality English", "Altrincham 01 Nov 1999 17 May 2002"))):
        raise ValueError("Hawes exact 11v11 DOB/nationality/tenure source differs")

    ground = BeautifulSoup(_source_body(data, "official-ground-history"), "lxml")
    ground_text = " ".join(ground.get_text(" ", strip=True).split())
    if "Moss Lane" not in ground_text:
        raise ValueError("official Altrincham ground history does not support Moss Lane")
    league = BeautifulSoup(_source_body(data, "fchd-league-history"), "lxml")
    league_text = " ".join(league.get_text(" ", strip=True).split())
    if "2001-02 NPL-P" not in league_text or "9/23" not in league_text:
        raise ValueError("independent season history no longer supports Altrincham NPL Premier")
    return {"source_input_sha256": INPUT_SHA256, "source_receipt_sha256": RECEIPT_SHA256,
        "aug11_report_sha256": next(x["sha256"] for x in data["source_bindings"] if x["id"] == "aug11-report"),
        "aug14_report_sha256": next(x["sha256"] for x in data["source_bindings"] if x["id"] == "aug14-report"),
        "manager": "Bernard Taylor", "ground": "Moss Lane", "roster_count": 18}


def _parent(base) -> tuple[dict, dict[str, bytes]]:
    if base.season != SEASON:
        raise ValueError("Altrincham 2001 source plan is season-bound to 2001-02")
    registered = registry.load_registered_release(SEASON, base.release_id)
    if (Path(registered.package_path).resolve() != Path(base.package_path).resolve()
            or Path(registered.game_path).resolve() != Path(base.game_path).resolve()):
        raise ValueError("passed parent is not the exact registered release tree")
    package_raw = base.package_path.read_bytes()
    package = json.loads(package_raw)
    paths = {name: base.game_path / "DBDAT" / name for name in REQUIRED_NATIVE + READ_ONLY_NATIVE}
    native = {name: path.read_bytes() for name, path in paths.items()}
    return {"season": SEASON, "release_id": base.release_id,
        "package_path": registry.relative_workspace_path(base.package_path),
        "package_sha256": _sha(package_raw),
        "package_canonical_sha256": registry.canonical_document_sha256(base.package_path),
        "native_sha256": {name: _sha(value) for name, value in native.items()}}, native


def _package_target(base, package: dict, native: dict[str, bytes]):
    clubs = {c["carrier_id"]: c for c in package["clubs"]}
    target = clubs.get(3310)
    kidder = clubs.get(370)
    if (target is None or target.get("id") != "club-3310"
            or target.get("name") != "Kidderminster Harriers"
            or target.get("manager_id") != "manager-807"):
        raise ValueError("3310 current club/manager target differs from the reviewed preimage")
    if kidder is None or kidder.get("name") != "Kidderminster Harriers":
        raise ValueError("real Kidderminster carrier370 is absent or relabeled")
    slots = sorted((copy.deepcopy(p) for p in package["players"] if p["club_id"] == target["id"]),
                   key=lambda p: p["carrier_id"])
    keepers = [copy.deepcopy(p) for p in package["players"] if p["club_id"] == kidder["id"]]
    if len(slots) != 18 or len({p["carrier_id"] for p in slots}) != 18:
        raise ValueError("current 3310 must remain exactly 18 unique source destination slots")
    # Every displaced Kidderminster actor has one same-name/DOB counterpart on
    # the canonical 370 club; protect those 370 actors and all their bytes.
    kidder_by_key: dict[tuple[str, str], list[dict]] = {}
    for row in keepers:
        key = (str(row.get("source_name", "")).casefold(),
               json.dumps(row.get("facts", {}).get("birth_date"), sort_keys=True))
        kidder_by_key.setdefault(key, []).append(row)
    crosswalk = []
    for row in slots:
        key = (str(row.get("source_name", "")).casefold(),
               json.dumps(row.get("facts", {}).get("birth_date"), sort_keys=True))
        matches = kidder_by_key.get(key, [])
        if len(matches) != 1:
            raise ValueError(f"3310 actor {row['carrier_id']} lacks one exact 370 name/DOB counterpart")
        crosswalk.append({"old_3310_carrier": row["carrier_id"], "preserved_370_carrier": matches[0]["carrier_id"],
            "source_name": row.get("source_name"), "birth_date": copy.deepcopy(row.get("facts", {}).get("birth_date"))})
    if len({r["preserved_370_carrier"] for r in crosswalk}) != 18:
        raise ValueError("Kidderminster preservation crosswalk is not one-to-one")

    jug = native["JUG98030.FDI"]
    jidx = IndexedFDIFile.from_bytes(jug)
    jentries = {e.record_id: e for e in jidx.entries}
    eq = native["EQ98030.FDI"]
    eqidx = IndexedFDIFile.from_bytes(eq)
    eentries = {e.record_id: e for e in eqidx.entries}
    eqentry = eentries.get(3310)
    if eqentry is None:
        raise ValueError("3310 EQ record is absent")
    roster = parse_eq_external_team_roster_payload(eq[eqentry.payload_offset:eqentry.payload_offset + eqentry.payload_length], {})
    ids = {p["carrier_id"] for p in slots}
    if (roster is None or roster.mode_byte != 1 or len(roster.rows) != 18
            or {r.player_record_id for r in roster.rows} != ids):
        raise ValueError("3310 native preimage is not an exact mode1 18-player roster")
    if [(r.player_record_id, r.slot_index, r.flag) for r in roster.rows if r.flag] != [(10958, 8, 1)]:
        raise ValueError("3310 exact sole flag1 preimage changed; only 10958 row8 is source-dispositioned")
    all_owners: dict[int, set[int]] = {}
    for entry in eqidx.entries:
        parsed = parse_eq_external_team_roster_payload(eq[entry.payload_offset:entry.payload_offset + entry.payload_length], {})
        if parsed is not None:
            for row in parsed.rows:
                all_owners.setdefault(row.player_record_id, set()).add(entry.record_id)
    if any(all_owners.get(pid) != {3310} for pid in ids):
        raise ValueError("each selected 3310 player must have exact exclusive EQ ownership")
    manager_holders, manager_names = _HELPER.whole._manager_graph(
        eq_path=base.game_path / "DBDAT/EQ98030.FDI", ent_path=base.game_path / "DBDAT/ENT98030.FDI")
    manager_owners = [x["carrier_id"] for x in manager_holders.get(807, [])]
    if manager_owners != [3310] or manager_names.get(807) != "Graham Allner":
        raise ValueError("manager807 exclusive owner or native preimage changed")
    for row in slots:
        if row["carrier_id"] not in jentries:
            raise ValueError(f"selected JUG carrier absent: {row['carrier_id']}")
    return target, slots, jentries, eentries, all_owners, roster, crosswalk


def _desired(data: dict) -> list[dict]:
    desired = []
    for row in data["players"]:
        name, position = row["source_name"], row["broad_position"]
        if position not in _ROLE_FINE:
            raise ValueError(f"unsupported editorial broad role for {name}")
        if row["source_order"] <= 11 and row["membership"] != "listed_starting_xi":
            raise ValueError("first eleven source-order rows must remain the witnessed starting team")
        if row["source_order"] > 11 and row["membership"] != "listed_reserve":
            raise ValueError("rows after the starting XI must remain listed reserves")
        dob, nationality = row.get("date_of_birth"), row.get("nationality")
        if name == "Stuart Coburn" and dob is not None:
            raise ValueError("Coburn source DOB conflict must remain native-preserved")
        if name == "Mark Maddox" and "Maddix" in row.get("source_person_id", ""):
            raise ValueError("Maddox spelling must not be joined to Maddix without proof")
        person = {"source_player_id": row["source_person_id"], "source_provider": row["source_provider"],
            "name": name, "given_name": name.split()[0], "family_name": name.split()[-1],
            "birth_date": dob, "identity_policy": row["source_identity_policy"],
            "identity_evidence": {"policy": row["source_identity_policy"], "raw_name": name,
                "source_order": row["source_order"], "fixture_date": "2001-08-11",
                "source_binding_id": "aug11-report", "source_input_sha256": INPUT_SHA256,
                "source_join_policy": row["source_join_policy"],
                "secondary_fact_status": row["secondary_fact_status"],
                "fact_bindings": copy.deepcopy(row["source_fact_bindings"])}}
        player = {"name": name, "birth_date": dob, "position": position,
            "nationality": nationality, "height_cm": None, "weight_kg": None,
            "membership": "starting_xi" if row["source_order"] <= 11 else "listed_reserve"}
        fallback = {"height_cm": {"method": "preserve-existing-mode1", "not_a_source_claim": True},
            "weight_kg": {"method": "preserve-existing-mode1", "not_a_source_claim": True},
            "shirt_number": {"method": "preserve-existing-mode1", "not_a_source_claim": True}}
        if dob is None:
            fallback["birth_date"] = {"policy": "preserve-existing-mode1", "method": "preserve-existing-mode1",
                "not_a_source_claim": True, "source_claim_status": row["secondary_fact_status"]}
        if nationality is None:
            fallback["nationality"] = {"policy": "preserve-existing-mode1", "method": "preserve-existing-mode1",
                "not_a_source_claim": True, "citizenship_inferred": False}
        desired.append({"source_person": person, "source_player": player,
            "membership": "starting_xi" if row["source_order"] <= 11 else "listed_reserve",
            "membership_source": {"path": next(x["path"] for x in data["source_bindings"] if x["id"] == "aug11-report"),
                "sha256": next(x["sha256"] for x in data["source_bindings"] if x["id"] == "aug11-report"),
                "date": "2001-08-11", "source_family": "official Altrincham archived team sheet"},
            "raw_evidence": {"source_family": "Altrincham official club archive",
                "source_name": name, "position_basis": row["position_basis"],
                "primary_role_historical_claim": row["position_basis"].startswith("report-4-4-2"),
                "fine_role_policy": "compatible editorial default G0/D4/M9/F12",
                "fact_fallbacks": fallback,
                "rating_policy": "existing editorial model; no period rating claim"}})
    if len({p["source_person"]["source_player_id"] for p in desired}) != 18:
        raise ValueError("Altrincham source person namespace repeats an identity key")
    return desired


def _country_codes(release) -> dict[str, int]:
    return _HELPER.compiler._extract_country_codes_from_textos(release.game_path / "DBDAT/TEXTOS.PKF")


def _editorial_ratings(player: dict, player_id: str, person_id: str, club_id: str) -> dict:
    day = "2001-08-11"
    # This exact source ID is attached to the package below; the rating model
    # remains editorial and does not claim the archive authored ratings.
    source_id = "altrincham-2001-official-archive-v1"
    hierarchy = {"schema_version": ratings.HIERARCHY_SCHEMA, "snapshot_date": day,
        "clubs": [{"club_id": club_id, "strength": 60, "source_ids": [source_id]}]}
    result = ratings.build_rating_output({"schema_version": ratings.INPUT_SCHEMA,
        "snapshot_date": day, "hierarchy": hierarchy,
        "players": [{"player_id": player_id, "person_id": person_id, "club_id": club_id,
            "position": player["position"], "birth_date": player["birth_date"],
            "height_cm": None, "squad_status": "substitute"}]})
    values = result["player_ratings"][0]["ratings"]
    values["provenance"] = {k: values["provenance"][k] for k in ("method", "proof_grade", "source_ids")}
    return values


def _compiler_inputs(package: dict, allocations: list[dict], artifact_id: str,
                     strength: int = 60) -> dict:
    result = copy.deepcopy(package)
    by_carrier = {p["carrier_id"]: p for p in result["players"]}
    changed = set()
    for allocation in allocations:
        carrier = allocation["carrier_id"]
        target = by_carrier[carrier]
        desired = allocation["replacement"]
        person = desired["source_person"]
        replacement = _HELPER._apply_source_person(target, desired,
            allocation["display"]["display_name"], artifact_id, strength,
            allocation["native_after"]["startup_order"], b"")
        # The generic legacy Alty helper defaults its rating date to the 2000
        # cohort. Replace only those editorial ratings with the correct 2001
        # snapshot using the same project rating model.
        replacement["ratings"] = _editorial_ratings(desired["source_player"], target["id"],
            replacement["person_id"], target["club_id"])
        target.clear()
        target.update(replacement)
        changed.add(target["id"])
    return result


def _build_package(base, package: dict, target: dict, allocations: list[dict], source_proof: dict,
                   crosswalk: list[dict], artifact_id: str, artifact_filename: str,
                   source_plan_doc: dict) -> dict:
    result = _compiler_inputs(package, allocations, artifact_id)
    source_club = next(c for c in result["clubs"] if c["carrier_id"] == 3310)
    source_club.update(name="Altrincham", full_name="Altrincham F.C.", ground_policy="write",
        ground_name="Moss Lane", identity_id=_HELPER.whole.builder._source_club_identity_id("england", "Altrincham"),
        roster_player_ids=[x["player_id"] for x in allocations],
        proof={"artifact_id": artifact_id, "grade": "source-receipt"})
    # division, capacity and opening are copied verbatim from mode1 parent.
    old_manager = next(m for m in result["managers"] if m["id"] == source_club["manager_id"])
    if old_manager.get("carrier_id") != 807 or old_manager.get("name") != "Graham Allner":
        raise ValueError("manager recipe preimage differs from the bound manager807 source")
    native_display, _ = manager_display.short_name("Bernard Taylor")
    if native_display != "Taylor":
        raise ValueError("existing manager short-name policy did not produce Taylor")
    old_manager.update(name="Bernard Taylor", policy="write", person_id="manager-altrincham-archive-bernard-taylor-2001-02",
        native_names={"surname": "Taylor", "display_name": "Taylor"},
        proof={"artifact_id": artifact_id, "grade": "source-receipt"})

    changed_players = [by for by in result["players"] if by["carrier_id"] in {x["carrier_id"] for x in allocations}]
    for player in changed_players:
        result["assets"]["portraits"] = [p for p in result["assets"]["portraits"] if p["player_id"] != player["id"]]
        result["assets"]["portraits"].append({"player_id": player["id"], "status": "native-no-photo",
            "proof": {"artifact_id": artifact_id, "grade": "source-receipt"},
            "review_reason": "Old Kidderminster identity portrait removed; no Altrincham replacement photo sourced."})
    result["assets"]["portraits"].sort(key=lambda p: p["player_id"])
    docbytes = package_v2.canonical_json_bytes(source_plan_doc)
    artifact = {"id": artifact_id, "kind": "season-input", "sha256": _sha(docbytes),
        "media_type": "application/json", "relative_path": artifact_filename}
    result["artifacts"] = sorted(result["artifacts"] + [artifact], key=lambda a: a["id"])
    result["sources"] = sorted(result["sources"] + [{"id": "altrincham-2001-official-archive-v1",
        "title": "Altrincham official 2001-02 preseason team sheet and club continuity",
        "uri": "https://web.archive.org/web/20061125000000id_/http://www.lusa.u-net.com/010811na.htm",
        "proof_grade": "source-receipt", "evidence_artifact_id": artifact_id}], key=lambda s: s["id"])
    result["proofs"] = sorted(result["proofs"] + [{"id": "proof-" + artifact_id,
        "artifact_id": artifact_id, "grade": "source-receipt",
        "covers": ["official 11-Aug-2001 18-person Altrincham preseason team sheet",
            "Bernard Taylor and Moss Lane source-backed club metadata",
            "source-identity replacement for exactly existing mode1 carrier3310"]}], key=lambda p: p["id"])
    package_v2.validate_package(result, strict=False)
    return result


def _compile_native(base, package: dict, source_proof: dict, target: dict, slots: list[dict],
                    jentries: dict, eentries: dict, owners: dict, roster, crosswalk: list[dict],
                    desired: list[dict], data: dict) -> dict:
    files = {name: (base.game_path / "DBDAT" / name).read_bytes() for name in REQUIRED_NATIVE + READ_ONLY_NATIVE}
    allocation = _HELPER.typed._assign_carriers(slots, files["JUG98030.FDI"], jentries, desired)
    if [x["replacement"]["source_person"]["name"] for x in allocation] != _EXPECTED_NAMES:
        raise ValueError("native carrier matching changed source row order")
    by_source_name = {x["replacement"]["source_person"]["name"]: x for x in allocation}
    if len(by_source_name) != 18:
        raise ValueError("source-to-carrier matching is not one-to-one")
    starters = [x for x in allocation if x["native_after"]["startup_order"] <= 11]
    if len(starters) != 11 or sum(x["replacement"]["source_player"]["position"] == "G" for x in starters) != 1:
        raise ValueError("source XI must have 11 people and exactly one keeper")
    if by_source_name["Stuart Coburn"]["replacement"]["source_player"]["position"] != "G":
        raise ValueError("source XI keeper identity differs")
    if by_source_name["Dale Newbrook"]["replacement"]["source_player"]["position"] != "G":
        raise ValueError("listed reserve keeper identity differs")

    artifact_id = "altrincham-2001-original-archive-source-v1"
    doc = {"schema": "pm99-private-altrincham-2001-whole-club-source-plan-v1",
        "source_release_id": base.release_id, "parent": source_proof["parent"],
        "source_input": {"path": registry.relative_workspace_path(INPUT_PATH), "sha256": INPUT_SHA256},
        "source_receipt": {"path": registry.relative_workspace_path(RECEIPT_PATH), "sha256": RECEIPT_SHA256},
        "source_bindings": copy.deepcopy(data["source_bindings"]),
        "source_fixture": {"date": "2001-08-11", "opponent": "Northwich Victoria",
            "competition": "friendly", "score": "Altrincham 3-2 Northwich Victoria",
            "venue": "Moss Lane", "cohort_type": "observed 18-person preseason team sheet, not formal registration"},
        "starting_xi": _EXPECTED_NAMES[:11], "listed_reserves": _EXPECTED_NAMES[11:],
        "formation": {"value": "4-4-2", "evidence": "official 11-Aug report prose",
            "native_mode1_tactics": "opaque-preserved", "native_formation_certified": False},
        "source_people_and_assignments": [{"source_order": x["native_after"]["startup_order"],
            "source_name": x["replacement"]["source_person"]["name"],
            "source_player_id": x["replacement"]["source_person"]["source_player_id"],
            "source_provider_namespace": x["replacement"]["source_person"]["source_provider"],
            "carrier_id": x["carrier_id"], "native_display": x["display"]["display_name"],
            "broad_role": x["replacement"]["source_player"]["position"],
            "fine_roles": _ROLE_FINE[x["replacement"]["source_player"]["position"]],
            "role_basis": x["replacement"]["raw_evidence"]["position_basis"],
            "birth_date": copy.deepcopy(x["replacement"]["source_player"]["birth_date"]),
            "nationality": copy.deepcopy(x["replacement"]["source_player"]["nationality"]),
            "unknown_fallbacks": copy.deepcopy(x["replacement"]["raw_evidence"]["fact_fallbacks"]),
            "prior_carrier": {"name": x["native_before"]["name"], "position": x["native_before"]["position"],
                "startup_order": x["native_before"]["startup_order"],
                "payload_sha256": x["native_before"]["payload_sha256"]}}
            for x in allocation],
        "preserve_real_kidderminster": {"carrier_id": 370,
            "old_3310_to_370_crosswalk": crosswalk,
            "all_370_player_payloads_and_owner_rows_preserved": True},
        "flag_disposition": {"eq_club_id": 3310, "row_carrier_id": 10958,
            "slot_index": 8, "api_slot_number": 9, "before": 1, "after": 0,
            "basis": "That exact prior mode1 identity is replaced by a positively listed Altrincham source player; only this bound flag is cleared."},
        "club_metadata": {"name": "Altrincham", "full_name": "Altrincham F.C.", "ground": "Moss Lane",
            "manager": "Bernard Taylor", "native_manager_display": "Taylor",
            "opaque_mode1_division_membership_capacity_opening": "preserve exact"},
        "write_scope": {"selected_jug_carriers": sorted(x["carrier_id"] for x in allocation),
            "selected_eq_records": [3310], "selected_ent_records": [807],
            "photo_carriers_cleared": sorted(x["carrier_id"] for x in allocation),
            "all_nonselected_native_payloads_preserved": True,
            "all_other_club_labels_ground_capacity_division_and_owners_preserved": True},
        "editorial_policy": {"roles": "broad period-role labels where source says so; compatible fine defaults G0/D4/M9/F12 otherwise",
            "unknown_secondary_facts": "explicit preserve-existing-mode1; no donor fact is represented as source fact",
            "ratings": "existing editorial model snapshot 2001-08-11, not historical sourced ratings",
            "photos": "no replacement portraits sourced; clear only these18 old identity images"},
        "publication_approved": False}
    result_package = _build_package(base, package, target, allocation, source_proof, crosswalk,
        artifact_id, SOURCE_PLAN_FILENAME, doc)

    # Compose only the 18 selected JUG identities through the existing Alty
    # generic player compiler. It also performs the project's native field
    # preservation/readback proof for source-null DOB/nationality/physical facts.
    changed_ids = {x["player_id"] for x in allocation}
    country_codes = _HELPER.compiler._extract_country_codes_from_textos(base.game_path / "DBDAT/TEXTOS.PKF")
    jug = _HELPER._compile_changed_players(files["JUG98030.FDI"], result_package, changed_ids, country_codes)

    # Pre-prove one exclusive owner per selected slot before any EQ order edit.
    if any(owners.get(x["carrier_id"]) != {3310} for x in allocation):
        raise ValueError("caller ownership preflight failed before mode1 roster rewrite")
    # Exact one-row availability clear through the existing linked EQ/JUG API
    # in a temporary directory. No shared or baseline path is writable here.
    with tempfile.TemporaryDirectory(prefix="alty2001-flag-") as tmp:
        temp = Path(tmp)
        eq_path, jug_path = temp / "EQ98030.FDI", temp / "JUG98030.FDI"
        eq_path.write_bytes(files["EQ98030.FDI"])
        jug_path.write_bytes(files["JUG98030.FDI"])
        edit_team_roster_eq_jug_linked(team_file=str(eq_path), player_file=str(jug_path),
            eq_record_id=3310, slot_number=9, flag=0, write_changes=True)
        eq_cleared = eq_path.read_bytes()
    old_eq = files["EQ98030.FDI"]
    old_team = eentries[3310]
    changed_offsets = [i for i, (a, b) in enumerate(zip(old_eq, eq_cleared)) if a != b]
    expected_flag_offset = old_team.payload_offset + next(r.raw_row_offset for r in roster.rows
        if r.player_record_id == 10958)
    if changed_offsets != [expected_flag_offset]:
        raise ValueError("existing flag editor changed more than the exact 10958 mode1 flag byte")
    if eq_cleared[expected_flag_offset] != 0:
        raise ValueError("mode1 availability flag did not clear to zero")

    # The existing mode1 whole-club writer keeps the opaque tactics prefix and
    # fixed 18-row carrier set; source order is the dated sheet's exact 1..18.
    ordered_carriers = [x["carrier_id"] for x in allocation]
    before_first_row = roster.rows[0].raw_row_offset
    eq = _HELPER.whole.rewrite_roster(eq_cleared, 3310, ordered_carriers)
    eq_index = IndexedFDIFile.from_bytes(eq)
    eq_entry = next(e for e in eq_index.entries if e.record_id == 3310)
    rostered_payload = eq_entry.decode_payload(eq)
    rostered_raw = eq[eq_entry.payload_offset:eq_entry.payload_offset + eq_entry.payload_length]
    rostered_rows = parse_eq_external_team_roster_payload(rostered_raw, {})
    if rostered_rows is None or rostered_rows.rows[0].raw_row_offset != roster.rows[0].raw_row_offset:
        raise ValueError("mode1 roster rewrite changed the opaque prefix/row boundary: "
            f"old={roster.rows[0].raw_row_offset} new={getattr(getattr(rostered_rows, 'rows', [None])[0], 'raw_row_offset', None)}")
    if rostered_payload[:roster.rows[0].raw_row_offset] != old_team.decode_payload(old_eq)[:before_first_row]:
        raise ValueError("mode1 roster rewrite changed opaque tactics/configuration prefix")
    payload = eq_entry.decode_payload(eq)
    labeled, label_changes = _patch_indexed_eq_team_string_payload(payload,
        short_name="Altrincham", stadium_name="Moss Lane", full_club_name="Altrincham F.C.")
    eq = delta.compiler._rebuild_indexed(eq, eq_index, {3310: labeled})

    # Rewrite startup order only after caller-side exact ownership, complete
    # permutation, and single-source-GK checks. This uses the existing low-level
    # writer because the high-level mode1 API refuses dd6361 carriers.
    current_index = IndexedFDIFile.from_bytes(jug)
    current_entries = {e.record_id: e for e in current_index.entries}
    order_changes = []
    for item in allocation:
        carrier = item["carrier_id"]
        current = read_initial_order(current_entries[carrier].decode_payload(jug))
        order_changes.append(OrderReplacement(carrier, current.name, current.order,
            item["native_after"]["startup_order"]))
    if sorted(x.after for x in order_changes) != list(range(1, 19)):
        raise ValueError("mode1 player order is not the complete 1..18 source permutation")
    native_goalkeepers = []
    after_jug_index = IndexedFDIFile.from_bytes(jug)
    after_entries = {e.record_id: e for e in after_jug_index.entries}
    for item in allocation:
        if item["replacement"]["source_player"]["position"] == "G":
            order = item["native_after"]["startup_order"]
            if order <= 11:
                native_goalkeepers.append(order)
    if native_goalkeepers != [1]:
        raise ValueError("the only source keeper among the first11 must be order1")
    jug = patch_initial_orders(jug, order_changes, allow_compact=True)
    final_jug_index = IndexedFDIFile.from_bytes(jug)
    final_jug_entries = {e.record_id: e for e in final_jug_index.entries}
    for item in allocation:
        carrier = item["carrier_id"]
        payload = final_jug_entries[carrier].decode_payload(jug)
        actual_order = read_initial_order(payload)
        actual_player = roster_reader.native_player(payload, carrier)
        if (actual_order.order != item["native_after"]["startup_order"]
                or roster_reader.normalise(actual_player["name"]) != roster_reader.normalise(item["display"]["display_name"])
                or actual_player["position"] != item["replacement"]["source_player"]["position"]
                or [v for v in actual_player["roles"] if v != 98] != _ROLE_FINE[item["replacement"]["source_player"]["position"]]):
            raise ValueError(f"native order/name/broad/fine role readback failed for carrier {carrier}")

    # Existing indexed ENT name writer; only exclusive manager807 changes.
    entidx = IndexedFDIFile.from_bytes(files["ENT98030.FDI"])
    ment = next(e for e in entidx.entries if e.record_id == 807)
    ent_payload = _HELPER.compiler._patch_ent_name(ment.decode_payload(files["ENT98030.FDI"]), 807,
        _HELPER.compiler._pm99_text("Bernard Taylor", label="dated Altrincham manager"),
        native_names={"surname": "Taylor", "display_name": "Taylor"})
    ent = delta.compiler._rebuild_indexed(files["ENT98030.FDI"], entidx, {807: ent_payload})
    photo_ids = {x["carrier_id"] for x in allocation}
    archive, photo_offsets = delta.no_photo_archive(files["MINIFOTO.PKF"], photo_ids)

    _HELPER.whole.preserve_other_records(files["JUG98030.FDI"], jug, photo_ids)
    _HELPER.whole.preserve_other_records(files["EQ98030.FDI"], eq, {3310})
    _HELPER.whole.preserve_other_records(files["ENT98030.FDI"], ent, {807})
    # Native EQ roster, flags, labels and mode1 tactic prefix all read back.
    final_team = next(e for e in IndexedFDIFile.from_bytes(eq).entries if e.record_id == 3310)
    final_rows = parse_eq_external_team_roster_payload(eq[final_team.payload_offset:final_team.payload_offset + final_team.payload_length], {})
    if (final_rows is None or final_rows.mode_byte != 1
            or [r.player_record_id for r in final_rows.rows] != ordered_carriers
            or any(r.flag != 0 for r in final_rows.rows)):
        raise ValueError("final source 3310 mode1 rows/order/zero flags differ")
    new_decoded = final_team.decode_payload(eq)
    if _HELPER.extract_team_labels(final_team.decode_payload(eq)) != ("Altrincham", "Moss Lane", "Altrincham F.C."):
        raise ValueError("native club label/ground readback differs")
    with tempfile.TemporaryDirectory(prefix="alty2001-manager-readback-") as tmp:
        eqp, entp = Path(tmp) / "EQ98030.FDI", Path(tmp) / "ENT98030.FDI"
        eqp.write_bytes(eq); entp.write_bytes(ent)
        holders, manager_names = _HELPER.whole._manager_graph(eq_path=eqp, ent_path=entp)
    if manager_names.get(807) != "Taylor" or [c["carrier_id"] for c in holders.get(807, [])] != [3310]:
        raise ValueError("native manager807 Taylor/owner readback differs")
    if _sha(archive) == _sha(files["MINIFOTO.PKF"]):
        # A no-op can be correct only if all selected identities already have
        # inactive/no archive entries. The helper returns the exact active
        # offsets; do not require a byte change in that valid case.
        if any(photo_offsets.values()):
            raise ValueError("no-photo archive reported active selected portraits but did not change bytes")

    return {"package": result_package,
        "native_files": {"JUG98030.FDI": jug, "EQ98030.FDI": eq,
            "ENT98030.FDI": ent, "MINIFOTO.PKF": archive},
        "source_plan": doc, "source_plan_bytes": package_v2.canonical_json_bytes(doc),
        "allocation": allocation, "photo_offsets": photo_offsets,
        "label_changes": label_changes, "parent": base}


def _implementation_bindings() -> list[dict[str, str]]:
    paths = {"adapter": Path(__file__).resolve(), "altrincham_2000_helpers": _HELPER_PATH,
        "altrincham_2000_typed_source_reader": registry.ROOT / "scripts/season_altrincham_source_reader_v1.py",
        "ownership_delta_native_compiler": Path(delta.__file__),
        "package_schema": Path(package_v2.__file__), "release_registry": Path(registry.__file__),
        "ratings_model": Path(ratings.__file__), "manager_display_policy": Path(manager_display.__file__),
        "fdi_indexed": Path(IndexedFDIFile.__module__.replace('.', '/')) if False else Path(__file__).resolve(),
        "eq_jug_codec": Path(parse_eq_external_team_roster_payload.__module__.replace('.', '/')) if False else Path(__file__).resolve(),
        "editor_actions": Path(edit_team_roster_eq_jug_linked.__module__.replace('.', '/')) if False else Path(__file__).resolve(),
        "order_writer": registry.ROOT / "upstream/pm99-skezmod-db-editor/app/player_initial_order.py",
        "indexed_role_writer": Path(indexed_jug_roles.__file__)}
    # Resolve the Python modules through module objects so plan paths are
    # explicit files rather than import-string descriptions.
    from app import editor_actions, eq_jug_linked, fdi_indexed, player_initial_order
    paths.update({"fdi_indexed": Path(fdi_indexed.__file__), "eq_jug_codec": Path(eq_jug_linked.__file__),
        "editor_actions": Path(editor_actions.__file__), "order_writer": Path(player_initial_order.__file__)})
    return [dict(name=name, path=registry.relative_workspace_path(path), sha256=_file_sha(path))
        for name, path in sorted(paths.items())]


def _binding_key(parent: dict, sources: list[dict], implementations: list[dict]) -> str:
    return _sha(package_v2.canonical_json_bytes({"schema": SCHEMA, "mode": MODE,
        "parent": parent, "source_bindings": sources, "implementation_bindings": implementations}))


def _compile(base, *, expected_plan: dict | None = None) -> dict:
    parent, native = _parent(base)
    data = _read_input()
    source_proof = _verify_sources(data)
    source_proof["parent"] = copy.deepcopy(parent)
    sources = [{"path": registry.relative_workspace_path(INPUT_PATH), "sha256": INPUT_SHA256},
        {"path": registry.relative_workspace_path(RECEIPT_PATH), "sha256": RECEIPT_SHA256}]
    for row in data["source_bindings"]:
        if row.get("path") and row.get("sha256"):
            sources.append({"path": row["path"], "sha256": row["sha256"]})
    sources = [{"path": path, "sha256": digest}
        for path, digest in sorted({(x["path"], x["sha256"]) for x in sources})]
    implementations = _implementation_bindings()
    key = _binding_key(parent, sources, implementations)
    cached = _CACHE.get(key)
    if cached is None:
        package = json.loads(base.package_path.read_text())
        target, slots, jentries, eentries, owners, roster, crosswalk = _package_target(base, package, native)
        desired = _desired(data)
        result = _compile_native(base, package, source_proof, target, slots, jentries,
            eentries, owners, roster, crosswalk, desired, data)
        plan = {"schema": SCHEMA, "mode": MODE, "season": SEASON,
            "parent": parent, "source_bindings": sources,
            "implementation_bindings": implementations,
            "inner_source_plan": result["source_plan"],
            "inner_source_plan_sha256": _sha(result["source_plan_bytes"]),
            "inner_source_plan_filename": SOURCE_PLAN_FILENAME,
            "package_postimage_sha256": _sha(package_v2.canonical_json_bytes(result["package"])),
            "native_postimages": {name: _sha(value) for name, value in result["native_files"].items()},
            "selected_jug_carriers": sorted(x["carrier_id"] for x in result["allocation"]),
            "selected_eq_carriers": [3310], "selected_ent_carriers": [807],
            "selected_photo_carriers": sorted(x["carrier_id"] for x in result["allocation"]),
            "selected_photo_offsets": {str(k): list(v) for k, v in result["photo_offsets"].items()},
            "players_written": 18,
            "scope": ("Replace the duplicated Kidderminster identity/roster on mode1 carrier3310 with the exact "
                "18-person Altrincham 11-Aug-2001 preseason sheet; set club label and Moss Lane ground; write "
                "Bernard Taylor to manager807; clear only stale portraits for these18 and clear only exact "
                "3310/10958/slot8 flag1. Preserve real Kidderminster370, all other records/owners/assets, and "
                "opaque mode1 division/ground-capacity-opening/tactics fields."),
            "publication_approved": False}
        plan["transaction_id"] = _sha(package_v2.canonical_json_bytes(plan))[:24]
        cached = {"plan": plan, "result": result, "parent": parent,
            "native_before": {name: native[name] for name in REQUIRED_NATIVE},
            "package_before": json.loads(base.package_path.read_text())}
        _CACHE[key] = cached
    if cached["parent"] != parent:
        raise ValueError("source adapter cache parent mismatch")
    if expected_plan is not None and expected_plan != cached["plan"]:
        raise ValueError("Altrincham source/native prepare plan does not reproduce exactly")
    for row in cached["plan"]["source_bindings"]:
        if _file_sha(registry.ROOT / row["path"]) != row["sha256"]:
            raise ValueError(f"bound source changed after prepare: {row['path']}")
    for row in cached["plan"]["implementation_bindings"]:
        if _file_sha(registry.ROOT / row["path"]) != row["sha256"]:
            raise ValueError(f"bound implementation changed after prepare: {row['path']}")
    current, _ = _parent(base)
    if current != parent:
        raise ValueError("exact whole-parent source binding changed")
    if _sha(package_v2.canonical_json_bytes(cached["result"]["package"])) != cached["plan"]["package_postimage_sha256"]:
        raise ValueError("cached recipe postimage no longer matches the outer plan")
    return cached


def prepare(base) -> dict:
    """Compile an immutable, source-bound plan in memory; no game files are written."""
    preferred = registry.load_preferred_release(SEASON)
    if base.release_id != preferred.release_id:
        raise ValueError("new Altrincham prepare must use the current preferred 2001-02 parent; rebase after child releases")
    return copy.deepcopy(_compile(base)["plan"])


def verify(base, plan: dict) -> None:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE or plan.get("season") != SEASON:
        raise ValueError("Altrincham source exchange requires its exact unique schema/mode/season")
    if plan.get("publication_approved") is not False:
        raise ValueError("prepare-only source plan cannot self-authorize publication")
    _compile(base, expected_plan=plan)


def bind(package: dict, plan: dict) -> dict:
    base = registry.load_registered_release(SEASON, plan.get("parent", {}).get("release_id", ""))
    verify(base, plan)
    cache = _compile(base, expected_plan=plan)
    if package not in (cache["package_before"], cache["result"]["package"]):
        raise ValueError("bind accepts only the exact complete source package or prepared postimage")
    return copy.deepcopy(cache["result"]["package"])


def _apply_single(current: bytes, before: bytes, after: bytes, label: str) -> bytes:
    if current not in (before, after):
        raise ValueError(f"{label} apply accepts only the exact source or exact prepared postimage")
    return after


def apply(jug: bytes, eq: bytes, plan: dict) -> tuple[bytes, bytes]:
    base = registry.load_registered_release(SEASON, plan.get("parent", {}).get("release_id", ""))
    verify(base, plan)
    cache = _compile(base, expected_plan=plan)
    posts = cache["result"]["native_files"]
    before_jug, before_eq = cache["native_before"]["JUG98030.FDI"], cache["native_before"]["EQ98030.FDI"]
    if (jug, eq) not in ((before_jug, before_eq), (posts["JUG98030.FDI"], posts["EQ98030.FDI"])):
        raise ValueError("JUG/EQ require the exact complete paired preimage or paired postimage")
    return posts["JUG98030.FDI"], posts["EQ98030.FDI"]


def apply_ent(ent: bytes, plan: dict) -> bytes:
    base = registry.load_registered_release(SEASON, plan.get("parent", {}).get("release_id", ""))
    verify(base, plan)
    cache = _compile(base, expected_plan=plan)
    return _apply_single(ent, cache["native_before"]["ENT98030.FDI"],
        cache["result"]["native_files"]["ENT98030.FDI"], "ENT")


def apply_minifoto(archive: bytes, plan: dict) -> bytes:
    base = registry.load_registered_release(SEASON, plan.get("parent", {}).get("release_id", ""))
    verify(base, plan)
    cache = _compile(base, expected_plan=plan)
    return _apply_single(archive, cache["native_before"]["MINIFOTO.PKF"],
        cache["result"]["native_files"]["MINIFOTO.PKF"], "MINIFOTO")


def selected_carriers(plan: dict) -> set[int]:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE:
        raise ValueError("Altrincham portrait routing requires the exact schema/mode")
    return set(plan["selected_photo_carriers"])


def photo_offsets(plan: dict) -> dict[int, list[int]]:
    base = registry.load_registered_release(SEASON, plan.get("parent", {}).get("release_id", ""))
    verify(base, plan)
    cache = _compile(base, expected_plan=plan)
    expected = {str(k): list(v) for k, v in cache["result"]["photo_offsets"].items()}
    if plan.get("selected_photo_offsets") != expected:
        raise ValueError("prepared selected portrait offsets differ from the exact parent/source")
    return {int(k): list(v) for k, v in expected.items()}


def filename(plan: dict) -> str:
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE:
        raise ValueError("Altrincham filename requires the exact schema/mode")
    return FILENAME


def source_artifact(plan: dict) -> dict[str, Any]:
    base = registry.load_registered_release(SEASON, plan.get("parent", {}).get("release_id", ""))
    verify(base, plan)
    document = copy.deepcopy(plan["inner_source_plan"])
    raw = package_v2.canonical_json_bytes(document)
    if (_sha(raw) != plan.get("inner_source_plan_sha256")
            or plan.get("inner_source_plan_filename") != SOURCE_PLAN_FILENAME):
        raise ValueError("Altrincham source artifact path or newline hash differs")
    return {"filename": SOURCE_PLAN_FILENAME, "document": document, "sha256": _sha(raw), "bytes": raw}


def reject_factory_recipe(package: dict) -> None:
    if any(a.get("relative_path") == SOURCE_PLAN_FILENAME for a in package.get("artifacts", [])):
        raise ValueError("Altrincham whole-club recipe requires source-bound reconstruction")


def reconstruction(previous, release_id: str):
    """SOURCE replay hook; invokes the existing publisher only after full proof checks."""
    from scripts import season_pipeline_v2 as pipeline
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if receipt.get("compilation_mode") != MODE:
        return None
    relative = previous.locator.get("sourced_profile_assignment_plan_path")
    if not relative:
        raise ValueError("Altrincham SOURCE lacks its exact source exchange plan path")
    plan_path = (registry.ROOT / relative).resolve()
    plan = pipeline.read_json_file(plan_path)
    parent = registry.load_registered_release(SEASON, plan.get("parent", {}).get("release_id", ""))
    verify(parent, plan)
    if (plan_path != (previous.package_path.parent / filename(plan)).resolve()
            or _file_sha(plan_path) != receipt.get("original_profile_assignment_plan_sha256")):
        raise ValueError("Altrincham SOURCE outer plan path/hash differs")
    inner = source_artifact(plan)
    artifact_path = previous.package_path.parent / inner["filename"]
    if _file_sha(artifact_path) != inner["sha256"]:
        raise ValueError("Altrincham retained inner source artifact differs")
    expected_package = bind(pipeline.read_json_file(parent.package_path), plan)
    previous_package_bytes = previous.package_path.read_bytes()
    if (pipeline.read_json_file(previous.package_path) != expected_package
            or previous_package_bytes != package_v2.canonical_json_bytes(expected_package)):
        raise ValueError("Altrincham SOURCE package differs from exact canonical source-bound postimage")
    previous_inventory = pipeline.read_json_file(previous.inventory_path)
    pipeline.assert_tree_matches_inventory(previous.game_path, previous_inventory)
    descriptor = previous.package_path.parent / "role-delta-input.json"
    expected_descriptor = {"season": SEASON, "release_id": parent.release_id,
        "package_sha256": plan["parent"]["package_sha256"],
        "jug_sha256": plan["parent"]["native_sha256"]["JUG98030.FDI"], "updates": [], "unresolved": []}
    if pipeline.read_json_file(descriptor) != expected_descriptor:
        raise ValueError("Altrincham SOURCE role descriptor is not the exact inert source input")
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(SEASON, descriptor, release_id=release_id, source_release_id=parent.release_id,
        profile_assignment_plan_path=plan_path)
    rebuilt = registry.load_registered_release(SEASON, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, previous_inventory)
    if (pipeline.read_json_file(rebuilt.package_path) != expected_package
            or rebuilt.package_path.read_bytes() != previous_package_bytes):
        raise ValueError("Altrincham complete SOURCE replay recipe bytes differ")
    return {"season": SEASON, "release_id": release_id, "complete_game_inventory_identical": True,
        "complete_recipe_identical": True, "compilation_mode": MODE}
