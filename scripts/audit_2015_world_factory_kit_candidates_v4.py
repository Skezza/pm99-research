#!/usr/bin/env python3
"""Independently reproduce and audit V4 native-hem-contour candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import pm99_factory_kit_renderer_v4 as factory_renderer
from scripts.audit_2015_world_factory_kit_candidates_v1 import audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-materialisation", type=Path, required=True)
    parser.add_argument("--candidate-materialisation", type=Path, required=True)
    parser.add_argument("--clean-dbdat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(
            source=json.loads(args.source_materialisation.read_text(encoding="utf-8")),
            candidate=json.loads(args.candidate_materialisation.read_text(encoding="utf-8")),
            clean_dbdat=args.clean_dbdat,
            renderer_module=factory_renderer,
            renderer_id=factory_renderer.RENDERER_ID,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], **result["coverage"]}, sort_keys=True))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
