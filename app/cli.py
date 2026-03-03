"""
Command-line interface for Premier Manager 99 Database Editor
"""

import argparse
import bisect
import json
import re
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

from .bulk_rename import bulk_rename_players, revert_player_renames
from .editor_actions import (
    batch_edit_player_metadata_records,
    batch_edit_team_roster_records,
    edit_player_metadata_records,
    edit_team_roster_eq_jug_linked,
    edit_team_roster_same_entry_authoritative,
    extract_team_rosters_eq_jug_linked,
    extract_team_rosters_eq_same_entry_overlap,
    inspect_main_dat_prefix,
    inspect_player_metadata_records,
    parse_player_skill_patch_assignments,
    patch_main_dat_prefix,
    patch_player_visible_skills_dd6361,
    profile_indexed_player_attribute_prefixes,
    profile_player_legacy_weight_candidates,
    profile_same_entry_authoritative_tail_bytes,
    profile_indexed_player_leading_bytes,
    profile_indexed_player_suffix_bytes,
    rename_coach_records,
    rename_player_records,
    rename_team_records,
    validate_database_files,
)
from .editor_helpers import (
    _coach_display_name,
    _player_display_name,
    _team_display_name,
    team_query_matches,
)
from .editor_sources import (
    gather_coach_records,
    gather_player_records,
    gather_player_records_heuristic,
    gather_player_records_strict,
    gather_team_records,
)
from .io import FDIFile
from .models import PlayerRecord
from .pkf_searcher import PKFSearcher
from .xor import decode_entry


def _parse_int_auto(value: str | None):
    if value is None:
        return None
    return int(str(value), 0)


def _jsonable(value):
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return value.hex()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _emit(value, as_json: bool = False):
    if as_json:
        print(json.dumps(_jsonable(value), indent=2))
    else:
        print(value)


def _write_json_report(path: str | None, value) -> None:
    if not path:
        return
    Path(path).write_text(json.dumps(_jsonable(value), indent=2) + "\n", encoding="utf-8")


def _print_database_validation_result(result) -> None:
    files = list(getattr(result, "files", []) or [])
    if not files:
        print("No database files were validated.")
        return
    print(f"Database validation: {'PASS' if getattr(result, 'all_valid', False) else 'FAIL'}")
    for item in files:
        status = "ok" if getattr(item, "success", False) else "error"
        valid_count = int(getattr(item, "valid_count", 0) or 0)
        uncertain_count = int(getattr(item, "uncertain_count", 0) or 0)
        detail = str(getattr(item, "detail", "") or "")
        print(
            f"  {getattr(item, 'category', 'unknown')}: {status} "
            f"valid={valid_count} uncertain={uncertain_count} "
            f"path={getattr(item, 'file_path', '')}"
        )
        if detail:
            print(f"    {detail}")


def _print_linked_team_rosters(rosters, row_limit: int) -> None:
    if not rosters:
        print("No parser-backed EQ->JUG roster rows found.")
        return

    for item in rosters:
        team_name = str(item.get("team_name") or "")
        full_club_name = str(item.get("full_club_name") or "")
        eq_record_id = int(item.get("eq_record_id") or 0)
        ent_count = int(item.get("ent_count") or 0)
        mode_byte = int(item.get("mode_byte") or 0)
        rows = list(item.get("rows") or [])
        display = team_name
        if full_club_name and full_club_name != team_name:
            display = f"{team_name} ({full_club_name})"
        print(
            f"{display}: provenance=eq_jug_linked_parser eq_record_id={eq_record_id} "
            f"mode={mode_byte} ent_count={ent_count} rows={len(rows)}"
        )
        shown = 0
        for row in rows:
            if row_limit and shown >= row_limit:
                remaining = len(rows) - shown
                if remaining > 0:
                    print(f"  ... {remaining} more row(s)")
                break
            shown += 1
            pid = int(row.get("pid") or 0)
            flag = int(row.get("flag") or 0)
            player_name = str(row.get("player_name") or "").strip()
            label = player_name or "(name unresolved)"
            print(f"  slot={shown:02d} pid={pid:5d} flag={flag} {label}")


def _print_linked_team_roster_edit_result(result, *, dry_run: bool) -> None:
    if not result.changes:
        print("No linked team roster rows changed.")
    else:
        action = "Staged" if dry_run else "Updated"
        print(f"{action} {len(result.changes)} parser-backed EQ->JUG linked roster row(s)")
        for change in result.changes[:20]:
            display = change.team_name
            if change.full_club_name and change.full_club_name != change.team_name:
                display = f"{change.team_name} ({change.full_club_name})"
            old_name = change.old_player_name or "(name unresolved)"
            new_name = change.new_player_name or "(name unresolved)"
            print(
                f"  eq_record_id={change.eq_record_id} {display} slot={change.slot_number:02d}: "
                f"pid {change.old_player_record_id} -> {change.new_player_record_id} "
                f"[{old_name} -> {new_name}], flag {change.old_flag} -> {change.new_flag}"
            )
    if result.backup_path:
        print(f"Backup: {result.backup_path}")
    for warning in result.warnings:
        prefix = f"Warning at {warning.offset}" if warning.offset is not None else "Warning"
        print(f"{prefix}: {warning.message}", file=sys.stderr)


def _print_same_entry_team_roster_edit_result(result, *, dry_run: bool) -> None:
    if not result.changes:
        print("No same-entry roster rows changed.")
    else:
        action = "Staged" if dry_run else "Updated"
        print(f"{action} {len(result.changes)} supported same-entry roster row(s)")
        for change in result.changes[:20]:
            display = change.team_name
            if change.full_club_name and change.full_club_name != change.team_name:
                display = f"{change.team_name} ({change.full_club_name})"
            old_name = change.old_player_name or "(name unresolved)"
            new_name = change.new_player_name or "(name unresolved)"
            provenance = str(getattr(change, "provenance", "") or "")
            provenance_suffix = f" provenance={provenance}" if provenance else ""
            tail_suffix = (
                f" preserved_tail={change.preserved_tail_bytes_hex}"
                if str(getattr(change, "preserved_tail_bytes_hex", "") or "")
                else ""
            )
            print(
                f"  team_offset=0x{change.team_offset:08X} {display} slot={change.slot_number:02d}: "
                f"pid {change.old_pid_candidate} -> {change.new_pid_candidate} "
                f"[{old_name} -> {new_name}] entry=0x{change.entry_offset:08X}{provenance_suffix}{tail_suffix}"
            )
    if result.backup_path:
        print(f"Backup: {result.backup_path}")
    for warning in result.warnings:
        prefix = f"Warning at {warning.offset}" if warning.offset is not None else "Warning"
        print(f"{prefix}: {warning.message}", file=sys.stderr)


def _print_team_roster_batch_edit_result(result, *, dry_run: bool) -> None:
    total_changes = len(getattr(result, "linked_changes", []) or []) + len(getattr(result, "same_entry_changes", []) or [])
    if total_changes == 0:
        print("No team roster rows changed.")
    else:
        action = "Staged" if dry_run else "Updated"
        print(
            f"{action} {total_changes} team roster row(s) "
            f"(linked={len(getattr(result, 'linked_changes', []) or [])}, "
            f"same_entry={len(getattr(result, 'same_entry_changes', []) or [])})"
        )
        linked_result = argparse.Namespace(
            changes=list(getattr(result, "linked_changes", []) or []),
            backup_path=None,
            warnings=[],
        )
        same_entry_result = argparse.Namespace(
            changes=list(getattr(result, "same_entry_changes", []) or []),
            backup_path=None,
            warnings=[],
        )
        if linked_result.changes:
            _print_linked_team_roster_edit_result(linked_result, dry_run=dry_run)
        if same_entry_result.changes:
            _print_same_entry_team_roster_edit_result(same_entry_result, dry_run=dry_run)
    if result.backup_path:
        print(f"Backup: {result.backup_path}")
    for warning in result.warnings:
        prefix = f"Warning at {warning.offset}" if warning.offset is not None else "Warning"
        print(f"{prefix}: {warning.message}", file=sys.stderr)


def _same_entry_row_tail_text(row) -> str:
    tail_hex = str((row or {}).get("tail_bytes_hex") or "").strip().lower()
    if len(tail_hex) == 6:
        return tail_hex
    row5_raw_hex = str((row or {}).get("row5_raw_hex") or "").strip().lower()
    if len(row5_raw_hex) == 10:
        return row5_raw_hex[4:10]
    return ""


def _print_same_entry_tail_profile_result(result) -> None:
    if not result.buckets:
        if getattr(result, "include_fallbacks", False):
            print("No preferred same-entry tail-byte buckets matched.")
        else:
            print("No authoritative same-entry tail-byte buckets matched.")
        return
    title = "Preferred same-entry tail-byte profile" if getattr(result, "include_fallbacks", False) else "Authoritative same-entry tail-byte profile"
    print(
        f"{title}: requested_teams={result.requested_team_count}, "
        f"authoritative_teams={result.authoritative_team_count}, rows={result.row_count}"
    )
    provenance_counts = dict(getattr(result, "provenance_counts", {}) or {})
    if provenance_counts:
        counts_text = ", ".join(f"{key}={provenance_counts[key]}" for key in sorted(provenance_counts.keys()))
        print(f"  provenance_counts={counts_text}")
    if len(result.buckets) == 1 and int(getattr(result.buckets[0], "count", 0) or 0) == int(getattr(result, "row_count", 0) or 0):
        only_bucket = result.buckets[0]
        if str(getattr(only_bucket, "tail_bytes_hex", "") or ""):
            field_name = "all_preferred_rows_share_tail" if getattr(result, "include_fallbacks", False) else "all_authoritative_rows_share_tail"
            print(f"  {field_name}={only_bucket.tail_bytes_hex}")
    for bucket in result.buckets:
        teams = ", ".join(bucket.sample_teams)
        players = ", ".join(bucket.sample_players)
        suffix_parts = []
        if teams:
            suffix_parts.append(f"teams={teams}")
        if players:
            suffix_parts.append(f"players={players}")
        suffix = f" {' | '.join(suffix_parts)}" if suffix_parts else ""
        provenance = str(getattr(bucket, "provenance", "") or "")
        provenance_prefix = f"provenance={provenance} " if provenance else ""
        print(
            f"  {provenance_prefix}tail={bucket.tail_bytes_hex or 'n/a'} "
            f"(b2={bucket.tail_byte_2}, b3={bucket.tail_byte_3}, b4={bucket.tail_byte_4}): "
            f"count={bucket.count}{suffix}"
        )


def _gather_player_entries_for_cli(args):
    if getattr(args, "strict", False):
        return gather_player_records_strict(
            args.file,
            require_team_id=getattr(args, "require_team_id", False),
        )
    return gather_player_records(args.file)


def _player_offset_is_writable(file_bytes, offset: int, expected_name: str) -> bool:
    """Return True when the offset decodes as a real player entry matching the expected name."""
    if file_bytes is None:
        # Unit-test stubs may not provide the loaded file image.
        return True
    if not isinstance(offset, int) or offset < 0 or offset + 2 > len(file_bytes):
        return False
    try:
        decoded, length = decode_entry(file_bytes, offset)
        parsed = PlayerRecord.from_bytes(decoded, offset)
    except Exception:
        return False
    if length < 40 or length > 1024:
        return False
    return _player_display_name(parsed).strip().lower() == (expected_name or "").strip().lower()


def _player_entry_payload(entry):
    return {
        "offset": entry.offset,
        "name": _player_display_name(entry.record),
        "team_id": getattr(entry.record, "team_id", None),
        "squad_number": getattr(entry.record, "squad_number", None),
        "source": entry.source,
    }


def _print_player_rename_result(result, *, dry_run: bool) -> None:
    if not result.changes:
        print("No player records changed.")
        return
    print(
        f"{'Staged' if dry_run else 'Renamed'} {len(result.changes)} player record(s) "
        f"(matched={result.matched_count}, valid={result.valid_count}, uncertain={result.uncertain_count})"
    )
    for change in result.changes[:20]:
        print(f"  0x{change.offset:08X}: {change.old_name} -> {change.new_name}")
    if len(result.changes) > 20:
        print(f"  ... and {len(result.changes) - 20} more")
    if result.backup_path:
        print(f"Backup: {result.backup_path}")
    for warning in result.warnings:
        print(f"Warning at {warning.offset}: {warning.message}", file=sys.stderr)


def _print_player_metadata_edit_result(result, *, dry_run: bool) -> None:
    count_label = "indexed_entries" if getattr(result, "storage_mode", "indexed") == "indexed" else "scanned_records"
    if not result.changes:
        print("No player metadata records changed.")
    else:
        print(
            f"{'Staged' if dry_run else 'Updated'} {len(result.changes)} player record(s) "
            f"(matched={result.matched_count}, {count_label}={result.record_count})"
        )
        for change in result.changes[:20]:
            field_changes = ", ".join(
                f"{field_name}: {before} -> {after}"
                for field_name, (before, after) in change.changed_fields.items()
            )
            print(f"  0x{change.offset:08X}: {change.name} [{field_changes}]")
        if len(result.changes) > 20:
            print(f"  ... and {len(result.changes) - 20} more")
        if result.backup_path:
            print(f"Backup: {result.backup_path}")
    for warning in result.warnings:
        prefix = f"Warning at {warning.offset}" if warning.offset is not None else "Warning"
        print(f"{prefix}: {warning.message}", file=sys.stderr)


def _print_player_batch_edit_result(result, *, dry_run: bool) -> None:
    count_label = "indexed_entries" if getattr(result, "storage_mode", "indexed") == "indexed" else "scanned_records"
    if not result.changes:
        print("No player batch edits changed any records.")
    else:
        print(
            f"{'Staged' if dry_run else 'Updated'} {len(result.changes)} player record(s) "
            f"from {result.row_count} CSV row(s) (matched_rows={result.matched_row_count}, {count_label}={result.record_count})"
        )
        for change in result.changes[:20]:
            field_changes = ", ".join(
                f"{field_name}: {before} -> {after}"
                for field_name, (before, after) in change.changed_fields.items()
            )
            print(f"  0x{change.offset:08X}: {change.name} [{field_changes}]")
        if len(result.changes) > 20:
            print(f"  ... and {len(result.changes) - 20} more")
        print(f"Plan: {result.csv_path}")
        if result.backup_path:
            print(f"Backup: {result.backup_path}")
    for warning in result.warnings:
        prefix = f"Warning at {warning.offset}" if warning.offset is not None else "Warning"
        print(f"{prefix}: {warning.message}", file=sys.stderr)


def _print_player_metadata_inspect_result(result) -> None:
    if not result.records:
        print("No player metadata records matched.")
        return
    count_label = "indexed_entries" if getattr(result, "storage_mode", "indexed") == "indexed" else "scanned_records"
    print(
        f"Matched {len(result.records)} player record(s) "
        f"({count_label}={result.record_count})"
    )
    for row in result.records[:20]:
        anchor_text = f"0x{row.suffix_anchor:02X}" if isinstance(row.suffix_anchor, int) else "n/a"
        dob_text = (
            f"{int(row.birth_day or 0):02d}/{int(row.birth_month or 0):02d}/{int(row.birth_year or 0):04d}"
            if row.birth_day is not None and row.birth_month is not None and row.birth_year is not None
            else "n/a"
        )
        hint = _player_suffix_pair_hint(row.indexed_unknown_9, row.indexed_unknown_10)
        hint_text = f" hint={hint}" if hint else ""
        face_text = f" face={row.face_components}" if row.face_components else ""
        prefix_text = ""
        if list(getattr(row, "attribute_prefix", []) or []):
            prefix_text = f" tail_prefix={list(getattr(row, 'attribute_prefix', []) or [])}"
        post_weight_text = ""
        if getattr(row, "post_weight_byte", None) is not None:
            post_weight_text = f" postwt={getattr(row, 'post_weight_byte', None)}"
        post_weight_hint_text = ""
        if (
            getattr(row, "post_weight_byte", None) is not None
            and getattr(row, "nationality", None) is not None
        ):
            if getattr(row, "post_weight_byte", None) == getattr(row, "nationality", None):
                post_weight_hint_text = " posthint=nat-search-mirror"
            else:
                post_weight_hint_text = " posthint=nat-search-group"
        trailer_text = ""
        if getattr(row, "trailer_byte", None) is not None:
            trailer_text = f" trail={getattr(row, 'trailer_byte', None)}"
        sidecar_text = ""
        if getattr(row, "sidecar_byte", None) is not None:
            sidecar_text = f" sidecar={getattr(row, 'sidecar_byte', None)}"
        leading_text = ""
        if row.indexed_unknown_0 is not None or row.indexed_unknown_1 is not None:
            leading_text = f" u0={row.indexed_unknown_0} u1={row.indexed_unknown_1}"
        u1_hint = _player_u1_display_hint(row.indexed_unknown_1)
        u1_hint_text = f" u1hint={u1_hint}" if u1_hint else ""
        guard_hint = _player_leading_guard_hint(row.indexed_unknown_0, row.indexed_unknown_1)
        guard_hint_text = f" guard={guard_hint}" if guard_hint else ""
        print(
            f"  0x{row.offset:08X} rid={row.record_id:5d}: {row.name} "
            f"[nat={row.nationality}{leading_text} u9={row.indexed_unknown_9} u10={row.indexed_unknown_10} "
            f"pos={row.position} dob={dob_text} ht={row.height} wt={row.weight} anchor={anchor_text}{prefix_text}{post_weight_text}{post_weight_hint_text}{trailer_text}{sidecar_text}{face_text}{u1_hint_text}{guard_hint_text}{hint_text}]"
        )
    if len(result.records) > 20:
        print(f"  ... and {len(result.records) - 20} more")


