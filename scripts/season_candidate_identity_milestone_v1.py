#!/usr/bin/env python3
"""Materialise one guarded, candidate-only foreign identity milestone.

This is the repeatable orchestration front door for the per-season editorial
pilot.  It derives a deterministic proposal from existing reviewed host and
source-name queue inputs, then emits a *separate* candidate ledger and audit.
It never changes the base assignment, approves an identity, or writes PM99.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignment_lib  # noqa: E402
from scripts import foreign_carrier_candidate_proposal_v1 as proposal_lib  # noqa: E402


class SeasonCandidateMilestoneError(ValueError):
    """The requested season cannot safely receive a candidate milestone."""


def _read(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value, _ = assignment_lib.read_canonical_json(path, label=label)
    except assignment_lib.AssignmentError as exc:
        raise SeasonCandidateMilestoneError(str(exc)) from exc
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _select_bound_source(*, sources_dir: Path, expected_source_hash: object) -> tuple[Path, dict[str, Any]]:
    """Select the one canonical receipt explicitly pinned by the assignment.

    Seasons can retain alternate source views (for example calendar and
    split-year captures).  Selecting by filename count would discard valid
    evidence or silently choose the wrong receipt, so only the assignment's
    canonical source hash may choose the input.
    """

    if not isinstance(expected_source_hash, str) or len(expected_source_hash) != 64:
        raise SeasonCandidateMilestoneError("base assignment has no valid source_capture_sha256")
    source_matches: list[tuple[Path, dict[str, Any]]] = []
    for candidate_path in sorted(sources_dir.glob("footballsquads-*.json")):
        candidate_capture = _read(candidate_path, label="historic squad capture")
        if hashlib.sha256(assignment_lib.canonical_json_bytes(candidate_capture)).hexdigest() == expected_source_hash:
            source_matches.append((candidate_path, candidate_capture))
    if len(source_matches) != 1:
        raise SeasonCandidateMilestoneError("season needs exactly one source receipt matching the assignment's source_capture_sha256")
    return source_matches[0]


def run_milestone(*, season_dir: Path, replace: bool = False) -> dict[str, Any]:
    season_dir = season_dir.resolve()
    registry_path = season_dir / "fixed-carrier-registry.json"
    assignment_path = season_dir / "foreign-carrier-assignment.json"
    queue_path = season_dir / "foreign-carrier-candidate-queue.json"
    outputs = {
        "proposal": season_dir / "foreign-carrier-candidate-proposal.json",
        "derived_assignment": season_dir / "foreign-carrier-assignment-candidates.json",
        "audit": season_dir / "foreign-carrier-assignment-candidates-audit.json",
    }
    existing = [name for name, path in outputs.items() if path.exists()]
    if existing and not replace:
        raise SeasonCandidateMilestoneError("milestone outputs already exist: " + ", ".join(existing))

    registry = _read(registry_path, label="fixed-carrier registry")
    assignment = _read(assignment_path, label="base carrier assignment")
    source_path, source_capture = _select_bound_source(
        sources_dir=season_dir / "sources", expected_source_hash=assignment.get("source_capture_sha256")
    )
    queue = _read(queue_path, label="carrier candidate queue")
    proposal = proposal_lib.build_candidate_proposal(
        registry=registry, source_capture=source_capture, assignment=assignment, queue=queue
    )
    derived = assignment_lib.apply_proposals(assignment=assignment, proposals=[proposal])
    audit = assignment_lib.audit_assignment(assignment=derived, registry=registry, source_capture=source_capture)
    assignment_lib.write_canonical_json(outputs["proposal"], proposal)
    assignment_lib.write_canonical_json(outputs["derived_assignment"], derived)
    assignment_lib.write_canonical_json(outputs["audit"], audit)
    return {
        "result": "candidate-identity-milestone-created",
        "season_label": assignment["season_label"],
        "candidate_assignment_count": len(proposal["assignments"]),
        "coverage": audit["coverage"],
        "outputs": {name: {"path": str(path.relative_to(ROOT)), "sha256": _sha256(path)} for name, path in outputs.items()},
        "release_boundary": "Candidate identities are unapproved editorial leads; no PM99 content or binaries were written.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season-dir", type=Path, required=True)
    parser.add_argument("--replace", action="store_true", help="replace only existing deterministic candidate milestone outputs")
    args = parser.parse_args(argv)
    try:
        report = run_milestone(season_dir=args.season_dir, replace=args.replace)
    except (SeasonCandidateMilestoneError, proposal_lib.CandidateProposalError, assignment_lib.AssignmentError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
