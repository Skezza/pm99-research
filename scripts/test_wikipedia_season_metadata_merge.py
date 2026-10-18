from __future__ import annotations

from scripts import capture_2015_world_wikipedia_season_metadata as capture
from scripts import merge_2015_world_wikipedia_metadata as merge


def test_capture_accepts_only_declared_season_and_label(monkeypatch) -> None:
    good = {"title": "2015–16 FC Barcelona season", "pageid": 1, "revid": 2, "timestamp": "x", "content_sha256": "a", "infobox": {"season": "2015–16", "club": "FC Barcelona", "manager": "Manager", "stadium": "Ground"}}
    monkeypatch.setattr(capture, "_fetch", lambda title: good if "FC Barcelona" in title else None)
    monkeypatch.setattr(capture, "_search_titles", lambda name: [])
    row = capture._one({"carrier_id": 1, "source_club_name": "Barcelona"})
    assert row["status"] == "exact-season-infobox-match"
    assert row["accepted_infobox_club_label"] == "FC Barcelona"


def test_transfermarkt_remains_stronger_than_wikipedia() -> None:
    candidate = {"schema_version": "pm99-world-2015-editorial-fallback-ratings-v1", "sources": {}, "coverage": {}, "carrier_drafts": [{"carrier_id": 1, "manager": {"name": "Fixture manager", "metadata_status": "fixture-source-fact"}, "opening_fixture": {"status": "source-qualified"}, "club": {}, "blockers": []}]}
    wiki = {"schema_version": capture.SCHEMA, "rows": [{"carrier_id": 1, "status": "exact-season-infobox-match", "facts": {"manager": "Wiki manager", "stadium": "Wiki ground", "capacity": None}, "page": {"title": "x", "pageid": 1, "revid": 2, "timestamp": "x", "content_sha256": "a"}}]}
    result = merge.merge(candidate, wiki)
    assert result["carrier_drafts"][0]["manager"]["name"] == "Fixture manager"
    assert result["carrier_drafts"][0]["club"]["wikipedia_stadium_evidence"]["stadium"] == "Wiki ground"
