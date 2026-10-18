#!/usr/bin/env python3
"""Acquire distinct, same-country 2015 squads for duplicate club carriers."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.supplement_2015_ntf_with_transfermarkt import _get, parse_squad

SCHEMA = "pm99-footballsquads-season-capture-v1"
TARGETS = {
    225: ("italy", "Carpi FC 1909", "carpi-fc-1909", 4102),
    250: ("italy", "Chievo Verona", "chievo-verona", 862),
    421: ("germany", "1. FC Koln", "1-fc-koln", 3),
    871: ("belgium", "Royal Antwerp FC", "royal-antwerpen-fc", 1096),
    872: ("belgium", "KAS Eupen", "kas-eupen", 1245),
    1111: ("switzerland", "FC Lausanne-Sport", "fc-lausanne-sport", 527),
    1112: ("switzerland", "Neuchatel Xamax FCS", "neuchatel-xamax", 625),
    3326: ("eng", "Stockport County", "stockport-county", 1098),
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def acquire(draft: dict[str, Any], cache_root: Path, fetch: Callable[[str], bytes] = _get) -> dict[str, Any]:
    proposals = {int(x["carrier_id"]): x for x in draft["proposals"]}
    clubs = []
    for carrier_id, (country, name, slug, club_id) in sorted(TARGETS.items()):
        proposal = proposals[carrier_id]
        url = f"https://www.transfermarkt.com/{slug}/kader/verein/{club_id}/saison_id/2015"
        rel = Path(f"transfermarkt-duplicate-closeout/{country}/{carrier_id}-{club_id}.html")
        path = cache_root / rel
        payload = path.read_bytes() if path.is_file() else fetch(url)
        players = parse_squad(payload)
        capacity = int(proposal["fixed_roster_slot_count"])
        if len(players) < capacity:
            raise ValueError(f"pinned squad short for carrier {carrier_id}: {len(players)}/{capacity}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        clubs.append({
            "candidate_carrier_id": carrier_id, "candidate_baseline_name": proposal["baseline_name"],
            "fixed_roster_slot_count": capacity, "country_catalog": country,
            "competition_catalog": "transfermarkt-2015-duplicate-closeout", "club_name": name,
            "competition_name": "Transfermarkt historical squad page (2015 season)",
            "source_path": rel.as_posix(), "source_sha256": hashlib.sha256(payload).hexdigest(),
            "source_url": url, "source_season_label": "2015", "players": players,
            "capture_note": "Distinct same-country 2015 club replacing an accidental duplicate identity",
        })
    return {"schema_version": SCHEMA, "source": {"title": "Transfermarkt duplicate-club closeout", "retrieved_on": date.today().isoformat()},
            "season": {"catalog": "2015-world-duplicate-closeout", "label": "2015/16"}, "clubs": clubs,
            "summary": {"club_count": len(clubs), "player_count": sum(len(c["players"]) for c in clubs)}}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--draft", type=Path, required=True); ap.add_argument("--cache-root", type=Path, required=True); ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args(); result = acquire(json.loads(a.draft.read_text()), a.cache_root)
    a.output.parent.mkdir(parents=True, exist_ok=True); a.output.write_bytes(canonical_bytes(result)); print(json.dumps(result["summary"], sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
