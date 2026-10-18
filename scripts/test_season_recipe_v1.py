"""Focused contract tests for data-only generic season recipes."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_recipe_v1 as recipes  # noqa: E402


def _write(path: Path, value: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(recipes.canonical_json_bytes(value))
    return recipes.sha256_file(path)


def _fixture_recipe(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    files = {
        "base.json": {"schema": "base", "files": []},
        "maps/mode0.json": {"schema": "mode0", "carriers": []},
        "maps/mode1.json": {"schema": "mode1", "carriers": []},
        "sources/kits.json": {"schema": "kits", "clubs": []},
        "sources/lineups.json": {"schema": "lineups", "clubs": []},
        "sources/managers.json": {"schema": "managers", "clubs": []},
        "sources/squads.json": {"schema_version": "pm99-footballsquads-season-capture-v1", "clubs": []},
        "overlays/aliases.json": {"schema": "editorial", "aliases": []},
    }
    hashes = {relative: _write(tmp_path / relative, value) for relative, value in files.items()}
    recipe: dict[str, object] = {
        "schema_version": recipes.SCHEMA,
        "recipe_id": "pm99-2000-01-source-recipe",
        "season": {"start_year": 2000, "end_year": 2001, "label": "2000/01"},
        "base": {"base_id": "pm99-verified-base", "descriptor_artifact_id": "base-descriptor"},
        "artifacts": [
            {"id": "base-descriptor", "role": "base-descriptor", "relative_path": "base.json", "sha256": hashes["base.json"], "encoding": "canonical-json"},
            {"id": "club-aliases", "role": "editorial-overlay", "relative_path": "overlays/aliases.json", "sha256": hashes["overlays/aliases.json"], "encoding": "canonical-json"},
            {"id": "kit-capture", "role": "kit-catalogue", "relative_path": "sources/kits.json", "sha256": hashes["sources/kits.json"], "encoding": "canonical-json"},
            {"id": "lineup-capture", "role": "opening-lineups", "relative_path": "sources/lineups.json", "sha256": hashes["sources/lineups.json"], "encoding": "canonical-json"},
            {"id": "manager-capture", "role": "manager-catalogue", "relative_path": "sources/managers.json", "sha256": hashes["sources/managers.json"], "encoding": "canonical-json"},
            {"id": "mode0-map", "role": "mode0-carrier-map", "relative_path": "maps/mode0.json", "sha256": hashes["maps/mode0.json"], "encoding": "canonical-json"},
            {"id": "mode1-map", "role": "mode1-carrier-map", "relative_path": "maps/mode1.json", "sha256": hashes["maps/mode1.json"], "encoding": "canonical-json"},
            {"id": "squad-capture", "role": "squad-capture", "relative_path": "sources/squads.json", "sha256": hashes["sources/squads.json"], "encoding": "canonical-json"},
        ],
        "carrier_maps": {
            "mode0": {"artifact_id": "mode0-map", "topology_policy": "existing-carriers-only"},
            "mode1": {"artifact_id": "mode1-map", "topology_policy": "existing-carriers-only"},
        },
        "source_adapters": {
            "kits": {"adapter_id": "kit-catalogue-v1", "artifact_ids": ["kit-capture"]},
            "managers": {"adapter_id": "manager-catalogue-v1", "artifact_ids": ["manager-capture"]},
            "opening_lineups": {"adapter_id": "opening-lineups-v1", "artifact_ids": ["lineup-capture"]},
            "squads": {"adapter_id": "footballsquads-season-capture-v1", "artifact_ids": ["squad-capture"]}
        },
        "allocation": {
            "mode0": {"selection_policy": "exact-normalised-name-then-editorial-overlay", "overflow_policy": "fail"},
            "mode1": {"selection_policy": "exact-normalised-name-then-editorial-overlay", "overflow_policy": "source-prefix-preserve-native-tail"},
        },
        "policies": {
            "rating_precedence": list(recipes.RATING_PRECEDENCE),
            "squad_snapshot": recipes.SQUAD_SNAPSHOT_POLICY,
            "formation_policy": recipes.FORMATION_POLICY,
            "manager_policy": recipes.MANAGER_POLICY,
            "club_name_policy": recipes.CLUB_NAME_POLICY,
            "portrait_fallback": "native-no-photo",
            "secondary_fact_policy": recipes.SECONDARY_FACT_POLICY,
            "kit_fallback": recipes.KIT_FALLBACK_POLICY,
            "mode1_opening": recipes.OPENING_FALLBACK_POLICY,
        },
        "overlays": [{"id": "club-aliases", "stage": "carrier-allocation", "artifact_id": "club-aliases"}],
    }
    recipe_path = tmp_path / "season-recipe.json"
    recipes.write_canonical_recipe(recipe_path, recipe)
    return recipe_path, recipe


def test_recipe_validates_and_verifies_only_declared_inputs(tmp_path: Path) -> None:
    recipe_path, recipe = _fixture_recipe(tmp_path)

    loaded = recipes.read_canonical_recipe(recipe_path)
    assert loaded == recipe
    verified = recipes.verify_recipe_inputs(recipe_path=recipe_path)
    assert verified["artifact_count"] == 8
    assert {row["id"] for row in verified["verified_artifacts"]} == {
        "base-descriptor", "mode0-map", "mode1-map", "squad-capture", "club-aliases",
        "kit-capture", "lineup-capture", "manager-capture",
    }
    assert recipes.describe_recipe(loaded)["database_output"] == "not-described-by-season-recipe-v1"


def test_recipe_rejects_adapter_role_mismatch_before_any_input_is_opened(tmp_path: Path) -> None:
    _recipe_path, recipe = _fixture_recipe(tmp_path)
    invalid = copy.deepcopy(recipe)
    invalid["source_adapters"]["squads"]["artifact_ids"] = ["mode0-map"]  # type: ignore[index]

    with pytest.raises(recipes.SeasonRecipeError, match="squad-capture"):
        recipes.validate_recipe(invalid)


def test_recipe_rejects_orphan_artifact_and_unsafe_path(tmp_path: Path) -> None:
    _recipe_path, recipe = _fixture_recipe(tmp_path)
    invalid = copy.deepcopy(recipe)
    invalid["artifacts"].append({  # type: ignore[index]
        "id": "unused", "role": "other", "relative_path": "unused.json", "sha256": "0" * 64, "encoding": "opaque",
    })
    with pytest.raises(recipes.SeasonRecipeError, match="referenced"):
        recipes.validate_recipe(invalid)

    unsafe = copy.deepcopy(recipe)
    unsafe["artifacts"][0]["relative_path"] = "../outside.json"  # type: ignore[index]
    with pytest.raises(recipes.SeasonRecipeError, match="safe"):
        recipes.validate_recipe(unsafe)


def test_input_verification_rejects_stale_and_noncanonical_artifacts(tmp_path: Path) -> None:
    recipe_path, _recipe = _fixture_recipe(tmp_path)
    (tmp_path / "sources/squads.json").write_text('{"clubs": [], "schema_version": "pm99-footballsquads-season-capture-v1"}\n', encoding="utf-8")
    with pytest.raises(recipes.SeasonRecipeError, match="hash mismatch"):
        recipes.verify_recipe_inputs(recipe_path=recipe_path)

    recipe_path, recipe = _fixture_recipe(tmp_path / "second")
    source = tmp_path / "second/sources/squads.json"
    source.write_text('{"clubs": [], "schema_version": "pm99-footballsquads-season-capture-v1"}\n', encoding="utf-8")
    squad_artifact = next(row for row in recipe["artifacts"] if row["id"] == "squad-capture")  # type: ignore[index]
    squad_artifact["sha256"] = recipes.sha256_file(source)
    recipes.write_canonical_recipe(recipe_path, recipe)
    with pytest.raises(recipes.SeasonRecipeError, match="not canonically"):
        recipes.verify_recipe_inputs(recipe_path=recipe_path)


@pytest.mark.parametrize(
    ("key", "invalid", "message"),
    [
        ("squad_snapshot", "whole-season-appearance-list", "opening-date squad"),
        ("formation_policy", "native-formation-fallback", "deterministic inference"),
        ("manager_policy", "preserve-native-manager", "correct sourced opening-date manager"),
        ("club_name_policy", "rename-every-club", "preserve continuing native club names"),
        ("kit_fallback", "preserve-existing-when-unresolved", "only for an exited carrier"),
        ("mode1_opening", "preserve-existing-mode1", "only for an exited carrier"),
        ("secondary_fact_policy", "all-facts-required", "log every field fallback"),
    ],
)
def test_recipe_rejects_relaxed_historical_fallbacks(
    tmp_path: Path, key: str, invalid: str, message: str
) -> None:
    _recipe_path, recipe = _fixture_recipe(tmp_path)
    broken = copy.deepcopy(recipe)
    broken["policies"][key] = invalid  # type: ignore[index]

    with pytest.raises(recipes.SeasonRecipeError, match=message):
        recipes.validate_recipe(broken)


@pytest.mark.parametrize("lane", ["managers", "opening_lineups", "kits"])
def test_recipe_requires_historical_source_lanes(tmp_path: Path, lane: str) -> None:
    _recipe_path, recipe = _fixture_recipe(tmp_path)
    broken = copy.deepcopy(recipe)
    del broken["source_adapters"][lane]  # type: ignore[index]

    with pytest.raises(recipes.SeasonRecipeError, match="squads, managers, opening_lineups and kits"):
        recipes.validate_recipe(broken)
