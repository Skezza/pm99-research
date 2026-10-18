from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import iter_minifoto_records  # noqa: E402
from scripts.apply_2015_world_portraits import apply_portraits  # noqa: E402

MINIFOTO = ROOT / ".local/season-pipeline-v2/english92-clean-release-2015-16-20260830/DBDAT/MINIFOTO.PKF"


@pytest.mark.skipif(not MINIFOTO.is_file(), reason="local PM99 fixture is unavailable")
def test_applies_one_existing_portrait_and_forces_another_to_no_photo(tmp_path: Path) -> None:
    records = iter_minifoto_records(MINIFOTO)
    assert len(records) >= 2
    applied, hidden = records[:2]
    game = tmp_path / "game"
    dbdat = game / "DBDAT"
    dbdat.mkdir(parents=True)
    shutil.copy2(MINIFOTO, dbdat / "MINIFOTO.PKF")
    converted = tmp_path / "converted.bmp"
    converted.write_bytes(applied.raw_bitmap)
    manifest = {
        "schema_version": "pm99-world-2015-asset-candidate-manifest-v1",
        "clubs": [{
            "carrier_id": 1,
            "source_status": "source-squad-ready",
            "players": [
                {"slot_index": 0, "player_carrier_id": applied.player_record_id, "name": "Applied", "portrait": {"status": "fifa16-url-candidate"}},
                {"slot_index": 1, "player_carrier_id": hidden.player_record_id, "name": "Hidden", "portrait": {"status": "needs-identity-safe-era-source"}},
            ],
        }],
    }
    import hashlib
    materialisation = {
        "schema_version": "pm99-world-2015-portrait-materialisation-v1",
        "coverage": {"pending_count": 0},
        "rows": [{
            "carrier_id": 1,
            "slot_index": 0,
            "player_carrier_id": applied.player_record_id,
            "status": "approved-crop-conversion-candidate",
            "converted_path": str(converted),
            "converted_sha256": hashlib.sha256(applied.raw_bitmap).hexdigest(),
        }],
    }
    result = apply_portraits(manifest=manifest, materialisation=materialisation, game_tree=game)
    final_ids = {record.player_record_id for record in iter_minifoto_records(dbdat / "MINIFOTO.PKF")}
    assert applied.player_record_id in final_ids
    assert hidden.player_record_id not in final_ids
    assert result["coverage"] == {"selected_player_count": 2, "applied_portrait_count": 1, "native_no_photo_count": 1, "preserved_native_portrait_count": 0, "pending_count": 0, "recycle_portrait_clone_count": 0, "recycle_portrait_clone_with_photo_count": 0}
