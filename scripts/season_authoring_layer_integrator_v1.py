#!/usr/bin/env python3
"""Join season-neutral authoring evidence into a Season Package V2 draft.

This is an offline join, not a source-discovery or database-build stage.  It
binds opening XIs, opening-date managers, deterministic ratings and rendered
kit receipts to the fixed carrier allocation used by the source-package
builder.  Missing evidence is reported as a hard blocker and the input draft
is never promoted to a release package.

Formation is the one permitted inference: when a reconciled XI has no
published formation, the broad source positions deterministically form the
defender-midfielder-forward bands.  Secondary player-fact fallbacks already
logged by the source-package builder remain non-blocking.  Players without a
historical portrait are explicitly declared ``native-no-photo``.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import materialise_opening_manager_ledger_v1 as manager_v1  # noqa: E402
from scripts import reconcile_transfermarkt_opening_lineups_v1 as opening_v1  # noqa: E402
from scripts import season_carrier_allocation_v1 as allocation_v1  # noqa: E402
from scripts import season_editorial_ratings_v1 as ratings_v1  # noqa: E402
from scripts import season_kit_catalogue_v1 as kits_v1  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-season-authoring-layer-integration-audit-v1"
KIT_BINDING_SCHEMA = "pm99-season-kit-render-bindings-v1"
FORMATION_POLICY = "published-opening-xi-formation-else-deterministic-position-inference"
PORTRAIT_POLICY = "native-no-photo-when-no-historical-portrait-is-supplied"


class LayerIntegrationError(ValueError):
    """An authoring input is malformed, stale or ambiguous."""


def _bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_bytes(dict(value))).hexdigest()


def _normalise(value: object) -> str:
    return "".join(char.casefold() for char in str(value or "") if char.isalnum())


def _selector(row: Mapping[str, Any]) -> tuple[str, str, str]:
    value = row.get("source_selector", row)
    if not isinstance(value, Mapping):
        raise LayerIntegrationError("source selector must be an object")
    result = tuple(str(value.get(key) or "").strip() for key in (
        "country_catalog", "competition_catalog", "club_name"
    ))
    if not all(result):
        raise LayerIntegrationError("source selector is incomplete")
    return result  # type: ignore[return-value]


def _allocation_index(document: Mapping[str, Any]) -> dict[tuple[str, str, str], int]:
    if document.get("schema_version") != allocation_v1.SCHEMA:
        raise LayerIntegrationError(f"carrier allocation must use {allocation_v1.SCHEMA}")
    result: dict[tuple[str, str, str], int] = {}
    carriers: set[int] = set()
    for row in document.get("assignments", []):
        if not isinstance(row, Mapping) or not isinstance(row.get("source_selector"), Mapping):
            raise LayerIntegrationError("carrier allocation has a malformed assignment")
        selector = dict(row["source_selector"])
        selector["club_name"] = row.get("club_name")
        key = _selector(selector)
        carrier = row.get("carrier_id")
        if not isinstance(carrier, int) or key in result or carrier in carriers:
            raise LayerIntegrationError("carrier allocation selectors and carrier IDs must be unique")
        result[key] = carrier
        carriers.add(carrier)
    return result


def _input_artifact(package: dict[str, Any], *, identity: str, digest: str) -> dict[str, str]:
    artifact = {"id": identity, "kind": "season-input", "sha256": digest}
    existing = next((row for row in package["artifacts"] if row["id"] == identity), None)
    if existing is not None and existing != artifact:
        raise LayerIntegrationError(f"artifact ID collision for {identity}")
    package["artifacts"] = sorted(
        [row for row in package["artifacts"] if row["id"] != identity] + [artifact],
        key=lambda row: str(row["id"]),
    )
    return {"grade": "source-captured", "artifact_id": identity}


def _source(package: dict[str, Any], *, identity: str, title: str, artifact_id: str,
            grade: str = "source-captured") -> None:
    row = {"id": identity, "title": title, "proof_grade": grade, "evidence_artifact_id": artifact_id}
    existing = next((item for item in package["sources"] if item["id"] == identity), None)
    if existing is not None and existing != row:
        raise LayerIntegrationError(f"source ID collision for {identity}")
    package["sources"] = sorted(
        [item for item in package["sources"] if item["id"] != identity] + [row],
        key=lambda item: str(item["id"]),
    )


def _manager_person_id(row: Mapping[str, Any]) -> str:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), Mapping) else {}
    claim = {
        "name": str(row.get("manager_name") or ""),
        "fixture_date": str(row.get("opening_fixture_date") or ""),
        "source_url": str(evidence.get("source_url") or ""),
    }
    return "person-manager-" + hashlib.sha256(_bytes(claim)).hexdigest()


def _formation_from_xi(xi: Sequence[Mapping[str, Any]]) -> str:
    positions = Counter(str(row.get("source_position") or "").upper() for row in xi)
    if positions["G"] != 1 or sum(positions[key] for key in ("D", "M", "F")) != 10:
        raise LayerIntegrationError("formation inference needs one G and ten D/M/F source positions")
    bands = [positions[key] for key in ("D", "M", "F") if positions[key]]
    if len(bands) < 2 or any(not 1 <= count <= 5 for count in bands):
        raise LayerIntegrationError("inferred formation cannot be represented by the PM99 formation contract")
    return "-".join(str(count) for count in bands)


def _formation_bands(value: object) -> tuple[int, ...]:
    text = str(value or "").strip()
    if not re.fullmatch(r"[1-5](?:-[0-5]){1,4}", text):
        raise LayerIntegrationError(f"unsupported formation {value!r}")
    bands = tuple(int(part) for part in text.split("-") if int(part))
    if sum(bands) != 10 or len(bands) not in {2, 3, 4, 5}:
        raise LayerIntegrationError(f"formation must describe ten outfield players: {value!r}")
    return bands


def _tactics_positions(formation: str, xi: Sequence[Mapping[str, Any]]) -> list[list[int]]:
    """Return deterministic PM99-native static bands in source XI order."""
    bands = _formation_bands(formation)
    depths = {2: (135, 400), 3: (135, 270, 400), 4: (130, 210, 280, 400),
              5: (125, 195, 270, 330, 405)}[len(bands)]
    if len(xi) != 11:
        raise LayerIntegrationError("tactics placement needs exactly eleven source players")
    goalkeeper_indexes = [index for index, row in enumerate(xi) if str(row.get("source_position") or "").upper() == "G"]
    if len(goalkeeper_indexes) != 1:
        raise LayerIntegrationError("tactics placement needs exactly one source goalkeeper")
    outfield_indexes = [index for index in range(11) if index not in goalkeeper_indexes]
    positions: list[list[int] | None] = [None] * 11
    positions[goalkeeper_indexes[0]] = [128, 55, 128, 55]
    cursor = 0
    for count, depth in zip(bands, depths, strict=True):
        lanes = [round(20 + offset * 188 / (count - 1)) if count > 1 else 128 for offset in range(count)]
        for index, lane in zip(outfield_indexes[cursor:cursor + count], lanes, strict=True):
            positions[index] = [lane, depth, lane, depth]
        cursor += count
    if any(row is None for row in positions):
        raise LayerIntegrationError("formation bands do not cover the ten outfield players")
    return [row for row in positions if row is not None]


def _kit_bindings(document: Mapping[str, Any] | None, *, catalogue_sha256: str) -> dict[int, list[dict[str, Any]]]:
    if document is None:
        return {}
    if document.get("schema_version") != KIT_BINDING_SCHEMA:
        raise LayerIntegrationError(f"kit bindings must use {KIT_BINDING_SCHEMA}")
    if document.get("kit_catalogue_sha256") != catalogue_sha256:
        raise LayerIntegrationError("kit render bindings target a different kit catalogue")
    result: dict[int, list[dict[str, Any]]] = {}
    for row in document.get("clubs", []):
        if not isinstance(row, Mapping) or not isinstance(row.get("carrier_id"), int):
            raise LayerIntegrationError("kit render binding has a malformed club")
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise LayerIntegrationError("kit render binding needs at least one artifact")
        checked: list[dict[str, Any]] = []
        for artifact in artifacts:
            if not isinstance(artifact, Mapping) or artifact.get("kind") != "kit-render":
                raise LayerIntegrationError("kit binding artifacts must be kit-render records")
            if not package_v2.ID_RE.fullmatch(str(artifact.get("id") or "")) or not package_v2.SHA256_RE.fullmatch(str(artifact.get("sha256") or "")):
                raise LayerIntegrationError("kit binding artifact needs a stable ID and SHA-256")
            checked.append(dict(artifact))
        carrier = int(row["carrier_id"])
        if carrier in result:
            raise LayerIntegrationError("kit render bindings duplicate a carrier")
        result[carrier] = checked
    return result


def integrate(
    *, draft_package: Mapping[str, Any], carrier_allocation: Mapping[str, Any],
    manager_ledger: Mapping[str, Any], opening_reconciliation: Mapping[str, Any],
    kit_catalogue: Mapping[str, Any], rating_output: Mapping[str, Any],
    kit_render_bindings: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an evidence-enriched package draft and an exact blocker audit."""
    package = copy.deepcopy(dict(draft_package))
    package_v2.validate_package(package, strict=True)
    if manager_ledger.get("schema_version") != manager_v1.OUTPUT_SCHEMA:
        raise LayerIntegrationError("unsupported manager ledger")
    if opening_reconciliation.get("schema_version") != opening_v1.SCHEMA:
        raise LayerIntegrationError("unsupported opening reconciliation")
    if kit_catalogue.get("schema_version") != kits_v1.SCHEMA:
        raise LayerIntegrationError("unsupported kit catalogue")
    if rating_output.get("schema_version") != ratings_v1.OUTPUT_SCHEMA:
        raise LayerIntegrationError("unsupported editorial rating output")

    allocation = _allocation_index(carrier_allocation)
    clubs_by_carrier = {int(row["carrier_id"]): row for row in package["clubs"]}
    if not set(allocation.values()) <= set(clubs_by_carrier):
        raise LayerIntegrationError("carrier allocation references a club absent from the draft package")
    season_start = package["season"]["start_year"]
    allocation_season = carrier_allocation.get("season")
    if isinstance(allocation_season, Mapping) and allocation_season.get("label") != package["season"]["label"]:
        raise LayerIntegrationError("carrier allocation season differs from package")
    if manager_ledger.get("season_start_year") != season_start:
        raise LayerIntegrationError("manager ledger season differs from package")
    kit_season = kit_catalogue.get("season")
    if isinstance(kit_season, Mapping) and kit_season.get("label") != package["season"]["label"]:
        raise LayerIntegrationError("kit catalogue season differs from package")
    snapshot_date = rating_output.get("snapshot_date")
    if isinstance(snapshot_date, str) and not snapshot_date.startswith(f"{season_start:04d}-"):
        raise LayerIntegrationError("editorial rating snapshot is outside the package start year")

    suffix = f"{season_start}-{str(package['season']['end_year'])[-2:]}"
    digests = {
        "manager": _digest(manager_ledger), "opening": _digest(opening_reconciliation),
        "kit": _digest(kit_catalogue), "ratings": _digest(rating_output),
        "portrait": hashlib.sha256(_bytes({"policy": PORTRAIT_POLICY})).hexdigest(),
    }
    proofs: dict[str, dict[str, str]] = {}
    for layer, digest in digests.items():
        artifact_id = f"authoring-{layer}-{suffix}"
        proofs[layer] = _input_artifact(package, identity=artifact_id, digest=digest)
        grade = ("reviewed-editorial" if layer == "ratings" else
                 "static-contract" if layer == "portrait" else "source-captured")
        proofs[layer]["grade"] = grade
        _source(package, identity=f"authoring-source-{layer}-{suffix}",
                title=f"{layer.title()} authoring layer for {package['season']['label']}",
                artifact_id=artifact_id, grade=grade)

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    coverage = Counter()
    mapped_carriers = set(allocation.values())

    manager_rows: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for row in manager_ledger.get("managers", []):
        key = _selector(row)
        if key in manager_rows:
            raise LayerIntegrationError("manager ledger duplicates a source selector")
        manager_rows[key] = row
    for selector, carrier in sorted(allocation.items(), key=lambda item: item[1]):
        club = clubs_by_carrier[carrier]
        row = manager_rows.get(selector)
        if row is None:
            blockers.append({"code": "opening-manager-unresolved", "carrier_id": carrier, "club_name": club["name"]})
            continue
        manager = next((item for item in package["managers"] if item["id"] == club["manager_id"]), None)
        if manager is None:
            raise LayerIntegrationError(f"club {club['id']} references an absent manager")
        manager.update({"name": str(row["manager_name"]), "person_id": _manager_person_id(row),
                        "policy": "write", "proof": copy.deepcopy(proofs["manager"])})
        coverage["manager"] += 1

    player_by_id = {str(row["id"]): row for row in package["players"]}
    opening_rows: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for row in opening_reconciliation.get("clubs", []):
        key = _selector(row)
        if key in opening_rows:
            raise LayerIntegrationError("opening reconciliation duplicates a source selector")
        opening_rows[key] = row
    for selector, carrier in sorted(allocation.items(), key=lambda item: item[1]):
        club = clubs_by_carrier[carrier]
        row = opening_rows.get(selector)
        if row is None or not row.get("starting_xi_reconciled"):
            blockers.append({"code": "opening-xi-unresolved", "carrier_id": carrier, "club_name": club["name"]})
            continue
        roster = [player_by_id[player_id] for player_id in club["roster_player_ids"]]
        by_name: dict[str, list[str]] = {}
        for player in roster:
            by_name.setdefault(_normalise(player.get("source_name", player["name"])), []).append(player["id"])
        xi: list[str] = []
        for source_player in row.get("starting_xi", []):
            candidates = by_name.get(_normalise(source_player.get("source_name")), [])
            if len(candidates) != 1:
                xi = []
                break
            xi.append(candidates[0])
        if len(xi) != 11 or len(set(xi)) != 11:
            blockers.append({"code": "opening-xi-package-player-join-unresolved", "carrier_id": carrier, "club_name": club["name"]})
            continue
        formation = row.get("formation")
        method = "published"
        if not formation:
            try:
                formation = _formation_from_xi(row["starting_xi"])
                method = "deterministic-position-inference"
            except LayerIntegrationError as exc:
                blockers.append({"code": "opening-formation-unresolved", "carrier_id": carrier,
                                 "club_name": club["name"], "detail": str(exc)})
                continue
        try:
            tactics = _tactics_positions(str(formation), row["starting_xi"])
        except LayerIntegrationError as exc:
            blockers.append({"code": "opening-formation-unresolved", "carrier_id": carrier,
                             "club_name": club["name"], "detail": str(exc)})
            continue
        club["opening"] = {
            "fixture_date": str(row["first_league_fixture_date"]),
            "starting_xi_player_ids": xi, "substitute_player_ids": [],
            "formation": str(formation), "tactics_positions": tactics,
            "proof": copy.deepcopy(proofs["opening"]),
        }
        coverage["opening"] += 1
        coverage[f"formation-{method}"] += 1

    rating_rows: dict[str, Mapping[str, Any]] = {}
    for row in rating_output.get("player_ratings", []):
        player_id = str(row.get("player_id") or "")
        if not player_id or player_id in rating_rows or player_id not in player_by_id:
            raise LayerIntegrationError("rating output has an unknown, blank or duplicate player ID")
        rating_rows[player_id] = row
    mapped_club_ids = {clubs_by_carrier[carrier]["id"] for carrier in mapped_carriers}
    required_rating_ids = {
        player["id"] for player in package["players"]
        if player["club_id"] in mapped_club_ids
        and str(player.get("person_id", "")).startswith("person-source-")
    }
    rating_source_id = f"authoring-source-ratings-{suffix}"
    for player_id in sorted(required_rating_ids):
        player = player_by_id[player_id]
        row = rating_rows.get(player_id)
        if row is None or row.get("person_id") != player.get("person_id"):
            blockers.append({"code": "player-rating-unresolved", "player_id": player_id})
            continue
        rating = copy.deepcopy(row["ratings"])
        provenance = rating.get("provenance")
        if not isinstance(provenance, Mapping):
            raise LayerIntegrationError(f"rating {player_id} has no provenance")
        rating["provenance"] = {
            "method": str(provenance.get("method") or "deterministic editorial rating model v1"),
            "proof_grade": "reviewed-editorial",
            "source_ids": [rating_source_id],
        }
        player["ratings"] = rating
        coverage["rating"] += 1

    catalogue_by_carrier: dict[int, Mapping[str, Any]] = {}
    for row in kit_catalogue.get("rows", []):
        carrier = row.get("carrier_id")
        if not isinstance(carrier, int) or carrier in catalogue_by_carrier:
            raise LayerIntegrationError("kit catalogue has a malformed or duplicate carrier")
        catalogue_by_carrier[carrier] = row
    bindings = _kit_bindings(kit_render_bindings, catalogue_sha256=digests["kit"])
    kits_by_club = {str(row["club_id"]): row for row in package["assets"]["kits"]}
    for selector, carrier in sorted(allocation.items(), key=lambda item: item[1]):
        club = clubs_by_carrier[carrier]
        row = catalogue_by_carrier.get(carrier)
        if row is None:
            blockers.append({"code": "kit-catalogue-club-unresolved", "carrier_id": carrier, "club_name": club["name"]})
            continue
        status = row.get("status")
        if status == "native-fallback-authorized" and row.get("carrier_status") == "exited":
            kits_by_club[club["id"]] = {"club_id": club["id"], "artifact_ids": [],
                                         "policy": "preserve-existing-mode1", "proof": copy.deepcopy(proofs["kit"])}
            coverage["kit-native-exited"] += 1
        elif status == "source-ready" and carrier in bindings:
            artifacts = bindings[carrier]
            artifact_ids = [str(artifact["id"]) for artifact in artifacts]
            for artifact in artifacts:
                existing = next((item for item in package["artifacts"] if item["id"] == artifact["id"]), None)
                if existing is not None and existing != artifact:
                    raise LayerIntegrationError(f"kit artifact ID collision for {artifact['id']}")
            package["artifacts"] = sorted(
                [item for item in package["artifacts"] if item["id"] not in artifact_ids] + artifacts,
                key=lambda item: str(item["id"]),
            )
            kits_by_club[club["id"]] = {"club_id": club["id"], "artifact_ids": artifact_ids,
                                         "policy": "write", "proof": {"grade": "source-receipt", "artifact_id": artifact_ids[0]}}
            coverage["kit-rendered"] += 1
        elif status == "source-ready":
            blockers.append({"code": "kit-render-artifact-required", "carrier_id": carrier, "club_name": club["name"]})
        else:
            blockers.append({"code": "continuing-club-kit-unresolved", "carrier_id": carrier,
                             "club_name": club["name"], "catalogue_status": status})
    package["assets"]["kits"] = [kits_by_club[club_id] for club_id in sorted(kits_by_club)]

    portraits = {str(row["player_id"]): row for row in package["assets"]["portraits"]}
    for player_id in sorted(required_rating_ids):
        portraits[player_id] = {
            "player_id": player_id, "status": "native-no-photo",
            "review_reason": "No hash-bound target-season portrait was supplied; deliberate no-image fallback.",
            "proof": copy.deepcopy(proofs["portrait"]),
        }
    package["assets"]["portraits"] = [portraits[player_id] for player_id in sorted(portraits)]
    coverage["portrait-native-no-photo"] = len(required_rating_ids)

    for carrier, club in sorted(clubs_by_carrier.items()):
        if carrier not in mapped_carriers and carrier not in allocation_v1.SYSTEM_SELECTION_IDS:
            blockers.append({"code": "carrier-target-season-authoring-unmapped", "carrier_id": carrier,
                             "club_name": club["name"]})
        elif carrier in allocation_v1.SYSTEM_SELECTION_IDS:
            coverage["system-selection-preserved"] += 1
    fallback_count = sum(len(player.get("fact_fallbacks", [])) for player in package["players"])
    if fallback_count:
        warnings.append({"code": "secondary-player-facts-fallback-logged", "count": fallback_count})

    package_v2.validate_package(package, strict=True)
    code_counts = Counter(row["code"] for row in blockers)
    audit = {
        "schema_version": SCHEMA,
        "season": copy.deepcopy(package["season"]),
        "inputs": {
            "draft_package_sha256": _digest(draft_package),
            "carrier_allocation_sha256": _digest(carrier_allocation),
            "manager_ledger_sha256": digests["manager"],
            "opening_reconciliation_sha256": digests["opening"],
            "kit_catalogue_sha256": digests["kit"],
            "rating_output_sha256": digests["ratings"],
            "kit_render_bindings_sha256": _digest(kit_render_bindings) if kit_render_bindings else None,
        },
        "policies": {"formation": FORMATION_POLICY, "portraits": PORTRAIT_POLICY,
                     "managers": "opening-date-source-required-no-native-fallback",
                     "kits": "continuing-source-and-render-required-native-fallback-only-exited",
                     "secondary_player_facts": "logged-fallback-nonblocking"},
        "coverage": dict(sorted(coverage.items())),
        "hard_blocker_counts": dict(sorted(code_counts.items())),
        "hard_blockers": blockers,
        "non_blocking_warnings": warnings,
        "release_eligible": not blockers,
        "integrated_draft_sha256": _digest(package),
    }
    return package, audit