def _print_player_legacy_weight_profile_result(result) -> None:
    if not getattr(result, "offsets", None):
        print("No legacy weight candidate offsets were profiled.")
        return
    print(
        f"Legacy weight candidate profile: indexed_entries={result.record_count}, "
        f"control_records={result.candidate_record_count}, recommended_offset={result.recommended_offset}"
    )
    print(f"  baseline height@marker+13 exact_ratio={getattr(result, 'height_baseline_exact_ratio', 0.0):.4f}")
    if int(getattr(result, "legacy_valid_record_count", 0) or 0):
        print(
            "  name-only validation: "
            + f"valid_records={int(getattr(result, 'legacy_valid_record_count', 0) or 0)} "
            + f"slot_records={int(getattr(result, 'legacy_slot_record_count', 0) or 0)} "
            + f"matched={int(getattr(result, 'legacy_matched_record_count', 0) or 0)} "
            + f"exact={int(getattr(result, 'legacy_exact_match_count', 0) or 0)} "
            + f"ratio={float(getattr(result, 'legacy_exact_match_ratio', 0.0) or 0.0):.4f}"
        )
    for row in result.offsets:
        values = ", ".join(f"{value}({count})" for value, count in list(getattr(row, "top_values", []) or []))
        values_suffix = f" top={values}" if values else ""
        print(
            f"  marker+{row.relative_offset}: eligible={row.eligible_count} "
            f"exact={row.exact_match_count} ratio={row.exact_match_ratio:.4f} "
            f"mae={row.mean_abs_error:.2f}{values_suffix}"
        )


def _print_player_suffix_profile_result(result) -> None:
    if not result.buckets:
        print("No indexed suffix profile buckets matched.")
        return
    filter_bits = []
    if result.nationality_filter is not None:
        filter_bits.append(f"nat={result.nationality_filter}")
    if result.position_filter is not None:
        filter_bits.append(f"pos={result.position_filter}")
    filter_text = f" [{' '.join(filter_bits)}]" if filter_bits else ""
    print(
        f"Indexed suffix profile{filter_text}: "
        f"anchored={result.anchored_count}, filtered={result.filtered_count}, indexed_entries={result.record_count}"
    )
    for bucket in result.buckets:
        names = ", ".join(bucket.sample_names)
        suffix = f" examples={names}" if names else ""
        hint = _player_suffix_pair_hint(bucket.indexed_unknown_9, bucket.indexed_unknown_10)
        hint_text = f" hint={hint}" if hint else ""
        print(
            f"  u9={bucket.indexed_unknown_9} u10={bucket.indexed_unknown_10}: "
            f"count={bucket.count}{hint_text}{suffix}"
        )


def _print_player_leading_profile_result(result) -> None:
    if not result.buckets:
        print("No indexed leading-byte profile buckets matched.")
        return
    filter_bits = []
    if result.nationality_filter is not None:
        filter_bits.append(f"nat={result.nationality_filter}")
    if result.position_filter is not None:
        filter_bits.append(f"pos={result.position_filter}")
    if result.indexed_unknown_0_filter is not None:
        filter_bits.append(f"u0={result.indexed_unknown_0_filter}")
    if result.indexed_unknown_1_filter is not None:
        filter_bits.append(f"u1={result.indexed_unknown_1_filter}")
    if result.indexed_unknown_9_filter is not None:
        filter_bits.append(f"u9={result.indexed_unknown_9_filter}")
    if result.indexed_unknown_10_filter is not None:
        filter_bits.append(f"u10={result.indexed_unknown_10_filter}")
    filter_text = f" [{' '.join(filter_bits)}]" if filter_bits else ""
    print(
        f"Indexed leading-byte profile{filter_text}: "
        f"anchored={result.anchored_count}, filtered={result.filtered_count}, indexed_entries={result.record_count}"
    )
    position_text = _format_profile_count_summary(
        getattr(result, "position_counts", []),
        label="pos",
    )
    if position_text:
        print(f"  positions={position_text}")
    nationality_text = _format_profile_count_summary(
        getattr(result, "nationality_counts", []),
        label="nat",
    )
    if nationality_text:
        print(f"  nationalities={nationality_text}")
    for bucket in result.buckets:
        names = ", ".join(bucket.sample_names)
        suffix = f" examples={names}" if names else ""
        hint = _player_u1_display_hint(bucket.indexed_unknown_1)
        hint_text = f" hint={hint}" if hint else ""
        guard_hint = _player_leading_guard_hint(bucket.indexed_unknown_0, bucket.indexed_unknown_1)
        guard_hint_text = f" guard={guard_hint}" if guard_hint else ""
        print(
            f"  u0={bucket.indexed_unknown_0} u1={bucket.indexed_unknown_1}: "
            f"count={bucket.count}{hint_text}{guard_hint_text}{suffix}"
        )


def _print_player_attribute_prefix_profile_result(result) -> None:
    if not result.buckets:
        print("No indexed tail-prefix profile buckets matched.")
        return
    filter_bits = []
    if result.nationality_filter is not None:
        filter_bits.append(f"nat={result.nationality_filter}")
    if result.position_filter is not None:
        filter_bits.append(f"pos={result.position_filter}")
    if result.indexed_unknown_0_filter is not None:
        filter_bits.append(f"u0={result.indexed_unknown_0_filter}")
    if result.indexed_unknown_1_filter is not None:
        filter_bits.append(f"u1={result.indexed_unknown_1_filter}")
    if result.indexed_unknown_9_filter is not None:
        filter_bits.append(f"u9={result.indexed_unknown_9_filter}")
    if result.indexed_unknown_10_filter is not None:
        filter_bits.append(f"u10={result.indexed_unknown_10_filter}")
    if result.attribute_0_filter is not None:
        filter_bits.append(f"a0={result.attribute_0_filter}")
    if result.attribute_1_filter is not None:
        filter_bits.append(f"a1={result.attribute_1_filter}")
    if result.attribute_2_filter is not None:
        filter_bits.append(f"a2={result.attribute_2_filter}")
    if getattr(result, "post_weight_byte_filter", None) is not None:
        filter_bits.append(f"postwt={getattr(result, 'post_weight_byte_filter', None)}")
    if result.trailer_byte_filter is not None:
        filter_bits.append(f"trail={result.trailer_byte_filter}")
    if getattr(result, "sidecar_byte_filter", None) is not None:
        filter_bits.append(f"sidecar={getattr(result, 'sidecar_byte_filter', None)}")
    filter_text = f" [{' '.join(filter_bits)}]" if filter_bits else ""
    print(
        f"Indexed tail-prefix profile{filter_text}: "
        f"anchored={result.anchored_count}, filtered={result.filtered_count}, indexed_entries={result.record_count}"
    )
    print(
        "  status=read-only structural signature / sidecar block "
        + "(the post-weight byte is fixed at [player+0x48] and acts as a secondary nationality/search key: "
        + "FUN_0043d960 is called from the search-options builder against the same 0x4B2E90 nationality table "
        + "used by the player-view nationality label, "
        + "two post-attribute bytes are discrete and rendered separately in DBASEPRE UI paths, "
        + "then the remainder is copied in bulk; "
        + "no fixed named offsets proven)"
    )
    print(
        "  layout="
        + f"verified={int(getattr(result, 'layout_verified_count', 0) or 0)} "
        + f"mismatch={int(getattr(result, 'layout_mismatch_count', 0) or 0)} "
        + "(attr0..2 in final variable block, attr3..11 in fixed trailer when verified)"
    )
    attr0_text = _format_profile_count_summary(getattr(result, "attribute_0_counts", []), label="a0")
    if attr0_text:
        print(f"  attr0={attr0_text}")
    attr1_text = _format_profile_count_summary(getattr(result, "attribute_1_counts", []), label="a1")
    if attr1_text:
        print(f"  attr1={attr1_text}")
    attr2_text = _format_profile_count_summary(getattr(result, "attribute_2_counts", []), label="a2")
    if attr2_text:
        print(f"  attr2={attr2_text}")
    post_weight_text = _format_profile_count_summary(
        getattr(result, "post_weight_byte_counts", []),
        label="postwt",
    )
    if post_weight_text:
        print(f"  post_weight={post_weight_text}")
    post_weight_nat_eligible = int(getattr(result, "post_weight_nationality_eligible_count", 0) or 0)
    if post_weight_nat_eligible:
        post_weight_nat_match = int(getattr(result, "post_weight_nationality_match_count", 0) or 0)
        post_weight_nat_ratio = float(getattr(result, "post_weight_nationality_match_ratio", 0.0) or 0.0)
        print(
            "  post_weight_vs_nat="
            + f"match={post_weight_nat_match}/{post_weight_nat_eligible} "
            + f"ratio={post_weight_nat_ratio:.4f}"
        )
        divergent_text = _format_profile_count_summary(
            getattr(result, "post_weight_divergent_counts", []),
            label="postwt",
            limit=5,
        )
        if divergent_text:
            print(f"  post_weight_group_keys={divergent_text}")
        mismatch_pairs = list(getattr(result, "post_weight_nationality_mismatch_pairs", []) or [])[:5]
        if mismatch_pairs:
            mismatch_text = ", ".join(
                f"postwt={post_value}->nat={nat_value}({count})"
                for post_value, nat_value, count in mismatch_pairs
            )
            print(f"  post_weight_mismatches={mismatch_text}")
    trailer_text = _format_profile_count_summary(getattr(result, "trailer_byte_counts", []), label="trail")
    if trailer_text:
        print(f"  trailer={trailer_text}")
    sidecar_entries = list(getattr(result, "sidecar_byte_counts", []) or [])[:4]
    if sidecar_entries:
        sidecar_text = ", ".join(f"{value}({count})" for value, count in sidecar_entries)
        print(f"  sidecar0={sidecar_text}")
    for bucket in result.buckets:
        names = ", ".join(bucket.sample_names)
        suffix = f" examples={names}" if names else ""
        print(
            f"  tail_prefix=[{bucket.attribute_0}, {bucket.attribute_1}, {bucket.attribute_2}]: "
            f"count={bucket.count}{suffix}"
        )
    for bucket in list(getattr(result, "signature_buckets", []) or []):
        names = ", ".join(bucket.sample_names)
        suffix = f" examples={names}" if names else ""
        print(
            f"  tail_signature=[{bucket.attribute_0}, {bucket.attribute_1}, {bucket.attribute_2} | "
            f"trail={bucket.trailer_byte} sidecar={getattr(bucket, 'sidecar_byte', None)}]: "
            f"count={bucket.count}{suffix}"
        )


def _format_profile_count_summary(entries, *, label: str, limit: int = 4) -> str:
    summary_parts = []
    for value, count in list(entries or [])[: max(1, int(limit or 4))]:
        summary_parts.append(f"{label}={value}({count})")
    return ", ".join(summary_parts)


def _player_u1_display_hint(indexed_unknown_1) -> str:
    """Return a cautious UI-color hint for indexed suffix byte +1."""
    hint_map = {
        0: "ui-grey",
        1: "ui-green",
        2: "ui-red",
        4: "ui-green(alias)",
    }
    return hint_map.get(indexed_unknown_1, "")


def _player_leading_guard_hint(indexed_unknown_0, indexed_unknown_1) -> str:
    """Return a cautious reserved/exclusion hint for leading indexed suffix bytes."""
    parts = []
    if isinstance(indexed_unknown_0, int) and indexed_unknown_0 >= 0x62:
        parts.append("u0-reserved?")
    if indexed_unknown_1 == 3:
        parts.append("u1-excluded?")
    return "+".join(parts)


def _player_suffix_pair_hint(indexed_unknown_9, indexed_unknown_10) -> str:
    """Return a cautious appearance-oriented working hypothesis for indexed suffix bytes."""
    tone_hint_map = {
        1: "light-skin?",
        2: "medium/dark-skin?",
        3: "dark-skin?",
    }
    hair_hint_map = {
        1: "fair/blond?",
        3: "black/very-dark?",
        5: "red/auburn?",
        6: "brown/dark-brown?",
    }
    tone_hint = tone_hint_map.get(indexed_unknown_9)
    hair_hint = hair_hint_map.get(indexed_unknown_10)
    if tone_hint and hair_hint:
        return f"{tone_hint}+{hair_hint}"
    if tone_hint:
        return tone_hint
    if hair_hint:
        return hair_hint
    return ""


def _find_enclosing_decoded_entry(file_bytes: bytes, target_offset: int):
    """
    Return (entry_offset, decoded_payload, encoded_length) for the sequential FDI entry
    that contains `target_offset`, or None if no enclosing entry is found.
    """
    offset = 0x400
    data_len = len(file_bytes)
    while offset + 2 <= data_len:
        length = int.from_bytes(file_bytes[offset:offset + 2], "little")
        if length <= 0 or offset + 2 + length > data_len:
            offset += 1
            continue
        start = offset + 2
        end = start + length
        if start <= target_offset < end:
            try:
                decoded, enc_len = decode_entry(file_bytes, offset)
            except Exception:
                return None
            return offset, decoded, enc_len
        offset = end
    return None


def _scan_entry_ranges(file_bytes: bytes):
    """Return sequentially decoded entry ranges: [(entry_offset, payload_start, payload_end, length)]."""
    ranges = []
    offset = 0x400
    data_len = len(file_bytes)
    while offset + 2 <= data_len:
        length = int.from_bytes(file_bytes[offset:offset + 2], "little")
        if length <= 0 or offset + 2 + length > data_len:
            offset += 1
            continue
        start = offset + 2
        end = start + length
        ranges.append((offset, start, end, length))
        offset = end
    return ranges


def _entry_for_payload_offset(entry_ranges, entry_starts, payload_offset: int):
    """Return entry tuple containing `payload_offset`, or None."""
    if not entry_ranges:
        return None
    idx = bisect.bisect_right(entry_starts, payload_offset) - 1
    if idx < 0:
        return None
    entry = entry_ranges[idx]
    _, start, end, _ = entry
    if start <= payload_offset < end:
        return entry
    return None


def _find_name_center_in_text(text: str, name: str, preferred_index: int | None = None, radius: int = 400) -> int:
    """Best-effort case-insensitive location of a player name in decoded text."""
    if not text:
        return -1
    name = (name or "").strip()
    if not name:
        return preferred_index if preferred_index is not None else -1

    upper_text = text.upper()
    upper_name = name.upper()
    if preferred_index is not None and preferred_index >= 0:
        lo = max(0, preferred_index - radius)
        hi = min(len(text), preferred_index + radius)
        rel = upper_text[lo:hi].find(upper_name)
        if rel != -1:
            return lo + rel
        return preferred_index

    return upper_text.find(upper_name)


_CLUB_LIKE_PATTERN = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+"
    r"(?:Town|City|United|Rovers|Wanderers|Albion|County|Athletic|Wednesday|Borough|Hotspur))"
    r"(?:\s*\(\d{2}\))?"
)


def _extract_nearby_club_mentions(text: str, center_index: int, window: int = 800, limit: int = 12):
    """Return club-like text mentions near `center_index`, ordered by proximity."""
    if center_index < 0:
        return []
    start = max(0, center_index - window)
    end = min(len(text), center_index + window)
    segment = text[start:end]
    mentions = []
    for match in _CLUB_LIKE_PATTERN.finditer(segment):
        abs_idx = start + match.start()
        raw_value = match.group(0)
        cleaned = re.sub(r"[^A-Za-z0-9()\s-]+", " ", raw_value)
        cleaned = " ".join(cleaned.split())
        if not cleaned:
            continue
        mentions.append(
            {
                "distance": abs(abs_idx - center_index),
                "index": abs_idx,
                "text": cleaned,
            }
        )
    mentions.sort(key=lambda item: (item["distance"], item["index"]))

    dedup = []
    seen = set()
    for item in mentions:
        key = item["text"].lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
        if len(dedup) >= limit:
            break
    return dedup


