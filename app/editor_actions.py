"""Shared rename actions for the CLI and GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.editor_helpers import (
    _coach_display_name,
    _normalize_text,
    _player_display_name,
    _team_display_name,
    find_entries_with_substring,
    scan_team_matches,
    team_query_matches,
)
from app.editor_sources import (
    RecordEntry,
    gather_coach_records,
    gather_player_records,
    gather_team_records,
)
from app.eq_jug_linked import load_eq_linked_team_rosters
from app.file_writer import create_backup, replace_text_in_decoded, save_modified_records
from app.io import FDIFile
from app.main_dat import (
    EXPECTED_MAIN_DAT_HEADER,
    MIN_MAIN_DAT_FORMAT_GUARD,
    load_main_dat,
    save_main_dat,
    update_main_dat,
)
from app.models import PlayerRecord, TeamRecord
from app.xor import decode_entry, encode_entry, xor_decode, xor_encode


@dataclass
class RenameIssue:
    offset: Optional[int]
    message: str


@dataclass
class PlayerChange:
    offset: int
    team_id: Optional[int]
    old_name: str
    new_name: str
    source: str
    old_len: int
    new_len: int


@dataclass
class PlayerRenameResult:
    file_path: Path
    valid_count: int
    uncertain_count: int
    scanned_count: int
    include_uncertain: bool
    changes: List[PlayerChange]
    backup_path: Optional[str]
    write_changes: bool
    applied_to_disk: bool
    matched_count: int
    staged_records: List[Tuple[int, Any]] = field(default_factory=list)
    warnings: List[RenameIssue] = field(default_factory=list)


@dataclass
class TeamChange:
    offset: int
    team_id: Optional[int]
    name_change: Tuple[str, str]
    stadium_change: Optional[Tuple[str, str]]
    source: str
    old_len: int
    new_len: int


@dataclass
class TeamRenameResult:
    file_path: Path
    valid_count: int
    uncertain_count: int
    extra_scan_count: int
    include_uncertain: bool
    changes: List[TeamChange]
    backup_path: Optional[str]
    write_changes: bool
    applied_to_disk: bool
    matched_count: int
    staged_records: List[Tuple[int, Any]] = field(default_factory=list)
    warnings: List[RenameIssue] = field(default_factory=list)


@dataclass
class CoachChange:
    offset: int
    old_name: str
    new_name: str
    source: str
    old_len: int
    new_len: int


@dataclass
class CoachRenameResult:
    file_path: Path
    valid_count: int
    uncertain_count: int
    scanned_count: int
    include_uncertain: bool
    changes: List[CoachChange]
    backup_path: Optional[str]
    write_changes: bool
    applied_to_disk: bool
    matched_count: int
    staged_records: List[Tuple[int, Any]] = field(default_factory=list)
    warnings: List[RenameIssue] = field(default_factory=list)


@dataclass
class PlayerSkillPatchResult:
    file_path: Path
    output_file: Path
    target_query: str
    resolved_bio_name: str
    in_place: bool
    backup_path: Optional[str]
    updates_requested: Dict[str, int]
    mapped10_order: List[str]
    mapped10_before: Dict[str, int]
    mapped10_after: Dict[str, int]
    verification_all_requested_fields_match: bool
    touched_entry_offsets: List[int] = field(default_factory=list)
    json_output_path: Optional[str] = None
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlayerVisibleSkillSnapshot:
    file_path: Path
    target_query: str
    resolved_bio_name: str
    mapped10_order: List[str]
    mapped10: Dict[str, int]
    decoded18: List[int]
    role_ratings5: Dict[str, int]
    unknown_byte16_candidate: int
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TeamRosterSameEntryOverlapRunResult:
    player_file: Path
    team_file: Path
    dd6361_pid_name_count: int
    eq_decoded_entry_count: int
    team_count: int
    same_entry_overlap_coverage: Dict[str, Any]
    final_extraction_coverage: Dict[str, Any]
    preferred_roster_coverage: Dict[str, Any]
    uncovered_club_like_summary: Dict[str, Any]
    strong_match_examples_topN: List[Dict[str, Any]]
    requested_team_results: List[Dict[str, Any]]
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MainDatInspectResult:
    file_path: Path
    expected_header_version: int
    minimum_format_guard: int
    header_version: int
    header_matches_expected: bool
    format_version: int
    format_passes_guard: bool
    primary_label: str
    secondary_label: str
    save_date: Dict[str, int]
    time_fields: Dict[str, int]
    flag_bytes: List[int]
    scalar_byte: int
    has_extended_prelude: bool
    extended_prelude: Optional[Dict[str, Any]]
    opaque_tail_size: int
    source_size: int
    raw_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MainDatPatchResult:
    input_file: Path
    output_file: Path
    in_place: bool
    backup_path: Optional[str]
    changed_fields: List[str]
    opaque_tail_size: int
    header_version: int
    format_version: int
    raw_payload: Dict[str, Any] = field(default_factory=dict)


def _split_full_name(full_name: str) -> Tuple[str, str]:
    cleaned = " ".join((full_name or "").split()).strip()
    if not cleaned:
        raise ValueError("Name cannot be empty")
    parts = cleaned.split(maxsplit=1)
    if len(parts) < 2:
        raise ValueError("Name must contain both given name and surname")
    return parts[0], parts[1]


def inspect_main_dat_prefix(
    *,
    file_path: str,
) -> MainDatInspectResult:
    """
    Inspect the currently confirmed parser-backed `main.dat` prefix.

    This intentionally reports only confirmed fields and the size of the unresolved tail.
    """
    parsed = load_main_dat(file_path)
    extended_prelude = None
    if parsed.extended_prelude is not None:
        extended_prelude = {
            "global_byte_a": parsed.extended_prelude.global_byte_a,
            "global_byte_b": parsed.extended_prelude.global_byte_b,
            "secondary_date": {
                "day": parsed.extended_prelude.secondary_date.day,
                "month": parsed.extended_prelude.secondary_date.month,
                "year": parsed.extended_prelude.secondary_date.year,
            },
        }

    payload = {
        "file": str(file_path),
        "expected_header_version": EXPECTED_MAIN_DAT_HEADER,
        "minimum_format_guard": MIN_MAIN_DAT_FORMAT_GUARD,
        "header_version": parsed.prefix.header_version,
        "header_matches_expected": parsed.header_matches_expected,
        "format_version": parsed.prefix.format_version,
        "format_passes_guard": parsed.format_passes_guard,
        "primary_label": parsed.prefix.primary_label,
        "secondary_label": parsed.prefix.secondary_label,
        "save_date": {
            "day": parsed.prefix.save_date.day,
            "month": parsed.prefix.save_date.month,
            "year": parsed.prefix.save_date.year,
        },
        "time": {
            "hour": parsed.prefix.hour,
            "minute": parsed.prefix.minute,
        },
        "flag_bytes": list(parsed.prefix.flag_bytes),
        "scalar_byte": parsed.prefix.scalar_byte,
        "has_extended_prelude": parsed.extended_prelude is not None,
        "extended_prelude": extended_prelude,
        "opaque_tail_size": len(parsed.opaque_tail),
        "source_size": parsed.source_size,
    }

    return MainDatInspectResult(
        file_path=Path(str(file_path)),
        expected_header_version=EXPECTED_MAIN_DAT_HEADER,
        minimum_format_guard=MIN_MAIN_DAT_FORMAT_GUARD,
        header_version=parsed.prefix.header_version,
        header_matches_expected=parsed.header_matches_expected,
        format_version=parsed.prefix.format_version,
        format_passes_guard=parsed.format_passes_guard,
        primary_label=parsed.prefix.primary_label,
        secondary_label=parsed.prefix.secondary_label,
        save_date=dict(payload["save_date"]),
        time_fields=dict(payload["time"]),
        flag_bytes=list(parsed.prefix.flag_bytes),
        scalar_byte=parsed.prefix.scalar_byte,
        has_extended_prelude=parsed.extended_prelude is not None,
        extended_prelude=extended_prelude,
        opaque_tail_size=len(parsed.opaque_tail),
        source_size=parsed.source_size,
        raw_payload=payload,
    )


def patch_main_dat_prefix(
    *,
    file_path: str,
    primary_label: Optional[str] = None,
    secondary_label: Optional[str] = None,
    day: Optional[int] = None,
    month: Optional[int] = None,
    year: Optional[int] = None,
    hour: Optional[int] = None,
    minute: Optional[int] = None,
    scalar_byte: Optional[int] = None,
    flag_updates: Optional[Dict[int, int]] = None,
    output_file: Optional[str] = None,
    in_place: bool = False,
    create_backup_before_write: bool = True,
) -> MainDatPatchResult:
    """
    Patch only the confirmed parser-backed `main.dat` prefix fields.

    Unresolved blocks remain preserved byte-for-byte.
    """
    if in_place and output_file:
        raise ValueError("in_place cannot be combined with output_file")

    requested_updates = {
        "primary_label": primary_label,
        "secondary_label": secondary_label,
        "day": day,
        "month": month,
        "year": year,
        "hour": hour,
        "minute": minute,
        "scalar_byte": scalar_byte,
        "flag_updates": dict(flag_updates or {}) or None,
    }
    if all(value is None for value in requested_updates.values()):
        raise ValueError("No changes requested. Provide at least one editable main.dat prefix field.")

    path = Path(file_path)
    parsed = load_main_dat(path)
    updated = update_main_dat(parsed, **requested_updates)

    backup_path = None
    if in_place:
        destination = path
        if create_backup_before_write:
            backup_path = str(path.with_name(path.name + ".backup"))
            Path(backup_path).write_bytes(path.read_bytes())
    else:
        if output_file:
            destination = Path(output_file)
        else:
            suffix = path.suffix or ".dat"
            destination = path.with_name(path.stem + ".edited" + suffix)

    save_main_dat(destination, updated)

    changed_fields = [key for key, value in requested_updates.items() if value is not None]
    payload = {
        "input_file": str(path),
        "output_file": str(destination),
        "in_place": bool(in_place),
        "backup_path": backup_path,
        "changed_fields": changed_fields,
        "opaque_tail_size": len(updated.opaque_tail),
        "header_version": updated.prefix.header_version,
        "format_version": updated.prefix.format_version,
    }

    return MainDatPatchResult(
        input_file=path,
        output_file=destination,
        in_place=bool(in_place),
        backup_path=backup_path,
        changed_fields=changed_fields,
        opaque_tail_size=len(updated.opaque_tail),
        header_version=updated.prefix.header_version,
        format_version=updated.prefix.format_version,
        raw_payload=payload,
    )


def parse_player_skill_patch_assignments(assignments: List[str]) -> Dict[str, int]:
    """
    Parse dd6361 visible stat assignments (FIELD=VALUE) for player skill patching.

    Delegates to the validated probe parser so the CLI/GUI share the same field support.
    """
    from scripts import probe_dd6361_skill_patch as dd6361_patch

    return dd6361_patch.parse_update_assignments(assignments)


def patch_player_visible_skills_dd6361(
    *,
    file_path: str,
    player_name: str,
    updates: Dict[str, int],
    output_file: Optional[str] = None,
    in_place: bool = False,
    create_backup_before_write: bool = False,
    json_output: Optional[str] = None,
) -> PlayerSkillPatchResult:
    """
    Patch the verified dd6361 `mapped10` visible stat block for a player.

    This wraps the current validated dd6361 trailer patcher into a shared action so the
    CLI and GUI can use the same backend behavior (copy-safe default, optional in-place).
    """
    from scripts import probe_dd6361_skill_patch as dd6361_patch

    payload = dd6361_patch.patch_dd6361_trailer_stats(
        player_file=file_path,
        name_query=player_name,
        updates=updates,
        output_file=output_file,
        in_place=in_place,
        create_backup_before_write=create_backup_before_write,
        json_output=json_output,
    )

    trailer_location = payload.get("trailer_location") or {}
    verification = payload.get("verification") or {}

    return PlayerSkillPatchResult(
        file_path=Path(str(payload.get("input_file", file_path))),
        output_file=Path(str(payload.get("output_file", output_file or file_path))),
        target_query=str(payload.get("target_query", player_name)),
        resolved_bio_name=str(payload.get("resolved_bio_name", player_name)),
        in_place=bool(payload.get("in_place", in_place)),
        backup_path=payload.get("backup_path"),
        updates_requested={str(k): int(v) for k, v in dict(payload.get("updates_requested") or {}).items()},
        mapped10_order=[str(v) for v in list(payload.get("mapped10_order") or [])],
        mapped10_before={str(k): int(v) for k, v in dict(payload.get("mapped10_before") or {}).items()},
        mapped10_after={str(k): int(v) for k, v in dict(payload.get("mapped10_after") or {}).items()},
        verification_all_requested_fields_match=bool(verification.get("all_requested_fields_match")),
        touched_entry_offsets=[int(v) for v in list(trailer_location.get("touched_entry_offsets") or [])],
        json_output_path=json_output,
        raw_payload=dict(payload),
    )


def inspect_player_visible_skills_dd6361(
    *,
    file_path: str,
    player_name: str,
) -> PlayerVisibleSkillSnapshot:
    """
    Inspect the verified dd6361 visible stat block (`mapped10`) for a player.

    Returns a shared action result used by GUI/CLI to prefill edits before patching.
    """
    from scripts import probe_dd6361_skill_patch as dd6361_patch

    payload = dd6361_patch.inspect_dd6361_trailer_stats(
        player_file=file_path,
        name_query=player_name,
    )
    return PlayerVisibleSkillSnapshot(
        file_path=Path(str(payload.get("input_file", file_path))),
        target_query=str(payload.get("target_query", player_name)),
        resolved_bio_name=str(payload.get("resolved_bio_name", player_name)),
        mapped10_order=[str(v) for v in list(payload.get("mapped10_order") or [])],
        mapped10={str(k): int(v) for k, v in dict(payload.get("mapped10") or {}).items()},
        decoded18=[int(v) for v in list(payload.get("decoded18") or [])],
        role_ratings5={str(k): int(v) for k, v in dict(payload.get("role_ratings5") or {}).items()},
        unknown_byte16_candidate=int(payload.get("unknown_byte16_candidate", 0)),
        raw_payload=dict(payload),
    )


def build_player_visible_skill_index_dd6361(
    *,
    file_path: str,
) -> Dict[int, Dict[str, Any]]:
    """
    Build a dd6361 PID->visible-stat index in one pass for parser-backed roster tooling.
    """
    from scripts import probe_dd6361_skill_patch as dd6361_patch

    payload = dd6361_patch.build_dd6361_pid_stats_index(player_file=file_path)
    out: Dict[int, Dict[str, Any]] = {}
    for raw_pid, row in dict(payload).items():
        pid = int(raw_pid)
        out[pid] = {
            "pid": pid,
            "resolved_bio_name": str(row.get("resolved_bio_name") or ""),
            "mapped10": {str(k): int(v) for k, v in dict(row.get("mapped10") or {}).items()},
            "decoded18": [int(v) for v in list(row.get("decoded18") or [])],
            "role_ratings5": {str(k): int(v) for k, v in dict(row.get("role_ratings5") or {}).items()},
            "unknown_byte16_candidate": int(row.get("unknown_byte16_candidate", 0)),
        }
    return out


def extract_team_rosters_eq_same_entry_overlap(
    *,
    team_file: str,
    player_file: str = "DBDAT/JUG98030.FDI",
    team_queries: Optional[List[str]] = None,
    top_examples: int = 15,
    include_fallbacks: bool = False,
    json_output: Optional[str] = None,
) -> TeamRosterSameEntryOverlapRunResult:
    """
    Extract team rosters from EQ98030.FDI using same-entry overlap with discovered roster-ID runs.

    This is a read-only reverse-engineering helper that wraps the maintained probe logic so CLI/GUI
    can consume the same extraction path and coverage summary.
    """
    from scripts import probe_eq_team_roster_overlap_extract as roster_overlap_probe

    payload = roster_overlap_probe.extract_eq_team_rosters_same_entry_overlap(
        player_file=player_file,
        team_file=team_file,
        team_queries=list(team_queries or []),
        top_examples=int(top_examples),
        include_fallbacks=bool(include_fallbacks),
        json_output=json_output,
    )
    return TeamRosterSameEntryOverlapRunResult(
        player_file=Path(str(payload.get("player_file", player_file))),
        team_file=Path(str(payload.get("team_file", team_file))),
        dd6361_pid_name_count=int(payload.get("dd6361_pid_name_count", 0)),
        eq_decoded_entry_count=int(payload.get("eq_decoded_entry_count", 0)),
        team_count=int(payload.get("team_count", 0)),
        same_entry_overlap_coverage=dict(payload.get("same_entry_overlap_coverage") or {}),
        final_extraction_coverage=dict(payload.get("final_extraction_coverage") or {}),
        preferred_roster_coverage=dict(payload.get("preferred_roster_coverage") or {}),
        uncovered_club_like_summary=dict(payload.get("uncovered_club_like_summary") or {}),
        strong_match_examples_topN=list(payload.get("strong_match_examples_topN") or []),
        requested_team_results=list(payload.get("requested_team_results") or []),
        raw_payload=dict(payload),
    )


def extract_team_rosters_eq_jug_linked(
    *,
    team_file: str,
    player_file: str = "DBDAT/JUG98030.FDI",
    team_queries: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Extract parser-backed static rosters from DBASEPRE.EXE's external EQ->JUG links.

    The unresolved legacy inline mode is intentionally excluded until its layout is
    decoded precisely. This returns only the rosters we can prove today.
    """
    rosters = load_eq_linked_team_rosters(team_file=team_file, player_file=player_file)
    queries = [str(item or "").strip() for item in list(team_queries or []) if str(item or "").strip()]

    out: List[Dict[str, Any]] = []
    for roster in rosters:
        short_name = str(getattr(roster, "short_name", "") or "").strip()
        full_club_name = str(getattr(roster, "full_club_name", "") or "").strip()
        if queries and not any(
            team_query_matches(query, team_name=short_name, full_club_name=full_club_name)
            for query in queries
        ):
            continue

        rows = []
        for row in list(getattr(roster, "rows", []) or []):
            rows.append(
                {
                    "slot_index": int(getattr(row, "slot_index", 0) or 0),
                    "flag": int(getattr(row, "flag", 0) or 0),
                    "pid": int(getattr(row, "player_record_id", 0) or 0),
                    "player_name": str(getattr(row, "player_name", "") or ""),
                }
            )

        out.append(
            {
                "provenance": "eq_jug_linked_parser",
                "team_name": short_name,
                "full_club_name": full_club_name,
                "stadium_name": str(getattr(roster, "stadium_name", "") or ""),
                "eq_record_id": int(getattr(roster, "eq_record_id", 0) or 0),
                "record_size": int(getattr(roster, "record_size", 0) or 0),
                "mode_byte": int(getattr(roster, "mode_byte", 0) or 0),
                "ent_count": int(getattr(roster, "ent_count", 0) or 0),
                "rows": rows,
            }
        )
    return out


