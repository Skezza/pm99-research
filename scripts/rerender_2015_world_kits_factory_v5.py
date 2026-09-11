#!/usr/bin/env python3
"""Create V5 native-tone-transfer 2015 kit candidates without game writes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import pm99_factory_kit_renderer_v5 as factory_renderer
from scripts.materialise_2015_world_kits import canonical_json_bytes, sha256_bytes
from scripts.rerender_2015_world_kits_factory_v1 import FactoryRerenderError, rerender


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materialisation", type=Path, required=True)
    parser.add_argument("--clean-dbdat", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        source_bytes = args.materialisation.read_bytes()
        result = rerender(
            materialisation=json.loads(source_bytes),
            clean_dbdat=args.clean_dbdat,
            output_dir=args.output_dir,
            renderer_module=factory_renderer,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, FactoryRerenderError) as exc:
        parser.error(str(exc))
        return 2
    result["renderer"]["source_materialisation_file_sha256"] = sha256_bytes(source_bytes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps({"rerendered": result["coverage"]["factory_template_rerendered_carrier_count"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