def _club_query_aliases(club_query: str) -> list[str]:
    """Generate query aliases (full + common abbreviations) for club mention matching."""
    cleaned = " ".join((club_query or "").split()).strip()
    if not cleaned:
        return []

    aliases: list[str] = [cleaned]
    normalized = _normalize_club_mention(cleaned)
    if normalized and normalized.lower() != cleaned.lower():
        aliases.append(normalized)

    match = re.match(
        r"^(?P<base>.+?)\s+(?P<suffix>City|Town|United|Rovers|Wanderers|Albion|County|Athletic|Hotspur|Rangers|Alexandra)$",
        normalized or cleaned,
        flags=re.IGNORECASE,
    )
    if match:
        base = " ".join(match.group("base").split())
        suffix = match.group("suffix")
        aliases.append(base)
        aliases.append(f"{base} {suffix[0].upper()}.")
        aliases.append(f"{base} {suffix[0].upper()}")

    # Acronyms help with labels and blobs such as "QPR" / "WBA".
    tokens = re.findall(r"[A-Za-z]+", normalized or cleaned)
    if len(tokens) >= 3:
        acronym = "".join(token[0].upper() for token in tokens if token)
        if len(acronym) >= 3:
            aliases.append(acronym)
            aliases.append(".".join(acronym) + ".")

    dedup: list[str] = []
    seen = set()
    for alias in aliases:
        key = alias.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(alias)
    return dedup


def _extract_query_mentions(
    text: str,
    center_index: int,
    aliases: list[str],
    window: int = 800,
    limit: int = 12,
):
    """Extract direct query alias mentions near a player occurrence (supports abbreviations like 'Stoke C.')."""
    if center_index < 0 or not text or not aliases:
        return []

    start = max(0, center_index - window)
    end = min(len(text), center_index + window)
    segment = text[start:end]
    mentions = []
    seen = set()
    for alias in aliases:
        if not alias:
            continue
        pattern = re.compile(re.escape(alias), flags=re.IGNORECASE)
        for match in pattern.finditer(segment):
            abs_idx = start + match.start()
            matched_text = " ".join(match.group(0).split())
            if not matched_text:
                continue
            alias_kind = "full"
            normalized_alias = _normalize_club_mention(alias)
            normalized_match = _normalize_club_mention(matched_text)
            if normalized_match != normalized_alias:
                alias_kind = "variant"
            if alias.endswith(".") or re.search(r"\b[A-Z]\.?$", alias):
                alias_kind = "abbrev"
            if len(alias.split()) == 1:
                alias_kind = "root"

            key = (abs_idx, normalized_match.lower(), alias_kind)
            if key in seen:
                continue
            seen.add(key)
            mentions.append(
                {
                    "distance": abs(abs_idx - center_index),
                    "index": abs_idx,
                    "text": matched_text,
                    "alias_kind": alias_kind,
                    "match_source": "query_alias",
                }
            )

    mentions.sort(key=lambda item: (item["distance"], item["index"]))
    return mentions[:limit]


def _normalize_club_mention(value: str) -> str:
    """Normalize club mention text for grouping (e.g. strip year suffixes)."""
    cleaned = " ".join((value or "").split()).strip()
    if not cleaned:
        return ""
    cleaned = re.sub(r"\s*\(\d{2}\)\s*$", "", cleaned)
    return cleaned


def _adjust_confidence_for_mention_kind(score: float, mention_kind: str | None) -> float:
    """Apply a small penalty for weaker (abbrev/root) mention matches."""
    penalty = 0.0
    if mention_kind == "abbrev":
        penalty = 0.07
    elif mention_kind == "root":
        penalty = 0.15
    elif mention_kind == "variant":
        penalty = 0.05
    return round(max(0.0, min(1.0, float(score) - penalty)), 4)


def _normalize_team_name_for_match(value: str) -> str:
    """Normalize team names for loose cross-file matching."""
    cleaned = _normalize_club_mention(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def _association_score(distance: int, window: int, association_type: str) -> float:
    """
    Score club association confidence from proximity and evidence type.

    association_type:
      - strict_subrecord_context
      - heuristic_blob_context
    """
    if window <= 0:
        window = 1
    norm = max(0.0, min(1.0, 1.0 - (float(distance) / float(window))))
    if association_type == "strict_subrecord_context":
        # Higher baseline confidence; distance adjusts within a narrow range.
        score = 0.65 + (0.35 * norm)
    else:
        # Heuristic context is useful but weaker evidence.
        score = 0.20 + (0.45 * norm)
    return round(max(0.0, min(1.0, score)), 4)


def _association_band(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def _build_club_index_rows(club_query: str, strict_hits: list[dict], heuristic_hits: list[dict]) -> list[dict]:
    """Aggregate per-hit evidence into a ranked club->players index for a single club query."""
    normalized_club = _normalize_club_mention(club_query)
    by_name: dict[str, dict] = {}
    for hit in strict_hits + heuristic_hits:
        name = hit.get("name") or ""
        key = name.upper()
        if not key:
            continue
        row = by_name.get(key)
        if row is None:
            row = {
                "club_query": club_query,
                "club_normalized": normalized_club,
                "player_name": name,
                "best_confidence_score": hit.get("confidence_score", 0.0),
                "best_confidence_band": hit.get("confidence_band", "low"),
                "best_association_type": hit.get("association_type", ""),
                "best_offset": hit.get("offset"),
                "evidence_count": 0,
                "strict_evidence_count": 0,
                "heuristic_evidence_count": 0,
                "team_ids": [],
                "strict_subrecord_group_bytes": [],
                "mentions": [],
                "offsets": [],
            }
            by_name[key] = row

        row["evidence_count"] += 1
        if hit.get("association_type") == "strict_subrecord_context":
            row["strict_evidence_count"] += 1
        else:
            row["heuristic_evidence_count"] += 1

        off = hit.get("offset")
        if off is not None and off not in row["offsets"]:
            row["offsets"].append(off)

        team_id = hit.get("team_id")
        if team_id is not None and team_id not in row["team_ids"]:
            row["team_ids"].append(team_id)

        group_byte = hit.get("subrecord_group_byte")
        if isinstance(group_byte, int) and group_byte not in row["strict_subrecord_group_bytes"]:
            row["strict_subrecord_group_bytes"].append(group_byte)

        for mention in hit.get("target_mentions", []) or []:
            norm_mention = _normalize_club_mention(mention)
            if norm_mention and norm_mention not in row["mentions"]:
                row["mentions"].append(norm_mention)

        score = float(hit.get("confidence_score", 0.0) or 0.0)
        if score > float(row["best_confidence_score"]):
            row["best_confidence_score"] = score
            row["best_confidence_band"] = hit.get("confidence_band", row["best_confidence_band"])
            row["best_association_type"] = hit.get("association_type", row["best_association_type"])
            row["best_offset"] = hit.get("offset", row["best_offset"])

    rows = list(by_name.values())
    rows.sort(key=lambda item: (-float(item["best_confidence_score"]), item["player_name"]))
    return rows


def _infer_teams_file_for_player_file(player_file: str) -> Path | None:
    player_path = Path(player_file)
    candidate = player_path.with_name("EQ98030.FDI")
    if candidate.exists():
        return candidate
    return None


def _resolve_club_query_to_teams(club_query: str, teams_file: str | None) -> list[dict]:
    """Resolve a club query to known team records (derived linkage, not player-record decode)."""
    if not teams_file:
        return []

    try:
        import contextlib
        import io

        # Team loaders currently print progress/noise; suppress to keep JSON output clean.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            valid, uncertain = gather_team_records(teams_file)
    except Exception:
        return []

    query_norm = _normalize_team_name_for_match(club_query)
    if not query_norm:
        return []

    rows: list[dict] = []
    seen: set[tuple[int | None, str]] = set()
    for entry in valid + uncertain:
        team_name = _team_display_name(entry.record)
        team_norm = _normalize_team_name_for_match(team_name)
        if not team_norm:
            continue

        if team_norm == query_norm:
            match_kind = "exact"
            match_score = 1.0
        elif query_norm in team_norm or team_norm in query_norm:
            match_kind = "substring"
            match_score = 0.75
        else:
            continue

        team_id = getattr(entry.record, "team_id", None)
        key = (team_id, team_norm)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "team_id": team_id,
                "team_name": team_name,
                "offset": entry.offset,
                "source": entry.source,
                "match_kind": match_kind,
                "match_score": match_score,
            }
        )

    rows.sort(key=lambda item: (-float(item["match_score"]), item["team_name"]))
    return rows


def _probe_player_subrecord_header(record) -> dict:
    """
    Extract lightweight header bytes from strict player subrecords for reverse-engineering.

    This does not decode a canonical team ID; it exposes stable bytes so we can cluster
    players within a club container while the subrecord layout is still under investigation.
    """
    raw = bytes(getattr(record, "original_raw_data", b"") or b"")
    if not raw:
        return {}

    probe = {
        "subrecord_prefix_hex": raw[:8].hex(),
        "subrecord_length": len(raw),
    }
    if raw.startswith(bytes([0xDD, 0x63, 0x60])):
        probe["subrecord_separator"] = "dd6360"
        if len(raw) >= 6:
            probe["subrecord_header_byte3"] = raw[3]
            probe["subrecord_group_byte"] = raw[4]
            probe["subrecord_header_byte5"] = raw[5]
            probe["subrecord_header_word_3_4_le"] = raw[3] | (raw[4] << 8)
    return probe


def _export_club_investigate_json(payload: dict, output_path: Path) -> None:
    output_path.write_text(json.dumps(_jsonable(payload), indent=2), encoding="utf-8")


def _export_club_investigate_csv(payload: dict, output_path: Path) -> None:
    import csv

    rows = payload.get("club_index", []) or []
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "club_query",
                "club_normalized",
                "player_name",
                "best_confidence_score",
                "best_confidence_band",
                "best_association_type",
                "best_offset_hex",
                "evidence_count",
                "strict_evidence_count",
                "heuristic_evidence_count",
                "team_ids",
                "strict_subrecord_group_bytes",
                "derived_team_ids",
                "derived_team_names",
                "derived_team_linkage",
                "mentions",
            ]
        )
        for row in rows:
            best_offset = row.get("best_offset")
            writer.writerow(
                [
                    row.get("club_query", ""),
                    row.get("club_normalized", ""),
                    row.get("player_name", ""),
                    row.get("best_confidence_score", ""),
                    row.get("best_confidence_band", ""),
                    row.get("best_association_type", ""),
                    (f"0x{int(best_offset):08X}" if isinstance(best_offset, int) else ""),
                    row.get("evidence_count", 0),
                    row.get("strict_evidence_count", 0),
                    row.get("heuristic_evidence_count", 0),
                    ",".join(str(v) for v in row.get("team_ids", [])),
                    ",".join(f"0x{int(v):02X}" for v in row.get("strict_subrecord_group_bytes", [])),
                    ",".join(str(v) for v in row.get("derived_team_ids", [])),
                    "; ".join(row.get("derived_team_names", [])),
                    row.get("derived_team_linkage", ""),
                    "; ".join(row.get("mentions", [])),
                ]
            )


def _export_club_investigate(payload: dict, export_path: str) -> Path:
    output_path = Path(export_path)
    if output_path.suffix.lower() == ".csv":
        _export_club_investigate_csv(payload, output_path)
    else:
        _export_club_investigate_json(payload, output_path)
    return output_path

def cmd_info(args):
    """Display file information"""
    fdi = FDIFile(args.file)
    fdi.load()
    print(f"File: {args.file}")
    print(f"Records: {len(fdi.records)}")
    print(f"Header: {fdi.header}")


def cmd_validate_database(args):
    """Re-open one or more database files through the shared parser-backed loaders."""
    if not any((getattr(args, "players", None), getattr(args, "teams", None), getattr(args, "coaches", None))):
        print("Error: provide at least one of --players, --teams, or --coaches", file=sys.stderr)
        raise SystemExit(1)

    result = validate_database_files(
        player_file=getattr(args, "players", None),
        team_file=getattr(args, "teams", None),
        coach_file=getattr(args, "coaches", None),
    )
    if getattr(args, "json", False):
        _emit(result, as_json=True)
    else:
        _print_database_validation_result(result)
    if not getattr(result, "all_valid", False):
        raise SystemExit(1)


def cmd_main_dat_inspect(args):
    """Inspect the parser-backed, currently confirmed `main.dat` prefix."""
    result = inspect_main_dat_prefix(file_path=str(args.file))

    if getattr(args, "json", False):
        _emit(result.raw_payload, as_json=True)
        return

    print(f"File: {args.file}")
    print(
        "Header: "
        f"0x{result.header_version:08X}"
        + (" (expected)" if result.header_matches_expected else " (unexpected)")
    )
    print(
        "Format: "
        f"0x{result.format_version:08X}"
        + (" (passes reader guard)" if result.format_passes_guard else " (fails reader guard)")
    )
    print(f"Primary label: {result.primary_label!r}")
    print(f"Secondary label: {result.secondary_label!r}")
    print(
        "Save date/time: "
        f"{result.save_date['year']:04d}-{result.save_date['month']:02d}-{result.save_date['day']:02d} "
        f"{result.time_fields['hour']:02d}:{result.time_fields['minute']:02d}"
    )
    print("Flag bytes: " + " ".join(f"0x{value:02X}" for value in result.flag_bytes))
    print(f"Scalar byte: 0x{result.scalar_byte:02X}")
    if result.extended_prelude is None:
        print("Extended prelude: not present")
    else:
        print(
            "Extended prelude: "
            f"0x{result.extended_prelude['global_byte_a']:02X} "
            f"0x{result.extended_prelude['global_byte_b']:02X}, "
            f"{result.extended_prelude['secondary_date']['year']:04d}-"
            f"{result.extended_prelude['secondary_date']['month']:02d}-"
            f"{result.extended_prelude['secondary_date']['day']:02d}"
        )
    print(f"Opaque unresolved tail: {result.opaque_tail_size} byte(s)")


def _parse_main_dat_flag_updates(items):
    updates = {}
    for raw_item in items or []:
        text = str(raw_item).strip()
        if "=" not in text:
            raise ValueError(f"Invalid --flag-byte value {raw_item!r}; expected INDEX=VALUE")
        raw_index, raw_value = text.split("=", 1)
        index = int(raw_index.strip(), 0)
        value = int(raw_value.strip(), 0)
        updates[index] = value
    return updates


def cmd_main_dat_edit(args):
    """Edit confirmed `main.dat` prefix fields while preserving unknown blocks."""
    if getattr(args, "in_place", False) and getattr(args, "output_file", None):
        raise ValueError("--in-place cannot be combined with --output-file")

    flag_updates = _parse_main_dat_flag_updates(getattr(args, "flag_byte", []))
    requested_updates = {
        "primary_label": getattr(args, "primary_label", None),
        "secondary_label": getattr(args, "secondary_label", None),
        "day": getattr(args, "day", None),
        "month": getattr(args, "month", None),
        "year": getattr(args, "year", None),
        "hour": getattr(args, "hour", None),
        "minute": getattr(args, "minute", None),
        "scalar_byte": getattr(args, "scalar_byte", None),
        "flag_updates": flag_updates or None,
    }
    if all(value is None for value in requested_updates.values()):
        raise ValueError("No changes requested. Provide at least one editable main.dat prefix field.")

    result = patch_main_dat_prefix(
        file_path=str(args.file),
        primary_label=requested_updates["primary_label"],
        secondary_label=requested_updates["secondary_label"],
        day=requested_updates["day"],
        month=requested_updates["month"],
        year=requested_updates["year"],
        hour=requested_updates["hour"],
        minute=requested_updates["minute"],
        scalar_byte=requested_updates["scalar_byte"],
        flag_updates=requested_updates["flag_updates"],
        output_file=getattr(args, "output_file", None),
        in_place=bool(getattr(args, "in_place", False)),
        create_backup_before_write=not bool(getattr(args, "no_backup", False)),
    )

    if getattr(args, "json", False):
        _emit(result.raw_payload, as_json=True)
        return

    print(f"Input: {result.input_file}")
    print(f"Output: {result.output_file}")
    if result.backup_path is not None:
        print(f"Backup: {result.backup_path}")
    print("Changed fields: " + ", ".join(result.changed_fields))
    print(f"Opaque unresolved tail preserved: {result.opaque_tail_size} byte(s)")

def cmd_list(args):
    """List players"""
    valid, uncertain = _gather_player_entries_for_cli(args)
    entries = valid + (uncertain if getattr(args, "include_uncertain", False) else [])
    if args.limit:
        entries = entries[:args.limit]
    if getattr(args, "json", False):
        _emit([_player_entry_payload(e) for e in entries], as_json=True)
        return
    for entry in entries:
        print(f"0x{entry.offset:08X}: {_player_display_name(entry.record)} ({getattr(entry.record, 'team_id', '')}) [{entry.source}]")

