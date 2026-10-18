from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_footballsquads_web_season as web_capture  # noqa: E402


ARCHIVE = b"""
<a href="/eng/2024-2025/engprem.htm">2024/25</a>
<a href="/brazil/2024/brasileir.htm">2024</a>
<a href="/eng/2023-2024/engprem.htm">2023/24</a>
"""
INDEX = b"""
<a href="../home.htm">Home</a>
<a href="engprem/arsenal.htm">Arsenal</a>
<a href="engprem/chelsea.htm">Chelsea</a>
"""
CLUB = b"""
<html><body><h2>Arsenal</h2><table>
<tr><th>Number</th><th>Name</th><th>Nat</th><th>Pos</th><th>Height</th><th>Weight</th><th>Date of Birth</th><th>Birth Place</th><th>Previous Club</th></tr>
<tr><td>1</td><td>David Raya</td><td>ESP</td><td>G</td><td>1.83</td><td>80</td><td>15-09-95</td><td>Barcelona</td><td>Brentford</td></tr>
<tr><td>2</td><td>Missing Facts</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td><td>-</td></tr>
<tr><td colspan="9">Players no longer at this club</td></tr>
<tr><td>3</td><td>Past Player</td><td>ENG</td><td>M</td><td>1.80</td><td>70</td><td>01-01-90</td><td>Test</td><td>Elsewhere</td></tr>
</table></body></html>
"""


def _write(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return web_capture.sha256_bytes(payload)


def test_archive_discovery_retains_only_split_and_start_calendar_catalogues() -> None:
    indexes = web_capture.discover_index_pages(
        archive_payload=ARCHIVE,
        archive_url=web_capture.DEFAULT_ARCHIVE_URL,
        season="2024-2025",
    )

    assert indexes == [
        {
            "country_catalog": "brazil",
            "source_catalog": "2024",
            "competition_catalog": "brasileir",
            "url": "https://footballsquads.co.uk/brazil/2024/brasileir.htm",
            "archive_label": "2024",
        },
        {
            "country_catalog": "eng",
            "source_catalog": "2024-2025",
            "competition_catalog": "engprem",
            "url": "https://footballsquads.co.uk/eng/2024-2025/engprem.htm",
            "archive_label": "2024/25",
        },
    ]


def test_index_discovery_refuses_navigation_and_retains_only_club_directory() -> None:
    index = {
        "country_catalog": "eng",
        "source_catalog": "2024-2025",
        "competition_catalog": "engprem",
        "url": "https://footballsquads.co.uk/eng/2024-2025/engprem.htm",
        "archive_label": "2024/25",
    }

    assert web_capture.discover_club_pages(index_payload=INDEX, index=index) == [
        {
            "url": "https://footballsquads.co.uk/eng/2024-2025/engprem/arsenal.htm",
            "archive_label": "Arsenal",
        },
        {
            "url": "https://footballsquads.co.uk/eng/2024-2025/engprem/chelsea.htm",
            "archive_label": "Chelsea",
        },
    ]


def test_index_discovery_accepts_a_source_subdirectory_different_from_the_index_stem() -> None:
    index = {
        "country_catalog": "arg",
        "source_catalog": "2024",
        "competition_catalog": "argprim",
        "url": "https://footballsquads.co.uk/arg/2024/argprim.htm",
        "archive_label": "2024",
    }
    payload = b'<a href="primera/boca.htm">Boca Juniors</a>'

    assert web_capture.discover_club_pages(index_payload=payload, index=index) == [
        {
            "url": "https://footballsquads.co.uk/arg/2024/primera/boca.htm",
            "archive_label": "Boca Juniors",
        }
    ]


def test_club_parser_keeps_current_squad_and_retains_missing_facts() -> None:
    name, players = web_capture.parse_club_page(payload=CLUB, source_year=2024, label="fixture")

    assert name == "Arsenal"
    assert players == [
        {
            "shirt_number": 1,
            "name": "David Raya",
            "nationality": "ESP",
            "position": "G",
            "height_cm": 183,
            "weight_kg": 80,
            "birth_date": "1995-09-15",
            "unresolved_fields": [],
        },
        {
            "shirt_number": 2,
            "name": "Missing Facts",
            "nationality": None,
            "position": None,
            "height_cm": None,
            "weight_kg": None,
            "birth_date": None,
            "unresolved_fields": ["nationality", "primary_position", "height_cm", "weight_kg", "birth_date"],
        },
    ]


def test_capture_from_snapshot_is_hash_locked_and_excludes_past_players(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    index_path = "indexes/eng/2024-2025/engprem.htm"
    club_path = "clubs/eng/2024-2025/engprem/arsenal.htm"
    index_hash = _write(cache_root / index_path, INDEX)
    club_hash = _write(cache_root / club_path, CLUB)
    snapshot = {
        "schema_version": web_capture.SNAPSHOT_SCHEMA,
        "snapshot_id": "footballsquads-2024-25-fixture",
        "retrieved_on": "2026-09-01",
        "source": {
            "archive_url": web_capture.DEFAULT_ARCHIVE_URL,
            "terms_url": web_capture.TERMS_URL,
            "attribution": "Fixture attribution",
        },
        "season": {
            "start_year": 2024,
            "end_year": 2025,
            "label": "2024/25",
            "split_catalog": "2024-2025",
            "calendar_catalog": "2024",
        },
        "archive": {"cache_path": "archive.html", "sha256": "a" * 64},
        "indexes": [
            {
                "country_catalog": "eng",
                "source_catalog": "2024-2025",
                "competition_catalog": "engprem",
                "url": "https://footballsquads.co.uk/eng/2024-2025/engprem.htm",
                "archive_label": "2024/25",
                "cache_path": index_path,
                "sha256": index_hash,
                "clubs": [
                    {
                        "archive_label": "Arsenal",
                        "cache_path": club_path,
                        "sha256": club_hash,
                        "url": "https://footballsquads.co.uk/eng/2024-2025/engprem/arsenal.htm",
                    }
                ],
            }
        ],
        "summary": {"index_count": 1, "club_page_count": 1, "source_catalogs": ["2024-2025"]},
    }

    capture = web_capture.capture_from_snapshot(
        snapshot=snapshot,
        snapshot_sha256="b" * 64,
        cache_root=cache_root,
        catalog="2024-2025",
    )

    assert capture["season"] == {"catalog": "2024-2025", "label": "2024/25"}
    assert capture["summary"]["player_count"] == 2
    assert capture["clubs"][0]["players"][0]["name"] == "David Raya"
    assert capture["source"]["snapshot_manifest_sha256"] == "b" * 64

    (cache_root / club_path).write_bytes(b"changed")
    with pytest.raises(web_capture.WebCaptureError, match="hash does not match"):
        web_capture.capture_from_snapshot(
            snapshot=snapshot,
            snapshot_sha256="b" * 64,
            cache_root=cache_root,
            catalog="2024-2025",
        )
