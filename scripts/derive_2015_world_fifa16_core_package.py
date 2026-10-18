#!/usr/bin/env python3
"""Derive a runnable, deliberately partial mode-1 core package from FIFA drafts.

This converts only the review-prefilled *blocked* fixed-carrier rows into the
narrow runtime-proven foreign write surface: player name, nationality, date of
birth, height/weight and nine core skills.  It preserves every mode-1 roster
row, manager carrier, manager surname, club metadata, kit, portrait, broad
position, fine role, shirt number and opening tactical state from the supplied
base tree.  It does not make a historical claim for those preserved lanes.

The result is useful for incremental runtime QA of the actual writer.  It is
not a complete world 2015/16 release: its scope says so, its assets remain
unresolved, and it must never be promoted over the sourced world ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.editor_actions import (  # noqa: E402
    _native_dd6360_role_start,
    _patch_indexed_player_variable_name_payload,
    _read_native_dd6360_fields,
)
from app.ent_manager_profiles import parse_indexed_ent_manager_profile  # noqa: E402
from app.eq_jug_linked import parse_eq_external_team_roster_payload  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.models import PlayerRecord  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import world_fixed_carrier_ledger_v2 as ledger  # noqa: E402


REPORT_SCHEMA = "pm99-world-fifa16-core-package-report-v1"
PLAYER_FAMILY = "dd6360"
POSITION = {0: "G", 1: "D", 2: "M", 3: "F"}


class WorldCorePackageError(ValueError):
    """A blocked draft cannot be represented by the current core writer."""


def canonical_json_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def sha256_file(path: Path) -> str:
    return package_v2.sha256_file(path)


def _pm99_text(value: str) -> str:
    """Apply PM99's documented CP1252 transliteration boundary once."""

    substitutions = str.maketrans({
        "Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ø": "O", "ø": "o",
        "Þ": "Th", "þ": "th", "Æ": "AE", "æ": "ae", "Ð": "D", "ð": "d", "İ": "I", "ı": "i",
    })
    text = unicodedata.normalize("NFKD", str(value).translate(substitutions))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = " ".join(text.split())
    if not text:
        raise WorldCorePackageError("cannot transliterate an empty PM99 string")
    try:
        text.encode("cp1252")
    except UnicodeEncodeError as exc:
        raise WorldCorePackageError(f"cannot represent source name in PM99 CP1252: {value!r}") from exc
    return text


def _read_canonical(path: Path, *, label: str) -> dict[str, Any]:
    value, _ = ledger.read_canonical_json(path, label=label)
    return value


def _manager_surnames(ent_path: Path) -> dict[int, str]:
    data = ent_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(data)
    result: dict[int, str] = {}
    for entry in indexed.entries:
        try:
            profile = parse_indexed_ent_manager_profile(
                data[entry.payload_offset : entry.payload_offset + entry.payload_length], record_id=int(entry.record_id)
            )
        except Exception:
            continue
        surname = " ".join(str(profile.surname or "").split())
        if surname:
            result[int(entry.record_id)] = surname
    return result


def _base_player_fields(jug_path: Path) -> dict[int, dict[str, Any]]:
    data = jug_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(data)
    result: dict[int, dict[str, Any]] = {}
    for entry in indexed.entries:
        decoded = entry.decode_payload(data)
        if decoded[2:5] != b"\xdd\x63\x60":
            continue
        try:
            fields = _read_native_dd6360_fields(decoded, int(_native_dd6360_role_start(decoded)))
        except Exception:
            continue
        roles = [int(value) for value in fields["fine_role_codes"] if int(value) != 98]
        visible_position = int(fields["visible_position_code"])
        position = POSITION.get(visible_position)
        if position is None or not roles or any(not 0 <= role <= 17 for role in roles):
            continue
        result[int(entry.record_id)] = {
            "primary_position": position,
            # These values are copied to declare the compact carrier's
            # unchanged tactical candidate set. They are not inferred as an
            # ordered primary/secondary position list.
            "fine_roles": roles,
            # Foreign shirt-number storage is not proven; zero is the explicit
            # preserve-only value expected by the native core compiler.
            "shirt_number": 0,
            "decoded_payload": decoded,
        }
    return result


