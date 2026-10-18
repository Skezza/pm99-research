#!/usr/bin/env python3
"""Validate hash-locked, data-only PM99 historical season recipes.

A season recipe describes the retained source inputs, base-owned carrier maps,
source adapters and small editorial overlays that will eventually seed a
Season Package V2.  It is deliberately *before* the package/compiler boundary:
it neither opens a PM99 game tree nor writes database, portrait, kit or
calendar output.

The recipe is canonical JSON.  Every named input is relative to the recipe
file, content-addressed and optionally required to be canonical JSON itself.
This makes it possible to rerun source normalisation with one corrected
overlay without treating an old built game folder as source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "pm99-season-recipe-v1"
SCHEMA_PATH = ROOT / "schemas" / f"{SCHEMA}.schema.json"
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SEASON_LABEL_RE = re.compile(r"^(?:19[0-9]{2}|20(?:0[0-9]|1[0-9]|2[0-5]))/[0-9]{2}$")
RATING_PRECEDENCE = [
    "reviewed-editorial",
    "nearby-season-editorial",
    "fifa-nearest-edition",
    "deterministic-context",
    "preserve-native",
]
SQUAD_SNAPSHOT_POLICY = "at-club-on-first-league-fixture-date-exclude-later-arrivals"
FORMATION_POLICY = "published-opening-xi-formation-else-deterministic-position-inference"
MANAGER_POLICY = "target-season-opening-date-source-required-no-native-fallback"
CLUB_NAME_POLICY = "preserve-native-name-for-continuing-club-reassign-only-exited-carrier"
KIT_FALLBACK_POLICY = "preserve-native-only-for-exited-carrier"
OPENING_FALLBACK_POLICY = "preserve-native-only-for-exited-carrier"
SECONDARY_FACT_POLICY = "source-where-available-else-explicit-field-fallback"
ARTIFACT_ROLES = {
    "base-descriptor",
    "mode0-carrier-map",
    "mode1-carrier-map",
    "squad-capture",
    "identity-facts",
    "rating-snapshot",
    "club-metadata",
    "opening-lineups",
    "manager-catalogue",
    "kit-catalogue",
    "portrait-catalogue",
    "editorial-overlay",
    "other",
}
ADAPTER_ROLE = {
    "squads": "squad-capture",
    "managers": "manager-catalogue",
    "identity_facts": "identity-facts",
    "ratings": "rating-snapshot",
    "club_metadata": "club-metadata",
    "opening_lineups": "opening-lineups",
    "kits": "kit-catalogue",
    "portraits": "portrait-catalogue",
}
OVERLAY_STAGES = {
    "carrier-allocation",
    "identity-resolution",
    "facts",
    "ratings",
    "club-metadata",
    "opening-lineups",
    "kits",
    "portraits",
}


class SeasonRecipeError(ValueError):
    """A recipe is unsafe, incomplete or points to stale retained input."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the only accepted portable JSON encoding."""

    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_canonical_recipe(path: Path, recipe: Mapping[str, Any]) -> None:
    """Validate and write a recipe without introducing machine-local fields."""

    validate_recipe(dict(recipe))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(dict(recipe)))


def read_canonical_recipe(path: Path) -> dict[str, Any]:
    """Load and validate recipe source; local artifact paths are not opened."""

    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SeasonRecipeError(f"cannot read recipe {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise SeasonRecipeError("recipe must be canonically encoded JSON")
    validate_recipe(value)
    return value


def _schema_errors(value: Mapping[str, Any]) -> list[str]:
    """Use the published schema when available, while retaining stdlib support."""

    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return []
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(dict(value)), key=lambda item: list(item.absolute_path))
    ]


