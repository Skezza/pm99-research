#!/usr/bin/env python3
"""Build a disposable V3 native-boundary renderer/palette runtime proof."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import pm99_factory_kit_renderer_v3 as factory_renderer
from scripts.build_2015_factory_kit_runtime_probe_v1 import ProbeError, build_probe


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-materialisation", type=Path, required=True)
    parser.add_argument("--target-game-tree", type=Path, required=True)
    parser.add_argument("--source-club", default="Barcelona")
    parser.add_argument("--target-carrier", type=int, default=309)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_probe(
            materialisation=json.loads(args.candidate_materialisation.read_text(encoding="utf-8")),
            target_game_tree=args.target_game_tree,
            source_club=args.source_club,
            target_carrier=args.target_carrier,
            renderer_module=factory_renderer,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ProbeError) as exc:
        parser.error(str(exc))
        return 2
    result["schema_version"] = "pm99-2015-factory-kit-runtime-probe-v3"
    result["renderer"] = factory_renderer.RENDERER_ID
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": result["result"], "events": len(result["events"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
