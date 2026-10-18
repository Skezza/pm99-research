#!/usr/bin/env python3
"""Derive conservative assignment *candidate* proposals from a review queue.

This helper is an editorial bridge, not a PM99 writer.  It creates proposal
rows only for a queue's single, capacity-compatible source-name lead.  The
result deliberately remains ``status: candidate`` with blockers: a human
approval and every club/player/asset/runtime gate are still required before
any database materialisation can be considered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignment_lib  # noqa: E402
from scripts import foreign_carrier_candidate_queue_v1 as queue_lib  # noqa: E402


SCHEMA = assignment_lib.PROPOSAL_SCHEMA
SLUG_RE = re.compile(r"[^a-z0-9]+")
BLOCKERS = [
    "candidate-name-token-link-not-editorially-approved",
    "requires-complete-club-player-manager-kit-portrait-and-runtime-transaction",
    "requires-independent-club-identity-review",
]


class CandidateProposalError(ValueError):
    """A candidate proposal would be stale, ambiguous, or overconfident."""


def canonical_json_bytes(value: Any) -> bytes:
    return assignment_lib.canonical_json_bytes(value)


def _slug(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = "".join(character for character in text if not unicodedata.combining(character))
    slug = SLUG_RE.sub("-", ascii_text.casefold()).strip("-")
    if not slug or not assignment_lib.ID_RE.fullmatch(slug):
        raise CandidateProposalError(f"cannot make a stable identity key from {value!r}")
    return slug


def build_candidate_proposal(
    *, registry: Mapping[str, Any], source_capture: Mapping[str, Any], assignment: Mapping[str, Any], queue: Mapping[str, Any]
) -> dict[str, Any]:
    assignment_lib.validate_assignment(assignment=assignment, registry=registry, source_capture=source_capture)
    queue_lib.validate_candidate_queue(queue=queue, registry=registry, source_capture=source_capture, assignment=assignment)
    existing = {int(row["carrier_id"]) for row in assignment["assignments"]}
    rows: list[dict[str, Any]] = []
    for queued in queue["queue"]:
        carrier_id = int(queued["carrier_id"])
        if carrier_id in existing or queued["candidate_state"] != "single-name-token-candidate":
            continue
        candidates = queued["candidates"]
        if not isinstance(candidates, list) or len(candidates) != 1:
            raise CandidateProposalError(f"carrier {carrier_id} is not a single candidate row")
        candidate = candidates[0]
        if candidate.get("slot_capacity") != "meets-fixed-carrier-capacity":
            continue
        selector = candidate.get("source_selector")
        if not isinstance(selector, dict) or set(selector) != {
            "country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256"
        }:
            raise CandidateProposalError(f"carrier {carrier_id} candidate has an invalid source selector")
        club_name = selector["club_name"]
        rows.append(
            {
                "carrier_id": carrier_id,
                "status": "candidate",
                "historical_club": {
                    "identity_key": f"{_slug(selector['country_catalog'])}-{_slug(club_name)}",
                    "name": club_name,
                },
                "source_selector": dict(selector),
                "blockers": BLOCKERS,
            }
        )
    if not rows:
        raise CandidateProposalError("queue has no unassigned single capacity-compatible candidate leads")
    proposal = {
        "schema_version": SCHEMA,
        "assignment_id": assignment["assignment_id"],
        "source_capture_sha256": assignment["source_capture_sha256"],
        "assignments": rows,
    }
    derived = assignment_lib.apply_proposals(assignment=assignment, proposals=[proposal])
    assignment_lib.validate_assignment(assignment=derived, registry=registry, source_capture=source_capture)
    return proposal


def validate_candidate_proposal(
    *, proposal: Mapping[str, Any], registry: Mapping[str, Any], source_capture: Mapping[str, Any], assignment: Mapping[str, Any], queue: Mapping[str, Any]
) -> None:
    expected = build_candidate_proposal(registry=registry, source_capture=source_capture, assignment=assignment, queue=queue)
    if dict(proposal) != expected:
        raise CandidateProposalError("candidate proposal does not exactly match its verified review queue")


def _read(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value, _ = assignment_lib.read_canonical_json(path, label=label)
    except assignment_lib.AssignmentError as exc:
        raise CandidateProposalError(str(exc)) from exc
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-capture", type=Path, required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, help="validate this candidate proposal")
    parser.add_argument("--output", type=Path, help="write a new candidate proposal")
    args = parser.parse_args(argv)
    if bool(args.proposal) == bool(args.output):
        parser.error("provide exactly one of --proposal or --output")
    try:
        registry = _read(args.registry, label="fixed-carrier registry")
        source_capture = _read(args.source_capture, label="historic squad capture")
        assignment = _read(args.assignment, label="carrier assignment")
        queue = _read(args.queue, label="carrier candidate queue")
        if args.proposal:
            proposal = _read(args.proposal, label="carrier candidate proposal")
            validate_candidate_proposal(proposal=proposal, registry=registry, source_capture=source_capture, assignment=assignment, queue=queue)
        else:
            proposal = build_candidate_proposal(registry=registry, source_capture=source_capture, assignment=assignment, queue=queue)
            assignment_lib.write_canonical_json(args.output, proposal)
        print(json.dumps({"candidate_assignment_count": len(proposal["assignments"])}, sort_keys=True))
    except (CandidateProposalError, assignment_lib.AssignmentError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
