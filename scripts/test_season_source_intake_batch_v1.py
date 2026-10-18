"""Focused safety tests for the generic source-intake batch coordinator."""

from __future__ import annotations

import copy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import foreign_carrier_assignment_v1 as assignments  # noqa: E402
from scripts.merge_footballsquads_captures import merge_captures  # noqa: E402
from scripts import season_source_intake_batch_v1 as batch  # noqa: E402
from scripts import season_source_bundle_v1 as bundles  # noqa: E402
from scripts import season_source_intake_v1 as intake  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


HASH = "a" * 64
SOURCE_HASH = "b" * 64


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
                    "name": "Baseline FC",
                    "full_name": "Baseline FC",
                    "ground_name": "Ground",
                    "seated_capacity": 10000,
                    "active_manager_carrier_id": 101,
                },
                "roster_slots": [
                    {
                        "slot_index": 0,
                        "player_carrier_id": 1000,
                        "flag": 0,
                        "family": "dd6360",
                        "baseline_name": "Baseline Player",
                    }
                ],
                "topology_policy": "preserve-existing-carrier-and-roster-slots",
            }
        ],
        "known_baseline_duplicate_player_carriers": [],
    }


def _capture(*, club_name: str = "Historical FC") -> dict[str, object]:
    return {
        "schema_version": assignments.SOURCE_SCHEMA,
        "source": {
            "title": "Fixture source",
            "repository": "https://example.invalid/source",
            "revision": None,
            "license": "CC0-1.0",
        },
        "season": {"catalog": "2000-2001", "label": "2000/01"},
        "clubs": [
            {
                "country_catalog": "spain",
                "competition_catalog": "laliga",
                "club_name": club_name,
                "competition_name": "League",
                "source_path": f"spain/2000-2001/laliga/{club_name.casefold().replace(' ', '-')}.txt",
                "source_sha256": SOURCE_HASH,
                "players": [
                    {
                        "shirt_number": 1,
                        "name": "Known Player",
                        "nationality": "ESP",
                        "position": "M",
                        "height_cm": 180,
                        "weight_kg": 75,
                        "birth_date": "1980-01-01",
                        "unresolved_fields": [],
                    }
                ],
            }
        ],
        "summary": {
            "club_count": 1,
            "player_count": 1,
            "player_rows_with_unresolved_facts": 0,
            "country_catalogs": ["spain"],
            "competition_catalogs": ["spain/laliga"],
        },
    }


def _write(path: Path, value: dict[str, object]) -> None:
    assignments.write_canonical_json(path, value)


def _make_season(
    tmp_path: Path,
    *,
    season_id: str,
    captures: list[tuple[str, dict[str, object]]],
    assignment_capture: dict[str, object] | None,
) -> Path:
    season_dir = tmp_path / "seasons" / season_id
    _write(season_dir / batch.REGISTRY_NAME, _registry())
    for filename, capture in captures:
        _write(season_dir / "sources" / filename, capture)
    if assignment_capture is not None:
        assignment = assignments.initialise_assignment(
            registry=_registry(),
            source_capture=assignment_capture,
            host_reports=[],
            assignment_id=f"world-{season_id}-fixed-carriers",
        )
        _write(season_dir / batch.BASE_ASSIGNMENT_NAME, assignment)
    return tmp_path / "seasons"


def _codes(row: dict[str, object]) -> set[str]:
    return {str(item["code"]) for item in row["blockers"]}  # type: ignore[index]


def test_batch_resolves_the_assignment_hash_not_a_capture_filename(tmp_path: Path) -> None:
    capture = _capture()
    seasons_root = _make_season(
        tmp_path,
        season_id="2000-01",
        captures=[("arbitrary-capture-name.json", capture)],
        assignment_capture=capture,
    )

    matrix = batch.build_matrix(seasons_root=seasons_root, selected=["2000-01"])
    row = matrix["rows"][0]

    assert row["blockers"] == []
    assert row["source_captures"] == {
        "canonical_capture_count": 1,
        "matching_capture": {
            "path": "seasons/2000-01/sources/arbitrary-capture-name.json",
            "sha256": assignments.sha256_file(seasons_root / "2000-01/sources/arbitrary-capture-name.json"),
        },
    }
    assert row["source_intake"]["status"] == "missing"
    assert matrix["summary"] == {
        "season_count": 1,
        "source_intake_eligible_count": 1,
        "source_intake_materialised_count": 0,
        "blocked_count": 0,
    }


