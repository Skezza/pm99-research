"""Fixture tests for exact conflict-source acquisition."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.acquire_2015_conflict_squad_sources import TARGETS, acquire


def test_target_table_is_explicit_and_unique() -> None:
    assert len(TARGETS) == 10
    assert len({(v["country"], v["club_id"]) for v in TARGETS.values()}) == 10


def test_acquire_uses_pinned_url_and_capacity(tmp_path: Path) -> None:
    draft = {"proposals": [{"carrier_id": cid, "baseline_name": f"Carrier {cid}", "fixed_roster_slot_count": 1, "status": "no-distinct-captured-top-competition-squad-with-required-capacity", "group": target["country"]} for cid, target in TARGETS.items()]}
    seen: list[str] = []

    def fetch(url: str) -> bytes:
        seen.append(url)
        # The parser needs one Transfermarkt-style athlete row.  This fixture
        # checks the source URL and output contract without network access.
        return b'<table class="items"><tr><td>1</td><td><a href="/profil/spieler/1">Fixture Player</a></td><td>Goalkeeper</td><td><img title="England"><img title="England"><img title="England"><img title="England"></td></tr></table>'

    result = acquire(draft=draft, cache_root=tmp_path, fetch=fetch)
    assert result["summary"]["club_count"] == 10
    assert all("/kader/verein/" in url and "/saison_id/2015" in url for url in seen)
    assert all(len(club["players"]) == 1 for club in result["clubs"])


if __name__ == "__main__":
    test_target_table_is_explicit_and_unique()
    print("manual fixture tests: ok")