def cmd_search(args):
    """Search players by name"""
    query = (args.name or "").strip().lower()
    valid, uncertain = _gather_player_entries_for_cli(args)
    entries = valid + (uncertain if getattr(args, "include_uncertain", False) else [])
    matches = [e for e in entries if query in _player_display_name(e.record).lower()]
    if getattr(args, "json", False):
        _emit([_player_entry_payload(e) for e in matches], as_json=True)
        return
    for entry in matches:
        print(f"0x{entry.offset:08X}: {_player_display_name(entry.record)} ({getattr(entry.record, 'team_id', '')}) [{entry.source}]")

def cmd_rename(args):
    """Legacy compatibility alias: resolve one player by ID, then use the shared rename path."""
    fdi = FDIFile(args.file)
    fdi.load()
    target_offset = _parse_int_auto(getattr(args, "offset", None))
    file_bytes = getattr(fdi, "file_data", None)
    target = None
    fallback_target = None
    for offset, record in fdi.list_players():
        if target_offset is not None and offset == target_offset:
            target = (offset, record)
            break
        if target_offset is None and getattr(record, "team_id", None) == args.id:
            display = _player_display_name(record)
            if _player_offset_is_writable(file_bytes, offset, display):
                target = (offset, record)
                break
            if fallback_target is None:
                fallback_target = (offset, record)
    if target is None:
        target = fallback_target
    if not target:
        print(f"Player {args.id} not found")
        return

    offset, record = target
    old_name = _player_display_name(record)
    if not _player_offset_is_writable(file_bytes, offset, old_name):
        print(f"Refusing to rename player at 0x{offset:08X}: offset is not a writable FDI entry boundary")
        return

    result = rename_player_records(
        file_path=args.file,
        target_old=old_name,
        new_name=args.name,
        include_uncertain=True,
        target_offset=offset,
        write_changes=True,
    )
    _print_player_rename_result(result, dry_run=False)


def cmd_player_list(args):
    cmd_list(args)


def cmd_player_search(args):
    cmd_search(args)


def cmd_player_investigate(args):
    query = (args.name or "").strip()
    lower_query = query.lower()

    heuristic_valid, heuristic_uncertain = gather_player_records_heuristic(args.file)
    strict_valid, strict_uncertain = gather_player_records_strict(args.file)
    strict_tid_valid, strict_tid_uncertain = gather_player_records_strict(args.file, require_team_id=True)

    heuristic_hits = [e for e in (heuristic_valid + heuristic_uncertain) if lower_query in _player_display_name(e.record).lower()]
    strict_hits = [e for e in (strict_valid + strict_uncertain) if lower_query in _player_display_name(e.record).lower()]
    strict_tid_hits = [e for e in (strict_tid_valid + strict_tid_uncertain) if lower_query in _player_display_name(e.record).lower()]

    file_bytes = Path(args.file).read_bytes()
    strict_offsets = {e.offset for e in strict_hits}
    investigations = []
    for entry in heuristic_hits:
        inv = {
            "offset": entry.offset,
            "name": _player_display_name(entry.record),
            "team_id": getattr(entry.record, "team_id", None),
            "squad_number": getattr(entry.record, "squad_number", None),
            "source": entry.source,
            "is_strict_match": entry.offset in strict_offsets,
        }
        enclosing = _find_enclosing_decoded_entry(file_bytes, entry.offset)
        if enclosing:
            entry_offset, decoded, enc_len = enclosing
            rel = entry.offset - (entry_offset + 2)
            text = decoded.decode("latin-1", errors="ignore")
            center = text.lower().find(lower_query)
            if center == -1 and rel >= 0:
                center = max(0, min(len(text), rel))
            inv["enclosing_entry_offset"] = entry_offset
            inv["enclosing_entry_length"] = enc_len
            inv["nearby_club_mentions"] = _extract_nearby_club_mentions(text, center, window=getattr(args, "context", 800))
            inv["name_occurrences_in_entry"] = text.lower().count(lower_query)
        investigations.append(inv)

    payload = {
        "query": query,
        "heuristic_matches": [_player_entry_payload(e) for e in heuristic_hits],
        "strict_matches": [_player_entry_payload(e) for e in strict_hits],
        "strict_team_matches": [_player_entry_payload(e) for e in strict_tid_hits],
        "investigations": investigations,
    }

    if args.json:
        _emit(payload, as_json=True)
        return

    print(f"Query: {query}")
    print(f"Heuristic matches: {len(heuristic_hits)}")
    print(f"Strict matches (entries + subrecords): {len(strict_hits)}")
    print(f"Strict matches with team_id != 0: {len(strict_tid_hits)}")
    for inv in investigations:
        print(f"  0x{inv['offset']:08X}: {inv['name']} team_id={inv['team_id']} source={inv['source']}")
        if inv.get("enclosing_entry_offset") is not None:
            print(
                f"    enclosing entry: 0x{inv['enclosing_entry_offset']:08X} len={inv['enclosing_entry_length']} "
                f"(strict_match={inv['is_strict_match']})"
            )
        mentions = inv.get("nearby_club_mentions") or []
        if mentions:
            print("    nearby club-like mentions:")
            for item in mentions[:8]:
                print(f"      - {item['text']} (distance={item['distance']})")


def cmd_club_investigate(args):
    club_query = " ".join((args.club or "").split()).strip()
    if not club_query:
        print("Club query cannot be empty.", file=sys.stderr)
        return
    club_query_norm = club_query.lower()
    strict_window = max(1, int(getattr(args, "context", 300) or 300))
    heuristic_window = max(1, int(getattr(args, "heuristic_context", 800) or 800))
    club_query_aliases = _club_query_aliases(club_query)
    club_query_aliases_lower = [a.lower() for a in club_query_aliases if a]

    file_bytes = Path(args.file).read_bytes()
    entry_ranges = _scan_entry_ranges(file_bytes)
    entry_starts = [start for _, start, _, _ in entry_ranges]

    # Decode only entries that contain the club string.
    target_entries = {}
    for entry_offset, _start, _end, _length in entry_ranges:
        try:
            decoded, enc_len = decode_entry(file_bytes, entry_offset)
        except Exception:
            continue
        text = decoded.decode("latin-1", errors="ignore")
        lower_text = text.lower()
        if any(alias in lower_text for alias in club_query_aliases_lower):
            target_entries[entry_offset] = {
                "decoded": decoded,
                "text": text,
                "length": enc_len,
            }

    strict_valid, strict_uncertain = gather_player_records_strict(args.file)
    strict_hits = []
    strict_seen_names = set()
    for entry in strict_valid + strict_uncertain:
        record = entry.record
        container_offset = getattr(record, "container_offset", None)
        if not isinstance(container_offset, int) or container_offset not in target_entries:
            continue

        text = target_entries[container_offset]["text"]
        rel = getattr(record, "container_relative_offset", None)
        preferred_index = int(rel) if isinstance(rel, int) else None
        original_sub = bytes(getattr(record, "original_raw_data", b"") or b"")
        name = _player_display_name(record)
        name_bytes = name.encode("latin-1", errors="ignore")
        if preferred_index is not None and original_sub and name_bytes:
            idx_sub = original_sub.upper().find(name_bytes.upper())
            if idx_sub != -1:
                preferred_index = preferred_index + idx_sub
        center = _find_name_center_in_text(text, name, preferred_index=preferred_index)
        mentions = _extract_nearby_club_mentions(text, center, window=strict_window, limit=12)
        alias_mentions = _extract_query_mentions(text, center, club_query_aliases, window=strict_window, limit=12)
        target_mentions = [m for m in mentions if club_query_norm in m["text"].lower()]
        # Merge alias/direct-query matches (e.g. "Stoke", "Stoke C.") with club-like matches.
        seen_tm = {(m["index"], m["text"].lower()) for m in target_mentions}
        for m in alias_mentions:
            key = (m["index"], m["text"].lower())
            if key in seen_tm:
                continue
            seen_tm.add(key)
            target_mentions.append(m)
        target_mentions.sort(key=lambda item: (item["distance"], item["index"]))
        if not target_mentions:
            continue

        key = (name.upper(), entry.offset)
        if key in strict_seen_names:
            continue
        strict_seen_names.add(key)
        nearest_distance = target_mentions[0]["distance"]
        confidence = _association_score(nearest_distance, strict_window, "strict_subrecord_context")
        confidence = _adjust_confidence_for_mention_kind(confidence, target_mentions[0].get("alias_kind"))
        hit = {
            "name": name,
            "offset": entry.offset,
            "container_offset": container_offset,
            "team_id": getattr(record, "team_id", None),
            "squad_number": getattr(record, "squad_number", None),
            "source": entry.source,
            "nearest_target_mention": target_mentions[0]["text"],
            "nearest_target_distance": nearest_distance,
            "target_mentions": [m["text"] for m in target_mentions[:5]],
            "nearest_target_alias_kind": target_mentions[0].get("alias_kind"),
            "association_type": "strict_subrecord_context",
            "confidence_score": confidence,
            "confidence_band": _association_band(confidence),
        }
        hit.update(_probe_player_subrecord_header(record))
        strict_hits.append(hit)

    heuristic_hits = []
    if getattr(args, "include_heuristic", False):
        heuristic_valid, heuristic_uncertain = gather_player_records_heuristic(args.file)
        all_heuristic = heuristic_valid + heuristic_uncertain
        strict_offsets = {entry["offset"] for entry in strict_hits}
        heuristic_seen = set()
        for entry in all_heuristic:
            if entry.offset in strict_offsets:
                continue
            enclosing = _entry_for_payload_offset(entry_ranges, entry_starts, entry.offset)
            if not enclosing:
                continue
            entry_offset, payload_start, _payload_end, _entry_length = enclosing
            if entry_offset not in target_entries:
                continue

            text = target_entries[entry_offset]["text"]
            rel = entry.offset - payload_start
            name = _player_display_name(entry.record)
            center = _find_name_center_in_text(text, name, preferred_index=rel)
            mentions = _extract_nearby_club_mentions(text, center, window=heuristic_window, limit=12)
            alias_mentions = _extract_query_mentions(text, center, club_query_aliases, window=heuristic_window, limit=12)
            target_mentions = [m for m in mentions if club_query_norm in m["text"].lower()]
            seen_tm = {(m["index"], m["text"].lower()) for m in target_mentions}
            for m in alias_mentions:
                key = (m["index"], m["text"].lower())
                if key in seen_tm:
                    continue
                seen_tm.add(key)
                target_mentions.append(m)
            target_mentions.sort(key=lambda item: (item["distance"], item["index"]))
            if not target_mentions:
                continue

            key = (name.upper(), entry.offset)
            if key in heuristic_seen:
                continue
            heuristic_seen.add(key)
            nearest_distance = target_mentions[0]["distance"]
            confidence = _association_score(nearest_distance, heuristic_window, "heuristic_blob_context")
            confidence = _adjust_confidence_for_mention_kind(confidence, target_mentions[0].get("alias_kind"))
            heuristic_hits.append(
                {
                    "name": name,
                    "offset": entry.offset,
                    "enclosing_entry_offset": entry_offset,
                    "team_id": getattr(entry.record, "team_id", None),
                    "squad_number": getattr(entry.record, "squad_number", None),
                    "source": entry.source,
                    "nearest_target_mention": target_mentions[0]["text"],
                    "nearest_target_distance": nearest_distance,
                    "target_mentions": [m["text"] for m in target_mentions[:5]],
                    "nearest_target_alias_kind": target_mentions[0].get("alias_kind"),
                    "association_type": "heuristic_blob_context",
                    "confidence_score": confidence,
                    "confidence_band": _association_band(confidence),
                }
            )

    strict_hits.sort(key=lambda item: (-float(item.get("confidence_score", 0.0)), item["nearest_target_distance"], item["name"]))
    heuristic_hits.sort(key=lambda item: (-float(item.get("confidence_score", 0.0)), item["nearest_target_distance"], item["name"]))

    # Dedup by display name for summary views.
    strict_unique_names = []
    seen_names = set()
    for item in strict_hits:
        key = item["name"].upper()
        if key in seen_names:
            continue
        seen_names.add(key)
        strict_unique_names.append(item["name"])

    heuristic_unique_names = []
    seen_names = set()
    for item in heuristic_hits:
        key = item["name"].upper()
        if key in seen_names:
            continue
        seen_names.add(key)
        heuristic_unique_names.append(item["name"])

    combined_unique_names = []
    seen_names = set()
    for item in strict_hits + heuristic_hits:
        key = item["name"].upper()
        if key in seen_names:
            continue
        seen_names.add(key)
        combined_unique_names.append(item["name"])

    club_index = _build_club_index_rows(club_query, strict_hits, heuristic_hits)

    teams_file_arg = getattr(args, "teams_file", None)
    if teams_file_arg:
        teams_file_path = Path(teams_file_arg)
    else:
        teams_file_path = _infer_teams_file_for_player_file(args.file) if getattr(args, "resolve_team", True) else None

    resolved_teams = _resolve_club_query_to_teams(club_query, str(teams_file_path) if teams_file_path else None)
    team_resolution = {
        "enabled": bool(getattr(args, "resolve_team", True)),
        "teams_file": str(teams_file_path) if teams_file_path else None,
        "resolved_count": len(resolved_teams),
    }
    derived_team_ids = [row.get("team_id") for row in resolved_teams if row.get("team_id") is not None]
    derived_team_names = [row.get("team_name") for row in resolved_teams if row.get("team_name")]
    for row in club_index:
        row["derived_team_ids"] = list(derived_team_ids)
        row["derived_team_names"] = list(derived_team_names)
        row["derived_team_linkage"] = "query_to_team_record" if resolved_teams else "unresolved"

    confidence_summary = {
        "strict": {
            "high": sum(1 for h in strict_hits if h.get("confidence_band") == "high"),
            "medium": sum(1 for h in strict_hits if h.get("confidence_band") == "medium"),
            "low": sum(1 for h in strict_hits if h.get("confidence_band") == "low"),
        },
        "heuristic": {
            "high": sum(1 for h in heuristic_hits if h.get("confidence_band") == "high"),
            "medium": sum(1 for h in heuristic_hits if h.get("confidence_band") == "medium"),
            "low": sum(1 for h in heuristic_hits if h.get("confidence_band") == "low"),
        },
    }

    payload = {
        "club_query": club_query,
        "club_query_normalized": _normalize_club_mention(club_query),
        "club_query_aliases": club_query_aliases,
        "target_entry_count": len(target_entries),
        "team_resolution": team_resolution,
        "resolved_teams": resolved_teams,
        "strict_subrecord_context_matches": strict_hits,
        "heuristic_context_matches": heuristic_hits,
        "strict_unique_names": strict_unique_names,
        "heuristic_unique_names": heuristic_unique_names,
        "combined_unique_names": combined_unique_names,
        "club_index": club_index,
        "confidence_summary": confidence_summary,
    }

    export_path = getattr(args, "export", None)
    if export_path:
        written = _export_club_investigate(payload, export_path)
        if not getattr(args, "json", False):
            print(f"Exported club index to: {written}")

    if getattr(args, "json", False):
        _emit(payload, as_json=True)
        return

    print(f"Club query: {club_query}")
    print(f"Decoded entries containing club text: {len(target_entries)}")
    print(f"Strict subrecord context matches: {len(strict_hits)} (unique names: {len(strict_unique_names)})")
    for item in strict_hits[: args.limit]:
        group_suffix = ""
        if isinstance(item.get("subrecord_group_byte"), int):
            group_suffix = f"; grp=0x{int(item['subrecord_group_byte']):02X}"
        print(
            f"  0x{item['offset']:08X}: {item['name']} "
            f"[{item['nearest_target_mention']}; d={item['nearest_target_distance']}; {item['confidence_band']} {item['confidence_score']:.2f}] "
            f"(container 0x{item['container_offset']:08X}{group_suffix})"
        )

    if getattr(args, "include_heuristic", False):
        print(f"Heuristic context matches: {len(heuristic_hits)} (unique names: {len(heuristic_unique_names)})")
        for item in heuristic_hits[: args.limit]:
            print(
                f"  0x{item['offset']:08X}: {item['name']} "
                f"[{item['nearest_target_mention']}; d={item['nearest_target_distance']}; {item['confidence_band']} {item['confidence_score']:.2f}] "
                f"({item['source']}, entry 0x{item['enclosing_entry_offset']:08X})"
            )

    if resolved_teams:
        print(f"Resolved team record(s): {len(resolved_teams)}")
        for team in resolved_teams[:5]:
            team_id = team.get("team_id")
            off = team.get("offset")
            print(
                f"  team_id={team_id} {team['team_name']} "
                f"[{team['match_kind']} {team['match_score']:.2f}]"
                + (f" offset=0x{off:08X}" if isinstance(off, int) else "")
            )
    elif team_resolution["teams_file"]:
        print(
            f"Resolved team record(s): 0 (teams file scanned: {team_resolution['teams_file']}; "
            "current team parser coverage may be incomplete)"
        )

    print(f"Club index (ranked players): {len(club_index)}")
    for row in club_index[: args.limit]:
        best_offset = row.get("best_offset")
        offset_text = f"0x{best_offset:08X}" if isinstance(best_offset, int) else "n/a"
        print(
            f"  {row['player_name']} [{row['best_confidence_band']} {row['best_confidence_score']:.2f}; "
            f"{row['best_association_type']}; evidence={row['evidence_count']}; offset={offset_text}]"
        )

    print(f"Combined unique names: {len(combined_unique_names)}")


