#!/usr/bin/env python3
"""Coordinate deterministic source-to-candidate authoring for many seasons.

This controller deliberately stops at reviewable authoring artifacts.  It
never compiles or labels a game database.  For each requested season it picks
the largest valid canonical FootballSquads capture, runs the fixed-carrier
allocation, and runs the existing package-draft and editorial-rating layers
when their complete inputs are present.  The matrix records every absent or
rejected lane as a hard blocker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_carrier_allocation_v1 as carrier_allocation  # noqa: E402
from scripts import season_editorial_ratings_v1 as editorial_ratings  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_source_intake_v1 as source_intake  # noqa: E402
from scripts import season_source_package_builder_v1 as package_builder  # noqa: E402


SCHEMA = "pm99-season-batch-authoring-matrix-v1"
SELECTION_SCHEMA = "pm99-season-source-selection-v1"
CAPTURE_SCHEMA = carrier_allocation.SOURCE_SCHEMA
REGISTRY_NAME = "fixed-carrier-registry.json"
INTAKE_NAME = "source-intake.json"
RATING_INPUT_NAME = "editorial-rating-input.json"
REQUIRED_EVIDENCE = {
    "opening-lineups": "opening-lineups.json",
    "target-season-managers": "managers.json",
    "target-season-kits": "kits.json",
}


class BatchAuthoringError(ValueError):
    """The batch invocation or one of its shared inputs is unsafe."""


def canonical_json_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def document_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _read_canonical(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise BatchAuthoringError(f"input is not canonical JSON: {path}")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(dict(value)))


def _capture_size(capture: Mapping[str, Any]) -> tuple[int, int]:
    clubs = capture.get("clubs")
    if capture.get("schema_version") != CAPTURE_SCHEMA or not isinstance(clubs, list):
        raise BatchAuthoringError(f"capture must use {CAPTURE_SCHEMA}")
    player_count = 0
    for club in clubs:
        if not isinstance(club, Mapping) or not isinstance(club.get("players"), list):
            raise BatchAuthoringError("capture clubs must contain player lists")
        player_count += len(club["players"])
    if not clubs:
        raise BatchAuthoringError("capture contains no clubs")
    return len(clubs), player_count


def select_capture(season_dir: Path) -> tuple[Path | None, dict[str, Any] | None, list[dict[str, str]]]:
    """Return the largest valid canonical capture and rejected-candidate log."""
    accepted: list[tuple[int, int, str, Path, dict[str, Any]]] = []
    rejected: list[dict[str, str]] = []
    source_dir = season_dir / "sources"
    for path in sorted(source_dir.glob("*.json")) if source_dir.is_dir() else []:
        relative = path.relative_to(season_dir).as_posix()
        try:
            capture = _read_canonical(path)
            club_count, player_count = _capture_size(capture)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, BatchAuthoringError) as exc:
            rejected.append({"path": relative, "reason": str(exc)})
            continue
        accepted.append((club_count, player_count, relative, path, capture))
    if not accepted:
        return None, None, rejected
    # Largest club coverage, then player coverage.  A lexical relative path is
    # the stable tie-breaker and is intentionally independent of mtime.
    accepted.sort(key=lambda row: (-row[0], -row[1], row[2]))
    chosen = accepted[0]
    return chosen[3], chosen[4], rejected


def _block(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, **details, "message": message}


def _lane_input(season_dir: Path, name: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    path = season_dir / name
    if not path.is_file():
        return None, {"status": "missing", "path": name}
    try:
        value = _read_canonical(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, BatchAuthoringError) as exc:
        return None, {"status": "invalid", "path": name, "error": str(exc)}
    return value, {"status": "available", "path": name, "sha256": document_sha256(value)}


def author_season(
    *, season_id: str, season_dir: Path, output_dir: Path,
    template: Mapping[str, Any] | None,
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    outputs: dict[str, Any] = {}
    lanes: dict[str, Any] = {}
    capture_path, capture, rejected = select_capture(season_dir)
    if capture is None or capture_path is None:
        blockers.append(_block("valid-footballsquads-capture-missing", "No valid canonical squad capture is available."))
        selection = {"schema_version": SELECTION_SCHEMA, "season_id": season_id, "selected": None, "rejected": rejected}
        _write(output_dir / "source-selection.json", selection)
        outputs["source_selection"] = "source-selection.json"
        return _row(season_id, lanes, outputs, blockers)

    club_count, player_count = _capture_size(capture)
    source_rel = capture_path.relative_to(season_dir).as_posix()
    selection = {
        "schema_version": SELECTION_SCHEMA,
        "season_id": season_id,
        "selected": {
            "path": source_rel,
            "sha256": document_sha256(capture),
            "club_count": club_count,
            "player_count": player_count,
        },
        "rejected": rejected,
    }
    _write(output_dir / "source-selection.json", selection)
    outputs["source_selection"] = "source-selection.json"
    lanes["source_capture"] = {"status": "selected", **selection["selected"]}

    registry, registry_lane = _lane_input(season_dir, REGISTRY_NAME)
    lanes["fixed_carrier_registry"] = registry_lane
    allocation: dict[str, Any] | None = None
    if registry is None:
        blockers.append(_block("fixed-carrier-registry-missing-or-invalid", "Carrier allocation requires a valid fixed-carrier registry."))
    else:
        try:
            allocation = carrier_allocation.build_allocation(source=capture, registry=registry)
            _write(output_dir / "carrier-allocation.json", allocation)
            outputs["carrier_allocation"] = "carrier-allocation.json"
            lanes["carrier_allocation"] = {"status": "materialised", "coverage": allocation["coverage"]}
            if allocation["gaps"]:
                blockers.append(_block("carrier-allocation-gaps", "The deterministic allocation retains unresolved carrier or capacity dispositions.", count=len(allocation["gaps"])))
        except (ValueError, KeyError, TypeError) as exc:
            lanes["carrier_allocation"] = {"status": "invalid", "error": str(exc)}
            blockers.append(_block("carrier-allocation-failed", "Carrier allocation rejected the selected inputs."))

    intake, intake_lane = _lane_input(season_dir, INTAKE_NAME)
    lanes["source_intake"] = intake_lane
    if intake is not None and intake.get("source_capture_sha256") != document_sha256(capture):
        lanes["source_intake"] = {**intake_lane, "status": "stale-for-selected-capture"}
        intake = None
        blockers.append(_block("source-intake-stale", "The retained source intake is not hash-bound to the selected largest capture."))
    elif intake is None:
        blockers.append(_block("source-intake-missing-or-invalid", "Package drafting requires a valid source intake."))

    if template is None:
        blockers.append(_block("template-package-missing", "Package drafting requires an explicit strict template package."))
    elif registry is not None and intake is not None:
        try:
            draft, audit = package_builder.build_draft(
                template=template,
                source_intake=intake,
                registry=registry,
                carrier_allocation=allocation,
                template_prevalidated=True,
            )
            _write(output_dir / "draft-season-package.json", draft)
            _write(output_dir / "source-package-build-audit.json", audit)
            outputs["draft_package"] = "draft-season-package.json"
            outputs["package_audit"] = "source-package-build-audit.json"
            lanes["package_candidate"] = {"status": "draft-materialised", "release_eligible": bool(audit["release_eligible"]), "coverage": audit["coverage"]}
            blockers.extend(dict(item) for item in audit["hard_blockers"])
        except (ValueError, KeyError, TypeError) as exc:
            lanes["package_candidate"] = {"status": "invalid", "error": str(exc)}
            blockers.append(_block("package-candidate-failed", "The package draft layer rejected its inputs."))

    rating_input, rating_lane = _lane_input(season_dir, RATING_INPUT_NAME)
    lanes["editorial_ratings"] = rating_lane
    if rating_input is None:
        blockers.append(_block("editorial-rating-input-missing-or-invalid", "A pinned rating input is required for deterministic ratings."))
    else:
        try:
            rating_output = editorial_ratings.build_rating_output(rating_input)
            _write(output_dir / "editorial-ratings.json", rating_output)
            outputs["editorial_ratings"] = "editorial-ratings.json"
            lanes["editorial_ratings"] = {"status": "materialised", "coverage": rating_output["coverage"]}
        except (ValueError, KeyError, TypeError) as exc:
            lanes["editorial_ratings"] = {"status": "invalid", "error": str(exc)}
            blockers.append(_block("editorial-ratings-failed", "The deterministic rating layer rejected its input."))

    for lane, filename in REQUIRED_EVIDENCE.items():
        value, state = _lane_input(season_dir, filename)
        lanes[lane] = state
        if value is None:
            blockers.append(_block(f"{lane}-input-missing-or-invalid", f"The {lane} evidence lane is mandatory for a playable historical candidate."))

    return _row(season_id, lanes, outputs, blockers)


def _row(season_id: str, lanes: Mapping[str, Any], outputs: Mapping[str, Any], blockers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted((dict(item) for item in blockers), key=lambda item: (str(item.get("code")), canonical_json_bytes(item)))
    return {
        "season_id": season_id,
        "status": "candidate-ready" if not ordered else "blocked",
        "lanes": dict(sorted(lanes.items())),
        "outputs": dict(sorted(outputs.items())),
        "hard_blockers": ordered,
    }


def build_batch(
    *, seasons_root: Path, output_root: Path, selected: Sequence[str],
    template_package: Path | None,
) -> dict[str, Any]:
    if len(selected) != len(set(selected)):
        raise BatchAuthoringError("selected season IDs must be unique")
    template = _read_canonical(template_package) if template_package is not None else None
    if template is not None:
        package_v2.validate_package(template, strict=True)
    rows = [
        author_season(
            season_id=season_id,
            season_dir=seasons_root / season_id,
            output_dir=output_root / season_id,
            template=template,
        )
        for season_id in sorted(selected)
    ]
    matrix = {
        "schema_version": SCHEMA,
        "rows": rows,
        "summary": {
            "season_count": len(rows),
            "candidate_ready_count": sum(row["status"] == "candidate-ready" for row in rows),
            "blocked_count": sum(row["status"] == "blocked" for row in rows),
            "draft_package_count": sum("draft_package" in row["outputs"] for row in rows),
            "database_count": 0,
        },
    }
    _write(output_root / "matrix.json", matrix)
    return matrix


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons-root", type=Path, default=ROOT / "seasons")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--template-package", type=Path)
    parser.add_argument("seasons", nargs="+")
    args = parser.parse_args(argv)
    try:
        matrix = build_batch(
            seasons_root=args.seasons_root,
            output_root=args.output_root,
            selected=args.seasons,
            template_package=args.template_package,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(matrix["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