def _assert_fixed_mode1_rosters_match_registry(*, eq_path: Path, registry: Mapping[str, Any]) -> None:
    """Require every foreign linked-roster tail to be unchanged before build.

    The incremental package only changes shared JUG facts.  It is never
    allowed to piggy-back on a materialisation which has consumed, reordered
    or relinked foreign roster rows for an English or other lane.  Checking
    every registered mode-1 carrier here keeps that composition condition
    before package emission, rather than discovering it after a partial
    compiler transaction.
    """

    data = eq_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(data)
    entries = {int(entry.record_id): entry for entry in indexed.entries}
    changed: list[int] = []
    for carrier in registry["carriers"]:
        carrier_id = int(carrier["carrier_id"])
        entry = entries.get(carrier_id)
        if entry is None:
            changed.append(carrier_id)
            continue
        raw = data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        parsed = parse_eq_external_team_roster_payload(raw, {})
        expected = [
            (int(slot["flag"]), int(slot["player_carrier_id"]))
            for slot in carrier["roster_slots"]
        ]
        actual = [] if parsed is None else [
            (int(row.flag), int(row.player_record_id)) for row in parsed.rows
        ]
        if actual != expected:
            changed.append(carrier_id)
    if changed:
        preview = ", ".join(str(carrier_id) for carrier_id in changed[:20])
        suffix = "" if len(changed) <= 20 else f" (+{len(changed) - 20} more)"
        raise WorldCorePackageError(
            "base tree does not preserve all fixed foreign mode-1 roster tails; "
            f"changed carrier ids: {preview}{suffix}"
        )


