#!/usr/bin/env python3
"""Normalise one dated squad capture into a hash-bound all-carrier intake.

This is a source-only authoring step.  It joins three existing, independently
validated inputs:

* a FootballSquads season capture (dated club/player source facts),
* the immutable PM99 foreign fixed-carrier registry, and
* the reviewed/candidate carrier assignment ledger.

The resulting intake deliberately contains neither inferred PM99 facts nor a
database writer.  It lists every fixed carrier, preserves missing source facts
as ``null`` plus their original ``unresolved_fields``, and keeps a selected
source club as a reference to the captured source rows rather than pretending
that its players have already been allocated to PM99 slots.

It is intentionally upstream of ``pm99-season-package-v2``.  A strict package
may only be promoted after editorial identities, carrier/slot bindings,
ratings, managers, assets and opening-fixture facts have been supplied.

Examples:

    python3 scripts/season_source_intake_v1.py build \
      --registry seasons/2000-01/fixed-carrier-registry.json \
      --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
      --assignment seasons/2000-01/foreign-carrier-assignment.json \
      --intake-id world-2000-01-source-intake \
      --output seasons/2000-01/source-intake.json

    python3 scripts/season_source_intake_v1.py audit \
      --registry seasons/2000-01/fixed-carrier-registry.json \
      --source-capture seasons/2000-01/sources/footballsquads-2000-01.json \
      --assignment seasons/2000-01/foreign-carrier-assignment.json \
      --intake seasons/2000-01/source-intake.json \
      --output seasons/2000-01/source-intake-audit.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignment_lib  # noqa: E402
from scripts import season_player_identity_v1 as identity_lib  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as registry_lib  # noqa: E402


SCHEMA = "pm99-season-source-intake-v1"
AUDIT_SCHEMA = "pm99-season-source-intake-audit-v1"
SOURCE_SCHEMA = assignment_lib.SOURCE_SCHEMA
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PLAYER_FIELDS = {
    "shirt_number",
    "name",
    "nationality",
    "position",
    "height_cm",
    "weight_kg",
    "birth_date",
    "unresolved_fields",
}
# Optional provider-scoped identity.  Absent means unknown; it is neither a
# null placeholder nor an unresolved fact, so legacy captures stay valid.
_OPTIONAL_PLAYER_FIELDS = {identity_lib.IDENTITY_FIELD}
_CLUB_FIELDS = {
    "country_catalog",
    "competition_catalog",
    "club_name",
    "competition_name",
    "source_path",
    "source_sha256",
    "players",
}
_SELECTOR_FIELDS = {
    "country_catalog",
    "competition_catalog",
    "club_name",
    "source_path",
    "source_sha256",
}


class SourceIntakeError(ValueError):
    """The intake is stale, malformed, or claims facts not in its sources."""


def canonical_json_bytes(value: Any) -> bytes:
    return assignment_lib.canonical_json_bytes(value)


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise SourceIntakeError(f"{label} must be a stable lower-case id")
    return value


def _require_text(value: Any, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise SourceIntakeError(f"{label} must be a non-blank string of at most {maximum} characters")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise SourceIntakeError(f"{label} must be a lowercase SHA-256")
    return value


def _selector(club: Mapping[str, Any]) -> dict[str, str]:
    """Return the exact selector shape owned by foreign-carrier-assignment-v1."""

    return {
        "country_catalog": str(club["country_catalog"]),
        "competition_catalog": str(club["competition_catalog"]),
        "club_name": str(club["club_name"]),
        "source_path": str(club["source_path"]),
        "source_sha256": str(club["source_sha256"]),
    }


def _selector_key(selector: Mapping[str, Any], *, label: str) -> tuple[str, str, str, str, str]:
    if set(selector) != _SELECTOR_FIELDS:
        raise SourceIntakeError(f"{label} must contain exactly the canonical source selector fields")
    return (
        _require_text(selector.get("country_catalog"), f"{label}.country_catalog"),
        _require_text(selector.get("competition_catalog"), f"{label}.competition_catalog"),
        _require_text(selector.get("club_name"), f"{label}.club_name"),
        _require_text(selector.get("source_path"), f"{label}.source_path"),
        _require_sha256(selector.get("source_sha256"), f"{label}.source_sha256"),
    )


def _validate_player(player: Any, *, label: str) -> dict[str, Any]:
    """Validate the capture's explicit known/unknown fact representation.

    This intentionally does not resolve a missing value.  The source capture
    owns whether a fact is known; this normaliser only makes that state durable
    and auditable in a carrier-oriented work queue.
    """

    if (
        not isinstance(player, dict)
        or not _PLAYER_FIELDS <= set(player)
        or set(player) - _PLAYER_FIELDS - _OPTIONAL_PLAYER_FIELDS
    ):
        raise SourceIntakeError(f"{label} has unsupported player fields")
    if identity_lib.IDENTITY_FIELD in player:
        try:
            identity_lib.validate_source_identity(player[identity_lib.IDENTITY_FIELD], label=f"{label}.source_identity")
        except identity_lib.IdentityError as exc:
            raise SourceIntakeError(str(exc)) from exc
    _require_text(player.get("name"), f"{label}.name", maximum=255)
    unresolved = player.get("unresolved_fields")
    # ``position`` is the capture's column-shaped field while
    # ``primary_position`` is the PM99-facing name intentionally used in its
    # gap ledger.  Preserve that source vocabulary exactly rather than
    # normalising a missing value into a different editorial assertion.
    fact_gap_names = {
        "shirt_number": "shirt_number",
        "nationality": "nationality",
        "position": "primary_position",
        "height_cm": "height_cm",
        "weight_kg": "weight_kg",
        "birth_date": "birth_date",
    }
    if (
        not isinstance(unresolved, list)
        or len(unresolved) != len(set(unresolved))
        or any(not isinstance(item, str) or item not in set(fact_gap_names.values()) for item in unresolved)
    ):
        raise SourceIntakeError(f"{label}.unresolved_fields must be a unique list of known fact names")
    for key, gap_name in fact_gap_names.items():
        value = player.get(key)
        if value is None:
            if gap_name not in unresolved:
                raise SourceIntakeError(f"{label}.{key} is null but not declared unresolved")
        elif gap_name in unresolved:
            raise SourceIntakeError(f"{label}.{key} is known but incorrectly declared unresolved")
    if player["shirt_number"] is not None and (
        not isinstance(player["shirt_number"], int) or not 1 <= player["shirt_number"] <= 99
    ):
        raise SourceIntakeError(f"{label}.shirt_number is invalid")
    if player["nationality"] is not None and (
        not isinstance(player["nationality"], str) or not re.fullmatch(r"[A-Z]{3}", player["nationality"])
    ):
        raise SourceIntakeError(f"{label}.nationality is invalid")
    if player["position"] is not None and player["position"] not in {"G", "D", "M", "F"}:
        raise SourceIntakeError(f"{label}.position is invalid")
    if player["height_cm"] is not None and (
        not isinstance(player["height_cm"], int) or not 120 <= player["height_cm"] <= 230
    ):
        raise SourceIntakeError(f"{label}.height_cm is invalid")
    if player["weight_kg"] is not None and (
        not isinstance(player["weight_kg"], int) or not 40 <= player["weight_kg"] <= 140
    ):
        raise SourceIntakeError(f"{label}.weight_kg is invalid")
    if player["birth_date"] is not None and (
        not isinstance(player["birth_date"], str) or not re.fullmatch(r"(?:19|20)\d{2}-\d{2}-\d{2}", player["birth_date"])
    ):
        raise SourceIntakeError(f"{label}.birth_date is invalid")
    return dict(player)


def _normalise_source_clubs(source_capture: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return all captured source rows with row hashes, in capture order.

    The row hash is an immutable reference for a future editorial overlay.  It
    identifies the exact source row without asserting a real-world identity or
    a PM99 carrier binding.
    """

    if source_capture.get("schema_version") != SOURCE_SCHEMA:
        raise SourceIntakeError(f"source capture schema_version must be {SOURCE_SCHEMA!r}")
    season = source_capture.get("season")
    if not isinstance(season, dict) or set(season) != {"catalog", "label"}:
        raise SourceIntakeError("source capture season is malformed")
    _require_text(season.get("catalog"), "source capture season.catalog")
    _require_text(season.get("label"), "source capture season.label")
    source = source_capture.get("source")
    if not isinstance(source, dict):
        raise SourceIntakeError("source capture source metadata is malformed")
    clubs = source_capture.get("clubs")
    if not isinstance(clubs, list) or not clubs:
        raise SourceIntakeError("source capture clubs must be a non-empty list")
    output: list[dict[str, Any]] = []
    seen_selectors: set[tuple[str, str, str, str, str]] = set()
    previous_sort: tuple[str, str, str] | None = None
    for club_index, club in enumerate(clubs):
        if not isinstance(club, dict) or set(club) != _CLUB_FIELDS:
            raise SourceIntakeError(f"source capture club {club_index} has unsupported fields")
        selector = _selector(club)
        selector_key = _selector_key(selector, label=f"source capture club {club_index}.selector")
        if selector_key in seen_selectors:
            raise SourceIntakeError("source capture duplicates a source club selector")
        seen_selectors.add(selector_key)
        sort_key = selector_key[:3]
        if previous_sort is not None and sort_key < previous_sort:
            raise SourceIntakeError("source capture clubs must be sorted by country, competition and club")
        previous_sort = sort_key
        _require_text(club.get("competition_name"), f"source capture club {club_index}.competition_name")
        players = club.get("players")
        if not isinstance(players, list) or not players:
            raise SourceIntakeError(f"source capture club {club_index} must contain players")
        rows = []
        club_identities: set[tuple[str, str]] = set()
        for row_index, player in enumerate(players):
            facts = _validate_player(player, label=f"source capture club {club_index} player {row_index}")
            if identity_lib.IDENTITY_FIELD in facts:
                key = identity_lib.identity_key(facts[identity_lib.IDENTITY_FIELD])
                if key in club_identities:
                    raise SourceIntakeError(
                        f"source capture club {club_index} repeats {key[0]} player {key[1]}"
                    )
                club_identities.add(key)
            rows.append(
                {
                    "source_row_index": row_index,
                    "source_row_sha256": _sha256(facts),
                    "facts": facts,
                }
            )
        output.append(
            {
                "selector": selector,
                "competition_name": str(club["competition_name"]),
                "players": rows,
            }
        )
    return output


