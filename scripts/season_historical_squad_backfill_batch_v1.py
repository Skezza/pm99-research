#!/usr/bin/env python3
"""Run the historical-squad capture/composition/intake lane by season.

The largest canonical FootballSquads capture is the deterministic base.  Only
country families absent from that base are requested from the explicit
Transfermarkt scope, preventing duplicate-source club pools.  All outputs are
content-addressed and safe to resume from the local snapshot cache.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_transfermarkt_historical_squads_v1 as capture_lib  # noqa: E402
from scripts import compose_season_source_captures_v1 as compose_lib  # noqa: E402
from scripts import season_carrier_allocation_v1 as allocation_lib  # noqa: E402
from scripts import season_source_intake_from_allocation_v1 as intake_adapter  # noqa: E402
from scripts import season_source_intake_v1 as intake_lib  # noqa: E402
from scripts import capture_ntf_historical_carrier_squads_v1 as ntf_lib  # noqa: E402
from scripts.capture_transfermarkt_opening_lineups_v1 import SnapshotCache  # noqa: E402

SCHEMA = "pm99-historical-squad-backfill-batch-v1"
CURRENT_SCHEMA = "pm99-historical-squad-backfill-current-v1"


def _read(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != capture_lib.canonical_bytes(value):
        raise ValueError(f"not canonical JSON: {path}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _document_sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(capture_lib.canonical_bytes(value)).hexdigest()


def _write_immutable(path: Path, value: Mapping[str, Any]) -> str:
    payload = capture_lib.canonical_bytes(value)
    digest = hashlib.sha256(payload).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"immutable revision artifact conflict: {path}")
    else:
        path.write_bytes(payload)
    return digest


def _publish_revision(*, local: Path, season: str, artifacts: Mapping[str, Mapping[str, Any]]) -> tuple[str, dict[str, Any]]:
    hashes = {name: _document_sha(value) for name, value in artifacts.items()}
    revision_id = "rev-" + hashlib.sha256(capture_lib.canonical_bytes(hashes)).hexdigest()[:20]
    revision_dir = local / "revisions" / revision_id
    filenames = {
        "source": "world-squads-composed.json", "supplemental": "transfermarkt-squads.json",
        "gaps": "gaps.json", "allocation": "carrier-allocation.json",
        "assignment": "foreign-carrier-assignment.json", "intake": "source-intake.json",
        "ntf": "ntf-squads.json", "ntf_gaps": "ntf-gaps.json",
        "soccerbase": "soccerbase-august-squads.json",
        "soccerbase_gaps": "soccerbase-august-gaps.json",
    }
    rows: dict[str, dict[str, str]] = {}
    for name, value in artifacts.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
            raise ValueError(f"invalid revision artifact name: {name}")
        path = revision_dir / filenames.get(name, f"{name.replace('_', '-')}.json")
        digest = _write_immutable(path, value)
        rows[name] = {"path": str(path.relative_to(local)), "sha256": digest}
    manifest = {
        "artifacts": rows, "revision_id": revision_id, "schema_version": CURRENT_SCHEMA,
        "season": season,
    }
    payload = capture_lib.canonical_bytes(manifest)
    local.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".current-", suffix=".json", dir=local, delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, local / "current.json")
    return revision_id, manifest


def discover_base(season_dir: Path) -> Path:
    candidates: list[tuple[int, str, Path]] = []
    for path in (season_dir / "sources").glob("*footballsquads*.json"):
        try:
            value = _read(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if value.get("schema_version") == capture_lib.SCHEMA and isinstance(value.get("clubs"), list) and value["clubs"]:
            candidates.append((len(value["clubs"]), path.name, path))
    if not candidates:
        raise ValueError(f"{season_dir.name}: no canonical base squad capture")
    return max(candidates)[2]


def missing_scope(base: dict[str, Any], scope: list[dict[str, str]]) -> list[dict[str, str]]:
    base_groups = {
        allocation_lib.COUNTRY_GROUPS.get(str(club.get("country_catalog") or ""))
        for club in base["clubs"]
    } - {None}
    return [row for row in scope if allocation_lib.COUNTRY_GROUPS.get(row["country_catalog"]) not in base_groups]


def run_season(*, season: str, scope_paths: list[Path], output_root: Path, offline: bool, delay: float,
               with_ntf: bool = False) -> dict[str, Any]:
    season_dir = ROOT / "seasons" / season
    base_path = discover_base(season_dir)
    base = _read(base_path)
    scope_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for scope_path in scope_paths:
        rows, _digest = capture_lib.load_scope(scope_path)
        for row in rows:
            # Later explicitly named scopes are reviewed overrides. This is
            # useful when a source retires a competition code while preserving
            # its country/catalogue identity.
            scope_by_key[(row["country_catalog"], row["competition_catalog"])] = row
    scope = sorted(scope_by_key.values(), key=lambda row: (row["country_catalog"], row["competition_catalog"]))
    scope_sha = hashlib.sha256(capture_lib.canonical_bytes(scope)).hexdigest()
    selected_scope = missing_scope(base, scope)
    start_year = int(season[:4])
    local = output_root / season
    local.mkdir(parents=True, exist_ok=True)
    if selected_scope:
        # One season-level cache is shared by direct and batch invocations.
        cache_path = ROOT / ".local" / f"season-{season}" / "transfermarkt-historical-squad-cache-v1"
        cache = SnapshotCache(cache_path, offline=offline, delay=delay)
        supplemental, gaps = capture_lib.build_capture(
            season_start_year=start_year, scope=selected_scope, scope_sha256=scope_sha, cache=cache,
        )
        composed = compose_lib.compose(
            inputs=[(base_path.name, base, _sha(base_path)), ("transfermarkt-squads.json", supplemental, _document_sha(supplemental))],
            catalog=f"{start_year}-{start_year + 1}", label=f"{start_year}/{str(start_year + 1)[-2:]}",
        )
    else:
        # Still materialise the standard downstream contract. The output is a
        # byte-for-byte semantic copy of the canonical base, not a fake empty
        # supplement or a skipped season.
        supplemental = {"clubs": [], "summary": {"player_count": 0}}
        gaps = {"summary": {"gap_count": 0}}
        composed = dict(base)
    registry_path = season_dir / "fixed-carrier-registry.json"
    registry = _read(registry_path)
    allocation = allocation_lib.build_allocation(source=composed, registry=registry)
    ntf: dict[str, Any] | None = None
    ntf_gaps: dict[str, Any] | None = None
    if with_ntf:
        ntf, ntf_gaps = ntf_lib.capture(
            registry=registry, allocation=allocation, season_start_year=start_year,
            cache=ntf_lib.Cache(
                ROOT / ".local" / f"season-{season}" / "ntf-historical-carrier-squad-cache-v2",
                offline=offline, delay=delay,
            ),
        )
        if ntf["clubs"]:
            composed = compose_lib.compose(
                inputs=[("world-squads-transfermarkt.json", composed, _document_sha(composed)),
                        ("ntf-squads.json", ntf, _document_sha(ntf))],
                catalog=f"{start_year}-{start_year + 1}", label=f"{start_year}/{str(start_year + 1)[-2:]}",
            )
            allocation = allocation_lib.build_allocation(source=composed, registry=registry)
    assignment = intake_adapter.adapt(
        allocation=allocation, registry=registry, source=composed,
        assignment_id=f"world-{season}-expanded-assignment",
    )
    intake = intake_lib.build_intake(
        registry=registry, source_capture=composed, assignment=assignment,
        intake_id=f"world-{season}-expanded-intake",
    )
    artifacts: dict[str, Mapping[str, Any]] = {
        "source": composed, "supplemental": supplemental, "gaps": gaps,
        "allocation": allocation, "assignment": assignment, "intake": intake,
    }
    if ntf is not None and ntf_gaps is not None:
        artifacts.update({"ntf": ntf, "ntf_gaps": ntf_gaps})
    revision_id, current = _publish_revision(local=local, season=season, artifacts=artifacts)
    old_path = ROOT / ".local" / "season-batch-v1" / season / "carrier-allocation.json"
    old_count = int(_read(old_path).get("coverage", {}).get("assignment_count", 0)) if old_path.is_file() else 0
    return {
        "season": season, "status": "captured" if selected_scope else "base-materialised-no-missing-scoped-country",
        "base_club_count": len(base["clubs"]), "supplemental_club_count": len(supplemental["clubs"]),
        "supplemental_player_count": supplemental["summary"]["player_count"],
        "composed_club_count": len(composed["clubs"]), "allocation_count": allocation["coverage"]["assignment_count"],
        "allocation_delta": allocation["coverage"]["assignment_count"] - old_count,
        "gap_count": gaps["summary"]["gap_count"], "intake_sha256": current["artifacts"]["intake"]["sha256"],
        "revision_id": revision_id,
        "ntf_club_count": len(ntf["clubs"]) if ntf is not None else 0,
        "ntf_gap_count": ntf_gaps["summary"]["gap_count"] if ntf_gaps is not None else 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", action="append", required=True)
    parser.add_argument("--scope", action="append", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=ROOT / ".local/season-historical-squad-backfill-v1")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--with-ntf", action="store_true")
    parser.add_argument("--matrix-output", type=Path)
    args = parser.parse_args(argv)
    rows = [run_season(season=season, scope_paths=args.scope, output_root=args.output_root, offline=args.offline, delay=args.delay,
                       with_ntf=args.with_ntf)
            for season in args.season]
    matrix = {"schema_version": SCHEMA, "scopes": [{"path": str(path), "sha256": _sha(path)} for path in args.scope], "seasons": rows}
    matrix_path = args.matrix_output or args.output_root / "matrix.json"
    matrix_path.parent.mkdir(parents=True, exist_ok=True)
    matrix_path.write_bytes(capture_lib.canonical_bytes(matrix))
    print(json.dumps(rows, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
