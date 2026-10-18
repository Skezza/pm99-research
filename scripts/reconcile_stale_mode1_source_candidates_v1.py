#!/usr/bin/env python3
"""Clear provably stale source identities from fixed mode-1 package slots.

Some replayed source packages retain a legacy ``person-N`` record carrying an
old source display name while a new ``person-source-*`` record is the only
current sourced claimant for that exact name/birth-date candidate.  This
command replaces only the stale record with its parser-read native whole-row
fallback.  It does not decide between two current source claims; those remain
explicit strict-package blockers for club/transfer evidence.

Inputs remain untouched and outputs must be new.  This is a static authoring
repair, not a release or gameplay assertion.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import reconcile_mode1_roster_base_v1 as base_rows  # noqa: E402
from scripts import season_package_compiler_v2 as compiler_v2  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402


SCHEMA = "pm99-stale-mode1-source-candidate-reconciliation-v1"
STATE = "stale-mode1-source-candidates-reconciled-static-candidate-only"
PRESERVATION_ARTIFACT_ID = "world-mode1-runtime-contract"
PRESERVATION_SOURCE_ID = "baseline-runtime-contract"


class StaleCandidateReconciliationError(ValueError):
    """The package has no safe stale source-candidate repairs."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_verified_base(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StaleCandidateReconciliationError(f"cannot read verified base descriptor: {path}: {exc}") from exc
    if not isinstance(value, dict) or raw != _canonical_bytes(value):
        raise StaleCandidateReconciliationError(f"verified base descriptor is not canonical JSON: {path}")
    return pipeline_v2.validate_verified_base_descriptor(value)


