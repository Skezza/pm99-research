#!/usr/bin/env python3
"""Pack verified foreign-carrier candidate queues for one-file human review.

This is a browser-review convenience manifest.  It does not merge, alter or
approve queues, and it cannot be supplied to the PM99 compiler.  Each queued
season remains embedded verbatim with its original canonical-byte SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignment_lib  # noqa: E402
from scripts import foreign_carrier_candidate_queue_v1 as queue_lib  # noqa: E402


SCHEMA = "pm99-foreign-carrier-candidate-batch-v1"


class CandidateBatchError(ValueError):
    """A batch input is not a canonical candidate queue."""


def canonical_json_bytes(value: Any) -> bytes:
    return assignment_lib.canonical_json_bytes(value)


def _read_queue(path: Path) -> tuple[dict[str, Any], str]:
    try:
        value, digest = assignment_lib.read_canonical_json(path, label="carrier candidate queue")
    except assignment_lib.AssignmentError as exc:
        raise CandidateBatchError(str(exc)) from exc
    if value.get("schema_version") != queue_lib.SCHEMA:
        raise CandidateBatchError(f"{path} is not a {queue_lib.SCHEMA} document")
    return value, digest


def build_batch(*, queues: list[tuple[str, Mapping[str, Any], str]], batch_id: str) -> dict[str, Any]:
    if not assignment_lib.ID_RE.fullmatch(batch_id):
        raise CandidateBatchError("batch_id must be a stable lower-case id")
    if not queues:
        raise CandidateBatchError("batch requires at least one candidate queue")
    rows: list[dict[str, Any]] = []
    seen_seasons: set[str] = set()
    for source_file, queue, digest in queues:
        season_label = queue.get("season_label")
        if not isinstance(source_file, str) or not source_file or Path(source_file).is_absolute() or ".." in Path(source_file).parts:
            raise CandidateBatchError("batch queue source_file must be a safe relative path")
        if not isinstance(season_label, str) or not season_label.strip():
            raise CandidateBatchError("batch queue season_label must be non-blank")
        if season_label in seen_seasons:
            raise CandidateBatchError(f"batch has duplicate season label {season_label!r}")
        seen_seasons.add(season_label)
        rows.append({"season_label": season_label, "source_file": source_file, "queue_sha256": digest, "queue": dict(queue)})
    rows.sort(key=lambda row: str(row["season_label"]))
    return {
        "schema_version": SCHEMA,
        "batch_id": batch_id,
        "purpose": "Browser review convenience only; it cannot approve or write PM99 content.",
        "queue_count": len(rows),
        "queues": rows,
    }


def validate_batch(batch: Mapping[str, Any]) -> None:
    if set(batch) != {"schema_version", "batch_id", "purpose", "queue_count", "queues"}:
        raise CandidateBatchError("batch has unsupported fields")
    if batch.get("schema_version") != SCHEMA:
        raise CandidateBatchError(f"batch schema_version must be {SCHEMA!r}")
    batch_id = batch.get("batch_id")
    if not isinstance(batch_id, str) or not assignment_lib.ID_RE.fullmatch(batch_id):
        raise CandidateBatchError("batch_id must be a stable lower-case id")
    rows = batch.get("queues")
    if not isinstance(rows, list) or not rows or batch.get("queue_count") != len(rows):
        raise CandidateBatchError("queue_count must exactly match non-empty queues")
    expected_rows: list[tuple[str, Mapping[str, Any], str]] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"season_label", "source_file", "queue_sha256", "queue"}:
            raise CandidateBatchError("batch queue row has unsupported fields")
        queue = row["queue"]
        if not isinstance(queue, dict) or queue.get("season_label") != row["season_label"]:
            raise CandidateBatchError("batch queue row season label does not match embedded queue")
        digest = hashlib.sha256(canonical_json_bytes(queue)).hexdigest()
        if row.get("queue_sha256") != digest:
            raise CandidateBatchError("batch queue digest does not match embedded canonical queue")
        expected_rows.append((str(row["source_file"]), queue, digest))
    if dict(batch) != build_batch(queues=expected_rows, batch_id=batch_id):
        raise CandidateBatchError("batch rows are not deterministically ordered or are malformed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, action="append", default=[])
    parser.add_argument("--batch-id", default="pm99-all-country-foreign-carrier-review")
    parser.add_argument("--batch", type=Path, help="validate a batch instead of creating one")
    parser.add_argument("--output", type=Path, help="destination for a new batch")
    args = parser.parse_args(argv)
    if bool(args.batch) == bool(args.output):
        parser.error("provide exactly one of --batch or --output")
    try:
        if args.batch:
            batch, _ = assignment_lib.read_canonical_json(args.batch, label="candidate queue batch")
            validate_batch(batch)
            print(json.dumps({"queue_count": batch["queue_count"]}, sort_keys=True))
        else:
            queue_rows = []
            for path in args.queue:
                queue, digest = _read_queue(path)
                try:
                    source_file = str(path.resolve().relative_to(ROOT))
                except ValueError as exc:
                    raise CandidateBatchError("queue must be inside the PM99RE workspace") from exc
                queue_rows.append((source_file, queue, digest))
            batch = build_batch(queues=queue_rows, batch_id=args.batch_id)
            assignment_lib.write_canonical_json(args.output, batch)
            print(json.dumps({"queue_count": batch["queue_count"]}, sort_keys=True))
    except (CandidateBatchError, assignment_lib.AssignmentError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
