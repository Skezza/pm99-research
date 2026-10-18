#!/usr/bin/env python3
"""Restore exact omitted fixed mode-1 base rows as whole-record preserves.

This is a deliberately narrow static-candidate repair.  It accepts a strict
Season Package V2 package only when one selected mode-1 club has one or more
missing base roster carriers, no extra carrier, and all remaining rows retain
the parser-backed base order.  Each restored player is *not* a target-season
source claim: it is a whole-record byte-preserve declaration with an
unresolved portrait outcome.

The command never modifies its input package, source intake, registry,
manifest, game tree, or release.  Both outputs must be new paths.
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
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.editor_actions import _native_dd6360_role_start, _read_native_dd6360_fields  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import season_package_compiler_v2 as compiler_v2  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402


SCHEMA = "pm99-mode1-roster-base-reconciliation-v1"
STATE = "base-roster-reconciled-static-candidate-only"
PRESERVE = {"policy": "preserve-existing-mode1"}


class ReconciliationError(ValueError):
    """The requested reconciliation is not an exact base-row restoration."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_descriptor(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReconciliationError(f"cannot read verified base descriptor: {path}: {exc}") from exc
    if not isinstance(value, dict) or _canonical_bytes(value) != path.read_bytes():
        raise ReconciliationError(f"verified base descriptor is not canonical JSON: {path}")
    return pipeline_v2.validate_verified_base_descriptor(value)


def _source_ids(package: Mapping[str, Any]) -> set[str]:
    rows = package.get("sources")
    if not isinstance(rows, list):
        return set()
    return {str(row.get("id")) for row in rows if isinstance(row, Mapping)}


def _artifact_ids(package: Mapping[str, Any]) -> set[str]:
    rows = package.get("artifacts")
    if not isinstance(rows, list):
        return set()
    return {str(row.get("id")) for row in rows if isinstance(row, Mapping)}


def _player_family(payload: bytes, *, player_carrier: int) -> str:
    signature = payload[2:5]
    if signature == b"\xdd\x63\x60":
        return "dd6360"
    if signature == b"\xdd\x63\x61":
        return "dd6361"
    raise ReconciliationError(
        f"missing base player carrier {player_carrier} has unsupported payload family {signature.hex()}"
    )


def _dd6360_ratings(payload: bytes, *, player_carrier: int) -> dict[str, int]:
    try:
        semantic = _read_native_dd6360_fields(payload, _native_dd6360_role_start(payload))
    except Exception as exc:
        raise ReconciliationError(
            f"missing base player carrier {player_carrier} has no parser-backed dd6360 readback"
        ) from exc
    values = dict(zip(compiler_v2.SKILLS, semantic["skills"], strict=True))
    values["handling"] = int(semantic["handling"])
    if set(values) != set(compiler_v2.DD6360_VISIBLE_SKILLS) or any(
        not isinstance(value, int) or not 0 <= value <= 99 for value in values.values()
    ):
        raise ReconciliationError(
            f"missing base player carrier {player_carrier} has invalid visible-skill readback"
        )
    return {
        "quality": values["quality"],
        "speed": values["speed"],
        "stamina": values["stamina"],
        "aggression": values["aggression"],
        "passing": values["passing"],
        "tackling": values["tackling"],
        "heading": values["heading"],
        "shooting": values["shooting"],
        "dribbling": values["dribbling"],
        "handling": values["handling"],
    }


def _preserved_player(
    *, payload: bytes, player_carrier: int, club_id: str,
    artifact_id: str, source_id: str,
) -> dict[str, Any]:
    family = _player_family(payload, player_carrier=player_carrier)
    if family != "dd6360":
        raise ReconciliationError(
            f"missing base player carrier {player_carrier} uses {family}; this reconciler supports only dd6360 preserves"
        )
    try:
        name = compiler_v2._player_name(payload, record_id=player_carrier)
    except compiler_v2.SeasonCompilerError as exc:
        raise ReconciliationError(str(exc)) from exc
    return {
        "carrier_family": family,
        "carrier_id": player_carrier,
        "club_id": club_id,
        "facts": {
            "birth_date": copy.deepcopy(PRESERVE),
            "fine_roles": copy.deepcopy(PRESERVE),
            "height_cm": copy.deepcopy(PRESERVE),
            "nationality": copy.deepcopy(PRESERVE),
            "primary_position": copy.deepcopy(PRESERVE),
            "shirt_number": copy.deepcopy(PRESERVE),
            "weight_kg": copy.deepcopy(PRESERVE),
        },
        "id": f"player-{player_carrier}",
        "name": name,
        "person_id": f"person-{player_carrier}",
        "policy": "preserve-existing-mode1",
        "proof": {"artifact_id": artifact_id, "grade": "static-contract"},
        "ratings": {
            "profile": "pm99-visible-skills-v1",
            "provenance": {
                "method": "preserved-baseline-readback",
                "proof_grade": "static-contract",
                "source_ids": [source_id],
            },
            "values": _dd6360_ratings(payload, player_carrier=player_carrier),
        },
    }