def _prune_unselected_mode1_owner_conflicts(
    *,
    registry: Mapping[str, Any],
    accepted: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Reject candidates which would require a foreign donor roster rewrite.

    Some old JUG rows occur in multiple mode-1 linked rosters.  The native
    compiler used to remove a selected JUG from every unselected owner, which
    makes a core-fields package silently mutate another foreign club.  Fixed
    rows take precedence: iteratively remove any candidate whose selected
    player also has an unselected mode-1 owner.  The fixed point is stable and
    independent of the original input order.
    """

    owners: dict[int, set[int]] = {}
    for carrier in registry["carriers"]:
        carrier_id = int(carrier["carrier_id"])
        for slot in carrier["roster_slots"]:
            owners.setdefault(int(slot["player_carrier_id"]), set()).add(carrier_id)

    remaining = list(accepted)
    removed: list[dict[str, Any]] = []
    while remaining:
        selected = {int(update["carrier_id"]) for update in remaining}
        unsafe: dict[int, list[dict[str, int]]] = {}
        for update in remaining:
            carrier_id = int(update["carrier_id"])
            conflicts = [
                {"player_carrier_id": player_id, "unselected_owner_carrier_id": owner}
                for player_id in sorted(int(row["player_carrier_id"]) for row in update["players"])
                for owner in sorted(owners.get(player_id, set()))
                if owner != carrier_id and owner not in selected
            ]
            if conflicts:
                unsafe[carrier_id] = conflicts
        if not unsafe:
            break
        remaining = [update for update in remaining if int(update["carrier_id"]) not in unsafe]
        removed.extend(
            {
                "carrier_id": carrier_id,
                "reason": "selected-player-has-unselected-mode1-roster-owner",
                "conflicts": conflicts,
            }
            for carrier_id, conflicts in sorted(unsafe.items())
        )
    return remaining, removed


def _artifact(identity: str, kind: str, path: Path) -> dict[str, str]:
    return {
        "id": identity,
        "kind": kind,
        "sha256": sha256_file(path),
        "relative_path": f"inputs/{path.name}",
    }


def _native_name_rewrite_is_safe(payload: bytes, target_name: str) -> bool:
    """Exercise the same parser-backed variable-name transaction as compile."""

    try:
        current_name = str(PlayerRecord.from_bytes(payload, 0).name or "").strip()
        if not current_name:
            return False
        _patch_indexed_player_variable_name_payload(payload, current_name, target_name)
    except Exception:
        return False
    return True


def _pm99_safe_display_name(payload: bytes, source_name: str) -> str | None:
    """Select a variable-length semantic display alias that fits this carrier.

    The fixed roster carrier may have a shorter native-name payload than a
    modern full legal name. This is not fixed-field truncation: every
    candidate is passed through the variable-name transaction and retains a
    recognisable source identity (full name, then ``A. Surname``, then surname).
    The resulting alias is recorded in the package report for review.
    """

    full = _pm99_text(source_name)
    candidates = [full]
    tokens = full.split()
    if len(tokens) >= 2 and tokens[0]:
        candidates.append(f"{tokens[0][0]}. {tokens[-1]}")
    if tokens:
        candidates.append(tokens[-1])
    for candidate in dict.fromkeys(candidates):
        if _native_name_rewrite_is_safe(payload, candidate):
            return candidate
    return None


def build_core_package(
    *,
    registry: Mapping[str, Any],
    blocked_ledger: Mapping[str, Any],
    base_tree: Path,
    blocked_ledger_sha256: str,
    registry_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive strict V2 metadata for the currently compilable mode-1 lanes."""

    ledger.validate_registry(registry)
    ledger.validate_ledger(registry=registry, ledger=blocked_ledger)
    base_tree = base_tree.resolve()
    dbdat = base_tree / "DBDAT"
    required = {
        "jug": dbdat / "JUG98030.FDI",
        "eq": dbdat / "EQ98030.FDI",
        "ent": dbdat / "ENT98030.FDI",
        "minifoto": dbdat / "MINIFOTO.PKF",
        "miniesc": dbdat / "MINIESC.PKF",
        "managpre": base_tree / "MANAGPRE.EXE",
    }
    missing = [str(path) for path in required.values() if not path.is_file() or path.is_symlink()]
    if missing:
        raise WorldCorePackageError("missing safe base-tree files: " + ", ".join(missing))
    _assert_fixed_mode1_rosters_match_registry(eq_path=required["eq"], registry=registry)
    base_players = _base_player_fields(required["jug"])
    manager_surnames = _manager_surnames(required["ent"])
    registry_by_carrier = {int(row["carrier_id"]): row for row in registry["carriers"]}

    accepted: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    used_manager_carriers: set[int] = set()
    candidate_signatures: set[tuple[str, str, str]] = set()
    for update in blocked_ledger["carrier_updates"]:
        carrier_id = int(update["carrier_id"])
        if update["status"] != "blocked":
            excluded.append({"carrier_id": carrier_id, "reason": "not-a-blocked-fifa-prefill-row"})
            continue
        carrier = registry_by_carrier[carrier_id]
        slots = carrier["roster_slots"]
        players = update["players"]
        if len(players) != len(slots) or len(players) < 16:
            excluded.append({"carrier_id": carrier_id, "reason": "incomplete-or-undersized-fixed-roster"})
            continue
        manager_carrier = int(update["manager"]["carrier_id"])
        if manager_carrier in used_manager_carriers or manager_carrier not in manager_surnames:
            excluded.append({"carrier_id": carrier_id, "reason": "unavailable-or-shared-baseline-manager-carrier"})
            continue
        player_carriers = [int(row["player_carrier_id"]) for row in players]
        if any(slot["family"] != PLAYER_FAMILY for slot in slots) or any(player_id not in base_players for player_id in player_carriers):
            excluded.append({"carrier_id": carrier_id, "reason": "mode1-player-not-proven-dd6360-core-family"})
            continue
        safe_names = {
            int(row["player_carrier_id"]): _pm99_safe_display_name(
                bytes(base_players[int(row["player_carrier_id"])]["decoded_payload"]), str(row["name"])
            )
            for row in players
        }
        if any(value is None for value in safe_names.values()):
            excluded.append({"carrier_id": carrier_id, "reason": "variable-name-exceeds-proven-native-window"})
            continue
        signatures = {
            (str(row["name"]).casefold(), str(row["facts"]["birth_date"]), str(row["facts"]["nationality"]))
            for row in players
        }
        if len(signatures) != len(players) or signatures & candidate_signatures:
            excluded.append({"carrier_id": carrier_id, "reason": "ambiguous-same-person-candidate"})
            continue
        accepted_update = dict(update)
        accepted_update["_core_pm99_names"] = {str(key): str(value) for key, value in safe_names.items()}
        accepted.append(accepted_update)
        used_manager_carriers.add(manager_carrier)
        candidate_signatures.update(signatures)

    accepted, topology_excluded = _prune_unselected_mode1_owner_conflicts(
        registry=registry, accepted=accepted
    )
    excluded.extend(topology_excluded)

    artifacts = [
        {"id": "world-fifa16-prefill-ledger", "kind": "season-input", "sha256": blocked_ledger_sha256,
         "relative_path": "season/world-2015-16-fifa16-prefill-ledger.json"},
        {"id": "world-fixed-carrier-registry", "kind": "season-input", "sha256": registry_sha256,
         "relative_path": "season/world-fixed-carriers.json"},
        _artifact("base-file-jug98030-fdi", "base-file", required["jug"]),
        _artifact("base-file-eq98030-fdi", "base-file", required["eq"]),
        _artifact("base-file-ent98030-fdi", "base-file", required["ent"]),
        _artifact("base-file-minifoto-pkf", "base-file", required["minifoto"]),
        _artifact("base-file-miniesc-pkf", "base-file", required["miniesc"]),
        _artifact("calendar-existing-base-managpre-exe", "calendar-patch", required["managpre"]),
    ]
    artifacts.sort(key=lambda row: row["id"])
    common_fifa_proof = {"grade": "source-receipt", "artifact_id": "world-fifa16-prefill-ledger"}
    common_contract_proof = {"grade": "static-contract", "artifact_id": "world-fixed-carrier-registry"}

    clubs: list[dict[str, Any]] = []
    managers: list[dict[str, Any]] = []
    package_players: list[dict[str, Any]] = []
    kits: list[dict[str, Any]] = []
    portraits: list[dict[str, Any]] = []
    name_transliterations: list[dict[str, Any]] = []
    for update in accepted:
        carrier_id = int(update["carrier_id"])
        club_id = f"club-carrier-{carrier_id}"
        manager_carrier = int(update["manager"]["carrier_id"])
        manager_id = f"manager-carrier-{manager_carrier}"
        manager_name = manager_surnames[manager_carrier]
        managers.append({
            "id": manager_id,
            "person_id": f"baseline-manager-carrier-{manager_carrier}",
            "carrier_id": manager_carrier,
            "name": manager_name,
            "proof": common_contract_proof,
        })
        roster_ids: list[str] = []
        for row in update["players"]:
            player_carrier = int(row["player_carrier_id"])
            player_id = f"player-carrier-{player_carrier}"
            roster_ids.append(player_id)
            facts = dict(row["facts"])
            facts.update({key: value for key, value in base_players[player_carrier].items() if key != "decoded_payload"})
            source_name = str(row["name"])
            pm99_name = str(update["_core_pm99_names"][str(player_carrier)])
            if pm99_name != source_name:
                name_transliterations.append({
                    "carrier_id": player_carrier,
                    "fifa_player_id": str(row["person_id"]),
                    "source_name": source_name,
                    "pm99_name": pm99_name,
                })
            # Handling is carried in portable data but its dd6360 mode-1 byte
            # is intentionally not written by the compiler.
            package_players.append({
                "id": player_id,
                "person_id": str(row["person_id"]),
                "carrier_id": player_carrier,
                "carrier_family": PLAYER_FAMILY,
                "club_id": club_id,
                "name": pm99_name,
                "facts": facts,
                "ratings": {
                    "profile": "pm99-visible-skills-v1",
                    "values": dict(row["ratings"]),
                    "provenance": {
                        "method": "FIFA 16 snapshot mapped to current mode-1 core write lanes; handling and roles remain preserved",
                        "proof_grade": "source-receipt",
                        "source_ids": ["fifa16-player-snapshot"],
                    },
                },
                "proof": common_fifa_proof,
            })
            portraits.append({
                "player_id": player_id,
                "status": "unresolved",
                "review_reason": "No approved era-correct portrait capture is included in the core-only incremental package.",
                "proof": common_contract_proof,
            })
        baseline_club = registry_by_carrier[carrier_id]["baseline_club"]
        clubs.append({
            "id": club_id,
            "identity_id": f"draft-carrier-{carrier_id}",
            "carrier_id": carrier_id,
            # FIFA supplies the short club identity; preserve unsupported club
            # fields from the base instead of writing a false 2015 ground.
            "name": str(update["club"]["name"]),
            "full_name": str(baseline_club["full_name"] or update["club"]["full_name"]),
            "division": "Foreign carrier (membership preserved)",
            "ground_name": str(baseline_club["ground_name"]),
            "seated_capacity": int(baseline_club["seated_capacity"]),
            "manager_id": manager_id,
            "roster_player_ids": roster_ids,
            # These mandatory V2 fields are metadata placeholders only. The
            # compiler's mode-1 route never writes them and records that fact
            # in its receipt; do not treat them as historical opening data.
            "opening": {
                "fixture_date": "2015-08-08",
                "starting_xi_player_ids": roster_ids[:11],
                "substitute_player_ids": roster_ids[11:16],
                "formation": "4-4-2",
                "tactics_positions": [[128, 55, 128, 55] for _ in range(11)],
                "proof": common_contract_proof,
            },
            "proof": common_fifa_proof,
        })
        kits.append({
            "club_id": club_id,
            "artifact_ids": ["base-file-miniesc-pkf"],
            "proof": common_contract_proof,
        })

    package = {
        "schema_version": package_v2.SCHEMA_VERSION,
        "package_id": "pm99-2015-16-world-fifa16-core-incremental",
        "season": {"start_year": 2015, "end_year": 2016, "label": "2015/16"},
        "scope": {
            "id": "foreign-fixed-carrier-fifa16-core-incremental",
            "title": "2015/16 foreign fixed-carrier FIFA 16 core-fields incremental QA package",
            "countries": ["XXX"],
            "competition_policy": "existing-carriers-only",
        },
        "artifacts": artifacts,
        "sources": [{
            "id": "fifa16-player-snapshot",
            "title": "FIFA 16 snapshot routed through the hash-locked world prefill ledger",
            "proof_grade": "source-receipt",
            "evidence_artifact_id": "world-fifa16-prefill-ledger",
        }],
        "clubs": sorted(clubs, key=lambda row: row["id"]),
        "players": sorted(package_players, key=lambda row: row["id"]),
        "managers": sorted(managers, key=lambda row: row["id"]),
        "assets": {
            "kits": sorted(kits, key=lambda row: row["club_id"]),
            "portraits": sorted(portraits, key=lambda row: row["player_id"]),
        },
        "calendar": {
            "base_year": 1998,
            "target_year": 2015,
            "target_rollover_year": 2016,
            "patch_artifact_id": "calendar-existing-base-managpre-exe",
            "proof": common_contract_proof,
        },
        "proofs": [
            {"id": "proof-fifa16-source", "grade": "source-receipt", "artifact_id": "world-fifa16-prefill-ledger",
             "covers": ["candidate-player-facts", "candidate-player-ratings"]},
            {"id": "proof-fixed-mode1-core", "grade": "static-contract", "artifact_id": "world-fixed-carrier-registry",
             "covers": ["fixed-roster-order", "mode1-core-write-boundary"]},
        ],
        "migration": {"status": "native-v2", "source_artifact_ids": ["world-fifa16-prefill-ledger", "world-fixed-carrier-registry"], "known_gaps": []},
    }
    try:
        package_v2.validate_package(package, strict=True)
    except package_v2.PackageValidationError as exc:
        raise WorldCorePackageError(f"derived core package is invalid: {exc}") from exc
    report = {
        "schema_version": REPORT_SCHEMA,
        "result": "strict-runnable-core-package-created",
        "package_id": package["package_id"],
        "coverage": {
            "blocked_prefill_carrier_count": len(blocked_ledger["carrier_updates"]),
            "runnable_core_carrier_count": len(clubs),
            "runnable_core_player_count": len(package_players),
            "excluded_prefill_carrier_count": len(excluded),
        },
        "included_carrier_ids": [int(row["carrier_id"]) for row in accepted],
        "excluded_carriers_by_reason": dict(sorted(Counter(row["reason"] for row in excluded).items())),
        "excluded_carriers": excluded,
        "name_transliterations": name_transliterations,
        "actual_write_surface": [
            "mode-1 dd6360 player name",
            "mode-1 dd6360 nationality, date of birth, height, weight and nine core skills",
            "existing mode-1 EQ strings/capacity/final manager link rewritten to preserved values only",
        ],
        "preserved_not_historical_in_this_package": [
            "club grounds, capacities, manager identities, foreign membership, kits, portraits, handling",
            "primary/fine roles, shirt numbers, opening XI, opening tactics and finance",
        ],
    }
    return package, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--blocked-ledger", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-report", required=True, type=Path)
    args = parser.parse_args(argv)
    registry, registry_sha = ledger.read_canonical_json(args.registry, label="fixed-carrier registry")
    blocked_ledger, blocked_sha = ledger.read_canonical_json(args.blocked_ledger, label="FIFA16 prefill ledger")
    package, report = build_core_package(
        registry=registry,
        blocked_ledger=blocked_ledger,
        base_tree=args.base_tree,
        blocked_ledger_sha256=blocked_sha,
        registry_sha256=registry_sha,
    )
    package_v2.write_canonical_package(args.output_package, package)
    args.output_report.parent.mkdir(parents=True, exist_ok=True)
    args.output_report.write_bytes(canonical_json_bytes(report))
    print(json.dumps({"package": str(args.output_package), "report": str(args.output_report), **report["coverage"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
