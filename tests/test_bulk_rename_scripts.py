from types import SimpleNamespace

import pytest

import app.bulk_rename as bulk_rename_core


class FakeFDIFile:
    fixtures = {}
    instances = []

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.modified_records = {}
        self.saved = False
        self._players = self.fixtures[file_path]
        self.__class__.instances.append(self)

    def load(self):
        return None

    def list_players(self):
        return self._players

    def save(self):
        self.saved = True


def _make_player(name: str, team_id: int = 1, squad_number: int = 1):
    return SimpleNamespace(name=name, team_id=team_id, squad_number=squad_number)


@pytest.fixture(autouse=True)
def reset_fake_fdi():
    FakeFDIFile.fixtures = {}
    FakeFDIFile.instances = []
    yield


def test_compute_new_name_is_length_preserving():
    assert bulk_rename_core.compute_new_name(12, 5) == "Z0000"
    assert bulk_rename_core.compute_new_name(12, 9) == "Z00000012"
    assert bulk_rename_core.compute_new_name(12, 12) == "Z00000012ZZZ"


def test_process_file_dry_run_writes_offset_mapping_without_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(bulk_rename_core, "FDIFile", FakeFDIFile)

    fdi_path = tmp_path / "JUGTEST.FDI"
    fdi_path.write_bytes(b"")
    rec = _make_player("ALAN", team_id=7, squad_number=9)
    FakeFDIFile.fixtures[str(fdi_path)] = [(0x1234, rec)]

    rows = []
    bulk_rename_core.process_player_file(fdi_path, rows, dry_run=True)

    assert len(rows) == 1
    assert rows[0]["record_index"] == 0
    assert rows[0]["offset"] == 0x1234
    assert rows[0]["offset_hex"] == "0x1234"
    assert rows[0]["file"] == "JUGTEST.FDI"
    assert rows[0]["original_name"] == "ALAN"
    assert len(rows[0]["new_name"]) == len(rows[0]["original_name"])
    assert not FakeFDIFile.instances[0].saved
    assert FakeFDIFile.instances[0].modified_records == {}
    assert rec.name == "ALAN"
    assert "name_dirty" not in rec.__dict__


def test_process_file_mutates_records_and_saves_when_not_dry_run(tmp_path, monkeypatch):
    monkeypatch.setattr(bulk_rename_core, "FDIFile", FakeFDIFile)

    fdi_path = tmp_path / "JUGSAVE.FDI"
    fdi_path.write_bytes(b"")
    rec = _make_player("ROBERT", team_id=3, squad_number=10)
    FakeFDIFile.fixtures[str(fdi_path)] = [(0x20, rec)]

    rows = []
    bulk_rename_core.process_player_file(fdi_path, rows, dry_run=False)

    assert rows[0]["offset"] == 0x20
    assert rec.name == rows[0]["new_name"]
    assert rec.name != "ROBERT"
    assert rec.name_dirty is True
    assert FakeFDIFile.instances[0].modified_records == {0x20: rec}
    assert FakeFDIFile.instances[0].saved is True


def test_process_file_skips_duplicate_offsets_with_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(bulk_rename_core, "FDIFile", FakeFDIFile)

    fdi_path = tmp_path / "JUGDUP.FDI"
    fdi_path.write_bytes(b"")
    rec1 = _make_player("ALPHA", team_id=1, squad_number=1)
    rec2 = _make_player("BRAVO", team_id=2, squad_number=2)
    FakeFDIFile.fixtures[str(fdi_path)] = [
        (0x1234, rec1),
        (0x1234, rec2),  # duplicate offset should be skipped
    ]

    rows = []
    result = bulk_rename_core.process_player_file(fdi_path, rows, dry_run=True)

    assert len(rows) == 1
    assert rows[0]["offset"] == 0x1234
    assert result.changed_players == 1
    assert result.skipped_players == 1
    assert any("duplicate offset" in warning.lower() for warning in result.warnings)


def test_revert_file_prefers_offset_over_record_index(tmp_path, monkeypatch):
    monkeypatch.setattr(bulk_rename_core, "FDIFile", FakeFDIFile)

    fdi_path = tmp_path / "JUGREV.FDI"
    fdi_path.write_bytes(b"")
    wrong_rec = _make_player("Z00000000", team_id=1, squad_number=1)
    target_rec = _make_player("Z00000001", team_id=2, squad_number=2)
    FakeFDIFile.fixtures[str(fdi_path)] = [(0x30, wrong_rec), (0x10, target_rec)]

    row = {
        "file": "JUGREV.FDI",
        "record_index": "0",  # stale/incorrect on purpose
        "offset": "0x10",
        "offset_hex": "0x10",
        "original_name": "ORIGNAME1",
        "new_name": "Z00000001",
    }
    assert len(row["original_name"]) == len(target_rec.name)

    bulk_rename_core.revert_player_file(fdi_path, [row], dry_run=False)

    assert wrong_rec.name == "Z00000000"
    assert target_rec.name == "ORIGNAME1"
    assert target_rec.name_dirty is True
    inst = FakeFDIFile.instances[0]
    assert inst.modified_records == {0x10: target_rec}
    assert inst.saved is True


def test_revert_file_falls_back_to_record_index_when_offset_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bulk_rename_core, "FDIFile", FakeFDIFile)

    fdi_path = tmp_path / "JUGOLDMAP.FDI"
    fdi_path.write_bytes(b"")
    rec0 = _make_player("Z00000000")
    rec1 = _make_player("Z00000001")
    FakeFDIFile.fixtures[str(fdi_path)] = [(0x40, rec0), (0x44, rec1)]

    row = {
        "file": "JUGOLDMAP.FDI",
        "record_index": "1",
        "original_name": "ORIGNAME1",
        "new_name": "Z00000001",
    }
    assert len(row["original_name"]) == len(rec1.name)

    bulk_rename_core.revert_player_file(fdi_path, [row], dry_run=False)

    assert rec0.name == "Z00000000"
    assert rec1.name == "ORIGNAME1"
    assert FakeFDIFile.instances[0].modified_records == {0x44: rec1}
