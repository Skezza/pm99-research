#!/usr/bin/env python3
"""Remove duplicate modern portraits from ownership-displaced player slots."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

SCHEMA = "pm99-world-2015-asset-candidate-manifest-v1"


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def build(*, manifest: dict[str, Any], ownership: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != SCHEMA:
        raise ValueError("asset manifest schema is unsupported")
    if ownership.get("schema_version") != "pm99-world-2015-person-ownership-decisions-v1":
        raise ValueError("ownership receipt schema is unsupported")
    result = copy.deepcopy(manifest)
    players: dict[tuple[int, int, int], dict[str, Any]] = {}
    for club in result.get("clubs", []):
        for player in club.get("players", []):
            key = (int(club["carrier_id"]), int(player["slot_index"]), int(player["player_carrier_id"]))
            if key in players:
                raise ValueError(f"duplicate asset player key: {key}")
            players[key] = player
    displaced_keys: set[tuple[int, int, int]] = set()
    retained_keys: set[tuple[int, int, int]] = set()
    for decision in ownership.get("decisions", []):
        retained = decision["retained"]
        retained_key = tuple(int(retained[key]) for key in ("team_carrier_id", "slot_index", "player_carrier_id"))
        if retained_key not in players or retained_key in retained_keys:
            raise ValueError(f"retained ownership player absent/shared: {retained_key}")
        retained_keys.add(retained_key)
        for displaced in decision.get("displaced", []):
            key = tuple(int(displaced[field]) for field in ("team_carrier_id", "slot_index", "player_carrier_id"))
            if displaced.get("disposition") != "preserve-native-carrier-row" or key not in players or key in displaced_keys:
                raise ValueError(f"invalid ownership displacement: {key}")
            displaced_keys.add(key)
            player = players[key]
            player.pop("fifa16_player_id", None)
            player.pop("fifa16_name", None)
            player.pop("fifa16_match_status", None)
            player["portrait"] = {
                "status": "preserve-native-carrier-portrait",
                "source_policy": "ownership-displaced-native-player-row; do-not-apply-duplicate-modern-portrait",
                "ownership_receipt_sha256": hashlib.sha256(canonical_bytes(ownership)).hexdigest(),
            }
            player["ownership_disposition"] = "preserve-native-carrier-row-and-native-portrait"
    if len(displaced_keys) != len(ownership.get("decisions", [])):
        raise ValueError("ownership receipt does not produce one displaced asset row per decision")
    statuses = Counter(str((player.get("portrait") or {}).get("status") or "") for player in players.values())
    result["coverage"] = dict(result.get("coverage") or {})
    result["coverage"]["portrait_status_counts"] = dict(sorted(statuses.items()))
    result["coverage"]["ownership_retained_portrait_count"] = len(retained_keys)
    result["coverage"]["ownership_displaced_native_portrait_preserve_count"] = len(displaced_keys)
    result["sources"] = dict(result.get("sources") or {})
    result["sources"]["person_ownership_decisions_sha256"] = hashlib.sha256(canonical_bytes(ownership)).hexdigest()
    result["policy"] = str(result.get("policy") or "") + "; ownership-displaced native rows preserve native portrait and never receive duplicate modern face"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--ownership", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = build(manifest=json.loads(args.manifest.read_text(encoding="utf-8")), ownership=json.loads(args.ownership.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps({"output": str(args.output), "ownership_displaced_native_portrait_preserve_count": result["coverage"]["ownership_displaced_native_portrait_preserve_count"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
