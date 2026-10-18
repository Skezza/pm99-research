#!/usr/bin/env python3
"""Canonical PM99 historical season-package V2 validation and legacy adapter.

This module deliberately contains no PM99 binary reader/writer.  A package is
portable metadata which names content-addressed inputs and output receipts; a
pipeline may consume it only after this validator accepts it.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import unicodedata
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "pm99-season-package-v2"
ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "pm99-season-package-v2.schema.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
ABSOLUTE_PATH_RE = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
# Provider -> identifier syntax.  Mirrors $defs/source-identity in the schema,
# which is the published contract; this keeps malformed identities rejected
# even where the optional jsonschema package is not installed.
SOURCE_IDENTITY_PATTERNS = {"transfermarkt": re.compile(r"^[1-9][0-9]{0,17}$")}
TIMESTAMP_KEY_RE = re.compile(r"(?:^|_)(?:created|generated|published|updated|timestamp)(?:_|$)")
PROOF_GRADES = {
    "source-captured",
    "source-receipt",
    "reviewed-editorial",
    "static-contract",
    "runtime-wine",
    "runtime-native-windows",
    "legacy-migrated",
}


# A workspace validates the same immutable canonical package at several
# boundaries (ingress, workspace binding and prepared-output verification).
# JSON Schema traversal dominates the cost for a world package, whereas its
# result is solely a function of the canonical package bytes.  Keep a small
# process-local cache of those results: all of the bespoke cross-reference and
# strict checks below still run on every call.
_SCHEMA_ERROR_CACHE_MAX_ENTRIES = 32
_SCHEMA_ERROR_CACHE: OrderedDict[str, tuple[str, ...]] = OrderedDict()
_FAST_SCHEMA_VALIDATOR_CACHE: OrderedDict[str, Any] = OrderedDict()


class PackageValidationError(ValueError):
    """A V2 package violates a structural or reproducibility contract."""


def canonical_json_bytes(value: Any) -> bytes:
    """Return the sole on-disk encoding accepted for reproducible packages."""
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_canonical_package(path: Path, package: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(package))


def read_canonical_package(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        decoded = raw.decode("utf-8")
        package = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageValidationError(f"{path}: not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(package, dict):
        raise PackageValidationError(f"{path}: package root must be an object")
    if raw != canonical_json_bytes(package):
        raise PackageValidationError(
            f"{path}: package is not canonically encoded; use write_canonical_package()"
        )
    return package


def _schema_errors(package: dict[str, Any]) -> list[str]:
    """Use the published JSON schema when available, retaining stdlib fallback."""
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return []

    schema_bytes = SCHEMA_PATH.read_bytes()
    package_digest = sha256_bytes(schema_bytes + b'\0' + canonical_json_bytes(package))
    cached = _SCHEMA_ERROR_CACHE.get(package_digest)
    if cached is not None:
        _SCHEMA_ERROR_CACHE.move_to_end(package_digest)
        return list(cached)

    messages: list[str] = []
    # The optional compiled engine validates the same Draft 2020-12 schema.
    # Retain the established Python diagnostics for all rejected documents.
    # No bespoke cross-reference/strict check below is skipped.
    if _fast_schema_valid(schema_bytes, package) is not True:
        schema = json.loads(schema_bytes)
        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(package), key=lambda item: list(item.absolute_path))
        for error in errors:
            location = ".".join(str(part) for part in error.absolute_path) or "<root>"
            messages.append(f"{location}: {error.message}")
    _SCHEMA_ERROR_CACHE[package_digest] = tuple(messages)
    _SCHEMA_ERROR_CACHE.move_to_end(package_digest)
    while len(_SCHEMA_ERROR_CACHE) > _SCHEMA_ERROR_CACHE_MAX_ENTRIES:
        _SCHEMA_ERROR_CACHE.popitem(last=False)
    return messages


def _fast_schema_valid(schema_bytes: bytes, package: dict[str, Any]) -> bool | None:
    """Optional accelerator; absence falls back to the original full validator."""
    try:
        import jsonschema_rs
    except ImportError:
        return None
    digest = sha256_bytes(schema_bytes)
    validator = _FAST_SCHEMA_VALIDATOR_CACHE.get(digest)
    if validator is None:
        schema = json.loads(schema_bytes)
        # This repository's contract has local references only. Never fetch
        # arbitrary remote references as a side effect of this fast path.
        if any(key == '$ref' and isinstance(value, str) and not value.startswith('#')
               for _, value, key in _walk(schema)):
            return None
        validator = jsonschema_rs.Draft202012Validator(schema, validate_formats=False)
        _FAST_SCHEMA_VALIDATOR_CACHE[digest] = validator
        while len(_FAST_SCHEMA_VALIDATOR_CACHE) > 4:
            _FAST_SCHEMA_VALIDATOR_CACHE.popitem(last=False)
    _FAST_SCHEMA_VALIDATOR_CACHE.move_to_end(digest)
    return bool(validator.is_valid(package))


def _walk(
    value: Any,
    location: str = "<root>",
    leaf_key: str | None = None,
) -> Iterable[tuple[str, Any, str | None]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_location = f"{location}.{key}" if location != "<root>" else key
            yield from _walk(child, child_location, key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{location}[{index}]", None)
    else:
        yield location, value, leaf_key


def _check_portable_strings(package: dict[str, Any], errors: list[str]) -> None:
    for location, value, leaf_key in _walk(package):
        if isinstance(value, str):
            if unicodedata.normalize("NFC", value) != value:
                errors.append(f"{location}: strings must be Unicode NFC")
            if ABSOLUTE_PATH_RE.match(value):
                errors.append(f"{location}: absolute filesystem paths are forbidden")
        if leaf_key and TIMESTAMP_KEY_RE.search(leaf_key):
            errors.append(f"{location}: timestamps are forbidden in a reproducible package")


def _index_by_id(items: Any, label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        errors.append(f"{label}: must be a list")
        return {}
    result: dict[str, dict[str, Any]] = {}
    previous: str | None = None
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{label}[{index}]: must be an object")
            continue
        identity = item.get("id")
        if not isinstance(identity, str) or not ID_RE.fullmatch(identity):
            errors.append(f"{label}[{index}].id: invalid stable id")
            continue
        if identity in result:
            errors.append(f"{label}[{index}].id: duplicate {identity!r}")
        if previous is not None and identity < previous:
            errors.append(f"{label}: ids must be sorted lexicographically")
        previous = identity
        result[identity] = item
    return result


def _check_reference(
    identity: Any,
    index: dict[str, Any],
    location: str,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(identity, str) or identity not in index:
        errors.append(f"{location}: unknown {label} {identity!r}")


def _check_proof_ref(
    proof: Any,
    artifact_index: dict[str, Any],
    location: str,
    errors: list[str],
) -> None:
    if not isinstance(proof, dict):
        errors.append(f"{location}: proof must be an object")
        return
    if proof.get("grade") not in PROOF_GRADES:
        errors.append(f"{location}.grade: unknown proof grade")
    _check_reference(proof.get("artifact_id"), artifact_index, f"{location}.artifact_id", "artifact", errors)


def _check_date(value: Any, location: str, errors: list[str]) -> None:
    if isinstance(value, dict) and value.get("policy") == "preserve-existing-mode1":
        return
    if not isinstance(value, str):
        errors.append(f"{location}: must be ISO date")
        return
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{location}: invalid ISO date {value!r}")


def _check_sorted_unique_ints(values: Any, location: str, errors: list[str]) -> None:
    if not isinstance(values, list) or not all(isinstance(value, int) for value in values):
        errors.append(f"{location}: expected integer list")
        return
    if values != sorted(values):
        errors.append(f"{location}: values must be sorted")
    if len(values) != len(set(values)):
        errors.append(f"{location}: values must be unique")


def _person_candidate_key(player: dict[str, Any]) -> tuple[str, str] | None:
    """Return a deliberately conservative same-person candidate key.

    A strict season source represents one instant in time, so two player rows
    with the same full source name and DOB must be reconciled
    before release.  This is an audit guard, not an assertion that the rows
    are definitely the same human.
    """
    # The native display field can require a source-derived abbreviation when
    # its carrier window is small.  Identity reconciliation must continue to
    # use the exact dated source name, not that lossy display alias.
    name = player.get("source_name") or player.get("name")
    facts = player.get("facts")
    if not isinstance(name, str) or not isinstance(facts, dict):
        return None
    # Citizenship can be missing, dual or wrong. It must not hide two copies.
    birth_date = facts.get("birth_date")
    if not isinstance(birth_date, str):
        return None
    normalised = unicodedata.normalize("NFKD", name)
    normalised = "".join(char.casefold() for char in normalised if char.isalnum())
    return (normalised, birth_date)


def validate_package(package: dict[str, Any], *, strict: bool = False) -> None:
    """Validate V2 schema, cross-links, canonical ordering, and safe provenance."""
    errors = _schema_errors(package)
    _check_portable_strings(package, errors)

    if package.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    package_id = package.get("package_id")
    if not isinstance(package_id, str) or not ID_RE.fullmatch(package_id):
        errors.append("package_id: invalid stable id")

    season = package.get("season")
    if isinstance(season, dict):
        start_year, end_year, label = season.get("start_year"), season.get("end_year"), season.get("label")
        if not isinstance(start_year, int) or not 1900 <= start_year <= 2025:
            errors.append("season.start_year must be 1900..2025")
        if not isinstance(end_year, int) or (isinstance(start_year, int) and end_year != start_year + 1):
            errors.append("season.end_year must equal start_year + 1")
        if isinstance(start_year, int) and label != f"{start_year}/{str(start_year + 1)[-2:]}":
            errors.append("season.label must match start_year/end_year")
    else:
        errors.append("season must be an object")

    artifact_index = _index_by_id(package.get("artifacts"), "artifacts", errors)
    for identity, artifact in artifact_index.items():
        digest = artifact.get("sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            errors.append(f"artifacts[{identity}].sha256 must be lowercase SHA-256")
        relative_path = artifact.get("relative_path")
        if relative_path is not None and (
            not isinstance(relative_path, str)
            or ABSOLUTE_PATH_RE.match(relative_path)
            or ".." in Path(relative_path).parts
        ):
            errors.append(f"artifacts[{identity}].relative_path must be a safe relative path")

    source_index = _index_by_id(package.get("sources"), "sources", errors)
    for identity, source in source_index.items():
        _check_reference(
            source.get("evidence_artifact_id"), artifact_index,
            f"sources[{identity}].evidence_artifact_id", "artifact", errors,
        )
        if source.get("proof_grade") not in PROOF_GRADES:
            errors.append(f"sources[{identity}].proof_grade: unknown proof grade")

    proof_index = _index_by_id(package.get("proofs"), "proofs", errors)
    for identity, proof in proof_index.items():
        if proof.get("grade") not in PROOF_GRADES:
            errors.append(f"proofs[{identity}].grade: unknown proof grade")
        _check_reference(proof.get("artifact_id"), artifact_index, f"proofs[{identity}].artifact_id", "artifact", errors)

    manager_index = _index_by_id(package.get("managers"), "managers", errors)
    manager_carriers: set[int] = set()
    manager_people: set[str] = set()
    for identity, manager in manager_index.items():
        carrier = manager.get("carrier_id")
        if carrier in manager_carriers:
            errors.append(f"managers[{identity}].carrier_id: duplicate carrier {carrier}")
        if isinstance(carrier, int):
            manager_carriers.add(carrier)
        native_names = manager.get("native_names")
        if native_names is not None:
            if manager.get("policy") == "preserve-existing-mode1":
                errors.append(f"managers[{identity}].native_names: a whole-record fallback cannot declare a name write")
            if not isinstance(native_names, dict) or set(native_names) != {"surname", "display_name"}:
                errors.append(f"managers[{identity}].native_names: requires explicit short and display names")
            else:
                for field, value in native_names.items():
                    try:
                        if not isinstance(value, str) or not value.strip() or value != value.strip() or any(not c.isprintable() for c in value):
                            raise ValueError("empty, padded or control text")
                        if len(value.encode("cp1252")) > 255:
                            raise ValueError("more than 255 bytes")
                    except (ValueError, UnicodeEncodeError) as exc:
                        errors.append(f"managers[{identity}].native_names.{field}: invalid CP1252 name ({exc})")
                    if isinstance(value, str) and isinstance(manager.get('name'), str):
                        def tokens(text):
                            transliteration = str.maketrans({'Ł': 'L', 'ł': 'l', 'Đ': 'D', 'đ': 'd',
                                'Ø': 'O', 'ø': 'o', 'Þ': 'Th', 'þ': 'th', 'Æ': 'AE', 'æ': 'ae', 'Ð': 'D', 'ð': 'd'})
                            text = unicodedata.normalize('NFKD', text.translate(transliteration)).casefold()
                            return [''.join(c for c in word if c.isalnum()) for word in text.split()
                                    if any(c.isalnum() for c in word)]
                        source_tokens = iter(tokens(manager['name']))
                        alias_tokens = tokens(value)
                        if not alias_tokens or not all(any(source == token for source in source_tokens) for token in alias_tokens):
                            errors.append(f"managers[{identity}].native_names.{field}: alias is not derived from the current canonical name; refresh it after a name edit")
        person_id = manager.get("person_id")
        if person_id is not None:
            if not isinstance(person_id, str) or not ID_RE.fullmatch(person_id):
                errors.append(f"managers[{identity}].person_id: invalid stable person ID")
            elif person_id in manager_people:
                errors.append(f"managers[{identity}].person_id: duplicate person {person_id}")
            else:
                manager_people.add(person_id)
        _check_proof_ref(manager.get("proof"), artifact_index, f"managers[{identity}].proof", errors)
        if strict and manager.get("person_id") is None and manager.get("policy") != "preserve-existing-mode1":
            errors.append(f"managers[{identity}].person_id: strict native packages require a reconciled person ID")

    club_index = _index_by_id(package.get("clubs"), "clubs", errors)
    club_carriers: set[int] = set()
    club_identities: set[str] = set()
    for identity, club in club_index.items():
        carrier = club.get("carrier_id")
        if carrier in club_carriers:
            errors.append(f"clubs[{identity}].carrier_id: duplicate carrier {carrier}")
        if isinstance(carrier, int):
            club_carriers.add(carrier)
        identity_id = club.get("identity_id")
        if identity_id is not None:
            if not isinstance(identity_id, str) or not ID_RE.fullmatch(identity_id):
                errors.append(f"clubs[{identity}].identity_id: invalid stable club ID")
            elif identity_id in club_identities:
                errors.append(f"clubs[{identity}].identity_id: duplicate identity {identity_id}")
            else:
                club_identities.add(identity_id)
        _check_reference(club.get("manager_id"), manager_index, f"clubs[{identity}].manager_id", "manager", errors)
        _check_proof_ref(club.get("proof"), artifact_index, f"clubs[{identity}].proof", errors)
        for field, policy in (("ground_name", "ground_policy"), ("seated_capacity", "capacity_policy")):
            if club.get(policy) == "preserve-existing-mode1" and field in club:
                errors.append(f"clubs[{identity}].{field}: preserve-existing-mode1 must omit the writable value")
        if strict and club.get("identity_id") is None:
            errors.append(f"clubs[{identity}].identity_id: strict native packages require a reconciled club ID")

    player_index = _index_by_id(package.get("players"), "players", errors)
    player_carriers: set[int] = set()
    player_people: set[str] = set()
    player_candidates: dict[tuple[str, str], list[str]] = {}
    player_source_identities: dict[tuple[str, str], list[str]] = {}
    for identity, player in player_index.items():
        carrier = player.get("carrier_id")
        if carrier in player_carriers:
            errors.append(f"players[{identity}].carrier_id: duplicate carrier {carrier}")
        if isinstance(carrier, int):
            player_carriers.add(carrier)
        append_from = player.get("append_from_carrier_id")
        if append_from is not None and (not isinstance(append_from, int) or append_from < 1):
            errors.append(f"players[{identity}].append_from_carrier_id: must be a positive carrier ID")
        if append_from is not None and append_from == carrier:
            errors.append(f"players[{identity}].append_from_carrier_id: must differ from carrier_id")
        recycle_from = player.get("recycle_from_mode1_carrier_id")
        if recycle_from is not None and (not isinstance(recycle_from, int) or recycle_from < 1):
            errors.append(f"players[{identity}].recycle_from_mode1_carrier_id: must be a positive carrier ID")
        if recycle_from is not None and recycle_from == carrier:
            errors.append(
                f"players[{identity}].recycle_from_mode1_carrier_id: must differ from carrier_id"
            )
        if recycle_from is not None and append_from is not None:
            errors.append(
                f"players[{identity}]: append_from_carrier_id and recycle_from_mode1_carrier_id are exclusive"
            )
        clone_carrier = player.get("mode0_clone_carrier_id")
        if clone_carrier is not None and (not isinstance(clone_carrier, int) or clone_carrier < 1):
            errors.append(f"players[{identity}].mode0_clone_carrier_id: must be a positive carrier ID")
        if clone_carrier is not None and recycle_from is None:
            errors.append(
                f"players[{identity}].mode0_clone_carrier_id: requires recycle_from_mode1_carrier_id"
            )
        if clone_carrier is not None and clone_carrier in player_carriers:
            errors.append(
                f"players[{identity}].mode0_clone_carrier_id: must not collide with a declared player carrier"
            )
        person_id = player.get("person_id")
        if person_id is not None:
            if not isinstance(person_id, str) or not ID_RE.fullmatch(person_id):
                errors.append(f"players[{identity}].person_id: invalid stable person ID")
            elif person_id in player_people:
                errors.append(f"players[{identity}].person_id: duplicate person {person_id}")
            else:
                player_people.add(person_id)
        _check_reference(player.get("club_id"), club_index, f"players[{identity}].club_id", "club", errors)
        _check_proof_ref(player.get("proof"), artifact_index, f"players[{identity}].proof", errors)
        if strict and player.get("person_id") is None:
            errors.append(f"players[{identity}].person_id: strict native packages require a reconciled person ID")
        candidate_key = _person_candidate_key(player)
        if candidate_key is not None:
            player_candidates.setdefault(candidate_key, []).append(identity)
        if "source_identity" in player:
            source_identity = player["source_identity"]
            pattern = (
                SOURCE_IDENTITY_PATTERNS.get(source_identity.get("provider"))
                if isinstance(source_identity, dict) and isinstance(source_identity.get("provider"), str)
                else None
            )
            if (
                pattern is None or set(source_identity) != {"provider", "player_id"}
                or not isinstance(source_identity["player_id"], str)
                or pattern.fullmatch(source_identity["player_id"]) is None
            ):
                errors.append(f"players[{identity}].source_identity: malformed provider player identity")
            else:
                player_source_identities.setdefault(
                    (source_identity["provider"], source_identity["player_id"]), []
                ).append(identity)
        facts = player.get("facts")
        if isinstance(facts, dict):
            _check_date(facts.get("birth_date"), f"players[{identity}].facts.birth_date", errors)
        fallback_rows = player.get("fact_fallbacks", [])
        if isinstance(fallback_rows, list):
            fallback_fields: list[str] = []
            for fallback_index, fallback in enumerate(fallback_rows):
                if not isinstance(fallback, dict):
                    continue
                location = f"players[{identity}].fact_fallbacks[{fallback_index}]"
                field = fallback.get("field")
                if isinstance(field, str):
                    fallback_fields.append(field)
                    if isinstance(facts, dict) and fallback.get("value") != facts.get(field):
                        errors.append(f"{location}.value: must equal facts.{field}")
                _check_proof_ref(fallback.get("proof"), artifact_index, f"{location}.proof", errors)
            if fallback_fields != sorted(fallback_fields) or len(fallback_fields) != len(set(fallback_fields)):
                errors.append(f"players[{identity}].fact_fallbacks: must be field-sorted and unique")
        ratings = player.get("ratings")
        if isinstance(ratings, dict):
            provenance = ratings.get("provenance")
            if isinstance(provenance, dict):
                for source_id in provenance.get("source_ids", []):
                    _check_reference(source_id, source_index, f"players[{identity}].ratings.provenance.source_ids", "source", errors)

    if strict:
        for (provider, provider_player_id), identities in sorted(player_source_identities.items()):
            if len(identities) > 1:
                errors.append(
                    "strict validation rejects repeated provider player identity "
                    f"{identities} ({provider} {provider_player_id}); reconcile the opening-date roster"
                )
        for (name, birth_date), identities in sorted(player_candidates.items()):
            if len(identities) > 1:
                errors.append(
                    "strict validation rejects ambiguous same-person player candidates "
                    f"{identities} ({name!r}, {birth_date}); reconcile the opening-date roster"
                )

    for identity, club in club_index.items():
        roster = club.get("roster_player_ids")
        if not isinstance(roster, list):
            errors.append(f"clubs[{identity}].roster_player_ids: must be a list")
            roster = []
        if len(roster) != len(set(roster)):
            errors.append(f"clubs[{identity}].roster_player_ids: duplicate player")
        shared_preserve = club.get("shared_preserve_player_ids") or []
        if not isinstance(shared_preserve, list):
            errors.append(f"clubs[{identity}].shared_preserve_player_ids: must be a list")
            shared_preserve = []
        for player_id in shared_preserve:
            if player_id not in roster:
                errors.append(f"clubs[{identity}].shared_preserve_player_ids: {player_id} is not in its roster")
            elif player_id in player_index and player_index[player_id].get("policy") != "preserve-existing-mode1":
                errors.append(f"clubs[{identity}].shared_preserve_player_ids: {player_id} is not whole-record preserve-only")
        for player_id in roster:
            _check_reference(player_id, player_index, f"clubs[{identity}].roster_player_ids", "player", errors)
            if player_id in player_index and player_index[player_id].get("club_id") != identity and player_id not in shared_preserve:
                errors.append(f"clubs[{identity}].roster_player_ids: {player_id} belongs to another club")
        opening = club.get("opening")
        if not isinstance(opening, dict):
            errors.append(f"clubs[{identity}].opening: must be an object")
            continue
        if opening.get("policy") == "preserve-existing-mode1":
            _check_proof_ref(opening.get("proof"), artifact_index, f"clubs[{identity}].opening.proof", errors)
            continue
        _check_date(opening.get("fixture_date"), f"clubs[{identity}].opening.fixture_date", errors)
        eleven = opening.get("starting_xi_player_ids")
        substitutes = opening.get("substitute_player_ids")
        if not isinstance(eleven, list) or len(eleven) != 11 or len(set(eleven)) != 11:
            errors.append(f"clubs[{identity}].opening.starting_xi_player_ids: exactly eleven unique players required")
            eleven = []
        if not isinstance(substitutes, list) or len(substitutes) != len(set(substitutes)):
            errors.append(f"clubs[{identity}].opening.substitute_player_ids: unique list required")
            substitutes = []
        for player_id in [*eleven, *substitutes]:
            if player_id not in roster:
                errors.append(f"clubs[{identity}].opening: {player_id!r} is not in its roster")
        if set(eleven) & set(substitutes):
            errors.append(f"clubs[{identity}].opening: starter cannot also be substitute")
        formation = opening.get("formation")
        if isinstance(formation, str) and re.fullmatch(r"[1-5](?:-[0-5]){1,4}", formation):
            if sum(int(part) for part in formation.split("-")) != 10:
                errors.append(f"clubs[{identity}].opening.formation: outfield shape must total ten")
        positions = opening.get("tactics_positions")
        if not isinstance(positions, list) or len(positions) != 11:
            errors.append(f"clubs[{identity}].opening.tactics_positions: eleven positions required")
        if "tactics_context" in opening:
            from scripts.season_contextual_tactics_v1 import validate_context, summary_positions
            try:
                context = opening["tactics_context"]
                validate_context(context, eleven)
                if positions != summary_positions(context):
                    raise ValueError("static summary conflicts with full contextual states")
                for slot in context['slots']:
                    if player_index[slot['player_id']]['carrier_id'] != slot['native_player_id']:
                        raise ValueError("contextual tactics native player ID differs from recipe")
            except (ValueError, KeyError, TypeError) as exc:
                errors.append(f"clubs[{identity}].opening.tactics_context: {exc}")
        _check_proof_ref(opening.get("proof"), artifact_index, f"clubs[{identity}].opening.proof", errors)

    assets = package.get("assets")
    if isinstance(assets, dict):
        kits = assets.get("kits")
        if not isinstance(kits, list):
            errors.append("assets.kits: must be a list")
            kits = []
        kit_clubs: set[str] = set()
        for index, kit in enumerate(kits):
            if not isinstance(kit, dict):
                errors.append(f"assets.kits[{index}]: must be an object")
                continue
            club_id = kit.get("club_id")
            _check_reference(club_id, club_index, f"assets.kits[{index}].club_id", "club", errors)
            if club_id in kit_clubs:
                errors.append(f"assets.kits[{index}].club_id: duplicate club")
            if isinstance(club_id, str):
                kit_clubs.add(club_id)
            if kit.get("policy") == "preserve-existing-mode1" and kit.get("artifact_ids"):
                errors.append(f"assets.kits[{index}].artifact_ids: preserve-existing-mode1 must not name a kit artifact")
            if kit.get("policy") != "preserve-existing-mode1" and not kit.get("artifact_ids"):
                errors.append(f"assets.kits[{index}].artifact_ids: writable kit requires an artifact")
            for artifact_id in kit.get("artifact_ids", []):
                _check_reference(artifact_id, artifact_index, f"assets.kits[{index}].artifact_ids", "artifact", errors)
            _check_proof_ref(kit.get("proof"), artifact_index, f"assets.kits[{index}].proof", errors)
        if set(club_index) != kit_clubs:
            errors.append("assets.kits: every club must have exactly one kit asset set")

        portraits = assets.get("portraits")
        if not isinstance(portraits, list):
            errors.append("assets.portraits: must be a list")
            portraits = []
        portrait_players: set[str] = set()
        for index, portrait in enumerate(portraits):
            if not isinstance(portrait, dict):
                errors.append(f"assets.portraits[{index}]: must be an object")
                continue
            player_id = portrait.get("player_id")
            _check_reference(player_id, player_index, f"assets.portraits[{index}].player_id", "player", errors)
            if player_id in portrait_players:
                errors.append(f"assets.portraits[{index}].player_id: duplicate player")
            if isinstance(player_id, str):
                portrait_players.add(player_id)
            status = portrait.get("status")
            if status == "applied":
                for key in (
                    "original_artifact_id", "crop_artifact_id", "conversion_receipt_artifact_id", "output_container_artifact_id",
                ):
                    _check_reference(portrait.get(key), artifact_index, f"assets.portraits[{index}].{key}", "artifact", errors)
            _check_proof_ref(portrait.get("proof"), artifact_index, f"assets.portraits[{index}].proof", errors)
        if set(player_index) != portrait_players:
            errors.append("assets.portraits: every player must have exactly one portrait declaration")
    else:
        errors.append("assets must be an object")

    calendar = package.get("calendar")
    if isinstance(calendar, dict):
        _check_reference(calendar.get("patch_artifact_id"), artifact_index, "calendar.patch_artifact_id", "artifact", errors)
        _check_proof_ref(calendar.get("proof"), artifact_index, "calendar.proof", errors)
        if isinstance(season, dict) and calendar.get("target_year") != season.get("start_year"):
            errors.append("calendar.target_year must equal season.start_year")
        if isinstance(season, dict) and calendar.get("target_rollover_year") != season.get("end_year"):
            errors.append("calendar.target_rollover_year must equal season.end_year")
    else:
        errors.append("calendar must be an object")

    migration = package.get("migration")
    if isinstance(migration, dict):
        source_artifact_ids = migration.get("source_artifact_ids")
        if not isinstance(source_artifact_ids, list):
            errors.append("migration.source_artifact_ids must be a list")
        else:
            for artifact_id in source_artifact_ids:
                _check_reference(artifact_id, artifact_index, "migration.source_artifact_ids", "artifact", errors)
        known_gaps = migration.get("known_gaps")
        if not isinstance(known_gaps, list) or known_gaps != sorted(known_gaps):
            errors.append("migration.known_gaps must be a lexicographically sorted list")
        if strict and migration.get("status") != "native-v2":
            errors.append("strict validation rejects legacy-migrated package")
        if strict and known_gaps:
            errors.append("strict validation rejects package with known migration gaps")
    else:
        errors.append("migration must be an object")

    if errors:
        raise PackageValidationError("Season package V2 validation failed:\n- " + "\n- ".join(errors))


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageValidationError(f"cannot read {path}: {exc}") from exc


def _safe_id(prefix: str, value: int | str) -> str:
    token = str(value).lower()
    token = unicodedata.normalize("NFKD", token).encode("ascii", "ignore").decode("ascii")
    token = re.sub(r"[^a-z0-9]+", "-", token).strip("-")
    return f"{prefix}-{token or 'unknown'}"


def _legacy_artifact(path: Path, identity: str, kind: str = "legacy-receipt") -> dict[str, str]:
    return {
        "id": identity,
        "kind": kind,
        "media_type": "application/json",
        "relative_path": f"legacy/{path.name}",
        "sha256": sha256_file(path),
    }


def _find_optional(build_dir: Path, pattern: str) -> Path | None:
    candidates = sorted(build_dir.glob(pattern))
    return candidates[0] if candidates else None


def _find_existing_legacy_asset(raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str):
        return None
    candidate = Path(raw_path)
    return candidate if candidate.is_file() else None


def migrate_2015_english92(build_dir: Path) -> dict[str, Any]:
    """Convert existing 2015 English receipts into portable V2 *metadata*.

    The migration hashes the actual receipts and any retained portrait source/crop
    files, but intentionally does not copy PM99 FDIs, PKFs, EXEs, or images.
    Their content IDs are enough for a future asset store and compiler to demand
    exact inputs.
    """
    manifest_path = build_dir / "2015-16-english92-manifest.json"
    player_ledger_path = build_dir / "player-ledger.json"
    manager_audit_path = build_dir / "manager-audit.json"
    if not all(path.is_file() for path in (manifest_path, player_ledger_path, manager_audit_path)):
        raise PackageValidationError(
            "legacy migration requires 2015-16-english92-manifest.json, player-ledger.json and manager-audit.json"
        )
    manifest = _load_json(manifest_path)
    player_ledger = _load_json(player_ledger_path)
    manager_audit = _load_json(manager_audit_path)
    face_path = _find_optional(build_dir, "face-stage-receipt.json")
    kit_path = _find_optional(build_dir, "kit-stage/*kit-receipt.json")
    calendar_path = _find_optional(build_dir, "calendar-patch-receipt.json")
    build_manifest_path = _find_optional(build_dir, "build-manifest.json")
    release_audit_path = _find_optional(build_dir, "release-audit.json")

    artifacts: list[dict[str, Any]] = [
        _legacy_artifact(manifest_path, "legacy-season-manifest"),
        _legacy_artifact(player_ledger_path, "legacy-player-ledger"),
        _legacy_artifact(manager_audit_path, "legacy-manager-audit"),
    ]
    receipt_ids: dict[str, str] = {
        "manifest": "legacy-season-manifest",
        "players": "legacy-player-ledger",
        "managers": "legacy-manager-audit",
    }
    for key, path, identity in (
        ("face", face_path, "legacy-face-stage-receipt"),
        ("kits", kit_path, "legacy-kit-stage-receipt"),
        ("calendar", calendar_path, "legacy-calendar-patch-receipt"),
        ("build", build_manifest_path, "legacy-build-manifest"),
        ("audit", release_audit_path, "legacy-release-audit"),
    ):
        if path is not None:
            artifacts.append(_legacy_artifact(path, identity))
            receipt_ids[key] = identity

    build_manifest = _load_json(build_manifest_path) if build_manifest_path else {}
    for phase, hashes, artifact_kind in (
        ("base", build_manifest.get("source_hashes", {}), "base-file"),
        ("output", build_manifest.get("output_hashes", {}), "database-output"),
    ):
        if isinstance(hashes, dict):
            for filename, digest in sorted(hashes.items()):
                if isinstance(filename, str) and isinstance(digest, str) and SHA256_RE.fullmatch(digest):
                    artifacts.append({
                        "id": _safe_id(f"{phase}-file", filename),
                        "kind": artifact_kind,
                        "sha256": digest,
                    })

    players_by_record = {
        row.get("record_id"): row for row in player_ledger
        if isinstance(row, dict) and isinstance(row.get("record_id"), int)
    }
    manifest_players_by_record = {
        row.get("record_id"): row for row in manifest.get("players", [])
        if isinstance(row, dict) and isinstance(row.get("record_id"), int)
    }
    teams = manifest.get("teams", [])
    if not isinstance(teams, list) or not isinstance(player_ledger, list) or not isinstance(manager_audit, list):
        raise PackageValidationError("legacy manifests have unexpected collection shapes")

    sources = [
        {
            "id": "legacy-player-ledger",
            "title": "2015/16 English player and rating ledger",
            "proof_grade": "legacy-migrated",
            "evidence_artifact_id": receipt_ids["players"],
        },
        {
            "id": "legacy-season-manifest",
            "title": "2015/16 English club, roster and opening-lineup manifest",
            "proof_grade": "legacy-migrated",
            "evidence_artifact_id": receipt_ids["manifest"],
        },
    ]

    proof_artifact = receipt_ids.get("audit", receipt_ids["manifest"])
    proof_grade = "static-contract" if "audit" in receipt_ids else "legacy-migrated"
    common_proof = {"grade": proof_grade, "artifact_id": proof_artifact}
    managers: list[dict[str, Any]] = []
    manager_by_record: dict[int, dict[str, Any]] = {}
    for row in manager_audit:
        if not isinstance(row, dict) or not isinstance(row.get("manager_record_id"), int):
            continue
        record_id = row["manager_record_id"]
        item = {
            "id": _safe_id("manager", record_id),
            "carrier_id": record_id,
            "name": row.get("manager_name", "Unknown manager"),
            "proof": {"grade": "legacy-migrated", "artifact_id": receipt_ids["managers"]},
        }
        managers.append(item)
        manager_by_record[record_id] = item
    managers.sort(key=lambda item: item["id"])

    clubs: list[dict[str, Any]] = []
    for team in teams:
        if not isinstance(team, dict) or not isinstance(team.get("record_id"), int):
            continue
        record_id = team["record_id"]
        roster_records = team.get("roster_player_record_ids", [])
        starter_records = team.get("opening_lineup_player_record_ids", [])
        substitute_records = team.get("substitute_player_record_ids", [])
        positions = team.get("opening_tactics_positions", [])
        source = team.get("opening_tactics_source", {})
        fixture_date = source.get("fixture_date", "") if isinstance(source, dict) else ""
        try:
            fixture_date = dt.datetime.strptime(fixture_date, "%d/%m/%Y").date().isoformat()
        except (TypeError, ValueError):
            fixture_date = "2015-08-01"
        manager_record = team.get("manager_record_id")
        if manager_record not in manager_by_record:
            raise PackageValidationError(f"team {team.get('club')}: manager record {manager_record!r} absent from manager audit")
        club = {
            "id": _safe_id("club", record_id),
            "carrier_id": record_id,
            "name": team.get("short_name") or team.get("club"),
            "full_name": team.get("full_club_name") or team.get("club"),
            "division": team.get("division", "Unknown"),
            "ground_name": team.get("stadium_name", ""),
            "seated_capacity": team.get("seated_capacity", 0),
            "starting_finance": team.get("starting_finance", 0),
            "manager_id": _safe_id("manager", manager_record),
            "roster_player_ids": [_safe_id("player", value) for value in roster_records],
            "opening": {
                "fixture_date": fixture_date,
                "starting_xi_player_ids": [_safe_id("player", value) for value in starter_records],
                "substitute_player_ids": [_safe_id("player", value) for value in substitute_records],
                "formation": source.get("formation", "4-4-2") if isinstance(source, dict) else "4-4-2",
                "tactics_positions": positions,
                "proof": {"grade": "legacy-migrated", "artifact_id": receipt_ids["manifest"]},
            },
            "proof": {"grade": "legacy-migrated", "artifact_id": receipt_ids["manifest"]},
        }
        if "opening_tactics_context" in team:
            club["opening"]["tactics_context"] = copy.deepcopy(team["opening_tactics_context"])
        clubs.append(club)
    clubs.sort(key=lambda item: item["id"])

    players: list[dict[str, Any]] = []
    for ledger in player_ledger:
        if not isinstance(ledger, dict) or not isinstance(ledger.get("record_id"), int):
            continue
        record_id = ledger["record_id"]
        manifest_player = manifest_players_by_record.get(record_id, {})
        visible = ledger.get("visible_skills", {})
        if not isinstance(visible, dict):
            visible = {}
        player = {
            "id": _safe_id("player", record_id),
            "carrier_id": record_id,
            "carrier_family": ledger.get("family", "unknown"),
            "club_id": _safe_id("club", ledger.get("team_record_id", "unknown")),
            "name": ledger.get("name", "Unknown player"),
            "facts": {
                "birth_date": ledger.get("birth_date", "1900-01-01"),
                "nationality": ledger.get("nationality", "UNK"),
                "height_cm": ledger.get("height_cm", 170),
                "weight_kg": ledger.get("weight_kg", 70),
                "primary_position": ledger.get("position", "M"),
                "fine_roles": ledger.get("fine_roles", manifest_player.get("fine_roles", [])),
                "shirt_number": ledger.get("shirt_number", 0),
            },
            "ratings": {
                "profile": "pm99-visible-skills-v1",
                "values": {key: visible.get(key, 0) for key in (
                    "quality", "speed", "stamina", "aggression", "passing", "tackling", "heading", "shooting", "dribbling", "handling",
                )},
                "provenance": {
                    "method": ledger.get("rating_basis", "legacy ledger"),
                    "proof_grade": "legacy-migrated",
                    "source_ids": ["legacy-player-ledger"],
                },
            },
            "proof": {"grade": "legacy-migrated", "artifact_id": receipt_ids["players"]},
        }
        players.append(player)
    players.sort(key=lambda item: item["id"])

    proof_rows = [
        {"id": "proof-club-contract", "grade": "legacy-migrated", "artifact_id": receipt_ids["manifest"], "covers": ["clubs", "opening-xi", "formations", "rosters"]},
        {"id": "proof-player-ledger", "grade": "legacy-migrated", "artifact_id": receipt_ids["players"], "covers": ["player-facts", "ratings", "player-provenance"]},
        {"id": "proof-manager-audit", "grade": "legacy-migrated", "artifact_id": receipt_ids["managers"], "covers": ["managers"]},
    ]

    faces = _load_json(face_path) if face_path else {}
    portraits: list[dict[str, Any]] = []
    output_container_id: str | None = None
    if isinstance(faces, dict) and isinstance(faces.get("minifoto_sha256_after"), str):
        output_container_id = "portrait-output-minifoto-pkf"
        artifacts.append({
            "id": output_container_id,
            "kind": "portrait-conversion",
            "sha256": faces["minifoto_sha256_after"],
        })
    face_rows = {
        row.get("record_id"): row for row in faces.get("rows", [])
        if isinstance(row, dict) and isinstance(row.get("record_id"), int)
    } if isinstance(faces, dict) else {}
    face_gaps: list[str] = []
    for player in players:
        record_id = player["carrier_id"]
        row = face_rows.get(record_id)
        if isinstance(row, dict) and row.get("status") == "intentionally-no-photo":
            reason = row.get("no_verified_portrait_reason")
            portraits.append({
                "player_id": player["id"],
                "status": "native-no-photo",
                "review_reason": reason if isinstance(reason, str) and reason.strip() else "legacy face stage selected PM99 native no-photo",
                "proof": {"grade": "legacy-migrated", "artifact_id": receipt_ids.get("face", receipt_ids["players"])},
            })
            continue
        if not isinstance(row, dict) or row.get("status") != "applied":
            portraits.append({
                "player_id": player["id"],
                "status": "unresolved",
                "review_reason": "legacy face stage did not retain an approved portrait outcome",
                "proof": {"grade": "legacy-migrated", "artifact_id": receipt_ids.get("face", receipt_ids["players"])},
            })
            continue
        original_path = _find_existing_legacy_asset(row.get("source_image_path"))
        crop_path = _find_existing_legacy_asset(row.get("preview_path"))
        if original_path is None or crop_path is None or output_container_id is None:
            face_gaps.append(f"portrait carrier {record_id} lacks retained source/crop/conversion receipt")
            portraits.append({
                "player_id": player["id"],
                "status": "unresolved",
                "proof": {"grade": "legacy-migrated", "artifact_id": receipt_ids.get("face", receipt_ids["players"])},
            })
            continue
        original_id = _safe_id("portrait-original", record_id)
        crop_id = _safe_id("portrait-crop", record_id)
        artifacts.extend([
            {"id": original_id, "kind": "portrait-original", "sha256": sha256_file(original_path)},
            {"id": crop_id, "kind": "portrait-crop", "sha256": sha256_file(crop_path)},
        ])
        portrait = {
            "player_id": player["id"],
            "status": "applied",
            "original_artifact_id": original_id,
            "crop_artifact_id": crop_id,
            "conversion_receipt_artifact_id": receipt_ids["face"],
            "output_container_artifact_id": output_container_id,
            "proof": {"grade": "legacy-migrated", "artifact_id": receipt_ids["face"]},
        }
        if isinstance(row.get("source_url"), str):
            portrait["source_uri"] = row["source_url"]
        portraits.append(portrait)
    portraits.sort(key=lambda item: item["player_id"])
    if face_path:
        proof_rows.append({"id": "proof-portrait-stage", "grade": "legacy-migrated", "artifact_id": receipt_ids["face"], "covers": ["portrait-original", "portrait-crop", "portrait-conversion"]})

    kits: list[dict[str, Any]] = []
    kit_receipt = _load_json(kit_path) if kit_path else {}
    kit_records_by_team: dict[int, list[str]] = {}
    if isinstance(kit_receipt, dict):
        for patch in kit_receipt.get("patched", []):
            if not isinstance(patch, dict) or not isinstance(patch.get("team_id"), int):
                continue
            digest = patch.get("bitmap_sha256_after")
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                continue
            identity = _safe_id("kit", f"{patch['team_id']}-{patch.get('archive_name', 'archive')}-slot-{patch.get('slot', 0)}")
            artifacts.append({"id": identity, "kind": "kit-render", "sha256": digest})
            kit_records_by_team.setdefault(patch["team_id"], []).append(identity)
    for club in clubs:
        record_ids = sorted(kit_records_by_team.get(club["carrier_id"], []))
        if not record_ids:
            raise PackageValidationError(f"club {club['name']}: no retained kit receipt assets")
        kits.append({
            "club_id": club["id"],
            "artifact_ids": record_ids,
            "proof": {"grade": "legacy-migrated", "artifact_id": receipt_ids.get("kits", receipt_ids["manifest"])},
        })
    kits.sort(key=lambda item: item["club_id"])
    if kit_path:
        proof_rows.append({"id": "proof-kit-stage", "grade": "legacy-migrated", "artifact_id": receipt_ids["kits"], "covers": ["kits"]})

    calendar_receipt = _load_json(calendar_path) if calendar_path else {}
    if not isinstance(calendar_receipt, dict) or not isinstance(calendar_receipt.get("after_sha256"), str):
        raise PackageValidationError("legacy migration requires calendar-patch-receipt.json with after_sha256")
    calendar_output_id = "calendar-output-managpre-exe"
    artifacts.append({"id": calendar_output_id, "kind": "calendar-patch", "sha256": calendar_receipt["after_sha256"]})
    proof_rows.append({"id": "proof-calendar-patch", "grade": "legacy-migrated", "artifact_id": receipt_ids["calendar"], "covers": ["calendar"]})
    proof_rows.sort(key=lambda item: item["id"])

    # Deduplicate by id after rows from independent legacy receipts are added.
    artifact_by_id: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        identity = artifact["id"]
        prior = artifact_by_id.get(identity)
        if prior is not None and prior != artifact:
            raise PackageValidationError(f"migration generated conflicting artifact {identity}")
        artifact_by_id[identity] = artifact

    gaps = [
        "external source pages were not captured with content hashes; their legacy receipts prove only the imported metadata",
        "legacy face receipts lack a per-player crop recipe; retained crop pixels are hashed but cannot be regenerated from originals alone",
        "legacy face receipts record only a shared MINIFOTO.PKF output hash, not one rendered bitmap hash per player",
        "legacy kit receipts prove rendered PM99 bitmap hashes but do not retain a source-artwork hash or editable kit recipe",
        "legacy release manifests contain machine paths and timestamps; those fields are intentionally omitted from V2",
    ]
    gaps.extend(face_gaps)
    package = {
        "schema_version": SCHEMA_VERSION,
        "package_id": "pm99-2015-16-english92-legacy",
        "season": {"start_year": 2015, "end_year": 2016, "label": "2015/16"},
        "scope": {
            "id": "english-four-divisions",
            "title": "2015/16 English four divisions, existing PM99 carriers",
            "countries": ["ENG"],
            "competition_policy": "proven-membership-only",
        },
        "artifacts": sorted(artifact_by_id.values(), key=lambda item: item["id"]),
        "sources": sorted(sources, key=lambda item: item["id"]),
        "clubs": clubs,
        "players": players,
        "managers": managers,
        "assets": {"kits": kits, "portraits": portraits},
        "calendar": {
            "base_year": calendar_receipt.get("base_year", 1998),
            "target_year": calendar_receipt.get("target_year", 2015),
            "target_rollover_year": calendar_receipt.get("target_rollover_year", 2016),
            "patch_artifact_id": calendar_output_id,
            "proof": {"grade": "legacy-migrated", "artifact_id": receipt_ids["calendar"]},
        },
        "proofs": proof_rows,
        "migration": {
            "status": "legacy-migrated",
            "source_artifact_ids": sorted(receipt_ids.values()),
            "known_gaps": sorted(set(gaps)),
        },
    }
    validate_package(package)
    return package


def _command_validate(args: argparse.Namespace) -> int:
    package = read_canonical_package(Path(args.package))
    validate_package(package, strict=args.strict)
    print(json.dumps({"ok": True, "package_id": package["package_id"], "sha256": sha256_file(Path(args.package))}, sort_keys=True))
    return 0


def _command_migrate_2015(args: argparse.Namespace) -> int:
    package = migrate_2015_english92(Path(args.input_dir))
    output = Path(args.output)
    write_canonical_package(output, package)
    print(json.dumps({
        "ok": True,
        "package_id": package["package_id"],
        "output": str(output),
        "sha256": sha256_file(output),
        "known_gaps": len(package["migration"]["known_gaps"]),
    }, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a canonical V2 package")
    validate.add_argument("--package", required=True)
    validate.add_argument("--strict", action="store_true", help="require native V2 package with no migration gaps")
    validate.set_defaults(handler=_command_validate)
    migrate = commands.add_parser("migrate-2015", help="adapt an existing 2015 English build directory")
    migrate.add_argument("--input-dir", required=True)
    migrate.add_argument("--output", required=True)
    migrate.set_defaults(handler=_command_migrate_2015)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except PackageValidationError as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
