from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.apply_2015_world_kits import ALL_ARCHIVES, apply_world_kits, records_by_carrier, sha256_file


ENGLISH_GAME = Path(".local/season-2015-16/english92-2015-16-editorial-v1-r2/game")
ENGLISH_RECEIPT = Path(".local/season-2015-16/english92-2015-16-editorial-v1-r2/kit-stage/2015-16-english-92-native-kit-receipt.json")
MATERIALISATION = Path(".local/season-pipeline-v2/world-2015-fifaindex-kit-materialisation-latest.json")
COMBINED = Path(".local/season-pipeline-v2/world-2015-combined-kit-materialisation-latest-v2.json")


@pytest.mark.skipif(not (ENGLISH_RECEIPT.is_file() and MATERIALISATION.is_file()), reason="local 2015 kit corpus is unavailable")
def test_apply_restores_english_archives_and_changes_only_approved_foreign_extent(tmp_path: Path) -> None:
    target = tmp_path / "game"
    dbdat = target / "DBDAT"
    dbdat.mkdir(parents=True)
    for archive in ALL_ARCHIVES:
        shutil.copy2(ENGLISH_GAME / "DBDAT" / archive, dbdat / archive)
    # Make the target observably different before assembly; the stage must
    # restore it from the certified English source before the foreign overlay.
    payload = bytearray((dbdat / "BIGESC.PKF").read_bytes())
    payload[-1] ^= 1
    (dbdat / "BIGESC.PKF").write_bytes(payload)

    source_materialisation = json.loads(MATERIALISATION.read_text(encoding="utf-8"))
    approved = next(row for row in source_materialisation["rows"] if row["status"] == "release-eligible-fifa16-identity-bound")
    materialisation = {"schema_version": source_materialisation["schema_version"], "rows": [approved]}
    receipt = json.loads(ENGLISH_RECEIPT.read_text(encoding="utf-8"))
    before_unapproved = records_by_carrier(ENGLISH_GAME / "DBDAT" / "MINIESC.PKF")[2].raw_bitmap
    result = apply_world_kits(materialisation=materialisation, english_dbdat=ENGLISH_GAME / "DBDAT", english_receipt=receipt, target_game_tree=target)

    assert result["coverage"]["english_verified_record_count"] == 447
    assert result["coverage"]["foreign_patched_record_count"] == 3
    assert sha256_file(dbdat / "BIGESC.PKF") == sha256_file(ENGLISH_GAME / "DBDAT" / "BIGESC.PKF")
    assert records_by_carrier(dbdat / "MINIESC.PKF")[2].raw_bitmap == before_unapproved
    carrier = int(approved["carrier_id"])
    for archive in ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"):
        assert sha256_file(Path(approved["assets"][archive]["path"])) == approved["assets"][archive]["sha256"]
        assert records_by_carrier(dbdat / archive)[carrier].raw_bitmap == Path(approved["assets"][archive]["path"]).read_bytes()


@pytest.mark.skipif(not (ENGLISH_RECEIPT.is_file() and COMBINED.is_file()), reason="local combined kit corpus unavailable")
def test_apply_accepts_reviewed_geometry_and_preserves_other_records(tmp_path: Path) -> None:
    target = tmp_path / "game"
    (target / "DBDAT").mkdir(parents=True)
    for archive in ALL_ARCHIVES:
        shutil.copy2(ENGLISH_GAME / "DBDAT" / archive, target / "DBDAT" / archive)
    source = json.loads(COMBINED.read_text(encoding="utf-8"))
    approved = next(row for row in source["rows"] if row["status"] == "release-eligible-reviewed-2015-geometry")
    materialisation = {"schema_version": source["schema_version"], "rows": [approved]}
    receipt = json.loads(ENGLISH_RECEIPT.read_text(encoding="utf-8"))
    untouched = records_by_carrier(ENGLISH_GAME / "DBDAT" / "MINIESC.PKF")[2].raw_bitmap
    result = apply_world_kits(materialisation=materialisation, english_dbdat=ENGLISH_GAME / "DBDAT", english_receipt=receipt, target_game_tree=target)
    assert result["coverage"]["foreign_patched_record_count"] == 3
    assert records_by_carrier(target / "DBDAT" / "MINIESC.PKF")[2].raw_bitmap == untouched
