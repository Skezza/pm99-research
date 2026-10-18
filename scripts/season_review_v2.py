#!/usr/bin/env python3
"""Produce PM99 playtest review queues and apply source-only review overlays.

The output of a PM99 build is deliberately immutable.  A playtester can still
find a bad rating, name, line-up or portrait: record that correction in a
small canonical overlay, then compile a *new* game materialisation from the
derived season package.  This module neither opens nor changes an FDI/PKF/EXE
or a previously built game directory.

Portraits fail open.  A failed or rejected image becomes PM99 native no-photo
and is emitted in a machine-readable queue with the player, club and reason.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2


PORTRAIT_RESULTS_SCHEMA = "pm99-portrait-stage-results-v1"
PORTRAIT_QUEUE_SCHEMA = "pm99-portrait-review-queue-v1"
OVERRIDES_SCHEMA = "pm99-season-review-overrides-v1"
APPLICATION_RECEIPT_SCHEMA = "pm99-season-review-application-receipt-v1"
OVERRIDES_SCHEMA_PATH = ROOT / "schemas" / "pm99-season-review-overrides-v1.schema.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

RATING_KEYS = {
    "quality", "speed", "stamina", "aggression", "passing", "tackling",
    "heading", "shooting", "dribbling", "handling",
}
ALLOWED_DATA_PATHS = {
    "player": {
        "name",
        "facts.birth_date", "facts.nationality", "facts.height_cm", "facts.weight_kg",
        "facts.primary_position", "facts.fine_roles", "facts.shirt_number",
        *(f"ratings.values.{key}" for key in RATING_KEYS),
    },
    "manager": {"name"},
    "club": {
        "name", "full_name", "ground_name", "seated_capacity", "starting_finance",
        "division", "opening.formation", "opening.tactics_positions",
        "opening.starting_xi_player_ids", "opening.substitute_player_ids",
    },
}


class SeasonReviewError(ValueError):
    """A review input is malformed, unsafe, or targets the wrong package."""


def canonical_json_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_canonical_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _read_canonical_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SeasonReviewError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise SeasonReviewError(f"{label} must be canonically encoded JSON")
    return value


def _package_hash(package: dict[str, Any]) -> str:
    return sha256_bytes(canonical_json_bytes(package))


def _require_sha(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise SeasonReviewError(f"{label} must be a lowercase SHA-256")
    return value


def _require_nonempty_string(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SeasonReviewError(f"{label} must be a non-empty string")
    return value


def _ids_sorted_unique(rows: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise SeasonReviewError(f"{label} must be a list")
    result: list[dict[str, Any]] = []
    identities: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SeasonReviewError(f"{label}[{index}] must be an object")
        identity = row.get("id")
        if not isinstance(identity, str) or not package_v2.ID_RE.fullmatch(identity):
            raise SeasonReviewError(f"{label}[{index}].id is not a stable identifier")
        identities.append(identity)
        result.append(row)
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise SeasonReviewError(f"{label} ids must be sorted and unique")
    return result


def _schema_errors(value: dict[str, Any]) -> list[str]:
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return []
    schema = json.loads(OVERRIDES_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.absolute_path))
    return [f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}" for error in errors]


def _proof_ref(value: Any, *, label: str) -> None:
    if not isinstance(value, dict) or set(value) != {"grade", "artifact_id"}:
        raise SeasonReviewError(f"{label} must have exactly grade and artifact_id")
    if value["grade"] not in package_v2.PROOF_GRADES:
        raise SeasonReviewError(f"{label}.grade is not a known proof grade")
    if not isinstance(value["artifact_id"], str) or not package_v2.ID_RE.fullmatch(value["artifact_id"]):
        raise SeasonReviewError(f"{label}.artifact_id is not a stable identifier")


def _get_path(value: dict[str, Any], dotted_path: str) -> Any:
    current: Any = value
    for part in dotted_path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise SeasonReviewError(f"target does not contain editable field {dotted_path!r}")
        current = current[part]
    return current


def _set_path(value: dict[str, Any], dotted_path: str, replacement: Any) -> None:
    parts = dotted_path.split(".")
    current: Any = value
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            raise SeasonReviewError(f"target does not contain editable field {dotted_path!r}")
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        raise SeasonReviewError(f"target does not contain editable field {dotted_path!r}")
    current[parts[-1]] = copy.deepcopy(replacement)


def _is_rating_path(path: str) -> bool:
    return path.startswith("ratings.values.")


def validate_overrides(overrides: dict[str, Any]) -> None:
    """Validate a narrow source overlay before it is permitted to touch a package."""
    errors = _schema_errors(overrides)
    package_v2._check_portable_strings(overrides, errors)  # canonical portable-string contract
    if overrides.get("schema_version") != OVERRIDES_SCHEMA:
        errors.append(f"schema_version must be {OVERRIDES_SCHEMA!r}")
    if not isinstance(overrides.get("override_id"), str) or not package_v2.ID_RE.fullmatch(overrides["override_id"]):
        errors.append("override_id must be a stable identifier")
    if not isinstance(overrides.get("base_package_canonical_sha256"), str) or not SHA256_RE.fullmatch(overrides["base_package_canonical_sha256"]):
        errors.append("base_package_canonical_sha256 must be a lowercase SHA-256")
    try:
        _ids_sorted_unique(overrides.get("artifacts"), label="artifacts")
        _ids_sorted_unique(overrides.get("sources"), label="sources")
        _ids_sorted_unique(overrides.get("proofs"), label="proofs")
    except SeasonReviewError as exc:
        errors.append(str(exc))

    data_rows = overrides.get("data_patches")
    if not isinstance(data_rows, list):
        errors.append("data_patches must be a list")
        data_rows = []
    portrait_rows = overrides.get("portrait_patches")
    if not isinstance(portrait_rows, list):
        errors.append("portrait_patches must be a list")
        portrait_rows = []
    patch_ids: list[str] = []
    touched_paths: set[tuple[str, str, str]] = set()
    for index, row in enumerate(data_rows):
        if not isinstance(row, dict):
            errors.append(f"data_patches[{index}] must be an object")
            continue
        identity = row.get("id")
        if not isinstance(identity, str) or not package_v2.ID_RE.fullmatch(identity):
            errors.append(f"data_patches[{index}].id is invalid")
        else:
            patch_ids.append(identity)
        target = row.get("target")
        if not isinstance(target, dict):
            errors.append(f"data_patches[{index}].target must be an object")
            continue
        entity, target_id = target.get("entity"), target.get("id")
        if entity not in ALLOWED_DATA_PATHS:
            errors.append(f"data_patches[{index}].target.entity is not editable")
            continue
        if not isinstance(target_id, str) or not package_v2.ID_RE.fullmatch(target_id):
            errors.append(f"data_patches[{index}].target.id is invalid")
        expected, replacement = row.get("expected"), row.get("set")
        if not isinstance(expected, dict) or not isinstance(replacement, dict) or not expected:
            errors.append(f"data_patches[{index}] needs non-empty expected and set objects")
            continue
        if set(expected) != set(replacement):
            errors.append(f"data_patches[{index}] expected and set must name the same fields")
        for path in replacement:
            if path not in ALLOWED_DATA_PATHS[entity]:
                errors.append(f"data_patches[{index}] cannot write {entity}.{path}")
                continue
            key = (str(entity), str(target_id), path)
            if key in touched_paths:
                errors.append(f"data_patches[{index}] duplicates target field {entity}.{target_id}.{path}")
            touched_paths.add(key)
        has_ratings = any(_is_rating_path(path) for path in replacement)
        provenance = row.get("rating_provenance")
        if has_ratings and not isinstance(provenance, dict):
            errors.append(f"data_patches[{index}] changing ratings requires rating_provenance")
        if not has_ratings and provenance is not None:
            errors.append(f"data_patches[{index}] has rating_provenance without a rating change")
        try:
            _require_nonempty_string(row.get("reason"), label=f"data_patches[{index}].reason")
            _proof_ref(row.get("proof"), label=f"data_patches[{index}].proof")
        except SeasonReviewError as exc:
            errors.append(str(exc))
    if patch_ids != sorted(patch_ids) or len(patch_ids) != len(set(patch_ids)):
        errors.append("data_patches ids must be sorted and unique")

    portrait_ids: list[str] = []
    portrait_players: set[str] = set()
    for index, row in enumerate(portrait_rows):
        if not isinstance(row, dict):
            errors.append(f"portrait_patches[{index}] must be an object")
            continue
        identity = row.get("id")
        player_id = row.get("player_id")
        if not isinstance(identity, str) or not package_v2.ID_RE.fullmatch(identity):
            errors.append(f"portrait_patches[{index}].id is invalid")
        else:
            portrait_ids.append(identity)
        if not isinstance(player_id, str) or not package_v2.ID_RE.fullmatch(player_id):
            errors.append(f"portrait_patches[{index}].player_id is invalid")
        elif player_id in portrait_players:
            errors.append(f"portrait_patches[{index}] duplicates player {player_id}")
        else:
            portrait_players.add(player_id)
        action = row.get("action")
        if action not in {"set-native-no-photo", "set-applied"}:
            errors.append(f"portrait_patches[{index}].action is invalid")
        if row.get("expected_status") not in {"applied", "native-no-photo", "unresolved"}:
            errors.append(f"portrait_patches[{index}].expected_status is invalid")
        try:
            _require_nonempty_string(row.get("reason"), label=f"portrait_patches[{index}].reason")
            _proof_ref(row.get("proof"), label=f"portrait_patches[{index}].proof")
        except SeasonReviewError as exc:
            errors.append(str(exc))
        portrait = row.get("portrait")
        if action == "set-applied":
            if not isinstance(portrait, dict):
                errors.append(f"portrait_patches[{index}] set-applied requires a portrait declaration")
            elif portrait.get("proof") != row.get("proof"):
                errors.append(f"portrait_patches[{index}] portrait proof must equal patch proof")
        elif portrait is not None:
            errors.append(f"portrait_patches[{index}] set-native-no-photo must not carry portrait bytes")
    if portrait_ids != sorted(portrait_ids) or len(portrait_ids) != len(set(portrait_ids)):
        errors.append("portrait_patches ids must be sorted and unique")
    if errors:
        raise SeasonReviewError("Season review override validation failed:\n- " + "\n- ".join(errors))


def read_overrides(path: Path) -> dict[str, Any]:
    value = _read_canonical_object(path, label="review overrides")
    validate_overrides(value)
    return value


def _load_package(path: Path) -> dict[str, Any]:
    package = package_v2.read_canonical_package(path)
    package_v2.validate_package(package)
    return package


def _build_indexes(package: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    players = {row["id"]: row for row in package["players"]}
    clubs = {row["id"]: row for row in package["clubs"]}
    portraits = {row["player_id"]: row for row in package["assets"]["portraits"]}
    return players, clubs, portraits


def portrait_results_from_legacy_face_receipt(package: dict[str, Any], receipt_path: Path) -> dict[str, Any]:
    """Normalise an old face-stage receipt into portable, per-player outcomes."""
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SeasonReviewError(f"cannot read face receipt: {receipt_path}: {exc}") from exc
    if not isinstance(receipt, dict) or not isinstance(receipt.get("rows"), list):
        raise SeasonReviewError("face receipt must contain a rows list")
    players, _, _ = _build_indexes(package)
    by_carrier = {player["carrier_id"]: player["id"] for player in players.values()}
    result_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in receipt["rows"]:
        if not isinstance(row, dict) or not isinstance(row.get("record_id"), int):
            continue
        player_id = by_carrier.get(row["record_id"])
        if player_id is None or player_id in seen:
            continue
        seen.add(player_id)
        status = row.get("status")
        if status == "applied":
            outcome = {"player_id": player_id, "resulting_state": "applied", "reason_code": "applied", "reason": "approved portrait applied"}
        else:
            reason = row.get("no_verified_portrait_reason")
            if not isinstance(reason, str) or not reason.strip():
                reason = f"face stage returned {status!r}; native no-photo used"
            reason_code = "face-stage-no-photo"
            if isinstance(status, str) and status.startswith("unresolved-"):
                reason_code = f"face-stage-{status[len('unresolved-') :]}"
            outcome = {"player_id": player_id, "resulting_state": "native-no-photo", "reason_code": reason_code, "reason": reason}
        result_rows.append(outcome)
    for player_id in players:
        if player_id not in seen:
            result_rows.append({
                "player_id": player_id,
                "resulting_state": "native-no-photo",
                "reason_code": "face-stage-missing-player",
                "reason": "face stage did not emit a result; native no-photo required",
            })
    result_rows.sort(key=lambda row: row["player_id"])
    return {
        "schema_version": PORTRAIT_RESULTS_SCHEMA,
        "package_canonical_sha256": _package_hash(package),
        "results": result_rows,
    }


def portrait_results_from_application_receipt(
    package: dict[str, Any], receipt_path: Path
) -> dict[str, Any]:
    """Normalise a carrier-keyed portrait application receipt.

    Older asset stages selected only the rows they attempted. Any package
    player absent from the receipt is made explicitly no-photo; omission must
    never preserve an unrelated carrier portrait by accident.
    """
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SeasonReviewError(
            f"cannot read portrait application receipt: {receipt_path}: {exc}"
        ) from exc
    operations = receipt.get("operations") if isinstance(receipt, dict) else None
    if not isinstance(operations, list):
        raise SeasonReviewError("portrait application receipt must contain an operations list")
    by_carrier = {row["carrier_id"]: row["id"] for row in package["players"]}
    outcomes: dict[str, dict[str, str]] = {}
    for index, operation in enumerate(operations):
        if not isinstance(operation, dict):
            raise SeasonReviewError(f"portrait operation {index} must be an object")
        carrier_id = operation.get("player_carrier_id")
        player_id = by_carrier.get(carrier_id)
        if player_id is None:
            continue
        if player_id in outcomes:
            raise SeasonReviewError(f"portrait application receipt duplicates carrier {carrier_id}")
        state = operation.get("resulting_state")
        if state in {"applied", "preserved-native-portrait"}:
            resulting_state = "applied"
        elif state == "native-no-photo":
            resulting_state = "native-no-photo"
        else:
            raise SeasonReviewError(
                f"portrait operation {index} has unknown resulting_state {state!r}"
            )
        candidate = str(operation.get("candidate_status") or "application-receipt")
        outcomes[player_id] = {
            "player_id": player_id,
            "resulting_state": resulting_state,
            "reason_code": candidate,
            "reason": (
                "approved portrait retained or applied"
                if resulting_state == "applied"
                else "no identity-safe portrait was applied; PM99 native no-photo is required"
            ),
        }
    for player in package["players"]:
        outcomes.setdefault(
            player["id"],
            {
                "player_id": player["id"],
                "resulting_state": "native-no-photo",
                "reason_code": "not-selected-by-legacy-portrait-stage",
                "reason": "legacy stage did not cover this player; fail-open policy requires PM99 native no-photo",
            },
        )
    result = {
        "schema_version": PORTRAIT_RESULTS_SCHEMA,
        "package_canonical_sha256": _package_hash(package),
        "results": sorted(outcomes.values(), key=lambda row: row["player_id"]),
    }
    validate_portrait_results(result, package)
    return result


def validate_portrait_results(value: dict[str, Any], package: dict[str, Any]) -> None:
    if set(value) != {"schema_version", "package_canonical_sha256", "results"}:
        raise SeasonReviewError("portrait stage results have invalid keys")
    if value.get("schema_version") != PORTRAIT_RESULTS_SCHEMA:
        raise SeasonReviewError(f"portrait stage results must use {PORTRAIT_RESULTS_SCHEMA}")
    if value.get("package_canonical_sha256") != _package_hash(package):
        raise SeasonReviewError("portrait stage results target a different season package")
    rows = value.get("results")
    if not isinstance(rows, list):
        raise SeasonReviewError("portrait stage results must contain a results list")
    player_ids = {row["id"] for row in package["players"]}
    observed: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"player_id", "resulting_state", "reason_code", "reason"}:
            raise SeasonReviewError(f"portrait stage result {index} has invalid keys")
        player_id = row["player_id"]
        if not isinstance(player_id, str) or player_id not in player_ids:
            raise SeasonReviewError(f"portrait stage result {index} names an unknown player")
        if row["resulting_state"] not in {"applied", "native-no-photo"}:
            raise SeasonReviewError(f"portrait stage result {index} has invalid resulting_state")
        _require_nonempty_string(row["reason_code"], label=f"portrait stage result {index}.reason_code")
        _require_nonempty_string(row["reason"], label=f"portrait stage result {index}.reason")
        observed.append(player_id)
    if observed != sorted(observed) or len(observed) != len(set(observed)) or set(observed) != player_ids:
        raise SeasonReviewError("portrait stage results must cover every player exactly once, sorted by player_id")


def read_portrait_results(path: Path, package: dict[str, Any]) -> dict[str, Any]:
    value = _read_canonical_object(path, label="portrait stage results")
    validate_portrait_results(value, package)
    return value


def build_portrait_review_queue(package: dict[str, Any], portrait_results: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make the small, human-reviewable list of players left without a photo."""
    players, clubs, portraits = _build_indexes(package)
    results = {row["player_id"]: row for row in portrait_results["results"]} if portrait_results else {}
    entries: list[dict[str, Any]] = []
    for player_id, player in sorted(players.items()):
        declaration = portraits[player_id]
        stage = results.get(player_id)
        declared_state = declaration["status"]
        if stage is not None:
            resulting_state = stage["resulting_state"]
            reason_code, reason = stage["reason_code"], stage["reason"]
        elif declared_state == "applied":
            resulting_state, reason_code, reason = "applied", "declared-applied", "approved portrait declared in the season package"
        elif declared_state == "native-no-photo":
            resulting_state = "native-no-photo"
            reason_code = "declared-native-no-photo"
            reason = declaration.get("review_reason", "native no-photo declared without a recorded reason")
        else:
            resulting_state = "native-no-photo"
            reason_code = "unresolved-package-portrait"
            reason = declaration.get("review_reason", "portrait unresolved in season package; native no-photo required")
        if resulting_state == "applied":
            continue
        club = clubs[player["club_id"]]
        entries.append({
            "player_id": player_id,
            "carrier_id": player["carrier_id"],
            "player_name": player["name"],
            "club_id": club["id"],
            "club_name": club["name"],
            "declared_state": declared_state,
            "resulting_state": resulting_state,
            "pm99_photo_state": "native-no-photo",
            "reason_code": reason_code,
            "reason": reason,
        })
    return {
        "schema_version": PORTRAIT_QUEUE_SCHEMA,
        "package_canonical_sha256": _package_hash(package),
        "entries": entries,
        "summary": {
            "players_total": len(players),
            "approved_portraits": len(players) - len(entries),
            "native_no_photo": len(entries),
        },
    }


