#!/usr/bin/env python3
"""Author and audit fixed PM99 carrier-to-season-club assignments.

This is deliberately the narrow bridge between two independently auditable
facts:

* a PM99 foreign carrier is visibly offered by a particular *host country* in
  the preseason picker; and
* a historical squad source contains a club from that same country.

It never writes PM99 files, derives a division from record numbers, or calls a
source competition catalogue a PM99 league.  It exists so the full 2015/16
world update can be built from reviewable assignments rather than an opaque
one-off bulk replacement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import world_fixed_carrier_ledger_v2 as registry_lib  # noqa: E402


SCHEMA = "pm99-foreign-carrier-assignment-v1"
AUDIT_SCHEMA = "pm99-foreign-carrier-assignment-audit-v1"
SOURCE_SCHEMA = "pm99-footballsquads-season-capture-v1"
HOST_REPORT_SCHEMA = "pm99-foreign-host-mapping-report-v1"
PROPOSAL_SCHEMA = "pm99-foreign-carrier-assignment-proposal-v1"
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AssignmentError(ValueError):
    """An assignment is incomplete, stale, or attempts to widen PM99 scope."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_canonical_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssignmentError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict) or raw != canonical_json_bytes(payload):
        raise AssignmentError(f"{label} must be canonical JSON")
    return payload, hashlib.sha256(raw).hexdigest()


