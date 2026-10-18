#!/usr/bin/env python3
"""Audit whether a PM99 database can safely resolve shared foreign JUG IDs.

This is a read-only release-gate tool.  PM99's mode-1 (foreign) roster graph
contains 36 duplicate compact JUG IDs in the clean database.  A fresh compact
JUG append can be searched but its native profile cannot be opened.  The only
promising replacement is to free an *existing* mode-0 dd6361 ID, append its
dd6361 clone back to its English roster, then reuse the original ID as the
foreign compact player.  The game also requires the compact player's primary
fine role to be present in that original mode-0 carrier's role vector.

This tool deliberately does not choose historical players or silently allocate
carriers.  It reports the exact duplicate slots, every parser-backed eligible
mode-0 source carrier by role, and the role codes that have runtime evidence.
The season compiler must consume an explicit reviewed allocation; a report of
capacity is never release permission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.models import PlayerRecord  # noqa: E402
from scripts.season_package_compiler_v2 import (  # noqa: E402
    SeasonCompilerError,
    _dd6361_fine_roles,
    _native_dd6360_role_start,
    _read_native_dd6360_fields,
    _source_roster_owners,
)


SCHEMA = "pm99-mode1-recycle-capacity-audit-v1"
# These are profile-route controls, not a claim that every role is qualified.
# These are direct foreign-profile recycle controls.  Code 3 is covered by
# the 2026-08-31 provisioned-clone control: an existing mode-0 dd6361 source
# was changed from [4, 5] to [3], cloned to its English row, and a compact
# foreign role-3 donor opened cleanly through the native profile route.  Code
# 12 is covered by the equivalent control using compact donor 35 (native
# primary role 12); the exact RECYCLE STRIKER profile opened without error.
RUNTIME_QUALIFIED_ROLE_CODES = (0, 3, 4, 8, 9, 12)
# Role 3 has no baseline mode-0 dd6361 source in the clean English database,
# but its paired-clone provision route is native-profile proven.  This is not
# an arbitrary fallback: the compiler requires the declared appended clone to
# write the same requested role before the target ID is recycled.
PROVISIONABLE_ROLE_CODES = (3,)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _name(payload: bytes) -> str | None:
    try:
        value = " ".join(str(PlayerRecord.from_bytes(payload, 0).name or "").split())
    except Exception:
        return None
    return value or None


def audit_mode1_recycle_capacity(*, dbdat: Path) -> dict[str, Any]:
    """Return a deterministic, non-mutating mode-1 recycle gate report."""

    dbdat = dbdat.expanduser().resolve()
    eq_path = dbdat / "EQ98030.FDI"
    jug_path = dbdat / "JUG98030.FDI"
    if not eq_path.is_file() or not jug_path.is_file():
        raise ValueError("--dbdat must contain EQ98030.FDI and JUG98030.FDI")
    eq_data = eq_path.read_bytes()
    jug_data = jug_path.read_bytes()
    owners, _rosters, modes = _source_roster_owners(eq_data)
    entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(jug_data).entries}

    eligible_by_role: dict[int, list[dict[str, Any]]] = defaultdict(list)
    rejected_mode0_sources: list[dict[str, Any]] = []
    for player_id, owner_ids in sorted(owners.items()):
        if len(owner_ids) != 1 or modes.get(owner_ids[0]) != 0:
            continue
        entry = entries.get(int(player_id))
        if entry is None:
            rejected_mode0_sources.append({"carrier_id": int(player_id), "reason": "absent-jug-entry"})
            continue
        payload = entry.decode_payload(jug_data)
        if payload[2:5] != b"\xdd\x63\x61":
            continue
        try:
            roles = sorted(_dd6361_fine_roles(payload, carrier=int(player_id)))
        except SeasonCompilerError as exc:
            rejected_mode0_sources.append({"carrier_id": int(player_id), "reason": str(exc)})
            continue
        source = {
            "carrier_id": int(player_id),
            "mode0_team_carrier_id": int(owner_ids[0]),
            "baseline_name": _name(payload),
            "role_candidates": roles,
        }
        for role in roles:
            eligible_by_role[role].append(source)

    duplicate_rows: list[dict[str, Any]] = []
    unsupported_duplicates: list[dict[str, Any]] = []
    baseline_roles = Counter()
    for player_id, owner_ids in sorted(owners.items()):
        if len(owner_ids) < 2 or any(modes.get(owner) != 1 for owner in owner_ids):
            continue
        entry = entries.get(int(player_id))
        if entry is None:
            unsupported_duplicates.append({"carrier_id": int(player_id), "reason": "absent-jug-entry"})
            continue
        payload = entry.decode_payload(jug_data)
        if payload[2:5] != b"\xdd\x63\x60":
            unsupported_duplicates.append({
                "carrier_id": int(player_id), "family": payload[2:5].hex(), "reason": "not-compact-dd6360"
            })
            continue
        try:
            fields = _read_native_dd6360_fields(payload, _native_dd6360_role_start(payload))
            roles = [int(role) for role in fields["fine_role_codes"] if int(role) != 98]
        except Exception as exc:
            unsupported_duplicates.append({"carrier_id": int(player_id), "reason": f"compact-role-read-failed: {exc}"})
            continue
        if not roles or not 0 <= roles[0] <= 17:
            unsupported_duplicates.append({"carrier_id": int(player_id), "reason": "no-supported-primary-fine-role"})
            continue
        baseline_roles.update([roles[0]])
        occurrences = [int(owner) for owner in sorted(owner_ids)]
        duplicate_rows.append({
            "shared_compact_carrier_id": int(player_id),
            "baseline_name": _name(payload),
            "baseline_fine_roles": roles,
            "retained_mode1_team_carrier_id": occurrences[0],
            "recycle_required_for_mode1_team_carrier_ids": occurrences[1:],
        })

    eligible_counts = {str(role): len(eligible_by_role.get(role, [])) for role in range(18)}
    eligible_sources = {
        str(role): sorted(eligible_by_role.get(role, []), key=lambda row: int(row["carrier_id"]))
        for role in range(18)
    }
    unavailable = [role for role, count in ((role, eligible_counts[str(role)]) for role in range(18)) if count == 0]
    unavailable_without_provision = [role for role in unavailable if role not in PROVISIONABLE_ROLE_CODES]
    runtime_unqualified = [role for role in range(18) if role not in RUNTIME_QUALIFIED_ROLE_CODES]
    required_slots = sum(len(row["recycle_required_for_mode1_team_carrier_ids"]) for row in duplicate_rows)
    blockers: list[str] = []
    if unsupported_duplicates:
        blockers.append("foreign duplicate graph contains an unsupported JUG family or unreadable compact role")
    if unavailable_without_provision:
        blockers.append(
            "no parser-backed recyclable mode-0 dd6361 carrier or qualified paired-clone provision route exists for role code(s): "
            + ", ".join(map(str, unavailable_without_provision))
        )
    if runtime_unqualified:
        blockers.append("runtime profile proof is still missing for role code(s): " + ", ".join(map(str, runtime_unqualified)))
    if required_slots != 36:
        blockers.append(f"expected 36 shared foreign extra slots, found {required_slots}")

    return {
        "schema_version": SCHEMA,
        "input": {
            "dbdat": str(dbdat),
            "eq98030_sha256": _sha256(eq_path),
            "jug98030_sha256": _sha256(jug_path),
        },
        "runtime_qualified_primary_fine_role_codes": list(RUNTIME_QUALIFIED_ROLE_CODES),
        "shared_compact_player_count": len(duplicate_rows),
        "recycle_required_slot_count": required_slots,
        "shared_compact_baseline_primary_role_counts": {
            str(role): int(count) for role, count in sorted(baseline_roles.items())
        },
        "eligible_mode0_dd6361_source_count_by_primary_role": eligible_counts,
        "eligible_mode0_dd6361_sources_by_primary_role": eligible_sources,
        "role_codes_without_eligible_mode0_source": unavailable,
        "role_codes_with_qualified_paired_clone_provision_route": list(PROVISIONABLE_ROLE_CODES),
        "role_codes_without_eligible_or_provisioned_mode0_source": unavailable_without_provision,
        "unreadable_or_ineligible_mode0_dd6361_source_count": len(rejected_mode0_sources),
        "duplicate_slots": duplicate_rows,
        "unsupported_duplicate_players": unsupported_duplicates,
        "release_status": "blocked" if blockers else "allocation-review-required",
        "release_blockers": blockers,
        "note": (
            "baseline_fine_roles are diagnostics from the 1998 carrier, not 2015 historical facts. "
            "A release needs an explicit reviewed source player and a compatible mode-0 target for each slot."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit_mode1_recycle_capacity(dbdat=args.dbdat)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "release_status": report["release_status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