def _collection_index(package: dict[str, Any], entity: str) -> dict[str, dict[str, Any]]:
    collections = {"player": "players", "club": "clubs", "manager": "managers"}
    return {row["id"]: row for row in package[collections[entity]]}


def _merge_new_rows(package: dict[str, Any], overrides: dict[str, Any], collection: str) -> None:
    existing = {row["id"] for row in package[collection]}
    incoming = overrides[collection]
    for row in incoming:
        if row["id"] in existing:
            raise SeasonReviewError(f"review override tries to replace existing {collection[:-1]} {row['id']}")
        existing.add(row["id"])
    package[collection].extend(copy.deepcopy(incoming))
    package[collection].sort(key=lambda row: row["id"])


def apply_overrides(package: dict[str, Any], overrides: dict[str, Any], *, derived_package_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply verified corrections to source metadata, never to a release tree."""
    package_v2.validate_package(package)
    validate_overrides(overrides)
    if not package_v2.ID_RE.fullmatch(derived_package_id):
        raise SeasonReviewError("derived_package_id must be a stable identifier")
    base_hash = _package_hash(package)
    if overrides["base_package_canonical_sha256"] != base_hash:
        raise SeasonReviewError("review overrides target a different canonical season package")

    derived = copy.deepcopy(package)
    _merge_new_rows(derived, overrides, "artifacts")
    _merge_new_rows(derived, overrides, "sources")
    _merge_new_rows(derived, overrides, "proofs")

    for patch in overrides["data_patches"]:
        target = patch["target"]
        entity = _collection_index(derived, target["entity"]).get(target["id"])
        if entity is None:
            raise SeasonReviewError(f"data patch {patch['id']} targets unknown {target['entity']} {target['id']}")
        for path, expected in patch["expected"].items():
            actual = _get_path(entity, path)
            if actual != expected:
                raise SeasonReviewError(
                    f"data patch {patch['id']} refuses stale target {target['entity']}.{target['id']}.{path}: "
                    f"expected {expected!r}, found {actual!r}"
                )
        for path, replacement in patch["set"].items():
            _set_path(entity, path, replacement)
        entity["proof"] = copy.deepcopy(patch["proof"])
        if "rating_provenance" in patch:
            entity["ratings"]["provenance"] = copy.deepcopy(patch["rating_provenance"])

    portrait_index = {row["player_id"]: index for index, row in enumerate(derived["assets"]["portraits"])}
    player_ids = {row["id"] for row in derived["players"]}
    for patch in overrides["portrait_patches"]:
        player_id = patch["player_id"]
        if player_id not in player_ids or player_id not in portrait_index:
            raise SeasonReviewError(f"portrait patch {patch['id']} targets unknown player {player_id}")
        current = derived["assets"]["portraits"][portrait_index[player_id]]
        if current["status"] != patch["expected_status"]:
            raise SeasonReviewError(
                f"portrait patch {patch['id']} refuses stale status for {player_id}: "
                f"expected {patch['expected_status']!r}, found {current['status']!r}"
            )
        if patch["action"] == "set-native-no-photo":
            replacement = {
                "player_id": player_id,
                "status": "native-no-photo",
                "review_reason": patch["reason"],
                "proof": copy.deepcopy(patch["proof"]),
            }
        else:
            replacement = {"player_id": player_id, "status": "applied", **copy.deepcopy(patch["portrait"])}
        derived["assets"]["portraits"][portrait_index[player_id]] = replacement
    derived["assets"]["portraits"].sort(key=lambda row: row["player_id"])
    derived["package_id"] = derived_package_id
    package_v2.validate_package(derived)
    receipt = {
        "schema_version": APPLICATION_RECEIPT_SCHEMA,
        "override_id": overrides["override_id"],
        "override_canonical_sha256": _package_hash(overrides),
        "base_package_canonical_sha256": base_hash,
        "derived_package_id": derived_package_id,
        "derived_package_canonical_sha256": _package_hash(derived),
        "data_patch_count": len(overrides["data_patches"]),
        "portrait_patch_count": len(overrides["portrait_patches"]),
    }
    return derived, receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    normalise = commands.add_parser("normalise-face-receipt", help="write canonical per-player portrait outcomes from an older face receipt")
    normalise.add_argument("--package", required=True, type=Path)
    normalise.add_argument("--face-receipt", required=True, type=Path)
    normalise.add_argument("--output", required=True, type=Path)
    application = commands.add_parser(
        "normalise-application-receipt",
        help="normalise a carrier-keyed asset receipt and fail uncovered players open",
    )
    application.add_argument("--package", required=True, type=Path)
    application.add_argument("--application-receipt", required=True, type=Path)
    application.add_argument("--output", required=True, type=Path)
    queue = commands.add_parser("portrait-queue", help="write concise no-photo review queue")
    queue.add_argument("--package", required=True, type=Path)
    input_group = queue.add_mutually_exclusive_group()
    input_group.add_argument("--portrait-results", type=Path)
    input_group.add_argument("--face-receipt", type=Path)
    queue.add_argument("--output", required=True, type=Path)
    apply = commands.add_parser("apply", help="derive a new package from a source-only review overlay")
    apply.add_argument("--package", required=True, type=Path)
    apply.add_argument("--overrides", required=True, type=Path)
    apply.add_argument("--derived-package-id", required=True)
    apply.add_argument("--output", required=True, type=Path)
    apply.add_argument("--receipt", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        package = _load_package(args.package)
        if args.command == "normalise-face-receipt":
            results = portrait_results_from_legacy_face_receipt(package, args.face_receipt)
            validate_portrait_results(results, package)
            write_canonical_json(args.output, results)
            print(json.dumps({"output": str(args.output), "players": len(results["results"])}, sort_keys=True))
        elif args.command == "normalise-application-receipt":
            results = portrait_results_from_application_receipt(package, args.application_receipt)
            write_canonical_json(args.output, results)
            print(json.dumps({"output": str(args.output), "players": len(results["results"])}, sort_keys=True))
        elif args.command == "portrait-queue":
            if args.portrait_results:
                results = read_portrait_results(args.portrait_results, package)
            elif args.face_receipt:
                results = portrait_results_from_legacy_face_receipt(package, args.face_receipt)
            else:
                results = None
            queue = build_portrait_review_queue(package, results)
            write_canonical_json(args.output, queue)
            print(json.dumps({"output": str(args.output), **queue["summary"]}, sort_keys=True))
        else:
            overrides = read_overrides(args.overrides)
            derived, receipt = apply_overrides(package, overrides, derived_package_id=args.derived_package_id)
            package_v2.write_canonical_package(args.output, derived)
            write_canonical_json(args.receipt, receipt)
            print(json.dumps({"output": str(args.output), "receipt": str(args.receipt), "derived_package_canonical_sha256": receipt["derived_package_canonical_sha256"]}, sort_keys=True))
    except (SeasonReviewError, package_v2.PackageValidationError, OSError) as exc:
        print(f"season review error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
