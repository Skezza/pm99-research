from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image

from scripts.dispose_2015_world_assets import (
    AssetDispositionError,
    _load_reviewed_kits,
    build_dispositions,
    canonical_json_bytes,
    sha256_file,
)


def _manifest() -> dict[str, object]:
    return {
        "schema_version": "pm99-world-2015-asset-candidate-manifest-v1",
        "clubs": [
            {
                "carrier_id": 7,
                "source_status": "source-squad-ready",
                "source_country_catalog": "spain",
                "source_club_name": "Example",
                "players": [
                    {"slot_index": 0, "player_carrier_id": 100, "name": "Cached", "fifa16_player_id": 1, "portrait": {"status": "cached-approved-era", "source_image_path": "SOURCE"}},
                    {"slot_index": 1, "player_carrier_id": 101, "name": "Missing", "fifa16_player_id": None, "portrait": {"status": "needs-identity-safe-era-source"}},
                    {"slot_index": 2, "player_carrier_id": 102, "name": "URL", "fifa16_player_id": 2, "portrait": {"status": "fifa16-url-candidate", "source_url": "https://example.test/2.png"}},
                ],
            },
            {"carrier_id": 8, "source_status": "no-captured-source-country", "source_country_catalog": None, "source_club_name": None, "players": []},
        ],
    }


def test_materialises_identity_safe_crop_and_explicit_no_photo(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGBA", (80, 100), (20, 40, 60, 255)).save(source)
    manifest = _manifest()
    manifest["clubs"][0]["players"][0]["portrait"]["source_image_path"] = str(source)  # type: ignore[index]
    result = build_dispositions(manifest, output_dir=tmp_path / "out")
    players = result["clubs"][0]["players"]  # type: ignore[index]
    assert players[0]["status"] == "approved-crop-candidate"
    assert players[0]["candidate_image"]["width"] == 32
    assert Path(players[0]["candidate_path"]).is_file()
    assert players[1]["status"] == "native-no-photo"
    assert players[1]["action"] == "preserve-native-no-photo"
    assert players[2]["status"] == "pending-source-materialisation"
    assert result["coverage"]["portrait_disposition_ready_carrier_count"] == 0  # type: ignore[index]
    assert result["coverage"]["asset_release_ready_carrier_count"] == 0  # type: ignore[index]


def test_unreviewed_kits_are_blocked_and_no_carrier_is_release_ready(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(source)
    manifest = _manifest()
    manifest["clubs"][0]["players"] = []  # type: ignore[index]
    result = build_dispositions(manifest, reviewed_kits={})
    assert result["clubs"][0]["kit"]["status"] == "blocked-no-reviewed-2015-kit"  # type: ignore[index]
    assert result["coverage"]["kit_disposition_ready_carrier_count"] == 0  # type: ignore[index]


def test_reviewed_kit_requires_matching_identity_and_hash(tmp_path: Path) -> None:
    source = tmp_path / "kit.png"
    Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(source)
    digest = sha256_file(source)
    reviewed = {7: {"carrier_id": 7, "source_country_catalog": "spain", "source_club_name": "Example", "season": "2015-16", "review_status": "approved", "source_url": "https://example.test/kit.png", "source_path": str(source), "source_sha256": digest, "ledger": "ledger.json"}}
    manifest = _manifest()
    manifest["clubs"][0]["players"] = []  # type: ignore[index]
    result = build_dispositions(manifest, reviewed_kits=reviewed)
    assert result["clubs"][0]["kit"]["status"] == "approved-reviewed-2015-kit-candidate"  # type: ignore[index]
    assert result["coverage"]["asset_release_ready_carrier_count"] == 0  # kit is ready but no player roster is not a complete portrait lane
    bad = dict(reviewed[7], source_club_name="Wrong Club")
    with pytest.raises(AssetDispositionError, match="does not match candidate club identity"):
        build_dispositions(manifest, reviewed_kits={7: bad})


def test_kit_ledger_loader_rejects_stale_hash(tmp_path: Path) -> None:
    source = tmp_path / "kit.png"
    Image.new("RGBA", (32, 32), (1, 2, 3, 255)).save(source)
    ledger = tmp_path / "kits.json"
    ledger.write_text(json.dumps({"schema_version": "pm99-world-reviewed-kit-candidates-v1", "rows": [{"carrier_id": 7, "source_country_catalog": "spain", "source_club_name": "Example", "season": "2015-16", "review_status": "approved", "source_url": "https://example.test/kit.png", "source_path": str(source), "source_sha256": "0" * 64}]}))
    with pytest.raises(AssetDispositionError, match="source hash does not match"):
        _load_reviewed_kits([ledger])


def test_disposition_json_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGBA", (32, 32), (9, 8, 7, 255)).save(source)
    manifest = _manifest()
    manifest["clubs"][0]["players"][0]["portrait"]["source_image_path"] = str(source)  # type: ignore[index]
    first = build_dispositions(manifest, output_dir=tmp_path / "out")
    second = build_dispositions(manifest, output_dir=tmp_path / "out")
    assert hashlib.sha256(canonical_json_bytes(first)).hexdigest() == hashlib.sha256(canonical_json_bytes(second)).hexdigest()