def cmd_roster_reconcile_pdf(args):
    from .roster_reconcile import (
        print_reconcile_run_summary,
        reconcile_pdf_rosters,
        write_reconcile_outputs,
    )

    result = reconcile_pdf_rosters(
        pdf_path=args.pdf,
        player_file=args.player_file,
        default_window=args.default_window,
        wide_window=args.wide_window,
        team_filter=getattr(args, "team", None),
        name_hints_path=getattr(args, "name_hints", None),
    )
    write_reconcile_outputs(
        result,
        json_output=args.json_output,
        csv_output=args.csv_output,
        team_summary_csv=getattr(args, "team_summary_csv", None),
    )
    print_reconcile_run_summary(result)


def cmd_player_rename(args):
    result = rename_player_records(
        file_path=args.file,
        target_old=args.old,
        new_name=args.new,
        include_uncertain=args.include_uncertain,
        target_offset=_parse_int_auto(args.offset),
        write_changes=not args.dry_run,
    )
    if args.json:
        _emit(result, as_json=True)
        return
    _print_player_rename_result(result, dry_run=args.dry_run)


def cmd_player_edit(args):
    try:
        result = edit_player_metadata_records(
            file_path=args.file,
            target_name=args.name,
            target_offset=_parse_int_auto(args.offset),
            new_name=args.new_name,
            position=args.position,
            nationality=args.nationality,
            birth_day=args.dob_day,
            birth_month=args.dob_month,
            birth_year=args.dob_year,
            height=args.height,
            weight=args.weight,
            write_changes=not args.dry_run,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result, as_json=True)
        return
    _print_player_metadata_edit_result(result, dry_run=args.dry_run)


def cmd_player_batch_edit(args):
    try:
        result = batch_edit_player_metadata_records(
            file_path=args.file,
            csv_path=args.csv,
            write_changes=not args.dry_run,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result, as_json=True)
        return
    _print_player_batch_edit_result(result, dry_run=args.dry_run)


def cmd_player_inspect(args):
    try:
        result = inspect_player_metadata_records(
            file_path=args.file,
            target_name=args.name,
            target_offset=_parse_int_auto(args.offset),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result, as_json=True)
        return
    _print_player_metadata_inspect_result(result)


def cmd_player_suffix_profile(args):
    try:
        result = profile_indexed_player_suffix_bytes(
            file_path=args.file,
            nationality=args.nationality,
            position=args.position,
            limit=args.limit,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result, as_json=True)
        return
    _print_player_suffix_profile_result(result)


def cmd_player_legacy_weight_profile(args):
    try:
        result = profile_player_legacy_weight_candidates(
            file_path=args.file,
            start_offset=max(1, int(getattr(args, "start_offset", 14) or 14)),
            end_offset=max(1, int(getattr(args, "end_offset", 18) or 18)),
            top_values=max(1, int(getattr(args, "top_values", 8) or 8)),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result, as_json=True)
        return
    _print_player_legacy_weight_profile_result(result)


def cmd_player_leading_profile(args):
    try:
        result = profile_indexed_player_leading_bytes(
            file_path=args.file,
            nationality=args.nationality,
            position=args.position,
            indexed_unknown_0=args.u0,
            indexed_unknown_1=args.u1,
            indexed_unknown_9=args.u9,
            indexed_unknown_10=args.u10,
            limit=args.limit,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result, as_json=True)
        return
    _print_player_leading_profile_result(result)


def cmd_player_tail_prefix_profile(args):
    try:
        result = profile_indexed_player_attribute_prefixes(
            file_path=args.file,
            nationality=args.nationality,
            position=args.position,
            indexed_unknown_0=args.u0,
            indexed_unknown_1=args.u1,
            indexed_unknown_9=args.u9,
            indexed_unknown_10=args.u10,
            attribute_0=args.a0,
            attribute_1=args.a1,
            attribute_2=args.a2,
            post_weight_byte=args.post_weight,
            trailer_byte=args.trail,
            sidecar_byte=args.sidecar,
            limit=args.limit,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result, as_json=True)
        return
    _print_player_attribute_prefix_profile_result(result)


def cmd_player_skill_patch(args):
    """
    Copy-safe patch for the verified dd6361 visible stat trailer mapping.

    This is intentionally scoped to the mapped10 visible stat block (core4 + 6 technicals)
    and does not attempt to edit dynamic lineup state (EN/MO/ROL/etc).
    """
    try:
        in_place = bool(getattr(args, "in_place", False))
        if getattr(args, "no_backup", False) and not in_place:
            print("Error: --no-backup only applies with --in-place", file=sys.stderr)
            raise SystemExit(1)
        if in_place and getattr(args, "output_file", None):
            print("Error: --in-place cannot be combined with --output-file", file=sys.stderr)
            raise SystemExit(1)
        updates = parse_player_skill_patch_assignments(getattr(args, "set_args", []) or [])
        result = patch_player_visible_skills_dd6361(
            file_path=args.file,
            player_name=args.name,
            updates=updates,
            output_file=None
            if in_place
            else (args.output_file or str(Path("/tmp") / "JUG98030.dd6361_patched.FDI")),
            in_place=in_place,
            create_backup_before_write=(in_place and not getattr(args, "no_backup", False)),
            json_output=getattr(args, "json_output", None),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result.raw_payload or result, as_json=True)
        return

    print(
        f"Patched dd6361 visible stats for {result.resolved_bio_name} "
        f"-> {result.output_file}"
    )
    if result.backup_path:
        print(f"Backup: {result.backup_path}")
    for field in result.mapped10_order:
        if field not in result.updates_requested:
            continue
        before = result.mapped10_before.get(field)
        after = result.mapped10_after.get(field)
        print(f"  {field}: {before} -> {after}")
    print(
        "Verification: "
        + ("ok" if result.verification_all_requested_fields_match else "FAILED")
    )
    touched_offsets = result.touched_entry_offsets
    if touched_offsets:
        preview = ", ".join(f"0x{int(off):08X}" for off in touched_offsets[:5])
        suffix = "" if len(touched_offsets) <= 5 else f" (+{len(touched_offsets) - 5} more)"
        print(f"Touched entries: {preview}{suffix}")
    if getattr(args, "json_output", None):
        print(f"Report: {args.json_output}")


def cmd_team_list(args):
    valid, uncertain = gather_team_records(args.file)
    entries = valid + (uncertain if args.include_uncertain else [])
    if args.limit:
        entries = entries[:args.limit]
    if args.json:
        _emit(
            [
                {
                    "offset": e.offset,
                    "team_id": getattr(e.record, "team_id", None),
                    "name": _team_display_name(e.record),
                    "stadium": getattr(e.record, "stadium", None),
                    "full_club_name": getattr(e.record, "full_club_name", None),
                    "chairman": getattr(e.record, "chairman", None),
                    "shirt_sponsor": getattr(e.record, "shirt_sponsor", None),
                    "kit_supplier": getattr(e.record, "kit_supplier", None),
                    "source": e.source,
                }
                for e in entries
            ],
            as_json=True,
        )
        return
    for entry in entries:
        print(f"0x{entry.offset:08X}: {getattr(entry.record, 'team_id', '')} {_team_display_name(entry.record)} [{entry.source}]")


def cmd_team_roster_extract(args):
    include_fallbacks = bool(getattr(args, "include_fallbacks", False))
    if not include_fallbacks:
        rosters = extract_team_rosters_eq_jug_linked(
            team_file=args.file,
            player_file=args.player_file,
            team_queries=list(args.team or []),
        )
        if args.json:
            _emit(rosters, as_json=True)
            return

        _write_json_report(getattr(args, "json_output", None), rosters)
        print("Selection mode: authoritative_only")
        if not rosters:
            if list(args.team or []):
                print("No parser-backed EQ->JUG roster found for the requested --team query.")
            else:
                print("Authoritative parser-backed roster coverage: 0 linked team records.")
        elif not list(args.team or []):
            total_rows = sum(len(list(item.get("rows") or [])) for item in rosters)
            print(
                f"Authoritative parser-backed roster coverage: {len(rosters)} linked team records "
                f"| linked player rows={total_rows}"
            )
        else:
            _print_linked_team_rosters(
                rosters,
                max(0, int(getattr(args, "row_limit", 25) or 0)),
            )

        if args.json_output:
            print(f"\nReport: {args.json_output}")
        return

    result = extract_team_rosters_eq_same_entry_overlap(
        team_file=args.file,
        player_file=args.player_file,
        team_queries=list(args.team or []),
        top_examples=int(args.top_examples),
        include_fallbacks=include_fallbacks,
        json_output=args.json_output,
    )
    if args.json:
        _emit(result.raw_payload or result, as_json=True)
        return

    coverage = dict(result.same_entry_overlap_coverage or {})
    final_coverage = dict(getattr(result, "final_extraction_coverage", {}) or {})
    preferred_coverage = dict(
        getattr(result, "preferred_roster_coverage", None)
        or dict((result.raw_payload or {}).get("preferred_roster_coverage") or {})
    )
    uncovered_club_like_summary = dict(
        getattr(result, "uncovered_club_like_summary", None)
        or dict((result.raw_payload or {}).get("uncovered_club_like_summary") or {})
    )
    status_counts = dict(coverage.get("status_counts") or {})
    strong_or_better = int(coverage.get("strong_or_better_count") or 0)
    ratio = float(coverage.get("strong_or_better_ratio") or 0.0)
    print("Selection mode: " + ("investigation_fallbacks_enabled" if include_fallbacks else "authoritative_only"))
    print(
        "Same-entry EQ roster overlap coverage: "
        f"{strong_or_better}/{result.team_count} ({ratio:.1%}) "
        f"| dd6361 pid names={result.dd6361_pid_name_count}"
    )
    if status_counts:
        counts_line = ", ".join(f"{k}={status_counts[k]}" for k in sorted(status_counts.keys()))
        print(f"Status counts: {counts_line}")
    if include_fallbacks and final_coverage:
        final_count = int(final_coverage.get("covered_count") or 0)
        final_ratio = float(final_coverage.get("covered_ratio") or 0.0)
        fallback_count = int(final_coverage.get("circular_shift_fallback_count") or 0)
        guarded_count = int(final_coverage.get("guarded_covered_count") or 0)
        guarded_ratio = float(final_coverage.get("guarded_covered_ratio") or 0.0)
        flagged_count = int(final_coverage.get("circular_shift_flagged_anchor_collision_count") or 0)
        print(
            "Heuristic candidate coverage (same-entry + circular-shift): "
            f"{final_count}/{result.team_count} ({final_ratio:.1%})"
            + (f" | circular_shift_fallback={fallback_count}" if fallback_count else "")
        )
        if flagged_count:
            print(
                "Guarded heuristic coverage (excluding known anchor-collision candidates): "
                f"{guarded_count}/{result.team_count} ({guarded_ratio:.1%})"
                + f" | flagged_anchor_collisions={flagged_count}"
            )
    if preferred_coverage:
        pref_count = int(preferred_coverage.get("covered_count") or 0)
        pref_ratio = float(preferred_coverage.get("covered_ratio") or 0.0)
        club_like_count = int(preferred_coverage.get("club_like_team_count") or 0)
        club_like_cov = int(preferred_coverage.get("club_like_covered_count") or 0)
        club_like_ratio = float(preferred_coverage.get("club_like_covered_ratio") or 0.0)
        pref_label = (
            "Preferred roster coverage (best available provenance): "
            if include_fallbacks
            else "Authoritative preferred roster coverage: "
        )
        print(f"{pref_label}{pref_count}/{result.team_count} ({pref_ratio:.1%})")
        if club_like_count:
            print(
                "Preferred roster coverage (club-like records): "
                f"{club_like_cov}/{club_like_count} ({club_like_ratio:.1%})"
            )
            remaining_club_like = max(0, club_like_count - club_like_cov)
            print(f"Remaining uncovered club-like records: {remaining_club_like}")
            entry_clusters = list(uncovered_club_like_summary.get("entry_clusters_top") or [])
            if remaining_club_like and entry_clusters:
                cluster_parts = []
                for cluster in entry_clusters[:4]:
                    entry_offset = cluster.get("entry_offset")
                    entry_label = (
                        f"0x{int(entry_offset):08X}"
                        if isinstance(entry_offset, int)
                        else "no-entry"
                    )
                    cluster_parts.append(f"{entry_label}:{int(cluster.get('team_count') or 0)}")
                if cluster_parts:
                    print("Top uncovered clusters by EQ entry: " + ", ".join(cluster_parts))

    requested = list(result.requested_team_results or [])
    if not requested:
        if list(args.team or []):
            print("No matching teams found for the requested --team query.")
        else:
            print("No --team filter provided; use --json or --json-output for the full coverage report.")
        if args.json_output:
            print(f"Report: {args.json_output}")
        return

    row_limit = max(0, int(getattr(args, "row_limit", 25) or 0))
    for item in requested:
        team_name = str(item.get("team_name") or "")
        full_club_name = str(item.get("full_club_name") or "") or None
        team_offset = item.get("team_offset")
        team_id = item.get("team_id")
        status = str(item.get("status") or "")
        candidate_status = str(item.get("circular_shift_candidate_status") or "")
        containing = dict(item.get("containing_entry") or {})
        top_run = dict(item.get("top_run_match") or {})
        candidate_run = dict(item.get("circular_shift_candidate_match") or {})
        anchor_assisted = dict(item.get("known_lineup_anchor_assisted_match") or {})
        pseudo_adjacent = dict(item.get("adjacent_pseudo_team_reassignment_candidate") or {})
        anchor_interval_candidate = dict(item.get("anchor_interval_monotonic_candidate") or {})
        preferred = dict(item.get("preferred_roster_match") or {})
        if (
            candidate_run
            and top_run
            and int(candidate_run.get("run_index", -1)) == int(top_run.get("run_index", -2))
        ):
            candidate_run = {}
        if (
            anchor_interval_candidate
            and top_run
            and int(anchor_interval_candidate.get("run_index", -1)) == int(top_run.get("run_index", -2))
        ):
            anchor_interval_candidate = {}

        title = team_name
        if full_club_name and full_club_name != team_name:
            title += f" ({full_club_name})"
        print()
        print(f"{title}")
        print(
            "  "
            + f"status={status}"
            + (f", team_id={team_id}" if team_id is not None else "")
            + (f", team_offset=0x{int(team_offset):08X}" if isinstance(team_offset, int) else "")
        )
        if include_fallbacks and candidate_status:
            print("  " + f"heuristic_candidate_status={candidate_status}")
        if include_fallbacks:
            warnings = list(item.get("heuristic_warnings") or [])
            for warning in warnings:
                if str(warning.get("type") or "") == "known_lineup_anchor_collision":
                    print(
                        "  "
                        + "WARNING "
                        + str(
                            warning.get("message")
                            or f"Known lineup anchor collision ({warning.get('dataset_key')})"
                            )
                        )
                elif str(warning.get("type") or "") == "anchor_interval_contested_run":
                    preview = [str(v or "") for v in list(warning.get("contested_team_names_preview") or []) if str(v or "")]
                    suffix = f" [contested_with={', '.join(preview)}]" if preview else ""
                    print("  " + "WARNING " + str(warning.get("message") or warning) + suffix)
                else:
                    print("  " + "WARNING " + str(warning.get("message") or warning))
        if containing:
            print(
                "  "
                + f"containing_entry=0x{int(containing.get('entry_offset', 0)):08X}"
                + f", length={int(containing.get('length', 0))}"
            )
        if preferred:
            print(
                "  "
                + f"preferred_roster provenance={str(preferred.get('provenance') or '')}"
                + f", rows={int(preferred.get('row_count', 0))}"
                + (", provisional=true" if bool(preferred.get("provisional")) else "")
            )
        if top_run:
            print(
                "  "
                + f"best_run index={int(top_run.get('run_index', -1))}"
                + f", overlap={int(top_run.get('overlap_hits_in_team_raw', 0))}/{int(top_run.get('non_empty_row_count', 0))}"
                + f", second_best={int(top_run.get('second_best_overlap_hits', 0))}"
            )
            rows = list(top_run.get("rows") or [])
            shown = 0
            for row in rows:
                if row.get("is_empty_slot"):
                    continue
                if row_limit and shown >= row_limit:
                    remaining = sum(1 for r in rows if (not r.get("is_empty_slot"))) - shown
                    if remaining > 0:
                        print(f"  ... {remaining} more row(s)")
                    break
                pid = int(row.get("pid_candidate", 0))
                dd_name = row.get("dd6361_name")
                marker = "*" if row.get("xor_pid_found_in_team_raw") else " "
                name_part = dd_name if dd_name else "(unresolved dd6361 name)"
                tail_text = _same_entry_row_tail_text(row)
                tail_suffix = f" tail={tail_text}" if tail_text else ""
                print(f"  {marker} pid={pid:5d}  {name_part}{tail_suffix}")
                shown += 1
        elif not candidate_run:
            print("  No roster run match details available.")

        if include_fallbacks and anchor_assisted:
            stride = dict(anchor_assisted.get("stride5_window") or {})
            print(
                "  "
                + "anchor_assisted "
                + f"dataset={str(anchor_assisted.get('dataset_key') or '')}"
                + f", entry=0x{int(anchor_assisted.get('entry_offset', 0)):08X}"
                + f", hit_count={int(anchor_assisted.get('hit_count', 0))}"
                + f", exact_anchors={int(anchor_assisted.get('exact_anchor_count', 0))}"
            )
            if stride:
                delta_preview = list(stride.get("delta_positions") or [])
                print(
                    "  "
                    + f"anchor_run_window rows={len(list(stride.get('rows') or []))}"
                    + f", delta_positions={delta_preview[:4]}"
                )
                rows = list(stride.get("rows") or [])
                shown = 0
                for row in rows:
                    if row.get("is_empty_slot"):
                        continue
                    if row_limit and shown >= row_limit:
                        remaining = sum(1 for r in rows if (not r.get("is_empty_slot"))) - shown
                        if remaining > 0:
                            print(f"  ... {remaining} more anchor-assisted row(s)")
                        break
                    pid = int(row.get("pid_candidate", 0))
                    dd_name = row.get("dd6361_name")
                    marker = "A" if row.get("is_anchor_pid") else " "
                    name_part = dd_name if dd_name else "(unresolved dd6361 name)"
                    tail_text = _same_entry_row_tail_text(row)
                    tail_suffix = f" tail={tail_text}" if tail_text else ""
                    print(f"  {marker} pid={pid:5d}  {name_part}{tail_suffix}")
                    shown += 1

        if include_fallbacks and pseudo_adjacent:
            print(
                "  "
                + f"pseudo_adjacent_candidate run={int(pseudo_adjacent.get('run_index', -1))}"
                + f", non_empty={int(pseudo_adjacent.get('non_empty_row_count', 0))}"
                + f", source_pseudo={str(pseudo_adjacent.get('source_pseudo_team_name') or '')}"
            )
            rows = list(pseudo_adjacent.get("rows") or [])
            shown = 0
            for row in rows:
                if row.get("is_empty_slot"):
                    continue
                if row_limit and shown >= row_limit:
                    remaining = sum(1 for r in rows if (not r.get("is_empty_slot"))) - shown
                    if remaining > 0:
                        print(f"  ... {remaining} more pseudo-adjacent row(s)")
                    break
                pid = int(row.get("pid_candidate", 0))
                dd_name = row.get("dd6361_name")
                marker = "*" if row.get("xor_pid_found_in_team_raw") else " "
                name_part = dd_name if dd_name else "(unresolved dd6361 name)"
                tail_text = _same_entry_row_tail_text(row)
                tail_suffix = f" tail={tail_text}" if tail_text else ""
                print(f"  {marker} pid={pid:5d}  {name_part}{tail_suffix}")
                shown += 1

        if include_fallbacks and anchor_interval_candidate:
            anchor_interval = dict(anchor_interval_candidate.get("anchor_interval") or {})
            print(
                "  "
                + f"anchor_interval_candidate run={int(anchor_interval_candidate.get('run_index', -1))}"
                + f", non_empty={int(anchor_interval_candidate.get('non_empty_row_count', 0))}"
                + f", anchors={int(anchor_interval.get('left_run_index', -1))}->{int(anchor_interval.get('right_run_index', -1))}"
            )
            rows = list(anchor_interval_candidate.get("rows") or [])
            shown = 0
            for row in rows:
                if row.get("is_empty_slot"):
                    continue
                if row_limit and shown >= row_limit:
                    remaining = sum(1 for r in rows if (not r.get("is_empty_slot"))) - shown
                    if remaining > 0:
                        print(f"  ... {remaining} more anchor-interval row(s)")
                    break
                pid = int(row.get("pid_candidate", 0))
                dd_name = row.get("dd6361_name")
                marker = "*" if row.get("xor_pid_found_in_team_raw") else " "
                name_part = dd_name if dd_name else "(unresolved dd6361 name)"
                tail_text = _same_entry_row_tail_text(row)
                tail_suffix = f" tail={tail_text}" if tail_text else ""
                print(f"  {marker} pid={pid:5d}  {name_part}{tail_suffix}")
                shown += 1

        if include_fallbacks and candidate_run:
            print(
                "  "
                + f"candidate_run index={int(candidate_run.get('run_index', -1))}"
                + f", non_empty={int(candidate_run.get('non_empty_row_count', 0))}"
                + f", method={str(candidate_run.get('selection_method') or 'circular_shift_same_entry')}"
            )
            rows = list(candidate_run.get("rows") or [])
            shown = 0
            for row in rows:
                if row.get("is_empty_slot"):
                    continue
                if row_limit and shown >= row_limit:
                    remaining = sum(1 for r in rows if (not r.get("is_empty_slot"))) - shown
                    if remaining > 0:
                        print(f"  ... {remaining} more candidate row(s)")
                    break
                pid = int(row.get("pid_candidate", 0))
                dd_name = row.get("dd6361_name")
                marker = "*" if row.get("xor_pid_found_in_team_raw") else " "
                name_part = dd_name if dd_name else "(unresolved dd6361 name)"
                tail_text = _same_entry_row_tail_text(row)
                tail_suffix = f" tail={tail_text}" if tail_text else ""
                print(f"  {marker} pid={pid:5d}  {name_part}{tail_suffix}")
                shown += 1

    if args.json_output:
        print(f"\nReport: {args.json_output}")