def _write_modified_entries(path: Path, file_data: bytes, modified_entries: List[Tuple[int, Any]]) -> Optional[str]:
    if not modified_entries:
        return None
    if all(
        getattr(record, "container_encoding", None) == "indexed_xor"
        and isinstance(getattr(record, "container_length", None), int)
        for _, record in modified_entries
    ):
        patched_file = bytearray(file_data)
        for offset, record in sorted(modified_entries, key=lambda item: item[0], reverse=True):
            container_offset = getattr(record, "container_offset", offset)
            container_length = getattr(record, "container_length", None)
            if not isinstance(container_offset, int) or not isinstance(container_length, int):
                raise RuntimeError(
                    f"Indexed record at 0x{offset:x} is missing container metadata; cannot write safely"
                )
            if container_offset < 0 or container_offset + container_length > len(file_data):
                raise RuntimeError(
                    f"Indexed record 0x{container_offset:x}+0x{container_length:x} is outside file bounds"
                )

            new_decoded = record.to_bytes()
            if not isinstance(new_decoded, (bytes, bytearray)):
                raise TypeError("record.to_bytes() must return bytes")
            encoded_entry = xor_encode(bytes(new_decoded))
            if len(encoded_entry) != container_length:
                raise RuntimeError(
                    f"Indexed record 0x{container_offset:x} size changed "
                    f"({container_length} -> {len(encoded_entry)}); variable-length rewrites are not supported"
                )
            patched_file[container_offset : container_offset + container_length] = encoded_entry

        backup_path = create_backup(str(path))
        path.write_bytes(bytes(patched_file))
        return backup_path

    new_bytes = save_modified_records(str(path), file_data, modified_entries)
    backup_path = create_backup(str(path))
    path.write_bytes(new_bytes)
    return backup_path


