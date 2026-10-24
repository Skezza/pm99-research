"""Private source-bound Coady cascade adapter for the 2017/18 and 2019/20 parents.

This prepare-only candidate reuses the exact indexed role/position writer. It
does not write native inputs, publish, build, or run the game. The FIFA 19 row
is used as an identity/role cross-check only; the dated Wolves history supplies
the period-specific defender claim and is not described as a FIFA 18/20 row.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from scripts import season_exact_primary_position_delta_v2 as native_writer
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_order_repair_v1 as owners
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

ROOT = registry.ROOT
QA = ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/coady-centerback-correction-v1"
CAPTURE_RECEIPT = QA / "capture_receipt.json"
SCHEMA = "pm99-source-bound-wolves-coady-defence-cascade-v1"
MODE = "known-good-baseline-source-bound-wolves-coady-defence-cascade-v1"
PREFIX = "source-bound-wolves-coady-defence-cascade-v1-"
IDENTITY = {"name": "Conor Coady", "birth_date": "1993-02-25", "family_hex": "dd6361"}
SOURCES = {
    "wolves_2019": {
        "path": QA / "source-captures/wolves-20190215-coady-defence.html",
        "sha256": "f45a950b3d787eaa2dbd62ed578cbe201395a0ae8b9f204f39c85db9d1f01f31",
        "url": "https://www.wolves.co.uk/news/mens-first-team/20190215-coady-and-doherty-commit-futures-to-wolves/",
    },
    "wolves_2022": {
        "path": QA / "source-captures/wolves-20220207-coady-three-defence.html",
        "sha256": "f8e6c5f6ddaec87701b35bb45c2227f976435df09338b67470d1be7882eb95f5",
        "url": "https://www.wolves.co.uk/news/features/20220207-300-club-conor-coady/",
    },
    "fifa19_identity_crosscheck": {
        "path": ROOT / ".local/season-2015-16/fifa19-sofifa-backfill.csv",
        "sha256": "cd037495104afe0649e8d99d8b884d2589b0e621dc6a9932a65398621d094350",
        "url": None,
    },
}
PARENTS = {
    "2017-18": {"release_id": "sourced-owned-opening-period-kit-20261017-r147a", "carrier_id": 21281, "club_carrier_id": 365},
    "2019-20": {"release_id": "sourced-remaining-manager-tenures-20261016-r116a", "carrier_id": 9900, "club_carrier_id": 333},
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    return _sha(Path(path).read_bytes())


def _canon(value) -> bytes:
    return packages.canonical_json_bytes(value)


def _digest(value) -> str:
    return _sha(_canon(value))


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def _html(path: Path) -> str:
    parser = _Text()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return " ".join(parser.parts).casefold()


def _source_evidence(season: str) -> dict:
    if season not in PARENTS:
        raise ValueError("Coady cascade candidate supports only the pinned 2017/18 and 2019/20 seasons")
    for key, row in SOURCES.items():
        if _file_sha(row["path"]) != row["sha256"]:
            raise ValueError(f"Coady source body changed: {key}")
    receipt = json.loads(CAPTURE_RECEIPT.read_text(encoding="utf-8"))
    if receipt.get("schema") != "pm99-coady-source-capture-receipt-v1":
        raise ValueError("Coady capture receipt schema differs")
    captured = {row.get("path"): row for row in receipt.get("sources", [])}
    for key in ("wolves_2019", "wolves_2022"):
        rel = "source-captures/" + SOURCES[key]["path"].name
        row = captured.get(rel)
        if not row or row.get("url") != SOURCES[key]["url"] or row.get("http_status") != 200 or row.get("sha256") != SOURCES[key]["sha256"]:
            raise ValueError(f"Coady official source receipt is missing or misbound: {key}")
    if _file_sha(CAPTURE_RECEIPT) != "1fcf386780354ddbfe4e922e026e228e85ce086923e80cf7ae1105212eaa378b":
        raise ValueError("Coady capture receipt bytes changed")

    body19 = _html(SOURCES["wolves_2019"]["path"])
    if not all(token in body19 for token in (
        "after performing in midfield during his opening two campaigns",
        "transformed into the linchpin of the defence since nuno espirito santo",
        "part of the back three",
    )):
        raise ValueError("official Wolves period-specific 2019 defensive history is missing")
    body22 = _html(SOURCES["wolves_2022"]["path"])
    if not all(token in body22 for token in (
        "moved to the centre of a three-man defence for wolves from the 2017/18 season onwards",
        "conor david coady",
        "25 th february 1993",
    )):
        raise ValueError("official Wolves 2017/18-onwards history or identity is missing")

    with SOURCES["fifa19_identity_crosscheck"]["path"].open(newline="", encoding="utf-8-sig") as stream:
        matches = [row for row in csv.DictReader(stream) if row.get("sofifa_id") == "202048"]
    if len(matches) != 1:
        raise ValueError("unique FIFA19 Coady identity row is missing or ambiguous")
    fifa = matches[0]
    if (fifa.get("long_name") != "Conor  Coady" or fifa.get("dob") != IDENTITY["birth_date"]
            or fifa.get("player_positions") != "CB" or fifa.get("team_position") != "CB"):
        raise ValueError("FIFA19 identity cross-check differs")

    annual = None
    if season == "2019-20":
        annual_path = ROOT / ".local/external-sources/cache.footballsquads/eng/2019-2020/engprem/wolves.txt"
        if _file_sha(annual_path) != "5ccbadbf860209c53764bb4b1a268f605246ecc8278b752fa586092b948a9bb6":
            raise ValueError("2019/20 FootballSquads annual bytes changed")
        rows = [(i, line) for i, line in enumerate(annual_path.read_text(encoding="utf-8").splitlines(), 1) if "Conor Coady" in line]
        if rows != [(12, "16, Conor Coady, ENG, M, 1.85, 75, 25-02-93, Liverpool, Huddersfield T")]:
            raise ValueError("2019/20 annual M conflict row changed")
        annual = {"path": str(annual_path.relative_to(ROOT)), "sha256": _file_sha(annual_path), "line": 12,
                  "position": "M", "disposition": "retained conflicting annual broad-position row; dated official Wolves history resolves this later period as defence"}
    return {
        "capture_receipt": {"path": str(CAPTURE_RECEIPT.relative_to(ROOT)), "sha256": _file_sha(CAPTURE_RECEIPT)},
        "official_history": {key: {"path": str(row["path"].relative_to(ROOT)), "sha256": row["sha256"], "url": row["url"]}
                             for key, row in SOURCES.items() if key.startswith("wolves_")},
        "identity_crosscheck": {"path": str(SOURCES["fifa19_identity_crosscheck"]["path"].relative_to(ROOT)),
                                "sha256": SOURCES["fifa19_identity_crosscheck"]["sha256"], "sofifa_id": "202048",
                                "name": fifa["long_name"], "dob": fifa["dob"], "role": "CB",
                                "role_use": "identity/role corroboration only; not claimed as the FIFA 18 or FIFA 20 edition"},
        "annual_conflict": annual,
        "role_evidence": {
            "2017-18": "Official Wolves retrospective dates the move to centre of a three-man defence from 2017/18 onwards.",
            "2019-20": "Official Wolves account says midfield in his opening two Wolves campaigns, then transformed into defensive linchpin after Nuno and part of the back three; official retrospective dates the switch from 2017/18 onwards.",
        }[season],
        "scope_note": "Native owner and package membership are bound separately. No retained specific-season 2017/18 or 2019/20 opening-match capture is asserted by this adapter.",
    }


def _base_exact(base):
    target = PARENTS.get(getattr(base, "season", None))
    if not target or base.release_id != target["release_id"]:
        raise ValueError("Coady cascade requires one of the two exact current parent releases")
    registered = registry.load_registered_release(base.season, base.release_id)
    if (Path(base.package_path).resolve() != Path(registered.package_path).resolve()
            or Path(base.game_path).resolve() != Path(registered.game_path).resolve()
            or base.manifest_sha256 != registered.manifest_sha256):
        raise ValueError("Coady cascade base is not the exact registered release")
    return target


def prepare(base):
    target = _base_exact(base)
    evidence = _source_evidence(base.season)
    package = pipeline.read_json_file(base.package_path)
    actors = [p for p in package["players"] if p.get("carrier_id") == target["carrier_id"]]
    if len(actors) != 1:
        raise ValueError("Coady actor carrier is missing or ambiguous")
    player = actors[0]
    clubs = {c["id"]: c for c in package["clubs"]}
    club = clubs.get(player.get("club_id"))
    if (player.get("name") != IDENTITY["name"] or player.get("source_name") != IDENTITY["name"]
            or player.get("facts", {}).get("birth_date") != IDENTITY["birth_date"]
            or player.get("facts", {}).get("primary_position") != "M"
            or player.get("facts", {}).get("fine_roles") != [9]
            or not club or club.get("carrier_id") != target["club_carrier_id"]
            or player["id"] not in club.get("roster_player_ids", [])):
        raise ValueError("exact Coady package identity/owner/role preimage differs")
    db = Path(base.game_path) / "DBDAT"
    jug = (db / "JUG98030.FDI").read_bytes()
    eq = (db / "EQ98030.FDI").read_bytes()
    index = IndexedFDIFile.from_bytes(jug)
    entries = {entry.record_id: entry for entry in index.entries}
    if target["carrier_id"] not in entries:
        raise ValueError("Coady native player carrier is absent")
    payload = entries[target["carrier_id"]].decode_payload(jug)
    native = roster.native_player(payload, target["carrier_id"])
    owner_map = owners.native_owners(eq)
    if (payload[2:5] != bytes.fromhex(IDENTITY["family_hex"])
            or owner_map.get(target["carrier_id"]) != {target["club_carrier_id"]}
            or roster.normalise(native["name"]) != "conorcoady"
            or native["position"] != "M" or native["roles"][0] != 9):
        raise ValueError("exact Coady native identity/role/exclusive-owner preimage differs")
    end = native["name_end"]
    native_dob = date(int.from_bytes(bytes(x ^ 0x61 for x in payload[end+14:end+16]), "little"),
                      payload[end+13] ^ 0x61, payload[end+12] ^ 0x61).isoformat()
    if native_dob != IDENTITY["birth_date"]:
        raise ValueError("Coady native DOB differs from the source identity")
    opening = next((c.get("opening") for c in package["clubs"] if c.get("carrier_id") == target["club_carrier_id"]), None)
    if opening:
        opener_member = player["id"] in (opening.get("starting_xi_player_ids", []) + opening.get("substitute_player_ids", []))
        opening_context = {"fixture_date": opening.get("fixture_date"), "player_listed": opener_member,
                           "proof": copy.deepcopy(opening.get("proof")),
                           "claim_limit": "existing recipe context only; this private correction does not assert independently captured match role or change opening membership"}
    else:
        opening_context = None
    writer_path = ROOT / "scripts/season_exact_primary_position_delta_v2.py"
    plan = {
        "schema": SCHEMA, "mode": MODE, "season": base.season, "release_id": base.release_id,
        "parent": {"manifest_sha256": base.manifest_sha256, "package_sha256": _file_sha(base.package_path),
                   "native_files": {"JUG98030.FDI": _sha(jug), "EQ98030.FDI": _sha(eq)}},
        "target": {"carrier_id": target["carrier_id"], "actor_id": player["id"], "club_id": player["club_id"],
                   "club_carrier_id": target["club_carrier_id"], "name": IDENTITY["name"], "birth_date": IDENTITY["birth_date"],
                   "before_player": copy.deepcopy(player), "before_native": copy.deepcopy(native),
                   "before": {"primary_position": "M", "fine_roles": [9]},
                   "after": {"primary_position": "D", "fine_roles": [4]},
                   "fine_role_policy": "generic central-defender-compatible role 4; source supports centre of a three-man defence, not left/right side assignment",
                   "package_opening_context": opening_context},
        "source_bindings": evidence,
        "implementation_binding": {"native_writer": "scripts/season_exact_primary_position_delta_v2.py", "sha256": _file_sha(writer_path)},
        "scope": "Only this target actor's package primary_position M->D, fine_roles [9]->[4], and exact indexed JUG position/first-role bytes. Preserve all other actor rows, skills, identity, facts, ownership, order, tactics, managers, assets, EQ bytes, and other native payloads.",
        "rebase_policy": "Exact parent release IDs and package/JUG/EQ hashes are required. Prepare again after any parent revision; do not transplant this plan to another child.",
        "authorization": {"build": False, "publish": False, "runner": False, "native_files_written": False},
    }
    plan["transaction_id"] = _digest(plan)[:24]
    return copy.deepcopy(plan)


def _check_plan(plan):
    if not isinstance(plan, dict) or plan.get("schema") != SCHEMA or plan.get("mode") != MODE:
        raise ValueError("Coady cascade schema/mode differs")


def verify(base, plan):
    _check_plan(plan)
    if _canon(prepare(base)) != _canon(plan):
        raise ValueError("Coady cascade source, parent, or exact preimage did not reproduce")
    return True


def filename(plan):
    _check_plan(plan)
    return f"coady-centreback-cascade-{plan['season']}-{plan['transaction_id']}.json"


def artifact_id(plan):
    _check_plan(plan)
    return PREFIX + plan["transaction_id"]


def bind(package, plan):
    _check_plan(plan)
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    verify(base, plan)
    if _file_sha(base.package_path) != plan["parent"]["package_sha256"]:
        raise ValueError("Coady cascade exact package parent changed")
    result = copy.deepcopy(package)
    original = pipeline.read_json_file(base.package_path)
    if _canon(result) != _canon(original):
        raise ValueError("Coady bind received a package other than its exact parent")
    player = next(p for p in result["players"] if p.get("carrier_id") == plan["target"]["carrier_id"])
    player["facts"]["primary_position"] = "D"
    player["facts"]["fine_roles"] = [4]
    aid = artifact_id(plan)
    result["artifacts"].append({"id": aid, "kind": "season-input", "relative_path": filename(plan),
                                "sha256": _digest(plan), "media_type": "application/json"})
    result["proofs"].append({"id": "proof-" + aid, "grade": "source-receipt", "artifact_id": aid,
                             "covers": ["exact-Coady-identity", "2017-18-onwards-Wolves-defence-history",
                                        "source-annual-M-conflict-retained-when-present", "native-exclusive-owner-guard"]})
    result["artifacts"].sort(key=lambda row: row["id"])
    result["proofs"].sort(key=lambda row: row["id"])
    packages.validate_package(result)
    # Only the target's two role facts and our artifact/proof may differ.
    expected = copy.deepcopy(original)
    expected_player = next(p for p in expected["players"] if p.get("carrier_id") == plan["target"]["carrier_id"])
    expected_player["facts"]["primary_position"] = "D"
    expected_player["facts"]["fine_roles"] = [4]
    expected["artifacts"].append(copy.deepcopy(next(row for row in result["artifacts"] if row["id"] == aid)))
    expected["proofs"].append(copy.deepcopy(next(row for row in result["proofs"] if row["id"] == "proof-" + aid)))
    expected["artifacts"].sort(key=lambda row: row["id"])
    expected["proofs"].sort(key=lambda row: row["id"])
    if _canon(expected) != _canon(result):
        raise ValueError("Coady cascade bind changed data outside declared role fields and evidence rows")
    return result


def apply(jug, eq, plan):
    _check_plan(plan)
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    verify(base, plan)
    if _sha(eq) != plan["parent"]["native_files"]["EQ98030.FDI"]:
        raise ValueError("Coady cascade exact EQ parent differs")
    original_jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    update = {"carrier_id": plan["target"]["carrier_id"], "before_player": plan["target"]["before_player"],
              "before_native": plan["target"]["before_native"], "primary_position": "D", "fine_roles": [4]}
    lower = {"schema": native_writer.SCHEMA, "season": plan["season"], "release_id": plan["release_id"],
             "package_sha256": plan["parent"]["package_sha256"],
             "jug_sha256": plan["parent"]["native_files"]["JUG98030.FDI"],
             "eq_sha256": plan["parent"]["native_files"]["EQ98030.FDI"], "updates": [update]}
    postimage, eq_out = native_writer.apply(original_jug, eq, lower)
    if jug not in (original_jug, postimage):
        raise ValueError("Coady cascade requires its exact parent or exact verified postimage")
    if eq_out != eq:
        raise ValueError("Coady cascade unexpectedly changed EQ")
    return postimage, eq_out


def reject_factory_recipe(package):
    if any(str(row.get("id", "")).startswith(PREFIX) for row in package.get("artifacts", [])):
        raise ValueError("Coady cascade source layer requires typed reconstruction, not factory compilation")


def reconstruction(previous, release_id):
    receipt_path = getattr(previous, "compiler_receipt_path", None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    # Check the private MODE before resolving optional locator/plan fields.
    if receipt.get("compilation_mode") != MODE:
        return None
    relative = getattr(previous, "locator", {}).get("sourced_profile_assignment_plan_path")
    if not relative:
        raise ValueError("Coady cascade SOURCE receipt has no typed plan path")
    path = (ROOT / relative).resolve(strict=True)
    plan = pipeline.read_json_file(path)
    _check_plan(plan)
    base = registry.load_registered_release(plan["season"], plan["release_id"])
    verify(base, plan)
    if path != (previous.package_path.parent / filename(plan)).resolve() or _file_sha(path) != receipt.get("original_profile_assignment_plan_sha256"):
        raise ValueError("Coady cascade SOURCE plan path/hash differs from compiler receipt")
    expected = bind(pipeline.read_json_file(base.package_path), plan)
    if _canon(pipeline.read_json_file(previous.package_path)) != _canon(expected):
        raise ValueError("Coady cascade SOURCE package differs from typed recipe")
    descriptor = previous.package_path.parent / "role-delta-input.json"
    expected_descriptor = {"season": base.season, "release_id": base.release_id,
                           "package_sha256": plan["parent"]["package_sha256"],
                           "jug_sha256": plan["parent"]["native_files"]["JUG98030.FDI"],
                           "updates": [], "unresolved": []}
    if pipeline.read_json_file(descriptor) != expected_descriptor:
        raise ValueError("Coady cascade SOURCE descriptor is not inert")
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor, release_id=release_id, source_release_id=plan["release_id"],
                      profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if _canon(pipeline.read_json_file(rebuilt.package_path)) != _canon(expected):
        raise ValueError("Coady cascade SOURCE reconstruction differs from exact typed recipe")
    return {"season": previous.season, "release_id": release_id, "complete_recipe_identical": True,
            "complete_game_inventory_identical": True, "compilation_mode": MODE}
