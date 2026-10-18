from pathlib import Path

import pytest

from scripts.pm99_kit_palette_v1 import runtime_kit_palette


def test_runtime_palette_requires_dat_beside_dbdat(tmp_path: Path) -> None:
    dbdat = tmp_path / "DBDAT"
    dbdat.mkdir()
    with pytest.raises(ValueError, match="DAT.PKF"):
        runtime_kit_palette(dbdat)


def test_lineup_palette_is_not_the_earlier_dat_palette():
    root = Path(__file__).resolve().parents[1]
    palette, source = runtime_kit_palette(root / '.local/season-pipeline-v2/pm99-base-clean/DBDAT')
    assert source['offset'] == 0x7F974
    assert palette[111] == (0, 0, 100)


def test_truncated_palette_has_a_clear_error(tmp_path):
    from scripts.pm99_kit_palette_v1 import PALETTE_OFFSET
    dbdat = tmp_path / 'DBDAT'
    dbdat.mkdir()
    (tmp_path / 'DAT.PKF').write_bytes(bytes(PALETTE_OFFSET) + b'RIFF')
    with pytest.raises(ValueError, match='RIFF palette is missing'):
        runtime_kit_palette(dbdat)
    (tmp_path / 'DAT.PKF').write_bytes(bytes(PALETTE_OFFSET) + b'RIFF\xff\xff\xff\xff')
    with pytest.raises(ValueError, match='truncated'):
        runtime_kit_palette(dbdat)
