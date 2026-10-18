#!/usr/bin/env python3
"""Batch exact, eligible mode-1 base-row preserves into one static candidate.

This is the scalable companion to ``reconcile_mode1_roster_base_v1.py``.  It
does not discover players or alter historical source data.  It only restores a
row where the package roster is an exact ordered subsequence of that club's
parser-backed mode-1 base roster, the omitted player has no package identity,
and the complete native DD6360 record can be read back.  Every restored row is
explicitly marked ``preserve-existing-mode1`` and is never a target-season
fact claim.

The input package, registries, manifests, game tree and releases are never
modified.  The output package and audit must be new paths.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import reconcile_mode1_roster_base_v1 as single_v1  # noqa: E402
from scripts import season_package_compiler_v2 as compiler_v2  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-mode1-roster-base-reconciliation-batch-v1"
STATE = "base-roster-batch-reconciled-static-candidate-only"


class BatchReconciliationError(ValueError):
    """The requested batch cannot safely be made."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_new(path: Path, payload: bytes) -> str:
    if path.exists() or path.is_symlink():
        raise BatchReconciliationError(f"refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return _sha256_bytes(payload)


def _candidate_carriers(
    *, package: Mapping[str, Any], base_tree: Path,
    preservation_artifact_id: str, preservation_source_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Return safe candidates and an explicit reason for every skipped mode-1 club."""

    eq_path = base_tree / "DBDAT" / "EQ98030.FDI"
    jug_path = base_tree / "DBDAT" / "JUG98030.FDI"
    if not eq_path.is_file() or not jug_path.is_file():
        raise BatchReconciliationError("verified base is missing required DBDAT/EQ98030.FDI or JUG98030.FDI")
    owners, rosters, modes = compiler_v2._source_roster_owners(eq_path.read_bytes())
    jug_data = jug_path.read_bytes()
    entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(jug_data).entries}
    player_by_id = {str(row["id"]): row for row in package["players"]}
    player_by_carrier = {int(row["carrier_id"]): row for row in package["players"]}
    existing_carriers = {int(row["carrier_id"]) for row in package["players"]}
    existing_person_ids = {
        str(row.get("person_id")) for row in package["players"] if row.get("person_id") is not None
    }
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    claimed_by: dict[int, list[int]] = defaultdict(list)

    for club in sorted(package["clubs"], key=lambda row: int(row["carrier_id"])):
        club_carrier = int(club["carrier_id"])
        if modes.get(club_carrier) != 1:
            continue
        baseline = rosters.get(club_carrier)
        if not baseline:
            skipped.append({"club_carrier_id": club_carrier, "reason": "no-parser-backed-base-roster"})
            continue
        try:
            requested = [int(player_by_id[str(player_id)]["carrier_id"])
                         for player_id in club["roster_player_ids"]]
        except KeyError as exc:
            skipped.append({"club_carrier_id": club_carrier,
                            "reason": f"unknown-package-player:{exc.args[0]}"})
            continue
        missing = [carrier for carrier in baseline if carrier not in requested]
        extra = [carrier for carrier in requested if carrier not in baseline]
        if not missing:
            skipped.append({"club_carrier_id": club_carrier, "reason": "already-has-full-base-roster"})
            continue
        if extra or requested != [carrier for carrier in baseline if carrier not in missing]:
            skipped.append({"club_carrier_id": club_carrier,
                            "reason": "roster-is-not-exact-ordered-base-subsequence"})
            continue
        shared_preserves: list[int] = []
        conflict: list[int] = []
        for carrier in missing:
            player = player_by_carrier.get(carrier)
            if player is None and f"person-{carrier}" not in existing_person_ids:
                continue
            base_owner_set = {
                owner for owner in owners.get(carrier, []) if modes.get(owner) == 1
            }
            current_owner_set = {
                int(existing_club["carrier_id"])
                for existing_club in package["clubs"]
                if f"player-{carrier}" in existing_club["roster_player_ids"]
            }
            if (
                player is not None
                and player.get("id") == f"player-{carrier}"
                and player.get("person_id") == f"person-{carrier}"
                and player.get("policy") == "preserve-existing-mode1"
                and base_owner_set == current_owner_set | {club_carrier}
                and club_carrier in base_owner_set
            ):
                shared_preserves.append(carrier)
            else:
                conflict.append(carrier)
        if conflict:
            skipped.append({"club_carrier_id": club_carrier,
                            "reason": "base-player-identity-already-declared",
                            "player_carrier_ids": conflict})
            continue
        try:
            for carrier in missing:
                entry = entries.get(carrier)
                if entry is None:
                    raise BatchReconciliationError(f"base-player-{carrier}-absent-from-jug")
                single_v1._preserved_player(
                    payload=entry.decode_payload(jug_data),
                    player_carrier=carrier,
                    club_id=str(club["id"]),
                    artifact_id=preservation_artifact_id,
                    source_id=preservation_source_id,
                )
        except (BatchReconciliationError, single_v1.ReconciliationError) as exc:
            skipped.append({"club_carrier_id": club_carrier, "reason": f"unsupported-whole-row-preserve:{exc}"})
            continue
        candidates.append({
            "club_carrier_id": club_carrier,
            "club_id": str(club["id"]),
            "base_roster_player_carrier_ids": list(baseline),
            "input_roster_player_carrier_ids": requested,
            "missing_player_carrier_ids": missing,
            "shared_preserve_player_carrier_ids": shared_preserves,
        })
        for carrier in missing:
            if carrier in shared_preserves:
                continue
            claimed_by[carrier].append(club_carrier)

    # Keep the shared-row audit defined even when this batch has no newly
    # duplicated base carriers.  Preview packages with many whole-record
    # preserves legitimately take this branch.
    shared_new: dict[int, set[int]] = {}
    duplicated = {carrier: clubs for carrier, clubs in claimed_by.items() if len(clubs) > 1}
    if duplicated:
        candidate_by_club = {int(row["club_carrier_id"]): row for row in candidates}
        rejected_clubs: set[int] = set()
        for carrier, clubs in duplicated.items():
            owners_for_carrier = {
                owner for owner in owners.get(carrier, []) if modes.get(owner) == 1
            }
            if set(clubs) == owners_for_carrier and all(club in candidate_by_club for club in owners_for_carrier):
                shared_new[carrier] = owners_for_carrier
                continue
            rejected_clubs.update(clubs)
        for carrier, owner_set in shared_new.items():
            for owner in owner_set:
                candidate_by_club[owner].setdefault("shared_new_player_carrier_ids", []).append(carrier)
        candidates = [row for row in candidates if int(row["club_carrier_id"]) not in rejected_clubs]
        for club_carrier in sorted(rejected_clubs):
            shared = sorted(carrier for carrier, clubs in duplicated.items() if club_carrier in clubs)
            skipped.append({"club_carrier_id": club_carrier,
                            "reason": "base-player-row-shared-by-multiple-batch-clubs",
                            "player_carrier_ids": shared})

    summary = {
        "selected_mode1_club_count": sum(1 for club in package["clubs"]
                                           if modes.get(int(club["carrier_id"])) == 1),
        "eligible_club_count": len(candidates),
        "eligible_player_row_count": sum(
            len(row["missing_player_carrier_ids"]) - len(row["shared_preserve_player_carrier_ids"])
            - len(row.get("shared_new_player_carrier_ids", []))
            for row in candidates
        ) + len(shared_new),
        "shared_preserved_player_row_count": sum(
            len(row["shared_preserve_player_carrier_ids"]) for row in candidates
        ),
        "shared_new_player_row_count": len(shared_new),
        "skipped_club_count": len(skipped),
        "skipped_reason_counts": dict(sorted(Counter(row["reason"] for row in skipped).items())),
    }
    return candidates, sorted(skipped, key=lambda row: int(row["club_carrier_id"])), summary


def reconcile_batch(
    *, package_path: Path, base_tree: Path, verified_base_path: Path,
    preservation_artifact_id: str, preservation_source_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    descriptor = single_v1._read_descriptor(verified_base_path)
    single_v1.pipeline_v2.verify_base_tree(tree=base_tree, verified_base=descriptor)
    if preservation_artifact_id not in single_v1._artifact_ids(package):
        raise BatchReconciliationError(f"preservation artifact is absent from package: {preservation_artifact_id}")
    if preservation_source_id not in single_v1._source_ids(package):
        raise BatchReconciliationError(f"preservation source is absent from package: {preservation_source_id}")

    plans, skipped, summary = _candidate_carriers(
        package=package,
        base_tree=base_tree,
        preservation_artifact_id=preservation_artifact_id,
        preservation_source_id=preservation_source_id,
    )
    if not plans:
        raise BatchReconciliationError("no mode-1 clubs were eligible for whole-row base preservation")

    eq_path = base_tree / "DBDAT" / "EQ98030.FDI"
    jug_path = base_tree / "DBDAT" / "JUG98030.FDI"
    base_owners, base_rosters, base_modes = compiler_v2._source_roster_owners(eq_path.read_bytes())
    jug_data = jug_path.read_bytes()
    entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(jug_data).entries}
    result = copy.deepcopy(package)
    clubs_by_carrier = {int(row["carrier_id"]): row for row in result["clubs"]}
    restored_players: list[dict[str, Any]] = []
    shared_new_players: dict[int, dict[str, Any]] = {}
    reconciliations: list[dict[str, Any]] = []
    for plan in plans:
        club_carrier = int(plan["club_carrier_id"])
        club = clubs_by_carrier[club_carrier]
        baseline = list(base_rosters[club_carrier])
        if base_modes.get(club_carrier) != 1 or baseline != plan["base_roster_player_carrier_ids"]:
            raise BatchReconciliationError(f"base roster changed during batch selection for club carrier {club_carrier}")
        requested = list(plan["input_roster_player_carrier_ids"])
        missing = list(plan["missing_player_carrier_ids"])
        shared_preserves = set(plan["shared_preserve_player_carrier_ids"])
        shared_new = set(plan.get("shared_new_player_carrier_ids", []))
        requested_by_carrier = dict(zip(requested, club["roster_player_ids"], strict=True))
        restored_by_carrier: dict[int, dict[str, Any]] = {}
        restored_audit_rows: list[dict[str, Any]] = []
        for player_carrier in missing:
            if player_carrier in shared_preserves:
                player = next((row for row in result["players"] if int(row["carrier_id"]) == player_carrier), None)
                if player is None or player.get("policy") != "preserve-existing-mode1":
                    raise BatchReconciliationError(
                        f"shared preserved base player carrier {player_carrier} changed during batch"
                    )
                restored_by_carrier[player_carrier] = player
                restored_audit_rows.append({
                    "player_id": player["id"],
                    "carrier_id": player_carrier,
                    "person_id": player["person_id"],
                    "name": player["name"],
                    "whole_record_policy": "already-preserved-shared-base-row",
                    "portrait_status": "unresolved",
                })
                continue
            if player_carrier in shared_new and player_carrier in shared_new_players:
                player = shared_new_players[player_carrier]
                restored_by_carrier[player_carrier] = player
                restored_audit_rows.append({
                    "player_id": player["id"],
                    "carrier_id": player_carrier,
                    "person_id": player["person_id"],
                    "name": player["name"],
                    "whole_record_policy": "new-shared-base-row-owned-by-another-base-club",
                    "portrait_status": "unresolved",
                })
                continue
            entry = entries.get(player_carrier)
            if entry is None:
                raise BatchReconciliationError(f"base player carrier {player_carrier} disappeared during batch")
            payload = entry.decode_payload(jug_data)
            player = single_v1._preserved_player(
                payload=payload,
                player_carrier=player_carrier,
                club_id=str(club["id"]),
                artifact_id=preservation_artifact_id,
                source_id=preservation_source_id,
            )
            restored_by_carrier[player_carrier] = player
            restored_players.append(player)
            if player_carrier in shared_new:
                shared_new_players[player_carrier] = player
            restored_audit_rows.append({
                "player_id": player["id"],
                "carrier_id": player_carrier,
                "person_id": player["person_id"],
                "name": player["name"],
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
                "whole_record_policy": player["policy"],
                "portrait_status": "unresolved",
            })
        club["roster_player_ids"] = [
            restored_by_carrier[carrier]["id"] if carrier in restored_by_carrier else requested_by_carrier[carrier]
            for carrier in baseline
        ]
        for player_carrier in shared_preserves:
            player_id = f"player-{player_carrier}"
            expected_owners = {
                owner for owner in base_owners.get(player_carrier, []) if base_modes.get(owner) == 1
            }
            for owner in expected_owners:
                owner_club = clubs_by_carrier.get(owner)
                if owner_club is None or player_id not in owner_club["roster_player_ids"]:
                    raise BatchReconciliationError(
                        f"shared preserved player {player_carrier} does not have its complete base owner graph"
                    )
                owner_club["shared_preserve_player_ids"] = sorted(set(
                    owner_club.get("shared_preserve_player_ids") or []
                ) | {player_id})
        reconciliations.append({
            "club_carrier_id": club_carrier,
            "club_id": club["id"],
            "base_roster_player_carrier_ids": baseline,
            "input_roster_player_carrier_ids": requested,
            "restored_players": restored_audit_rows,
            "output_roster_player_carrier_ids": baseline,
        })
    result["players"].extend(restored_players)
    result["players"].sort(key=lambda row: str(row["id"]))
    result["assets"]["portraits"].extend({
        "player_id": player["id"],
        "proof": {"artifact_id": preservation_artifact_id, "grade": "static-contract"},
        "review_reason": "restored fixed base roster row is whole-record preserve-only; no dated portrait claim",
        "status": "unresolved",
    } for player in restored_players)
    result["assets"]["portraits"].sort(key=lambda row: str(row["player_id"]))
    for player_carrier, player in shared_new_players.items():
        player_id = player["id"]
        expected_owners = {
            owner for owner in base_owners.get(player_carrier, []) if base_modes.get(owner) == 1
        }
        for owner in expected_owners:
            owner_club = clubs_by_carrier.get(owner)
            if owner_club is None or player_id not in owner_club["roster_player_ids"]:
                raise BatchReconciliationError(
                    f"new shared preserved player {player_carrier} does not have its complete base owner graph"
                )
            owner_club["shared_preserve_player_ids"] = sorted(set(
                owner_club.get("shared_preserve_player_ids") or []
            ) | {player_id})
    package_v2.validate_package(result, strict=True)

    audit = {
        "schema_version": SCHEMA,
        "state": STATE,
        "season": result["season"],
        "release_eligible": False,
        "input": {
            "package_sha256": package_v2.sha256_file(package_path),
            "verified_base_sha256": package_v2.sha256_file(verified_base_path),
            "base_inventory_fingerprint": descriptor["inventory"]["files_fingerprint"],
            "base_eq98030_sha256": hashlib.sha256((base_tree / "DBDAT" / "EQ98030.FDI").read_bytes()).hexdigest(),
            "base_jug98030_sha256": hashlib.sha256((base_tree / "DBDAT" / "JUG98030.FDI").read_bytes()).hexdigest(),
        },
        "batch": {
            "selection_policy": "all-eligible-mode1-whole-row-preserve-only",
            **summary,
            "skipped": skipped,
        },
        "reconciliations": reconciliations,
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
    return result, audit


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--preservation-artifact-id", required=True)
    parser.add_argument("--preservation-source-id", required=True)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_package.resolve() == args.output_audit.resolve():
        print("mode-1 roster batch reconciliation error: output package and audit must differ", file=sys.stderr)
        return 2
    if args.output_package.exists() or args.output_audit.exists():
        existing = args.output_package if args.output_package.exists() else args.output_audit
        print(f"mode-1 roster batch reconciliation error: refusing to replace existing output: {existing.resolve()}", file=sys.stderr)
        return 2
    try:
        output, audit = reconcile_batch(
            package_path=args.package.resolve(),
            base_tree=args.base_tree.resolve(),
            verified_base_path=args.verified_base.resolve(),
            preservation_artifact_id=args.preservation_artifact_id,
            preservation_source_id=args.preservation_source_id,
        )
        package_sha256 = _write_new(args.output_package.resolve(), _canonical_bytes(output))
        audit["output"] = {"package_path": str(args.output_package), "package_sha256": package_sha256}
        _write_new(args.output_audit.resolve(), _canonical_bytes(audit))
    except (
        BatchReconciliationError,
        single_v1.ReconciliationError,
        package_v2.PackageValidationError,
        OSError,
        ValueError,
    ) as exc:
        print(f"mode-1 roster batch reconciliation error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "eligible_club_count": audit["batch"]["eligible_club_count"],
        "output_audit": str(args.output_audit),
        "output_package_sha256": package_sha256,
        "restored_player_row_count": audit["batch"]["eligible_player_row_count"],
        "state": STATE,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
