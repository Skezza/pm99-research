#!/usr/bin/env python3
"""Read-only inventory for the fixed PM99 world-club carrier corpus.

This is deliberately an *evidence inventory*, not a league classifier.  It
does not infer a club's country or competition from EQ record number, record
order, or the mode byte.  Those are exactly the assumptions the world-update
research must replace with fresh-game evidence.

The JSON output gives every modern EQ carrier a stable record id, layout,
current strings, linked roster/player-family mix, manager-link state and
portrait availability.  It is the starting ledger for the mode-1 pilot and
for the browser editor's field-capability matrix.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.ent_manager_profiles import parse_indexed_ent_manager_profile
from app.eq_jug_linked import load_eq_linked_team_rosters
from app.eq_team_manager_links import parse_indexed_eq_manager_links
from app.fdi_indexed import IndexedFDIFile
from app.minifoto_bitmap_archive import iter_minifoto_records
from app.models import PlayerRecord


KNOWN_SPECIAL_CARRIERS = {"stars", "free players"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dbdat", required=True, type=Path, help="Directory containing PM99 database files")
    parser.add_argument("--output", required=True, type=Path, help="JSON report path")
    return parser.parse_args()


def _compact(value: str) -> str:
    return " ".join(str(value or "").split())


def _player_family(decoded: bytes) -> str:
    if len(decoded) < 5:
        return "short_or_opaque"
    marker = decoded[2:5].hex()
    if marker == "dd6360":
        return "dd6360"
    if marker == "dd6361":
        return "dd6361"
    return f"other_{marker}"


def _player_catalog(player_path: Path) -> tuple[dict[int, dict[str, Any]], dict[str, int]]:
    data = player_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(data)
    catalog: dict[int, dict[str, Any]] = {}
    parse_states: Counter[str] = Counter()
    for entry in indexed.entries:
        decoded = entry.decode_payload(data)
        family = _player_family(decoded)
        try:
            player = PlayerRecord.from_bytes(decoded, entry.payload_offset)
            name = _compact(getattr(player, "name", ""))
            parsed = name not in {"", "Unknown Player", "Parse Error"}
        except Exception as exc:  # defensive inventory: bad row must not stop the audit
            name = ""
            parsed = False
            family = f"{family}:parse_error"
            parse_states["exception"] += 1
        else:
            parse_states["parsed" if parsed else "opaque_or_unresolved"] += 1
        catalog[int(entry.record_id)] = {
            "record_id": int(entry.record_id),
            "payload_length": int(entry.payload_length),
            "family": family,
            "display_name": name or None,
            "parser_state": "parsed" if parsed else "opaque_or_unresolved",
        }
    return catalog, dict(sorted(parse_states.items()))


def _manager_catalog(manager_path: Path) -> dict[int, dict[str, Any]]:
    data = manager_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(data)
    catalog: dict[int, dict[str, Any]] = {}
    for entry in indexed.entries:
        try:
            profile = parse_indexed_ent_manager_profile(
                data[entry.payload_offset : entry.payload_offset + entry.payload_length],
                record_id=int(entry.record_id),
            )
        except Exception:
            continue
        catalog[int(entry.record_id)] = {
            "record_id": int(entry.record_id),
            "format": profile.format,
            "surname": _compact(profile.surname) or None,
            "display_name": _compact(profile.display_name) or None,
            "has_profile_text": bool(profile.profile_text),
        }
    return catalog


def _carrier_classification(short_name: str) -> str:
    if _compact(short_name).casefold() in KNOWN_SPECIAL_CARRIERS:
        return "special_non_club"
    return "unclassified_existing_carrier"


def main() -> int:
    args = _parse_args()
    dbdat = args.dbdat.resolve()
    required = {name: dbdat / name for name in ("EQ98030.FDI", "JUG98030.FDI", "ENT98030.FDI", "MINIFOTO.PKF")}
    missing = [str(path) for path in required.values() if not path.is_file()]
    if missing:
        raise SystemExit("missing required PM99 database files: " + ", ".join(missing))

    player_catalog, player_parse_states = _player_catalog(required["JUG98030.FDI"])
    manager_catalog = _manager_catalog(required["ENT98030.FDI"])
    minifoto_ids = {int(row.player_record_id) for row in iter_minifoto_records(required["MINIFOTO.PKF"])}
    rosters = {
        int(row.eq_record_id): row
        for row in load_eq_linked_team_rosters(
            team_file=str(required["EQ98030.FDI"]),
            player_file=str(required["JUG98030.FDI"]),
        )
    }

    eq_data = required["EQ98030.FDI"].read_bytes()
    eq_indexed = IndexedFDIFile.from_bytes(eq_data)
    carriers: list[dict[str, Any]] = []
    unsupported_eq_entries: list[dict[str, Any]] = []
    mode_counts: Counter[str] = Counter()
    roster_state_counts: Counter[str] = Counter()
    manager_state_counts: Counter[str] = Counter()
    linked_roster_player_families_by_mode: dict[str, Counter[str]] = {
        "0": Counter(),
        "1": Counter(),
    }
    mode_one_non_dd6360_roster_rows: list[dict[str, Any]] = []
    roster_player_memberships: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for entry in eq_indexed.entries:
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        record_size = int.from_bytes(raw[0x26:0x28], "little") if len(raw) >= 0x2A else None
        mode = int(raw[0x29]) if len(raw) >= 0x2A else None
        if record_size != 700 or mode not in {0, 1}:
            unsupported_eq_entries.append(
                {
                    "record_id": int(entry.record_id),
                    "key": entry.key,
                    "payload_length": int(entry.payload_length),
                    "record_size": record_size,
                    "record_mode": mode,
                    "reason": "not_a_proven_modern_700_byte_carrier_layout",
                }
            )
            continue

        roster = rosters.get(int(entry.record_id))
        roster_state = "parsed" if roster is not None else "not_parsed"
        roster_state_counts[roster_state] += 1
        short_name = _compact(getattr(roster, "short_name", "")) if roster is not None else ""
        stadium_name = _compact(getattr(roster, "stadium_name", "")) if roster is not None else ""
        full_club_name = _compact(getattr(roster, "full_club_name", "")) if roster is not None else ""
        player_ids = [int(row.player_record_id) for row in getattr(roster, "rows", [])] if roster is not None else []
        linked_players = [player_catalog.get(player_id) for player_id in player_ids]
        family_mix = Counter((row or {"family": "missing"})["family"] for row in linked_players)
        parsed_players = sum(1 for row in linked_players if row and row["parser_state"] == "parsed")
        photo_players = sum(1 for player_id in player_ids if player_id in minifoto_ids)

        try:
            links = parse_indexed_eq_manager_links(raw)
            manager_id = links.active_manager_record_id
            manager_state = "linked" if manager_id else "no_existing_link"
        except Exception as exc:
            links = None
            manager_id = None
            manager_state = f"unparsed:{type(exc).__name__}"
        manager_state_counts[manager_state.split(":", 1)[0]] += 1
        manager = manager_catalog.get(int(manager_id or 0))
        mode_counts[str(mode)] += 1
        linked_roster_player_families_by_mode[str(mode)].update(family_mix)
        if mode == 1 and roster is not None:
            for row in roster.rows:
                player = player_catalog.get(int(row.player_record_id), {})
                if player.get("family") != "dd6360":
                    mode_one_non_dd6360_roster_rows.append(
                        {
                            "eq_record_id": int(entry.record_id),
                            "club_short_name": short_name or None,
                            "slot_index": int(row.slot_index),
                            "player_record_id": int(row.player_record_id),
                            "player_display_name": player.get("display_name"),
                            "player_family": player.get("family"),
                        }
                    )

        if roster is not None:
            for row in roster.rows:
                roster_player_memberships[int(row.player_record_id)].append(
                    {
                        "eq_record_id": int(entry.record_id),
                        "club_short_name": short_name or None,
                        "slot_index": int(row.slot_index),
                        "flag": int(row.flag),
                    }
                )

        carriers.append(
            {
                "eq_record_id": int(entry.record_id),
                "directory_key": entry.key,
                "payload_length": int(entry.payload_length),
                "record_size": record_size,
                "record_mode": mode,
                "classification": _carrier_classification(short_name),
                "competition": {"state": "unresearched", "value": None, "do_not_infer_from": ["record_id", "record_order", "record_mode"]},
                "club_strings": {
                    "state": "parsed" if roster is not None else "unparsed",
                    "short_name": short_name or None,
                    "stadium_name": stadium_name or None,
                    "full_club_name": full_club_name or None,
                },
                "manager": {
                    "link_state": manager_state,
                    "active_manager_record_id": int(manager_id) if manager_id else None,
                    "profile": manager,
                    "ownership_contract": "Existing final EQ->ENT manager link. Runtime-proven for mode 0 and for the mode-1 Barcelona fixture; this inventory structurally verifies every modern carrier, not every individual dashboard.",
                },
                "roster": {
                    "state": roster_state,
                    "slot_count": len(player_ids),
                    "linked_player_record_ids": player_ids,
                    "parsed_player_count": parsed_players,
                    "opaque_or_missing_player_count": len(player_ids) - parsed_players,
                    "player_family_mix": dict(sorted(family_mix.items())),
                    "minifoto_count": photo_players,
                    "no_minifoto_count": len(player_ids) - photo_players,
                },
                "write_contract": {
                    "club_strings": "layout_contract_runtime_proven_for_indexed_existing_carriers_not_individually_exercised",
                    "manager_link": (
                        "runtime_proven_existing_final_link_replacement_only_preserve_count_and_preceding_ids"
                    ),
                    "manager_name_or_biography": "variable_length_surname_runtime_proven_for_surname_only_and_full_profile_ent_records_full_profile_display_name_and_biography_tail_preserve_only",
                    "roster_links": "existing_row_source_and_target_transaction_runtime_proven_preserve_count_and_flag_reject_generated_duplicate_jug_ids",
                    "player_identity_and_visible_fields": "dd6360_nationality_date_physicals_and_visible_skills_runtime_proven_by_native_cursor_other_identity_and_role_fields_research_pending",
                    "minifoto": "player_id_asset_contract_runtime_proven_not_individually_exercised",
                    "kit": "compact_ui_assets_are_existing_EQ96<carrier-id>.BMP_records_in_MINIESC_NANOESC_RIDIESC_and_are_runtime_proven_by_Barcelona;_BIG_archives_and_other_render_surfaces_remain_separate",
                    "opening_tactics": "research_pending_mode1",
                    "competition_membership": "preserve_only_pending_contract",
                },
            }
        )

    duplicate_roster_player_memberships = [
        {
            "player_record_id": player_id,
            "membership_count": len(memberships),
            "memberships": memberships,
        }
        for player_id, memberships in sorted(roster_player_memberships.items())
        if len(memberships) > 1
    ]
    linked_roster_rows = sum(len(memberships) for memberships in roster_player_memberships.values())

    report = {
        "schema": "pm99-world-carrier-inventory/v1",
        "purpose": "Read-only baseline for international carrier research; not a competition registry or a bulk-write authority.",
        "dbdat": str(dbdat),
        "counts": {
            "eq_index_entries": len(eq_indexed.entries),
            "modern_carriers": len(carriers),
            "modern_carriers_by_mode": dict(sorted(mode_counts.items())),
            "modern_carriers_with_parsed_roster": dict(sorted(roster_state_counts.items())),
            "modern_carriers_by_manager_link_state": dict(sorted(manager_state_counts.items())),
            "linked_roster_player_families_by_mode": {
                mode: dict(sorted(families.items()))
                for mode, families in sorted(linked_roster_player_families_by_mode.items())
            },
            "non_modern_or_unhandled_eq_entries": len(unsupported_eq_entries),
            "indexed_players": len(player_catalog),
            "player_parse_states": player_parse_states,
            "parsed_manager_profiles": len(manager_catalog),
            "minifoto_records": len(minifoto_ids),
            "linked_roster_rows": linked_roster_rows,
            "linked_unique_player_ids": len(roster_player_memberships),
            "linked_duplicate_player_ids": len(duplicate_roster_player_memberships),
            "linked_duplicate_rows": sum(
                row["membership_count"] - 1 for row in duplicate_roster_player_memberships
            ),
        },
        "field_contracts": {
            "club_short_name_stadium_full_name": "indexed-EQ variable rebuild contract is runtime-proven for existing carriers; inventory rows are not individual runtime certifications; preserve all unapproved bytes",
            "active_manager_link": "runtime-proven replacement of the existing final ENT link for modes 0 and 1; preserve the count and all preceding ids, and require the replacement ENT id to exist",
            "manager_names_and_biography": "variable-length ENT surname rebuild is runtime-proven for surname-only and full-profile records; the full-profile dashboard consumes the surname, while its display-name segment and biography/career prose remain preserve-only",
            "player_fields": "family-specific; do not treat a parsed player as automatically writable",
            "roster_and_membership": "separate contracts; source-and-target mode-1 external-row transaction is runtime-proven for profile-club resolution, while duplicate/loan precedence, row-count/flag semantics and competition membership remain separate",
            "minifoto": "player-id asset mapping and native no-photo state are proven as a format contract; inventory rows are not individual portrait certifications",
            "kit": "compact UI artwork is direct carrier-keyed and runtime-proven for the Barcelona foreign selector; large/archive and 3D surfaces remain separate preserve-only decisions",
            "opening_tactics": "mode-0 opening grid is runtime-proven; the similarly bounded mode-1 candidate is not a write contract",
            "competition_membership": "preserve-only until fresh-game country/league mapping and write contract exist",
        },
        "unsupported_eq_entries": unsupported_eq_entries,
        "mode_one_non_dd6360_roster_rows": mode_one_non_dd6360_roster_rows,
        "duplicate_roster_player_memberships": duplicate_roster_player_memberships,
        "carriers": carriers,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