def cmd_team_roster_linked(args):
    rosters = extract_team_rosters_eq_jug_linked(
        team_file=args.file,
        player_file=args.player_file,
        team_queries=list(args.team or []),
    )
    if args.json:
        _emit(rosters, as_json=True)
        return

    if not rosters:
        if list(args.team or []):
            print("No parser-backed EQ->JUG roster found for the requested --team query.")
        else:
            print("No parser-backed EQ->JUG roster rows found.")
        return

    if not list(args.team or []):
        print(
            f"Parser-backed EQ->JUG roster coverage: {len(rosters)} linked team records. "
            "Use --team to filter, or --json for the full dump."
        )
        return

    _print_linked_team_rosters(rosters, max(0, int(getattr(args, "row_limit", 25) or 0)))


def cmd_team_roster_edit_linked(args):
    try:
        result = edit_team_roster_eq_jug_linked(
            team_file=args.file,
            player_file=args.player_file,
            team_query=args.team,
            eq_record_id=args.eq_record_id,
            slot_number=args.slot,
            player_record_id=args.player_id,
            flag=args.flag,
            write_changes=not args.dry_run,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result, as_json=True)
        return
    _print_linked_team_roster_edit_result(result, dry_run=args.dry_run)


def cmd_team_roster_edit_same_entry(args):
    try:
        result = edit_team_roster_same_entry_authoritative(
            team_file=args.file,
            player_file=args.player_file,
            team_query=args.team,
            team_offset=_parse_int_auto(args.team_offset),
            slot_number=args.slot,
            pid_candidate=args.pid,
            write_changes=not args.dry_run,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result, as_json=True)
        return
    _print_same_entry_team_roster_edit_result(result, dry_run=args.dry_run)