def _read(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise LayerIntegrationError(f"input must be a JSON object: {path}")
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_bytes(dict(value)))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft-package", required=True, type=Path)
    parser.add_argument("--carrier-allocation", required=True, type=Path)
    parser.add_argument("--manager-ledger", required=True, type=Path)
    parser.add_argument("--opening-reconciliation", required=True, type=Path)
    parser.add_argument("--kit-catalogue", required=True, type=Path)
    parser.add_argument("--rating-output", required=True, type=Path)
    parser.add_argument("--kit-render-bindings", type=Path)
    parser.add_argument("--output-draft", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        package, audit = integrate(
            draft_package=_read(args.draft_package), carrier_allocation=_read(args.carrier_allocation),
            manager_ledger=_read(args.manager_ledger), opening_reconciliation=_read(args.opening_reconciliation),
            kit_catalogue=_read(args.kit_catalogue), rating_output=_read(args.rating_output),
            kit_render_bindings=_read(args.kit_render_bindings) if args.kit_render_bindings else None,
        )
        _write(args.output_draft, package)
        _write(args.output_audit, audit)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, LayerIntegrationError,
            package_v2.PackageValidationError) as exc:
        parser.error(str(exc))
    print(json.dumps({"coverage": audit["coverage"], "hard_blocker_counts": audit["hard_blocker_counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
