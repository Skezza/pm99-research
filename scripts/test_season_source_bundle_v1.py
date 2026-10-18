from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignments  # noqa: E402
from scripts import season_source_bundle_v1 as bundles  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


HASH = "a" * 64


def _registry() -> dict[str, object]:
    return {
        "schema_version": ledger.REGISTRY_SCHEMA,
        "registry_id": "synthetic-world-fixed-carriers",
        "baseline": {
            "database_files": {
                name: {"relative_path": f"DBDAT/{name}", "sha256": HASH, "size": 100}
                for name in ("ENT98030.FDI", "EQ98030.FDI", "JUG98030.FDI")
            }
        },
        "topology_policy": "preserve-existing-carriers-no-country-division-or-membership-claims",
        "carriers": [
            {
                "carrier_id": 1,
                "record_mode": 1,
                "baseline_club": {
                    "name": "Baseline",
                    "full_name": "Baseline FC",
                    "ground_name": "Ground",
                    "seated_capacity": 10000,
                    "active_manager_carrier_id": 101,
                },
                "roster_slots": [
                    {
                        "slot_index": index,
                        "player_carrier_id": 1000 + index,
                        "flag": 0,
                        "family": "dd6360",
                        "baseline_name": f"Player {index}",
                    }
                    for index in range(16)
                ],
                "topology_policy": "preserve-existing-carrier-and-roster-slots",
            }
        ],
        "known_baseline_duplicate_player_carriers": [],
    }


def _capture(*, catalog: str, label: str, country: str, club_name: str) -> dict[str, object]:
    source_hash = hashlib.sha256(f"{catalog}:{country}:{club_name}".encode()).hexdigest()
    return {
        "schema_version": assignments.SOURCE_SCHEMA,
        "source": {
            "title": "Fixture historic source",
            "repository": "https://example.invalid/source",
            "revision": "1" * 40,
            "license": "CC0-1.0",
        },
        "season": {"catalog": catalog, "label": label},
        "clubs": [
            {
                "country_catalog": country,
                "competition_catalog": "league",
                "club_name": club_name,
                "competition_name": "League",
                "source_path": f"{country}/{catalog}/league/{club_name}.txt",
                "source_sha256": source_hash,
                "players": [{"name": f"Player {index}"} for index in range(16)],
            }
        ],
        "summary": {
            "club_count": 1,
            "player_count": 16,
            "player_rows_with_unresolved_facts": 0,
            "country_catalogs": [country],
            "competition_catalogs": [f"{country}/league"],
        },
    }


def _write(path: Path, value: dict[str, object]) -> str:
    assignments.write_canonical_json(path, value)
    return assignments.sha256_file(path)


def _bundle_fixture(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    registry = _registry()
    registry_hash = _write(tmp_path / "fixed-carrier-registry.json", registry)
    calendar = _capture(catalog="2008", label="2008", country="brazil", club_name="Santos")
    split = _capture(catalog="2008-2009", label="2008/09", country="spain", club_name="Barcelona")
    calendar_hash = _write(tmp_path / "sources/calendar.json", calendar)
    split_hash = _write(tmp_path / "sources/split.json", split)
    assignment = assignments.initialise_assignment(
        registry=registry,
        source_capture=split,
        host_reports=[],
        assignment_id="world-2008-09-fixed-carriers",
    )
    assignment_hash = _write(tmp_path / "foreign-carrier-assignment.json", assignment)
    bundle: dict[str, object] = {
        "schema_version": bundles.SCHEMA,
        "bundle_id": "world-2008-09-source-bundle",
        "season": {"catalog": "2008-09-hybrid", "label": "2008/09"},
        "registry": {"relative_path": "fixed-carrier-registry.json", "sha256": registry_hash},
        "captures": [
            {"relative_path": "sources/calendar.json", "sha256": calendar_hash},
            {"relative_path": "sources/split.json", "sha256": split_hash},
        ],
        "output": {"relative_path": "sources/composed.json"},
        "assignment_rebinding": {
            "input_relative_path": "foreign-carrier-assignment.json",
            "input_sha256": assignment_hash,
            "previous_capture_relative_path": "sources/split.json",
            "output_relative_path": "foreign-carrier-assignment-composed.json",
            "assignment_id": "world-2008-09-composed-fixed-carriers",
        },
    }
    bundle_path = tmp_path / "source-bundle.json"
    _write(bundle_path, bundle)
    return bundle_path, bundle


def test_bundle_builds_and_verifies_hash_locked_composition(tmp_path: Path) -> None:
    bundle_path, bundle = _bundle_fixture(tmp_path)

    receipt = bundles.build_bundle(bundle_path=bundle_path, bundle=bundle)

    assert receipt["season"] == {"catalog": "2008-09-hybrid", "label": "2008/09"}
    assert (tmp_path / "sources/composed.json").is_file()
    assert (tmp_path / "foreign-carrier-assignment-composed.json").is_file()
    assert bundles.verify_bundle(bundle_path=bundle_path, bundle=bundle) == receipt


def test_bundle_refuses_replacing_its_completed_outputs(tmp_path: Path) -> None:
    bundle_path, bundle = _bundle_fixture(tmp_path)
    bundles.build_bundle(bundle_path=bundle_path, bundle=bundle)

    with pytest.raises(bundles.SourceBundleError, match="already exist"):
        bundles.build_bundle(bundle_path=bundle_path, bundle=bundle)


def test_bundle_rejects_stale_capture_before_materialising_output(tmp_path: Path) -> None:
    bundle_path, bundle = _bundle_fixture(tmp_path)
    (tmp_path / "sources/calendar.json").write_bytes(b"{}\n")

    with pytest.raises(bundles.SourceBundleError, match="capture hash does not match"):
        bundles.build_bundle(bundle_path=bundle_path, bundle=bundle)
    assert not (tmp_path / "sources/composed.json").exists()


def test_bundle_rejects_two_inputs_with_the_same_filename(tmp_path: Path) -> None:
    bundle_path, bundle = _bundle_fixture(tmp_path)
    bundle["captures"] = [
        {"relative_path": "sources/calendar.json", "sha256": bundle["captures"][0]["sha256"]},  # type: ignore[index]
        {"relative_path": "sources2/calendar.json", "sha256": bundle["captures"][1]["sha256"]},  # type: ignore[index]
    ]

    with pytest.raises(bundles.SourceBundleError, match="unique filenames"):
        bundles.validate_bundle(bundle)
