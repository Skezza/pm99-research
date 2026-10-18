#!/usr/bin/env python3
"""Audit the intended visual delta between factory-template V1 and V2.

This is not a substitute for either renderer's independent reproduction
audit.  It proves a useful additional invariant: V2 changes an asset exactly
when the explicit reviewed template policy selects different original PM99
artwork.  Plain-kit assets therefore cannot drift merely because V2 exists.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.materialise_2015_world_kits import ARCHIVES  # noqa: E402
from scripts import pm99_factory_kit_renderer_v1 as renderer_v1  # noqa: E402
from scripts import pm99_factory_kit_renderer_v2 as renderer_v2  # noqa: E402
from scripts.rerender_2015_world_kits_factory_v1 import APPROVED_STATUSES  # noqa: E402


def _rows(materialisation: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    return {
        int(row["carrier_id"]): row
        for row in materialisation.get("rows") or []
        if isinstance(row, Mapping) and row.get("status") in APPROVED_STATUSES
    }


def audit(v1: Mapping[str, Any], v2: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if (v1.get("renderer") or {}).get("id") != renderer_v1.RENDERER_ID:
        errors.append({"code": "wrong-v1-renderer"})
    if (v2.get("renderer") or {}).get("id") != renderer_v2.RENDERER_ID:
        errors.append({"code": "wrong-v2-renderer"})
    v1_rows, v2_rows = _rows(v1), _rows(v2)
    if set(v1_rows) != set(v2_rows):
        errors.append({"code": "approved-carrier-set-mismatch"})

    checked = changed = 0
    patterns = Counter()
    changed_patterns = Counter()
    for carrier in sorted(set(v1_rows) & set(v2_rows)):
        first, second = v1_rows[carrier], v2_rows[carrier]
        recipe = second.get("render_recipe")
        if not isinstance(recipe, Mapping) or recipe != first.get("render_recipe"):
            errors.append({"code": "recipe-drift", "carrier_id": carrier})
            continue
        pattern = str(recipe.get("pattern") or "unknown")
        for archive in ARCHIVES:
            first_asset = (first.get("assets") or {}).get(archive)
            second_asset = (second.get("assets") or {}).get(archive)
            if not isinstance(first_asset, Mapping) or not isinstance(second_asset, Mapping):
                errors.append({"code": "asset-missing", "carrier_id": carrier, "archive": archive})
                continue
            v1_template = renderer_v1.factory_template_carrier(archive, dict(recipe))
            v2_template = renderer_v2.factory_template_carrier(archive, dict(recipe))
            did_change = first_asset.get("sha256") != second_asset.get("sha256")
            expected_change = v1_template != v2_template
            if did_change != expected_change:
                errors.append(
                    {
                        "code": "unexpected-asset-delta",
                        "carrier_id": carrier,
                        "archive": archive,
                        "pattern": pattern,
                        "v1_template": v1_template,
                        "v2_template": v2_template,
                        "changed": did_change,
                    }
                )
            checked += 1
            patterns[pattern] += 1
            if did_change:
                changed += 1
                changed_patterns[pattern] += 1
    return {
        "schema_version": "pm99-2015-factory-kit-v1-v2-differential-audit-v1",
        "result": "pass" if not errors else "fail",
        "coverage": {
            "approved_carrier_count": len(v1_rows),
            "checked_asset_count": checked,
            "changed_asset_count": changed,
            "unchanged_asset_count": checked - changed,
            "assets_by_recipe_pattern": dict(sorted(patterns.items())),
            "changed_assets_by_recipe_pattern": dict(sorted(changed_patterns.items())),
            "error_count": len(errors),
        },
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-materialisation", type=Path, required=True)
    parser.add_argument("--v2-materialisation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(
            json.loads(args.v1_materialisation.read_text(encoding="utf-8")),
            json.loads(args.v2_materialisation.read_text(encoding="utf-8")),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, KeyError) as exc:
        parser.error(str(exc))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], **result["coverage"]}, sort_keys=True))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