def build_intake(
    *,
    registry: Mapping[str, Any],
    source_capture: Mapping[str, Any],
    assignment: Mapping[str, Any],
    intake_id: str,
) -> dict[str, Any]:
    """Build one exact, non-writing intake from the three locked inputs."""

    registry_lib.validate_registry(registry)
    assignment_lib.validate_assignment(
        assignment=assignment,
        registry=registry,
        source_capture=source_capture,
    )
    _require_id(intake_id, "intake_id")
    source_clubs = _normalise_source_clubs(source_capture)
    source_by_selector = {
        _selector_key(row["selector"], label="normalised source club selector"): row
        for row in source_clubs
    }
    assignment_by_carrier = {
        int(row["carrier_id"]): dict(row)
        for row in assignment["assignments"]
    }
    carriers: list[dict[str, Any]] = []
    for carrier in registry["carriers"]:
        carrier_id = int(carrier["carrier_id"])
        assignment_row = assignment_by_carrier.get(carrier_id)
        if assignment_row is None:
            assignment_disposition: dict[str, Any] = {"status": "unassigned"}
            selection = None
        else:
            # The assignment validator has already established that this exact
            # selector exists in the capture.  Retain its candidate/approved/
            # blocked status; do not upgrade it at intake time.
            assignment_disposition = assignment_row
            selection = source_by_selector[_selector_key(
                assignment_row["source_selector"], label=f"carrier {carrier_id} source_selector"
            )]
        source_player_count = len(selection["players"]) if selection is not None else 0
        fixed_slot_count = len(carrier["roster_slots"])
        carriers.append(
            {
                "carrier_id": carrier_id,
                "fixed_roster_slot_count": fixed_slot_count,
                "assignment": assignment_disposition,
                "selected_source_player_count": source_player_count,
                "source_capacity": (
                    "not-selected"
                    if selection is None
                    else "meets-fixed-carrier-capacity"
                    if source_player_count >= fixed_slot_count
                    else "below-fixed-carrier-capacity"
                ),
            }
        )
    return {
        "schema_version": SCHEMA,
        "intake_id": intake_id,
        "season": dict(source_capture["season"]),
        "source": dict(source_capture["source"]),
        "registry_sha256": _sha256(registry),
        "source_capture_sha256": _sha256(source_capture),
        "assignment_sha256": _sha256(assignment),
        "topology_policy": "preserve-existing-carriers-no-membership-write",
        "source_clubs": source_clubs,
        "carriers": carriers,
    }


