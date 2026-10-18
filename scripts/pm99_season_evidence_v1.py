#!/usr/bin/env python3
"""List the exact registered Line-Up screenshot for each season release."""

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


def evidence_row(season: str) -> dict[str, object]:
    release = registry.load_preferred_release(season)
    if release.attestation_path is None:
        return {"season": season, "release_id": release.release_id, "attested": False, "screenshot": None}
    issues = registry._validate_runtime_attestation(release)
    attestation = pipeline.read_json_file(release.attestation_path)
    receipts = attestation.get("runtime_receipts") or []
    receipt = receipts[0] if len(receipts) == 1 and isinstance(receipts[0], dict) else {}
    return {
        "season": season,
        "release_id": release.release_id,
        "attested": not issues,
        "screenshot": receipt.get("lineup_screenshot"),
        "screenshot_sha256": receipt.get("lineup_screenshot_sha256"),
        "team_identity": receipt.get("team_identity"),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season", nargs="?", default="all")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    seasons = registry.supported_seasons() if args.season == "all" else [pipeline.normalise_season_id(args.season)]
    rows = [evidence_row(season) for season in seasons]
    if args.json:
        print(json.dumps({"season_count": len(rows), "evidence": rows}, indent=2, sort_keys=True))
    else:
        for row in rows:
            state = "verified" if row["attested"] else "missing"
            print(f"{row['season']}  {state:<8}  {row['screenshot'] or '-'}")
    return 0 if all(row["attested"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