def test_batch_ignores_non_capture_source_evidence_but_rejects_a_malformed_declared_capture(tmp_path: Path) -> None:
    capture = _capture()
    seasons_root = _make_season(
        tmp_path,
        season_id="2000-01",
        captures=[("source.json", capture)],
        assignment_capture=capture,
    )
    source_dir = seasons_root / "2000-01" / "sources"
    (source_dir / "source-availability.json").write_text('{"status": "blocked"}\n', encoding="utf-8")

    matrix = batch.build_matrix(seasons_root=seasons_root, selected=["2000-01"])
    assert matrix["rows"][0]["blockers"] == []

    malformed = source_dir / "declared-capture.json"
    malformed.write_text(
        '{"schema_version": "pm99-footballsquads-season-capture-v1"}\n', encoding="utf-8"
    )
    broken = batch.build_matrix(seasons_root=seasons_root, selected=["2000-01"])
    assert _codes(broken["rows"][0]) == {"source-capture-invalid"}


def test_batch_reports_missing_assignment_hash_mismatch_and_multi_source_without_guessing(tmp_path: Path) -> None:
    missing = _capture(club_name="Missing Assignment")
    mismatch = _capture(club_name="Declared But Absent")
    available = _capture(club_name="Available But Wrong")
    multi_match = _capture(club_name="Matched Capture")
    multi_other = _capture(club_name="Other Capture")
    root = _make_season(
        tmp_path, season_id="2000-01", captures=[("only.json", missing)], assignment_capture=None
    )
    _make_season(
        tmp_path,
        season_id="2001-02",
        captures=[("available.json", available)],
        assignment_capture=mismatch,
    )
    _make_season(
        tmp_path,
        season_id="2002-03",
        captures=[("match.json", multi_match), ("other.json", multi_other)],
        assignment_capture=multi_match,
    )

    matrix = batch.build_matrix(
        seasons_root=root,
        selected=["2000-01", "2001-02", "2002-03"],
    )
    rows = {row["season_id"]: row for row in matrix["rows"]}

    assert _codes(rows["2000-01"]) == {"no-assignment"}
    assert _codes(rows["2001-02"]) == {"source-capture-hash-mismatch"}
    assert _codes(rows["2002-03"]) == {"multi-source-composition-required"}
    assert rows["2002-03"]["source_captures"]["matching_capture"]["path"].endswith("match.json")
    assert rows["2002-03"]["source_intake"]["status"] == "not-evaluated"


def test_write_materialises_only_missing_exact_receipts(tmp_path: Path) -> None:
    capture = _capture()
    seasons_root = _make_season(
        tmp_path,
        season_id="2000-01",
        captures=[("source.json", capture)],
        assignment_capture=capture,
    )

    written = batch.build_matrix(seasons_root=seasons_root, selected=["2000-01"], write=True)
    row = written["rows"][0]
    assert row["blockers"] == []
    assert row["source_intake"]["status"] == "materialised"
    assert row["source_intake_audit"]["status"] == "materialised"
    intake_path = seasons_root / "2000-01" / batch.INTAKE_NAME
    audit_path = seasons_root / "2000-01" / batch.AUDIT_NAME
    assert intake_path.is_file() and audit_path.is_file()

    rerun = batch.build_matrix(seasons_root=seasons_root, selected=["2000-01"], write=True)
    assert rerun["rows"][0]["source_intake"]["status"] == "validated"
    assert rerun["rows"][0]["source_intake_audit"]["status"] == "validated"


def test_batch_can_use_an_explicit_rebound_assignment_filename(tmp_path: Path) -> None:
    capture = _capture()
    seasons_root = _make_season(
        tmp_path,
        season_id="2000-01",
        captures=[("source.json", capture)],
        assignment_capture=capture,
    )
    season_dir = seasons_root / "2000-01"
    rebound = season_dir / "foreign-carrier-assignment-composed.json"
    (season_dir / batch.BASE_ASSIGNMENT_NAME).rename(rebound)

    matrix = batch.build_matrix(
        seasons_root=seasons_root,
        selected=["2000-01"],
        assignment_name=rebound.name,
    )

    assert matrix["rows"][0]["blockers"] == []
    assert matrix["rows"][0]["base_assignment"]["path"].endswith(rebound.name)


