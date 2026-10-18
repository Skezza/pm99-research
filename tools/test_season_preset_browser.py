from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from tools.season_preset_browser import (
    PresetCatalog,
    _structured_summary,
    discover_presets,
    discover_runtime_recipe_presets,
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _empty_indexes(tmp_path: Path) -> dict[str, Path]:
    return {
        "baseline_index": tmp_path / "missing-baseline.json",
        "manager_overlay_index": tmp_path / "missing-manager-index.json",
        "overlays_root": tmp_path / "missing-overlays",
    }


def test_discovers_season_presets_without_raw_sources(tmp_path: Path) -> None:
    _write(tmp_path / "2000-01" / "fixed-carrier-ledger.json", {"schema_version": "ledger-v1", "ledger_id": "test-ledger"})
    (tmp_path / "2000-01" / "README.md").write_text("# Season\n", encoding="utf-8")
    _write(tmp_path / "2000-01" / "sources" / "squad.json", {"source": "raw"})
    _write(tmp_path / "editorial" / "ignored.json", {"not": "a season"})

    discovered = discover_presets(tmp_path)

    assert list(discovered) == ["2000-01"]
    assert [item.relative_path for item in discovered["2000-01"]] == ["README.md", "fixed-carrier-ledger.json"]
    assert discovered["2000-01"][1].title == "test-ledger"


def test_optional_source_capture_and_catalog_allowlist(tmp_path: Path) -> None:
    _write(tmp_path / "2015-16" / "workspace.json", {"schema_version": "workspace-v1", "workspace_id": "world-2015"})
    _write(tmp_path / "2015-16" / "sources" / "squad.json", {"source": "dated"})
    catalog = PresetCatalog(tmp_path, include_source_captures=True, **_empty_indexes(tmp_path))

    index = catalog.index()
    assert index["read_only"] is True
    assert index["season_count"] == 1
    assert [row["relative_path"] for row in index["seasons"][0]["presets"]] == [
        "overview/season-assembly-map.json", "sources/squad.json", "workspace.json"
    ]
    document = catalog.read("2015-16", "workspace.json")
    assert document["content_type"] == "json"
    assert '"workspace_id": "world-2015"' in document["content"]
    with pytest.raises(KeyError):
        catalog.read("2015-16", "../../outside.json")


def test_catalog_includes_local_playtest_manifest_for_its_target_season(tmp_path: Path) -> None:
    seasons_root = tmp_path / "seasons"
    playtests_root = tmp_path / "playtests"
    _write(seasons_root / "2000-01" / "source-intake.json", {"schema_version": "intake-v1"})
    _write(
        playtests_root / "pm99-2000-01-calendar-playtest-r1" / "provisional-playtest-manifest.json",
        {
            "schema_version": "pm99-provisional-playtest-calendar-variant-v1",
            "target_season": "2000-01",
            "variant_id": "pm99-2000-01-calendar-playtest-r1",
        },
    )

    catalog = PresetCatalog(
        seasons_root,
        include_source_captures=False,
        playtests_root=playtests_root,
        **_empty_indexes(tmp_path),
    )

    rows = catalog.index()["seasons"][0]["presets"]
    playtest = next(row for row in rows if row["kind"] == "playtest")
    assert playtest["title"] == "pm99-2000-01-calendar-playtest-r1"
    assert playtest["relative_path"].startswith("local-playtest/")
    document = catalog.read("2000-01", playtest["id"])
    assert document["content_type"] == "json"
    assert '"target_season": "2000-01"' in document["content"]


def test_catalog_discovers_generated_authoring_manifests_without_uploads(tmp_path: Path) -> None:
    seasons_root = tmp_path / "seasons"
    authoring_root = tmp_path / "authoring"
    _write(seasons_root / "2000-01" / "workspace.json", {"schema_version": "workspace-v1"})
    source_path = authoring_root / "2000-01" / "revisions" / "rev-example" / "draft-season-package.json"
    _write(source_path, {"schema_version": "pm99-season-package-v2", "package_id": "pm99-2000-01-draft"})
    _write(
        authoring_root / "2000-01" / "current.json",
        {
            "schema_version": "pm99-historical-squad-backfill-current-v1",
            "revision_id": "rev-example",
            "artifacts": {
                "source": {
                    "path": "revisions/rev-example/draft-season-package.json",
                    "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                }
            },
        },
    )

    catalog = PresetCatalog(
        seasons_root,
        include_source_captures=False,
        authoring_root=authoring_root,
        **_empty_indexes(tmp_path),
    )

    rows = catalog.index()["seasons"][0]["presets"]
    generated = next(row for row in rows if row["kind"] == "authoring-input")
    assert generated["relative_path"] == "authoring/revisions/rev-example/draft-season-package.json"
    document = catalog.read("2000-01", generated["id"])
    assert '"package_id": "pm99-2000-01-draft"' in document["content"]
    assert document["summary"]["title"] == "Club, manager and opening-lineup overview"


def test_structured_summary_exposes_current_revision_and_cross_season_coverage() -> None:
    current = _structured_summary({
        "schema_version": "pm99-historical-squad-backfill-current-v1",
        "revision_id": "rev-example",
        "artifacts": {"source": {"path": "revisions/rev-example/source.json", "sha256": "a" * 64}},
    })
    assert current is not None
    assert current["counts"]["revision"] == "rev-example"
    assert current["rows"][0]["artifact"] == "source"

    matrix = _structured_summary({
        "schema_version": "pm99-historical-squad-current-coverage-matrix-v1",
        "seasons": [{"season": "2000-01", "assigned_real_carrier_count": 400,
                     "unassigned_real_carrier_count": 46}],
    })
    assert matrix is not None
    assert matrix["columns"] == [
        "season", "assigned_real_carrier_count", "unassigned_real_carrier_count"
    ]


def test_structured_summary_exposes_a_read_only_season_assembly_map() -> None:
    overview = _structured_summary({
        "schema_version": "pm99-local-season-assembly-map-v1",
        "state": {"playable": False, "release_status": "not released"},
        "components": [{
            "role": "Frozen base", "kind": "frozen-base", "relative_path": "assembly/base.json", "sha256": "a" * 64,
        }],
    })
    assert overview is not None
    assert overview["counts"]["playable"] is False
    assert overview["rows"][0]["manifest"] == "assembly/base.json"


def test_catalog_stages_and_materialises_a_hash_bound_source_copy(tmp_path: Path) -> None:
    seasons_root = tmp_path / "seasons"
    source_path = seasons_root / "2000-01" / "source.json"
    source = {"clubs": [{"name": "Wrong name"}]}
    _write(source_path, source)
    catalog = PresetCatalog(
        seasons_root,
        include_source_captures=False,
        amendment_output_root=tmp_path / "materialised",
        **_empty_indexes(tmp_path),
    )
    catalog.index()
    staged = catalog.stage_amendment(
        season="2000-01",
        manifest_id="source.json",
        json_pointer="/clubs/0/name",
        replacement="Correct name",
        reason="Opening-season source confirms the club name.",
        evidence="https://example.test/source",
    )
    assert staged["changes"][0]["expected"] == "Wrong name"
    assert json.loads(source_path.read_text(encoding="utf-8")) == source

    receipt = catalog.materialise_amendments(season="2000-01")
    output = Path(receipt["outputs"][0]["output_path"])
    assert json.loads(output.read_text(encoding="utf-8"))["clubs"][0]["name"] == "Correct name"
    assert receipt["state"] == "materialised-source-copies-not-promoted"


def _package() -> dict[str, object]:
    return {
        "schema_version": "pm99-season-package-v2",
        "package_id": "world-2000-01-test",
        "players": [{
            "id": "player-1", "name": "Ada Player", "club_id": "club-1",
            "facts": {
                "birth_date": "1980-01-02", "nationality": "ENG", "primary_position": "M",
                "shirt_number": 8, "height_cm": 170, "weight_kg": 60,
            },
            "ratings": {"values": {"handling": 5, "speed": 70}},
        }],
        "managers": [{"id": "manager-1", "name": "Ada Manager", "carrier_id": 10, "policy": "write"}],
        "clubs": [{
            "id": "club-1", "name": "Ada Town", "full_name": "Ada Town FC", "division": "Division One",
            "ground_name": "Ada Ground", "manager_id": "manager-1", "carrier_id": 10,
        }],
    }


def test_spreadsheet_model_is_year_first_and_stages_a_cell_more_than_once(tmp_path: Path) -> None:
    seasons_root = tmp_path / "seasons"
    _write(seasons_root / "2000-01" / "season-package.json", _package())
    catalog = PresetCatalog(
        seasons_root,
        include_source_captures=False,
        amendment_output_root=tmp_path / "materialised",
        **_empty_indexes(tmp_path),
    )

    assert catalog.index()["seasons"][0]["spreadsheet_ready"] is True
    metadata = catalog.spreadsheet_metadata("2000-01")
    assert [tab["id"] for tab in metadata["workbook"]["tabs"]] == ["players", "managers", "clubs", "kits"]
    assert metadata["workbook"]["choices"]["nationality"][0]["value"]
    players = catalog.spreadsheet_tab(
        season="2000-01", tab="players", query="Ada", offset=0, limit=20,
    )["table"]
    assert players["rows"][0]["cells"]["name"]["pointer"] == "/players/0/name"
    assert players["rows"][0]["cells"]["portrait"]["display"] == "No verified portrait"
    assert players["rows"][0]["cells"]["rating:handling"]["maximum"] == 100
    clubs = catalog.spreadsheet_tab(
        season="2000-01", tab="clubs", query="", offset=0, limit=20,
    )["table"]
    assert clubs["rows"][0]["cells"]["manager"]["kind"] == "select"

    catalog.stage_amendment(
        season="2000-01", manifest_id="season-package.json", json_pointer="/players/0/name",
        replacement="Ada Correct", reason="Correct source spelling", evidence=None,
    )
    amended = catalog.stage_amendment(
        season="2000-01", manifest_id="season-package.json", json_pointer="/players/0/name",
        replacement="Ada Final", reason="Correct source spelling", evidence=None,
    )
    assert len(amended["changes"]) == 1
    assert amended["changes"][0]["expected"] == "Ada Player"
    assert amended["changes"][0]["set"] == "Ada Final"
    # The workbook previews a copy with staged, hash-bound changes applied;
    # the selected source remains immutable until explicit materialisation.
    preview = catalog.spreadsheet_tab(
        season="2000-01", tab="players", query="", offset=0, limit=20,
    )["table"]
    assert preview["rows"][0]["cells"]["name"]["value"] == "Ada Final"
    assert json.loads((seasons_root / "2000-01" / "season-package.json").read_text(encoding="utf-8"))[
        "players"
    ][0]["name"] == "Ada Player"


def test_runtime_recipe_discovery_requires_the_matching_local_game_tree(tmp_path: Path) -> None:
    ingress = tmp_path / "ingress"
    runtime = tmp_path / "runtime"
    _write(
        ingress / "2000-01-worldwide-source-backed-r1" / "season-package.source-writable.json",
        _package(),
    )
    (runtime / "2000-01" / "worldwide-source-backed-r1" / "game").mkdir(parents=True)

    discovered, states = discover_runtime_recipe_presets(ingress, runtime)

    assert discovered["2000-01"][0].kind == "runtime-recipe"
    assert states["2000-01"]["playable"] is True
