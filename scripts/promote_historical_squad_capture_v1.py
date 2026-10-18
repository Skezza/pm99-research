#!/usr/bin/env python3
"""Compose a credited canonical squad capture into an immutable revision."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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


SELECTOR_FIELDS = ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")


def _capture_selectors(document: dict[str, Any]) -> set[tuple[str, ...]]:
    return {tuple(str(row.get(key) or "") for key in SELECTOR_FIELDS) for row in document["clubs"]}


def _without_capture_clubs(source: dict[str, Any], capture: dict[str, Any]) -> dict[str, Any]:
    """Remove exactly one previously named capture from a composed source."""

    selectors = _capture_selectors(capture)
    present = _capture_selectors(source)
    missing = selectors - present
    if missing:
        raise ValueError(f"cannot replace capture: {len(missing)} source selectors are absent")
    result = dict(source)
    result["clubs"] = [
        row for row in source["clubs"]
        if tuple(str(row.get(key) or "") for key in SELECTOR_FIELDS) not in selectors
    ]
    return result


def promote(*, season: str, artifact_name: str, capture_path: Path, gaps_path: Path | None,
            output_root: Path, replace_existing: bool = False) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", artifact_name):
        raise ValueError("artifact name must be lower-case snake_case")
    local = output_root / season
    current = batch._read(local / "current.json")

    def artifact(name: str) -> dict[str, Any]:
        row = current["artifacts"][name]
        path = local / row["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"current artifact hash mismatch: {name}")
        return batch._read(path)

    old_source = artifact("source")
    addition = batch._read(capture_path)
    addition_sha = batch._document_sha(addition)
    start_year = int(season[:4])
    if addition.get("season", {}).get("label") != f"{start_year}/{str(start_year + 1)[-2:]}":
        raise ValueError("capture season label does not match target season")
    if artifact_name in current["artifacts"]:
        existing_sha = current["artifacts"][artifact_name]["sha256"]
        if existing_sha != addition_sha and not replace_existing:
            raise ValueError(f"current revision already contains a different {artifact_name} capture")
        if existing_sha == addition_sha:
            source = old_source
        else:
            base = _without_capture_clubs(old_source, artifact(artifact_name))
            source = compositor.compose(
                inputs=[("world-squads-current-without-replaced-capture.json", base, batch._document_sha(base)),
                        (f"{artifact_name}.json", addition, addition_sha)],
                catalog=f"{start_year}-{start_year + 1}", label=f"{start_year}/{str(start_year + 1)[-2:]}",
            )
    else:
        old_selectors = _capture_selectors(old_source)
        new_selectors = _capture_selectors(addition)
        if new_selectors and new_selectors <= old_selectors:
            # A previous batch may already have composed this byte-identical
            # provider capture without retaining a named revision artifact.
            source = old_source
        else:
            source = compositor.compose(
                inputs=[("world-squads-current.json", old_source, batch._document_sha(old_source)),
                        (f"{artifact_name}.json", addition, addition_sha)],
                catalog=f"{start_year}-{start_year + 1}", label=f"{start_year}/{str(start_year + 1)[-2:]}",
            )
    registry = batch._read(ROOT / "seasons" / season / "fixed-carrier-registry.json")
    allocation = allocator.build_allocation(source=source, registry=registry)
    assignment = adapter.adapt(allocation=allocation, registry=registry, source=source,
                               assignment_id=f"world-{season}-expanded-assignment")
    intake = intake_lib.build_intake(registry=registry, source_capture=source, assignment=assignment,
                                    intake_id=f"world-{season}-expanded-intake")
    replace = {"source", "allocation", "assignment", "intake", artifact_name, f"{artifact_name}_gaps"}
    artifacts = {name: artifact(name) for name in current["artifacts"] if name not in replace}
    artifacts.update(source=source, allocation=allocation, assignment=assignment, intake=intake)
    artifacts[artifact_name] = addition
    if gaps_path is not None:
        artifacts[f"{artifact_name}_gaps"] = batch._read(gaps_path)
    revision, manifest = batch._publish_revision(local=local, season=season, artifacts=artifacts)
    return {"allocation_sha256": manifest["artifacts"]["allocation"]["sha256"],
            "assignment_count": allocation["coverage"]["assignment_count"],
            "intake_sha256": manifest["artifacts"]["intake"]["sha256"],
            "revision_id": revision, "season": season}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True); parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--capture", required=True, type=Path); parser.add_argument("--gaps", type=Path)
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    args = parser.parse_args(argv)
    print(json.dumps(promote(season=args.season, artifact_name=args.artifact_name, capture_path=args.capture,
                             gaps_path=args.gaps, output_root=args.output_root,
                             replace_existing=args.replace_existing), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