def validate_intake(
    *,
    intake: Mapping[str, Any],
    registry: Mapping[str, Any],
    source_capture: Mapping[str, Any],
    assignment: Mapping[str, Any],
) -> None:
    """Verify an intake exactly matches the content-addressed inputs.

    Rebuilding the expected document makes the contract deliberately narrow:
    no consumer can sneak an unsourced edit into an intake.  Editorial changes
    must happen in a later, explicit overlay rather than this raw source lane.
    """

    if intake.get("schema_version") != SCHEMA:
        raise SourceIntakeError(f"source intake schema_version must be {SCHEMA!r}")
    intake_id = _require_id(intake.get("intake_id"), "intake_id")
    expected = build_intake(
        registry=registry,
        source_capture=source_capture,
        assignment=assignment,
        intake_id=intake_id,
    )
    if dict(intake) != expected:
        raise SourceIntakeError("source intake does not exactly match its hash-locked inputs")


def audit_intake(
    *,
    intake: Mapping[str, Any],
    registry: Mapping[str, Any],
    source_capture: Mapping[str, Any],
    assignment: Mapping[str, Any],
) -> dict[str, Any]:
    """Return deterministic coverage and release-boundary information."""

    validate_intake(
        intake=intake,
        registry=registry,
        source_capture=source_capture,
        assignment=assignment,
    )
    source_clubs = intake["source_clubs"]
    source_by_selector = {
        _selector_key(row["selector"], label="intake source club selector"): row
        for row in source_clubs
    }
    carrier_rows = intake["carriers"]
    status_counts = Counter(str(row["assignment"]["status"]) for row in carrier_rows)
    capacity_counts = Counter(str(row["source_capacity"]) for row in carrier_rows)
    selected_selectors = {
        _selector_key(row["assignment"]["source_selector"], label=f"intake carrier {row['carrier_id']} selector")
        for row in carrier_rows
        if row["assignment"]["status"] != "unassigned"
    }
    selected_source_clubs = [source_by_selector[selector] for selector in sorted(selected_selectors)]
    all_player_rows = [
        player
        for club in source_clubs
        for player in club["players"]
    ]
    selected_player_rows = [
        player
        for club in selected_source_clubs
        for player in club["players"]
    ]
    unresolved_by_field = Counter(
        field
        for player in all_player_rows
        for field in player["facts"]["unresolved_fields"]
    )
    selected_unresolved_by_field = Counter(
        field
        for player in selected_player_rows
        for field in player["facts"]["unresolved_fields"]
    )
    identified_count = sum(identity_lib.IDENTITY_FIELD in player["facts"] for player in all_player_rows)
    approved_count = status_counts["approved"]
    non_approved_count = len(carrier_rows) - approved_count
    selected_count = len(selected_selectors)
    blockers: list[dict[str, Any]] = []
    if non_approved_count:
        blockers.append(
            {
                "code": "fixed-carrier-identities-not-approved",
                "carrier_count": non_approved_count,
                "message": "Candidate, blocked and unassigned carrier rows are source-intake records, not approved historical PM99 identities.",
            }
        )
    if capacity_counts["below-fixed-carrier-capacity"]:
        blockers.append(
            {
                "code": "selected-source-below-fixed-carrier-capacity",
                "carrier_count": capacity_counts["below-fixed-carrier-capacity"],
                "message": "A selected dated squad has fewer rows than its immutable PM99 carrier slots; no slot allocation may be inferred.",
            }
        )
    if unresolved_by_field:
        blockers.append(
            {
                "code": "dated-source-facts-unresolved",
                "player_row_count": sum(1 for row in all_player_rows if row["facts"]["unresolved_fields"]),
                "fields": dict(sorted(unresolved_by_field.items())),
                "message": "Source gaps remain explicit and need evidence-backed editorial resolution before a strict package can write those fields.",
            }
        )
    if selected_count != len(source_clubs):
        blockers.append(
            {
                "code": "captured-clubs-not-selected-for-fixed-carriers",
                "club_count": len(source_clubs) - selected_count,
                "message": "Captured club squads are retained as evidence but have no fixed-carrier selection in this intake.",
            }
        )
    blockers.append(
        {
            "code": "source-intake-is-not-a-package-or-database-build",
            "message": "This intake has no player-slot bindings, managers, ratings, opening fixtures, kits, portraits, PM99 writes or runtime qualification.",
        }
    )
    audit = {
        "schema_version": AUDIT_SCHEMA,
        "intake_id": intake["intake_id"],
        "intake_sha256": _sha256(intake),
        "season": dict(intake["season"]),
        "registry_sha256": intake["registry_sha256"],
        "source_capture_sha256": intake["source_capture_sha256"],
        "assignment_sha256": intake["assignment_sha256"],
        "coverage": {
            "fixed_carrier_count": len(carrier_rows),
            "fixed_roster_slot_count": sum(int(row["fixed_roster_slot_count"]) for row in carrier_rows),
            "assignment_status_counts": dict(sorted(status_counts.items())),
            "source_capacity_counts": dict(sorted(capacity_counts.items())),
            "source_club_count": len(source_clubs),
            "source_player_row_count": len(all_player_rows),
            "source_player_rows_with_unresolved_facts": sum(
                1 for row in all_player_rows if row["facts"]["unresolved_fields"]
            ),
            "unresolved_fact_counts": dict(sorted(unresolved_by_field.items())),
            "selected_source_club_count": selected_count,
            "selected_source_player_row_count": len(selected_player_rows),
            "selected_source_player_rows_with_unresolved_facts": sum(
                1 for row in selected_player_rows if row["facts"]["unresolved_fields"]
            ),
            "selected_unresolved_fact_counts": dict(sorted(selected_unresolved_by_field.items())),
        },
        "blockers": blockers,
        "scope_exclusions": [
            "No country, division, draw-pool, competition membership or foreign topology is inferred or written.",
            "No captured player row is treated as a reconciled person, a PM99 player carrier or a roster-slot allocation.",
            "No generated game tree, FDI, PKF or EXE is read or written by this source-only intake stage.",
        ],
    }
    if identified_count:
        audit["coverage"]["source_player_rows_with_provider_identity"] = identified_count
    return audit


