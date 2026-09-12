"""Tests for the pinned-2015-squad manager source pass."""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts import capture_2015_world_manager_transfermarkt_snapshot_v5 as subject


def _candidate() -> dict:
    return {
        "schema_version": subject.CANDIDATE_SCHEMA,
        "carrier_drafts": [{
            "carrier_id": 7,
            "club": {
                "source_club_name": "Example Town",
                "source_selector": {
                    "country_catalog": "example", "competition_catalog": "top", "club_name": "Example Town",
                },
            },
            "manager": {"metadata_status": "unavailable-no-dated-manager-source", "name": None},
        }],
    }


def _wiki(candidate_sha: str) -> dict:
    return {
        "schema_version": subject.WIKIPEDIA_SCHEMA,
        "sources": {"source_candidate_sha256": candidate_sha},
        "rows": [{"carrier_id": 7, "status": "requires-review-no-dated-national-wikipedia-manager-match"}],
    }


def test_capture_uses_exact_pinned_2015_club_identity(monkeypatch, tmp_path: Path) -> None:
    candidate = _candidate()
    candidate_sha = hashlib.sha256(subject.canonical_json_bytes(candidate)).hexdigest()
    squad_root = tmp_path / "squads"
    cached = squad_root / "example" / "7-example-town.html"
    cached.parent.mkdir(parents=True)
    cached.write_text('<link href="https://www.transfermarkt.com/example-town/kader/verein/42/saison_id/2015">')

    monkeypatch.setattr(subject.history, "manager_at_date", lambda *_args: ("Historical Manager", "99"))

    class Cache:
        used: dict[str, dict[str, str]] = {}

        def get(self, url: str, key: str) -> bytes:
            self.used[key] = {"cache_path": key, "sha256": "a" * 64, "url": url}
            return b"history"

    result = subject.capture(
        candidate=candidate, candidate_sha256=candidate_sha,
        wikipedia=_wiki(candidate_sha), wikipedia_sha256="wiki-sha",
        pinned_squad_cache=squad_root, manager_history_cache=Cache(),  # type: ignore[arg-type]
    )

    assert result["coverage"]["dated_transfermarkt_manager_match_count"] == 1
    assert result["rows"][0]["manager_name"] == "Historical Manager"
    assert result["rows"][0]["pinned_2015_squad"]["transfermarkt_club_id"] == 42
    assert result["rows"][0]["snapshot_as_of"] == "2015-09-01"


def test_capture_rejects_non_cp1252_manager_name(monkeypatch, tmp_path: Path) -> None:
    candidate = _candidate()
    candidate_sha = hashlib.sha256(subject.canonical_json_bytes(candidate)).hexdigest()
    squad_root = tmp_path / "squads"
    cached = squad_root / "example" / "7-example-town.html"
    cached.parent.mkdir(parents=True)
    cached.write_text('<link href="https://www.transfermarkt.com/example-town/kader/verein/42/saison_id/2015">')
    monkeypatch.setattr(subject.history, "manager_at_date", lambda *_args: ("Иван Иванов", "99"))

    class Cache:
        used: dict[str, dict[str, str]] = {}

        def get(self, url: str, key: str) -> bytes:
            self.used[key] = {"cache_path": key, "sha256": "a" * 64, "url": url}
            return b"history"

    result = subject.capture(
        candidate=candidate, candidate_sha256=candidate_sha,
        wikipedia=_wiki(candidate_sha), wikipedia_sha256="wiki-sha",
        pinned_squad_cache=squad_root, manager_history_cache=Cache(),  # type: ignore[arg-type]
    )

    assert result["rows"] == []
    assert result["gaps"][0]["reason"] == "published manager display name requires a reviewed PM99 Latin spelling"