def _duplicate_candidates(package: dict[str, Any]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for player in package["players"]:
        key = package_v2._person_candidate_key(player)
        if key is not None:
            groups[key].append(player)
    return {key: rows for key, rows in groups.items() if len(rows) > 1}


def reconcile_stale_candidates(
    *, package_path: Path, base_tree: Path, verified_base_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=False)
    base = _read_verified_base(verified_base_path)
    pipeline_v2.verify_base_tree(tree=base_tree, verified_base=base)
    if PRESERVATION_ARTIFACT_ID not in base_rows._artifact_ids(package):
        raise StaleCandidateReconciliationError(
            f"preservation artifact is absent from package: {PRESERVATION_ARTIFACT_ID}"
        )
    if PRESERVATION_SOURCE_ID not in base_rows._source_ids(package):
        raise StaleCandidateReconciliationError(
            f"preservation source is absent from package: {PRESERVATION_SOURCE_ID}"
        )
    eq_path = base_tree / "DBDAT" / "EQ98030.FDI"
    jug_path = base_tree / "DBDAT" / "JUG98030.FDI"
    _owners, _rosters, modes = compiler_v2._source_roster_owners(eq_path.read_bytes())
    jug_data = jug_path.read_bytes()
    entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(jug_data).entries}
    output = copy.deepcopy(package)
    players_by_id = {str(player["id"]): player for player in output["players"]}
    clubs_by_id = {str(club["id"]): club for club in output["clubs"]}
    repaired: list[dict[str, Any]] = []

    for key, rows in sorted(_duplicate_candidates(output).items()):
        current = [row for row in rows if str(row.get("person_id") or "").startswith("person-source-")]
        stale = [row for row in rows if not str(row.get("person_id") or "").startswith("person-source-")]
        if len(rows) != 2 or len(current) != 1 or len(stale) != 1:
            continue
        stale_player = stale[0]
        club = clubs_by_id.get(str(stale_player["club_id"]))
        if club is None or modes.get(int(club["carrier_id"])) != 1:
            continue
        player_id = str(stale_player["id"])
        if player_id not in club["roster_player_ids"]:
            raise StaleCandidateReconciliationError(
                f"stale player {player_id} is not in its declared mode-1 club roster"
            )
        carrier = int(stale_player["carrier_id"])
        entry = entries.get(carrier)
        if entry is None:
            raise StaleCandidateReconciliationError(f"stale player carrier {carrier} is absent from base JUG")
        payload = entry.decode_payload(jug_data)
        fallback = base_rows._preserved_player(
            payload=payload,
            player_carrier=carrier,
            club_id=str(club["id"]),
            artifact_id=PRESERVATION_ARTIFACT_ID,
            source_id=PRESERVATION_SOURCE_ID,
        )
        if fallback["id"] != player_id:
            raise StaleCandidateReconciliationError(f"base fallback ID changed for stale player {player_id}")
        players_by_id[player_id] = fallback
        repaired.append({
            "candidate": {"normalised_name": key[0], "birth_date": key[1]},
            "current_source_player_id": current[0]["id"],
            "current_source_person_id": current[0]["person_id"],
            "stale_player_id": player_id,
            "stale_person_id": stale_player.get("person_id"),
            "carrier_id": carrier,
            "club_id": club["id"],
            "restored_native_name": fallback["name"],
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
        })
    if not repaired:
        raise StaleCandidateReconciliationError("no exact one-current/one-stale mode-1 candidate pairs were found")

    output["players"] = sorted(players_by_id.values(), key=lambda row: str(row["id"]))
    repaired_ids = {row["stale_player_id"] for row in repaired}
    portraits: list[dict[str, Any]] = []
    for portrait in output["assets"]["portraits"]:
        if portrait["player_id"] not in repaired_ids:
            portraits.append(portrait)
            continue
        portraits.append({
            "player_id": portrait["player_id"],
            "proof": {"artifact_id": PRESERVATION_ARTIFACT_ID, "grade": "static-contract"},
            "review_reason": "stale legacy source candidate replaced by parser-read native whole-row fallback",
            "status": "unresolved",
        })
    output["assets"]["portraits"] = sorted(portraits, key=lambda row: str(row["player_id"]))
    package_v2.validate_package(output, strict=False)
    remaining = _duplicate_candidates(output)
    audit = {
        "schema_version": SCHEMA,
        "state": STATE,
        "season": output["season"],
        "release_eligible": False,
        "input": {
            "package_sha256": _sha256(package_path),
            "verified_base_sha256": _sha256(verified_base_path),
            "base_inventory_fingerprint": base["inventory"]["files_fingerprint"],
            "base_eq98030_sha256": hashlib.sha256(eq_path.read_bytes()).hexdigest(),
            "base_jug98030_sha256": hashlib.sha256(jug_data).hexdigest(),
        },
        "reconciliation": {
            "policy": "replace-only-exact-one-current-source-versus-one-legacy-non-source-mode1-candidate",
            "repaired_pair_count": len(repaired),
            "repaired": repaired,
            "remaining_duplicate_candidate_group_count": len(remaining),
            "remaining_current_source_duplicate_group_count": sum(
                all(str(player.get("person_id") or "").startswith("person-source-") for player in rows)
                for rows in remaining.values()
            ),
        },
        "not_performed": [
            "source acquisition",
            "source manifest change",
            "club-identity decision between current source claims",
            "binary compiler materialisation",
            "clean static audit",
            "release manifest generation",
            "PM99 runtime validation",
            "target-season runtime screenshot",
        ],
    }
    return output, audit


def _write_new(path: Path, value: Any) -> str:
    if path.exists() or path.is_symlink():
        raise StaleCandidateReconciliationError(f"refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_bytes(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_package.resolve() == args.output_audit.resolve():
        print("stale candidate reconciliation error: output package and audit must differ", file=sys.stderr)
        return 2
    if args.output_package.exists() or args.output_audit.exists():
        existing = args.output_package if args.output_package.exists() else args.output_audit
        print(f"stale candidate reconciliation error: refusing to replace existing output: {existing.resolve()}", file=sys.stderr)
        return 2
    try:
        output, audit = reconcile_stale_candidates(
            package_path=args.package.resolve(),
            base_tree=args.base_tree.resolve(),
            verified_base_path=args.verified_base.resolve(),
        )
        output_sha256 = _write_new(args.output_package.resolve(), output)
        audit["output"] = {"package_path": str(args.output_package), "package_sha256": output_sha256}
        _write_new(args.output_audit.resolve(), audit)
    except (
        StaleCandidateReconciliationError,
        base_rows.ReconciliationError,
        package_v2.PackageValidationError,
        pipeline_v2.PipelineError,
        OSError,
        ValueError,
    ) as exc:
        print(f"stale candidate reconciliation error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "repaired_pair_count": audit["reconciliation"]["repaired_pair_count"],
        "remaining_duplicate_candidate_group_count": audit["reconciliation"]["remaining_duplicate_candidate_group_count"],
        "output_package_sha256": output_sha256,
        "state": STATE,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
