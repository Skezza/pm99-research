#!/usr/bin/env python3
"""Acquire explicit 2015 Transfermarkt squad pages for source conflicts.

The target table is intentionally small and reviewable.  Every row has a
country-scoped PM99 carrier, a pinned ``saison_id/2015`` URL, and a fixed
historical club identity.  This produces source facts only; it does not
allocate or write PM99 data.
"""

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

# Exact historical names and Transfermarkt IDs, reviewed from the search
# result.  No fuzzy search or automatic club-name assignment is performed.
TARGETS: dict[int, dict[str, Any]] = {
    225: {"country": "italy", "name": "AC Perugia Calcio", "slug": "ac-perugia-calcio", "club_id": 839},
    250: {"country": "italy", "name": "FC Empoli", "slug": "fc-empoli", "club_id": 749},
    421: {"country": "germany", "name": "Hertha BSC", "slug": "hertha-bsc", "club_id": 44},
    871: {"country": "belgium", "name": "KSC Lokeren (-2020)", "slug": "ksc-lokeren", "club_id": 498},
    872: {"country": "belgium", "name": "KVC Westerlo", "slug": "kvc-westerlo", "club_id": 968},
    960: {"country": "sweden", "name": "Trelleborgs FF", "slug": "trelleborgs-ff", "club_id": 701},
    1111: {"country": "switzerland", "name": "FC Zürich", "slug": "fc-zurich", "club_id": 260},
    1112: {"country": "switzerland", "name": "BSC Young Boys", "slug": "bsc-young-boys", "club_id": 452},
    3326: {"country": "eng", "name": "Boston United", "slug": "boston-united", "club_id": 3489},
    3330: {"country": "eng", "name": "Chorley FC", "slug": "chorley-fc", "club_id": 13286},
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def acquire(*, draft: dict[str, Any], cache_root: Path, fetch: Callable[[str], bytes] = _get) -> dict[str, Any]:
    by_id = {int(row["carrier_id"]): row for row in draft.get("proposals", [])}
    clubs: list[dict[str, Any]] = []
    for carrier_id in sorted(TARGETS):
        target = TARGETS[carrier_id]
        proposal = by_id.get(carrier_id)
        if proposal is None or proposal.get("status") != "no-distinct-captured-top-competition-squad-with-required-capacity":
            raise ValueError(f"carrier {carrier_id} is not an unresolved selector conflict")
        url = f"https://www.transfermarkt.com/{target['slug']}/kader/verein/{target['club_id']}/saison_id/2015"
        payload = fetch(url)
        players = parse_squad(payload)
        if not players:
            raise ValueError(f"pinned 2015 squad has no parsed rows: {carrier_id} {url}")
        source_path = Path(f"transfermarkt/{target['country']}/{carrier_id}-{target['club_id']}.html")
        full_path = cache_root / source_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(payload)
        clubs.append({
            "candidate_carrier_id": carrier_id,
            "candidate_baseline_name": proposal["baseline_name"],
            "fixed_roster_slot_count": int(proposal["fixed_roster_slot_count"]),
            "country_catalog": target["country"],
            "competition_catalog": "transfermarkt-2015-squad",
            "club_name": target["name"],
            "competition_name": "Transfermarkt historical squad page (2015 season)",
            "source_path": source_path.as_posix(),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "source_url": url,
            "source_season_label": "2015",
            "players": players,
            "capture_note": "Pinned Transfermarkt 2015 squad; exact club identity; source facts only",
        })
    return {
        "schema_version": SCHEMA,
        "source": {"title": "Transfermarkt historical conflict squad capture", "repository": "https://www.transfermarkt.com", "revision": "2015-dated-pages-content-addressed-v1", "license": "public factual source; URL and content hash retained", "retrieved_on": date.today().isoformat()},
        "season": {"catalog": "2015-world-conflict-supplements", "label": "2015/16 plus 2015 calendar-year leagues"},
        "clubs": clubs,
        "summary": {"club_count": len(clubs), "player_count": sum(len(c["players"]) for c in clubs), "candidate_carrier_count": len(clubs), "capacity_complete_count": sum(len(c["players"]) >= int(c["fixed_roster_slot_count"]) for c in clubs)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = acquire(draft=json.loads(args.draft.read_text(encoding="utf-8")), cache_root=args.cache_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