def reconcile_package(
    *, package_path: Path, base_tree: Path, verified_base_path: Path,
    club_carrier: int, preservation_artifact_id: str, preservation_source_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a strict package with exact missing base roster rows restored."""

    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    base = _read_descriptor(verified_base_path)
    pipeline_v2.verify_base_tree(tree=base_tree, verified_base=base)
    if preservation_artifact_id not in _artifact_ids(package):
        raise ReconciliationError(f"preservation artifact is absent from package: {preservation_artifact_id}")
    if preservation_source_id not in _source_ids(package):
        raise ReconciliationError(f"preservation source is absent from package: {preservation_source_id}")

    eq_path = base_tree / "DBDAT" / "EQ98030.FDI"
    jug_path = base_tree / "DBDAT" / "JUG98030.FDI"
    if not eq_path.is_file() or not jug_path.is_file():
        raise ReconciliationError("verified base is missing required DBDAT/EQ98030.FDI or JUG98030.FDI")
    _owners, base_rosters, base_modes = compiler_v2._source_roster_owners(eq_path.read_bytes())
    if base_modes.get(club_carrier) != 1:
        raise ReconciliationError(f"club carrier {club_carrier} is not mode 1 in the verified base")
    baseline = base_rosters.get(club_carrier)
    if not baseline:
        raise ReconciliationError(f"club carrier {club_carrier} has no parser-backed base roster")

    output = copy.deepcopy(package)
    clubs = [row for row in output["clubs"] if int(row["carrier_id"]) == club_carrier]
    if len(clubs) != 1:
        raise ReconciliationError(f"package must select exactly one club carrier {club_carrier}")
    club = clubs[0]
    player_by_id = {str(row["id"]): row for row in output["players"]}
    requested_ids = [str(value) for value in club["roster_player_ids"]]
    try:
        requested = [int(player_by_id[player_id]["carrier_id"]) for player_id in requested_ids]
    except KeyError as exc:
        raise ReconciliationError(
            f"club carrier {club_carrier} names an unknown package player {exc.args[0]!r}"
        ) from exc
    if len(requested) != len(set(requested)):
        raise ReconciliationError(f"club carrier {club_carrier} roster has duplicate player carriers")

    missing = [carrier for carrier in baseline if carrier not in requested]
    extra = [carrier for carrier in requested if carrier not in baseline]
    if not missing or extra or requested != [carrier for carrier in baseline if carrier not in missing]:
        raise ReconciliationError(
            f"club carrier {club_carrier} does not contain exact base-row omissions; "
            f"missing={missing}, extra={extra}"
        )
    existing_carriers = {int(row["carrier_id"]) for row in output["players"]}
    existing_person_ids = {
        str(row.get("person_id")) for row in output["players"] if row.get("person_id") is not None
    }
    for missing_carrier in missing:
        new_player_id = f"player-{missing_carrier}"
        if missing_carrier in existing_carriers or new_player_id in player_by_id:
            raise ReconciliationError(
                f"missing base player carrier {missing_carrier} already has a package declaration"
            )
        if f"person-{missing_carrier}" in existing_person_ids:
            raise ReconciliationError(f"preserved person ID already exists: person-{missing_carrier}")

    jug_data = jug_path.read_bytes()
    entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(jug_data).entries}
    restored_players: list[dict[str, Any]] = []
    restored_by_carrier: dict[int, dict[str, Any]] = {}
    for missing_carrier in missing:
        entry = entries.get(missing_carrier)
        if entry is None:
            raise ReconciliationError(
                f"missing base player carrier {missing_carrier} is absent from JUG98030.FDI"
            )
        payload = entry.decode_payload(jug_data)
        player = _preserved_player(
            payload=payload,
            player_carrier=missing_carrier,
            club_id=str(club["id"]),
            artifact_id=preservation_artifact_id,
            source_id=preservation_source_id,
        )
        restored_players.append({
            "player_id": player["id"],
            "carrier_id": missing_carrier,
            "person_id": player["person_id"],
            "name": player["name"],
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "whole_record_policy": player["policy"],
            "portrait_status": "unresolved",
        })
        restored_by_carrier[missing_carrier] = player

    requested_by_carrier = dict(zip(requested, requested_ids, strict=True))
    club["roster_player_ids"] = [
        restored_by_carrier[carrier]["id"] if carrier in restored_by_carrier else requested_by_carrier[carrier]
        for carrier in baseline
    ]
    output["players"].extend(restored_by_carrier.values())
    output["players"].sort(key=lambda row: str(row["id"]))
    output["assets"]["portraits"].extend({
        "player_id": player["id"],
        "proof": {"artifact_id": preservation_artifact_id, "grade": "static-contract"},
        "review_reason": "restored fixed base roster row is whole-record preserve-only; no dated portrait claim",
        "status": "unresolved",
    } for player in restored_by_carrier.values())
    output["assets"]["portraits"].sort(key=lambda row: str(row["player_id"]))
    package_v2.validate_package(output, strict=True)

    audit = {
        "schema_version": SCHEMA,
        "state": STATE,
        "season": output["season"],
        "release_eligible": False,
        "input": {
            "package_sha256": package_v2.sha256_file(package_path),
            "verified_base_sha256": package_v2.sha256_file(verified_base_path),
            "base_inventory_fingerprint": base["inventory"]["files_fingerprint"],
            "base_eq98030_sha256": hashlib.sha256(eq_path.read_bytes()).hexdigest(),
            "base_jug98030_sha256": hashlib.sha256(jug_data).hexdigest(),
        },
        "reconciliation": {
            "club_carrier_id": club_carrier,
            "club_id": club["id"],
            "base_roster_player_carrier_ids": baseline,
            "input_roster_player_carrier_ids": requested,
            "restored_players": restored_players,
            "output_roster_player_carrier_ids": list(baseline),
        },
        "not_performed": [
            "source acquisition",
            "source manifest change",
            "binary compiler materialisation",
            "clean static audit",
            "release manifest generation",
            "PM99 runtime validation",
            "target-season runtime screenshot",
        ],
    }
    return output, audit


def _write_new(path: Path, payload: bytes) -> str:
    if path.exists():
        raise ReconciliationError(f"refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--club-carrier", required=True, type=int)
    parser.add_argument("--preservation-artifact-id", required=True)
    parser.add_argument("--preservation-source-id", required=True)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_package.resolve() == args.output_audit.resolve():
        print("mode-1 roster reconciliation error: output package and audit must differ", file=sys.stderr)
        return 2
    if args.output_package.exists() or args.output_audit.exists():
        existing = args.output_package if args.output_package.exists() else args.output_audit
        print(f"mode-1 roster reconciliation error: refusing to replace existing output: {existing.resolve()}", file=sys.stderr)
        return 2
    try:
        output, audit = reconcile_package(
            package_path=args.package.resolve(),
            base_tree=args.base_tree.resolve(),
            verified_base_path=args.verified_base.resolve(),
            club_carrier=args.club_carrier,
            preservation_artifact_id=args.preservation_artifact_id,
            preservation_source_id=args.preservation_source_id,
        )
        package_sha256 = _write_new(args.output_package.resolve(), _canonical_bytes(output))
        audit["output"] = {"package_path": str(args.output_package), "package_sha256": package_sha256}
        _write_new(args.output_audit.resolve(), _canonical_bytes(audit))
    except (
        ReconciliationError,
        package_v2.PackageValidationError,
        pipeline_v2.PipelineError,
        OSError,
        ValueError,
    ) as exc:
        print(f"mode-1 roster reconciliation error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "club_carrier": args.club_carrier,
        "output_audit": str(args.output_audit),
        "output_package_sha256": package_sha256,
        "state": STATE,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