def _require_id(value: Any, *, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        errors.append(f"{label} must be a stable lower-case ID")
        return None
    return value


def _require_sha(value: Any, *, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        errors.append(f"{label} must be a lowercase SHA-256")
        return None
    return value


def _safe_relative_path(value: Any, *, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        errors.append(f"{label} must be a non-empty POSIX relative path")
        return None
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts or candidate.as_posix() != value:
        errors.append(f"{label} must be a safe recipe-relative path")
        return None
    return value


def _sorted_unique_ids(value: Any, *, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{label} must be a non-empty list")
        return []
    if value != sorted(value) or len(value) != len(set(value)):
        errors.append(f"{label} must be sorted and unique")
    result: list[str] = []
    for index, item in enumerate(value):
        identity = _require_id(item, label=f"{label}[{index}]", errors=errors)
        if identity is not None:
            result.append(identity)
    return result


def _validate_season(value: Any, *, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("season must be an object")
        return
    if set(value) != {"start_year", "end_year", "label"}:
        errors.append("season must contain only start_year, end_year and label")
        return
    start, end, label = value.get("start_year"), value.get("end_year"), value.get("label")
    if not isinstance(start, int) or isinstance(start, bool) or not 1900 <= start <= 2025:
        errors.append("season.start_year must be in 1900..2025")
    if not isinstance(end, int) or isinstance(end, bool) or not 1901 <= end <= 2026:
        errors.append("season.end_year must be in 1901..2026")
    if isinstance(start, int) and isinstance(end, int) and end != start + 1:
        errors.append("season years must be consecutive")
    expected = f"{start}/{str(end)[-2:]}" if isinstance(start, int) and isinstance(end, int) else None
    if not isinstance(label, str) or not SEASON_LABEL_RE.fullmatch(label) or label != expected:
        errors.append("season.label must match consecutive start_year/end_year")


def _validate_artifacts(recipe: Mapping[str, Any], *, errors: list[str]) -> dict[str, dict[str, Any]]:
    artifacts = recipe.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        errors.append("artifacts must be a non-empty list")
        return {}
    result: dict[str, dict[str, Any]] = {}
    previous: str | None = None
    for index, row in enumerate(artifacts):
        if not isinstance(row, dict) or set(row) != {"id", "role", "relative_path", "sha256", "encoding"}:
            errors.append(f"artifacts[{index}] has unsupported fields")
            continue
        identity = _require_id(row.get("id"), label=f"artifacts[{index}].id", errors=errors)
        if identity is None:
            continue
        if previous is not None and identity <= previous:
            errors.append("artifacts must be ID-sorted and unique")
        previous = identity
        if identity in result:
            errors.append(f"artifacts contains duplicate ID {identity!r}")
            continue
        role = row.get("role")
        if role not in ARTIFACT_ROLES:
            errors.append(f"artifacts[{index}].role is unsupported")
        _safe_relative_path(row.get("relative_path"), label=f"artifacts[{index}].relative_path", errors=errors)
        _require_sha(row.get("sha256"), label=f"artifacts[{index}].sha256", errors=errors)
        if row.get("encoding") not in {"canonical-json", "opaque"}:
            errors.append(f"artifacts[{index}].encoding is unsupported")
        result[identity] = row
    return result


def _require_artifact_role(
    artifacts: Mapping[str, Mapping[str, Any]],
    artifact_id: Any,
    *,
    role: str,
    label: str,
    errors: list[str],
) -> None:
    identity = _require_id(artifact_id, label=label, errors=errors)
    if identity is None:
        return
    artifact = artifacts.get(identity)
    if artifact is None:
        errors.append(f"{label} references missing artifact {identity!r}")
    elif artifact.get("role") != role:
        errors.append(f"{label} must reference a {role!r} artifact")


def _validate_base_and_maps(recipe: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]], *, errors: list[str]) -> set[str]:
    referenced: set[str] = set()
    base = recipe.get("base")
    if not isinstance(base, dict) or set(base) != {"base_id", "descriptor_artifact_id"}:
        errors.append("base must contain only base_id and descriptor_artifact_id")
    else:
        _require_id(base.get("base_id"), label="base.base_id", errors=errors)
        descriptor = base.get("descriptor_artifact_id")
        _require_artifact_role(artifacts, descriptor, role="base-descriptor", label="base.descriptor_artifact_id", errors=errors)
        if isinstance(descriptor, str):
            referenced.add(descriptor)

    maps = recipe.get("carrier_maps")
    if not isinstance(maps, dict) or set(maps) != {"mode0", "mode1"}:
        errors.append("carrier_maps must contain exactly mode0 and mode1")
        return referenced
    for mode, role in (("mode0", "mode0-carrier-map"), ("mode1", "mode1-carrier-map")):
        row = maps.get(mode)
        if not isinstance(row, dict) or set(row) != {"artifact_id", "topology_policy"}:
            errors.append(f"carrier_maps.{mode} has unsupported fields")
            continue
        artifact_id = row.get("artifact_id")
        _require_artifact_role(artifacts, artifact_id, role=role, label=f"carrier_maps.{mode}.artifact_id", errors=errors)
        if isinstance(artifact_id, str):
            referenced.add(artifact_id)
        if row.get("topology_policy") != "existing-carriers-only":
            errors.append(f"carrier_maps.{mode}.topology_policy must preserve existing carriers")
    return referenced


def _validate_adapters(recipe: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]], *, errors: list[str]) -> set[str]:
    referenced: set[str] = set()
    adapters = recipe.get("source_adapters")
    required_lanes = {"squads", "managers", "opening_lineups", "kits"}
    if (
        not isinstance(adapters, dict)
        or not required_lanes.issubset(adapters)
        or set(adapters) - set(ADAPTER_ROLE)
    ):
        errors.append(
            "source_adapters must contain squads, managers, opening_lineups and kits, "
            "and only known source lanes"
        )
        return referenced
    for lane, row in adapters.items():
        if not isinstance(row, dict) or set(row) != {"adapter_id", "artifact_ids"}:
            errors.append(f"source_adapters.{lane} has unsupported fields")
            continue
        _require_id(row.get("adapter_id"), label=f"source_adapters.{lane}.adapter_id", errors=errors)
        for artifact_id in _sorted_unique_ids(row.get("artifact_ids"), label=f"source_adapters.{lane}.artifact_ids", errors=errors):
            _require_artifact_role(
                artifacts,
                artifact_id,
                role=ADAPTER_ROLE[lane],
                label=f"source_adapters.{lane}.artifact_ids",
                errors=errors,
            )
            referenced.add(artifact_id)
    return referenced


def _validate_allocation_and_policies(recipe: Mapping[str, Any], *, errors: list[str]) -> None:
    allocation = recipe.get("allocation")
    if not isinstance(allocation, dict) or set(allocation) != {"mode0", "mode1"}:
        errors.append("allocation must contain exactly mode0 and mode1")
    else:
        for mode in ("mode0", "mode1"):
            row = allocation.get(mode)
            if not isinstance(row, dict) or set(row) != {"selection_policy", "overflow_policy"}:
                errors.append(f"allocation.{mode} has unsupported fields")
                continue
            if row.get("selection_policy") not in {
                "exact-normalised-name-then-editorial-overlay",
                "candidate-only-name-match",
            }:
                errors.append(f"allocation.{mode}.selection_policy is unsupported")
            if row.get("overflow_policy") not in {"fail", "source-prefix-preserve-native-tail"}:
                errors.append(f"allocation.{mode}.overflow_policy is unsupported")
    policies = recipe.get("policies")
    expected_policy_keys = {
        "club_name_policy",
        "formation_policy",
        "kit_fallback",
        "manager_policy",
        "mode1_opening",
        "portrait_fallback",
        "rating_precedence",
        "secondary_fact_policy",
        "squad_snapshot",
    }
    if not isinstance(policies, dict) or set(policies) != expected_policy_keys:
        errors.append("policies has unsupported fields")
        return
    if policies.get("rating_precedence") != RATING_PRECEDENCE:
        errors.append("policies.rating_precedence must use the fixed V2 provenance order")
    if policies.get("portrait_fallback") != "native-no-photo":
        errors.append("policies.portrait_fallback must be native-no-photo")
    if policies.get("secondary_fact_policy") != SECONDARY_FACT_POLICY:
        errors.append(
            "policies.secondary_fact_policy must source secondary facts where available "
            "and log every field fallback"
        )
    if policies.get("squad_snapshot") != SQUAD_SNAPSHOT_POLICY:
        errors.append("policies.squad_snapshot must select the opening-date squad and exclude later arrivals")
    if policies.get("formation_policy") != FORMATION_POLICY:
        errors.append("policies.formation_policy must use a published opening formation or deterministic inference")
    if policies.get("manager_policy") != MANAGER_POLICY:
        errors.append("policies.manager_policy must require the correct sourced opening-date manager")
    if policies.get("club_name_policy") != CLUB_NAME_POLICY:
        errors.append("policies.club_name_policy must preserve continuing native club names")
    if policies.get("kit_fallback") != KIT_FALLBACK_POLICY:
        errors.append("policies.kit_fallback may preserve a native kit only for an exited carrier")
    if policies.get("mode1_opening") != OPENING_FALLBACK_POLICY:
        errors.append("policies.mode1_opening may preserve native opening state only for an exited carrier")


def _validate_overlays(recipe: Mapping[str, Any], artifacts: Mapping[str, Mapping[str, Any]], *, errors: list[str]) -> set[str]:
    referenced: set[str] = set()
    overlays = recipe.get("overlays")
    if not isinstance(overlays, list):
        errors.append("overlays must be a list")
        return referenced
    previous: tuple[str, str] | None = None
    seen_ids: set[str] = set()
    for index, row in enumerate(overlays):
        if not isinstance(row, dict) or set(row) != {"id", "stage", "artifact_id"}:
            errors.append(f"overlays[{index}] has unsupported fields")
            continue
        identity = _require_id(row.get("id"), label=f"overlays[{index}].id", errors=errors)
        stage = row.get("stage")
        if stage not in OVERLAY_STAGES:
            errors.append(f"overlays[{index}].stage is unsupported")
            continue
        if identity is not None:
            key = (str(stage), identity)
            if previous is not None and key <= previous:
                errors.append("overlays must be sorted by stage then ID and unique")
            previous = key
            if identity in seen_ids:
                errors.append(f"overlays contains duplicate ID {identity!r}")
            seen_ids.add(identity)
        artifact_id = row.get("artifact_id")
        _require_artifact_role(
            artifacts, artifact_id, role="editorial-overlay", label=f"overlays[{index}].artifact_id", errors=errors
        )
        if isinstance(artifact_id, str):
            referenced.add(artifact_id)
    return referenced


def validate_recipe(recipe: Mapping[str, Any]) -> None:
    """Validate a source-only recipe and every internal artifact reference."""

    if not isinstance(recipe, Mapping):
        raise SeasonRecipeError("recipe must be an object")
    errors = _schema_errors(recipe)
    expected_keys = {
        "schema_version", "recipe_id", "season", "base", "artifacts", "carrier_maps",
        "source_adapters", "allocation", "policies", "overlays",
    }
    if set(recipe) != expected_keys:
        errors.append(f"recipe keys must exactly equal {sorted(expected_keys)}")
    if recipe.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA!r}")
    _require_id(recipe.get("recipe_id"), label="recipe_id", errors=errors)
    _validate_season(recipe.get("season"), errors=errors)
    artifacts = _validate_artifacts(recipe, errors=errors)
    referenced = _validate_base_and_maps(recipe, artifacts, errors=errors)
    referenced.update(_validate_adapters(recipe, artifacts, errors=errors))
    _validate_allocation_and_policies(recipe, errors=errors)
    referenced.update(_validate_overlays(recipe, artifacts, errors=errors))
    orphaned = sorted(set(artifacts) - referenced)
    if orphaned:
        errors.append(f"artifacts must be referenced by base, carrier map, adapter or overlay: {orphaned}")
    if errors:
        raise SeasonRecipeError("Season recipe validation failed:\n- " + "\n- ".join(errors))


