#!/usr/bin/env python3
"""Produce a machine-readable receipt for the Stars untouched-EXE profile proof."""

from __future__ import annotations

try:
    from scripts import json_storage_io_v1 as storage_io
except ModuleNotFoundError:
    import sys as _storage_sys
    from pathlib import Path as _StoragePath
    _storage_sys.path.insert(0, str(next(p for p in _StoragePath(__file__).resolve().parents if (p / 'scripts/json_storage_io_v1.py').is_file())))
    from scripts import json_storage_io_v1 as storage_io

import argparse
import json
from pathlib import Path


_CASES = (
    ("rafael_martin_vazquez", "Rafael Martin Vazquez", ("vazquez",)),
    ("rafa_paz", "Rafa Paz", ("paz",)),
    ("marcio_santos", "Marcio Santos", ("santos",)),
    ("luis_hernandez", "Luis Hernandez", ("hernandez",)),
    # PM99's small anti-aliased ñ often OCRs as "fi".  The screenshot is
    # retained and manually checked; either form is a narrowly scoped title
    # token for this one exact record, not a relaxed first-result assertion.
    ("carlos_munoz", "Carlos Munoz", ("munoz", "mufioz")),
    ("leonel_alvarez", "Leonel Alvarez", ("alvarez",)),
    ("carlos_valderrama", "Carlos Valderrama", ("valderrama",)),
    ("marco_etcheverry", "Marco Etcheverry", ("etcheverry",)),
    ("diego_sonora", "Diego Sonora", ("sonora",)),
    ("alexi_lalas", "Alexi Lalas", ("lalas",)),
)


def _artifact_dir(root: Path, slug: str) -> Path:
    matches = [path for path in storage_io.glob(root, f'stars_db_only_{slug}_*') if path.is_dir()]
    if not matches:
        return root / f"stars_db_only_{slug}_MISSING"
    # Run tags contain both historical timestamps and human retry suffixes
    # (`r9`, `r10`, ...); lexical sorting chooses r9 over r10.  The last
    # completed local artifact is the relevant proof candidate.
    return max(matches, key=lambda path: storage_io.stat_result(path).st_mtime_ns)


def audit(root: Path) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for slug, player, title_tokens in _CASES:
        artifact_dir = _artifact_dir(root, slug)
        summary_path = artifact_dir / "summary.json"
        if not storage_io.exists(summary_path):
            rows.append({"slug": slug, "player": player, "result": "missing_artifact", "artifact_dir": str(artifact_dir)})
            continue
        summary = json.loads(storage_io.read_text(summary_path, encoding='utf-8'))
        screenshots = sorted(storage_io.glob(artifact_dir / 'screens', f'*inspect_{slug}_profile.png'))
        expected_phase = f"profile_only_{slug}_done"
        title_ocr = str(dict(summary.get("player_profile") or {}).get("player_name_ocr_normalized") or "")
        checks = {
            "summary_success": bool(summary.get("success")),
            "window_detected": bool(summary.get("window_detected")),
            "no_crash": not bool(summary.get("crash_detected")),
            "phase_reached": summary.get("phase_reached") == expected_phase,
            "profile_screenshot_present": bool(screenshots),
            "profile_title_matches_expected_player": any(token in title_ocr for token in title_tokens),
        }
        rows.append(
            {
                "slug": slug,
                "player": player,
                "artifact_dir": str(artifact_dir),
                "summary": str(summary_path),
                "profile_screenshot": str(screenshots[-1]) if screenshots else None,
                "profile_title_ocr": title_ocr,
                "accepted_title_tokens": list(title_tokens),
                "checks": checks,
                "result": "pass" if all(checks.values()) else "fail",
            }
        )
    return {
        "schema_version": 1,
        "purpose": "Stars database-only profile proof against an unmodified MANAGPRE.EXE",
        "case_count": len(rows),
        "pass_count": sum(1 for row in rows if row["result"] == "pass"),
        "rows": rows,
        "result": "pass" if rows and all(row["result"] == "pass" for row in rows) else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.artifact_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    storage_io.write_text(args.output, json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