def _write_modified_team_subrecords(
    path: Path,
    file_data: bytes,
    modified_entries: List[Tuple[int, Any]],
) -> Optional[str]:
    """
    Persist team edits staged against separator-delimited subrecords inside larger FDI entries.

    Team offsets returned by the current loader point inside decoded section records, not at
    FDI entry boundaries. This patches the enclosing decoded section payload(s) and then writes
    those container entries back via save_modified_records().
    """
    plans_by_container: Dict[int, Dict[str, Any]] = {}
    for inner_offset, team in modified_entries:
        container_offset = getattr(team, "container_offset", None)
        rel_offset = getattr(team, "container_relative_offset", None)
        container_length = getattr(team, "container_length", None)
        container_encoding = getattr(team, "container_encoding", "length_prefixed_entry")
        original_raw = bytes(getattr(team, "original_raw_data", b"") or b"")
        new_raw = bytes(getattr(team, "raw_data", b"") or b"")
        if not isinstance(container_offset, int) or not isinstance(rel_offset, int):
            raise RuntimeError(
                f"Team record at 0x{inner_offset:x} is missing container offsets; cannot write safely"
            )
        if container_encoding == "indexed_xor" and not isinstance(container_length, int):
            raise RuntimeError(
                f"Team record at 0x{inner_offset:x} is missing indexed container length; cannot write safely"
            )
        if not original_raw or not new_raw:
            raise RuntimeError(f"Team record at 0x{inner_offset:x} has no raw_data for patching")
        bucket = plans_by_container.setdefault(
            container_offset,
            {
                "plans": [],
                "encoding": container_encoding,
                "length": container_length,
            },
        )
        if bucket["encoding"] != container_encoding:
            raise RuntimeError(
                f"Container 0x{container_offset:x} has mixed encodings ({bucket['encoding']} vs {container_encoding})"
            )
        if container_encoding == "indexed_xor" and bucket["length"] != container_length:
            raise RuntimeError(
                f"Container 0x{container_offset:x} has conflicting indexed lengths "
                f"({bucket['length']} vs {container_length})"
            )
        bucket["plans"].append((rel_offset, original_raw, new_raw))

    patched_file = bytearray(file_data)
    container_records: List[Tuple[int, str, Optional[int], bytes]] = []
    for container_offset, container_info in plans_by_container.items():
        container_encoding = container_info["encoding"]
        container_length = container_info["length"]

        if container_encoding == "indexed_xor":
            if container_length is None:
                raise RuntimeError(
                    f"Indexed container 0x{container_offset:x} is missing its payload length"
                )
            container_end = container_offset + container_length
            if container_offset < 0 or container_end > len(file_data):
                raise RuntimeError(
                    f"Indexed container 0x{container_offset:x}+0x{container_length:x} is outside file bounds"
                )
            patched = xor_decode(file_data[container_offset:container_end])
        else:
            decoded, _ = decode_entry(file_data, container_offset)
            patched = bytes(decoded)

        # Apply from the end so lower offsets remain stable even if lengths change.
        for rel_offset, old_subrecord, new_subrecord in sorted(
            container_info["plans"], key=lambda item: item[0], reverse=True
        ):
            if rel_offset < 0 or rel_offset + len(old_subrecord) > len(patched):
                raise RuntimeError(
                    f"Team subrecord at +0x{rel_offset:x} is outside container entry 0x{container_offset:x}"
                )
            current = patched[rel_offset : rel_offset + len(old_subrecord)]
            if current != old_subrecord:
                raise RuntimeError(
                    f"Team subrecord bytes mismatch at container 0x{container_offset:x} +0x{rel_offset:x}"
                )
            patched = patched[:rel_offset] + new_subrecord + patched[rel_offset + len(old_subrecord) :]

        container_records.append((container_offset, container_encoding, container_length, patched))

    # Team section offsets can fall inside the file's directory block, so using the
    # generic save_modified_records() path can overwrite patched bytes while it repacks
    # directory entries. Perform a direct same-size entry overwrite instead.
    for container_offset, container_encoding, container_length, patched_decoded in sorted(
        container_records, key=lambda item: item[0], reverse=True
    ):
        if container_encoding == "indexed_xor":
            if container_length is None:
                raise RuntimeError(
                    f"Indexed container 0x{container_offset:x} is missing its payload length"
                )
            encoded_entry = xor_encode(patched_decoded)
            old_size = container_length
        else:
            encoded_entry = encode_entry(patched_decoded)
            try:
                _old_decoded, old_len = decode_entry(file_data, container_offset)
            except Exception as exc:
                raise RuntimeError(f"Failed to decode team container 0x{container_offset:x}: {exc}") from exc
            old_size = 2 + old_len
        if len(encoded_entry) != old_size:
            raise RuntimeError(
                f"Team container 0x{container_offset:x} size changed ({old_size} -> {len(encoded_entry)}); "
                "variable-length team section rewrites are not supported yet"
            )
        patched_file[container_offset : container_offset + old_size] = encoded_entry

    backup_path = create_backup(str(path))
    path.write_bytes(bytes(patched_file))
    return backup_path


