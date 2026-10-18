#!/usr/bin/env python3
"""Shared identities and time-scoped corrections for PM99 historical seasons.

This sits above individual V2 season packages.  It keeps a real player, club
or manager identity separate from the PM99 carrier slot used in one season,
then compiles applicable editorial amendments into the existing guarded review
overlay format.  It never edits a generated game directory.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2
from scripts import season_review_v2 as review_v2


SCHEMA = "pm99-editorial-timeline-v1"
IDENTITY_AUDIT_SCHEMA = "pm99-editorial-identity-audit-v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SEASON_RE = re.compile(r"^20(?:0[0-9]|1[0-9]|2[0-5])-[0-9]{2}$")


class TimelineError(ValueError):
    """The shared editorial source is malformed or cannot safely target a package."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _hash(value: Any) -> str:
    return review_v2.sha256_bytes(_canonical_bytes(value))


def _read(path: Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TimelineError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != _canonical_bytes(value):
        raise TimelineError(f"{label} must be canonical JSON")
    return value


def _stable_id(prefix: str, value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-")
    candidate = f"{prefix}-{text or 'unknown'}"
    if len(candidate) > 80:
        candidate = candidate[:80].rstrip("-")
    if not package_v2.ID_RE.fullmatch(candidate):
        raise TimelineError(f"cannot make a stable identity ID from {value!r}")
    return candidate


def _validate_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not package_v2.ID_RE.fullmatch(value):
        raise TimelineError(f"{label} must be a stable ID")
    return value


def _validate_proof(value: Any, *, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"grade", "artifact_id"}:
        raise TimelineError(f"{label} must contain grade and artifact_id")
    if value["grade"] not in package_v2.PROOF_GRADES:
        raise TimelineError(f"{label}.grade is unknown")
    return {"grade": str(value["grade"]), "artifact_id": _validate_id(value["artifact_id"], label=f"{label}.artifact_id")}


def _schema_errors(value: dict[str, Any]) -> list[str]:
    schema_path = ROOT / "schemas" / "pm99-editorial-timeline-v1.schema.json"
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ImportError:
        return []
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(jsonschema.Draft202012Validator(schema).iter_errors(value), key=lambda item: list(item.absolute_path))
    return [f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}" for error in errors]


def validate_timeline(timeline: dict[str, Any]) -> None:
    """Validate shared identities, record bindings and time-scoped amendments."""
    errors = _schema_errors(timeline)
    package_v2._check_portable_strings(timeline, errors)
    if timeline.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA!r}")
    try:
        _validate_id(timeline.get("timeline_id"), label="timeline_id")
    except TimelineError as exc:
        errors.append(str(exc))
    identities = timeline.get("identities")
    if not isinstance(identities, dict) or set(identities) != {"clubs", "people"}:
        errors.append("identities must contain exactly clubs and people")
        identities = {"clubs": [], "people": []}
    club_ids: set[str] = set()
    people: dict[str, set[str]] = {}
    for collection, expected_kind in (("clubs", "club"), ("people", None)):
        rows = identities.get(collection)
        if not isinstance(rows, list):
            errors.append(f"identities.{collection} must be a list")
            continue
        previous: str | None = None
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                errors.append(f"identities.{collection}[{index}] must be an object")
                continue
            identity = row.get("id")
            try:
                identity = _validate_id(identity, label=f"identities.{collection}[{index}].id")
            except TimelineError as exc:
                errors.append(str(exc))
                continue
            if previous is not None and identity <= previous:
                errors.append(f"identities.{collection} IDs must be sorted and unique")
            previous = identity
            if not isinstance(row.get("name"), str) or not row["name"].strip():
                errors.append(f"identities.{collection}[{index}].name is required")
            aliases = row.get("aliases")
            if (
                not isinstance(aliases, list)
                or not all(isinstance(item, str) for item in aliases)
                or aliases != sorted(set(aliases))
            ):
                errors.append(f"identities.{collection}[{index}].aliases must be sorted unique strings")
            if expected_kind == "club":
                club_ids.add(identity)
            else:
                roles = row.get("roles")
                if (
                    not isinstance(roles, list)
                    or not roles
                    or not all(role in {"player", "manager"} for role in roles)
                    or roles != sorted(set(roles))
                ):
                    errors.append(f"identities.people[{index}].roles must be sorted player/manager roles")
                else:
                    people[identity] = set(roles)

    bindings = timeline.get("bindings")
    binding_keys: set[tuple[str, str, str]] = set()
    binding_index: dict[tuple[str, str, str], str] = {}
    if not isinstance(bindings, list):
        errors.append("bindings must be a list")
        bindings = []
    previous_binding: tuple[str, str, str] | None = None
    for index, row in enumerate(bindings):
        if not isinstance(row, dict):
            errors.append(f"bindings[{index}] must be an object")
            continue
        season, entity, record_id, identity_id = row.get("season"), row.get("entity"), row.get("package_record_id"), row.get("identity_id")
        if not isinstance(season, str) or not SEASON_RE.fullmatch(season):
            errors.append(f"bindings[{index}].season must be canonical YYYY-YY")
            continue
        if entity not in {"player", "club", "manager"}:
            errors.append(f"bindings[{index}].entity is invalid")
            continue
        try:
            record_id = _validate_id(record_id, label=f"bindings[{index}].package_record_id")
            identity_id = _validate_id(identity_id, label=f"bindings[{index}].identity_id")
        except TimelineError as exc:
            errors.append(str(exc))
            continue
        key = (season, str(entity), record_id)
        if previous_binding is not None and key <= previous_binding:
            errors.append("bindings must be sorted and unique by season/entity/package_record_id")
        previous_binding = key
        if key in binding_keys:
            errors.append(f"bindings[{index}] duplicates {key}")
        binding_keys.add(key)
        if entity == "club" and identity_id not in club_ids:
            errors.append(f"bindings[{index}] references unknown club identity {identity_id}")
        if entity in {"player", "manager"} and entity not in people.get(identity_id, set()):
            errors.append(f"bindings[{index}] references wrong or unknown person identity {identity_id}")
        binding_index[key] = identity_id

    amendments = timeline.get("amendments")
    if not isinstance(amendments, list):
        errors.append("amendments must be a list")
        amendments = []
    previous_amendment: str | None = None
    occupied: set[tuple[str, str, str, str]] = set()
    for index, row in enumerate(amendments):
        if not isinstance(row, dict):
            errors.append(f"amendments[{index}] must be an object")
            continue
        try:
            amendment_id = _validate_id(row.get("id"), label=f"amendments[{index}].id")
            proof = _validate_proof(row.get("proof"), label=f"amendments[{index}].proof")
        except TimelineError as exc:
            errors.append(str(exc))
            continue
        if previous_amendment is not None and amendment_id <= previous_amendment:
            errors.append("amendments must be sorted and unique by id")
        previous_amendment = amendment_id
        seasons = row.get("seasons")
        if not isinstance(seasons, list) or not seasons or seasons != sorted(set(seasons)) or not all(isinstance(item, str) and SEASON_RE.fullmatch(item) for item in seasons):
            errors.append(f"amendments[{index}].seasons must be sorted canonical seasons")
            continue
        target = row.get("target")
        if not isinstance(target, dict) or set(target) != {"entity", "identity_id"}:
            errors.append(f"amendments[{index}].target is invalid")
            continue
        entity, identity_id = target.get("entity"), target.get("identity_id")
        if entity not in review_v2.ALLOWED_DATA_PATHS:
            errors.append(f"amendments[{index}].target.entity is not editable")
            continue
        if entity == "club" and identity_id not in club_ids:
            errors.append(f"amendments[{index}] references unknown club identity")
        if entity in {"player", "manager"} and entity not in people.get(identity_id, set()):
            errors.append(f"amendments[{index}] references wrong or unknown person identity")
        changes = row.get("changes")
        if not isinstance(changes, dict) or not changes:
            errors.append(f"amendments[{index}].changes must be a non-empty object")
            continue
        rating_change = False
        for path in changes:
            if path not in review_v2.ALLOWED_DATA_PATHS[str(entity)]:
                errors.append(f"amendments[{index}] cannot change {entity}.{path}")
            if path.startswith("ratings.values."):
                rating_change = True
            for season in seasons:
                key = (season, str(entity), str(identity_id), path)
                if key in occupied:
                    errors.append(f"amendments[{index}] overlaps another amendment for {key}")
                occupied.add(key)
        if rating_change and not isinstance(row.get("rating_provenance"), dict):
            errors.append(f"amendments[{index}] rating changes require rating_provenance")
        if not rating_change and row.get("rating_provenance") is not None:
            errors.append(f"amendments[{index}] has rating_provenance without rating changes")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            errors.append(f"amendments[{index}].reason is required")
        _ = proof
    if errors:
        raise TimelineError("Editorial timeline validation failed:\n- " + "\n- ".join(errors))


def _season_key(package: dict[str, Any]) -> str:
    season = package.get("season")
    if not isinstance(season, dict) or not isinstance(season.get("start_year"), int) or not isinstance(season.get("end_year"), int):
        raise TimelineError("package has no usable season")
    return f"{season['start_year']:04d}-{season['end_year'] % 100:02d}"


def _package_rows(package: dict[str, Any], entity: str) -> list[dict[str, Any]]:
    return list(package[{"player": "players", "club": "clubs", "manager": "managers"}[entity]])


def identity_audit_package(package: dict[str, Any]) -> dict[str, Any]:
    """Report unbound records and ambiguous legacy identity candidates.

    Candidate rows are diagnostic only.  They are deliberately not converted
    into person IDs: equal display facts do not prove that two PM99 carriers
    represent one real person.
    """
    package_v2.validate_package(package)
    result: dict[str, Any] = {
        "schema_version": IDENTITY_AUDIT_SCHEMA,
        "package_id": package["package_id"],
        "package_canonical_sha256": _hash(package),
        "records": {},
        "ambiguous_player_candidates": [],
    }
    for entity in ("club", "player", "manager"):
        field = "identity_id" if entity == "club" else "person_id"
        rows = _package_rows(package, entity)
        missing = sorted(row["id"] for row in rows if row.get(field) is None)
        result["records"][entity] = {"total": len(rows), "missing_identity_ids": missing}
    candidates: dict[tuple[str, str, str], list[str]] = {}
    for player in _package_rows(package, "player"):
        facts = player.get("facts", {})
        if not isinstance(facts, dict):
            continue
        key = (str(player.get("name", "")).casefold(), str(facts.get("birth_date", "")), str(facts.get("nationality", "")))
        candidates.setdefault(key, []).append(str(player["id"]))
    result["ambiguous_player_candidates"] = [
        {
            "name": name,
            "birth_date": birth_date,
            "nationality": nationality,
            "package_record_ids": sorted(record_ids),
        }
        for (name, birth_date, nationality), record_ids in sorted(candidates.items())
        if len(record_ids) > 1
    ]
    return result


def validate_timeline_against_package(timeline: dict[str, Any], package: dict[str, Any]) -> None:
    """Require bindings for every editable identity in this package season.

    A preserve-only foreign manager may intentionally lack ``person_id``.  It
    is not editorial source and cannot be targeted by an amendment, so forcing
    a made-up real-world identity would make the shared timeline less honest.
    Every other package record remains an exact-binding requirement.
    """
    validate_timeline(timeline)
    package_v2.validate_package(package)
    season = _season_key(package)
    bindings = [row for row in timeline["bindings"] if row["season"] == season]
    by_key = {(row["entity"], row["package_record_id"]): row["identity_id"] for row in bindings}
    for entity in ("player", "club", "manager"):
        records = _package_rows(package, entity)
        expected = {
            row["id"]
            for row in records
            if not (
                entity == "manager"
                and row.get("policy") == "preserve-existing-mode1"
                and row.get("person_id") is None
            )
        }
        actual = {record_id for bound_entity, record_id in by_key if bound_entity == entity}
        if expected != actual:
            raise TimelineError(
                f"timeline bindings for {season} {entity}s do not exactly match package records; "
                f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
            )
        identity_field = "identity_id" if entity == "club" else "person_id"
        for row in records:
            declared = row.get(identity_field)
            bound = by_key.get((entity, row["id"]))
            if bound is None and row["id"] not in expected:
                continue
            if bound is None:
                raise TimelineError(f"package {entity} {row['id']} has no timeline binding")
            if declared is not None and declared != bound:
                raise TimelineError(
                    f"package {entity} {row['id']} has {identity_field} {declared!r}, timeline binds {bound!r}"
                )


def seed_timeline_from_package(package: dict[str, Any], *, timeline_id: str) -> dict[str, Any]:
    """Create an identity map from an identity-complete native season package.

    The operation intentionally does *not* derive person identities from a
    name, birthday or PM99 carrier.  Legacy data can contain duplicate carriers
    for the same apparent person; guessing would turn a data defect into an
    untraceable cross-season merge.
    """
    package_v2.validate_package(package)
    _validate_id(timeline_id, label="timeline_id")
    season = _season_key(package)
    clubs: list[dict[str, Any]] = []
    people_by_id: dict[str, dict[str, Any]] = {}
    bindings: list[dict[str, str]] = []
    for club in package["clubs"]:
        identity = club.get("identity_id")
        if not isinstance(identity, str):
            raise TimelineError(
                f"club {club['id']} lacks identity_id; reconcile its real-world identity before seeding"
            )
        clubs.append({"id": identity, "name": str(club["name"]), "aliases": []})
        bindings.append({"season": season, "entity": "club", "package_record_id": club["id"], "identity_id": identity})
    for entity, rows in (("player", package["players"]), ("manager", package["managers"])):
        for row in rows:
            identity = row.get("person_id")
            if not isinstance(identity, str):
                if entity == "manager" and row.get("policy") == "preserve-existing-mode1":
                    continue
                raise TimelineError(
                    f"{entity} {row['id']} lacks person_id; reconcile its real-world identity before seeding"
                )
            person = people_by_id.get(identity)
            if person is None:
                person = {"id": identity, "roles": [entity], "name": str(row["name"]), "aliases": []}
                people_by_id[identity] = person
            else:
                if person["name"] != str(row["name"]):
                    raise TimelineError(
                        f"person {identity} is named both {person['name']!r} and {row['name']!r}; "
                        "resolve the identity or record an alias before seeding"
                    )
                person["roles"] = sorted(set(person["roles"]) | {entity})
            bindings.append({"season": season, "entity": entity, "package_record_id": row["id"], "identity_id": identity})
    result = {
        "schema_version": SCHEMA,
        "timeline_id": timeline_id,
        "identities": {
            "clubs": sorted(clubs, key=lambda row: row["id"]),
            "people": sorted(people_by_id.values(), key=lambda row: row["id"]),
        },
        "bindings": sorted(bindings, key=lambda row: (row["season"], row["entity"], row["package_record_id"])),
        "amendments": [],
    }
    validate_timeline(result)
    return result


def build_review_overlay(
    *, package: dict[str, Any], timeline: dict[str, Any], override_id: str
) -> dict[str, Any]:
    """Translate applicable shared amendments into one guarded package overlay."""
    validate_timeline_against_package(timeline, package)
    _validate_id(override_id, label="override_id")
    season = _season_key(package)
    record_by_identity = {
        (binding["entity"], binding["identity_id"]): binding["package_record_id"]
        for binding in timeline["bindings"] if binding["season"] == season
    }
    artifacts = {row["id"] for row in package["artifacts"]}
    rows = {entity: {row["id"]: row for row in _package_rows(package, entity)} for entity in ("player", "club", "manager")}
    patches: list[dict[str, Any]] = []
    for amendment in timeline["amendments"]:
        if season not in amendment["seasons"]:
            continue
        target = amendment["target"]
        entity = target["entity"]
        record_id = record_by_identity.get((entity, target["identity_id"]))
        if record_id is None:
            raise TimelineError(f"amendment {amendment['id']} has no {season} carrier binding")
        proof = _validate_proof(amendment["proof"], label=f"amendment {amendment['id']}.proof")
        if proof["artifact_id"] not in artifacts:
            raise TimelineError(
                f"amendment {amendment['id']} evidence artifact {proof['artifact_id']!r} is absent from package"
            )
        target_row = rows[entity][record_id]
        expected = {path: copy.deepcopy(review_v2._get_path(target_row, path)) for path in amendment["changes"]}
        patch: dict[str, Any] = {
            "id": amendment["id"],
            "target": {"entity": entity, "id": record_id},
            "expected": expected,
            "set": copy.deepcopy(amendment["changes"]),
            "reason": amendment["reason"],
            "proof": proof,
        }
        if "rating_provenance" in amendment:
            patch["rating_provenance"] = copy.deepcopy(amendment["rating_provenance"])
        patches.append(patch)
    overlay = {
        "schema_version": review_v2.OVERRIDES_SCHEMA,
        "override_id": override_id,
        "base_package_canonical_sha256": _hash(package),
        "artifacts": [], "sources": [], "proofs": [],
        "data_patches": patches,
        "portrait_patches": [],
    }
    review_v2.validate_overrides(overlay)
    return overlay


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a canonical shared editorial timeline")
    validate.add_argument("--timeline", required=True, type=Path)
    seed = commands.add_parser("seed", help="seed one season's identity map from a V2 package")
    seed.add_argument("--package", required=True, type=Path)
    seed.add_argument("--timeline-id", required=True)
    seed.add_argument("--output", required=True, type=Path)
    audit = commands.add_parser("audit-package", help="report identity gaps without assigning identities")
    audit.add_argument("--package", required=True, type=Path)
    audit.add_argument("--output", required=True, type=Path)
    overlay = commands.add_parser("build-overlay", help="compile one season's applicable amendments into review overrides")
    overlay.add_argument("--package", required=True, type=Path)
    overlay.add_argument("--timeline", required=True, type=Path)
    overlay.add_argument("--override-id", required=True)
    overlay.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            timeline = _read(args.timeline, label="timeline")
            validate_timeline(timeline)
            print(json.dumps({"ok": True, "timeline_id": timeline["timeline_id"], "sha256": _hash(timeline)}, sort_keys=True))
        else:
            package = package_v2.read_canonical_package(args.package)
            package_v2.validate_package(package)
            if args.command == "audit-package":
                output = identity_audit_package(package)
            elif args.command == "seed":
                output = seed_timeline_from_package(package, timeline_id=args.timeline_id)
            else:
                timeline = _read(args.timeline, label="timeline")
                output = build_review_overlay(package=package, timeline=timeline, override_id=args.override_id)
            review_v2.write_canonical_json(args.output, output)
            print(json.dumps({"output": str(args.output), "sha256": _hash(output)}, sort_keys=True))
    except (TimelineError, package_v2.PackageValidationError, review_v2.SeasonReviewError, OSError) as exc:
        print(f"editorial timeline error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
