#!/usr/bin/env python3
"""Extract PM99 screenshot ROL. numeric-box crops and compare with dd6361 trailer fields.

This is a reverse-engineering aid for the tiny on-screen `ROL.` numeric selector shown in
player screenshots (e.g. "0", "1", "8"). The current working finding is negative:
the displayed ROL. numeric value does not directly equal any one of the solved dd6361
trailer fields (`role_ratings5`, `byte16`) in the 8-player seed set.

Because OCR on the tiny box is unreliable, this script:
1) crops/enlarges the box deterministically for manual verification
2) stores user/manual readings (when supplied)
3) joins those readings to `probe_bio_trailer_stats.py` output for comparison
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import probe_bio_trailer_stats as trailer_probe  # type: ignore


# Empirically calibrated for the user's 640x480 PM99 screenshots in `.local/PlayerStills/`.
ROL_BOX_640 = (48, 108, 94, 138)  # x1, y1, x2, y2


DEFAULT_MANUAL_READINGS = {
    "Peter Boleslaw SCHMEICHEL": 2,
    "David Robert BECKHAM": 8,
    "Paul SCHOLES": 1,
    "Jaap STAM": 4,
    "Andrew Alexander COLE": 8,
    "Ryan Joseph GIGGS": 1,
    "Dwight YORKE": 3,
    "Graham KAVANAGH": 0,
}


def _iter_pngs(path: Path) -> list[Path]:
    return sorted([p for p in path.glob("*.png") if p.is_file()])


def _guess_name_from_filename(stem: str) -> str:
    # "David Beckham" -> "David Beckham" (later matched by surname fallback against dd6361 names)
    return stem.replace("_", " ")


def _extract_crop(src_path: Path, out_dir: Path, scale: int = 16) -> dict[str, Any]:
    img = Image.open(src_path).convert("RGB")
    crop = img.crop(ROL_BOX_640)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{src_path.stem.replace(' ', '_')}_rolbox.png"
    crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.NEAREST).save(out_path)
    return {
        "file": src_path.name,
        "image_size": [img.width, img.height],
        "rol_box_xyxy": list(ROL_BOX_640),
        "crop_output": str(out_path),
        "filename_name_guess": _guess_name_from_filename(src_path.stem),
    }


def _load_manual_readings(path: Path | None) -> dict[str, int]:
    if path is None:
        return dict(DEFAULT_MANUAL_READINGS)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    if isinstance(payload, dict):
        for k, v in payload.items():
            try:
                out[str(k)] = int(v)
            except Exception:
                continue
    return out


def _load_example_role_labels(example_file: Path | None) -> dict[str, dict[str, Any]]:
    if example_file is None or not example_file.exists():
        return {}
    try:
        return trailer_probe._parse_example_player_data(example_file)
    except Exception:
        return {}


def _find_bio_row_for_name(
    rows: list[dict[str, Any]],
    screenshot_name_guess: str,
) -> dict[str, Any] | None:
    q = trailer_probe._norm_name(screenshot_name_guess)
    # exact
    for row in rows:
        if trailer_probe._norm_name(str(row.get("name", ""))) == q:
            return row
    # substring
    for row in rows:
        if q and q in trailer_probe._norm_name(str(row.get("name", ""))):
            return row
    # surname fallback
    q_parts = q.split()
    if q_parts:
        surname = q_parts[-1]
        for row in rows:
            r_parts = trailer_probe._norm_name(str(row.get("name", ""))).split()
            if r_parts and r_parts[-1] == surname:
                return row
    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract PM99 screenshot ROL numeric box crops and compare to dd6361 trailer fields")
    p.add_argument(
        "--screenshots-dir",
        default=str(REPO_ROOT / ".local" / "PlayerStills"),
        help="Directory containing PM99 screenshot PNGs",
    )
    p.add_argument(
        "--player-file",
        default=str(REPO_ROOT / "DBDAT" / "JUG98030.FDI"),
        help="Path to JUG98030.FDI (for dd6361 trailer extraction)",
    )
    p.add_argument(
        "--manual-readings-json",
        help="Optional JSON mapping dd6361 full names (or screenshot names) to manually read ROL numbers",
    )
    p.add_argument(
        "--example-data",
        default=str(REPO_ROOT / ".local" / "PlayerStills" / "ExamplePlayerData.txt"),
        help="Optional OCR/screenshot text file for role-label joins",
    )
    p.add_argument(
        "--crop-output-dir",
        default=str(Path("/tmp") / "pm99_rol_box_crops"),
        help="Directory to write enlarged ROL numeric-box crops",
    )
    p.add_argument("--json-output", help="Write JSON report to this path")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    screenshots_dir = Path(args.screenshots_dir)
    player_file = Path(args.player_file)
    crop_out_dir = Path(args.crop_output_dir)
    manual_map = _load_manual_readings(Path(args.manual_readings_json) if args.manual_readings_json else None)
    example_map = _load_example_role_labels(Path(args.example_data) if getattr(args, "example_data", None) else None)

    crop_rows: list[dict[str, Any]] = []
    if screenshots_dir.exists():
        for png in _iter_pngs(screenshots_dir):
            if png.name.lower() == "exampleplayerdata.txt":
                continue
            crop_rows.append(_extract_crop(png, crop_out_dir))

    # Collect all dd6361 rows (fast enough for one-off reverse engineering runs).
    entries = trailer_probe._iter_decoded_entries(player_file)
    markers = trailer_probe._collect_bio_markers(entries)
    bio_rows: list[dict[str, Any]] = []
    for idx, marker in enumerate(markers[:-1]):
        name = marker.get("name")
        if not name:
            continue
        cont = trailer_probe._assemble_bio_continuation(entries, marker, markers[idx + 1])
        trailer_info = trailer_probe._extract_trailer_from_bio_continuation(cont)
        if trailer_info is None:
            continue
        bio_rows.append({"name": name, **trailer_info})

    comparisons: list[dict[str, Any]] = []
    for row in crop_rows:
        guess = str(row.get("filename_name_guess") or "")
        bio = _find_bio_row_for_name(bio_rows, guess)
        entry: dict[str, Any] = dict(row)
        if bio is not None:
            dd_name = str(bio.get("name"))
            entry["dd6361_bio_name"] = dd_name
            entry["mapped10"] = bio.get("mapped10")
            entry["role_ratings5"] = bio.get("role_ratings5")
            entry["unknown_byte16_candidate"] = bio.get("unknown_byte16_candidate")

            manual_val = None
            # Try exact dd6361 name first, then screenshot guess.
            if dd_name in manual_map:
                manual_val = manual_map[dd_name]
            elif guess in manual_map:
                manual_val = manual_map[guess]
            else:
                # surname fallback
                dd_surname = trailer_probe._norm_name(dd_name).split()[-1] if trailer_probe._norm_name(dd_name).split() else ""
                for k, v in manual_map.items():
                    parts = trailer_probe._norm_name(k).split()
                    if parts and dd_surname and parts[-1] == dd_surname:
                        manual_val = int(v)
                        break

            if manual_val is not None:
                role_vals = [int(bio["role_ratings5"][f"role_{i}"]) for i in range(1, 6)]
                entry["rol_num_manual"] = int(manual_val)
                entry["rol_num_matches_any_role_ratings5_value"] = int(manual_val) in set(role_vals)
                entry["rol_num_equals_byte16"] = int(manual_val) == int(bio["unknown_byte16_candidate"])
                entry["role_ratings5_argmax_index0"] = max(range(5), key=lambda i: (role_vals[i], -i))
                entry["role_ratings5_argmin_index0"] = min(range(5), key=lambda i: (role_vals[i], i))
                entry["role_ratings5_values"] = role_vals
                entry["rol_num_matches_argmax_index0"] = int(manual_val) == int(entry["role_ratings5_argmax_index0"])
                entry["rol_num_matches_argmin_index0"] = int(manual_val) == int(entry["role_ratings5_argmin_index0"])

            # Join OCR role label (exact or surname fallback) for duplicate-code analysis.
            exact = example_map.get(trailer_probe._norm_name(dd_name))
            role_entry = exact
            if role_entry is None:
                dd_surname = trailer_probe._norm_name(dd_name).split()[-1] if trailer_probe._norm_name(dd_name).split() else ""
                for k, v in example_map.items():
                    parts = k.split()
                    if parts and dd_surname and parts[-1] == dd_surname:
                        role_entry = v
                        break
            if role_entry is not None:
                entry["example_role_label"] = role_entry.get("role_label")
                entry["example_position"] = role_entry.get("position")
        comparisons.append(entry)

    with_manual = [r for r in comparisons if "rol_num_manual" in r]
    rol_num_to_labels: dict[str, set[str]] = {}
    for row in with_manual:
        if "rol_num_manual" not in row:
            continue
        label = str(row.get("example_role_label") or "").strip()
        if not label:
            continue
        key = str(int(row["rol_num_manual"]))
        rol_num_to_labels.setdefault(key, set()).add(label)
    rol_num_to_labels_json = {k: sorted(v) for k, v in sorted(rol_num_to_labels.items(), key=lambda kv: int(kv[0]))}
    non_unique_codes = {
        k: labels for k, labels in rol_num_to_labels_json.items() if len(labels) > 1
    }

    payload = {
        "screenshots_dir": str(screenshots_dir),
        "player_file": str(player_file),
        "rol_box_xyxy_640": list(ROL_BOX_640),
        "crop_output_dir": str(crop_out_dir),
        "screenshot_count": len(crop_rows),
        "dd6361_bio_row_count": len(bio_rows),
        "manual_readings_count": len(manual_map),
        "manual_comparison_count": len(with_manual),
        "manual_summary": {
            "rol_num_matches_any_role_ratings5_value_count": sum(
                1 for r in with_manual if r.get("rol_num_matches_any_role_ratings5_value") is True
            ),
            "rol_num_equals_byte16_count": sum(
                1 for r in with_manual if r.get("rol_num_equals_byte16") is True
            ),
            "rol_num_matches_argmax_index0_count": sum(
                1 for r in with_manual if r.get("rol_num_matches_argmax_index0") is True
            ),
            "rol_num_matches_argmin_index0_count": sum(
                1 for r in with_manual if r.get("rol_num_matches_argmin_index0") is True
            ),
            "rol_num_to_role_labels": rol_num_to_labels_json,
            "rol_num_non_unique_role_label_codes": non_unique_codes,
        },
        "notes": [
            "Crops are calibrated for the provided 640x480 PM99 screenshots.",
            "Manual ROL numeric readings are currently used instead of OCR due to tiny glyph size.",
            "Current seed-8 evidence indicates the displayed ROL number is not a direct role_ratings5 value, argmax/argmin role slot, or byte16.",
        ],
        "comparisons": comparisons,
    }

    text = json.dumps(payload, indent=2)
    if args.json_output:
        out_path = Path(args.json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
