#!/usr/bin/env python3
"""Project a complete, generic package-intake into Season Package V2.

This is the intentionally narrow authoring bridge between the reusable source
intake/reconciliation lane and the reusable binary compiler.  It does not discover clubs,
assign PM99 carriers, match people, invent ratings, or make assets.  Those are
inputs.  Its job is to make the hand-off deterministic and fail closed:

* a canonical ``pm99-season-package-intake-v1`` supplies reconciled factual
  club, manager and player rows, plus source artifacts and proofs; and
  is deliberately downstream of the raw all-carrier
  ``pm99-season-source-intake-v1`` capture;
* one or more canonical ``pm99-season-intake-editorial-overlay-v1`` documents
  supply the required opening, rating, kit and portrait declarations; and
* the result is accepted only when it is a strict
  ``pm99-season-package-v2`` document.

Consequently, changing one rating, kit, portrait, or opening lineup is a small
hash-bound overlay change.  It cannot cause an unrelated season record to be
rediscovered or regenerated.  The producer of the intake is deliberately a
separate concern; it can be fed by any dated source capture once fixed-carrier
identity and person reconciliation are complete.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2


INTAKE_SCHEMA = "pm99-season-package-intake-v1"
OVERLAY_SCHEMA = "pm99-season-intake-editorial-overlay-v1"
RECEIPT_SCHEMA = "pm99-season-intake-package-projection-receipt-v1"

_INTAKE_KEYS = {
    "schema_version",
    "intake_id",
    "season",
    "scope",
    "artifacts",
    "sources",
    "clubs",
    "players",
    "managers",
    "calendar",
    "proofs",
    "migration",
}
_INTAKE_CLUB_REQUIRED = {
    "id",
    "identity_id",
    "carrier_id",
    "name",
    "division",
    "manager_id",
    "roster_player_ids",
    "proof",
}
_INTAKE_CLUB_OPTIONAL = {
    "full_name",
    "ground_name",
    "seated_capacity",
    "ground_policy",
    "capacity_policy",
    "starting_finance",
    "shared_preserve_player_ids",
}
_INTAKE_PLAYER_REQUIRED = {
    "id",
    "person_id",
    "carrier_id",
    "carrier_family",
    "club_id",
    "name",
    "facts",
    "proof",
}
_INTAKE_PLAYER_OPTIONAL = {
    "source_name",
    "append_from_carrier_id",
    "recycle_from_mode1_carrier_id",
    "mode0_clone_carrier_id",
    "policy",
    "fact_fallbacks",
}
_INTAKE_MANAGER_REQUIRED = {"id", "person_id", "carrier_id", "name", "proof"}
_INTAKE_MANAGER_OPTIONAL = {"policy"}
_OVERLAY_KEYS = {
    "schema_version",
    "overlay_id",
    "intake_sha256",
    "package_id",
    "club_openings",
    "club_kits",
    "player_ratings",
    "player_portraits",
}
_RATING_KEYS = {"player_id", "ratings"}
_OPENING_KEYS = {"club_id", "opening"}
_KIT_KEYS = {"club_id", "artifact_ids", "policy", "proof"}
_PORTRAIT_KEYS = {
    "player_id",
    "status",
    "original_artifact_id",
    "crop_artifact_id",
    "crop_recipe_artifact_id",
    "conversion_receipt_artifact_id",
    "output_container_artifact_id",
    "source_uri",
    "review_reason",
    "proof",
}
_PLAYER_FACT_KEYS = {
    "birth_date",
    "nationality",
    "height_cm",
    "weight_kg",
    "primary_position",
    "fine_roles",
    "shirt_number",
}
_SECONDARY_FACT_KEYS = {
    "birth_date",
    "nationality",
    "height_cm",
    "weight_kg",
    "shirt_number",
}
_FACT_FALLBACK_KEYS = {"field", "method", "value", "reason", "proof"}
_FACT_FALLBACK_METHODS = {
    "deterministic-default",
    "nearby-season",
    "preserve-existing-mode1",
}


class IntakePackageError(ValueError):
    """An intake or overlay cannot safely become a strict package."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_document(value: Mapping[str, Any]) -> str:
    return _sha256_bytes(_canonical_bytes(dict(value)))


