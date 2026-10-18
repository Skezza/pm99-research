#!/usr/bin/env python3
"""Compose prior repairs and the final ratings layer into one season package."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402


SCHEMA = "pm99-registered-quality-package-composition-v1"


class CompositionError(ValueError):
    """The existing repair layers cannot be combined without ambiguity."""


def _read(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompositionError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise CompositionError(f"{label} must be an object: {path}")
    return value


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(
        character.casefold() for character in text
        if character.isalnum() and not unicodedata.combining(character)
    )


def _repair_source(season: str, kind: str) -> tuple[dict[str, Any], Path, Path] | None:
    path = ROOT / f".local/season-direct-{kind}-repairs-v1/{season}.json"
    if not path.is_file():
        return None
    receipt = _read(path, label=f"{kind} repair receipt")
    refresh = receipt.get("runtime_refresh")
    source_path = Path(str(refresh.get("package_path"))) if isinstance(refresh, Mapping) else None
    if source_path is None or not source_path.is_file():
        raise CompositionError(f"{kind} receipt has no retained corrected package: {path}")
    # Derive the field-level delta from the retained strict corrected package. An
    # older direct-repair receipt can legitimately describe the last binary
    # refresh rather than every prior recipe correction (2004/05 exposed this
    # after a later Handling-only refresh).  The corrected package is the
    # durable result; its incidental action list is not an authoritative diff.
    corrected = _read(source_path, label=f"{kind} corrected package")
    package_v2.validate_package(corrected, strict=True)
    return corrected, source_path, path


def compose(season: str) -> tuple[dict[str, Any], dict[str, Any]]:
    release = registry.load_preferred_release(season)
    package = copy.deepcopy(_read(release.package_path, label="registered quality package"))
    players = {
        str(row.get("id")): row for row in package.get("players", [])
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }
    changes: dict[str, list[str]] = {"birth_date": [], "primary_position": [], "ratings": []}
    corrected_position_players: dict[str, Mapping[str, Any]] = {}
    inputs = [{
        "role": "registered-quality-package",
        "path": registry.relative_workspace_path(release.package_path),
        "sha256": registry.sha256_file(release.package_path),
    }]

    for kind, fact_fields in (
        ("birth-date-plausibility", ("birth_date",)),
        ("opening-lineup-position", ("primary_position",)),
    ):
        repair = _repair_source(season, kind)
        if repair is None:
            continue
        corrected, corrected_path, receipt_path = repair
        corrected_players = {
            str(row.get("id")): row for row in corrected.get("players", [])
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        }
        if set(corrected_players) != set(players):
            raise CompositionError(f"{kind} corrected package has a different player identity set")
        for player_id in sorted(players):
            target, source = players.get(player_id), corrected_players.get(player_id)
            assert target is not None and source is not None
            target_facts = target.get("facts")
            source_facts = source.get("facts")
            if not isinstance(target_facts, dict) or not isinstance(source_facts, Mapping):
                raise CompositionError(f"{kind} player has malformed facts: {player_id}")
            changed = False
            for field in fact_fields:
                before = target_facts.get(field)
                if field in source_facts:
                    target_facts[field] = copy.deepcopy(source_facts[field])
                else:
                    target_facts.pop(field, None)
                if target_facts.get(field) != before:
                    changes[field].append(player_id)
                    changed = True
            if kind == "opening-lineup-position" and changed:
                corrected_position_players[player_id] = source
        inputs.append({
            "role": f"{kind}-receipt", "path": registry.relative_workspace_path(receipt_path),
            "sha256": registry.sha256_file(receipt_path),
        })
        # Legacy repair stages edited their shared recipe path in place after
        # writing the receipt, so its historic package hash can be stale.  Bind
        # this migration to the exact strict package bytes actually consumed.
        inputs.append({
            "role": f"{kind}-corrected-package", "path": registry.relative_workspace_path(corrected_path),
            "sha256": registry.sha256_file(corrected_path),
        })

    rating_path = ROOT / f".local/season-english-preseason-rating-policy-v4/{season}/english-rating-layer.json"
    rating_layer = _read(rating_path, label="final English rating layer")
    rating_artifact_id = "english-preseason-ratings-v4"
    rating_source_id = "english-preseason-ratings-v4"
    artifacts = package.get("artifacts")
    sources = package.get("sources")
    if not isinstance(artifacts, list) or not isinstance(sources, list):
        raise CompositionError("registered package has malformed artifacts or sources")
    artifacts[:] = [row for row in artifacts if row.get("id") != rating_artifact_id]
    artifacts.append({
        "id": rating_artifact_id,
        "kind": "season-input",
        "relative_path": registry.relative_workspace_path(rating_path),
        "sha256": registry.sha256_file(rating_path),
    })
    sources[:] = [row for row in sources if row.get("id") != rating_source_id]
    sources.append({
        "id": rating_source_id,
        "title": "Deterministic prior-season table and player-context rating layer",
        "proof_grade": "reviewed-editorial",
        "evidence_artifact_id": rating_artifact_id,
    })
    artifacts.sort(key=lambda row: str(row.get("id") or ""))
    sources.sort(key=lambda row: str(row.get("id") or ""))
    clubs_by_name = {
        _normalise(row.get("name")): row for row in package.get("clubs", [])
        if isinstance(row, dict) and str(row.get("id") or "").startswith("english-club-")
    }
    unresolved = []
    ambiguous = []
    for club_row in rating_layer.get("rows", []):
        if not isinstance(club_row, Mapping):
            raise CompositionError("rating layer contains a malformed club row")
        club = clubs_by_name.get(_normalise(club_row.get("club")))
        if club is None:
            unresolved.append({"club": club_row.get("club"), "reason": "club-not-in-package"})
            continue
        roster = set(club.get("roster_player_ids") or [])
        roster_players = [players[player_id] for player_id in roster if player_id in players]
        players_by_name: dict[str, list[dict[str, Any]]] = {}
        for player in roster_players:
            for label in {player.get("name"), player.get("source_name")}:
                key = _normalise(label)
                if key:
                    players_by_name.setdefault(key, []).append(player)
        for rating in club_row.get("players", []):
            if not isinstance(rating, Mapping):
                raise CompositionError("rating layer contains a malformed player row")
            candidates_by_id = {
                str(player["id"]): player
                for player in players_by_name.get(_normalise(rating.get("player")), [])
            }
            candidates = list(candidates_by_id.values())
            if not candidates:
                unresolved.append({
                    "club": club.get("name"), "player": rating.get("player"),
                    "person_id": rating.get("person_id"), "candidate_count": 0,
                })
                continue
            if len(candidates) != 1:
                ambiguous.append({
                    "club": club.get("name"), "player": rating.get("player"),
                    "candidate_player_ids": sorted(candidates_by_id),
                })
                continue
            player = candidates[0]
            player["ratings"] = {
                "profile": "pm99-visible-skills-v1",
                "values": copy.deepcopy(rating.get("ratings")),
                "provenance": {
                    "method": "deterministic prior-season table editorial rating model v1",
                    "proof_grade": "reviewed-editorial",
                    "source_ids": [rating_source_id],
                },
            }
            changes["ratings"].append(str(player["id"]))
    if ambiguous:
        raise CompositionError(
            f"final English rating layer has {len(ambiguous)} ambiguous rows; first: {ambiguous[0]}"
        )
    rated_count = len(set(changes["ratings"]))
    source_rating_count = sum(
        len(row.get("players", [])) for row in rating_layer.get("rows", [])
        if isinstance(row, Mapping)
    )
    if rated_count < 0.8 * source_rating_count:
        raise CompositionError(
            f"final English rating coverage is too low: {rated_count}/{source_rating_count}"
        )
    # The historic position-repair receipts also contain the associated
    # goalkeeper/outfield Handling correction.  Apply only that one semantic
    # field after the broad ratings layer so the later stage cannot undo it.
    for player_id, corrected in corrected_position_players.items():
        target_values = players[player_id].get("ratings", {}).get("values")
        corrected_values = corrected.get("ratings", {}).get("values")
        if not isinstance(target_values, dict) or not isinstance(corrected_values, Mapping):
            raise CompositionError(f"position-repaired player lacks rating values: {player_id}")
        target_values["handling"] = corrected_values["handling"]
    package_v2.validate_package(package, strict=True)
    inputs.append({
        "role": "final-english-rating-layer", "path": registry.relative_workspace_path(rating_path),
        "sha256": registry.sha256_file(rating_path),
    })
    audit = {
        "schema_version": SCHEMA,
        "season": season,
        "inputs": inputs,
        "changes": {key: {"count": len(set(value)), "player_ids": sorted(set(value))} for key, value in changes.items()},
        "unresolved_rating_rows": unresolved,
        "result": "composed-strict-package",
    }
    return package, audit


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("season")
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        package, audit = compose(args.season)
        for path, value in ((args.output_package, package), (args.output_audit, audit)):
            path.parent.mkdir(parents=True, exist_ok=True)
            pipeline.write_canonical_json(path, value)
    except (OSError, package_v2.PackageValidationError, pipeline.PipelineError, registry.RegistryError, CompositionError) as exc:
        print(f"quality package composition error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"season": args.season, "changes": audit["changes"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
