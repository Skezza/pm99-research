#!/usr/bin/env python3
"""Block a 2015/16 world release with semantic manager, handling or kit defects.

Structural hashes can prove that a byte range was written.  They cannot prove
that a manager entity is not still linked to a second club, that the field
labelled ``HANDLING`` is goalkeeper technique rather than ball control, or
that a quantised kit is acceptable in the game UI.  This read-only audit joins
the compiled FDI files to the declared package and records those semantic
conditions explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.editor_actions import _native_dd6360_role_start, _read_native_dd6360_fields, build_player_visible_skill_index_dd6361  # noqa: E402
from app.ent_manager_profiles import parse_indexed_ent_manager_profile  # noqa: E402
from app.eq_team_manager_links import parse_indexed_eq_manager_links  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records  # noqa: E402
from app.xor import xor_decode  # noqa: E402


SCHEMA = "pm99-world-2015-release-semantic-qa-v1"
KIT_REVIEW_SCHEMA = "pm99-kit-visual-review-v1"
FOREIGN_KIT_ARCHIVES = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")
OUTFIELD_HANDLING_MAXIMUM = 20


class SemanticQaError(ValueError):
    pass


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_object(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemanticQaError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise SemanticQaError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _read_list(path: Path, label: str) -> tuple[list[dict[str, Any]], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SemanticQaError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise SemanticQaError(f"{label} must be a JSON list of objects")
    return value, hashlib.sha256(raw).hexdigest()


def _team_name(raw_payload: bytes) -> str:
    """Read the proven indexed EQ display-name span without changing it."""
    if len(raw_payload) < 0x2C:
        return ""
    length = int.from_bytes(raw_payload[0x2A:0x2C], "little")
    start, end = 0x2C, 0x2C + length
    if length <= 0 or end > len(raw_payload):
        return ""
    return xor_decode(raw_payload[start:end]).decode("cp1252", errors="replace").rstrip("\x00")


def _manager_graph(*, eq_path: Path, ent_path: Path) -> tuple[dict[int, list[dict[str, Any]]], dict[int, str]]:
    eq_bytes, ent_bytes = eq_path.read_bytes(), ent_path.read_bytes()
    manager_names: dict[int, str] = {}
    for entry in IndexedFDIFile.from_bytes(ent_bytes).entries:
        raw = ent_bytes[entry.payload_offset:entry.payload_offset + entry.payload_length]
        try:
            manager_names[entry.record_id] = parse_indexed_ent_manager_profile(raw, record_id=entry.record_id).display_name
        except ValueError:
            continue
    holders: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for entry in IndexedFDIFile.from_bytes(eq_bytes).entries:
        raw = eq_bytes[entry.payload_offset:entry.payload_offset + entry.payload_length]
        try:
            manager_id = parse_indexed_eq_manager_links(raw).active_manager_record_id
        except ValueError:
            continue
        if manager_id is not None:
            holders[manager_id].append({"carrier_id": entry.record_id, "club_name": _team_name(raw)})
    return dict(holders), manager_names


def _written_manager_expectations(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    managers = package.get("managers")
    clubs = package.get("clubs")
    if not isinstance(managers, list) or not isinstance(clubs, list):
        raise SemanticQaError("world package lacks managers or clubs")
    owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for club in clubs:
        if isinstance(club, Mapping) and isinstance(club.get("manager_id"), str):
            owners[str(club["manager_id"])].append({
                "carrier_id": int(club.get("carrier_id") or 0), "club_name": str(club.get("name") or ""),
            })
    rows: list[dict[str, Any]] = []
    for manager in managers:
        if not isinstance(manager, Mapping) or manager.get("policy") != "write":
            continue
        carrier = int(manager.get("carrier_id") or 0)
        identifier = str(manager.get("id") or "")
        if carrier <= 0 or not identifier:
            raise SemanticQaError("written manager is missing its carrier or ID")
        rows.append({
            "manager_record_id": carrier,
            "canonical_manager_name": str(manager.get("name") or ""),
            "manager_name": str((manager.get("native_names") or {}).get("display_name") or manager.get("name") or ""),
            "expected_clubs": sorted(owners.get(identifier, []), key=lambda row: row["carrier_id"]),
        })
    return sorted(rows, key=lambda row: row["manager_record_id"])


def audit_managers(*, package: Mapping[str, Any], eq_path: Path, ent_path: Path) -> dict[str, Any]:
    holders, names = _manager_graph(eq_path=eq_path, ent_path=ent_path)
    rows: list[dict[str, Any]] = []
    for expected in _written_manager_expectations(package):
        manager_id = int(expected["manager_record_id"])
        actual = sorted(holders.get(manager_id, []), key=lambda row: row["carrier_id"])
        expected_clubs = expected["expected_clubs"]
        exact_owner = actual == expected_clubs and len(actual) == 1
        name_matches = names.get(manager_id) == expected["manager_name"]
        rows.append({
            **expected,
            "stored_manager_name": names.get(manager_id),
            "actual_active_clubs": actual,
            "exclusive_correct_owner": exact_owner,
            "stored_name_matches_package": name_matches,
            "pass": exact_owner and name_matches,
        })
    return {
        "written_manager_count": len(rows),
        "exclusive_correct_owner_count": sum(row["exclusive_correct_owner"] for row in rows),
        "name_match_count": sum(row["stored_name_matches_package"] for row in rows),
        "failure_count": sum(not row["pass"] for row in rows),
        "failures": [row for row in rows if not row["pass"]],
    }


def _ledger_player_rows(rows: Iterable[Mapping[str, Any]]) -> Iterable[dict[str, Any]]:
    for row in rows:
        skills = row.get("visible_skills")
        if not isinstance(skills, Mapping):
            raise SemanticQaError("English player ledger row lacks visible_skills")
        yield {
            "record_id": int(row.get("record_id") or 0),
            "name": str(row.get("name") or ""),
            "club": str(row.get("club") or ""),
            "position": str(row.get("position") or ""),
            "family": str(row.get("family") or ""),
            "handling": int(skills.get("handling") or 0),
            "handling_basis": str(row.get("handling_basis") or ""),
            "source": "english-player-ledger",
        }


def _package_player_rows(package: Mapping[str, Any]) -> Iterable[dict[str, Any]]:
    clubs = {str(row.get("id") or ""): str(row.get("name") or "") for row in package.get("clubs") or [] if isinstance(row, Mapping)}
    for row in package.get("players") or []:
        if not isinstance(row, Mapping):
            raise SemanticQaError("world package contains a malformed player")
        facts, ratings = row.get("facts"), row.get("ratings")
        values = ratings.get("values") if isinstance(ratings, Mapping) else None
        if not isinstance(facts, Mapping) or not isinstance(values, Mapping):
            raise SemanticQaError("world package player lacks facts or ratings.values")
        yield {
            "record_id": int(row.get("carrier_id") or 0),
            "name": str(row.get("name") or ""),
            "club": clubs.get(str(row.get("club_id") or ""), str(row.get("club_id") or "")),
            "position": str(facts.get("primary_position") or ""),
            "family": str(row.get("carrier_family") or ""),
            "handling": int(values.get("handling") or 0),
            "handling_basis": "package-rated",
            "source": "world-package",
        }


def _name_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").casefold()
    return "".join(character for character in text if character.isalnum())


def _runtime_handling_indexes(jug_path: Path, player_rows: Iterable[Mapping[str, Any]]) -> tuple[dict[int, int], dict[str, list[dict[str, Any]]]]:
    player_rows = list(player_rows)
    needed_dd6360 = {int(row["record_id"]) for row in player_rows if row["family"] == "dd6360"}
    needed_dd6361 = {int(row["record_id"]) for row in player_rows if row["family"] == "dd6361"}
    index = IndexedFDIFile.from_path(jug_path)
    data = jug_path.read_bytes()
    compact: dict[int, int] = {}
    for entry in index.entries:
        if entry.record_id not in needed_dd6360:
            continue
        decoded = entry.decode_payload(data)
        compact[entry.record_id] = int(_read_native_dd6360_fields(decoded, _native_dd6360_role_start(decoded))["handling"])
    extended = build_player_visible_skill_index_dd6361(file_path=str(jug_path))
    by_record = dict(compact)
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record_id, row in extended.items():
        if "handling" not in row["mapped10"]:
            continue
        handling = int(row["mapped10"]["handling"])
        # A cross-entry dd6361 biography scan can surface the same numeric ID
        # as a real compact dd6360 carrier.  The package-declared family and
        # direct compact payload read are authoritative for that carrier.
        if record_id not in needed_dd6360:
            by_record[record_id] = handling
        by_name[_name_key(str(row["resolved_bio_name"]))].append({"record_id": record_id, "handling": handling})
    # The editor's biography index intentionally excludes several valid
    # dd6361 carrier shapes (including compact biographies and very large
    # fixed rows).  The compiler's proven write contract is broader: after
    # validating the family signature, Handling is always the XOR byte at
    # payload[-7].  Read that exact byte for requested carrier IDs that the
    # biography parser did not index, matching the compiler's own mandatory
    # post-write verification rather than reporting them as absent.
    entries = {entry.record_id: entry for entry in index.entries}
    for record_id in sorted(needed_dd6361):
        entry = entries.get(record_id)
        if entry is None:
            continue
        payload = entry.decode_payload(data)
        if len(payload) >= 19 and payload[2:5] == b"\xdd\x63\x61":
            by_record[record_id] = int(payload[-7] ^ 0x61)
    return by_record, dict(by_name)


def audit_handling(*, english_ledger: Sequence[Mapping[str, Any]], package: Mapping[str, Any], jug_path: Path) -> dict[str, Any]:
    rows = [*_ledger_player_rows(english_ledger), *_package_player_rows(package)]
    by_record: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["record_id"] <= 0:
            raise SemanticQaError("player QA row has no valid record ID")
        by_record[row["record_id"]].append(row)
    ownership_collisions = [
        {"record_id": record_id, "claims": claims}
        for record_id, claims in sorted(by_record.items())
        if len(claims) > 1
    ]
    runtime_by_record, runtime_by_name = _runtime_handling_indexes(jug_path, rows)
    failures: list[dict[str, Any]] = []
    for row in rows:
        if row["family"] == "dd6361":
            candidates = runtime_by_name.get(_name_key(row["name"]), [])
            observed = candidates[0]["handling"] if len(candidates) == 1 else None
            observed_record_id = candidates[0]["record_id"] if len(candidates) == 1 else None
        else:
            observed = runtime_by_record.get(row["record_id"])
            observed_record_id = row["record_id"] if observed is not None else None
        non_goalkeeper = row["position"] != "G"
        semantic_ok = not non_goalkeeper or 1 <= row["handling"] <= OUTFIELD_HANDLING_MAXIMUM
        runtime_semantic_ok = not non_goalkeeper or (observed is not None and 1 <= observed <= OUTFIELD_HANDLING_MAXIMUM)
        runtime_readback_ok = not non_goalkeeper or observed == row["handling"]
        ball_control_ok = "ball-control" not in row["handling_basis"].casefold()
        passed = semantic_ok and runtime_semantic_ok and runtime_readback_ok and ball_control_ok
        if not passed:
            failures.append({
                **row, "runtime_record_id": observed_record_id, "runtime_handling": observed,
                "outfield_handling_in_range": semantic_ok,
                "runtime_outfield_handling_in_range": runtime_semantic_ok,
                "runtime_readback_matches": runtime_readback_ok,
                "handling_basis_is_not_ball_control": ball_control_ok,
            })
    return {
        "player_count": len(rows),
        "unique_player_record_count": len(by_record),
        "outfield_player_count": sum(row["position"] != "G" for row in rows),
        "outfield_handling_maximum": OUTFIELD_HANDLING_MAXIMUM,
        "ownership_collision_count": len(ownership_collisions),
        "semantic_or_readback_failure_count": len(failures),
        "failure_count": len(ownership_collisions) + len(failures),
        "ownership_collisions": ownership_collisions,
        "failures": failures,
    }


def _kit_records(path: Path) -> dict[int, Any]:
    return {
        int(match.group(1)): record
        for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$")
        if (match := re.fullmatch(r"EQ96(\d{4})\.BMP", str(record.file_name), re.IGNORECASE))
    }


def _reviewed_carriers(review: Mapping[str, Any] | None) -> set[int]:
    if review is None:
        return set()
    if review.get("schema_version") != KIT_REVIEW_SCHEMA:
        raise SemanticQaError("kit review receipt has an unsupported schema")
    rows = review.get("rows")
    if not isinstance(rows, list):
        raise SemanticQaError("kit review receipt has no rows")
    return {int(row.get("carrier_id") or 0) for row in rows if isinstance(row, Mapping) and row.get("approved") is True}


def audit_kits(*, game_tree: Path, receipt: Mapping[str, Any], review: Mapping[str, Any] | None) -> dict[str, Any]:
    events = receipt.get("foreign_events")
    if not isinstance(events, list):
        raise SemanticQaError("foreign kit receipt has no foreign_events")
    reviewed = _reviewed_carriers(review)
    expected: dict[int, dict[str, str]] = defaultdict(dict)
    for event in events:
        if not isinstance(event, Mapping):
            raise SemanticQaError("foreign kit receipt contains a malformed event")
        archive, carrier = str(event.get("archive") or ""), int(event.get("carrier_id") or 0)
        digest = str(event.get("bitmap_sha256_after") or "")
        if archive not in FOREIGN_KIT_ARCHIVES or carrier <= 0 or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SemanticQaError("foreign kit event has an invalid archive, carrier or bitmap hash")
        if archive in expected[carrier]:
            raise SemanticQaError(f"foreign kit receipt duplicates {archive} carrier {carrier}")
        expected[carrier][archive] = digest
    failures: list[dict[str, Any]] = []
    record_indexes = {archive: _kit_records(game_tree / "DBDAT" / archive) for archive in FOREIGN_KIT_ARCHIVES}
    for carrier, archive_hashes in sorted(expected.items()):
        readback_ok = True
        for archive in FOREIGN_KIT_ARCHIVES:
            record = record_indexes[archive].get(carrier)
            if record is None or hashlib.sha256(record.raw_bitmap).hexdigest() != archive_hashes.get(archive):
                readback_ok = False
        visual_approved = carrier in reviewed
        if not readback_ok or not visual_approved:
            failures.append({"carrier_id": carrier, "archive_readback_matches": readback_ok, "visual_review_approved": visual_approved})
    return {
        "patched_foreign_carrier_count": len(expected),
        "visually_approved_carrier_count": len(set(expected) & reviewed),
        "failure_count": len(failures),
        "failures": failures,
        "policy": "each patched foreign carrier needs exact archive readback and an explicit visual-review approval; byte-valid artwork alone is insufficient",
    }


def audit_release(*, game_tree: Path, world_package: Mapping[str, Any], english_ledger: Sequence[Mapping[str, Any]], kit_receipt: Mapping[str, Any], kit_review: Mapping[str, Any] | None) -> dict[str, Any]:
    dbdat = game_tree / "DBDAT"
    managers = audit_managers(package=world_package, eq_path=dbdat / "EQ98030.FDI", ent_path=dbdat / "ENT98030.FDI")
    handling = audit_handling(english_ledger=english_ledger, package=world_package, jug_path=dbdat / "JUG98030.FDI")
    kits = audit_kits(game_tree=game_tree, receipt=kit_receipt, review=kit_review)
    passed = not managers["failure_count"] and not handling["failure_count"] and not kits["failure_count"]
    return {
        "schema_version": SCHEMA,
        "classification": "post-compile-semantic-release-gate",
        "result": "pass" if passed else "fail",
        "policy": {
            "manager": "a written manager entity must be the active manager of exactly its one declared club",
            "handling": f"every outfield player must have runtime Handling in 1..{OUTFIELD_HANDLING_MAXIMUM}; ball-control is never Handling",
            "kits": "every changed foreign compact kit needs byte readback plus an explicit visual-review approval",
        },
        "summary": {
            "manager_failure_count": managers["failure_count"],
            "handling_failure_count": handling["failure_count"],
            "kit_failure_count": kits["failure_count"],
        },
        "managers": managers,
        "handling": handling,
        "kits": kits,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-tree", required=True, type=Path)
    parser.add_argument("--world-package", required=True, type=Path)
    parser.add_argument("--english-player-ledger", required=True, type=Path)
    parser.add_argument("--foreign-kit-receipt", required=True, type=Path)
    parser.add_argument("--kit-review-receipt", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        package, package_sha = _read_object(args.world_package, "world package")
        ledger, ledger_sha = _read_list(args.english_player_ledger, "English player ledger")
        kits, kits_sha = _read_object(args.foreign_kit_receipt, "foreign kit receipt")
        review, review_sha = (None, None)
        if args.kit_review_receipt is not None:
            review, review_sha = _read_object(args.kit_review_receipt, "kit review receipt")
        result = audit_release(game_tree=args.game_tree, world_package=package, english_ledger=ledger, kit_receipt=kits, kit_review=review)
    except (OSError, SemanticQaError, ValueError) as exc:
        parser.error(str(exc))
    result["inputs"] = {
        "game_tree": str(args.game_tree.resolve()),
        "world_package": {"path": str(args.world_package.resolve()), "sha256": package_sha},
        "english_player_ledger": {"path": str(args.english_player_ledger.resolve()), "sha256": ledger_sha},
        "foreign_kit_receipt": {"path": str(args.foreign_kit_receipt.resolve()), "sha256": kits_sha},
        "kit_review_receipt": None if review_sha is None else {"path": str(args.kit_review_receipt.resolve()), "sha256": review_sha},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_bytes(result))
    print(json.dumps({"result": result["result"], **result["summary"]}, sort_keys=True))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
