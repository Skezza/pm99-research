#!/usr/bin/env python3
"""Build deterministic, non-writing review queues for foreign carrier identity.

The fixed-carrier assignment ledger can only hold a reviewed club identity.
This helper deliberately stops one step earlier: it turns a reviewed
preseason-picker host-country fact plus a dated squad capture into a small
human review queue.  A name-token match is a useful lead, not proof that an
old PM99 carrier should represent that historical club.

It never writes a PM99 database, changes an assignment ledger, infers a
division, or turns a source competition catalogue into a PM99 field.
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

from scripts import foreign_carrier_assignment_v1 as assignment_lib  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as registry_lib  # noqa: E402


SCHEMA = "pm99-foreign-carrier-candidate-queue-v1"
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
TOKEN_RE = re.compile(r"[^a-z0-9]+")
IGNORED_CLUB_TOKENS = frozenset({"c", "cf", "club", "f", "fc", "r", "rc"})


class CandidateQueueError(ValueError):
    """The queued leads are stale, malformed, or overstate their evidence."""


def canonical_json_bytes(value: Any) -> bytes:
    return assignment_lib.canonical_json_bytes(value)


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def _country_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(character.casefold() for character in text if character.isalnum())


def _club_tokens(value: object) -> list[str]:
    text = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(character for character in text if not unicodedata.combining(character))
    tokens = [token for token in TOKEN_RE.sub(" ", ascii_text.casefold()).split() if token not in IGNORED_CLUB_TOKENS]
    return sorted(set(tokens))


def _selector(club: Mapping[str, Any]) -> dict[str, str]:
    return {
        "country_catalog": str(club["country_catalog"]),
        "competition_catalog": str(club["competition_catalog"]),
        "club_name": str(club["club_name"]),
        "source_path": str(club["source_path"]),
        "source_sha256": str(club["source_sha256"]),
    }


def build_candidate_queue(
    *, registry: Mapping[str, Any], source_capture: Mapping[str, Any], assignment: Mapping[str, Any]
) -> dict[str, Any]:
    """Return candidates derived solely from locked input evidence.

    Candidates require every meaningful token of a carrier's *baseline* club
    name to appear in one source-club display name from the reviewed host
    country.  This intentionally favours a compact, inspectable review list
    over broad country-level guesses.  It is still non-authoritative because
    carrier reuse needs a human editorial identity decision.
    """

    registry_lib.validate_registry(registry)
    assignment_lib.validate_assignment(assignment=assignment, registry=registry, source_capture=source_capture)
    clubs = assignment_lib._source_clubs(source_capture)
    carriers = {int(item["carrier_id"]): item for item in registry["carriers"]}
    existing_rows = {int(item["carrier_id"]): str(item["status"]) for item in assignment["assignments"]}
    host_rows = {int(item["carrier_id"]): item for item in assignment["host_mapping_evidence"]}
    queue_rows: list[dict[str, Any]] = []

    for carrier_id in sorted(host_rows):
        if carrier_id in existing_rows:
            continue
        carrier = carriers[carrier_id]
        baseline_name = str(carrier["baseline_club"]["name"])
        baseline_tokens = _club_tokens(baseline_name)
        if not baseline_tokens:
            raise CandidateQueueError(f"carrier {carrier_id} baseline club has no meaningful name tokens")
        host = host_rows[carrier_id]
        host_key = _country_key(host["host_country"])
        source_clubs = [
            club for key, club in clubs.items()
            if _country_key(key[0]) == host_key
        ]
        candidates: list[dict[str, Any]] = []
        for club in source_clubs:
            source_tokens = _club_tokens(club["club_name"])
            if not set(baseline_tokens).issubset(source_tokens):
                continue
            player_count = len(club["players"])
            required_slots = len(carrier["roster_slots"])
            candidates.append(
                {
                    "source_selector": _selector(club),
                    "competition_name": str(club["competition_name"]),
                    "player_count": player_count,
                    "slot_capacity": "meets-fixed-carrier-capacity" if player_count >= required_slots else "below-fixed-carrier-capacity",
                    "match": {
                        "kind": "source-name-covers-baseline-significant-tokens",
                        "baseline_tokens": baseline_tokens,
                        "source_tokens": source_tokens,
                    },
                }
            )
        candidates.sort(key=lambda item: (
            item["source_selector"]["club_name"].casefold(),
            item["source_selector"]["competition_catalog"],
            item["source_selector"]["source_path"],
        ))
        candidate_state = (
            "no-name-token-candidate" if not candidates
            else "single-name-token-candidate" if len(candidates) == 1
            else "multiple-name-token-candidates"
        )
        queue_rows.append(
            {
                "carrier_id": carrier_id,
                "baseline_club_name": baseline_name,
                "host_country": str(host["host_country"]),
                "host_mapping_evidence": {
                    "capture_id": str(host["capture_id"]),
                    "report_sha256": str(host["report_sha256"]),
                    "screenshot_sha256": str(host["screenshot_sha256"]),
                },
                "required_roster_slots": len(carrier["roster_slots"]),
                "assignment_state": "unassigned",
                "candidate_state": candidate_state,
                "candidate_blockers": [
                    "candidate-only-name-token-link",
                    "requires-editorial-carrier-identity-approval",
                    "requires-complete-club-player-manager-kit-portrait-and-runtime-transaction",
                ],
                "candidates": candidates,
            }
        )

    counts = Counter(str(row["candidate_state"]) for row in queue_rows)
    return {
        "schema_version": SCHEMA,
        "season_label": str(assignment["season_label"]),
        "registry_sha256": _sha256(registry),
        "source_capture_sha256": _sha256(source_capture),
        "assignment_sha256": _sha256(assignment),
        "queue_policy": [
            "A candidate is a review lead, not an approved historical identity assignment.",
            "The match uses only normalised significant display-name tokens within a reviewed host country.",
            "The source competition catalogue is provenance and must not be written as a PM99 division, membership or draw-pool claim.",
            "No queue row writes PM99 files or changes the immutable fixed-carrier assignment ledger.",
        ],
        "coverage": {
            "reviewed_host_carrier_count": len(host_rows),
            "already_assigned_host_carrier_count": len(set(host_rows) & set(existing_rows)),
            "unassigned_host_carrier_queue_count": len(queue_rows),
            "candidate_state_counts": dict(sorted(counts.items())),
        },
        "queue": queue_rows,
    }


def validate_candidate_queue(
    *, queue: Mapping[str, Any], registry: Mapping[str, Any], source_capture: Mapping[str, Any], assignment: Mapping[str, Any]
) -> None:
    if queue.get("schema_version") != SCHEMA:
        raise CandidateQueueError(f"candidate queue schema_version must be {SCHEMA!r}")
    expected = build_candidate_queue(registry=registry, source_capture=source_capture, assignment=assignment)
    if dict(queue) != expected:
        raise CandidateQueueError("candidate queue does not exactly match its hash-locked source inputs")


def _read(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value, _ = assignment_lib.read_canonical_json(path, label=label)
    except assignment_lib.AssignmentError as exc:
        raise CandidateQueueError(str(exc)) from exc
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    parser.add_argument("--queue", type=Path, help="validate an existing queue instead of creating one")
    parser.add_argument("--output", type=Path, help="destination for a newly generated queue")
    args = parser.parse_args(argv)
    if bool(args.queue) == bool(args.output):
        parser.error("provide exactly one of --queue or --output")
    try:
        registry = _read(args.registry, label="fixed-carrier registry")
        source_capture = _read(args.source_capture, label="historic squad capture")
        assignment = _read(args.assignment, label="carrier assignment")
        if args.queue:
            queue = _read(args.queue, label="carrier candidate queue")
            validate_candidate_queue(queue=queue, registry=registry, source_capture=source_capture, assignment=assignment)
            print(json.dumps(queue["coverage"], sort_keys=True))
        else:
            queue = build_candidate_queue(registry=registry, source_capture=source_capture, assignment=assignment)
            assignment_lib.write_canonical_json(args.output, queue)
            print(json.dumps(queue["coverage"], sort_keys=True))
    except (CandidateQueueError, assignment_lib.AssignmentError, registry_lib.WorldLedgerError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
