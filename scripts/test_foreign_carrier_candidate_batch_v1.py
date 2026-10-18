from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_candidate_batch_v1 as batch_lib  # noqa: E402
from scripts import foreign_carrier_candidate_queue_v1 as queue_lib  # noqa: E402


def _queue(season_label: str) -> dict[str, object]:
    return {
        "schema_version": queue_lib.SCHEMA,
        "season_label": season_label,
        "registry_sha256": "a" * 64,
        "source_capture_sha256": "b" * 64,
        "assignment_sha256": "c" * 64,
        "queue_policy": ["Fixture"],
        "coverage": {"reviewed_host_carrier_count": 1, "already_assigned_host_carrier_count": 0, "unassigned_host_carrier_queue_count": 1, "candidate_state_counts": {"single-name-token-candidate": 1}},
        "queue": [],
    }


def test_batch_preserves_embedded_canonical_queue_hashes() -> None:
    first, second = _queue("2001/02"), _queue("2000/01")
    rows = [
        ("seasons/2001-02/foreign-carrier-candidate-queue.json", first, hashlib.sha256(batch_lib.canonical_json_bytes(first)).hexdigest()),
        ("seasons/2000-01/foreign-carrier-candidate-queue.json", second, hashlib.sha256(batch_lib.canonical_json_bytes(second)).hexdigest()),
    ]
    batch = batch_lib.build_batch(queues=rows, batch_id="pm99-review-batch")
    assert [row["season_label"] for row in batch["queues"]] == ["2000/01", "2001/02"]
    batch_lib.validate_batch(batch)


def test_batch_rejects_changed_embedded_queue_or_duplicate_season() -> None:
    queue = _queue("2000/01")
    digest = hashlib.sha256(batch_lib.canonical_json_bytes(queue)).hexdigest()
    batch = batch_lib.build_batch(queues=[("seasons/2000-01/foreign-carrier-candidate-queue.json", queue, digest)], batch_id="pm99-review-batch")
    changed = copy.deepcopy(batch)
    changed["queues"][0]["queue"]["coverage"]["reviewed_host_carrier_count"] = 2
    with pytest.raises(batch_lib.CandidateBatchError, match="digest"):
        batch_lib.validate_batch(changed)
    with pytest.raises(batch_lib.CandidateBatchError, match="duplicate season"):
        batch_lib.build_batch(queues=[("one.json", queue, digest), ("two.json", queue, digest)], batch_id="pm99-review-batch")
