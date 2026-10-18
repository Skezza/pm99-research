#!/usr/bin/env python3
"""Promote exact dated opening-manager evidence into one season package.

The historical capture lane contains many more clubs than PM99's fixed club
inventory.  This adapter joins those two worlds conservatively: a club name
must have one exact accent-insensitive match, and the target manager carrier
must belong to that club alone.  Anything else is reported and left unchanged.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-target-season-manager-ledger-application-v1"


class ManagerLedgerApplicationError(ValueError):
    """A manager ledger cannot be promoted without guessing."""


def _normalise(value: object) -> str:
    text = str(value or "").translate(str.maketrans({
        "ı": "i", "İ": "I", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
        "ð": "d", "Ð": "D", "þ": "th", "Þ": "Th", "æ": "ae", "Æ": "Ae",
        "ø": "o", "Ø": "O", "ß": "ss",
    }))
    text = unicodedata.normalize("NFKD", text)
    return "".join(
        character.casefold()
        for character in text
        if character.isalnum() and not unicodedata.combining(character)
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ManagerLedgerApplicationError(
            f"manager ledger lies outside the workspace: {path}"
        ) from exc


def _season_key(package: Mapping[str, Any]) -> str:
    season = package.get("season")
    if not isinstance(season, Mapping):
        raise ManagerLedgerApplicationError("package season is missing")
    start, end = season.get("start_year"), season.get("end_year")
    if not isinstance(start, int) or not isinstance(end, int):
        raise ManagerLedgerApplicationError("package season years are invalid")
    return f"{start:04d}-{end % 100:02d}"


def apply_ledger(
    package: Mapping[str, Any], ledger: Mapping[str, Any], *,
    ledger_path: str, ledger_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a derived package and complete conservative join audit."""
    output = copy.deepcopy(dict(package))
    season = _season_key(output)
    if ledger.get("season_start_year") != int(season[:4]):
        raise ManagerLedgerApplicationError("manager ledger targets a different season")
    ledger_rows = ledger.get("managers")
    if not isinstance(ledger_rows, list):
        raise ManagerLedgerApplicationError("manager ledger has no manager rows")

    source_by_club: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    source_by_carrier: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in ledger_rows:
        if not isinstance(row, Mapping):
            continue
        selector = row.get("source_selector")
        club_name = selector.get("club_name") if isinstance(selector, Mapping) else None
        manager_name = str(row.get("manager_name") or "").strip()
        if club_name and manager_name:
            source_by_club[_normalise(club_name)].append(row)
        # A fixed PM99 carrier can deliberately display a different native
        # club name.  A reviewed carrier key is therefore the only safe join
        # for global world receipts; it takes precedence over name matching.
        carrier_id = row.get("carrier_id")
        if isinstance(carrier_id, int) and carrier_id > 0 and manager_name:
            source_by_carrier[carrier_id].append(row)

    clubs = [row for row in output.get("clubs") or [] if isinstance(row, dict)]
    managers = {
        str(row.get("id") or ""): row
        for row in output.get("managers") or []
        if isinstance(row, dict)
    }
    owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for club in clubs:
        owners[str(club.get("manager_id") or "")].append(club)

    artifact_id = f"opening-manager-ledger-{season}"
    artifacts = [row for row in output.get("artifacts") or [] if isinstance(row, dict)]
    artifacts = [row for row in artifacts if row.get("id") != artifact_id]
    artifacts.append({
        "id": artifact_id,
        "kind": "season-input",
        "relative_path": ledger_path,
        "sha256": ledger_sha256,
    })
    output["artifacts"] = sorted(artifacts, key=lambda row: str(row.get("id") or ""))

    applied: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for club in clubs:
        club_name = str(club.get("name") or "")
        carrier_id = int(club.get("carrier_id") or 0)
        carrier_candidates = source_by_carrier.get(carrier_id, [])
        candidates = carrier_candidates or source_by_club.get(_normalise(club_name), [])
        join_method = "explicit-reviewed-carrier" if carrier_candidates else "exact-normalised-club-name"
        manager_id = str(club.get("manager_id") or "")
        manager = managers.get(manager_id)
        if len(candidates) != 1:
            gaps.append({
                "club_id": club.get("id"), "club": club_name,
                "reason": "source-club-absent" if not candidates else "source-club-ambiguous",
                "source_match_count": len(candidates),
            })
            continue
        if manager is None:
            gaps.append({
                "club_id": club.get("id"), "club": club_name,
                "reason": "package-manager-entity-missing", "manager_id": manager_id,
            })
            continue
        if len(owners[manager_id]) != 1:
            gaps.append({
                "club_id": club.get("id"), "club": club_name,
                "reason": "manager-carrier-shared-by-clubs", "manager_id": manager_id,
                "owner_clubs": [str(row.get("name") or "") for row in owners[manager_id]],
            })
            continue

        source = candidates[0]
        expected_name = str(source["manager_name"]).strip()
        previous_name = str(manager.get("name") or "")
        previous_policy = manager.get("policy")
        manager["name"] = expected_name
        manager["policy"] = "write"
        manager["person_id"] = f"manager-person-evidence-{season}-{int(manager['carrier_id'])}"
        manager["proof"] = {"artifact_id": artifact_id, "grade": "source-receipt"}
        evidence = source.get("evidence") if isinstance(source.get("evidence"), Mapping) else {}
        row = {
            "club_id": club.get("id"), "club": club_name, "manager_id": manager_id,
            "manager_carrier_id": manager.get("carrier_id"),
            "previous_manager": previous_name, "opening_manager": expected_name,
            "opening_fixture_date": source.get("opening_fixture_date"),
            "resolution_method": source.get("resolution_method"),
            "package_join_method": join_method,
            "source_url": evidence.get("source_url"),
            "source_snapshot_sha256": evidence.get("source_snapshot_sha256"),
        }
        if _normalise(previous_name) == _normalise(expected_name) and previous_policy == "write":
            unchanged.append(row)
        else:
            applied.append(row)

    output["managers"] = sorted(managers.values(), key=lambda row: str(row.get("id") or ""))
    audit = {
        "schema_version": SCHEMA,
        "season": season,
        "state": "exact-dated-manager-evidence-promoted",
        "input": {"manager_ledger_path": ledger_path, "manager_ledger_sha256": ledger_sha256},
        "policy": (
            "reviewed explicit carrier when supplied, otherwise exact-normalised-club-name; "
            "unique source row; exclusive package manager carrier"
        ),
        "coverage": {
            "package_club_count": len(clubs),
            "ledger_manager_count": len(ledger_rows),
            "evidence_bound_count": len(applied) + len(unchanged),
            "changed_manager_count": len(applied),
            "already_correct_manager_count": len(unchanged),
            "gap_count": len(gaps),
        },
        "applied": applied,
        "already_correct": unchanged,
        "gaps": gaps,
    }
    return output, audit


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output_package.exists() or args.output_audit.exists():
            raise ManagerLedgerApplicationError("refusing to overwrite an existing output")
        package = package_v2.read_canonical_package(args.package)
        package_v2.validate_package(package, strict=True)
        ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
        if not isinstance(ledger, dict):
            raise ManagerLedgerApplicationError("manager ledger must be an object")
        derived, audit = apply_ledger(
            package, ledger, ledger_path=_relative(args.ledger), ledger_sha256=_sha256(args.ledger),
        )
        package_v2.validate_package(derived, strict=True)
    except (OSError, json.JSONDecodeError, package_v2.PackageValidationError, ManagerLedgerApplicationError) as exc:
        parser.error(str(exc))
    args.output_package.parent.mkdir(parents=True, exist_ok=True)
    args.output_package.write_bytes(package_v2.canonical_json_bytes(derived))
    audit["input"]["package_path"] = _relative(args.package)
    audit["input"]["package_sha256"] = _sha256(args.package)
    audit["output"] = {
        "package_path": _relative(args.output_package),
        "package_sha256": _sha256(args.output_package),
    }
    args.output_audit.write_bytes(package_v2.canonical_json_bytes(audit))
    print(json.dumps(audit["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