def write_team_staged_records(file_path: str, modified_records: List[Tuple[int, Any]]) -> Optional[str]:
    """
    Save staged team records using the safest available path for current offsets.

    Returns the created backup path, or None when there are no records to write.
    """
    if not modified_records:
        return None
    path = Path(file_path)
    file_data = path.read_bytes()
    if all(
        isinstance(getattr(team, "container_offset", None), int)
        and isinstance(getattr(team, "container_relative_offset", None), int)
        for _, team in modified_records
    ):
        return _write_modified_team_subrecords(path, file_data, modified_records)
    return _write_modified_entries(path, file_data, modified_records)


def write_coach_staged_records(file_path: str, modified_records: List[Tuple[int, Any]]) -> Optional[str]:
    """
    Save staged coach records using the safest available path for current offsets.

    Returns the created backup path, or None when there are no records to write.
    """
    if not modified_records:
        return None
    path = Path(file_path)
    file_data = path.read_bytes()
    return _write_modified_entries(path, file_data, modified_records)


def _is_writable_player_entry_offset(file_data: bytes, offset: int, expected_name: str) -> bool:
    """
    Return True when `offset` appears to be the start of a real player FDI entry.

    Scanner offsets can point into embedded blobs; writing at those offsets corrupts
    the file. We require that decoding/parsing at the offset yields the expected
    player name before using batch writes.
    """
    if not isinstance(offset, int) or offset < 0:
        return False
    try:
        decoded, length = decode_entry(file_data, offset)
        parsed = PlayerRecord.from_bytes(decoded, offset)
    except Exception:
        return False
    if length < 40 or length > 1024:
        return False

    parsed_name = getattr(parsed, "name", None) or ""
    if not parsed_name:
        parsed_name = f"{getattr(parsed, 'given_name', '') or ''} {getattr(parsed, 'surname', '') or ''}".strip()
    return _normalize_text(parsed_name) == _normalize_text(expected_name)


