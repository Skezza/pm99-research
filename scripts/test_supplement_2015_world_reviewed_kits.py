from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.supplement_2015_world_reviewed_kits import REVIEWED_STATUS, ReviewedKitError, render_geometry, supplement


DBDAT = Path(".local/season-pipeline-v2/english92-clean-release-2015-16-20260830/DBDAT")
MATERIALISATION = Path(".local/season-pipeline-v2/world-2015-fifaindex-kit-materialisation-latest-v2.json")
LEDGER = Path("scripts/data/world_2015_reviewed_kit_geometry.json")


@pytest.mark.skipif(not (DBDAT.is_dir() and MATERIALISATION.is_file()), reason="local 2015 kit corpus unavailable")
def test_reviewed_supplement_is_identity_bound_and_writes_three_candidates(tmp_path: Path) -> None:
    source = json.loads(MATERIALISATION.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    ledger["clubs"] = ledger["clubs"][:1]
    result = supplement(materialisation=source, ledger=ledger, dbdat=DBDAT, output_dir=tmp_path)
    row = next(row for row in result["rows"] if row["carrier_id"] == 701)
    assert row["status"] == REVIEWED_STATUS
    assert set(row["assets"]) == {"MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF"}
    assert all(Path(asset["path"]).read_bytes() for asset in row["assets"].values())


@pytest.mark.skipif(not (DBDAT.is_dir() and MATERIALISATION.is_file()), reason="local 2015 kit corpus unavailable")
def test_reviewed_supplement_rejects_carrier_name_mismatch(tmp_path: Path) -> None:
    source = json.loads(MATERIALISATION.read_text(encoding="utf-8"))
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    ledger["clubs"] = [dict(ledger["clubs"][0], source_club_name="Wrong Club")]
    with pytest.raises(ReviewedKitError, match="identity mismatch"):
        supplement(materialisation=source, ledger=ledger, dbdat=DBDAT, output_dir=tmp_path)
