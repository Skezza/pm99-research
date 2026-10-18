from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import plan_transfermarkt_opening_lineups_batch_v1 as planner


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _intake(path: Path) -> None:
    document = {
        "source_clubs": [
            {"selector": {"club_name": "Stoke City", "competition_catalog": "d2", "country_catalog": "eng"}},
            {"selector": {"club_name": "Sydney Olympic", "competition_catalog": "prem", "country_catalog": "australia"}},
        ]
    }
    path.parent.mkdir(parents=True)
    path.write_text(_canonical(document), encoding="utf-8")


def test_reviewed_aliases_preserve_historical_english_codes() -> None:
    codes = planner.reviewed_competition_codes()
    assert codes[("eng", "d1")] == "EFD2"
    assert codes[("eng", "d2")] == "ENSD"
    assert codes[("eng", "d3")] == "ENTD"
    assert codes[("eng", "flcham")] == "GB2"
    assert codes[("spain", "laliga2")] == "ES2"


def test_all_repository_catalog_aliases_are_explicitly_classified() -> None:
    classified = set(planner.reviewed_competition_codes()) | set(planner.REVIEWED_UNSUPPORTED)
    observed: set[tuple[str, str]] = set()
    for path in sorted((ROOT / "seasons").glob("*/source-intake.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        observed.update(
            (club["selector"]["country_catalog"], club["selector"]["competition_catalog"])
            for club in document["source_clubs"]
        )
    assert observed - classified == set()


def test_plan_writes_canonical_capture_inputs_without_fetching(tmp_path: Path) -> None:
    source = tmp_path / "seasons" / "2000-01" / "source-intake.json"
    _intake(source)
    output = tmp_path / "plans" / "2000-01"
    plan = planner.plan_season(source_intake=source, output_directory=output, repo_root=tmp_path)

    assert plan["summary"] == {
        "source_club_count": 2,
        "supported_club_count": 1,
        "supported_competition_count": 1,
        "unselected_source_club_count": 0,
        "unsupported_club_count": 1,
        "unsupported_competition_count": 1,
    }
    assert plan["capture"]["executed"] is False
    assert plan["capture"]["network_fetch_performed"] is False
    assert plan["unsupported_competitions"][0]["reason"] == "historical-national-soccer-league-code-not-reviewed"
    assert json.loads((output / "competition-map.json").read_text())["competitions"] == [{
        "competition_catalog": "d2", "country_catalog": "eng", "source_competition_code": "ENSD",
    }]
    selectors = json.loads((output / "source-selectors.json").read_text())
    assert [row["club_name"] for row in selectors["clubs"]] == ["Stoke City"]
    assert selectors["excluded_unsupported_club_count"] == 1
    assert (output / "competition-map.json").read_bytes().endswith(b"\n")
    assert not (output / "cache").exists()
    assert not (output / "opening-lineups.json").exists()


def test_discovery_rejects_a_requested_missing_season(tmp_path: Path) -> None:
    seasons = tmp_path / "seasons"
    _intake(seasons / "2000-01" / "source-intake.json")
    try:
        planner.discover_source_intakes(seasons, ["2001-02"])
    except ValueError as exc:
        assert "2001-02" in str(exc)
    else:
        raise AssertionError("missing requested season was accepted")


def test_historical_current_discovery_verifies_revision_hash_and_preserves_season_id(tmp_path: Path) -> None:
    season = tmp_path / "historical" / "2001-02"
    intake = season / "revisions" / "rev-example" / "source-intake.json"
    _intake(intake)
    digest = hashlib.sha256(intake.read_bytes()).hexdigest()
    (season / "current.json").write_text(_canonical({
        "schema_version": "pm99-historical-squad-backfill-current-v1",
        "artifacts": {
            "intake": {"path": "revisions/rev-example/source-intake.json", "sha256": digest},
            "allocation": {"path": "revisions/rev-example/carrier-allocation.json", "sha256": "unused-in-discovery"},
        },
    }), encoding="utf-8")
    revisions = planner.discover_current_source_intakes(tmp_path / "historical", ["2001-02"])
    output = tmp_path / "plans" / "2001-02"
    plan = planner.plan_season(source_intake=revisions[0][1], output_directory=output,
                               repo_root=tmp_path, season_id=revisions[0][0])
    assert plan["season"] == {"directory": "2001-02", "start_year": 2001}
    assert plan["source_intake"]["sha256"] == digest
