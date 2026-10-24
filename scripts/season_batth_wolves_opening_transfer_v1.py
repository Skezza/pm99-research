"""Source-bound adapter for the r213a Batth opening-owner correction.

This module uses only existing
compiler writers and parser APIs, and writes no native files.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, read_initial_order, patch_initial_orders
from app.xor import xor_encode
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA = "pm99-source-bound-batth-wolves-opening-transfer-v1"
INPUT_SCHEMA = "pm99-batth-wolves-opening-transfer-input-v1"
MODE = "known-good-baseline-source-bound-batth-wolves-opening-transfer-v1"
FILENAME = "source-batth-wolves-opening-transfer-v1.json"
ARTIFACT_ID = "source-batth-wolves-opening-transfer-2018-19-v1"
BASE_RELEASE = "sourced-vokes-crouch-opening-owners-20261024-r213a"
SOURCE_BINDINGS = {
    ".local/transfermarkt-opening-plans-current-v1/2018-19/opening-lineups.json":
        ("33b01d4e0b5142a6f9577711501e0e10b7443ac1c266f02009f55ca12466a05f",
         "captured Transfermarkt opening lineup index"),
    ".local/transfermarkt-opening-plans-current-v1/2018-19/cache/report/3053576.html":
        ("e676c0e5331e1ffa20f7840e27af99504a99d6969ae8c2472bbd30c4f037e20c",
         "https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/3053576"),
    ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/"
    "batth-wolves-opening-transfer-r213-v1/source-captures/wolves-august-loan.html":
        ("d6ce3794516d1c3a1b4c52b4f6f17cb5abb4ebb1d22f680b3fecb8ad00168215",
         "https://www.wolves.co.uk/news/mens-first-team/20180831-batth-joins-middlesbrough-on-loan/"),
    ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/"
    "batth-wolves-opening-transfer-r213-v1/source-captures/wolves-january-transfer.html":
        ("e8497837f5eaa50deac6edd613f81c9d1331bcbe5b9d8d86ae145255f4a9506b",
         "https://www.wolves.co.uk/news/mens-first-team/20190128-batth-departs-in-permanent-move/"),
}
SCOPE = (
    "Transfer existing Batth carrier 10749 from Stoke EQ351 to Wolves EQ333, "
    "substitute Fletcher carrier 10762 in Stoke's sourced opening bench slot, "
    "and compact only the required native startup-order bytes. No new identity, "
    "ratings, facts, first-XI, image, or other roster ownership changes."
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def filename(plan: Mapping[str, Any]) -> str:
    return FILENAME


def artifact_id(plan: Mapping[str, Any]) -> str:
    return ARTIFACT_ID


def _parent_files(base):
    return {
        "package_sha256": registry.sha256_file(base.package_path),
        "eq_sha256": registry.sha256_file(base.game_path / "DBDAT/EQ98030.FDI"),
        "jug_sha256": registry.sha256_file(base.game_path / "DBDAT/JUG98030.FDI"),
        "ent_sha256": registry.sha256_file(base.game_path / "DBDAT/ENT98030.FDI"),
    }


def _bound_path(row: Mapping[str, Any]) -> Path:
    raw = Path(str(row.get("path") or ""))
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("source evidence path must be project-relative and confined")
    path = (registry.ROOT / raw).resolve()
    if registry.ROOT.resolve() not in path.parents:
        raise ValueError("source evidence path escapes project root")
    if not path.is_file() or path.is_symlink() or registry.sha256_file(path) != row.get("sha256"):
        raise ValueError("bound source evidence is missing or changed")
    return path


def _validate_sources(request: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(request.get("source_inputs") or [])
    actual_bindings = {str(x.get("path")): (str(x.get("sha256")), str(x.get("url"))) for x in rows}
    if actual_bindings != SOURCE_BINDINGS:
        raise ValueError("source input paths and immutable raw-body hashes differ")
    if len(rows) != len(SOURCE_BINDINGS):
        raise ValueError("source input binding contains duplicate or missing rows")
    bound = {Path(str(x["path"])).name: _bound_path(x).read_bytes() for x in rows}
    lineups = json.loads(bound["opening-lineups.json"])
    rows = [x for x in lineups.get("clubs", [])
            if str(x.get("source_match_id")) == "3053576"
            and x.get("source_selector", {}).get("club_name") == "Stoke City"]
    if len(rows) != 1:
        raise ValueError("retained Stoke opener source row is missing or ambiguous")
    fixture = rows[0]
    if (fixture.get("first_league_fixture_date") != "2018-08-05"
            or fixture.get("source_status") != "source-qualified"
            or fixture.get("source_selector", {}).get("transfermarkt_club_id") != 512):
        raise ValueError("retained Stoke opener source binding differs")
    source_players = [x for x in fixture.get("substitutes", [])
                      if str(x.get("source_player_id")) == "3547"]
    if len(source_players) != 1 or source_players[0].get("display_name") != "Darren Fletcher":
        raise ValueError("Fletcher is not the unique published Stoke substitute")
    report = bound["3053576.html"]
    if b'href="/darren-fletcher/profil/spieler/3547">Darren Fletcher</a>' not in report:
        raise ValueError("raw Stoke match report does not bind Fletcher name and source ID")
    august = bound["wolves-august-loan.html"].decode("utf-8", "replace")
    january = bound["wolves-january-transfer.html"].decode("utf-8", "replace")
    for token in ("31st August 2018", "Danny Batth", "season-long loan", "Middlesbrough"):
        if token.casefold() not in august.casefold():
            raise ValueError("official Wolves August loan source lacks required ownership text")
    for token in ("29th January 2019", "Danny Batth", "moved to Stoke City", "18-year association"):
        if token.casefold() not in january.casefold():
            raise ValueError("official Wolves January transfer source lacks required ownership text")
    return {"fixture": fixture, "fletcher": source_players[0]}


def _native_facts(jug: bytes, carrier: int) -> dict[str, Any]:
    index = IndexedFDIFile.from_bytes(jug)
    entries = [e for e in index.entries if e.record_id == carrier]
    if len(entries) != 1:
        raise ValueError("native actor carrier is missing or ambiguous")
    payload = entries[0].decode_payload(jug)
    order = read_initial_order(payload)
    from app.models import PlayerRecord
    record = PlayerRecord.from_bytes(payload, 0)
    facts = {
        "name": order.name,
        "birth_date": f"{record.birth_year:04d}-{record.birth_month:02d}-{record.birth_day:02d}",
        "shirt_number": int(payload[7] ^ 0x61) if payload[2:5] == b"\xdd\x63\x61" else None,
        "startup_order": order.order,
        "family": order.family,
    }
    return facts


def _roster_preimages(eq: bytes) -> tuple[dict[int, list[tuple[int, int]]], dict[int, set[int]], dict[int, int]]:
    index = IndexedFDIFile.from_bytes(eq)
    rows_by_club: dict[int, list[tuple[int, int]]] = {}
    owners: dict[int, set[int]] = {}
    modes: dict[int, int] = {}
    for entry in index.entries:
        payload = eq[entry.payload_offset:entry.payload_offset + entry.payload_length]
        roster = parse_eq_external_team_roster_payload(payload, {})
        if roster is None:
            continue
        modes[entry.record_id] = roster.mode_byte
        rows_by_club[entry.record_id] = [(r.player_record_id, r.flag) for r in roster.rows]
        for row in roster.rows:
            owners.setdefault(row.player_record_id, set()).add(entry.record_id)
    return rows_by_club, owners, modes


def _assert_package_native_preimage(base, package, eq: bytes, jug: bytes) -> tuple[dict, dict]:
    clubs = {int(c["carrier_id"]): c for c in package["clubs"]}
    people = {int(p["carrier_id"]): p for p in package["players"]}
    rows_by_club, owners, modes = _roster_preimages(eq)
    for cid in (333, 351):
        roster = rows_by_club.get(cid)
        expected = [int(people_id.split("-")[-1]) for people_id in clubs[cid]["roster_player_ids"]]
        if (roster is None or modes[cid] != 0 or len(roster) != 25
                or [r[0] for r in roster] != expected or any(flag for _, flag in roster)):
            raise ValueError(f"r213a native/package roster preimage differs for EQ{cid}")
    if owners.get(10749) != {351} or owners.get(10762) != {351}:
        raise ValueError("Batth or Fletcher does not have the expected unique Stoke owner")
    batth_native = _native_facts(jug, 10749)
    if (batth_native["name"] != "Danny BATTH"
            or batth_native["birth_date"] != "1990-09-21"):
        raise ValueError("native Batth identity preimage differs")
    fletcher_native = _native_facts(jug, 10762)
    if (fletcher_native["name"] != "Darren FLETCHER"
            or fletcher_native["birth_date"] != "1984-02-01"
            or fletcher_native["shirt_number"] != 24):
        raise ValueError("native Fletcher name/DOB/shirt preimage differs")
    return {"clubs": clubs, "people": people}, {"rows": rows_by_club, "owners": owners, "modes": modes}


def _make_bound_package(package: Mapping[str, Any], plan: Mapping[str, Any]) -> dict:
    result = copy.deepcopy(dict(package))
    clubs = {int(c["carrier_id"]): c for c in result["clubs"]}
    people = {int(p["carrier_id"]): p for p in result["players"]}
    batth = people[10749]
    if (batth.get("club_id") != "english-club-351"
            or clubs[351]["roster_player_ids"].count(batth["id"]) != 1
            or batth["id"] in clubs[333]["roster_player_ids"]):
        raise ValueError("recipe Batth ownership preimage differs")
    if batth.get("facts") != plan["batth_before"]["facts"] or batth.get("ratings") != plan["batth_before"]["ratings"]:
        raise ValueError("Batth facts/ratings preimage differs")
    if clubs[351]["opening"]["starting_xi_player_ids"] != plan["stoke_xi_before"]:
        raise ValueError("Stoke starting XI recipe preimage differs")
    if clubs[333]["opening"]["starting_xi_player_ids"] != plan["wolves_xi_before"]:
        raise ValueError("Wolves starting XI recipe preimage differs")
    if batth["id"] not in clubs[351]["opening"]["substitute_player_ids"]:
        raise ValueError("Batth is not in the expected Stoke substitute slot")
    if clubs[351]["roster_player_ids"].count("english-player-10762") != 1:
        raise ValueError("Fletcher recipe actor is absent/repeated at Stoke")
    fletcher = people[10762]
    if fletcher != plan["fletcher_before"]["complete_actor"]:
        raise ValueError("Fletcher complete recipe preimage differs")
    clubs[351]["roster_player_ids"].remove(batth["id"])
    clubs[333]["roster_player_ids"].append(batth["id"])
    batth["club_id"] = "english-club-333"
    clubs[351]["opening"]["substitute_player_ids"] = [
        "english-player-10762" if x == "english-player-10749" else x
        for x in clubs[351]["opening"]["substitute_player_ids"]
    ]
    if len(clubs[351]["roster_player_ids"]) != 24 or len(clubs[333]["roster_player_ids"]) != 26:
        raise ValueError("typed transfer would produce unexpected roster counts")
    if clubs[333]["roster_player_ids"][:25] != plan["wolves_roster_before_ids"]:
        raise ValueError("original Wolves 25 are not preserved in order")
    if (clubs[351]["opening"]["starting_xi_player_ids"] != plan["stoke_xi_before"]
            or clubs[333]["opening"]["starting_xi_player_ids"] != plan["wolves_xi_before"]):
        raise ValueError("typed transfer changed a first XI")
    aid = ARTIFACT_ID
    if any(a.get("id") == aid for a in result.get("artifacts", [])):
        raise ValueError("Batth transfer artifact already exists in the parent recipe")
    result["artifacts"].append({"id": aid, "kind": "season-input", "relative_path": FILENAME,
                                 "sha256": digest(packages.canonical_json_bytes(dict(plan))),
                                 "media_type": "application/json"})
    clubs[351]["opening"]["proof"] = {"artifact_id": aid, "grade": "source-receipt"}
    clubs[333]["opening"]["proof"] = {"artifact_id": aid, "grade": "source-receipt"}
    result["artifacts"].sort(key=lambda x: x["id"])
    packages.validate_package(result)
    return result


def prepare(base, input_path):
    request = pipeline.read_json_file(Path(input_path))
    if (request.get("schema") != INPUT_SCHEMA or request.get("season") != base.season
            or request.get("release_id") != base.release_id or base.release_id != BASE_RELEASE):
        raise ValueError("typed Batth adapter requires its exact registered r213a parent")
    expected_parent = {"manifest_sha256": base.manifest_sha256, **_parent_files(base)}
    if request.get("parent") != expected_parent:
        raise ValueError("whole registered r213a package/native preimage hashes differ")
    source = _validate_sources(request)
    package = pipeline.read_json_file(base.package_path)
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    info, native = _assert_package_native_preimage(base, package, eq, jug)
    stoke, wolves, batth, fletcher = (info["clubs"][351], info["clubs"][333],
                                     info["people"][10749], info["people"][10762])
    if (request.get("fixture", {}).get("source_player_id") != "3547"
            or request.get("ownership", {}).get("player_carrier_id") != 10749
            or request.get("fletcher", {}).get("player_carrier_id") != 10762):
        raise ValueError("typed request actor IDs differ")
    if (fletcher["name"] != "Darren Fletcher" or fletcher["facts"]["birth_date"] != "1984-02-01"
            or batth["name"] != "Danny Batth" or batth["facts"]["birth_date"] != "1990-09-21"):
        raise ValueError("recipe actor identities differ from native/source bindings")
    candidate = copy.deepcopy(package)
    clubs = {int(c["carrier_id"]): c for c in candidate["clubs"]}
    people = {int(p["carrier_id"]): p for p in candidate["players"]}
    clubs[351]["roster_player_ids"].remove(people[10749]["id"])
    clubs[333]["roster_player_ids"].append(people[10749]["id"])
    people[10749]["club_id"] = clubs[333]["id"]
    clubs[351]["opening"]["substitute_player_ids"] = [
        people[10762]["id"] if x == people[10749]["id"] else x
        for x in clubs[351]["opening"]["substitute_player_ids"]]
    desired_orders = compiler._club_player_orders(candidate)
    index = IndexedFDIFile.from_bytes(jug)
    entries = {e.record_id: e for e in index.entries}
    order_changes = []
    for club in (clubs[351], clubs[333]):
        for player_id in club["roster_player_ids"]:
            actor = next(p for p in candidate["players"] if p["id"] == player_id)
            native_order = read_initial_order(entries[int(actor["carrier_id"])].decode_payload(jug))
            target = int(desired_orders[player_id])
            if native_order.order != target:
                order_changes.append({"carrier_id": int(actor["carrier_id"]), "name": native_order.name,
                                      "before": native_order.order, "after": target,
                                      "club_id": int(club["carrier_id"])})
    if len(order_changes) != 7:
        raise ValueError("opening transfer does not resolve to the exact seven-order-byte plan")
    request_path = Path(input_path).resolve()
    if registry.ROOT.resolve() not in request_path.parents or request_path.is_symlink():
        raise ValueError("typed request path must be retained inside project root")
    plan = {
        "schema": SCHEMA, "mode": MODE, "season": base.season, "release_id": base.release_id,
        "request_input": {"path": str(request_path.relative_to(registry.ROOT.resolve())),
                          "sha256": registry.sha256_file(request_path)},
        "parent": expected_parent,
        "source_inputs": request["source_inputs"],
        "fixture_source": {"match_id": "3053576", "fixture_date": "2018-08-05",
                           "lineup_url": source["fixture"]["lineup_source_url"],
                           "fletcher_source_id": "3547", "fletcher_source_name": "Darren Fletcher"},
        "ownership_source": request["ownership"],
        "package_canonical_sha256": digest(packages.canonical_json_bytes(package)),
        "batth_before": {"id": batth["id"], "carrier_id": 10749, "club_id": batth["club_id"],
                         "facts": copy.deepcopy(batth["facts"]), "ratings": copy.deepcopy(batth["ratings"])},
        "fletcher_before": {"id": fletcher["id"], "carrier_id": 10762, "name": fletcher["name"],
                            "facts": copy.deepcopy(fletcher["facts"]),
                            "complete_actor": copy.deepcopy(fletcher)},
        "stoke_roster_before": [list(row) for row in native["rows"][351]],
        "wolves_roster_before": [list(row) for row in native["rows"][333]],
        "stoke_roster_before_ids": list(stoke["roster_player_ids"]),
        "wolves_roster_before_ids": list(wolves["roster_player_ids"]),
        "stoke_xi_before": copy.deepcopy(stoke["opening"]["starting_xi_player_ids"]),
        "wolves_xi_before": copy.deepcopy(wolves["opening"]["starting_xi_player_ids"]),
        "order_changes": order_changes,
        "proof_covers": ["dated-batth-wolves-opening-ownership", "dated-stoke-fletcher-opening-substitute",
                         "two-mode0-roster-transfer-and-native-order-replay"],
        "scope": SCOPE,
    }
    plan["transaction_id"] = digest(packages.canonical_json_bytes(plan))[:24]
    return plan


def verify(base, plan):
    if plan.get("schema") != SCHEMA or plan.get("mode") != MODE:
        raise ValueError("unsupported Batth opening-transfer schema/mode")
    rel = Path(plan["request_input"]["path"])
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("unsafe Batth transaction request binding")
    path = registry.ROOT / rel
    if registry.sha256_file(path) != plan["request_input"]["sha256"]:
        raise ValueError("Batth transaction input changed")
    if prepare(base, path) != plan:
        raise ValueError("source-bound Batth transaction does not reproduce")


def bind(package, plan):
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    verify(base, plan)
    if digest(packages.canonical_json_bytes(package)) != plan["package_canonical_sha256"]:
        raise ValueError("whole package preimage differs from registered r213a")
    return _make_bound_package(package, plan)


def _candidate_native(base, plan):
    verify(base, plan)
    source_package = pipeline.read_json_file(base.package_path)
    package = bind(source_package, plan)
    original_eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    original_jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    original_ent = (base.game_path / "DBDAT/ENT98030.FDI").read_bytes()
    ent_ids = {e.record_id for e in IndexedFDIFile.from_bytes(original_ent).entries}
    all_replacements, _, _ = compiler._team_replacements(
        package=package, eq_data=original_eq, ent_carriers=ent_ids)
    eq_candidate = compiler._rebuild_indexed(
        original_eq, IndexedFDIFile.from_bytes(original_eq),
        {carrier: all_replacements[carrier] for carrier in (333, 351)})
    preserve_other_records(original_eq, eq_candidate, {333, 351})
    orders = [OrderReplacement(record_id=row["carrier_id"], expected_name=row["name"],
                               before=row["before"], after=row["after"])
              for row in plan["order_changes"]]
    jug_candidate = patch_initial_orders(original_jug, orders, allow_compact=True)
    before = {e.record_id: e for e in IndexedFDIFile.from_bytes(original_jug).entries}
    after = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug_candidate).entries}
    changed_payload_ids = []
    for carrier in before:
        if before[carrier].decode_payload(original_jug) != after[carrier].decode_payload(jug_candidate):
            changed_payload_ids.append(carrier)
    if set(changed_payload_ids) != {row["carrier_id"] for row in plan["order_changes"]}:
        raise ValueError("JUG order rewrite changed an unexpected actor payload")
    allowed_offsets = set()
    for row in plan["order_changes"]:
        entry = before[row["carrier_id"]]
        field = read_initial_order(entry.decode_payload(original_jug))
        allowed_offsets.add(entry.payload_offset + field.offset)
    actual_offsets = {i for i, (old, new) in enumerate(zip(original_jug, jug_candidate)) if old != new}
    if actual_offsets != allowed_offsets:
        raise ValueError("JUG candidate changed bytes outside the seven selected order fields")
    _verify_postimage(package, jug_candidate, eq_candidate)
    return jug_candidate, eq_candidate


def _verify_postimage(package, jug, eq):
    clubs = {int(c["carrier_id"]): c for c in package["clubs"]}
    people = {int(p["carrier_id"]): p for p in package["players"]}
    rows_by_club, owners, modes = _roster_preimages(eq)
    expected_stoke = [int(x.split("-")[-1]) for x in clubs[351]["roster_player_ids"]]
    expected_wolves = [int(x.split("-")[-1]) for x in clubs[333]["roster_player_ids"]]
    for cid, expected in ((351, expected_stoke), (333, expected_wolves)):
        actual = rows_by_club[cid]
        if (modes[cid] != 0 or len(actual) != len(expected)
                or [r[0] for r in actual] != expected or any(flag for _, flag in actual)):
            raise ValueError(f"native postimage roster mismatch at EQ{cid}")
    if owners.get(10749) != {333} or owners.get(10762) != {351}:
        raise ValueError("native postimage ownership is not exclusive")
    ix = IndexedFDIFile.from_bytes(jug); es = {e.record_id: e for e in ix.entries}
    for carrier, expected in ((10749, 26), (10762, 15)):
        if read_initial_order(es[carrier].decode_payload(jug)).order != expected:
            raise ValueError("native postimage startup order differs")
    if len(clubs[351]["roster_player_ids"]) != 24 or len(clubs[333]["roster_player_ids"]) != 26:
        raise ValueError("recipe postimage counts differ")
    if clubs[333]["roster_player_ids"][:25] != [f"english-player-{rid}" for rid, _ in rows_by_club[333][:25]]:
        raise ValueError("original Wolves 25 are not preserved before appended Batth")


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    verify(base, plan)
    original_jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    original_eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    is_before = jug == original_jug and eq == original_eq
    if is_before:
        return _candidate_native(base, plan)
    if (jug == original_jug) != (eq == original_eq):
        raise ValueError("apply accepts only the complete registered preimage or complete candidate postimage")
    expected_jug, expected_eq = _candidate_native(base, plan)
    is_after = jug == expected_jug and eq == expected_eq
    if not is_after:
        raise ValueError("apply accepts only the complete registered preimage or complete candidate postimage")
    return (expected_jug, expected_eq) if is_before else (jug, eq)


def reject_factory_recipe(package):
    if any(a.get("id") == ARTIFACT_ID for a in package.get("artifacts", [])):
        raise ValueError("Batth opening ownership requires its source-bound transaction replay")


def reconstruction(previous, release_id):
    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    relative = previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative:
        raise ValueError('Batth SOURCE lacks its assignment plan')
    path = (registry.ROOT / relative).resolve()
    plan = pipeline.read_json_file(path)
    base = registry.load_registered_release(plan['season'], BASE_RELEASE)
    verify(base, plan)
    if (path != (previous.package_path.parent / filename(plan)).resolve()
            or registry.sha256_file(path) != receipt.get('original_profile_assignment_plan_sha256')):
        raise ValueError('Batth SOURCE assignment path/hash differs')
    expected = bind(pipeline.read_json_file(base.package_path), plan)
    if pipeline.read_json_file(previous.package_path) != expected:
        raise ValueError('Batth SOURCE recipe differs from source-bound postimage')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    expected_descriptor = dict(season=base.season, release_id=BASE_RELEASE,
        package_sha256=plan['parent']['package_sha256'],
        jug_sha256=plan['parent']['jug_sha256'], updates=[], unresolved=[])
    if pipeline.read_json_file(descriptor) != expected_descriptor:
        raise ValueError('Batth SOURCE descriptor is not the exact inert parent input')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(base.season, descriptor, release_id=release_id,
        source_release_id=BASE_RELEASE, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(base.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,
        pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != expected:
        raise ValueError('Batth whole SOURCE recipe replay differs')
    return dict(season=base.season, release_id=release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True,
        compilation_mode=MODE)