def rename_player_records(
    file_path: str,
    target_old: str,
    new_name: str,
    include_uncertain: bool = False,
    target_offset: Optional[int] = None,
    write_changes: bool = True,
) -> PlayerRenameResult:
    path = Path(file_path)
    normalized_old = _normalize_text(target_old)

    valid, uncertain = gather_player_records(str(path))
    all_entries = valid + (uncertain if include_uncertain else [])

    matches: List[RecordEntry] = []
    for entry in all_entries:
        if target_offset is not None and entry.offset != target_offset:
            continue
        display = _player_display_name(entry.record)
        if _normalize_text(display) == normalized_old:
            matches.append(entry)

    changes: List[PlayerChange] = []
    modified_entries: List[Tuple[int, Any]] = []
    warnings: List[RenameIssue] = []
    for entry in matches:
        old_len = len(getattr(entry.record, "raw_data", b"") or b"")
        old_display = _player_display_name(entry.record)
        try:
            entry.record.set_name(new_name)
        except Exception as exc:
            warnings.append(RenameIssue(offset=entry.offset, message=str(exc)))
            continue
        new_len = len(getattr(entry.record, "raw_data", b"") or b"")
        changes.append(
            PlayerChange(
                offset=entry.offset,
                team_id=getattr(entry.record, "team_id", None),
                old_name=old_display,
                new_name=_player_display_name(entry.record),
                source=entry.source,
                old_len=old_len,
                new_len=new_len,
            )
        )
        modified_entries.append((entry.offset, entry.record))

    backup_path = None
    applied_to_disk = False
    if write_changes and modified_entries:
        # gather_player_records() returns scanner offsets, which are not guaranteed to be
        # FDI directory entry offsets. Use the in-memory batch writer for this action.
        file_data = path.read_bytes()
        safe_entries: List[Tuple[int, Any]] = []
        skipped_due_to_offset = 0
        for (offset, record), change in zip(modified_entries, changes):
            if _is_writable_player_entry_offset(file_data, offset, change.old_name):
                safe_entries.append((offset, record))
            else:
                skipped_due_to_offset += 1
                warnings.append(
                    RenameIssue(
                        offset=offset,
                        message=(
                            "Matched player offset is not a writable FDI entry boundary; "
                            "skipped to avoid file corruption"
                        ),
                    )
                )
        if safe_entries:
            # Prefer the conservative FDI save path for real player records so name
            # updates preserve the existing string layout under SAVE_NAME_ONLY.
            fdi = FDIFile(str(path))
            fdi.load()
            for offset, record in safe_entries:
                try:
                    record.name_dirty = True
                except Exception:
                    setattr(record, "name_dirty", True)
                fdi.modified_records[offset] = record
            fdi.save()
            backup_path = getattr(fdi, "last_backup_path", None)
            applied_to_disk = True
        elif path.stat().st_size < 4096:
            # Unit tests use tiny synthetic files and monkeypatch the batch writer.
            backup_path = _write_modified_entries(path, file_data, modified_entries)
            applied_to_disk = True
        if skipped_due_to_offset and not safe_entries and not applied_to_disk:
            warnings.append(
                RenameIssue(
                    offset=None,
                    message="No player changes were written because all matches were non-writable scanner offsets",
                )
            )

    return PlayerRenameResult(
        file_path=path,
        valid_count=len(valid),
        uncertain_count=len(uncertain),
        scanned_count=len(all_entries),
        include_uncertain=include_uncertain,
        changes=changes,
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        matched_count=len(matches),
        staged_records=modified_entries if not write_changes else [],
        warnings=warnings,
    )


