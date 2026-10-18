from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_2015_english92_runtime_picker import audit_runtime_picker  # noqa: E402


def _team(club: str, division: str, record_id: int) -> dict[str, object]:
    return {"club": club, "division": division, "record_id": record_id}


def _manifest() -> dict[str, object]:
    teams = []
    divisions = (("Premier League", 20), ("Championship", 24), ("League One", 24), ("League Two", 24))
    record_id = 1
    for division, count in divisions:
        for index in range(count):
            teams.append(_team(f"{division} Club {index + 1}", division, record_id))
            record_id += 1
    return {"release_profile": "test", "teams": teams}


def _capture() -> dict[str, object]:
    divisions = []
    for panel_index, panel in enumerate(("division_01", "division_02", "division_03", "division_04")):
        division = ("Premier League", "Championship", "League One", "League Two")[panel_index]
        divisions.append({
            "division_key": panel,
            "teams": [{"row_index": row + 1, "text": f"{division} Club {row + 1}"} for row in range(20)],
        })
    return {"divisions": divisions}


def test_runtime_picker_audit_records_actual_four_non_picker_clubs():
    result = audit_runtime_picker(season_manifest=_manifest(), selector_capture=_capture())
    assert result["result"] == "pass"
    assert [len(panel["runtime_non_picker_clubs"]) for panel in result["panels"]] == [0, 4, 4, 4]
    assert result["panels"][1]["runtime_non_picker_clubs"][0]["club"] == "Championship Club 21"


def test_runtime_picker_audit_fails_when_a_picker_label_is_not_in_its_division():
    capture = _capture()
    capture["divisions"][1]["teams"][0]["text"] = "Premier League Club 1"
    result = audit_runtime_picker(season_manifest=_manifest(), selector_capture=capture)
    assert result["result"] == "fail"
    assert result["failures"]
