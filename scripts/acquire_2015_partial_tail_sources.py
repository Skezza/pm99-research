#!/usr/bin/env python3
"""Acquire pinned 2015 squads that close previously partial carrier tails.

Every target is an exact, reviewed club identity and a Transfermarkt club ID.
The capture is accepted only when the dated ``saison_id/2015`` table fills the
carrier's immutable roster capacity.  Short pages remain absent from the
output rather than being padded with invented identities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.supplement_2015_ntf_with_transfermarkt import _get, parse_squad

SCHEMA = "pm99-footballsquads-season-capture-v1"

# These pages were individually checked after the interrupted network pass.
# Targets whose 2015 page remains shorter than the PM99 carrier are omitted
# and therefore continue to carry an explicit partial-tail disposition.
TARGETS: dict[int, dict[str, Any]] = {
    1453: {"country": "czechia", "name": "SK Slavia Prague", "slug": "sk-slavia-prag", "club_id": 62},
    1506: {"country": "bulgaria", "name": "Litex Lovech", "slug": "litex-lovech", "club_id": 1703},
    1554: {"country": "slovakia", "name": "FC VSS Kosice", "slug": "fc-vss-kosice", "club_id": 779},
    1556: {"country": "slovakia", "name": "Dukla Banska Bystrica", "slug": "dukla-banska-bystrica", "club_id": 4786},
    1802: {"country": "luxembourg", "name": "Jeunesse Esch", "slug": "jeunesse-esch", "club_id": 1257},
    1901: {"country": "northern-ireland", "name": "Linfield FC", "slug": "linfield-fc", "club_id": 3471},
    1902: {"country": "northern-ireland", "name": "Crusaders FC", "slug": "crusaders-fc", "club_id": 21532},
    1903: {"country": "northern-ireland", "name": "Glenavon FC", "slug": "glenavon-fc", "club_id": 3463},
    1904: {"country": "northern-ireland", "name": "Portadown FC", "slug": "portadown-fc", "club_id": 5594},
    1905: {"country": "northern-ireland", "name": "Glentoran FC", "slug": "glentoran-fc", "club_id": 9026},
    1906: {"country": "northern-ireland", "name": "Cliftonville FC", "slug": "cliftonville-fc", "club_id": 1251},
    1951: {"country": "iceland", "name": "KR Reykjavik", "slug": "kr-reykjavik", "club_id": 3237},
    2004: {"country": "finland", "name": "FC Haka", "slug": "fc-haka", "club_id": 1225},
    2005: {"country": "finland", "name": "FC Jazz Pori", "slug": "fc-jazz-pori", "club_id": 304},
    2651: {"country": "ecuador", "name": "CD El Nacional", "slug": "cd-el-nacional", "club_id": 1143},
    2652: {"country": "ecuador", "name": "CS Emelec", "slug": "cs-emelec", "club_id": 4561},
    3100: {"country": "colombia", "name": "CD America de Cali", "slug": "cd-america-de-cali", "club_id": 2352},
    3102: {"country": "colombia", "name": "Millonarios FC", "slug": "millonarios-fc", "club_id": 2350},
    3202: {"country": "paraguay", "name": "Club Guarani", "slug": "club-guarani", "club_id": 1468},
    4000: {"country": "latvia", "name": "Skonto Riga", "slug": "skonto-riga", "club_id": 1043},
    4001: {"country": "latvia", "name": "FK Liepaja", "slug": "fk-liepaja", "club_id": 43162},
    4125: {"country": "azerbaijan", "name": "Neftchi Baku", "slug": "neftchi-baku", "club_id": 7769},
}


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def acquire(*, draft: dict[str, Any], cache_root: Path, fetch: Callable[[str], bytes] = _get, continue_on_error: bool = False) -> dict[str, Any]:
    proposals = {int(row["carrier_id"]): row for row in draft.get("proposals", [])}
    clubs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for carrier_id, target in sorted(TARGETS.items()):
        proposal = proposals.get(carrier_id)
        if proposal is None or proposal.get("status") != "undersized-source-squad":
            raise ValueError(f"carrier {carrier_id} is not a partial sourced carrier")
        if str(proposal.get("group")) != target["country"]:
            raise ValueError(f"carrier {carrier_id} crosses country family")
        url = f"https://www.transfermarkt.com/{target['slug']}/kader/verein/{target['club_id']}/saison_id/2015"
        source_path = Path(f"transfermarkt-tail-closeout/{target['country']}/{carrier_id}-{target['club_id']}.html")
        destination = cache_root / source_path
        if destination.is_file():
            payload = destination.read_bytes()
        else:
            failure: Exception | None = None
            for attempt in range(3):
                try:
                    payload = fetch(url)
                    break
                except Exception as error:  # network pass is resumable
                    failure = error
                    if attempt < 2:
                        time.sleep(1 + attempt)
            else:
                assert failure is not None
                if continue_on_error:
                    failures.append({"carrier_id": carrier_id, "source_url": url, "reason": "fetch-failed", "detail": str(failure)})
                    continue
                raise failure
        players = parse_squad(payload)
        capacity = int(proposal["fixed_roster_slot_count"])
        if len(players) < capacity:
            if continue_on_error:
                failures.append({"carrier_id": carrier_id, "source_url": url, "reason": "pinned-squad-short", "player_count": len(players), "fixed_roster_slot_count": capacity})
                continue
            raise ValueError(f"pinned 2015 squad is short: {carrier_id} {len(players)}/{capacity}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        clubs.append({
            "candidate_carrier_id": carrier_id,
            "candidate_baseline_name": proposal.get("baseline_name"),
            "fixed_roster_slot_count": capacity,
            "country_catalog": target["country"],
            "competition_catalog": "transfermarkt-2015-squad-tail-closeout",
            "club_name": target["name"],
            "competition_name": "Transfermarkt historical squad page (2015 season)",
            "source_path": source_path.as_posix(),
            "source_sha256": hashlib.sha256(payload).hexdigest(),
            "source_url": url,
            "source_season_label": "2015",
            "players": players,
            "capture_note": "Pinned exact 2015 squad; fills immutable carrier; source facts only",
        })
    return {
        "schema_version": SCHEMA,
        "source": {"title": "Transfermarkt partial-tail closeout", "repository": "https://www.transfermarkt.com", "revision": "2015-dated-pages-content-addressed-v1", "license": "public factual source; URL and content hash retained", "retrieved_on": date.today().isoformat()},
        "season": {"catalog": "2015-world-partial-tail-closeout", "label": "2015/16 plus 2015 calendar-year leagues"},
        "clubs": clubs,
        "unresolved": failures,
        "summary": {"target_count": len(TARGETS), "club_count": len(clubs), "player_count": sum(len(row["players"]) for row in clubs), "capacity_complete_count": len(clubs), "unresolved_count": len(failures)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--cache-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = acquire(draft=json.loads(args.draft.read_text(encoding="utf-8")), cache_root=args.cache_root, continue_on_error=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