def _require_exact_keys(value: Any, *, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise IntakePackageError(f"{label} must have exactly {sorted(keys)}; got {actual}")
    return value


def _require_keys_subset(
    value: Any, *, required: set[str], optional: set[str], label: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise IntakePackageError(f"{label} must be an object")
    actual = set(value)
    missing = sorted(required - actual)
    extra = sorted(actual - required - optional)
    if missing or extra:
        raise IntakePackageError(f"{label} has missing {missing} or unsupported {extra} fields")
    return value


def _require_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not package_v2.ID_RE.fullmatch(value):
        raise IntakePackageError(f"{label} must be a stable lower-case ID")
    return value


def _require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not package_v2.SHA256_RE.fullmatch(value):
        raise IntakePackageError(f"{label} must be a lowercase SHA-256")
    return value


def _require_sorted_unique_rows(
    value: Any, *, id_key: str, label: str
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise IntakePackageError(f"{label} must be a list")
    rows: list[dict[str, Any]] = []
    previous: str | None = None
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            raise IntakePackageError(f"{label}[{index}] must be an object")
        identity = _require_id(row.get(id_key), label=f"{label}[{index}].{id_key}")
        if previous is not None and identity <= previous:
            raise IntakePackageError(f"{label} must be strictly sorted and unique by {id_key}")
        previous = identity
        rows.append(row)
    return rows


def _read_canonical(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    path = path.expanduser().resolve()
    if path.is_symlink() or not path.is_file():
        raise IntakePackageError(f"{label} must be a regular file: {path}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntakePackageError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict) or raw != _canonical_bytes(value):
        raise IntakePackageError(f"{label} must be canonical UTF-8 JSON: {path}")
    return value, _sha256_bytes(raw)


def _validate_intake_club(row: Any, *, index: int) -> None:
    label = f"intake.clubs[{index}]"
    row = _require_keys_subset(
        row,
        required=_INTAKE_CLUB_REQUIRED,
        optional=_INTAKE_CLUB_OPTIONAL,
        label=label,
    )
    for key in ("id", "identity_id", "manager_id"):
        _require_id(row.get(key), label=f"{label}.{key}")


def _validate_intake_player(row: Any, *, index: int) -> None:
    label = f"intake.players[{index}]"
    row = _require_keys_subset(
        row,
        required=_INTAKE_PLAYER_REQUIRED,
        optional=_INTAKE_PLAYER_OPTIONAL,
        label=label,
    )
    for key in ("id", "person_id", "club_id"):
        _require_id(row.get(key), label=f"{label}.{key}")
    facts = row.get("facts")
    if not isinstance(facts, dict) or set(facts) != _PLAYER_FACT_KEYS:
        raise IntakePackageError(f"{label}.facts must contain every strict player fact")
    for field in ("primary_position", "fine_roles"):
        value = facts[field]
        if value is None or isinstance(value, Mapping):
            raise IntakePackageError(
                f"{label}.facts.{field} is required and cannot use a field fallback"
            )
    fallback_rows = row.get("fact_fallbacks", [])
    if not isinstance(fallback_rows, list):
        raise IntakePackageError(f"{label}.fact_fallbacks must be a list")
    previous: str | None = None
    fallback_fields: set[str] = set()
    for fallback_index, fallback in enumerate(fallback_rows):
        fallback_label = f"{label}.fact_fallbacks[{fallback_index}]"
        fallback = _require_exact_keys(fallback, keys=_FACT_FALLBACK_KEYS, label=fallback_label)
        field = fallback.get("field")
        if field not in _SECONDARY_FACT_KEYS:
            raise IntakePackageError(
                f"{fallback_label}.field must name a secondary player fact"
            )
        if previous is not None and str(field) <= previous:
            raise IntakePackageError(f"{label}.fact_fallbacks must be field-sorted and unique")
        previous = str(field)
        fallback_fields.add(str(field))
        if fallback.get("method") not in _FACT_FALLBACK_METHODS:
            raise IntakePackageError(f"{fallback_label}.method is unsupported")
        if not isinstance(fallback.get("reason"), str) or not fallback["reason"].strip():
            raise IntakePackageError(f"{fallback_label}.reason must explain the missing source fact")
        proof = fallback.get("proof")
        if not isinstance(proof, dict) or set(proof) != {"grade", "artifact_id"}:
            raise IntakePackageError(f"{fallback_label}.proof must be an explicit proof reference")
        if fallback.get("value") != facts[field]:
            raise IntakePackageError(f"{fallback_label}.value must equal facts.{field}")
        if fallback.get("method") == "preserve-existing-mode1" and fallback.get("value") != {
            "policy": "preserve-existing-mode1"
        }:
            raise IntakePackageError(
                f"{fallback_label}.value must request preserve-existing-mode1"
            )
    for field in _SECONDARY_FACT_KEYS:
        value = facts[field]
        if value is None:
            raise IntakePackageError(
                f"{label}.facts.{field} must contain a usable value or explicit preserve fallback"
            )
        if isinstance(value, Mapping) and field not in fallback_fields:
            raise IntakePackageError(
                f"{label}.facts.{field} preserve fallback must be logged in fact_fallbacks"
            )


def _validate_intake_manager(row: Any, *, index: int) -> None:
    label = f"intake.managers[{index}]"
    row = _require_keys_subset(
        row,
        required=_INTAKE_MANAGER_REQUIRED,
        optional=_INTAKE_MANAGER_OPTIONAL,
        label=label,
    )
    for key in ("id", "person_id"):
        _require_id(row.get(key), label=f"{label}.{key}")


def validate_intake(value: Mapping[str, Any]) -> None:
    """Validate the source half of a strict package before overlays are read."""

    intake = _require_exact_keys(dict(value), keys=_INTAKE_KEYS, label="intake")
    if intake["schema_version"] != INTAKE_SCHEMA:
        raise IntakePackageError(f"intake.schema_version must be {INTAKE_SCHEMA!r}")
    _require_id(intake["intake_id"], label="intake.intake_id")
    clubs = _require_sorted_unique_rows(intake["clubs"], id_key="id", label="intake.clubs")
    players = _require_sorted_unique_rows(intake["players"], id_key="id", label="intake.players")
    managers = _require_sorted_unique_rows(intake["managers"], id_key="id", label="intake.managers")
    if not clubs or not players or not managers:
        raise IntakePackageError("strict intake needs at least one club, player and manager")
    for index, row in enumerate(clubs):
        _validate_intake_club(row, index=index)
    for index, row in enumerate(players):
        _validate_intake_player(row, index=index)
    for index, row in enumerate(managers):
        _validate_intake_manager(row, index=index)


def _validate_overlay_row_keys(
    value: Any, *, required: set[str], optional: set[str], label: str
) -> dict[str, Any]:
    return _require_keys_subset(value, required=required, optional=optional, label=label)


def _collect_overlay_rows(
    overlays: Sequence[tuple[Mapping[str, Any], str]],
    *,
    field: str,
    id_key: str,
    required: set[str],
    optional: set[str],
    known_ids: set[str],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for overlay, _digest in overlays:
        overlay_id = str(overlay["overlay_id"])
        rows = _require_sorted_unique_rows(
            overlay[field], id_key=id_key, label=f"overlay {overlay_id}.{field}"
        )
        for index, row in enumerate(rows):
            label = f"overlay {overlay_id}.{field}[{index}]"
            _validate_overlay_row_keys(row, required=required, optional=optional, label=label)
            identity = _require_id(row[id_key], label=f"{label}.{id_key}")
            if identity not in known_ids:
                raise IntakePackageError(f"{label}.{id_key} does not exist in the source intake: {identity}")
            if identity in result:
                raise IntakePackageError(
                    f"multiple editorial overlays change the same {field} target: {identity}"
                )
            result[identity] = copy.deepcopy(row)
    if set(result) != known_ids:
        missing = sorted(known_ids - set(result))
        raise IntakePackageError(f"editorial overlays leave {field} incomplete: {missing}")
    return result


def validate_overlays(
    overlays: Sequence[tuple[Mapping[str, Any], str]], *, intake_sha256: str, intake: Mapping[str, Any]
) -> None:
    if not overlays:
        raise IntakePackageError("at least one editorial overlay is required")
    seen_ids: set[str] = set()
    package_id: str | None = None
    for overlay, _digest in overlays:
        value = _require_exact_keys(dict(overlay), keys=_OVERLAY_KEYS, label="editorial overlay")
        if value["schema_version"] != OVERLAY_SCHEMA:
            raise IntakePackageError(
                f"editorial overlay.schema_version must be {OVERLAY_SCHEMA!r}"
            )
        overlay_id = _require_id(value["overlay_id"], label="editorial overlay.overlay_id")
        if overlay_id in seen_ids:
            raise IntakePackageError(f"editorial overlay ID is duplicated: {overlay_id}")
        seen_ids.add(overlay_id)
        if _require_sha256(value["intake_sha256"], label=f"overlay {overlay_id}.intake_sha256") != intake_sha256:
            raise IntakePackageError(f"overlay {overlay_id} targets a different source intake")
        candidate_package_id = _require_id(value["package_id"], label=f"overlay {overlay_id}.package_id")
        if package_id is not None and candidate_package_id != package_id:
            raise IntakePackageError("all editorial overlays must name the same package_id")
        package_id = candidate_package_id

    club_ids = {str(row["id"]) for row in intake["clubs"]}
    player_ids = {str(row["id"]) for row in intake["players"]}
    _collect_overlay_rows(
        overlays,
        field="club_openings",
        id_key="club_id",
        required=_OPENING_KEYS,
        optional=set(),
        known_ids=club_ids,
    )
    _collect_overlay_rows(
        overlays,
        field="club_kits",
        id_key="club_id",
        required={"club_id", "artifact_ids", "proof"},
        optional={"policy"},
        known_ids=club_ids,
    )
    _collect_overlay_rows(
        overlays,
        field="player_ratings",
        id_key="player_id",
        required=_RATING_KEYS,
        optional=set(),
        known_ids=player_ids,
    )
    _collect_overlay_rows(
        overlays,
        field="player_portraits",
        id_key="player_id",
        required={"player_id", "status", "proof"},
        optional=_PORTRAIT_KEYS - {"player_id", "status", "proof"},
        known_ids=player_ids,
    )


def project_package(
    *, intake: Mapping[str, Any], overlays: Sequence[tuple[Mapping[str, Any], str]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return one strict V2 package and a path-independent projection receipt."""

    intake = copy.deepcopy(dict(intake))
    validate_intake(intake)
    intake_sha256 = _sha256_document(intake)
    ordered_overlays = sorted(overlays, key=lambda item: str(item[0].get("overlay_id", "")))
    validate_overlays(ordered_overlays, intake_sha256=intake_sha256, intake=intake)

    club_ids = {str(row["id"]) for row in intake["clubs"]}
    player_ids = {str(row["id"]) for row in intake["players"]}
    openings = _collect_overlay_rows(
        ordered_overlays, field="club_openings", id_key="club_id", required=_OPENING_KEYS,
        optional=set(), known_ids=club_ids,
    )
    kits = _collect_overlay_rows(
        ordered_overlays, field="club_kits", id_key="club_id",
        required={"club_id", "artifact_ids", "proof"}, optional={"policy"}, known_ids=club_ids,
    )
    ratings = _collect_overlay_rows(
        ordered_overlays, field="player_ratings", id_key="player_id", required=_RATING_KEYS,
        optional=set(), known_ids=player_ids,
    )
    portraits = _collect_overlay_rows(
        ordered_overlays, field="player_portraits", id_key="player_id",
        required={"player_id", "status", "proof"},
        optional=_PORTRAIT_KEYS - {"player_id", "status", "proof"}, known_ids=player_ids,
    )

    package_id = str(ordered_overlays[0][0]["package_id"])
    clubs = []
    for row in intake["clubs"]:
        club = copy.deepcopy(row)
        club["opening"] = openings[str(club["id"])]["opening"]
        clubs.append(club)
    players = []
    for row in intake["players"]:
        player = copy.deepcopy(row)
        player["ratings"] = ratings[str(player["id"])]["ratings"]
        players.append(player)

    package = {
        "schema_version": package_v2.SCHEMA_VERSION,
        "package_id": package_id,
        "season": copy.deepcopy(intake["season"]),
        "scope": copy.deepcopy(intake["scope"]),
        "artifacts": sorted(copy.deepcopy(intake["artifacts"]), key=lambda row: str(row.get("id", ""))),
        "sources": sorted(copy.deepcopy(intake["sources"]), key=lambda row: str(row.get("id", ""))),
        "clubs": sorted(clubs, key=lambda row: str(row["id"])),
        "players": sorted(players, key=lambda row: str(row["id"])),
        "managers": sorted(copy.deepcopy(intake["managers"]), key=lambda row: str(row.get("id", ""))),
        "assets": {
            "kits": [kits[club_id] for club_id in sorted(kits)],
            "portraits": [portraits[player_id] for player_id in sorted(portraits)],
        },
        "calendar": copy.deepcopy(intake["calendar"]),
        "proofs": sorted(copy.deepcopy(intake["proofs"]), key=lambda row: str(row.get("id", ""))),
        "migration": copy.deepcopy(intake["migration"]),
    }
    try:
        package_v2.validate_package(package, strict=True)
    except package_v2.PackageValidationError as exc:
        raise IntakePackageError(
            "source intake plus editorial overlays cannot form a strict V2 package: "
            f"{exc}"
        ) from exc

    package_sha256 = _sha256_document(package)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "intake_id": intake["intake_id"],
        "intake_sha256": intake_sha256,
        "overlays": [
            {"overlay_id": overlay["overlay_id"], "sha256": digest}
            for overlay, digest in ordered_overlays
        ],
        "package_id": package_id,
        "package_sha256": package_sha256,
        "coverage": {
            "club_count": len(package["clubs"]),
            "manager_count": len(package["managers"]),
            "player_count": len(package["players"]),
            "kit_declaration_count": len(package["assets"]["kits"]),
            "portrait_declaration_count": len(package["assets"]["portraits"]),
        },
        "implementation_sha256": package_v2.sha256_file(Path(__file__).resolve()),
    }
    return package, receipt


def _write_canonical(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(dict(value)))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", required=True, type=Path)
    parser.add_argument(
        "--editorial-overlay",
        required=True,
        action="append",
        type=Path,
        help="canonical overlay; repeat to compose independent field-scoped decisions",
    )
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-receipt", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        intake_path = args.intake.resolve()
        intake, _intake_digest = _read_canonical(intake_path, label="source intake")
        overlays = [
            _read_canonical(path.resolve(), label="editorial overlay")
            for path in args.editorial_overlay
        ]
        output_package = args.output_package.resolve()
        output_receipt = args.output_receipt.resolve()
        inputs = {intake_path, *(path.resolve() for path in args.editorial_overlay)}
        if output_package in inputs or output_receipt in inputs or output_package == output_receipt:
            raise IntakePackageError("package and receipt outputs must be distinct from all source documents")
        package, receipt = project_package(intake=intake, overlays=overlays)
        package_v2.write_canonical_package(output_package, package)
        _write_canonical(output_receipt, receipt)
    except (IntakePackageError, OSError) as exc:
        print(f"season intake package error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
