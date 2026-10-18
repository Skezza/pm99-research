#!/usr/bin/env python3
"""Resolve one current-source mode-1 duplicate from bound opening-date evidence.

The selected player must be the sole earliest dated opening-XI claim in the
package-bound opening-squad preallocation.  Every competing package row is
restored from its parser-read native base record.  Inputs are never replaced;
this emits a static-only candidate and audit, not a release or gameplay claim.
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

from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import reconcile_mode1_roster_base_v1 as base_rows  # noqa: E402
from scripts import reconcile_stale_mode1_source_candidates_v1 as stale  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402
from scripts import season_package_compiler_v2 as compiler_v2  # noqa: E402


SCHEMA = "pm99-opening-date-mode1-candidate-reconciliation-v1"
STATE = "opening-date-mode1-candidate-reconciled-static-candidate-only"


class OpeningDateCandidateError(ValueError):
    """The requested duplicate cannot be resolved by the narrow contract."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_canonical(path: Path, *, label: str) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != package_v2.canonical_json_bytes(value):
        raise OpeningDateCandidateError(f"{label} is not canonical JSON: {path}")
    return value


def reconcile(
    *, package_path: Path, opening_evidence_path: Path, candidate_name: str,
    base_tree: Path, verified_base_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=False)
    evidence = _read_canonical(opening_evidence_path, label="opening evidence")
    base = stale._read_verified_base(verified_base_path)
    pipeline_v2.verify_base_tree(tree=base_tree, verified_base=base)

    evidence_hash = _sha256(opening_evidence_path)
    bound = [
        row for row in package["artifacts"]
        if row.get("id") == f"opening-squad-preallocation-{package['season']['start_year']}-{str(package['season']['end_year'])[-2:]}"
    ]
    if len(bound) != 1 or bound[0].get("sha256") != evidence_hash:
        raise OpeningDateCandidateError("opening evidence is not hash-bound by this package")

    duplicates = stale._duplicate_candidates(package)
    matches = [(key, rows) for key, rows in duplicates.items() if key[0] == candidate_name]
    if len(matches) != 1:
        raise OpeningDateCandidateError(f"expected one duplicate group for {candidate_name!r}")
    key, rows = matches[0]
    if len(rows) != 2 or not all(str(row.get("person_id", "")).startswith("person-source-") for row in rows):
        raise OpeningDateCandidateError("candidate must contain exactly two current-source rows")

    claims: list[dict[str, Any]] = []
    for club in evidence.get("source_clubs", []):
        if not isinstance(club, Mapping):
            continue
        fixture_date = club.get("opening_fixture_date")
        for player in club.get("players", []):
            if not isinstance(player, Mapping):
                continue
            facts = player.get("facts")
            if not isinstance(facts, Mapping):
                continue
            probe = {"name": facts.get("name"), "facts": dict(facts)}
            if package_v2._person_candidate_key(probe) != key:
                continue
            row_hash = player.get("source_row_sha256")
            if not isinstance(row_hash, str) or len(row_hash) != 64:
                raise OpeningDateCandidateError("matching evidence row has no SHA-256")
            claims.append({
                "club_name": ((club.get("selector") or {}).get("club_name")),
                "opening_fixture_date": fixture_date,
                "opening_xi_order": player.get("opening_xi_order"),
                "source_row_sha256": row_hash,
            })
    dated_xi = [
        row for row in claims
        if isinstance(row["opening_fixture_date"], str)
        and isinstance(row["opening_xi_order"], int)
        and not isinstance(row["opening_xi_order"], bool)
    ]
    earliest = min((row["opening_fixture_date"] for row in dated_xi), default=None)
    winners = [row for row in dated_xi if row["opening_fixture_date"] == earliest]
    if earliest is None or len(winners) != 1:
        raise OpeningDateCandidateError("opening evidence has no unique earliest dated opening-XI owner")
    winner_claim = winners[0]
    winner_person_id = f"person-source-{winner_claim['source_row_sha256']}"
    winner_rows = [row for row in rows if row.get("person_id") == winner_person_id]
    if len(winner_rows) != 1:
        raise OpeningDateCandidateError("unique evidence winner does not identify exactly one package row")
    winner = winner_rows[0]
    loser = next(row for row in rows if row is not winner)

    clubs = {str(row["id"]): row for row in package["clubs"]}
    loser_club = clubs.get(str(loser["club_id"]))
    if loser_club is None or loser["id"] not in loser_club["roster_player_ids"]:
        raise OpeningDateCandidateError("losing player is not in its declared club roster")
    eq_data = (base_tree / "DBDAT" / "EQ98030.FDI").read_bytes()
    _owners, _rosters, modes = compiler_v2._source_roster_owners(eq_data)
    if modes.get(int(loser_club["carrier_id"])) != 1:
        raise OpeningDateCandidateError("losing player does not belong to a mode-1 club")
    jug_path = base_tree / "DBDAT" / "JUG98030.FDI"
    jug_data = jug_path.read_bytes()
    entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(jug_data).entries}
    carrier = int(loser["carrier_id"])
    if carrier not in entries:
        raise OpeningDateCandidateError("losing player carrier is absent from base JUG")
    payload = entries[carrier].decode_payload(jug_data)
    fallback = base_rows._preserved_player(
        payload=payload, player_carrier=carrier, club_id=str(loser_club["id"]),
        artifact_id=stale.PRESERVATION_ARTIFACT_ID, source_id=stale.PRESERVATION_SOURCE_ID,
    )
    if fallback["id"] != loser["id"]:
        raise OpeningDateCandidateError("native fallback changes the losing package player ID")

    output = copy.deepcopy(package)
    output["players"] = sorted(
        [fallback if row["id"] == loser["id"] else row for row in output["players"]],
        key=lambda row: str(row["id"]),
    )
    output["assets"]["portraits"] = sorted([
        ({
            "player_id": portrait["player_id"],
            "proof": {"artifact_id": stale.PRESERVATION_ARTIFACT_ID, "grade": "static-contract"},
            "review_reason": "non-winning current-source duplicate replaced by parser-read native whole-row fallback",
            "status": "unresolved",
        } if portrait["player_id"] == loser["id"] else portrait)
        for portrait in output["assets"]["portraits"]
    ], key=lambda row: str(row["player_id"]))
    package_v2.validate_package(output, strict=False)
    remaining = stale._duplicate_candidates(output)
    if len(remaining) != len(duplicates) - 1:
        raise OpeningDateCandidateError("repair did not remove exactly one duplicate group")

    audit = {
        "schema_version": SCHEMA,
        "state": STATE,
        "season": output["season"],
        "release_eligible": False,
        "input": {
            "package_sha256": _sha256(package_path),
            "opening_evidence_sha256": evidence_hash,
            "verified_base_sha256": _sha256(verified_base_path),
            "base_inventory_fingerprint": base["inventory"]["files_fingerprint"],
        },
        "reconciliation": {
            "policy": "single-unique-earliest-dated-opening-xi-owner; restore-other-current-source-row-from-native-base",
            "candidate": {"normalised_name": key[0], "birth_date": key[1]},
            "evidence_claims": claims,
            "winner": {
                "player_id": winner["id"], "person_id": winner["person_id"],
                **winner_claim,
            },
            "restored": {
                "player_id": loser["id"], "discarded_person_id": loser["person_id"],
                "carrier_id": carrier, "club_id": loser_club["id"],
                "native_name": fallback["name"], "payload_sha256": hashlib.sha256(payload).hexdigest(),
            },
            "duplicate_candidate_group_count_before": len(duplicates),
            "duplicate_candidate_group_count_after": len(remaining),
        },
        "not_performed": [
            "source acquisition", "source/current manifest change", "binary compiler materialisation",
            "clean static audit", "release manifest generation", "PM99 runtime validation",
            "target-season runtime screenshot",
        ],
    }
    return output, audit


def _write_new(path: Path, value: Any) -> str:
    if path.exists() or path.is_symlink():
        raise OpeningDateCandidateError(f"refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = package_v2.canonical_json_bytes(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--opening-evidence", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        output, audit = reconcile(
            package_path=args.package.resolve(), opening_evidence_path=args.opening_evidence.resolve(),
            candidate_name=args.candidate, base_tree=args.base_tree.resolve(),
            verified_base_path=args.verified_base.resolve(),
        )
        output_hash = _write_new(args.output_package.resolve(), output)
        audit["output"] = {"package_path": str(args.output_package), "package_sha256": output_hash}
        audit_hash = _write_new(args.output_audit.resolve(), audit)
    except (OpeningDateCandidateError, OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "state": STATE, "output_package_sha256": output_hash,
        "output_audit_sha256": audit_hash,
        "remaining_duplicate_candidate_group_count": audit["reconciliation"]["duplicate_candidate_group_count_after"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