def _resolve_artifact(recipe_path: Path, artifact: Mapping[str, Any]) -> Path:
    relative = str(artifact["relative_path"])
    root = recipe_path.parent.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SeasonRecipeError(f"artifact path escapes recipe directory: {relative}") from exc
    if candidate.is_symlink() or not candidate.is_file():
        raise SeasonRecipeError(f"artifact must be an existing regular file: {relative}")
    return candidate


def verify_recipe_inputs(*, recipe_path: Path, recipe: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Verify every retained input without reading or writing a PM99 tree."""

    recipe_path = recipe_path.expanduser().resolve()
    value = dict(recipe) if recipe is not None else read_canonical_recipe(recipe_path)
    validate_recipe(value)
    verified: list[dict[str, str]] = []
    for artifact in value["artifacts"]:
        path = _resolve_artifact(recipe_path, artifact)
        actual = sha256_file(path)
        if actual != artifact["sha256"]:
            raise SeasonRecipeError(
                f"artifact hash mismatch for {artifact['id']}: expected {artifact['sha256']}, got {actual}"
            )
        if artifact["encoding"] == "canonical-json":
            try:
                payload = json.loads(path.read_bytes().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SeasonRecipeError(f"canonical JSON artifact {artifact['id']} is unreadable") from exc
            if not isinstance(payload, dict) or path.read_bytes() != canonical_json_bytes(payload):
                raise SeasonRecipeError(f"canonical JSON artifact {artifact['id']} is not canonically encoded")
        verified.append({"id": str(artifact["id"]), "sha256": actual})
    return {
        "recipe_id": value["recipe_id"],
        "season": value["season"]["label"],
        "artifact_count": len(verified),
        "verified_artifacts": verified,
    }


def describe_recipe(recipe: Mapping[str, Any]) -> dict[str, Any]:
    """Return deterministic review metadata; this is intentionally not a seed."""

    validate_recipe(recipe)
    artifact_roles = Counter(str(row["role"]) for row in recipe["artifacts"])
    overlay_stages = Counter(str(row["stage"]) for row in recipe["overlays"])
    return {
        "recipe_id": recipe["recipe_id"],
        "season": recipe["season"]["label"],
        "base_id": recipe["base"]["base_id"],
        "artifact_role_counts": dict(sorted(artifact_roles.items())),
        "source_adapter_lanes": sorted(recipe["source_adapters"]),
        "overlay_stage_counts": dict(sorted(overlay_stages.items())),
        "database_output": "not-described-by-season-recipe-v1",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "verify-inputs", "describe"):
        subparser = commands.add_parser(command)
        subparser.add_argument("--recipe", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        recipe = read_canonical_recipe(args.recipe)
        if args.command == "validate":
            result: Mapping[str, Any] = {
                "recipe_id": recipe["recipe_id"],
                "season": recipe["season"]["label"],
                "result": "valid-data-only-recipe",
            }
        elif args.command == "verify-inputs":
            result = verify_recipe_inputs(recipe_path=args.recipe, recipe=recipe)
        else:
            result = describe_recipe(recipe)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except SeasonRecipeError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
