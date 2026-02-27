import shutil
from pathlib import Path

import pytest

from app.editor_actions import rename_player_records, rename_team_records
from app.editor_helpers import _player_display_name
from app.models import PlayerRecord
from app.editor_sources import gather_player_records, gather_player_records_strict, gather_team_records
from app.xor import decode_entry


def _ensure_data_file(path: Path):
    if not path.exists():
        pytest.skip(f"Required data file not found: {path}")
    return path


def _is_writable_player_entry(path: Path, entry) -> bool:
    """Only use candidates whose offsets decode as real player entries."""
    try:
        decoded, length = decode_entry(path.read_bytes(), entry.offset)
        parsed = PlayerRecord.from_bytes(decoded, entry.offset)
    except Exception:
        return False
    if length < 40 or length > 1024:
        return False
    return _player_display_name(parsed) == _player_display_name(entry.record)


def test_gather_player_records_contains_known_name():
    player_fdi = _ensure_data_file(Path("DBDAT/JUG98030.FDI"))
    valid, _ = gather_player_records(str(player_fdi))
    names = [_player_display_name(entry.record).upper() for entry in valid]
    assert any("MORIENTES" in name for name in names)


def test_gather_player_records_strict_contains_known_name():
    player_fdi = _ensure_data_file(Path("DBDAT/JUG98030.FDI"))
    valid, uncertain = gather_player_records_strict(str(player_fdi))
    names = [_player_display_name(entry.record).upper() for entry in (valid + uncertain)]
    assert any("MORIENTES" in name for name in names)


def test_gather_team_records_returns_valid_entries():
    team_fdi = _ensure_data_file(Path("DBDAT/EQ98030.FDI"))
    valid, _ = gather_team_records(str(team_fdi))
    assert valid
    assert any((entry.record.name or "").strip() for entry in valid)


def test_rename_player_preserves_length(tmp_path):
    player_fdi = _ensure_data_file(Path("DBDAT/JUG98030.FDI"))
    valid, _ = gather_player_records(str(player_fdi))
    candidate = next(
        (
            entry
            for entry in valid
            if len(_player_display_name(entry.record).split()) >= 2
            and _is_writable_player_entry(player_fdi, entry)
        ),
        None,
    )
    if candidate is None:
        pytest.skip("No writable player entry found in fixture database")
    old_name = _player_display_name(candidate.record)
    assert old_name
    parts = old_name.split(maxsplit=1)
    if len(parts[1]) < 1:
        pytest.skip("Unable to construct alternative surname")
    given, surname = parts
    new_surname = surname[:-1] + ("Z" if surname[-1] != "Z" else "Y")
    new_name = f"{given} {new_surname}"

    target = tmp_path / "JUG98030.FDI"
    shutil.copy2(player_fdi, target)
    result = rename_player_records(
        str(target),
        old_name,
        new_name,
        include_uncertain=True,
        target_offset=candidate.offset,
    )
    assert result.changes
    assert result.backup_path
    assert all(change.old_len == change.new_len for change in result.changes)
    refreshed, _ = gather_player_records(str(target))
    assert any(_player_display_name(entry.record) == new_name for entry in refreshed)


def test_rename_team_creates_backup(tmp_path):
    team_fdi = _ensure_data_file(Path("DBDAT/EQ98030.FDI"))
    valid, _ = gather_team_records(str(team_fdi))
    candidate = next(
        (entry for entry in valid if (entry.record.name or "").strip()),
        None,
    )
    if candidate is None:
        pytest.skip("No renameable team records found")
    old_name = candidate.record.name or ""
    if len(old_name) < 2:
        pytest.skip("Team name too short for rename test")
    chars = list(old_name)
    idx = next((i for i, ch in enumerate(chars) if ch.isalpha()), None)
    if idx is None:
        pytest.skip("Team name has no alphabetic characters to mutate")
    chars[idx] = "Z" if chars[idx] != "Z" else "Y"
    new_name = "".join(chars)
    target = tmp_path / "EQ98030.FDI"
    shutil.copy2(team_fdi, target)
    result = rename_team_records(
        str(target),
        old_name,
        new_name,
        include_uncertain=True,
        target_offsets=[candidate.offset],
    )
    assert result.changes
    assert result.backup_path
    assert result.applied_to_disk is True
    refreshed, _ = gather_team_records(str(target))
    assert any((entry.record.name or "") == new_name for entry in refreshed)