def _read(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value, _ = assignment_lib.read_canonical_json(path, label=label)
    except assignment_lib.AssignmentError as exc:
        raise SourceIntakeError(str(exc)) from exc
    return value


def _load_inputs(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        _read(args.registry, label="fixed-carrier registry"),
        _read(args.source_capture, label="historic squad capture"),
        _read(args.assignment, label="foreign carrier assignment"),
    )


def _command_build(args: argparse.Namespace) -> int:
    registry, source_capture, assignment = _load_inputs(args)
    intake = build_intake(
        registry=registry,
        source_capture=source_capture,
        assignment=assignment,
        intake_id=args.intake_id,
    )
    assignment_lib.write_canonical_json(args.output, intake)
    print(json.dumps(audit_intake(
        intake=intake,
        registry=registry,
        source_capture=source_capture,
        assignment=assignment,
    )["coverage"], sort_keys=True))
    return 0


def _command_validate(args: argparse.Namespace) -> int:
    registry, source_capture, assignment = _load_inputs(args)
    intake = _read(args.intake, label="season source intake")
    validate_intake(
        intake=intake,
        registry=registry,
        source_capture=source_capture,
        assignment=assignment,
    )
    print("season source intake validation passed")
    return 0


def _command_audit(args: argparse.Namespace) -> int:
    registry, source_capture, assignment = _load_inputs(args)
    intake = _read(args.intake, label="season source intake")
    audit = audit_intake(
        intake=intake,
        registry=registry,
        source_capture=source_capture,
        assignment=assignment,
    )
    assignment_lib.write_canonical_json(args.output, audit)
    print(json.dumps(audit["coverage"], sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "validate", "audit"):
        child = sub.add_parser(command)
        child.add_argument("--registry", type=Path, required=True)
        child.add_argument("--source-capture", type=Path, required=True)
        child.add_argument("--assignment", type=Path, required=True)
        if command == "build":
            child.add_argument("--intake-id", required=True)
            child.add_argument("--output", type=Path, required=True)
            child.set_defaults(handler=_command_build)
        elif command == "validate":
            child.add_argument("--intake", type=Path, required=True)
            child.set_defaults(handler=_command_validate)
        else:
            child.add_argument("--intake", type=Path, required=True)
            child.add_argument("--output", type=Path, required=True)
            child.set_defaults(handler=_command_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (SourceIntakeError, assignment_lib.AssignmentError, registry_lib.WorldLedgerError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
