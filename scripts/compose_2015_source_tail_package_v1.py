#!/usr/bin/env python3
"""Join the three reviewed 2015 source-tail routes into one checked receipt.

This is deliberately a source composition step, not a database writer.  It
proves every target-membership carrier has exactly one capacity-safe roster
source, preserves hashes and source routes, and refuses unknown nationality or
position values.  It does not choose an arbitrary subset from an unranked
season squad: that later roster-selection policy must remain explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SCHEMA = "pm99-world-2015-source-tail-package-v1"
PLAN_SCHEMA = "pm99-world-2015-source-tail-replacement-plan-v1"
PINNED_SCHEMA = "pm99-world-2015-source-tail-squad-capture-v1"
OPENING_SCHEMA = "pm99-world-2015-source-tail-opening-squad-capture-v1"
GRANITAS_SCHEMA = "pm99-world-2015-lff-opening-squad-capture-v1"
TARGET_STATUSES = {
    "proposed-target-membership-club-awaiting-capacity-source",
    "retain-baseline-target-membership-awaiting-capacity-source",
    "retain-declared-target-club-needs-capacity-source",
}


class SourceTailPackageError(ValueError):
    """One source input cannot form a safe, complete package."""


@dataclass(frozen=True)
class CaptureInput:
    name: str
    route: str
    value: Mapping[str, Any]
    sha256: str


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _read(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourceTailPackageError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != canonical_bytes(value):
        raise SourceTailPackageError(f"{label} must be canonical JSON")
    return value, hashlib.sha256(raw).hexdigest()


def _target(assignment: Mapping[str, Any]) -> Mapping[str, Any]:
    target = assignment.get("proposed_target") or assignment.get("target_membership")
    if not isinstance(target, Mapping) or not all(
        isinstance(target.get(key), str) and target[key].strip()
        for key in ("name", "article_title", "article_path")
    ):
        raise SourceTailPackageError("target-membership assignment has an incomplete club identity")
    return target


def _expected_carriers(plan: Mapping[str, Any]) -> dict[int, dict[str, Any]]:
    if plan.get("schema_version") != PLAN_SCHEMA or not isinstance(plan.get("assignments"), list):
        raise SourceTailPackageError("source-tail plan has an unsupported schema or no assignments")
    result: dict[int, dict[str, Any]] = {}
    for assignment in plan["assignments"]:
        if not isinstance(assignment, Mapping) or assignment.get("status") not in TARGET_STATUSES:
            continue
        carrier_id, capacity = assignment.get("carrier_id"), assignment.get("fixed_roster_slot_count")
        if not isinstance(carrier_id, int) or carrier_id <= 0 or not isinstance(capacity, int) or capacity < 11:
            raise SourceTailPackageError("target-membership assignment has an invalid carrier or capacity")
        if carrier_id in result:
            raise SourceTailPackageError(f"source-tail plan duplicates carrier {carrier_id}")
        result[carrier_id] = {
            "capacity": capacity,
            "country_catalog": assignment.get("family"),
            "status": assignment.get("status"),
            "target": dict(_target(assignment)),
        }
    if not result:
        raise SourceTailPackageError("source-tail plan has no source-eligible carrier")
    return result


def _plan_sha(capture: Mapping[str, Any], *, schema: str) -> str:
    if capture.get("schema_version") != schema:
        raise SourceTailPackageError(f"source capture must have schema {schema}")
    source = capture.get("sources") if schema == PINNED_SCHEMA else capture.get("source")
    field = "source_tail_plan_sha256" if schema == PINNED_SCHEMA else "tail_plan_sha256"
    value = source.get(field) if isinstance(source, Mapping) else None
    if not isinstance(value, str) or len(value) != 64:
        raise SourceTailPackageError(f"{schema} capture lacks its source-tail plan hash")
    return value


def _capture_clubs(capture: CaptureInput) -> list[dict[str, Any]]:
    schema = capture.value.get("schema_version")
    if schema == GRANITAS_SCHEMA:
        club = capture.value.get("club")
        if not isinstance(club, Mapping):
            raise SourceTailPackageError("Granitas exception capture has no club")
        return [dict(club)]
    clubs = capture.value.get("clubs")
    if not isinstance(clubs, list) or not clubs:
        raise SourceTailPackageError(f"{capture.name} has no clubs")
    if not all(isinstance(club, Mapping) for club in clubs):
        raise SourceTailPackageError(f"{capture.name} has a malformed club")
    return [dict(club) for club in clubs]


def _validate_club(
    *, club: Mapping[str, Any], expected: Mapping[str, Any], capture: CaptureInput
) -> None:
    carrier_id = club.get("candidate_carrier_id")
    if not isinstance(carrier_id, int):
        raise SourceTailPackageError(f"{capture.name} has a club without a carrier id")
    target = expected["target"]
    if club.get("fixed_roster_slot_count") != expected["capacity"]:
        raise SourceTailPackageError(f"carrier {carrier_id} has a changed fixed capacity")
    for field in ("country_catalog", "club_name", "target_article_title", "target_article_path"):
        expected_value = expected["country_catalog"] if field == "country_catalog" else target[
            {"club_name": "name", "target_article_title": "article_title", "target_article_path": "article_path"}[field]
        ]
        if club.get(field) != expected_value:
            raise SourceTailPackageError(f"carrier {carrier_id} source identity disagrees at {field}")
    players = club.get("players")
    if not isinstance(players, list) or len(players) < int(expected["capacity"]):
        raise SourceTailPackageError(f"carrier {carrier_id} does not meet immutable roster capacity")
    for player in players:
        if not isinstance(player, Mapping):
            raise SourceTailPackageError(f"carrier {carrier_id} has a malformed player")
        if not isinstance(player.get("name"), str) or not player["name"].strip():
            raise SourceTailPackageError(f"carrier {carrier_id} has a player without a name")
        if not isinstance(player.get("nationality"), str) or player["nationality"] in {"", "UNK", "XXX"}:
            raise SourceTailPackageError(f"carrier {carrier_id} has an unresolved nationality")
        if player.get("position") not in {"G", "D", "M", "F"}:
            raise SourceTailPackageError(f"carrier {carrier_id} has an unresolved broad position")
        if not isinstance(player.get("unresolved_fields"), list):
            raise SourceTailPackageError(f"carrier {carrier_id} has no unresolved-field ledger")


def compose(*, plan: Mapping[str, Any], plan_sha256: str, captures: Sequence[CaptureInput]) -> dict[str, Any]:
    """Return one hash-bound package after complete, non-overlapping coverage checks."""

    expected = _expected_carriers(plan)
    by_schema = {str(capture.value.get("schema_version")): capture for capture in captures}
    required_schemas = {PINNED_SCHEMA, OPENING_SCHEMA, GRANITAS_SCHEMA}
    if set(by_schema) != required_schemas or len(captures) != len(by_schema):
        raise SourceTailPackageError("package needs one each of pinned, opening-window and Granitas captures")
    pinned, opening, granitas = (
        by_schema[PINNED_SCHEMA], by_schema[OPENING_SCHEMA], by_schema[GRANITAS_SCHEMA],
    )
    for capture, schema in ((pinned, PINNED_SCHEMA), (opening, OPENING_SCHEMA), (granitas, GRANITAS_SCHEMA)):
        if _plan_sha(capture.value, schema=schema) != plan_sha256:
            raise SourceTailPackageError(f"{capture.name} is not bound to this exact tail plan")
    opening_source = opening.value.get("source")
    if not isinstance(opening_source, Mapping) or opening_source.get("tail_squad_receipt_sha256") != pinned.sha256:
        raise SourceTailPackageError("opening-window capture is not bound to the pinned-squad receipt")

    clubs: list[dict[str, Any]] = []
    seen: set[int] = set()
    for capture in captures:
        for club in _capture_clubs(capture):
            carrier_id = club.get("candidate_carrier_id")
            if not isinstance(carrier_id, int) or carrier_id not in expected:
                raise SourceTailPackageError(f"{capture.name} supplies an unexpected carrier {carrier_id!r}")
            if carrier_id in seen:
                raise SourceTailPackageError(f"source captures overlap on carrier {carrier_id}")
            _validate_club(club=club, expected=expected[carrier_id], capture=capture)
            selection_status = (
                "opening-window-ordered-capacity-roster"
                if capture.route in {"opening-window", "official-opening-window-exception"}
                else "capacity-safe-season-roster-awaiting-explicit-opening-order"
            )
            clubs.append({
                **club,
                "source_package": {
                    "capture_name": capture.name,
                    "capture_sha256": capture.sha256,
                    "route": capture.route,
                    "roster_selection_status": selection_status,
                },
            })
            seen.add(carrier_id)
    missing = sorted(set(expected) - seen)
    if missing:
        raise SourceTailPackageError(f"source package is missing planned carriers {missing}")
    clubs.sort(key=lambda club: int(club["candidate_carrier_id"]))
    unresolved = Counter(
        field for club in clubs for player in club["players"] for field in player["unresolved_fields"]
    )
    source_metadata = []
    for capture in sorted(captures, key=lambda item: item.name):
        source = capture.value.get("source") or capture.value.get("sources")
        source_metadata.append({
            "capture_name": capture.name,
            "capture_sha256": capture.sha256,
            "route": capture.route,
            "schema_version": capture.value["schema_version"],
            "source_repository": source.get("repository") if isinstance(source, Mapping) else None,
            "source_title": source.get("title") if isinstance(source, Mapping) else None,
        })
    routes = Counter(club["source_package"]["route"] for club in clubs)
    selection = Counter(club["source_package"]["roster_selection_status"] for club in clubs)
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only composition; complete one-to-one carrier coverage; all country and broad-position "
            "facts must be published; secondary missing facts remain logged; no PM99 database write and no "
            "implicit truncation of an unranked season roster"
        ),
        "sources": {
            "source_tail_plan_sha256": plan_sha256,
            "captures": source_metadata,
        },
        "clubs": clubs,
        "summary": {
            "planned_carrier_count": len(expected),
            "covered_carrier_count": len(clubs),
            "source_candidate_player_count": sum(len(club["players"]) for club in clubs),
            "source_route_counts": dict(sorted(routes.items())),
            "roster_selection_status_counts": dict(sorted(selection.items())),
            "unresolved_secondary_field_counts": dict(sorted(unresolved.items())),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--pinned-squads", required=True, type=Path)
    parser.add_argument("--opening-squads", required=True, type=Path)
    parser.add_argument("--granitas-squad", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"refusing to overwrite source package: {args.output}")
    try:
        plan, plan_sha = _read(args.plan, label="source-tail plan")
        inputs = []
        for name, route, path in (
            ("pinned-historic-squads", "pinned-historic-season-squad", args.pinned_squads),
            ("opening-window-supplements", "opening-window", args.opening_squads),
            ("granitas-official-opening-window", "official-opening-window-exception", args.granitas_squad),
        ):
            value, digest = _read(path, label=name)
            inputs.append(CaptureInput(name=name, route=route, value=value, sha256=digest))
        result = compose(plan=plan, plan_sha256=plan_sha, captures=inputs)
    except (OSError, SourceTailPackageError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
