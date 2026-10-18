#!/usr/bin/env python3
"""Report the preferred registered PM99 season releases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402


def status(season: str, *, verify: bool) -> dict[str, object]:
    release = registry.load_preferred_release(season)
    playable = registry.validate_preferred_release(season, level="playable")
    qa_status = release.locator.get("qa_status", "not-recorded")
    result: dict[str, object] = {
        "season": release.season,
        "release_id": release.release_id,
        "technical_status": release.locator.get("technical_status"),
        "editorial_warning_count": (
            release.locator.get("editorial_warning_count") if qa_status == "pass" else None
        ),
        "editorial_status": release.locator.get("editorial_status", "not-recorded"),
        "qa_status": qa_status,
        "game": registry.relative_workspace_path(release.game_path),
        "package": registry.relative_workspace_path(release.package_path),
        "manifest_registered": release.manifest_sha256 is not None,
        "runtime_attested": release.attestation_path is not None,
        "import_issue_count": len(release.locator.get("import_issues") or []),
        "playable": playable["valid"],
    }
    if verify:
        result["playable_validation"] = playable
        result["release_validation"] = registry.validate_preferred_release(season, level="release")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", nargs="?", default="all")
    parser.add_argument("--verify", action="store_true", help="rehash the registered game and release")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    seasons = registry.supported_seasons() if args.season == "all" else [pipeline.normalise_season_id(args.season)]
    rows = [status(season, verify=args.verify) for season in seasons]
    payload = {
        "schema_version": "pm99-season-release-status-v2",
        "season_count": len(rows),
        "playable_count": sum(row.get("playable") is True for row in rows),
        "technically_verified_count": sum(row.get("technical_status") == "technically-verified" for row in rows),
        "inconsistent_count": sum(row.get("technical_status") == "inconsistent" for row in rows),
        "seasons": rows,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"{payload['season_count']} registered seasons: "
            f"{payload['playable_count']} playable, "
            f"{payload['technically_verified_count']} technically verified, "
            f"{payload['inconsistent_count']} inconsistent"
        )
        for row in rows:
            warning_count = row["editorial_warning_count"]
            warning_label = str(warning_count) if isinstance(warning_count, int) else "not reviewed"
            print(
                f"{row['season']}  {'playable' if row['playable'] else 'not-playable':<12}  "
                f"{row['technical_status']:<21}  "
                f"{row['release_id']}  QA: {row['qa_status']}  "
                f"editorial warnings: {warning_label}"
            )
    if args.verify:
        return 0 if all(
            isinstance(row.get("release_validation"), dict)
            and row["release_validation"].get("valid") is True
            for row in rows
        ) else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
