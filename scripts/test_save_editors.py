#!/usr/bin/env python3
"""Tests for saving coach and team records using save_modified_records."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import pytest

# Ensure package imports work when running as a standalone script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.coach_models import EditableCoachRecord, parse_coaches_from_record
from app.file_writer import save_modified_records
from app.io import FDIFile
from app.models import TeamRecord


def test_coach() -> None:
    coach_path = Path("DBDAT/ENT98030.FDI")
    if not coach_path.exists():
        pytest.skip("Required data file not found: DBDAT/ENT98030.FDI")

    data = coach_path.read_bytes()
    fdi = FDIFile(str(coach_path))
    fdi.load()

    for entry, decoded, _ in fdi.iter_decoded_directory_entries():
        coaches = parse_coaches_from_record(decoded) or []
        if not coaches:
            continue

        coach = coaches[0]
        editable = EditableCoachRecord(
            decoded,
            entry.offset,
            getattr(coach, "given_name", ""),
            getattr(coach, "surname", ""),
        )
        new_given = (editable.given_name or "Coach") + "_X"
        editable.set_name(new_given, editable.surname)

        new_bytes = save_modified_records(str(coach_path), data, [(entry.offset, editable)])
        print(
            "COACH UPDATED:",
            coach_path,
            "offset",
            hex(entry.offset),
            "orig_len",
            len(data),
            "new_len",
            len(new_bytes),
            "delta",
            len(new_bytes) - len(data),
        )
        assert len(new_bytes) >= len(data)
        return

    pytest.skip("No coach entries parsed from ENT98030.FDI")


def test_team() -> None:
    team_path = Path("DBDAT/EQ98030.FDI")
    if not team_path.exists():
        pytest.skip("Required data file not found: DBDAT/EQ98030.FDI")

    data = team_path.read_bytes()
    fdi = FDIFile(str(team_path))
    fdi.load()

    for entry, decoded, _ in fdi.iter_decoded_directory_entries():
        team = TeamRecord(decoded, entry.offset)
        if not team.name or team.name in ("Unknown Team", "Parse Error"):
            continue

        try:
            old_name = team.name
            new_name = old_name + "_X"
            team.set_name(new_name)
            new_bytes = save_modified_records(str(team_path), data, [(entry.offset, team)])
            print(
                "TEAM UPDATED:",
                team_path,
                "offset",
                hex(entry.offset),
                "oldname",
                old_name,
                "new_len",
                len(new_bytes),
                "delta",
                len(new_bytes) - len(data),
            )
            assert len(new_bytes) >= len(data)
            return
        except Exception as exc:  # pragma: no cover - diagnostic output
            print("TEAM MODIFY FAILED", exc)
            traceback.print_exc()
            pytest.fail("Team modification failed")

    pytest.skip("No suitable team entries found in EQ98030.FDI")


if __name__ == "__main__":
    try:
        test_coach()
        test_team()
    except pytest.SkipTest as exc:
        print(exc)
        sys.exit(0)