def cmd_team_roster_profile_same_entry(args):
    try:
        result = profile_same_entry_authoritative_tail_bytes(
            team_file=args.file,
            player_file=args.player_file,
            team_queries=list(args.team or []),
            limit=max(1, int(getattr(args, "limit", 10) or 10)),
            include_fallbacks=bool(getattr(args, "include_fallbacks", False)),
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return
    if args.json:
        _emit(result, as_json=True)
        return
    _print_same_entry_tail_profile_result(result)


def cmd_team_roster_batch_edit(args):
    try:
        result = batch_edit_team_roster_records(
            team_file=args.file,
            player_file=args.player_file,
            csv_path=args.csv,
            write_changes=not args.dry_run,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        _emit(result, as_json=True)
        return
    _print_team_roster_batch_edit_result(result, dry_run=args.dry_run)


def cmd_team_search(args):
    query = (args.name or "").strip()
    valid, uncertain = gather_team_records(args.file)
    entries = valid + (uncertain if args.include_uncertain else [])
    matches = [
        e for e in entries
        if team_query_matches(
            query,
            team_name=_team_display_name(e.record),
            full_club_name=str(getattr(e.record, "full_club_name", "") or ""),
        )
        or query.lower() in str(getattr(e.record, "team_id", "")).lower()
    ]
    if args.json:
        _emit(
            [
                {
                    "offset": e.offset,
                    "team_id": getattr(e.record, "team_id", None),
                    "name": _team_display_name(e.record),
                    "stadium": getattr(e.record, "stadium", None),
                    "full_club_name": getattr(e.record, "full_club_name", None),
                    "chairman": getattr(e.record, "chairman", None),
                    "shirt_sponsor": getattr(e.record, "shirt_sponsor", None),
                    "kit_supplier": getattr(e.record, "kit_supplier", None),
                    "source": e.source,
                }
                for e in matches
            ],
            as_json=True,
        )
        return
    for entry in matches:
        print(f"0x{entry.offset:08X}: {getattr(entry.record, 'team_id', '')} {_team_display_name(entry.record)} [{entry.source}]")


def cmd_team_rename(args):
    target_offsets = [_parse_int_auto(args.offset)] if args.offset else None
    result = rename_team_records(
        file_path=args.file,
        old_team=args.old,
        new_team=args.new,
        old_stadium=args.old_stadium,
        new_stadium=args.new_stadium,
        include_uncertain=args.include_uncertain,
        target_offsets=target_offsets,
        write_changes=not args.dry_run,
    )
    if args.json:
        _emit(result, as_json=True)
        return
    if not result.changes:
        print("No team records changed.")
        return
    print(
        f"{'Staged' if args.dry_run else 'Renamed'} {len(result.changes)} team record(s) "
        f"(matched={result.matched_count}, valid={result.valid_count}, uncertain={result.uncertain_count})"
    )
    for change in result.changes[:20]:
        name_part = f"{change.name_change[0]} -> {change.name_change[1]}"
        if change.stadium_change:
            name_part += f" | stadium: {change.stadium_change[0]} -> {change.stadium_change[1]}"
        print(f"  0x{change.offset:08X}: {name_part}")
    if result.backup_path:
        print(f"Backup: {result.backup_path}")
    for warning in result.warnings:
        print(f"Warning at {warning.offset}: {warning.message}", file=sys.stderr)


def cmd_coach_list(args):
    valid, uncertain = gather_coach_records(args.file)
    entries = valid + (uncertain if args.include_uncertain else [])
    if args.limit:
        entries = entries[:args.limit]
    if args.json:
        _emit(
            [
                {"offset": e.offset, "name": _coach_display_name(e.record), "source": e.source}
                for e in entries
            ],
            as_json=True,
        )
        return
    for entry in entries:
        print(f"0x{entry.offset:08X}: {_coach_display_name(entry.record)} [{entry.source}]")


def cmd_coach_search(args):
    query = (args.name or "").strip().lower()
    valid, uncertain = gather_coach_records(args.file)
    entries = valid + (uncertain if args.include_uncertain else [])
    matches = [e for e in entries if query in _coach_display_name(e.record).lower()]
    if args.json:
        _emit(
            [
                {"offset": e.offset, "name": _coach_display_name(e.record), "source": e.source}
                for e in matches
            ],
            as_json=True,
        )
        return
    for entry in matches:
        print(f"0x{entry.offset:08X}: {_coach_display_name(entry.record)} [{entry.source}]")


def cmd_coach_rename(args):
    result = rename_coach_records(
        file_path=args.file,
        old_name=args.old,
        new_name=args.new,
        include_uncertain=args.include_uncertain,
        target_offset=_parse_int_auto(args.offset),
        write_changes=not args.dry_run,
    )
    if args.json:
        _emit(result, as_json=True)
        return
    if not result.changes:
        print("No coach records changed.")
        return
    print(
        f"{'Staged' if args.dry_run else 'Renamed'} {len(result.changes)} coach record(s) "
        f"(matched={result.matched_count})"
    )
    for change in result.changes[:20]:
        print(f"  0x{change.offset:08X}: {change.old_name} -> {change.new_name}")
    if result.backup_path:
        print(f"Backup: {result.backup_path}")
    for warning in result.warnings:
        print(f"Warning at {warning.offset}: {warning.message}", file=sys.stderr)


def cmd_bulk_player_rename(args):
    result = bulk_rename_players(
        data_dir=args.data_dir,
        map_output=args.map_output,
        dry_run=args.dry_run,
        integrity_checks=not args.skip_integrity_checks,
    )
    if args.json:
        _emit(result, as_json=True)
        return
    print(
        f"{'Dry run completed' if args.dry_run else 'Bulk rename completed'}: "
        f"files={result.files_processed}, rows={result.rows_written}, map={result.map_output}"
    )


def cmd_bulk_player_revert(args):
    result = revert_player_renames(
        data_dir=args.data_dir,
        map_input=args.map_input,
        dry_run=args.dry_run,
        integrity_checks=not args.skip_integrity_checks,
    )
    if args.json:
        _emit(result, as_json=True)
        return
    print(
        f"{'Dry run completed' if args.dry_run else 'Bulk revert completed'}: "
        f"files={result.files_processed}, rows={result.rows_processed}, map={result.map_input}"
    )

def cmd_pkf_search(args):
    """Search for strings/patterns across PKF files"""
    directory = Path(args.directory)
    
    if not directory.exists():
        print(f"Error: Directory '{directory}' not found", file=sys.stderr)
        sys.exit(1)
    
    # Create searcher
    searcher = PKFSearcher(
        directory=directory,
        recursive=not args.no_recursive,
        file_pattern=args.file_pattern,
        max_results=args.limit,
        context_size=args.context,
    )
    
    # Find PKF files
    pkf_files = searcher.find_pkf_files()
    if not pkf_files:
        print(f"No PKF files found in {directory}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Searching in: {directory}")
    print(f"Found {len(pkf_files)} PKF file(s)")
    print(f"Pattern: {args.query}")
    print()
    
    # Perform search based on mode
    try:
        if args.mode == "hex":
            results = searcher.search_hex(args.query, use_parallel=not args.no_parallel)
        elif args.mode == "regex":
            results = searcher.search_regex(args.query, encoding=args.encoding, use_parallel=not args.no_parallel)
        elif args.xor is not None:
            xor_key = int(args.xor, 16) if args.xor.startswith('0x') else int(args.xor)
            results = searcher.search_with_xor(args.query, xor_key, encoding=args.encoding, use_parallel=not args.no_parallel)
        else:
            results = searcher.search_text(args.query, case_sensitive=args.case_sensitive,
                                          encoding=args.encoding, use_parallel=not args.no_parallel)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Display results
    if not results:
        print("No matches found.")
        return
    
    print(f"Found {len(results)} match(es) across {len(set(r.file_path for r in results))} file(s):\n")
    
    # Group results by file
    by_file = {}
    for result in results:
        if result.file_path not in by_file:
            by_file[result.file_path] = []
        by_file[result.file_path].append(result)
    
    # Display grouped results
    for file_path, file_results in by_file.items():
        print(f"File: {file_path.relative_to(directory) if file_path.is_relative_to(directory) else file_path}")
        
        for result in file_results:
            print(f"  Entry {result.entry_index} @ 0x{result.entry_offset:08X} (offset in entry: 0x{result.match_offset:04X}):")
            
            # Show hex preview
            preview = result.format_preview(width=16)
            for line in preview.split('\n'):
                print(f"    {line}")
            
            # Show decoded text if applicable
            if result.encoding and result.encoding != "raw":
                try:
                    text = result.get_match_text(result.encoding)
                    if text and not text.startswith("<binary"):
                        print(f"    Text: {text}")
                except Exception:
                    pass
            
            print()
    
    # Export if requested
    if args.export:
        export_path = Path(args.export)
        if export_path.suffix.lower() == '.json':
            _export_json(results, export_path, directory)
        else:
            _export_csv(results, export_path, directory)
        print(f"Results exported to: {export_path}")

def _export_csv(results, output_path, base_dir):
    """Export results to CSV format"""
    import csv
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['File', 'Entry', 'Entry Offset', 'Match Offset', 'Absolute Offset',
                        'Match (Hex)', 'Match (Text)', 'Encoding', 'XOR Key'])
        
        for result in results:
            rel_path = result.file_path.relative_to(base_dir) if result.file_path.is_relative_to(base_dir) else result.file_path
            match_text = result.get_match_text(result.encoding or 'utf-8')
            
            writer.writerow([
                str(rel_path),
                result.entry_index,
                f"0x{result.entry_offset:08X}",
                f"0x{result.match_offset:04X}",
                f"0x{result.absolute_offset:08X}",
                result.match_bytes.hex(),
                match_text,
                result.encoding or '',
                f"0x{result.xor_key:02X}" if result.xor_key is not None else '',
            ])

def _export_json(results, output_path, base_dir):
    """Export results to JSON format"""
    import json
    
    data = []
    for result in results:
        rel_path = result.file_path.relative_to(base_dir) if result.file_path.is_relative_to(base_dir) else result.file_path
        
        data.append({
            'file': str(rel_path),
            'entry_index': result.entry_index,
            'entry_offset': f"0x{result.entry_offset:08X}",
            'match_offset': f"0x{result.match_offset:04X}",
            'absolute_offset': f"0x{result.absolute_offset:08X}",
            'match_hex': result.match_bytes.hex(),
            'match_text': result.get_match_text(result.encoding or 'utf-8'),
            'context_before_hex': result.context_before.hex(),
            'context_after_hex': result.context_after.hex(),
            'encoding': result.encoding,
            'xor_key': f"0x{result.xor_key:02X}" if result.xor_key is not None else None,
        })
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({'results': data, 'total': len(data)}, f, indent=2)

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(description="Premier Manager 99 Database Editor")
    subparsers = parser.add_subparsers(dest="command")
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Display file information")
    info_parser.add_argument("file", help="FDI file path")
    info_parser.set_defaults(func=cmd_info)

    validate_db_parser = subparsers.add_parser(
        "validate-database",
        help="Re-open player/team/coach files through the shared parser-backed loaders",
    )
    validate_db_parser.add_argument("--players", help="Player FDI path (for example JUG98030.FDI)")
    validate_db_parser.add_argument("--teams", help="Team FDI path (for example EQ98030.FDI)")
    validate_db_parser.add_argument("--coaches", help="Coach FDI path (for example ENT98030.FDI)")
    validate_db_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    validate_db_parser.set_defaults(func=cmd_validate_database)

    main_dat_parser = subparsers.add_parser(
        "main-dat-inspect",
        help="Inspect the parser-backed, currently confirmed main.dat prefix",
    )
    main_dat_parser.add_argument("file", help="Path to main.dat")
    main_dat_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    main_dat_parser.set_defaults(func=cmd_main_dat_inspect)

    main_dat_edit_parser = subparsers.add_parser(
        "main-dat-edit",
        help="Edit confirmed main.dat prefix fields while preserving unresolved blocks",
    )
    main_dat_edit_parser.add_argument("file", help="Path to main.dat")
    main_dat_edit_parser.add_argument("--primary-label", help="Replace the first confirmed XOR u16 string")
    main_dat_edit_parser.add_argument("--secondary-label", help="Replace the second confirmed XOR u16 string")
    main_dat_edit_parser.add_argument("--day", type=int, help="Replace the confirmed save-day byte")
    main_dat_edit_parser.add_argument("--month", type=int, help="Replace the confirmed save-month byte")
    main_dat_edit_parser.add_argument("--year", type=int, help="Replace the confirmed save-year word")
    main_dat_edit_parser.add_argument("--hour", type=int, help="Replace the confirmed hour byte")
    main_dat_edit_parser.add_argument("--minute", type=int, help="Replace the confirmed minute byte")
    main_dat_edit_parser.add_argument("--scalar-byte", type=int, help="Replace the confirmed scalar byte after the 10 flags")
    main_dat_edit_parser.add_argument(
        "--flag-byte",
        action="append",
        default=[],
        help="Replace one confirmed flag byte: INDEX=VALUE (repeatable, indices 0-9)",
    )
    output_group = main_dat_edit_parser.add_mutually_exclusive_group()
    output_group.add_argument("--output-file", help="Write a patched copy (default: <input>.edited.dat)")
    output_group.add_argument("--in-place", action="store_true", help="Patch the input file directly")
    main_dat_edit_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="With --in-place, skip creating a .backup file",
    )
    main_dat_edit_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    main_dat_edit_parser.set_defaults(func=cmd_main_dat_edit)
    
    # List command
    list_parser = subparsers.add_parser("list", help="List players")
    list_parser.add_argument("file", help="FDI file path")
    list_parser.add_argument("--limit", type=int, help="Maximum records to list")
    list_parser.add_argument("--include-uncertain", action="store_true", help="Include low-confidence matches")
    list_parser.add_argument("--strict", action="store_true", help="Sequential scan of real entries + player subrecords (slower, fewer false positives)")
    list_parser.add_argument("--require-team-id", action="store_true", help="With --strict, only include entries with non-zero team_id")
    list_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    list_parser.set_defaults(func=cmd_list)
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search players by name")
    search_parser.add_argument("file", help="FDI file path")
    search_parser.add_argument("name", help="Name to search for")
    search_parser.add_argument("--include-uncertain", action="store_true", help="Include low-confidence matches")
    search_parser.add_argument("--strict", action="store_true", help="Sequential scan of real entries + player subrecords (slower, fewer false positives)")
    search_parser.add_argument("--require-team-id", action="store_true", help="With --strict, only include entries with non-zero team_id")
    search_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    search_parser.set_defaults(func=cmd_search)
    
    # Rename command
    rename_parser = subparsers.add_parser("rename", help="Rename player by ID")
    rename_parser.add_argument("file", help="FDI file path")
    rename_parser.add_argument("--id", type=int, required=True, help="Player ID")
    rename_parser.add_argument("--name", required=True, help="New name")
    rename_parser.add_argument("--offset", help="Optional record offset (hex or decimal) to disambiguate")
    rename_parser.set_defaults(func=cmd_rename)

    # Player-specific v1 commands
    player_list_parser = subparsers.add_parser("player-list", help="List player records (offset-aware)")
    player_list_parser.add_argument("file", help="FDI file path")
    player_list_parser.add_argument("--limit", type=int, help="Maximum records to list")
    player_list_parser.add_argument("--include-uncertain", action="store_true", help="Include low-confidence matches")
    player_list_parser.add_argument("--strict", action="store_true", help="Sequential scan of real entries + player subrecords (slower, fewer false positives)")
    player_list_parser.add_argument("--require-team-id", action="store_true", help="With --strict, only include entries with non-zero team_id")
    player_list_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    player_list_parser.set_defaults(func=cmd_player_list)

    player_search_parser = subparsers.add_parser("player-search", help="Search player records by name")
    player_search_parser.add_argument("file", help="FDI file path")
    player_search_parser.add_argument("name", help="Name substring to search for")
    player_search_parser.add_argument("--include-uncertain", action="store_true", help="Include low-confidence matches")
    player_search_parser.add_argument("--strict", action="store_true", help="Sequential scan of real entries + player subrecords (slower, fewer false positives)")
    player_search_parser.add_argument("--require-team-id", action="store_true", help="With --strict, only include entries with non-zero team_id")
    player_search_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    player_search_parser.set_defaults(func=cmd_player_search)

    player_investigate_parser = subparsers.add_parser(
        "player-investigate",
        help="Investigate heuristic vs strict matches and nearby club mentions for a player name",
    )
    player_investigate_parser.add_argument("file", help="FDI file path")
    player_investigate_parser.add_argument("name", help="Player name substring to investigate")
    player_investigate_parser.add_argument("--context", type=int, default=800, help="Context window for club mention extraction")
    player_investigate_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    player_investigate_parser.set_defaults(func=cmd_player_investigate)

    club_investigate_parser = subparsers.add_parser(
        "club-investigate",
        help="Investigate player names associated with a club mention in player data blobs",
    )
    club_investigate_parser.add_argument("file", help="FDI file path")
    club_investigate_parser.add_argument("club", help="Club name substring (e.g. 'Stoke City')")
    club_investigate_parser.add_argument("--context", type=int, default=300, help="Context window for subrecord/heuristic club mention association")
    club_investigate_parser.add_argument("--include-heuristic", action="store_true", help="Also include scanner-only heuristic matches from biography/news blobs")
    club_investigate_parser.add_argument("--limit", type=int, default=40, help="Max rows to print per section")
    club_investigate_parser.add_argument(
        "--heuristic-context",
        type=int,
        default=800,
        help="Context window for scanner-only heuristic matches (default: 800)",
    )
    club_investigate_parser.add_argument("--teams-file", help="Optional teams FDI (EQ98030.FDI) for derived club->team resolution")
    club_investigate_parser.add_argument("--no-team-resolve", dest="resolve_team", action="store_false", help="Disable derived club query resolution against team records")
    club_investigate_parser.add_argument("--export", help="Write club index payload (.json or .csv)")
    club_investigate_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    club_investigate_parser.set_defaults(resolve_team=True)
    club_investigate_parser.set_defaults(func=cmd_club_investigate)

    roster_reconcile_pdf_parser = subparsers.add_parser(
        "roster-reconcile-pdf",
        help="Reconcile PM99 roster listing PDF against player records",
    )
    roster_reconcile_pdf_parser.add_argument("--pdf", required=True, help="Path to PM99 listing PDF")
    roster_reconcile_pdf_parser.add_argument("--player-file", default="DBDAT/JUG98030.FDI", help="Player FDI file path")
    roster_reconcile_pdf_parser.add_argument(
        "--default-window",
        type=int,
        default=800,
        help="Default club mention context window (default: 800)",
    )
    roster_reconcile_pdf_parser.add_argument(
        "--wide-window",
        type=int,
        default=10000,
        help="Wide fallback context window (default: 10000)",
    )
    roster_reconcile_pdf_parser.add_argument("--json-output", required=True, help="Output JSON path")
    roster_reconcile_pdf_parser.add_argument("--csv-output", required=True, help="Output CSV path (detailed rows)")
    roster_reconcile_pdf_parser.add_argument("--team-summary-csv", help="Optional output CSV path for team summaries")
    roster_reconcile_pdf_parser.add_argument("--team", help="Optional team label/query filter (e.g. 'Stoke City')")
    roster_reconcile_pdf_parser.add_argument("--name-hints", help="Optional CSV/JSON name hints for disambiguation")
    roster_reconcile_pdf_parser.set_defaults(func=cmd_roster_reconcile_pdf)

    player_rename_parser = subparsers.add_parser("player-rename", help="Rename player record(s) by current name")
    player_rename_parser.add_argument("file", help="FDI file path")
    player_rename_parser.add_argument("--old", required=True, help="Current player name")
    player_rename_parser.add_argument("--new", required=True, help="New player name")
    player_rename_parser.add_argument("--offset", help="Optional record offset (hex or decimal) to disambiguate")
    player_rename_parser.add_argument("--include-uncertain", action="store_true", help="Include low-confidence matches")
    player_rename_parser.add_argument("--dry-run", action="store_true", help="Validate and stage only (no file write)")
    player_rename_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    player_rename_parser.set_defaults(func=cmd_player_rename)

    player_edit_parser = subparsers.add_parser(
        "player-edit",
        help="Edit parser-backed player metadata for indexed JUG files",
    )
    player_edit_parser.add_argument("file", help="FDI file path")
    player_edit_parser.add_argument("--name", help="Current player name")
    player_edit_parser.add_argument("--offset", help="Optional indexed payload offset (hex or decimal)")
    player_edit_parser.add_argument("--new-name", help="New player name")
    player_edit_parser.add_argument("--position", type=int, help="Primary position ID")
    player_edit_parser.add_argument("--nationality", type=int, help="Nationality ID")
    player_edit_parser.add_argument("--dob-day", type=int, help="Birth day")
    player_edit_parser.add_argument("--dob-month", type=int, help="Birth month")
    player_edit_parser.add_argument("--dob-year", type=int, help="Birth year")
    player_edit_parser.add_argument("--height", type=int, help="Height in cm")
    player_edit_parser.add_argument("--weight", type=int, help="Weight in kg")
    player_edit_parser.add_argument("--dry-run", action="store_true", help="Validate and stage only (no file write)")
    player_edit_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    player_edit_parser.set_defaults(func=cmd_player_edit)

    player_batch_edit_parser = subparsers.add_parser(
        "player-batch-edit",
        help="Apply CSV-driven indexed player renames and metadata edits in one pass",
    )
    player_batch_edit_parser.add_argument("file", help="FDI file path")
    player_batch_edit_parser.add_argument("--csv", required=True, help="CSV plan path")
    player_batch_edit_parser.add_argument("--dry-run", action="store_true", help="Validate and stage only (no file write)")
    player_batch_edit_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    player_batch_edit_parser.set_defaults(func=cmd_player_batch_edit)

    player_inspect_parser = subparsers.add_parser(
        "player-inspect",
        help="Inspect parser-backed indexed player metadata (including unresolved suffix bytes)",
    )
    player_inspect_parser.add_argument("file", help="FDI file path")
    player_inspect_parser.add_argument("--name", required=True, help="Current player name")
    player_inspect_parser.add_argument("--offset", help="Optional indexed payload offset (hex or decimal)")
    player_inspect_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    player_inspect_parser.set_defaults(func=cmd_player_inspect)

    player_legacy_weight_profile_parser = subparsers.add_parser(
        "player-legacy-weight-profile",
        help="Use indexed suffix weights as a control set to test legacy marker-relative weight offsets",
    )
    player_legacy_weight_profile_parser.add_argument(
        "file",
        nargs="?",
        default="DBDAT/JUG98030.FDI",
        help="Path to indexed JUG98030.FDI (default: DBDAT/JUG98030.FDI)",
    )
    player_legacy_weight_profile_parser.add_argument(
        "--start-offset",
        type=int,
        default=14,
        help="First marker-relative offset to test (default: 14)",
    )
    player_legacy_weight_profile_parser.add_argument(
        "--end-offset",
        type=int,
        default=18,
        help="Last marker-relative offset to test (default: 18)",
    )
    player_legacy_weight_profile_parser.add_argument(
        "--top-values",
        type=int,
        default=8,
        help="Top decoded values to print per offset (default: 8)",
    )
    player_legacy_weight_profile_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    player_legacy_weight_profile_parser.set_defaults(func=cmd_player_legacy_weight_profile)

    player_suffix_profile_parser = subparsers.add_parser(
        "player-suffix-profile",
        help="Profile unresolved indexed suffix-byte pairs across parser-backed player records",
    )
    player_suffix_profile_parser.add_argument("file", help="FDI file path")
    player_suffix_profile_parser.add_argument("--nationality", type=int, help="Optional nationality filter")
    player_suffix_profile_parser.add_argument("--position", type=int, help="Optional primary position filter")
    player_suffix_profile_parser.add_argument("--limit", type=int, default=10, help="Max buckets to print")
    player_suffix_profile_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    player_suffix_profile_parser.set_defaults(func=cmd_player_suffix_profile)

    player_leading_profile_parser = subparsers.add_parser(
        "player-leading-profile",
        help="Profile the leading indexed suffix-byte pair across parser-backed player records",
    )
    player_leading_profile_parser.add_argument("file", help="FDI file path")
    player_leading_profile_parser.add_argument("--nationality", type=int, help="Optional nationality filter")
    player_leading_profile_parser.add_argument("--position", type=int, help="Optional primary position filter")
    player_leading_profile_parser.add_argument("--u0", type=int, help="Optional leading indexed suffix byte +0 filter")
    player_leading_profile_parser.add_argument("--u1", type=int, help="Optional leading indexed suffix byte +1 filter")
    player_leading_profile_parser.add_argument("--u9", type=int, help="Optional indexed suffix byte +9 filter")
    player_leading_profile_parser.add_argument("--u10", type=int, help="Optional indexed suffix byte +10 filter")
    player_leading_profile_parser.add_argument("--limit", type=int, default=10, help="Max buckets to print")
    player_leading_profile_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    player_leading_profile_parser.set_defaults(func=cmd_player_leading_profile)

    player_tail_prefix_profile_parser = subparsers.add_parser(
        "player-tail-prefix-profile",
        help="Profile the unresolved 3-byte tail prefix across parser-backed indexed player records",
    )
    player_tail_prefix_profile_parser.add_argument("file", help="FDI file path")
    player_tail_prefix_profile_parser.add_argument("--nationality", type=int, help="Optional nationality filter")
    player_tail_prefix_profile_parser.add_argument("--position", type=int, help="Optional primary position filter")
    player_tail_prefix_profile_parser.add_argument("--u0", type=int, help="Optional leading indexed suffix byte +0 filter")
    player_tail_prefix_profile_parser.add_argument("--u1", type=int, help="Optional leading indexed suffix byte +1 filter")
    player_tail_prefix_profile_parser.add_argument("--u9", type=int, help="Optional indexed suffix byte +9 filter")
    player_tail_prefix_profile_parser.add_argument("--u10", type=int, help="Optional indexed suffix byte +10 filter")
    player_tail_prefix_profile_parser.add_argument("--a0", type=int, help="Optional tail-prefix Attr 0 filter")
    player_tail_prefix_profile_parser.add_argument("--a1", type=int, help="Optional tail-prefix Attr 1 filter")
    player_tail_prefix_profile_parser.add_argument("--a2", type=int, help="Optional tail-prefix Attr 2 filter")
    player_tail_prefix_profile_parser.add_argument(
        "--post-weight",
        type=int,
        help="Optional indexed byte immediately after weight (stored at [player+0x48])",
    )
    player_tail_prefix_profile_parser.add_argument("--trail", type=int, help="Optional fixed trailer byte filter")
    player_tail_prefix_profile_parser.add_argument(
        "--sidecar",
        type=int,
        help="Optional first post-trailer sidecar byte filter",
    )
    player_tail_prefix_profile_parser.add_argument("--limit", type=int, default=10, help="Max buckets to print")
    player_tail_prefix_profile_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    player_tail_prefix_profile_parser.set_defaults(func=cmd_player_tail_prefix_profile)

    player_skill_patch_parser = subparsers.add_parser(
        "player-skill-patch",
        help="Patch dd6361 visible player stats on a copy of JUG98030.FDI",
    )
    player_skill_patch_parser.add_argument(
        "file",
        nargs="?",
        default="DBDAT/JUG98030.FDI",
        help="Path to JUG98030.FDI (default: DBDAT/JUG98030.FDI)",
    )
    player_skill_patch_parser.add_argument("--name", required=True, help="Player name query (dd6361 bio name)")
    player_skill_patch_parser.add_argument(
        "--set",
        dest="set_args",
        action="append",
        default=[],
        help="Mapped10 stat assignment (repeatable): FIELD=VALUE",
    )
    player_skill_patch_parser.add_argument(
        "--output-file",
        default=None,
        help="Patched output file path (copy-safe; default: /tmp/JUG98030.dd6361_patched.FDI)",
    )
    player_skill_patch_parser.add_argument(
        "--in-place",
        action="store_true",
        help="Patch the input file directly (creates backup by default; cannot be used with --output-file)",
    )
    player_skill_patch_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="With --in-place, skip creating a .backup file",
    )
    player_skill_patch_parser.add_argument("--json-output", help="Optional JSON report file path")
    player_skill_patch_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    player_skill_patch_parser.set_defaults(func=cmd_player_skill_patch)

    # Team commands
    team_list_parser = subparsers.add_parser("team-list", help="List team records")
    team_list_parser.add_argument("file", help="FDI file path")
    team_list_parser.add_argument("--limit", type=int, help="Maximum records to list")
    team_list_parser.add_argument("--include-uncertain", action="store_true", help="Include uncertain records")
    team_list_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    team_list_parser.set_defaults(func=cmd_team_list)

    team_search_parser = subparsers.add_parser("team-search", help="Search team records by name or id")
    team_search_parser.add_argument("file", help="FDI file path")
    team_search_parser.add_argument("name", help="Team name/team-id query")
    team_search_parser.add_argument("--include-uncertain", action="store_true", help="Include uncertain records")
    team_search_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    team_search_parser.set_defaults(func=cmd_team_search)

    team_rename_parser = subparsers.add_parser("team-rename", help="Rename team and optional stadium")
    team_rename_parser.add_argument("file", help="FDI file path")
    team_rename_parser.add_argument("--old", required=True, help="Current team name")
    team_rename_parser.add_argument("--new", required=True, help="New team name")
    team_rename_parser.add_argument("--old-stadium", help="Current stadium name (optional)")
    team_rename_parser.add_argument("--new-stadium", help="New stadium name (optional)")
    team_rename_parser.add_argument("--offset", help="Optional record offset (hex or decimal)")
    team_rename_parser.add_argument("--include-uncertain", action="store_true", help="Include uncertain records")
    team_rename_parser.add_argument("--dry-run", action="store_true", help="Validate and stage only (no file write)")
    team_rename_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    team_rename_parser.set_defaults(func=cmd_team_rename)

    team_roster_extract_parser = subparsers.add_parser(
        "team-roster-extract",
        help="Extract team roster (parser-backed by default; heuristic fallbacks optional)",
    )
    team_roster_extract_parser.add_argument(
        "file",
        nargs="?",
        default="DBDAT/EQ98030.FDI",
        help="Path to EQ98030.FDI (default: DBDAT/EQ98030.FDI)",
    )
    team_roster_extract_parser.add_argument(
        "--player-file",
        default="DBDAT/JUG98030.FDI",
        help="Path to JUG98030.FDI for dd6361 player-id -> name mapping",
    )
    team_roster_extract_parser.add_argument(
        "--team",
        action="append",
        default=[],
        help="Team query substring filter (repeatable). Omit for coverage summary only.",
    )
    team_roster_extract_parser.add_argument(
        "--top-examples",
        type=int,
        default=15,
        help="How many strong-match examples to include in the JSON payload (default: 15)",
    )
    team_roster_extract_parser.add_argument(
        "--row-limit",
        type=int,
        default=25,
        help="Max non-empty roster rows to print per requested team in text mode (default: 25)",
    )
    team_roster_extract_parser.add_argument(
        "--include-fallbacks",
        action="store_true",
        help=(
            "Enable investigation fallbacks (anchor-assisted and heuristic candidate mappings). "
            "Default output is authoritative-only."
        ),
    )
    team_roster_extract_parser.add_argument("--json-output", help="Optional JSON report file path")
    team_roster_extract_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    team_roster_extract_parser.set_defaults(func=cmd_team_roster_extract)

    team_roster_linked_parser = subparsers.add_parser(
        "team-roster-linked",
        help="Extract parser-backed EQ->JUG linked team rosters (read-only)",
    )
    team_roster_linked_parser.add_argument(
        "file",
        nargs="?",
        default="DBDAT/EQ98030.FDI",
        help="Path to EQ98030.FDI (default: DBDAT/EQ98030.FDI)",
    )
    team_roster_linked_parser.add_argument(
        "--player-file",
        default="DBDAT/JUG98030.FDI",
        help="Path to JUG98030.FDI for player-id -> player-name resolution",
    )
    team_roster_linked_parser.add_argument(
        "--team",
        action="append",
        default=[],
        help="Team query substring filter (repeatable). Omit for a coverage summary only.",
    )
    team_roster_linked_parser.add_argument(
        "--row-limit",
        type=int,
        default=25,
        help="Max roster rows to print per requested team in text mode (default: 25)",
    )
    team_roster_linked_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    team_roster_linked_parser.set_defaults(func=cmd_team_roster_linked)

    team_roster_edit_linked_parser = subparsers.add_parser(
        "team-roster-edit-linked",
        help="Edit one parser-backed EQ->JUG linked roster slot in place",
    )
    team_roster_edit_linked_parser.add_argument(
        "file",
        nargs="?",
        default="DBDAT/EQ98030.FDI",
        help="Path to EQ98030.FDI (default: DBDAT/EQ98030.FDI)",
    )
    team_roster_edit_linked_parser.add_argument(
        "--player-file",
        default="DBDAT/JUG98030.FDI",
        help="Path to JUG98030.FDI for player-id -> player-name resolution",
    )
    team_roster_edit_linked_parser.add_argument("--team", help="Team query filter (preferred when unique)")
    team_roster_edit_linked_parser.add_argument(
        "--eq-record-id",
        type=int,
        help="Exact EQ linked roster record ID (use this to disambiguate)",
    )
    team_roster_edit_linked_parser.add_argument(
        "--slot",
        type=int,
        required=True,
        help="1-based linked roster slot number to edit",
    )
    team_roster_edit_linked_parser.add_argument(
        "--player-id",
        type=int,
        help="New JUG player record ID for the slot",
    )
    team_roster_edit_linked_parser.add_argument(
        "--flag",
        type=int,
        help="Optional new row flag byte (0-255)",
    )
    team_roster_edit_linked_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and stage only (no file write)",
    )
    team_roster_edit_linked_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    team_roster_edit_linked_parser.set_defaults(func=cmd_team_roster_edit_linked)

    team_roster_edit_same_entry_parser = subparsers.add_parser(
        "team-roster-edit-same-entry",
        help="Edit the leading 2-byte PID field in one supported same-entry roster slot",
    )
    team_roster_edit_same_entry_parser.add_argument(
        "file",
        nargs="?",
        default="DBDAT/EQ98030.FDI",
        help="Path to EQ98030.FDI (default: DBDAT/EQ98030.FDI)",
    )
    team_roster_edit_same_entry_parser.add_argument(
        "--player-file",
        default="DBDAT/JUG98030.FDI",
        help="Path to JUG98030.FDI for dd6361 PID -> player-name resolution",
    )
    team_roster_edit_same_entry_parser.add_argument(
        "--team",
        required=True,
        help="Team query filter (must resolve to one authoritative same-entry result)",
    )
    team_roster_edit_same_entry_parser.add_argument(
        "--team-offset",
        help="Optional exact team offset (hex or decimal) to disambiguate",
    )
    team_roster_edit_same_entry_parser.add_argument(
        "--slot",
        type=int,
        required=True,
        help="1-based non-empty slot number within the authoritative same-entry run",
    )
    team_roster_edit_same_entry_parser.add_argument(
        "--pid",
        type=int,
        required=True,
        help="New 16-bit PID candidate for the slot",
    )
    team_roster_edit_same_entry_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and stage only (no file write)",
    )
    team_roster_edit_same_entry_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    team_roster_edit_same_entry_parser.set_defaults(func=cmd_team_roster_edit_same_entry)

    team_roster_batch_edit_parser = subparsers.add_parser(
        "team-roster-batch-edit",
        help="Batch edit proven linked and authoritative same-entry roster slots from CSV",
    )
    team_roster_batch_edit_parser.add_argument(
        "file",
        nargs="?",
        default="DBDAT/EQ98030.FDI",
        help="Path to EQ98030.FDI (default: DBDAT/EQ98030.FDI)",
    )
    team_roster_batch_edit_parser.add_argument(
        "--player-file",
        default="DBDAT/JUG98030.FDI",
        help="Path to JUG98030.FDI for player-name resolution",
    )
    team_roster_batch_edit_parser.add_argument(
        "--csv",
        required=True,
        help="Path to a CSV plan with team, slot, source, and row values",
    )
    team_roster_batch_edit_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and stage only (no file write)",
    )
    team_roster_batch_edit_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    team_roster_batch_edit_parser.set_defaults(func=cmd_team_roster_batch_edit)

    team_roster_profile_same_entry_parser = subparsers.add_parser(
        "team-roster-profile-same-entry",
        help="Profile the trailing 3 bytes in preferred same-entry roster rows",
    )
    team_roster_profile_same_entry_parser.add_argument(
        "file",
        nargs="?",
        default="DBDAT/EQ98030.FDI",
        help="Path to EQ98030.FDI (default: DBDAT/EQ98030.FDI)",
    )
    team_roster_profile_same_entry_parser.add_argument(
        "--player-file",
        default="DBDAT/JUG98030.FDI",
        help="Path to JUG98030.FDI for dd6361 PID -> player-name resolution",
    )
    team_roster_profile_same_entry_parser.add_argument(
        "--team",
        action="append",
        default=[],
        help="Optional team query filter (repeatable). Omit to profile all parsed team names.",
    )
    team_roster_profile_same_entry_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Max buckets to print (default: 10)",
    )
    team_roster_profile_same_entry_parser.add_argument(
        "--include-fallbacks",
        action="store_true",
        help="Include all preferred same-entry fallback provenances, not just same_entry_authoritative",
    )
    team_roster_profile_same_entry_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    team_roster_profile_same_entry_parser.set_defaults(func=cmd_team_roster_profile_same_entry)

    # Coach commands
    coach_list_parser = subparsers.add_parser("coach-list", help="List coach records")
    coach_list_parser.add_argument("file", help="FDI file path")
    coach_list_parser.add_argument("--limit", type=int, help="Maximum records to list")
    coach_list_parser.add_argument("--include-uncertain", action="store_true", help="Include uncertain records")
    coach_list_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    coach_list_parser.set_defaults(func=cmd_coach_list)

    coach_search_parser = subparsers.add_parser("coach-search", help="Search coach records by name")
    coach_search_parser.add_argument("file", help="FDI file path")
    coach_search_parser.add_argument("name", help="Coach name query")
    coach_search_parser.add_argument("--include-uncertain", action="store_true", help="Include uncertain records")
    coach_search_parser.add_argument("--json", action="store_true", help="Emit JSON output")
    coach_search_parser.set_defaults(func=cmd_coach_search)

    coach_rename_parser = subparsers.add_parser("coach-rename", help="Rename coach record(s) by current name")
    coach_rename_parser.add_argument("file", help="FDI file path")
    coach_rename_parser.add_argument("--old", required=True, help="Current coach name")
    coach_rename_parser.add_argument("--new", required=True, help="New coach name")
    coach_rename_parser.add_argument("--offset", help="Optional record offset (hex or decimal)")
    coach_rename_parser.add_argument("--include-uncertain", action="store_true", help="Include uncertain records")
    coach_rename_parser.add_argument("--dry-run", action="store_true", help="Validate and stage only (no file write)")
    coach_rename_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    coach_rename_parser.set_defaults(func=cmd_coach_rename)

    # Bulk player rename/revert commands (M1)
    bulk_player_rename_parser = subparsers.add_parser("bulk-player-rename", help="Deterministic bulk rename for player files")
    bulk_player_rename_parser.add_argument("--data-dir", required=True, help="Directory containing JUG*.FDI files")
    bulk_player_rename_parser.add_argument("--map-output", required=True, help="Output CSV path")
    bulk_player_rename_parser.add_argument("--dry-run", action="store_true", help="Write mapping only, no FDI modifications")
    bulk_player_rename_parser.add_argument("--skip-integrity-checks", action="store_true", help="Skip consistency checks")
    bulk_player_rename_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    bulk_player_rename_parser.set_defaults(func=cmd_bulk_player_rename)

    bulk_player_revert_parser = subparsers.add_parser("bulk-player-revert", help="Revert deterministic bulk player renames")
    bulk_player_revert_parser.add_argument("--data-dir", required=True, help="Directory containing JUG*.FDI files")
    bulk_player_revert_parser.add_argument("--map-input", required=True, help="Mapping CSV path")
    bulk_player_revert_parser.add_argument("--dry-run", action="store_true", help="Validate mapping only, no FDI modifications")
    bulk_player_revert_parser.add_argument("--skip-integrity-checks", action="store_true", help="Skip consistency checks")
    bulk_player_revert_parser.add_argument("--json", action="store_true", help="Emit JSON result")
    bulk_player_revert_parser.set_defaults(func=cmd_bulk_player_revert)
    
    # PKF Search command
    pkf_search_parser = subparsers.add_parser("pkf-search", help="Search for strings/patterns in PKF files")
    pkf_search_parser.add_argument("directory", help="Directory containing PKF files")
    pkf_search_parser.add_argument("query", help="Search query (text, regex, or hex)")
    pkf_search_parser.add_argument("--mode", choices=["text", "regex", "hex"], default="text",
                                   help="Search mode (default: text)")
    pkf_search_parser.add_argument("--encoding", default="utf-8",
                                   choices=["utf-8", "cp1252", "latin1", "raw"],
                                   help="Text encoding (default: utf-8)")
    pkf_search_parser.add_argument("--case-sensitive", action="store_true",
                                   help="Enable case-sensitive search")
    pkf_search_parser.add_argument("--xor", metavar="KEY",
                                   help="XOR key for decoding (hex or decimal)")
    pkf_search_parser.add_argument("--context", type=int, default=32,
                                   help="Context bytes before/after match (default: 32)")
    pkf_search_parser.add_argument("--no-recursive", action="store_true",
                                   help="Don't search subdirectories")
    pkf_search_parser.add_argument("--file-pattern", default="*.pkf",
                                   help="PKF file pattern (default: *.pkf)")
    pkf_search_parser.add_argument("--limit", type=int, default=1000,
                                   help="Maximum results (default: 1000)")
    pkf_search_parser.add_argument("--export", metavar="FILE",
                                   help="Export results to CSV or JSON file")
    pkf_search_parser.add_argument("--no-parallel", action="store_true",
                                   help="Disable parallel processing")
    pkf_search_parser.set_defaults(func=cmd_pkf_search)
    
    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
