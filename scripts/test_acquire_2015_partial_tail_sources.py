"""Tests for exact dated partial-tail source acquisition."""

from pathlib import Path

from scripts.acquire_2015_partial_tail_sources import TARGETS, acquire


def test_targets_are_country_scoped_and_unique() -> None:
    assert len(TARGETS) == 22
    assert len({(row["country"], row["club_id"]) for row in TARGETS.values()}) == len(TARGETS)


def test_short_source_fails_closed(tmp_path: Path) -> None:
    cid, target = next(iter(TARGETS.items()))
    draft = {"proposals": [{"carrier_id": cid, "baseline_name": "x", "group": target["country"], "status": "undersized-source-squad", "fixed_roster_slot_count": 2}]}
    fixture = b'<table class="items"><tr><td>1</td><td><a href="/profil/spieler/1">One Player</a></td><td>Goalkeeper</td><td></td></tr></table>'
    try:
        acquire(draft=draft, cache_root=tmp_path, fetch=lambda _: fixture)
    except ValueError as error:
        assert "short" in str(error)
    else:
        raise AssertionError("short source must fail closed")
