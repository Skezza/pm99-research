#!/usr/bin/env python3
"""Atomically promote multiple credited squad captures in one season revision."""

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
from scripts.promote_historical_squad_capture_v1 import _capture_selectors, _without_capture_clubs


def _declaration(value: str) -> tuple[str, Path]:
    name, separator, path = value.partition("=")
    if not separator or not re.fullmatch(r"[a-z][a-z0-9_]*", name) or not path:
        raise argparse.ArgumentTypeError("declaration must be lower_snake_name=path")
    return name, Path(path)


def promote_wave(
    *, season: str, captures: Sequence[tuple[str, Path]], gaps: Sequence[tuple[str, Path]],
    replacements: set[str], output_root: Path, dry_run: bool = False,
) -> dict[str, Any]:
    names = [name for name, _path in captures]
    if len(names) != len(set(names)) or not names:
        raise ValueError("capture artifact names must be non-empty and unique")
    if replacements - set(names):
        raise ValueError("replacement names must also be declared captures")
    gap_paths = dict(gaps)
    if set(gap_paths) - set(names):
        raise ValueError("gap names must also be declared captures")

    local = output_root / season
    current = batch._read(local / "current.json")

    def artifact(name: str) -> dict[str, Any]:
        row = current["artifacts"][name]
        path = local / row["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError(f"current artifact hash mismatch: {name}")
        return batch._read(path)

    start_year = int(season[:4])
    source = artifact("source")
    additions: list[tuple[str, dict[str, Any], str]] = []
    loaded: dict[str, dict[str, Any]] = {}
    for name, path in captures:
        addition = batch._read(path)
        loaded[name] = addition
        addition_sha = batch._document_sha(addition)
        if addition.get("season", {}).get("label") != f"{start_year}/{str(start_year + 1)[-2:]}":
            raise ValueError(f"{name} capture season label does not match target season")
        if name in current["artifacts"]:
            existing_sha = current["artifacts"][name]["sha256"]
            if existing_sha == addition_sha:
                continue
            if name not in replacements:
                raise ValueError(f"current revision already contains a different {name} capture")
            source = _without_capture_clubs(source, artifact(name))
        elif _capture_selectors(addition) <= _capture_selectors(source):
            continue
        additions.append((f"{name}.json", addition, addition_sha))

    if additions:
        source = compositor.compose(
            inputs=[("world-squads-current-wave-base.json", source, batch._document_sha(source)), *additions],
            catalog=f"{start_year}-{start_year + 1}", label=f"{start_year}/{str(start_year + 1)[-2:]}",
        )
    registry = batch._read(ROOT / "seasons" / season / "fixed-carrier-registry.json")
    allocation = allocator.build_allocation(source=source, registry=registry)
    if dry_run:
        return {
            "assignment_count": allocation["coverage"]["assignment_count"],
            "current_assignment_count": artifact("allocation")["coverage"]["assignment_count"],
            "dry_run": True,
            "season": season,
        }
    assignment = adapter.adapt(
        allocation=allocation, registry=registry, source=source,
        assignment_id=f"world-{season}-expanded-assignment",
    )
    intake = intake_lib.build_intake(
        registry=registry, source_capture=source, assignment=assignment,
        intake_id=f"world-{season}-expanded-intake",
    )
    replace = {"source", "allocation", "assignment", "intake"}
    for name in names:
        replace.update({name, f"{name}_gaps"})
    artifacts = {name: artifact(name) for name in current["artifacts"] if name not in replace}
    artifacts.update(source=source, allocation=allocation, assignment=assignment, intake=intake)
    for name in names:
        artifacts[name] = loaded[name]
        if name in gap_paths:
            artifacts[f"{name}_gaps"] = batch._read(gap_paths[name])
    revision, manifest = batch._publish_revision(local=local, season=season, artifacts=artifacts)
    return {
        "assignment_count": allocation["coverage"]["assignment_count"],
        "current_manifest_sha256": batch._document_sha(manifest),
        "revision_id": revision, "season": season,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", required=True)
    parser.add_argument("--capture", action="append", required=True, type=_declaration)
    parser.add_argument("--gaps", action="append", default=[], type=_declaration)
    parser.add_argument("--replace", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true", help="validate and project without publishing")
    parser.add_argument("--output-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    args = parser.parse_args(argv)
    print(json.dumps(promote_wave(
        season=args.season, captures=args.capture, gaps=args.gaps,
        replacements=set(args.replace), output_root=args.output_root, dry_run=args.dry_run,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