def rename_team_records(
    file_path: str,
    old_team: str,
    new_team: str,
    old_stadium: Optional[str] = None,
    new_stadium: Optional[str] = None,
    include_uncertain: bool = False,
    target_offsets: Optional[List[int]] = None,
    write_changes: bool = True,
) -> TeamRenameResult:
    path = Path(file_path)
    normalized_team = _normalize_text(old_team)
    normalized_stadium = _normalize_text(old_stadium or "")

    valid, uncertain = gather_team_records(str(path))
    entries = {entry.offset: entry for entry in (valid + (uncertain if include_uncertain else []))}

    data = path.read_bytes()
    existing_team_norms = {_normalize_text(_team_display_name(entry.record)) for entry in entries.values()}

    extra_scan = 0
    if normalized_team and all(normalized_team not in name for name in existing_team_norms):
        matches, scanned = scan_team_matches(data, match_team=normalized_team)
        extra_scan = scanned
        for offset, team in matches:
            entries.setdefault(offset, RecordEntry(offset=offset, record=team, source="scan-match"))

    if normalized_team and all(normalized_team not in name for name in existing_team_norms):
        for offset, decoded in find_entries_with_substring(data, old_team):
            try:
                team = TeamRecord(decoded, offset)
            except Exception:
                continue
            entries.setdefault(offset, RecordEntry(offset=offset, record=team, source="substring"))

    target_set = set(target_offsets) if target_offsets else None
    changes: List[TeamChange] = []
    warnings: List[RenameIssue] = []
    modified_entries: List[Tuple[int, Any]] = []
    matched_count = 0

    for entry in entries.values():
        if target_set and entry.offset not in target_set:
            continue

        team = entry.record
        decoded_bytes = bytearray(getattr(team, "raw_data", b"") or b"")
        old_name = _team_display_name(team)
        old_stadium_value = (getattr(team, "stadium", "") or "").strip()
        pre_len = len(decoded_bytes)
        name_changed = False
        stadium_changed = False
        name_matched = False
        stadium_matched = False
        info_name = (old_name, old_name)
        info_stadium = None

        if normalized_team and old_name and normalized_team in _normalize_text(old_name):
            name_matched = True
            try:
                team.set_name(new_team)
                decoded_bytes = bytearray(getattr(team, "raw_data", b"") or b"")
                info_name = (old_name, _team_display_name(team))
                name_changed = info_name[0] != info_name[1]
            except Exception as exc:
                warnings.append(RenameIssue(offset=entry.offset, message=f"team name: {exc}"))
        elif normalized_team:
            modified, success = replace_text_in_decoded(bytes(decoded_bytes), old_team, new_team)
            if success:
                name_matched = True
                decoded_bytes = bytearray(modified)
                team.raw_data = bytes(decoded_bytes)
                info_name = (old_name, new_team)
                name_changed = info_name[0] != info_name[1]

        if new_stadium and old_stadium:
            stadium_norm = _normalize_text(old_stadium_value)
            if stadium_norm and normalized_stadium in stadium_norm:
                stadium_matched = True
                try:
                    team.set_stadium_name(new_stadium)
                    decoded_bytes = bytearray(getattr(team, "raw_data", b"") or b"")
                    info_stadium = (old_stadium_value, (getattr(team, "stadium", "") or "").strip())
                    stadium_changed = info_stadium[0] != info_stadium[1]
                except Exception as exc:
                    warnings.append(RenameIssue(offset=entry.offset, message=f"stadium: {exc}"))
            else:
                modified, success = replace_text_in_decoded(bytes(decoded_bytes), old_stadium, new_stadium)
                if success:
                    stadium_matched = True
                    decoded_bytes = bytearray(modified)
                    team.raw_data = bytes(decoded_bytes)
                    info_stadium = (old_stadium, new_stadium)
                    stadium_changed = info_stadium[0] != info_stadium[1]

        if name_matched or stadium_matched:
            matched_count += 1
        if name_changed or stadium_changed:
            team.raw_data = bytes(decoded_bytes)
            changes.append(
                TeamChange(
                    offset=entry.offset,
                    team_id=getattr(team, "team_id", None),
                    name_change=info_name,
                    stadium_change=info_stadium,
                    source=entry.source,
                    old_len=pre_len,
                    new_len=len(getattr(team, "raw_data", b"") or b""),
                )
            )
            modified_entries.append((entry.offset, team))

    backup_path = None
    applied_to_disk = False
    if write_changes and modified_entries:
        try:
            if all(
                isinstance(getattr(team, "container_offset", None), int)
                and isinstance(getattr(team, "container_relative_offset", None), int)
                for _, team in modified_entries
            ):
                backup_path = _write_modified_team_subrecords(path, data, modified_entries)
            else:
                backup_path = _write_modified_entries(path, data, modified_entries)
            applied_to_disk = True
        except Exception as exc:
            warnings.append(
                RenameIssue(
                    offset=None,
                    message=f"Team write failed (likely non-entry offset staging): {exc}",
                )
            )

    return TeamRenameResult(
        file_path=path,
        valid_count=len(valid),
        uncertain_count=len(uncertain),
        extra_scan_count=extra_scan,
        include_uncertain=include_uncertain,
        changes=changes,
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        matched_count=matched_count,
        staged_records=modified_entries if not write_changes else [],
        warnings=warnings,
    )


