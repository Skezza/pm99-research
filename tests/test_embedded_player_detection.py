#!/usr/bin/env python3
"""
Embedded player detection tests:
- Verifies CLI pipeline (app/io.py) detects players inside large sections without separators
- Ensures team_id normalization (>5000 -> 0) for embedded-derived records to avoid misleading values
"""

from pathlib import Path
import sys
import pytest

# Ensure project root is on sys.path for module resolution when running tests directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.io import FDIFile


@pytest.mark.integration
def test_cli_detects_beckham_embedded():
    """Ensure Beckham is found via the embedded-record scanning pass."""
    fdi_path = Path("DBDAT/JUG98030.FDI")
    if not fdi_path.exists():
        pytest.skip("Required database file not found: DBDAT/JUG98030.FDI")

    fdi = FDIFile(fdi_path)
    fdi.load()

    matches = fdi.find_by_name("Beckham")
    assert len(matches) >= 1, "Beckham should be detected by embedded scan"

    names = [f"{r.given_name} {r.surname}".strip() for r in matches]
    assert any("BECKHAM" in n.upper() for n in names), f"Unexpected names for Beckham matches: {names}"


@pytest.mark.integration
def test_team_id_normalized_for_embedded_records():
    """Ensure embedded-derived team IDs are normalized (no misleading large values)."""
    fdi_path = Path("DBDAT/JUG98030.FDI")
    if not fdi_path.exists():
        pytest.skip("Required database file not found: DBDAT/JUG98030.FDI")

    fdi = FDIFile(fdi_path)
    fdi.load()

    # We look for several known embedded patterns to exercise normalization logic broadly
    targets = ["Beckham", "Giggs", "Scholes", "Zidane"]
    all_ok = True
    offending = []

    for target in targets:
        matches = fdi.find_by_name(target)
        for rec in matches:
            if not (0 <= rec.team_id <= 5000):
                all_ok = False
                offending.append((target, rec.team_id, f"{rec.given_name} {rec.surname}"))

    assert all_ok, f"Found unnormalized team_id values: {offending}"
