#!/usr/bin/env python3
"""Audit the two foreign dd6360 native-cursor runtime mutation fixtures."""

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
    {
        "slug": "kluivert",
        "player": "Patrick Kluivert",
        "run_tag": "dd6360_native_kluivert_20260829",
        "receipt": ".local/research-probes/dd6360-mode1-native-20260829/dd6360-kluivert-native-probe.json",
        "title_token": "kluivert",
        "gap": 4,
        "nationality": 22,
    },
    {
        "slug": "guardiola",
        "player": "Josep Guardiola",
        "run_tag": "dd6360_native_guardiola_20260829",
        "receipt": ".local/research-probes/dd6360-mode1-native-guardiola-20260829/dd6360-guardiola-native-probe.json",
        "title_token": "guardiola",
        "gap": 3,
        "nationality": 27,
    },
)

_EXPECTED_AFTER = {
    "birth_day": 2,
    "birth_month": 8,
    "birth_year": 1966,
    "height_cm": 199,
    "weight_kg": 99,
    "skills": [99] * 9,
}


def _row(root: Path, case: dict[str, object]) -> dict[str, object]:
    artifact = root / str(case["run_tag"])
    summary_path = artifact / "summary.json"
    receipt_path = Path(str(case["receipt"]))
    if not storage_io.is_file(summary_path) or not storage_io.is_file(receipt_path):
        return {
            "slug": case["slug"],
            "player": case["player"],
            "result": "missing_evidence",
            "summary": str(summary_path),
            "receipt": str(receipt_path),
        }

    summary = json.loads(storage_io.read_text(summary_path, encoding='utf-8'))
    receipt = json.loads(storage_io.read_text(receipt_path, encoding='utf-8'))
    title = str(dict(summary.get("player_profile") or {}).get("player_name_ocr_normalized") or "")
    expected_phase = f"profile_only_{str(case['player']).lower().replace(' ', '_')}_done"
    profile_screens = list(storage_io.glob(artifact / 'screens', '*profile*.png'))
    after = dict(receipt.get("after") or {})
    checks = {
        "single_span_only": bool(receipt.get("unchanged_elsewhere")),
        "expected_native_gap": int(receipt.get("pre_marker_gap_bytes", -1)) == int(case["gap"]),
        "mutated_core_values_reparse": (
            all(after.get(key) == value for key, value in _EXPECTED_AFTER.items())
            and after.get("visible_nationality_code") == int(case["nationality"])
        ),
        "summary_success": bool(summary.get("success")),
        "window_detected": bool(summary.get("window_detected")),
        "no_crash": not bool(summary.get("crash_detected")),
        "profile_phase_reached": summary.get("phase_reached") == expected_phase,
        "profile_screenshot_present": bool(profile_screens),
        "profile_title_matches": str(case["title_token"]) in title,
    }
    return {
        "slug": case["slug"],
        "player": case["player"],
        "summary": str(summary_path),
        "receipt": str(receipt_path),
        "profile_title_ocr": title,
        "checks": checks,
        "result": "pass" if all(checks.values()) else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = [_row(args.artifact_root, case) for case in _CASES]
    result = {
        "schema_version": 1,
        "purpose": "Foreign dd6360 native-cursor same-span mutation proof",
        "case_count": len(rows),
        "pass_count": sum(row["result"] == "pass" for row in rows),
        "rows": rows,
    }
    result["result"] = "pass" if result["pass_count"] == result["case_count"] else "fail"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    storage_io.write_text(args.output, json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