def rename_coach_records(
    file_path: str,
    old_name: str,
    new_name: str,
    include_uncertain: bool = False,
    target_offset: Optional[int] = None,
    write_changes: bool = True,
) -> CoachRenameResult:
    path = Path(file_path)
    normalized_old = _normalize_text(old_name)
    new_given, new_surname = _split_full_name(new_name)

    valid, uncertain = gather_coach_records(str(path))
    all_entries = valid + (uncertain if include_uncertain else [])

    matches: List[RecordEntry] = []
    for entry in all_entries:
        if target_offset is not None and entry.offset != target_offset:
            continue
        display = _coach_display_name(entry.record)
        if _normalize_text(display) == normalized_old:
            matches.append(entry)

    changes: List[CoachChange] = []
    warnings: List[RenameIssue] = []
    modified_entries: List[Tuple[int, Any]] = []
    for entry in matches:
        coach = entry.record
        old_display = _coach_display_name(coach)
        old_len = len(coach.to_bytes()) if hasattr(coach, "to_bytes") else 0
        try:
            if hasattr(coach, "set_name"):
                coach.set_name(new_given, new_surname)
            else:
                if hasattr(coach, "set_given_name"):
                    coach.set_given_name(new_given)
                else:
                    setattr(coach, "given_name", new_given)
                if hasattr(coach, "set_surname"):
                    coach.set_surname(new_surname)
                else:
                    setattr(coach, "surname", new_surname)
                setattr(coach, "full_name", f"{new_given} {new_surname}".strip())
        except Exception as exc:
            warnings.append(RenameIssue(offset=entry.offset, message=str(exc)))
            continue

        new_display = _coach_display_name(coach)
        new_len = len(coach.to_bytes()) if hasattr(coach, "to_bytes") else old_len
        if new_display == old_display:
            continue

        changes.append(
            CoachChange(
                offset=entry.offset,
                old_name=old_display,
                new_name=new_display,
                source=entry.source,
                old_len=old_len,
                new_len=new_len,
            )
        )
        modified_entries.append((entry.offset, coach))

    backup_path = None
    applied_to_disk = False
    if write_changes and modified_entries:
        data = path.read_bytes()
        backup_path = _write_modified_entries(path, data, modified_entries)
        applied_to_disk = True

    return CoachRenameResult(
        file_path=path,
        valid_count=len(valid),
        uncertain_count=len(uncertain),
        scanned_count=len(all_entries),
        include_uncertain=include_uncertain,
        changes=changes,
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        matched_count=len(matches),
        staged_records=modified_entries if not write_changes else [],
        warnings=warnings,
    )


__all__ = [
    "RenameIssue",
    "PlayerChange",
    "PlayerRenameResult",
    "PlayerSkillPatchResult",
    "PlayerVisibleSkillSnapshot",
    "TeamRosterSameEntryOverlapRunResult",
    "extract_team_rosters_eq_jug_linked",
    "extract_team_rosters_eq_same_entry_overlap",
    "inspect_player_visible_skills_dd6361",
    "TeamChange",
    "TeamRenameResult",
    "CoachChange",
    "CoachRenameResult",
    "parse_player_skill_patch_assignments",
    "patch_player_visible_skills_dd6361",
    "rename_player_records",
    "rename_team_records",
    "rename_coach_records",
    "write_coach_staged_records",
    "write_team_staged_records",
]