def read_json_document(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    """Read reviewed evidence without imposing a presentation encoding.

    Runner host-mapping reports are deliberately human-readable pretty JSON;
    their raw-byte digest is the evidence lock. Season sources and assignment
    manifests, by contrast, are canonical so they can be merged reproducibly.
    """

    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AssignmentError(f"cannot read {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise AssignmentError(f"{label} root must be a JSON object")
    return payload, hashlib.sha256(raw).hexdigest()


def write_canonical_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(dict(value)))


def _normalise_country(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(character.casefold() for character in text if character.isalnum())


def _require_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise AssignmentError(f"{label} must be a stable lower-case id")
    return value


def _require_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise AssignmentError(f"{label} must be a lowercase SHA-256")
    return value


def _require_text(value: Any, label: str, *, maximum: int = 300) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise AssignmentError(f"{label} must be a non-blank string of at most {maximum} characters")
    return value.strip()


def _source_clubs(capture: Mapping[str, Any]) -> dict[tuple[str, str, str, str, str], dict[str, Any]]:
    if capture.get("schema_version") != SOURCE_SCHEMA:
        raise AssignmentError(f"source capture schema must be {SOURCE_SCHEMA!r}")
    clubs = capture.get("clubs")
    if not isinstance(clubs, list) or not clubs:
        raise AssignmentError("source capture clubs must be a non-empty list")
    result: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for index, club in enumerate(clubs):
        if not isinstance(club, dict) or set(club) != {
            "country_catalog", "competition_catalog", "club_name", "competition_name", "source_path", "source_sha256", "players"
        }:
            raise AssignmentError(f"source capture club {index} is malformed")
        key = (
            _require_text(club.get("country_catalog"), f"source club {index}.country_catalog"),
            _require_text(club.get("competition_catalog"), f"source club {index}.competition_catalog"),
            _require_text(club.get("club_name"), f"source club {index}.club_name"),
            _require_text(club.get("source_path"), f"source club {index}.source_path"),
            _require_sha256(club.get("source_sha256"), f"source club {index}.source_sha256"),
        )
        if key in result:
            raise AssignmentError(f"source capture duplicates club selector {key!r}")
        players = club.get("players")
        if not isinstance(players, list) or not players:
            raise AssignmentError(f"source club {index} has no players")
        result[key] = dict(club)
    return result


def _host_evidence(
    *, registry: Mapping[str, Any], host_reports: list[tuple[Mapping[str, Any], str]]
) -> list[dict[str, Any]]:
    registry_lib.validate_registry(registry)
    base_hash = str(registry["baseline"]["database_files"]["EQ98030.FDI"]["sha256"])
    carrier_ids = {int(item["carrier_id"]) for item in registry["carriers"]}
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    for report, report_sha in host_reports:
        if report.get("schema") != HOST_REPORT_SCHEMA or report.get("read_only") is not True:
            raise AssignmentError("host mapping input is not a reviewed read-only host report")
        base = report.get("base")
        if not isinstance(base, dict) or base.get("eq98030_sha256") != base_hash:
            raise AssignmentError("host mapping report is bound to a different base EQ file")
        capture_id = _require_text(report.get("capture_id"), "host mapping capture_id")
        mappings = report.get("accepted_host_mappings")
        if not isinstance(mappings, list):
            raise AssignmentError("host mapping report accepted_host_mappings must be a list")
        for item in mappings:
            if not isinstance(item, dict):
                raise AssignmentError("host mapping entry must be an object")
            carrier_id = item.get("eq_record_id")
            if not isinstance(carrier_id, int) or carrier_id not in carrier_ids:
                raise AssignmentError("host mapping entry names an unknown fixed carrier")
            if carrier_id in seen:
                raise AssignmentError(f"carrier {carrier_id} appears in more than one host mapping report")
            seen.add(carrier_id)
            evidence = item.get("evidence")
            if not isinstance(evidence, dict):
                raise AssignmentError(f"host mapping evidence for carrier {carrier_id} is missing")
            rows.append(
                {
                    "carrier_id": carrier_id,
                    "host_country": _require_text(item.get("host_country"), f"host mapping {carrier_id}.host_country"),
                    "capture_id": capture_id,
                    "report_sha256": report_sha,
                    "screenshot_sha256": _require_sha256(evidence.get("sha256"), f"host mapping {carrier_id}.screenshot_sha256"),
                }
            )
    return sorted(rows, key=lambda row: int(row["carrier_id"]))


def initialise_assignment(
    *, registry: Mapping[str, Any], source_capture: Mapping[str, Any], host_reports: list[tuple[Mapping[str, Any], str]], assignment_id: str
) -> dict[str, Any]:
    registry_lib.validate_registry(registry)
    _source_clubs(source_capture)
    _require_id(assignment_id, "assignment_id")
    return {
        "schema_version": SCHEMA,
        "assignment_id": assignment_id,
        "season_label": str(source_capture.get("season", {}).get("label") or ""),
        "registry_sha256": hashlib.sha256(canonical_json_bytes(dict(registry))).hexdigest(),
        "source_capture_sha256": hashlib.sha256(canonical_json_bytes(dict(source_capture))).hexdigest(),
        "topology_policy": "preserve-existing-carriers-no-membership-write",
        "host_mapping_evidence": _host_evidence(registry=registry, host_reports=host_reports),
        "assignments": [],
    }


def validate_assignment(
    *, assignment: Mapping[str, Any], registry: Mapping[str, Any], source_capture: Mapping[str, Any]
) -> None:
    registry_lib.validate_registry(registry)
    source_by_selector = _source_clubs(source_capture)
    expected_fields = {
        "schema_version", "assignment_id", "season_label", "registry_sha256", "source_capture_sha256",
        "topology_policy", "host_mapping_evidence", "assignments",
    }
    if set(assignment) != expected_fields:
        raise AssignmentError("assignment has unsupported fields")
    if assignment.get("schema_version") != SCHEMA:
        raise AssignmentError("assignment schema_version is unsupported")
    _require_id(assignment.get("assignment_id"), "assignment_id")
    source_season = source_capture.get("season")
    if not isinstance(source_season, dict) or assignment.get("season_label") != source_season.get("label"):
        raise AssignmentError("assignment season_label must match source capture")
    if assignment.get("registry_sha256") != hashlib.sha256(canonical_json_bytes(dict(registry))).hexdigest():
        raise AssignmentError("assignment is locked to a different fixed-carrier registry")
    if assignment.get("source_capture_sha256") != hashlib.sha256(canonical_json_bytes(dict(source_capture))).hexdigest():
        raise AssignmentError("assignment is locked to a different historic source capture")
    if assignment.get("topology_policy") != "preserve-existing-carriers-no-membership-write":
        raise AssignmentError("assignment must preserve fixed PM99 topology")

    carrier_slots = {int(item["carrier_id"]): len(item["roster_slots"]) for item in registry["carriers"]}
    host_rows = assignment.get("host_mapping_evidence")
    if not isinstance(host_rows, list):
        raise AssignmentError("host_mapping_evidence must be a list")
    host_by_carrier: dict[int, dict[str, Any]] = {}
    previous_host = 0
    for row in host_rows:
        if not isinstance(row, dict) or set(row) != {"carrier_id", "host_country", "capture_id", "report_sha256", "screenshot_sha256"}:
            raise AssignmentError("host mapping evidence has unsupported fields")
        carrier_id = row.get("carrier_id")
        if not isinstance(carrier_id, int) or carrier_id <= previous_host or carrier_id not in carrier_slots:
            raise AssignmentError("host mapping evidence must be fixed-carrier sorted and unique")
        previous_host = carrier_id
        host_by_carrier[carrier_id] = row
        _require_text(row.get("host_country"), f"host mapping {carrier_id}.host_country")
        _require_text(row.get("capture_id"), f"host mapping {carrier_id}.capture_id")
        _require_sha256(row.get("report_sha256"), f"host mapping {carrier_id}.report_sha256")
        _require_sha256(row.get("screenshot_sha256"), f"host mapping {carrier_id}.screenshot_sha256")

    rows = assignment.get("assignments")
    if not isinstance(rows, list):
        raise AssignmentError("assignments must be a list")
    seen_carriers: set[int] = set()
    seen_source_selectors: set[tuple[str, str, str, str, str]] = set()
    previous = 0
    for row in rows:
        expected = {"carrier_id", "status", "historical_club", "source_selector", "blockers"}
        if not isinstance(row, dict) or set(row) != expected:
            raise AssignmentError("assignment row has unsupported fields")
        carrier_id = row.get("carrier_id")
        if not isinstance(carrier_id, int) or carrier_id <= previous or carrier_id not in carrier_slots:
            raise AssignmentError("assignment carrier IDs must be existing, sorted and unique")
        previous = carrier_id
        seen_carriers.add(carrier_id)
        if row.get("status") not in {"candidate", "approved", "blocked"}:
            raise AssignmentError(f"carrier {carrier_id} has invalid assignment status")
        club = row.get("historical_club")
        if not isinstance(club, dict) or set(club) != {"identity_key", "name"}:
            raise AssignmentError(f"carrier {carrier_id} historical_club is invalid")
        _require_id(club.get("identity_key"), f"carrier {carrier_id} club identity_key")
        _require_text(club.get("name"), f"carrier {carrier_id} club name")
        selector = row.get("source_selector")
        if not isinstance(selector, dict) or set(selector) != {"country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256"}:
            raise AssignmentError(f"carrier {carrier_id} source_selector is invalid")
        selector_key = (
            _require_text(selector.get("country_catalog"), f"carrier {carrier_id} source country_catalog"),
            _require_text(selector.get("competition_catalog"), f"carrier {carrier_id} source competition_catalog"),
            _require_text(selector.get("club_name"), f"carrier {carrier_id} source club_name"),
            _require_text(selector.get("source_path"), f"carrier {carrier_id} source path"),
            _require_sha256(selector.get("source_sha256"), f"carrier {carrier_id} source sha256"),
        )
        source_club = source_by_selector.get(selector_key)
        if source_club is None:
            raise AssignmentError(f"carrier {carrier_id} source selector is not in the captured season")
        if selector_key in seen_source_selectors:
            raise AssignmentError(f"historical source club is assigned to more than one carrier: {selector_key[2]}")
        seen_source_selectors.add(selector_key)
        blockers = row.get("blockers")
        if not isinstance(blockers, list) or blockers != sorted(blockers) or any(not isinstance(item, str) or not item for item in blockers):
            raise AssignmentError(f"carrier {carrier_id} blockers must be a sorted string list")
        if row["status"] == "approved":
            host = host_by_carrier.get(carrier_id)
            if host is None:
                raise AssignmentError(f"approved carrier {carrier_id} has no reviewed host-country evidence")
            if _normalise_country(host["host_country"]) != _normalise_country(selector_key[0]):
                raise AssignmentError(f"approved carrier {carrier_id} assigns a source club from a different host country")
            if len(source_club["players"]) < carrier_slots[carrier_id]:
                raise AssignmentError(f"approved carrier {carrier_id} source roster is smaller than its fixed PM99 capacity")
            if blockers:
                raise AssignmentError(f"approved carrier {carrier_id} cannot retain blockers")
        elif row["status"] == "blocked" and not blockers:
            raise AssignmentError(f"blocked carrier {carrier_id} needs explicit blockers")


def audit_assignment(*, assignment: Mapping[str, Any], registry: Mapping[str, Any], source_capture: Mapping[str, Any]) -> dict[str, Any]:
    validate_assignment(assignment=assignment, registry=registry, source_capture=source_capture)
    assignment_rows = assignment["assignments"]
    all_ids = {int(item["carrier_id"]) for item in registry["carriers"]}
    assigned_ids = {int(item["carrier_id"]) for item in assignment_rows}
    status_counts = Counter(str(item["status"]) for item in assignment_rows)
    host_count = len(assignment["host_mapping_evidence"])
    return {
        "schema_version": AUDIT_SCHEMA,
        "result": "identity-assignment-incomplete" if assigned_ids != all_ids else "identity-assignment-complete-not-content-release",
        "season_label": assignment["season_label"],
        "assignment_sha256": hashlib.sha256(canonical_json_bytes(dict(assignment))).hexdigest(),
        "coverage": {
            "fixed_foreign_carrier_count": len(all_ids),
            "host_country_evidence_count": host_count,
            "historical_identity_assignment_count": len(assignment_rows),
            "status_counts": dict(sorted(status_counts.items())),
            "unassigned_carrier_count": len(all_ids - assigned_ids),
        },
        "unassigned_carrier_ids": sorted(all_ids - assigned_ids),
        "release_boundary": [
            "An approved assignment proves only a fixed carrier, reviewed host country and same-country historic source club.",
            "It does not write membership, country, division, promotion/relegation structure or continental draw pools.",
            "It is not a complete content transaction: manager, stadium, kit, portrait/no-photo, player fact/rating and runtime gates remain mandatory.",
        ],
    }


def apply_proposals(*, assignment: Mapping[str, Any], proposals: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply reviewed, declarative season edits without mutating their base.

    A future review note such as "carrier 38 should be Las Palmas" belongs in
    a small proposal file.  The base retains the evidence lock and every
    derived result is revalidated against the source capture before it can be
    used by a compiler.
    """

    output = json.loads(json.dumps(assignment))
    rows = {int(item["carrier_id"]): item for item in output["assignments"]}
    for proposal in proposals:
        if set(proposal) != {"schema_version", "assignment_id", "source_capture_sha256", "assignments"}:
            raise AssignmentError("assignment proposal has unsupported fields")
        if proposal.get("schema_version") != PROPOSAL_SCHEMA:
            raise AssignmentError("assignment proposal schema_version is unsupported")
        if proposal.get("assignment_id") != output.get("assignment_id"):
            raise AssignmentError("assignment proposal targets a different assignment ledger")
        if proposal.get("source_capture_sha256") != output.get("source_capture_sha256"):
            raise AssignmentError("assignment proposal targets a different historic source capture")
        edits = proposal.get("assignments")
        if not isinstance(edits, list) or not edits:
            raise AssignmentError("assignment proposal must contain a non-empty assignments list")
        prior = 0
        for edit in edits:
            if not isinstance(edit, dict) or not isinstance(edit.get("carrier_id"), int):
                raise AssignmentError("assignment proposal row must have an integer carrier_id")
            carrier_id = int(edit["carrier_id"])
            if carrier_id <= prior:
                raise AssignmentError("assignment proposal rows must be carrier-id sorted and unique")
            prior = carrier_id
            rows[carrier_id] = edit
    output["assignments"] = [rows[carrier_id] for carrier_id in sorted(rows)]
    return output


def rebind_assignment_to_capture(
    *,
    assignment: Mapping[str, Any],
    registry: Mapping[str, Any],
    previous_source_capture: Mapping[str, Any],
    source_capture: Mapping[str, Any],
    assignment_id: str,
) -> dict[str, Any]:
    """Derive a new assignment ledger for a composed canonical capture.

    A carrier assignment is deliberately locked to the complete source
    capture, not merely to its individual club row hashes.  When a season's
    split-year and calendar-year receipts are composed, copying the old
    document would therefore be stale.  This helper validates the old ledger,
    changes only the capture/season binding and ID, then validates every
    retained selector against the new capture.  It never auto-assigns a club
    or promotes a candidate.
    """

    validate_assignment(
        assignment=assignment,
        registry=registry,
        source_capture=previous_source_capture,
    )
    _source_clubs(source_capture)
    source_season = source_capture.get("season")
    if not isinstance(source_season, dict):
        raise AssignmentError("new source capture season is malformed")
    season_label = source_season.get("label")
    _require_text(season_label, "new source capture season.label")
    output = json.loads(json.dumps(assignment))
    output["assignment_id"] = _require_id(assignment_id, "assignment_id")
    output["season_label"] = season_label
    output["source_capture_sha256"] = hashlib.sha256(
        canonical_json_bytes(dict(source_capture))
    ).hexdigest()
    validate_assignment(assignment=output, registry=registry, source_capture=source_capture)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--assignment", type=Path)
    parser.add_argument("--rebind-from-source-capture", type=Path)
    parser.add_argument("--rebind-assignment-id")
    parser.add_argument("--host-report", type=Path, action="append", default=[])
    parser.add_argument("--proposal", type=Path, action="append", default=[])
    parser.add_argument("--initialise", action="store_true")
    parser.add_argument("--assignment-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        registry, _ = read_canonical_json(args.registry, label="fixed-carrier registry")
        capture, _ = read_canonical_json(args.source_capture, label="historic squad capture")
        reports = [read_json_document(path, label="host mapping report") for path in args.host_report]
        if args.initialise and args.rebind_from_source_capture is not None:
            raise AssignmentError("--initialise cannot be combined with --rebind-from-source-capture")
        if args.initialise:
            if not args.assignment_id:
                raise AssignmentError("--initialise requires --assignment-id")
            payload = initialise_assignment(registry=registry, source_capture=capture, host_reports=reports, assignment_id=args.assignment_id)
        elif args.rebind_from_source_capture is not None:
            if args.assignment is None:
                raise AssignmentError("--rebind-from-source-capture requires --assignment")
            if not args.rebind_assignment_id:
                raise AssignmentError("--rebind-from-source-capture requires --rebind-assignment-id")
            previous_capture, _ = read_canonical_json(
                args.rebind_from_source_capture, label="previous historic squad capture"
            )
            prior, _ = read_canonical_json(args.assignment, label="carrier assignment")
            payload = rebind_assignment_to_capture(
                assignment=prior,
                registry=registry,
                previous_source_capture=previous_capture,
                source_capture=capture,
                assignment_id=args.rebind_assignment_id,
            )
        else:
            if args.assignment is None:
                raise AssignmentError("--assignment is required unless --initialise is used")
            payload, _ = read_canonical_json(args.assignment, label="carrier assignment")
        proposals = [read_canonical_json(path, label="assignment proposal")[0] for path in args.proposal]
        if proposals:
            payload = apply_proposals(assignment=payload, proposals=proposals)
        audit = audit_assignment(assignment=payload, registry=registry, source_capture=capture)
    except AssignmentError as exc:
        parser.error(str(exc))
    write_canonical_json(
        args.output,
        payload if args.initialise or args.proposal or args.rebind_from_source_capture is not None else audit,
    )
    print(json.dumps(audit["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
