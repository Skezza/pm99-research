from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from scripts.materialise_2015_world_portraits import (
    PortraitMaterialisationError,
    _fetch_one,
    _url_bound_to_id,
    materialise_portraits,
)


MINIFOTO = Path(".local/season-pipeline-v2/english92-clean-release-2015-16-20260830/DBDAT/MINIFOTO.PKF")


def test_url_binding_rejects_a_different_player() -> None:
    assert _url_bound_to_id("https://www.fifaindex.com/static/FIFA16/images/players/10/192448.png", 192448)
    assert not _url_bound_to_id("https://www.fifaindex.com/static/FIFA16/images/players/10/192448.png", 192449)
    assert _url_bound_to_id("https://cdn.sofifa.net/players/192/448/16_120.png", 192448)


def test_fetch_failure_is_explicit_no_photo(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 404
        content = b""

    monkeypatch.setattr("scripts.materialise_2015_world_portraits.requests.get", lambda *args, **kwargs: Response())
    row = _fetch_one({"carrier_id": 1, "slot_index": 0, "player_carrier_id": 2, "name": "Missing", "fifa16_player_id": 192448, "portrait": {"status": "fifa16-url-candidate", "source_url": "https://example.invalid/192448.png"}})
    assert row["status"] == "native-no-photo"
    assert row["reason"] == "all-identity-bound-source-urls-failed"
    assert len(row["attempts"]) == 3


def test_bulk_lane_records_success_and_failure_without_game_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = Path(".local/season-pipeline-v2/world-2015-asset-candidate-manifest.json")
    import json

    manifest = json.loads(source.read_text(encoding="utf-8"))
    player = next(p for c in manifest["clubs"] for p in c.get("players", []) if p["portrait"].get("status") == "fifa16-url-candidate")
    manifest["clubs"] = [{"carrier_id": 1, "source_status": "source-squad-ready", "players": [player]}]

    class Response:
        status_code = 200
        content = Path(".local/season-pipeline-v2/world2015-foreign-core-with-assets-20260830/face-sources/fifa16/03612.png").read_bytes()

    monkeypatch.setattr("scripts.materialise_2015_world_portraits.requests.get", lambda *args, **kwargs: Response())
    before = MINIFOTO.read_bytes()
    result = materialise_portraits(manifest, minifoto_path=MINIFOTO, cache_dir=tmp_path / "cache", output_dir=tmp_path / "out", workers=1)
    assert result["coverage"]["success_count"] == 1
    assert result["rows"][0]["status"] == "approved-crop-conversion-candidate"
    assert MINIFOTO.read_bytes() == before


def test_bad_minifoto_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(PortraitMaterialisationError, match="no parseable records"):
        materialise_portraits({"schema_version": "pm99-world-2015-asset-candidate-manifest-v1", "clubs": []}, minifoto_path=tmp_path / "empty.PKF", cache_dir=tmp_path / "cache", output_dir=tmp_path / "out")
