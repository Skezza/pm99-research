#!/usr/bin/env python3
"""Repair the complete 2015/16 club-to-manager graph without player writes.

The first world build reused ENT manager records across the foreign and
English carrier sets.  Renaming a foreign manager could therefore make an
English club display that foreign manager.  This command allocates one safe
ENT record per *sourced club manager*, writes the parser-backed EQ link and
the bounded ENT display name, and leaves all player, kit and calendar bytes
alone.

It is intentionally split into a source plan and a materialisation step.  A
plan is hash-bound to its foreign recipe, English recipe, source allocation
receipt and exact EQ/ENT input bytes.  Applying it refuses a different game.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.ent_manager_profiles import parse_indexed_ent_manager_profile  # noqa: E402
from app.eq_team_manager_links import (  # noqa: E402
    parse_indexed_eq_manager_links,
    patch_indexed_eq_active_manager_id,
)
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.xor import xor_decode, xor_encode  # noqa: E402
from scripts.build_2015_english92_release import _patch_ent_name, _rebuild_indexed  # noqa: E402
from scripts.season_english_mode0_package_adapter_v1 import _manager_candidates  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


SCHEMA = "pm99-world-2015-manager-graph-repair-plan-v1"
ALLOCATION_SCHEMA = "pm99-world-2015-global-manager-allocation-v1"
PACKAGE_SCHEMA = "pm99-season-package-v2"

# Published manager names need a CP1252 display form before PM99 can write
# them.  These entries retain the original exact identity in the allocation
# receipt and make the smallest readable Latinisation at the writer boundary;
# no name is silently stripped or guessed.
PM99_DISPLAY_OVERRIDES = {
    201: "Sinisa Mihajlovic",
    701: "Miodrag Bozovic",
    704: "Zlatomir Zagorcic",
    821: "Darije Kalezic",
    901: "Damir Buric",
    902: "Zoran Mamic",
    1003: "Hamza Hamzaoglu",
    1007: "Mustafa Resit Akcay",
    1008: "Abdullah Avci",
    1009: "Ertugrul Saglam",
    1051: "Michal Probierz",
    1053: "Leszek Ojrzynski",
    1054: "Jerzy Brzeczek",
    1057: "Maciej Skorza",
    1060: "Jacek Zielinski",
    1452: "Zdenek Scasny",
    1458: "Radomir Korytar",
    1502: "Stoycho Stoev",
    1503: "Ermin Šiljak",
    1504: "Ivan Kolev",
    1505: "Hristo Yanev",
    1506: "Laurentiu Reghecampf",
    1654: "Thomas Christiansen",
    1655: "Pedro Emanuel",
    2701: "Vuk Rasovic",
}


class ManagerGraphError(ValueError):
    """The manager graph cannot be planned or materialised safely."""


def _canonical(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ManagerGraphError(f"path must be within workspace: {path}") from exc


def _read_package(path: Path, *, label: str, strict: bool = True) -> tuple[dict[str, Any], bytes]:
    try:
        package = package_v2.read_canonical_package(path)
        package_v2.validate_package(package, strict=strict)
    except (OSError, package_v2.PackageValidationError) as exc:
        raise ManagerGraphError(f"invalid {label} package: {exc}") from exc
    return package, path.read_bytes()


def _read_canonical_object(path: Path, *, schema: str, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagerGraphError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict) or raw != _canonical(value):
        raise ManagerGraphError(f"{label} must be canonical JSON")
    if value.get("schema_version") != schema:
        raise ManagerGraphError(f"{label} must use {schema}")
    return value, raw


def _manager_by_id(package: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = package.get("managers")
    if not isinstance(rows, list):
        raise ManagerGraphError("package has no managers")
    result = {str(row.get("id") or ""): row for row in rows if isinstance(row, Mapping)}
    if len(result) != len(rows) or "" in result:
        raise ManagerGraphError("package managers lack unique IDs")
    return result


def _source_name_by_foreign_carrier(
    *, foreign: Mapping[str, Any], allocation: Mapping[str, Any],
) -> tuple[dict[int, tuple[str, str]], set[int]]:
    clubs = foreign.get("clubs")
    if not isinstance(clubs, list):
        raise ManagerGraphError("foreign package has no clubs")
    managers = _manager_by_id(foreign)
    foreign_clubs = {int(row["carrier_id"]): row for row in clubs if isinstance(row, Mapping)}
    if len(foreign_clubs) != len(clubs):
        raise ManagerGraphError("foreign package club carrier IDs are invalid")
    assignments = allocation.get("assignments")
    if not isinstance(assignments, list):
        raise ManagerGraphError("manager allocation has no assignments")
    allocation_rows = {
        int(row["team_carrier_id"]): row
        for row in assignments
        if isinstance(row, Mapping) and isinstance(row.get("team_carrier_id"), int)
    }
    if not set(foreign_clubs) <= set(allocation_rows):
        missing = sorted(set(foreign_clubs) - set(allocation_rows))
        raise ManagerGraphError(f"allocation omits foreign club carrier {missing[0]}")

    named: dict[int, tuple[str, str]] = {}
    preserved_non_club: set[int] = set()
    for carrier, club in sorted(foreign_clubs.items()):
        allocation_row = allocation_rows[carrier]
        status = str(allocation_row.get("target_manager_source_status") or "")
        published = allocation_row.get("target_manager_name")
        if status == "out-of-scope-non-club-carrier":
            preserved_non_club.add(carrier)
            continue
        if status == "target-manager-pm99-transliteration-required":
            name = PM99_DISPLAY_OVERRIDES.get(carrier)
            if name is None:
                raise ManagerGraphError(f"missing reviewed transliteration for foreign club {carrier}")
            named[carrier] = (name, "reviewed-pm99-transliteration")
            continue
        if not isinstance(published, str) or not published.strip():
            raise ManagerGraphError(
                f"foreign club {carrier} has no dated manager name ({status or 'missing status'})"
            )
        name = " ".join(published.split())
        try:
            name.encode("cp1252")
        except UnicodeEncodeError:
            replacement = PM99_DISPLAY_OVERRIDES.get(carrier)
            if replacement is None:
                raise ManagerGraphError(f"foreign manager {name!r} has no reviewed PM99 display form")
            name = replacement
            status = f"{status}-reviewed-pm99-display-form"
        # Bind the allocation's source result to the actual current package
        # club identity.  The old manager entity is deliberately not trusted:
        # it is the surface which leaked names across teams.
        if str(club.get("manager_id") or "") not in managers:
            raise ManagerGraphError(f"foreign club {carrier} has no package manager entity")
        named[carrier] = (name, status)
    if set(named) | preserved_non_club != set(foreign_clubs):
        raise ManagerGraphError("foreign manager source partition is incomplete")
    return named, preserved_non_club


def _source_name_by_english_carrier(english: Mapping[str, Any]) -> dict[int, str]:
    clubs = english.get("clubs")
    managers = _manager_by_id(english)
    if not isinstance(clubs, list) or len(clubs) != 92:
        raise ManagerGraphError("English package must contain exactly 92 clubs")
    result: dict[int, str] = {}
    for club in clubs:
        if not isinstance(club, Mapping):
            raise ManagerGraphError("English package has malformed club row")
        carrier = club.get("carrier_id")
        manager = managers.get(str(club.get("manager_id") or ""))
        name = " ".join(str((manager or {}).get("name") or "").split())
        if not isinstance(carrier, int) or carrier in result or not name:
            raise ManagerGraphError("English package has an incomplete manager row")
        try:
            name.encode("cp1252")
        except UnicodeEncodeError as exc:
            raise ManagerGraphError(f"English manager {name!r} is not PM99-writable") from exc
        result[carrier] = name
    return result


def build_plan(
    *, foreign: Mapping[str, Any], foreign_raw: bytes,
    english: Mapping[str, Any], english_raw: bytes,
    allocation: Mapping[str, Any], allocation_raw: bytes,
    base_tree: Path,
) -> dict[str, Any]:
    foreign_names, non_club = _source_name_by_foreign_carrier(
        foreign=foreign, allocation=allocation,
    )
    english_names = _source_name_by_english_carrier(english)
    if set(foreign_names) & set(english_names):
        raise ManagerGraphError("foreign and English package carrier scopes overlap")

    eq_path = base_tree / "DBDAT/EQ98030.FDI"
    ent_path = base_tree / "DBDAT/ENT98030.FDI"
    if not eq_path.is_file() or not ent_path.is_file():
        raise ManagerGraphError("base tree is missing EQ98030.FDI or ENT98030.FDI")
    eq_data, ent_data = eq_path.read_bytes(), ent_path.read_bytes()
    eq_entries = {int(row.record_id): row for row in IndexedFDIFile.from_bytes(eq_data).entries}
    ent_entries = {int(row.record_id): row for row in IndexedFDIFile.from_bytes(ent_data).entries}

    all_targets = {
        **{carrier: (name, status, "foreign") for carrier, (name, status) in foreign_names.items()},
        **{carrier: (name, "dated-english-package-manager-source", "english") for carrier, name in english_names.items()},
    }
    if len(all_targets) != 538:
        raise ManagerGraphError(f"expected 538 sourced club-manager targets, found {len(all_targets)}")
    if any(carrier not in eq_entries for carrier in all_targets):
        missing = sorted(carrier for carrier in all_targets if carrier not in eq_entries)
        raise ManagerGraphError(f"EQ lacks target club carrier {missing[0]}")

    # Preserve the five deliberately non-club links. They have no historical
    # club-manager fact and must not consume a newly-written manager record.
    reserved: set[int] = set()
    preserved_rows: list[dict[str, Any]] = []
    for carrier in sorted(non_club):
        entry = eq_entries.get(carrier)
        if entry is None:
            raise ManagerGraphError(f"EQ lacks non-club carrier {carrier}")
        current = parse_indexed_eq_manager_links(
            eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        ).active_manager_record_id
        if not isinstance(current, int):
            raise ManagerGraphError(f"non-club carrier {carrier} has no active manager link")
        reserved.add(current)
        preserved_rows.append({"team_carrier_id": carrier, "manager_carrier_id": current})

    safe_slots = [
        int(carrier) for carrier in _manager_candidates(ent_data)
        if int(carrier) not in reserved
    ]
    if len(safe_slots) < len(all_targets):
        raise ManagerGraphError(
            f"only {len(safe_slots)} exclusive writable ENT records for {len(all_targets)} sourced clubs"
        )
    allocated = safe_slots[:len(all_targets)]
    if len(set(allocated)) != len(allocated) or any(carrier not in ent_entries for carrier in allocated):
        raise ManagerGraphError("manager allocation is not a unique ENT subset")

    targets: list[dict[str, Any]] = []
    for (team, (name, source_status, scope)), manager_carrier in zip(
        sorted(all_targets.items()), allocated, strict=True,
    ):
        # Run the real writer as a preflight; a content receipt is not enough
        # if this particular variable-length ENT record cannot carry the name.
        entry = ent_entries[manager_carrier]
        _patch_ent_name(entry.decode_payload(ent_data), manager_carrier, name)
        targets.append({
            "team_carrier_id": team,
            "manager_carrier_id": manager_carrier,
            "manager_name": name,
            "source_status": source_status,
            "scope": scope,
        })

    return {
        "schema_version": SCHEMA,
        "season": "2015-16",
        "policy": (
            "allocate one parser-writable ENT record to every sourced English or foreign club; "
            "write only the active EQ manager link and the ENT display name; preserve the five non-club links"
        ),
        "inputs": {
            "foreign_package": {"path": "", "sha256": _sha256_bytes(foreign_raw)},
            "english_package": {"path": "", "sha256": _sha256_bytes(english_raw)},
            "manager_source_allocation": {"path": "", "sha256": _sha256_bytes(allocation_raw)},
            "EQ98030.FDI_sha256": _sha256_bytes(eq_data),
            "ENT98030.FDI_sha256": _sha256_bytes(ent_data),
        },
        "coverage": {
            "sourced_club_manager_count": len(targets),
            "foreign_sourced_manager_count": len(foreign_names),
            "english_sourced_manager_count": len(english_names),
            "preserved_non_club_link_count": len(preserved_rows),
            "source_status_counts": dict(sorted(Counter(row["source_status"] for row in targets).items())),
            "unallocated_safe_manager_slot_count": len(safe_slots) - len(targets),
        },
        "targets": targets,
        "preserved_non_club_links": preserved_rows,
    }


def apply_plan(*, plan: Mapping[str, Any], game: Path, apply: bool) -> dict[str, Any]:
    if plan.get("schema_version") != SCHEMA:
        raise ManagerGraphError(f"plan must use {SCHEMA}")
    inputs = plan.get("inputs")
    targets = plan.get("targets")
    if not isinstance(inputs, Mapping) or not isinstance(targets, list):
        raise ManagerGraphError("manager graph plan has no inputs or targets")
    if len(targets) != 538:
        raise ManagerGraphError("manager graph plan must have 538 sourced targets")
    game = game.resolve()
    jug_path, eq_path, ent_path = (game / "DBDAT/JUG98030.FDI", game / "DBDAT/EQ98030.FDI", game / "DBDAT/ENT98030.FDI")
    for path in (jug_path, eq_path, ent_path):
        if not path.is_file() or path.is_symlink():
            raise ManagerGraphError(f"game input is missing or unsafe: {path}")
    if _sha256_file(eq_path) != inputs.get("EQ98030.FDI_sha256"):
        raise ManagerGraphError("game EQ98030.FDI differs from the plan's verified base")
    if _sha256_file(ent_path) != inputs.get("ENT98030.FDI_sha256"):
        raise ManagerGraphError("game ENT98030.FDI differs from the plan's verified base")

    eq_data, ent_data = eq_path.read_bytes(), ent_path.read_bytes()
    eq_index, ent_index = IndexedFDIFile.from_bytes(eq_data), IndexedFDIFile.from_bytes(ent_data)
    eq_entries = {int(row.record_id): row for row in eq_index.entries}
    ent_entries = {int(row.record_id): row for row in ent_index.entries}
    team_ids: set[int] = set()
    manager_ids: set[int] = set()
    eq_replacements: dict[int, bytes] = {}
    ent_replacements: dict[int, bytes] = {}
    for row in targets:
        if not isinstance(row, Mapping):
            raise ManagerGraphError("manager graph target is malformed")
        team, manager = row.get("team_carrier_id"), row.get("manager_carrier_id")
        name = " ".join(str(row.get("manager_name") or "").split())
        if not isinstance(team, int) or not isinstance(manager, int) or not name:
            raise ManagerGraphError("manager graph target is incomplete")
        if team in team_ids or manager in manager_ids:
            raise ManagerGraphError("manager graph target does not provide exclusive club and ENT IDs")
        team_ids.add(team); manager_ids.add(manager)
        eq_entry, ent_entry = eq_entries.get(team), ent_entries.get(manager)
        if eq_entry is None or ent_entry is None:
            raise ManagerGraphError("manager graph target references a missing EQ or ENT record")
        decoded_eq = eq_entry.decode_payload(eq_data)
        patched_stored = patch_indexed_eq_active_manager_id(xor_encode(decoded_eq), manager)
        eq_replacements[team] = xor_decode(patched_stored)
        before = parse_indexed_ent_manager_profile(
            ent_data[ent_entry.payload_offset : ent_entry.payload_offset + ent_entry.payload_length],
            record_id=manager,
        ).display_name
        if before.casefold() != name.casefold():
            ent_replacements[manager] = _patch_ent_name(ent_entry.decode_payload(ent_data), manager, name)

    rebuilt_eq = _rebuild_indexed(eq_data, eq_index, eq_replacements)
    rebuilt_ent = _rebuild_indexed(ent_data, ent_index, ent_replacements)
    rebuilt_eq_entries = {int(row.record_id): row for row in IndexedFDIFile.from_bytes(rebuilt_eq).entries}
    rebuilt_ent_entries = {int(row.record_id): row for row in IndexedFDIFile.from_bytes(rebuilt_ent).entries}
    for row in targets:
        team, manager, name = int(row["team_carrier_id"]), int(row["manager_carrier_id"]), str(row["manager_name"])
        eq_entry, ent_entry = rebuilt_eq_entries[team], rebuilt_ent_entries[manager]
        link = parse_indexed_eq_manager_links(rebuilt_eq[eq_entry.payload_offset : eq_entry.payload_offset + eq_entry.payload_length])
        actual = parse_indexed_ent_manager_profile(
            rebuilt_ent[ent_entry.payload_offset : ent_entry.payload_offset + ent_entry.payload_length], record_id=manager,
        ).display_name
        if link.active_manager_record_id != manager or actual.casefold() != name.casefold():
            raise ManagerGraphError(f"manager graph read-back failed for club carrier {team}")

    jug_before = _sha256_file(jug_path)
    eq_before, ent_before = _sha256_file(eq_path), _sha256_file(ent_path)
    eq_after, ent_after = _sha256_bytes(rebuilt_eq), _sha256_bytes(rebuilt_ent)
    if apply:
        eq_temp = eq_path.with_name(f".{eq_path.name}.manager-graph.tmp")
        ent_temp = ent_path.with_name(f".{ent_path.name}.manager-graph.tmp")
        if any(path.exists() or path.is_symlink() for path in (eq_temp, ent_temp)):
            raise ManagerGraphError("stale manager graph temporary output exists")
        eq_temp.write_bytes(rebuilt_eq)
        ent_temp.write_bytes(rebuilt_ent)
        try:
            eq_temp.replace(eq_path)
            ent_temp.replace(ent_path)
        finally:
            for path in (eq_temp, ent_temp):
                if path.exists() or path.is_symlink():
                    path.unlink()
    return {
        "schema_version": "pm99-world-2015-manager-graph-repair-application-v1",
        "season": "2015-16",
        "state": "applied-to-candidate-game" if apply else "validated-plan-only",
        "coverage": dict(plan["coverage"]),
        "readback_failure_count": 0,
        "byte_contract": {
            "jug_unchanged_sha256": jug_before,
            "eq_before_sha256": eq_before, "eq_after_sha256": eq_after,
            "ent_before_sha256": ent_before, "ent_after_sha256": ent_after,
            "changed_eq_club_count": sum(1 for row in targets if eq_data[eq_entries[int(row["team_carrier_id"])].payload_offset:eq_entries[int(row["team_carrier_id"])].payload_offset + eq_entries[int(row["team_carrier_id"])].payload_length] != eq_replacements[int(row["team_carrier_id"])]),
            "changed_ent_manager_count": len(ent_replacements),
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build-plan")
    build.add_argument("--foreign-package", required=True, type=Path)
    build.add_argument("--english-package", required=True, type=Path)
    build.add_argument("--manager-source-allocation", required=True, type=Path)
    build.add_argument("--base-tree", required=True, type=Path)
    build.add_argument("--output-plan", required=True, type=Path)
    apply = sub.add_parser("apply")
    apply.add_argument("--plan", required=True, type=Path)
    apply.add_argument("--game", required=True, type=Path)
    apply.add_argument("--output-audit", required=True, type=Path)
    apply.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "build-plan":
            if args.output_plan.exists() or args.output_plan.is_symlink():
                raise ManagerGraphError(f"refusing to overwrite plan: {args.output_plan}")
            foreign, foreign_raw = _read_package(args.foreign_package, label="foreign")
            # This legacy English V2 file is not a strict world package (it
            # predates reconciled person IDs).  This repair consumes only its
            # 92 dated manager strings and club carrier keys, which are
            # independently checked below.
            english, english_raw = _read_package(args.english_package, label="English", strict=False)
            allocation, allocation_raw = _read_canonical_object(
                args.manager_source_allocation, schema=ALLOCATION_SCHEMA, label="manager source allocation",
            )
            plan = build_plan(
                foreign=foreign, foreign_raw=foreign_raw, english=english, english_raw=english_raw,
                allocation=allocation, allocation_raw=allocation_raw, base_tree=args.base_tree.resolve(),
            )
            plan["inputs"]["foreign_package"]["path"] = _relative(args.foreign_package)
            plan["inputs"]["english_package"]["path"] = _relative(args.english_package)
            plan["inputs"]["manager_source_allocation"]["path"] = _relative(args.manager_source_allocation)
            args.output_plan.parent.mkdir(parents=True, exist_ok=True)
            args.output_plan.write_bytes(_canonical(plan))
            print(json.dumps(plan["coverage"], ensure_ascii=False, sort_keys=True))
            return 0
        raw = args.plan.read_bytes()
        plan = json.loads(raw.decode("utf-8"))
        if not isinstance(plan, dict) or raw != _canonical(plan):
            raise ManagerGraphError("manager graph plan must be canonical JSON")
        if args.output_audit.exists() or args.output_audit.is_symlink():
            raise ManagerGraphError(f"refusing to overwrite audit: {args.output_audit}")
        result = apply_plan(plan=plan, game=args.game, apply=args.apply)
        args.output_audit.parent.mkdir(parents=True, exist_ok=True)
        args.output_audit.write_bytes(_canonical(result))
        print(json.dumps({"state": result["state"], **result["coverage"], **result["byte_contract"]}, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ManagerGraphError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