def test_batch_accepts_only_a_hash_bound_composition_with_all_inputs_present(tmp_path: Path) -> None:
    first = _capture(club_name="Split FC")
    second = _capture(club_name="Calendar FC")
    seasons_root = _make_season(
        tmp_path,
        season_id="2000-01",
        captures=[("split.json", first), ("calendar.json", second)],
        assignment_capture=None,
    )
    season_dir = seasons_root / "2000-01"
    merged = merge_captures(
        captures=[
            ("calendar.json", second, assignments.sha256_file(season_dir / "sources/calendar.json")),
            ("split.json", first, assignments.sha256_file(season_dir / "sources/split.json")),
        ],
        merged_catalog="2000-01-hybrid",
        merged_label="2000/01",
    )
    _write(season_dir / "sources/composed.json", merged)
    composed_assignment = assignments.initialise_assignment(
        registry=_registry(),
        source_capture=merged,
        host_reports=[],
        assignment_id="world-2000-01-composed-fixed-carriers",
    )
    _write(season_dir / "foreign-carrier-assignment-composed.json", composed_assignment)

    matrix = batch.build_matrix(
        seasons_root=seasons_root,
        selected=["2000-01"],
        assignment_name="foreign-carrier-assignment-composed.json",
    )
    row = matrix["rows"][0]

    assert row["blockers"] == []
    assert row["source_captures"]["composition"] == {
        "status": "validated",
        "input_capture_count": 2,
    }
    assert row["coverage"]["source_club_count"] == 2


def test_default_batch_uses_a_verified_season_local_source_bundle(tmp_path: Path) -> None:
    split = _capture(club_name="Split FC")
    calendar = _capture(club_name="Calendar FC")
    seasons_root = _make_season(
        tmp_path,
        season_id="2000-01",
        captures=[("split.json", split), ("calendar.json", calendar)],
        assignment_capture=split,
    )
    season_dir = seasons_root / "2000-01"
    bundle = {
        "schema_version": bundles.SCHEMA,
        "bundle_id": "world-2000-01-source-bundle",
        "season": {"catalog": "2000-01-hybrid", "label": "2000/01"},
        "registry": {
            "relative_path": batch.REGISTRY_NAME,
            "sha256": assignments.sha256_file(season_dir / batch.REGISTRY_NAME),
        },
        "captures": [
            {
                "relative_path": "sources/calendar.json",
                "sha256": assignments.sha256_file(season_dir / "sources/calendar.json"),
            },
            {
                "relative_path": "sources/split.json",
                "sha256": assignments.sha256_file(season_dir / "sources/split.json"),
            },
        ],
        "output": {"relative_path": "sources/composed.json"},
        "assignment_rebinding": {
            "input_relative_path": batch.BASE_ASSIGNMENT_NAME,
            "input_sha256": assignments.sha256_file(season_dir / batch.BASE_ASSIGNMENT_NAME),
            "previous_capture_relative_path": "sources/split.json",
            "output_relative_path": "foreign-carrier-assignment-composed.json",
            "assignment_id": "world-2000-01-composed-fixed-carriers",
        },
    }
    bundle_path = season_dir / batch.SOURCE_BUNDLE_NAME
    _write(bundle_path, bundle)
    bundles.build_bundle(bundle_path=bundle_path, bundle=bundle)

    matrix = batch.build_matrix(seasons_root=seasons_root, selected=["2000-01"])
    row = matrix["rows"][0]

    assert row["blockers"] == []
    assert row["source_bundle"] == {
        "path": "seasons/2000-01/source-bundle.json",
        "bundle_id": "world-2000-01-source-bundle",
        "status": "verified",
        "capture_sha256": assignments.sha256_file(season_dir / "sources/composed.json"),
        "assignment_sha256": assignments.sha256_file(season_dir / "foreign-carrier-assignment-composed.json"),
    }
    assert row["base_assignment"]["path"].endswith("foreign-carrier-assignment-composed.json")


def test_default_scope_excludes_1999_but_an_explicit_selection_can_include_it(tmp_path: Path) -> None:
    root = tmp_path / "seasons"
    for season_id in ("1999-00", "2000-01", "2025-26"):
        (root / season_id).mkdir(parents=True)

    default_scope = batch.discover_season_ids(seasons_root=root)
    assert len(default_scope) == 26
    assert default_scope[0] == "2000-01"
    assert default_scope[-1] == "2025-26"
    assert "1999-00" not in default_scope
    assert batch.discover_season_ids(seasons_root=root, selected=["1999-00"]) == ["1999-00"]
