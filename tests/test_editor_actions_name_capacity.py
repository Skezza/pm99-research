from pathlib import Path

import pytest

from app.editor_actions import inspect_player_name_capacities
from app.io import FDIFile


FIXTURE = Path("tests/debug_roundtrip.fdi")


def _first_named_player(path: Path):
    fdi = FDIFile(str(path))
    fdi.load()
    for offset, record in getattr(fdi, "records_with_offsets", []):
        name = (getattr(record, "name", "") or "").strip()
        if not name:
            given = str(getattr(record, "given_name", "") or "").strip()
            surname = str(getattr(record, "surname", "") or "").strip()
            name = " ".join(part for part in (given, surname) if part).strip()
        if name:
            return int(offset), name
    return None, ""


def test_player_name_capacity_probe_reports_capacity_and_proposed_eval():
    if not FIXTURE.exists():
        pytest.skip("debug_roundtrip fixture is missing")

    offset, name = _first_named_player(FIXTURE)
    if offset is None or not name:
        pytest.skip("fixture did not expose a named player")

    proposed_name = (name + " " + ("X" * 64)).strip()
    result = inspect_player_name_capacities(
        str(FIXTURE),
        target_name=name,
        target_offset=offset,
        proposed_name=proposed_name,
        include_uncertain=True,
        limit=10,
    )

    assert result.matched_count >= 1
    assert result.records
    row = result.records[0]
    assert row.offset == offset
    assert row.current_name_bytes > 0
    assert row.exact_full_name_max_bytes >= 0
    assert row.structured_window_max_bytes >= 0
    assert row.proposed_name == proposed_name
    assert row.proposed_name_bytes == len(proposed_name.encode("cp1252", errors="replace"))
    assert row.proposed_overflow_by == max(0, row.proposed_name_bytes - row.exact_full_name_max_bytes)


def test_player_name_capacity_probe_returns_empty_for_missing_name():
    if not FIXTURE.exists():
        pytest.skip("debug_roundtrip fixture is missing")

    result = inspect_player_name_capacities(
        str(FIXTURE),
        target_name="Definitely Not A Real PM99 Player Name",
        include_uncertain=True,
        limit=5,
    )

    assert result.matched_count == 0
    assert result.records == []
