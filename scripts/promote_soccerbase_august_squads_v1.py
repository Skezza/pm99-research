#!/usr/bin/env python3
"""Compose one Soccerbase August capture into an immutable current revision."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import compose_season_source_captures_v1 as compositor
from scripts import season_carrier_allocation_v1 as allocator
from scripts import season_historical_squad_backfill_batch_v1 as batch
from scripts import season_source_intake_from_allocation_v1 as adapter
from scripts import season_source_intake_v1 as intake_lib


def promote(*, season: str, capture_path: Path, gaps_path: Path, output_root: Path) -> dict[str, Any]:
    local = output_root / season
    current = batch._read(local / "current.json")

    def artifact(name: str) -> dict[str, Any]:
        row = current["artifacts"][name]
        path = local / row["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"current artifact hash mismatch: {name}")
        return batch._read(path)

    old_source = artifact("source")
    soccerbase = batch._read(capture_path)
    gaps = batch._read(gaps_path)
    start_year = int(season[:4])
    soccerbase_sha = batch._document_sha(soccerbase)
    if "soccerbase" in current["artifacts"]:
        if current["artifacts"]["soccerbase"]["sha256"] != soccerbase_sha:
            raise ValueError("current revision already contains a different Soccerbase capture")
        source = old_source
    else:
        source = compositor.compose(
            inputs=[
                ("world-squads-current.json", old_source, batch._document_sha(old_source)),
                ("soccerbase-august-squads.json", soccerbase, soccerbase_sha),
            ],
            catalog=f"{start_year}-{start_year + 1}",
            label=f"{start_year}/{str(start_year + 1)[-2:]}",
        )
    registry = batch._read(ROOT / "seasons" / season / "fixed-carrier-registry.json")
    allocation = allocator.build_allocation(source=source, registry=registry)
    assignment = adapter.adapt(
        allocation=allocation, registry=registry, source=source,
        assignment_id=f"world-{season}-expanded-assignment",
    )
    intake = intake_lib.build_intake(
        registry=registry, source_capture=source, assignment=assignment,
        intake_id=f"world-{season}-expanded-intake",
    )
    artifacts = {
        name: artifact(name) for name in current["artifacts"]
        if name not in {"source", "allocation", "assignment", "intake", "soccerbase", "soccerbase_gaps"}
    }
    artifacts.update(
        source=source, allocation=allocation, assignment=assignment, intake=intake,
        soccerbase=soccerbase, soccerbase_gaps=gaps,
    )
    revision, manifest = batch._publish_revision(local=local, season=season, artifacts=artifacts)
    return {
        "allocation_sha256": manifest["artifacts"]["allocation"]["sha256"],
        "assignment_count": allocation["coverage"]["assignment_count"],
        "intake_sha256": manifest["artifacts"]["intake"]["sha256"],
        "revision_id": revision,
        "season": season,
        "soccerbase_club_count": len(soccerbase["clubs"]),
        "soccerbase_gap_count": gaps["summary"]["gap_count"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--gaps", required=True, type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    args = parser.parse_args(argv)
    result = promote(season=args.season, capture_path=args.capture, gaps_path=args.gaps, output_root=args.output_root)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
