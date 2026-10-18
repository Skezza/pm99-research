#!/usr/bin/env python3
"""Validate a PM99 world season's fixed-carrier content contract.

This tool deliberately has no membership writer.  PM99 foreign league / draw
topology is not a proven persistent DBDAT field.  The only supported action is
to replace proven content *inside* an existing EQ carrier while preserving the
base EQ directory identity exactly.  It binds a canonical Season Package V2 to
that carrier map, validates source evidence, and emits an explicit native
no-photo review queue for every non-applied portrait.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = REPO_ROOT / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from season_package_v2 import (  # noqa: E402
    PackageValidationError,
    canonical_json_bytes,
    read_canonical_package,
    sha256_file,
    validate_package,
    write_canonical_package,
)


SCHEMA_VERSION = "pm99-fixed-carrier-world-ledger-v1"
SCHEMA_PATH = REPO_ROOT / "schemas" / f"{SCHEMA_VERSION}.schema.json"
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class LedgerValidationError(ValueError):
    """The fixed-carrier ledger is not reproducible or would widen scope."""


def _canonical_json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


def read_canonical_ledger(path: Path) -> dict[str, Any]:
    """Read the sole portable on-disk form accepted for a carrier ledger."""
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LedgerValidationError(f"{path}: not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LedgerValidationError(f"{path}: ledger root must be an object")
    if raw != _canonical_json_bytes(value):
        raise LedgerValidationError(
            f"{path}: ledger is not canonically encoded; use write_canonical_ledger()"
        )
    return value


def write_canonical_ledger(path: Path, ledger: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(ledger))


def _schema_errors(ledger: dict[str, Any]) -> list[str]:
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return []
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(ledger), key=lambda item: list(item.absolute_path))
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in errors
    ]


def _directory_identity(indexed: IndexedFDIFile) -> list[dict[str, Any]]:
    """Return the only immutable directory identity this contract relies on.

    Payload offsets and lengths can change during a variable-length content
    rebuild.  EQ record ID, key and ordinal cannot: changing any of them is a
    topology modification and is refused.
    """
    return [
        {"ordinal": ordinal, "record_id": int(entry.record_id), "key": entry.key}
        for ordinal, entry in enumerate(indexed.entries)
    ]


def directory_identity_sha256(indexed: IndexedFDIFile) -> str:
    return hashlib.sha256(_canonical_json_bytes(_directory_identity(indexed))).hexdigest()


def inspect_base_eq(path: Path) -> dict[str, Any]:
    """Read a base EQ file and create the values a ledger must lock."""
    indexed = IndexedFDIFile.from_path(path)
    return {
        "eq98030_sha256": sha256_file(path),
        "record_count": int(indexed.record_count),
        "directory_identity_sha256": directory_identity_sha256(indexed),
        "write_policy": "preserve-existing-carriers",
    }


def _index_items(
    items: Any,
    label: str,
    errors: list[str],
    *,
    id_key: str = "id",
    sorted_by: str | None = None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        errors.append(f"{label}: must be a list")
        return {}
    result: dict[str, dict[str, Any]] = {}
    previous: str | None = None
    key_name = sorted_by or id_key
    for number, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{number}]: must be an object")
            continue
        identity = item.get(id_key)
        if not isinstance(identity, str) or not ID_RE.fullmatch(identity):
            errors.append(f"{label}[{number}].{id_key}: invalid stable id")
            continue
        if identity in result:
            errors.append(f"{label}[{number}].{id_key}: duplicate {identity!r}")
        sortable = item.get(key_name)
        if not isinstance(sortable, str):
            errors.append(f"{label}[{number}].{key_name}: invalid sort key")
        elif previous is not None and sortable < previous:
            errors.append(f"{label}: must be sorted by {key_name}")
        elif isinstance(sortable, str):
            previous = sortable
        result[identity] = item
    return result


def _package_indexes(package: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    clubs = package.get("clubs")
    sources = package.get("sources")
    club_index = {
        row["id"]: row for row in clubs if isinstance(row, dict) and isinstance(row.get("id"), str)
    } if isinstance(clubs, list) else {}
    package_sources = {
        row["id"] for row in sources if isinstance(row, dict) and isinstance(row.get("id"), str)
    } if isinstance(sources, list) else set()
    return club_index, package_sources


def _validate_base_lock(ledger: dict[str, Any], base_eq: Path, errors: list[str]) -> tuple[IndexedFDIFile | None, dict[int, int]]:
    try:
        indexed = IndexedFDIFile.from_path(base_eq)
    except (OSError, ValueError) as exc:
        errors.append(f"base EQ cannot be parsed: {exc}")
        return None, {}
    lock = ledger.get("topology_lock")
    if not isinstance(lock, dict):
        return indexed, {}
    actual = inspect_base_eq(base_eq)
    for key in ("eq98030_sha256", "record_count", "directory_identity_sha256", "write_policy"):
        if lock.get(key) != actual[key]:
            errors.append(
                f"topology_lock.{key}: expected locked {lock.get(key)!r}, actual base EQ is {actual[key]!r}"
            )
    return indexed, {int(entry.record_id): ordinal for ordinal, entry in enumerate(indexed.entries)}


def validate_ledger(
    ledger: dict[str, Any],
    package: dict[str, Any],
    *,
    package_path: Path | None = None,
    base_eq: Path | None = None,
) -> dict[str, Any]:
    """Validate the world ledger without changing a game or package file.

    A ledger covers *all* clubs in its package.  This prevents an accidental
    silent fallback to an inherited carrier when a world source is incomplete.
    It also makes carrier identity checks exact rather than relying on an
    unproven country/division field.
    """
    errors = _schema_errors(ledger)
    try:
        validate_package(package, strict=False)
    except PackageValidationError as exc:
        errors.append(f"season package is invalid: {exc}")

    if ledger.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    ledger_id = ledger.get("ledger_id")
    if not isinstance(ledger_id, str) or not ID_RE.fullmatch(ledger_id):
        errors.append("ledger_id: invalid stable id")
    digest = ledger.get("package_sha256")
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        errors.append("package_sha256: must be a lowercase SHA-256")
    elif package_path is not None and digest != sha256_file(package_path):
        errors.append("package_sha256 does not bind this canonical season package")

    season = package.get("season") if isinstance(package, dict) else None
    if not isinstance(season, dict) or ledger.get("season_label") != season.get("label"):
        errors.append("season_label must exactly match the package season label")
    scope = package.get("scope") if isinstance(package, dict) else None
    if not isinstance(scope, dict) or scope.get("competition_policy") != "existing-carriers-only":
        errors.append(
            "package scope.competition_policy must be 'existing-carriers-only'; "
            "this ledger cannot authorise a membership/topology write"
        )

    club_index, package_source_ids = _package_indexes(package)
    source_index = _index_items(ledger.get("sources"), "sources", errors)
    for source_id, source in source_index.items():
        evidence = source.get("evidence_sha256")
        if not isinstance(evidence, str) or not SHA256_RE.fullmatch(evidence):
            errors.append(f"sources[{source_id}].evidence_sha256: must be a lowercase SHA-256")
        linked_sources = source.get("package_source_ids")
        if not isinstance(linked_sources, list) or not linked_sources:
            errors.append(f"sources[{source_id}].package_source_ids: at least one V2 source is required")
        else:
            for source_ref in linked_sources:
                if source_ref not in package_source_ids:
                    errors.append(f"sources[{source_id}].package_source_ids: unknown package source {source_ref!r}")

    assignments = ledger.get("carrier_assignments")
    assignment_index = _index_items(assignments, "carrier_assignments", errors, id_key="club_id", sorted_by="club_id")
    seen_carriers: set[int] = set()
    for club_id, assignment in assignment_index.items():
        club = club_index.get(club_id)
        if club is None:
            errors.append(f"carrier_assignments[{club_id}]: unknown package club")
            continue
        carrier_id = assignment.get("carrier_id")
        if not isinstance(carrier_id, int) or carrier_id < 1:
            errors.append(f"carrier_assignments[{club_id}].carrier_id: must be a positive integer")
        elif carrier_id in seen_carriers:
            errors.append(f"carrier_assignments[{club_id}].carrier_id: duplicate fixed carrier {carrier_id}")
        else:
            seen_carriers.add(carrier_id)
        if carrier_id != club.get("carrier_id"):
            errors.append(
                f"carrier_assignments[{club_id}].carrier_id must equal package club carrier_id; "
                "the ledger cannot move a club to a new carrier"
            )
        source_ids = assignment.get("identity_source_ids")
        if not isinstance(source_ids, list) or not source_ids:
            errors.append(f"carrier_assignments[{club_id}].identity_source_ids: source evidence is required")
        else:
            for source_id in source_ids:
                if source_id not in source_index:
                    errors.append(f"carrier_assignments[{club_id}].identity_source_ids: unknown ledger source {source_id!r}")

    if set(assignment_index) != set(club_index):
        missing = sorted(set(club_index) - set(assignment_index))
        extra = sorted(set(assignment_index) - set(club_index))
        if missing:
            errors.append(f"carrier_assignments: package clubs without immutable carrier assignment: {missing}")
        if extra:
            errors.append(f"carrier_assignments: assignments for unknown package clubs: {extra}")

    policy = ledger.get("portrait_policy")
    if not isinstance(policy, dict) or policy.get("on_unavailable") != "native-no-photo" or policy.get("on_unsafe_conversion") != "native-no-photo" or policy.get("emit_review_queue") is not True:
        errors.append("portrait_policy must fail open to native-no-photo and emit a review queue")

    carrier_ordinals: dict[int, int] = {}
    if base_eq is not None:
        indexed, carrier_ordinals = _validate_base_lock(ledger, base_eq, errors)
        if indexed is not None:
            for club_id, assignment in assignment_index.items():
                carrier_id = assignment.get("carrier_id")
                actual_ordinal = carrier_ordinals.get(carrier_id)
                if actual_ordinal is None:
                    errors.append(f"carrier_assignments[{club_id}].carrier_id {carrier_id} is absent from base EQ")
                elif assignment.get("carrier_ordinal") != actual_ordinal:
                    errors.append(
                        f"carrier_assignments[{club_id}].carrier_ordinal must be {actual_ordinal} for fixed carrier {carrier_id}"
                    )

    if errors:
        raise LedgerValidationError("Fixed-carrier world ledger validation failed:\n- " + "\n- ".join(errors))
    return portrait_review_report(package)


def portrait_review_report(package: dict[str, Any]) -> dict[str, Any]:
    """List every player intentionally receiving PM99's native no-photo state."""
    players = {
        row["id"]: row
        for row in package.get("players", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    portraits = package.get("assets", {}).get("portraits", []) if isinstance(package.get("assets"), dict) else []
    queue: list[dict[str, Any]] = []
    counts = {"applied": 0, "native-no-photo": 0, "unresolved": 0}
    for portrait in portraits if isinstance(portraits, list) else []:
        if not isinstance(portrait, dict):
            continue
        status = portrait.get("status")
        if status not in counts:
            continue
        counts[status] += 1
        if status == "applied":
            continue
        player = players.get(portrait.get("player_id"), {})
        queue.append({
            "player_id": portrait.get("player_id"),
            "carrier_id": player.get("carrier_id"),
            "club_id": player.get("club_id"),
            "player_name": player.get("name"),
            "portrait_status": status,
            "review_reason": portrait.get("review_reason") or "reason not supplied in season package",
            "required_materialisation": "remove inherited carrier photo; use PM99 native no-photo state",
        })
    queue.sort(key=lambda row: str(row["player_id"]))
    return {
        "policy": "fail-open-native-no-photo",
        "release_blocking": False,
        "counts": counts,
        "review_queue": queue,
    }


def audit_output_eq(ledger: dict[str, Any], base_eq: Path, output_eq: Path) -> dict[str, Any]:
    """Prove an EQ output kept directory topology and touched only named carriers."""
    base_bytes, output_bytes = base_eq.read_bytes(), output_eq.read_bytes()
    base, output = IndexedFDIFile.from_bytes(base_bytes), IndexedFDIFile.from_bytes(output_bytes)
    base_identity, output_identity = _directory_identity(base), _directory_identity(output)
    topology_preserved = base_identity == output_identity
    base_by_id = {int(entry.record_id): entry for entry in base.entries}
    output_by_id = {int(entry.record_id): entry for entry in output.entries}
    changed_ids = sorted(
        record_id for record_id, entry in base_by_id.items()
        if entry.decode_payload(base_bytes) != output_by_id[record_id].decode_payload(output_bytes)
    ) if topology_preserved else []
    assignments = ledger.get("carrier_assignments", [])
    permitted = {
        row.get("carrier_id") for row in assignments
        if isinstance(row, dict) and isinstance(row.get("carrier_id"), int)
    }
    forbidden = sorted(set(changed_ids) - permitted)
    return {
        "base_eq": str(base_eq),
        "output_eq": str(output_eq),
        "topology_preserved": topology_preserved,
        "base_directory_identity_sha256": directory_identity_sha256(base),
        "output_directory_identity_sha256": directory_identity_sha256(output),
        "changed_carrier_ids": changed_ids,
        "permitted_carrier_ids": sorted(permitted),
        "forbidden_changed_carrier_ids": forbidden,
        "result": "passed" if topology_preserved and not forbidden else "failed",
    }


def _render_report(value: dict[str, Any], path: Path | None) -> None:
    rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect-base-eq", help="Print immutable EQ lock values for ledger authoring")
    inspect.add_argument("--eq", required=True, type=Path)
    inspect.add_argument("--report", type=Path)
    for command in ("validate", "audit-eq"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--ledger", required=True, type=Path)
        subparser.add_argument("--package", required=True, type=Path)
        subparser.add_argument("--base-eq", required=True, type=Path)
        subparser.add_argument("--report", type=Path)
        if command == "audit-eq":
            subparser.add_argument("--output-eq", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "inspect-base-eq":
            _render_report(inspect_base_eq(args.eq), args.report)
            return 0
        ledger = read_canonical_ledger(args.ledger)
        package = read_canonical_package(args.package)
        portrait_report = validate_ledger(ledger, package, package_path=args.package, base_eq=args.base_eq)
        if args.command == "validate":
            _render_report({"result": "passed", "portrait_review": portrait_report}, args.report)
            return 0
        audit = audit_output_eq(ledger, args.base_eq, args.output_eq)
        audit["portrait_review"] = portrait_report
        _render_report(audit, args.report)
        return 0 if audit["result"] == "passed" else 1
    except (LedgerValidationError, PackageValidationError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
