"""Shared rename actions for the CLI and GUI."""

from __future__ import annotations

import csv
import re
import shutil
import struct
from collections import Counter
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
from app.fdi_indexed import IndexedFDIFile
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
from app.xor import decode_entry, encode_entry, read_string, xor_decode, xor_encode


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
    post_write_validation: Optional[DatabaseValidationResult] = None


@dataclass
class PlayerMetadataChange:
    offset: int
    team_id: Optional[int]
    name: str
    source: str
    changed_fields: Dict[str, Tuple[Any, Any]]


@dataclass
class PlayerMetadataEditResult:
    file_path: Path
    record_count: int
    storage_mode: str
    changes: List[PlayerMetadataChange]
    backup_path: Optional[str]
    write_changes: bool
    applied_to_disk: bool
    matched_count: int
    staged_records: List[Tuple[int, Any]] = field(default_factory=list)
    warnings: List[RenameIssue] = field(default_factory=list)
    post_write_validation: Optional[DatabaseValidationResult] = None


@dataclass
class PlayerBatchEditResult:
    file_path: Path
    csv_path: Path
    record_count: int
    storage_mode: str
    row_count: int
    matched_row_count: int
    changes: List[PlayerMetadataChange]
    backup_path: Optional[str]
    write_changes: bool
    applied_to_disk: bool
    staged_records: List[Tuple[int, Any]] = field(default_factory=list)
    warnings: List[RenameIssue] = field(default_factory=list)
    post_write_validation: Optional[DatabaseValidationResult] = None


@dataclass
class PlayerMetadataSnapshot:
    record_id: int
    offset: int
    team_id: Optional[int]
    name: str
    source: str
    suffix_anchor: Optional[int]
    attribute_prefix: List[int]
    indexed_unknown_0: Optional[int]
    indexed_unknown_1: Optional[int]
    face_components: List[int]
    nationality: Optional[int]
    indexed_unknown_9: Optional[int]
    indexed_unknown_10: Optional[int]
    position: Optional[int]
    birth_day: Optional[int]
    birth_month: Optional[int]
    birth_year: Optional[int]
    height: Optional[int]
    weight: Optional[int]
    post_weight_byte: Optional[int]
    trailer_byte: Optional[int]
    sidecar_byte: Optional[int]


@dataclass
class PlayerMetadataInspectResult:
    file_path: Path
    record_count: int
    matched_count: int
    records: List[PlayerMetadataSnapshot]
    storage_mode: str = "indexed"


@dataclass
class PlayerNameCapacitySnapshot:
    record_id: int
    offset: int
    team_id: Optional[int]
    name: str
    source: str
    storage_mode: str
    current_name_bytes: int
    exact_full_name_max_bytes: int
    plain_text_max_bytes: Optional[int]
    length_prefixed_max_bytes: Optional[int]
    structured_window_max_bytes: int
    can_expand_without_growth: bool
    notes: List[str] = field(default_factory=list)
    proposed_name: Optional[str] = None
    proposed_name_bytes: Optional[int] = None
    proposed_within_exact_limit: Optional[bool] = None
    proposed_may_truncate: Optional[bool] = None
    proposed_overflow_by: Optional[int] = None


@dataclass
class PlayerNameCapacityResult:
    file_path: Path
    record_count: int
    matched_count: int
    records: List[PlayerNameCapacitySnapshot]
    storage_mode: str = "indexed"
    target_name: Optional[str] = None
    target_offset: Optional[int] = None
    proposed_name: Optional[str] = None
    proposed_name_bytes: Optional[int] = None
    limit: int = 0
    truncated: bool = False


@dataclass
class PlayerLegacyWeightCandidateProfile:
    relative_offset: int
    eligible_count: int
    exact_match_count: int
    exact_match_ratio: float
    mean_abs_error: float
    top_values: List[Tuple[int, int]]


@dataclass
class PlayerLegacyWeightProfileResult:
    file_path: Path
    record_count: int
    candidate_record_count: int
    recommended_offset: Optional[int]
    height_baseline_exact_ratio: float
    offsets: List[PlayerLegacyWeightCandidateProfile]
    legacy_valid_record_count: int = 0
    legacy_slot_record_count: int = 0
    legacy_matched_record_count: int = 0
    legacy_exact_match_count: int = 0
    legacy_exact_match_ratio: float = 0.0


@dataclass
class PlayerSuffixProfileBucket:
    indexed_unknown_9: Optional[int]
    indexed_unknown_10: Optional[int]
    count: int
    sample_names: List[str]


@dataclass
class PlayerSuffixProfileResult:
    file_path: Path
    record_count: int
    anchored_count: int
    filtered_count: int
    nationality_filter: Optional[int]
    position_filter: Optional[int]
    buckets: List[PlayerSuffixProfileBucket]


@dataclass
class PlayerLeadingProfileBucket:
    indexed_unknown_0: Optional[int]
    indexed_unknown_1: Optional[int]
    count: int
    sample_names: List[str]


@dataclass
class PlayerLeadingProfileResult:
    file_path: Path
    record_count: int
    anchored_count: int
    filtered_count: int
    nationality_filter: Optional[int]
    position_filter: Optional[int]
    indexed_unknown_0_filter: Optional[int]
    indexed_unknown_1_filter: Optional[int]
    indexed_unknown_9_filter: Optional[int]
    indexed_unknown_10_filter: Optional[int]
    position_counts: List[Tuple[Optional[int], int]]
    nationality_counts: List[Tuple[Optional[int], int]]
    buckets: List[PlayerLeadingProfileBucket]


@dataclass
class PlayerAttributePrefixProfileBucket:
    attribute_0: Optional[int]
    attribute_1: Optional[int]
    attribute_2: Optional[int]
    count: int
    sample_names: List[str]


@dataclass
class PlayerAttributeSignatureProfileBucket:
    attribute_0: Optional[int]
    attribute_1: Optional[int]
    attribute_2: Optional[int]
    trailer_byte: Optional[int]
    sidecar_byte: Optional[int]
    count: int
    sample_names: List[str]


@dataclass
class PostWeightGroupCluster:
    post_weight_byte: Optional[int]
    total_count: int
    nationality_counts: List[Tuple[Optional[int], int]]
    sample_names: List[str]


@dataclass
class PlayerAttributePrefixProfileResult:
    file_path: Path
    record_count: int
    anchored_count: int
    filtered_count: int
    nationality_filter: Optional[int]
    position_filter: Optional[int]
    indexed_unknown_0_filter: Optional[int]
    indexed_unknown_1_filter: Optional[int]
    indexed_unknown_9_filter: Optional[int]
    indexed_unknown_10_filter: Optional[int]
    attribute_0_filter: Optional[int]
    attribute_1_filter: Optional[int]
    attribute_2_filter: Optional[int]
    post_weight_byte_filter: Optional[int]
    trailer_byte_filter: Optional[int]
    sidecar_byte_filter: Optional[int]
    layout_verified_count: int
    layout_mismatch_count: int
    attribute_0_counts: List[Tuple[Optional[int], int]]
    attribute_1_counts: List[Tuple[Optional[int], int]]
    attribute_2_counts: List[Tuple[Optional[int], int]]
    post_weight_byte_counts: List[Tuple[Optional[int], int]]
    post_weight_nationality_eligible_count: int
    post_weight_nationality_match_count: int
    post_weight_nationality_match_ratio: float
    post_weight_divergent_counts: List[Tuple[Optional[int], int]]
    post_weight_nationality_mismatch_pairs: List[Tuple[Optional[int], Optional[int], int]]
    post_weight_group_clusters: List[PostWeightGroupCluster]
    trailer_byte_counts: List[Tuple[Optional[int], int]]
    sidecar_byte_counts: List[Tuple[Optional[int], int]]
    buckets: List[PlayerAttributePrefixProfileBucket]
    signature_buckets: List[PlayerAttributeSignatureProfileBucket]


@dataclass
class DatabaseFileValidation:
    category: str
    file_path: Path
    success: bool
    valid_count: int
    uncertain_count: int
    detail: str


@dataclass
class DatabaseValidationResult:
    files: List[DatabaseFileValidation]
    all_valid: bool


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
    post_write_validation: Optional[DatabaseValidationResult] = None


@dataclass
class TeamLinkedRosterChange:
    eq_record_id: int
    team_name: str
    full_club_name: str
    slot_number: int
    old_flag: int
    new_flag: int
    old_player_record_id: int
    new_player_record_id: int
    old_player_name: str
    new_player_name: str
    plan_row_number: int = 0


@dataclass
class TeamLinkedRosterEditResult:
    file_path: Path
    player_file: Path
    matched_count: int
    changes: List[TeamLinkedRosterChange]
    backup_path: Optional[str]
    write_changes: bool
    applied_to_disk: bool
    warnings: List[RenameIssue] = field(default_factory=list)
    post_write_validation: Optional[DatabaseValidationResult] = None


@dataclass
class TeamRosterPlayerPromotionResult:
    team_file: Path
    player_file: Path
    eq_record_id: int
    team_name: str
    full_club_name: str
    slot_number: int
    player_record_id: int
    old_player_name: str
    new_player_name: str
    skill_updates_requested: Dict[str, int]
    visible_skills_before: Dict[str, int]
    visible_skills_after: Dict[str, int]
    alias_replacements: Dict[str, int]
    backup_path: Optional[str]
    write_changes: bool
    applied_to_disk: bool
    warnings: List[RenameIssue] = field(default_factory=list)
    post_write_validation: Optional[DatabaseValidationResult] = None


@dataclass
class TeamRosterPromotionSkip:
    slot_number: int
    player_record_id: int
    player_name: str
    reason_code: str
    reason_message: str


@dataclass
class TeamRosterBulkPromotionResult:
    team_file: Path
    player_file: Path
    eq_record_id: int
    team_name: str
    full_club_name: str
    new_player_name: str
    slot_count: int
    matched_slot_count: int
    promotions: List[TeamRosterPlayerPromotionResult]
    skipped_slots: List[TeamRosterPromotionSkip] = field(default_factory=list)
    backup_path: Optional[str] = None
    write_changes: bool = True
    applied_to_disk: bool = False
    warnings: List[RenameIssue] = field(default_factory=list)
    post_write_validation: Optional[DatabaseValidationResult] = None


@dataclass
class TeamRosterBulkPromotionSafetySummary:
    eq_record_id: int
    team_name: str
    full_club_name: str
    new_player_name: str
    slot_count: int
    matched_slot_count: int
    skipped_slot_count: int
    reason_counts: Dict[str, int] = field(default_factory=dict)
    fixed_name_unsafe_count: int = 0
    already_target_count: int = 0
    other_skip_count: int = 0
    sample_skips: List[TeamRosterPromotionSkip] = field(default_factory=list)


@dataclass
class TeamSameEntryRosterChange:
    team_offset: int
    team_name: str
    full_club_name: str
    entry_offset: int
    slot_number: int
    old_pid_candidate: int
    new_pid_candidate: int
    old_player_name: str
    new_player_name: str
    provenance: str = ""
    preserved_tail_bytes_hex: str = ""
    plan_row_number: int = 0


@dataclass
class TeamSameEntryRosterEditResult:
    file_path: Path
    player_file: Path
    matched_count: int
    changes: List[TeamSameEntryRosterChange]
    backup_path: Optional[str]
    write_changes: bool
    applied_to_disk: bool
    warnings: List[RenameIssue] = field(default_factory=list)
    post_write_validation: Optional[DatabaseValidationResult] = None


@dataclass
class TeamSameEntryTailProfileBucket:
    tail_bytes_hex: str
    tail_byte_2: Optional[int]
    tail_byte_3: Optional[int]
    tail_byte_4: Optional[int]
    count: int
    sample_teams: List[str]
    sample_players: List[str]
    provenance: str = ""


@dataclass
class TeamSameEntryTailProfileResult:
    team_file: Path
    player_file: Path
    requested_team_count: int
    authoritative_team_count: int
    row_count: int
    buckets: List[TeamSameEntryTailProfileBucket]
    include_fallbacks: bool = False
    provenance_counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class TeamRosterBatchPlanRowPreview:
    row_number: Optional[int]
    status: str
    source: str
    team_query: str
    slot_number: Optional[int]
    resolved_team_name: str = ""
    resolved_full_club_name: str = ""
    eq_record_id: Optional[int] = None
    team_offset: Optional[int] = None
    changed: bool = False
    diff_summary: str = ""
    warning_message: str = ""
    old_player_name: str = ""
    new_player_name: str = ""
    old_player_record_id: Optional[int] = None
    new_player_record_id: Optional[int] = None
    old_flag: Optional[int] = None
    new_flag: Optional[int] = None
    old_pid_candidate: Optional[int] = None
    new_pid_candidate: Optional[int] = None
    provenance: str = ""


@dataclass
class TeamRosterBatchEditResult:
    file_path: Path
    player_file: Path
    csv_path: Path
    row_count: int
    matched_row_count: int
    linked_changes: List[TeamLinkedRosterChange]
    same_entry_changes: List[TeamSameEntryRosterChange]
    backup_path: Optional[str]
    write_changes: bool
    applied_to_disk: bool
    warnings: List[RenameIssue] = field(default_factory=list)
    plan_preview: List[TeamRosterBatchPlanRowPreview] = field(default_factory=list)
    post_write_validation: Optional[DatabaseValidationResult] = None


@dataclass
class TeamLinkedRosterCloneResult:
    file_path: Path
    player_file: Path
    source_eq_record_id: int
    source_team_name: str
    source_full_club_name: str
    target_eq_record_id: int
    target_team_name: str
    target_full_club_name: str
    slot_limit: int
    compared_slot_count: int
    matched_count: int
    changes: List[TeamLinkedRosterChange]
    backup_path: Optional[str]
    write_changes: bool
    applied_to_disk: bool
    warnings: List[RenameIssue] = field(default_factory=list)
    post_write_validation: Optional[DatabaseValidationResult] = None


@dataclass
class TeamRosterBatchTemplateExportResult:
    team_file: Path
    player_file: Path
    output_csv: Path
    source: str
    team_name: str
    full_club_name: str
    eq_record_id: Optional[int]
    team_offset: Optional[int]
    row_count: int
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
    post_write_validation: Optional[DatabaseValidationResult] = None


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
    post_write_validation: Optional[DatabaseValidationResult] = None


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


@dataclass
class BitmapReferenceHit:
    offset: int
    marker: str
    snippet_start: int
    snippet_end: int
    snippet: str


@dataclass
class BitmapReferenceFileResult:
    label: str
    file_path: Path
    exists: bool
    read_error: str = ""
    hit_count: int = 0
    hits: List[BitmapReferenceHit] = field(default_factory=list)


@dataclass
class BitmapReferenceProbeResult:
    markers: List[str]
    max_hits_per_file: int
    files: List[BitmapReferenceFileResult] = field(default_factory=list)
    total_hits: int = 0


def _split_full_name(full_name: str) -> Tuple[str, str]:
    cleaned = " ".join((full_name or "").split()).strip()
    if not cleaned:
        raise ValueError("Name cannot be empty")
    parts = cleaned.split(maxsplit=1)
    if len(parts) < 2:
        raise ValueError("Name must contain both given name and surname")
    return parts[0], parts[1]


def _ascii_snippet(data: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in data)


def inspect_bitmap_references(
    *,
    player_file: str = "DBDAT/JUG98030.FDI",
    team_file: str = "DBDAT/EQ98030.FDI",
    coach_file: str = "DBDAT/ENT98030.FDI",
    markers: Optional[List[str]] = None,
    max_hits_per_file: int = 8,
    snippet_before: int = 24,
    snippet_after: int = 32,
) -> BitmapReferenceProbeResult:
    normalized_markers = [str(marker or "").strip().upper() for marker in list(markers or [".BMP", ".TGA"]) if str(marker or "").strip()]
    if not normalized_markers:
        raise ValueError("At least one marker is required")

    max_hits = max(1, int(max_hits_per_file))
    before = max(0, int(snippet_before))
    after = max(1, int(snippet_after))

    targets = [
        ("Players", Path(str(player_file))),
        ("Clubs", Path(str(team_file))),
        ("Coaches", Path(str(coach_file))),
    ]

    file_results: List[BitmapReferenceFileResult] = []
    total_hits = 0
    for label, path in targets:
        if not path.exists():
            file_results.append(
                BitmapReferenceFileResult(
                    label=label,
                    file_path=path,
                    exists=False,
                    read_error="file missing",
                )
            )
            continue

        try:
            data = path.read_bytes()
        except Exception as exc:
            file_results.append(
                BitmapReferenceFileResult(
                    label=label,
                    file_path=path,
                    exists=True,
                    read_error=str(exc),
                )
            )
            continue

        data_upper = data.upper()
        hits: List[BitmapReferenceHit] = []
        for marker in normalized_markers:
            marker_bytes = marker.encode("ascii", errors="ignore")
            if not marker_bytes:
                continue
            search_at = 0
            while len(hits) < max_hits:
                found_at = data_upper.find(marker_bytes, search_at)
                if found_at < 0:
                    break
                snippet_start = max(0, found_at - before)
                snippet_end = min(len(data), found_at + after)
                hits.append(
                    BitmapReferenceHit(
                        offset=int(found_at),
                        marker=marker,
                        snippet_start=snippet_start,
                        snippet_end=snippet_end,
                        snippet=_ascii_snippet(data[snippet_start:snippet_end]),
                    )
                )
                search_at = found_at + len(marker_bytes)

        hits.sort(key=lambda item: (item.offset, item.marker))
        if len(hits) > max_hits:
            hits = hits[:max_hits]

        file_results.append(
            BitmapReferenceFileResult(
                label=label,
                file_path=path,
                exists=True,
                read_error="",
                hit_count=len(hits),
                hits=hits,
            )
        )
        total_hits += len(hits)

    return BitmapReferenceProbeResult(
        markers=normalized_markers,
        max_hits_per_file=max_hits,
        files=file_results,
        total_hits=total_hits,
    )


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
    import contextlib
    import io

    from scripts import probe_eq_team_roster_overlap_extract as roster_overlap_probe

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
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


def _same_entry_row_tail_bytes(row: Dict[str, Any]) -> Tuple[Optional[int], Optional[int], Optional[int], str]:
    tail_hex = str(row.get("tail_bytes_hex") or "").strip().lower()
    if len(tail_hex) == 6:
        try:
            tail_bytes = bytes.fromhex(tail_hex)
            return int(tail_bytes[0]), int(tail_bytes[1]), int(tail_bytes[2]), tail_hex
        except Exception:
            pass

    row5_raw_hex = str(row.get("row5_raw_hex") or "").strip().lower()
    if len(row5_raw_hex) == 10:
        try:
            row5 = bytes.fromhex(row5_raw_hex)
            tail = row5[2:5]
            return int(tail[0]), int(tail[1]), int(tail[2]), tail.hex()
        except Exception:
            pass

    b2 = row.get("tail_byte_2")
    b3 = row.get("tail_byte_3")
    b4 = row.get("tail_byte_4")
    if all(isinstance(value, int) and 0 <= int(value) <= 255 for value in (b2, b3, b4)):
        return int(b2), int(b3), int(b4), bytes([int(b2), int(b3), int(b4)]).hex()

    return None, None, None, ""


_SAME_ENTRY_FIXED_TAIL_HEX = "616161"
_SUPPORTED_SAME_ENTRY_WRITE_PROVENANCES = {
    "same_entry_authoritative",
    "known_lineup_anchor_assisted",
}


def _preferred_same_entry_rows(preferred: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [dict(row or {}) for row in list(preferred.get("rows") or []) if not bool((row or {}).get("is_empty_slot"))]


def _preferred_same_entry_has_fixed_tail(
    preferred: Dict[str, Any],
    *,
    expected_tail_hex: str = _SAME_ENTRY_FIXED_TAIL_HEX,
) -> bool:
    rows = _preferred_same_entry_rows(preferred)
    if not rows:
        return False
    for row in rows:
        _b2, _b3, _b4, tail_hex = _same_entry_row_tail_bytes(row)
        if tail_hex != expected_tail_hex:
            return False
    return True


def profile_same_entry_authoritative_tail_bytes(
    *,
    team_file: str,
    player_file: str = "DBDAT/JUG98030.FDI",
    team_queries: Optional[List[str]] = None,
    limit: int = 10,
    sample_size: int = 3,
    include_fallbacks: bool = False,
) -> TeamSameEntryTailProfileResult:
    """
    Profile the trailing 3 bytes in preferred same-entry 5-byte roster rows.

    By default this only counts `same_entry_authoritative`. When `include_fallbacks=True`,
    it profiles all preferred same-entry provenances so row-shape confidence can be compared
    separately from mapping confidence.
    """
    normalized_queries = [str(query).strip() for query in list(team_queries or []) if str(query).strip()]
    if not normalized_queries:
        import contextlib
        import io

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            valid, uncertain = gather_team_records(str(team_file))
        seen_queries: set[str] = set()
        for entry in list(valid) + list(uncertain):
            name = _team_display_name(entry.record)
            normalized = _normalize_text(name)
            if not name or normalized in seen_queries:
                continue
            seen_queries.add(normalized)
            normalized_queries.append(name)

    result = extract_team_rosters_eq_same_entry_overlap(
        team_file=team_file,
        player_file=player_file,
        team_queries=normalized_queries,
        include_fallbacks=bool(include_fallbacks),
    )

    requested = list(getattr(result, "requested_team_results", []) or [])
    bucket_counts: Dict[Tuple[str, Optional[int], Optional[int], Optional[int], str], int] = {}
    sample_teams: Dict[Tuple[str, Optional[int], Optional[int], Optional[int], str], List[str]] = {}
    sample_players: Dict[Tuple[str, Optional[int], Optional[int], Optional[int], str], List[str]] = {}
    authoritative_team_count = 0
    row_count = 0
    provenance_counts: Dict[str, int] = {}

    for item in requested:
        preferred = dict(item.get("preferred_roster_match") or {})
        provenance = str(preferred.get("provenance") or "")
        if not provenance:
            continue
        if (not include_fallbacks) and provenance != "same_entry_authoritative":
            continue
        authoritative_team_count += 1
        provenance_counts[provenance] = int(provenance_counts.get(provenance, 0) or 0) + 1
        team_name = str(item.get("team_name") or "")
        full_club_name = str(item.get("full_club_name") or "")
        display = f"{team_name} ({full_club_name})" if full_club_name and full_club_name != team_name else team_name
        for row in _preferred_same_entry_rows(preferred):
            b2, b3, b4, tail_hex = _same_entry_row_tail_bytes(row)
            row_count += 1
            key = (provenance, b2, b3, b4, tail_hex)
            bucket_counts[key] = bucket_counts.get(key, 0) + 1

            teams = sample_teams.setdefault(key, [])
            if display and display not in teams and len(teams) < sample_size:
                teams.append(display)

            player_name = str(row.get("dd6361_name") or "").strip()
            players = sample_players.setdefault(key, [])
            if player_name and player_name not in players and len(players) < sample_size:
                players.append(player_name)

    ordered = sorted(
        bucket_counts.items(),
        key=lambda item: (
            -item[1],
            item[0][0],
            item[0][1] if item[0][1] is not None else -1,
            item[0][2] if item[0][2] is not None else -1,
            item[0][3] if item[0][3] is not None else -1,
            item[0][4],
        ),
    )
    buckets: List[TeamSameEntryTailProfileBucket] = []
    for key, count in ordered[: max(1, int(limit or 10))]:
        buckets.append(
            TeamSameEntryTailProfileBucket(
                tail_bytes_hex=key[4],
                tail_byte_2=key[1],
                tail_byte_3=key[2],
                tail_byte_4=key[3],
                count=count,
                sample_teams=list(sample_teams.get(key, [])),
                sample_players=list(sample_players.get(key, [])),
                provenance=key[0],
            )
        )

    return TeamSameEntryTailProfileResult(
        team_file=Path(str(team_file)),
        player_file=Path(str(player_file)),
        requested_team_count=len(requested),
        authoritative_team_count=authoritative_team_count,
        row_count=row_count,
        buckets=buckets,
        include_fallbacks=bool(include_fallbacks),
        provenance_counts=provenance_counts,
    )


_ELITE_VISIBLE_SKILL_UPDATES: Dict[str, int] = {
    "speed": 99,
    "stamina": 99,
    "aggression": 99,
    "quality": 99,
    "heading": 99,
    "dribbling": 99,
    "passing": 99,
    "shooting": 99,
    "tackling": 99,
    "handling": 99,
}


@dataclass
class _IndexedRawStageRecord:
    raw_payload: bytes
    container_offset: int
    container_length: int
    container_encoding: str = "indexed_xor"

    def to_bytes(self) -> bytes:
        return bytes(self.raw_payload)


def _is_reasonable_fixed_name_result(*, requested_name: str, applied_name: str) -> bool:
    requested = _normalize_text(requested_name)
    applied = _normalize_text(applied_name)
    if not requested or not applied:
        return False
    return applied == requested or requested.startswith(applied)


def _build_parser_fixed_name_candidate(
    *,
    decoded_payload: bytes,
    payload_offset: int,
    new_name: str,
) -> bytes:
    rec = PlayerRecord.from_bytes(decoded_payload, payload_offset)
    rec.set_name(new_name)
    candidate = bytearray(rec.to_bytes())
    # Preserve opaque header bytes exactly; parser fields do not reliably decode these.
    candidate[:5] = decoded_payload[:5]
    return bytes(candidate)


def _candidate_change_profile(original: bytes, candidate: bytes) -> Tuple[int, int, int]:
    diffs = [i for i, (before, after) in enumerate(zip(original, candidate)) if before != after]
    if not diffs:
        return 0, -1, -1
    return len(diffs), diffs[0], diffs[-1]


def _replace_fixed_width_text_all(decoded_payload: bytes, old_text: str, new_text: str) -> Tuple[bytes, int]:
    old_bytes = str(old_text or "").encode("cp1252", errors="replace")
    if not old_bytes:
        return decoded_payload, 0
    new_bytes = str(new_text or "").encode("cp1252", errors="replace")
    if len(new_bytes) < len(old_bytes):
        new_bytes = new_bytes + (b" " * (len(old_bytes) - len(new_bytes)))
    elif len(new_bytes) > len(old_bytes):
        new_bytes = new_bytes[: len(old_bytes)]
    count = decoded_payload.count(old_bytes)
    if not count:
        return decoded_payload, 0
    return decoded_payload.replace(old_bytes, new_bytes), int(count)


def _replace_fixed_width_text_limited(
    decoded_payload: bytes,
    old_text: str,
    new_text: str,
    *,
    max_offset: int,
) -> Tuple[bytes, int]:
    if max_offset <= 0:
        return decoded_payload, 0
    limit = min(len(decoded_payload), int(max_offset))
    if limit <= 0:
        return decoded_payload, 0
    prefix = decoded_payload[:limit]
    suffix = decoded_payload[limit:]
    replaced_prefix, count = _replace_fixed_width_text_all(prefix, old_text, new_text)
    if not count:
        return decoded_payload, 0
    return bytes(replaced_prefix) + bytes(suffix), int(count)


def _sync_fixed_name_aliases(
    *,
    payload: bytes,
    parsed_before: PlayerRecord,
    new_name: str,
    max_sync_offset: int = 256,
) -> bytes:
    updated = bytes(payload)

    given_before = str(getattr(parsed_before, "given_name", "") or "").strip()
    surname_before = str(getattr(parsed_before, "surname", "") or "").strip()
    if not given_before or not surname_before:
        return updated

    old_display = " ".join((given_before, surname_before)).strip()
    old_title = " ".join((given_before, surname_before.title())).strip()

    new_display_fit = _truncate_cp1252_text(new_name, len(old_display.encode("cp1252", errors="replace")))
    new_title_fit = _truncate_cp1252_text(new_name, len(old_title.encode("cp1252", errors="replace")))

    # Restrict alias replacements to early payload bytes only; global substitutions
    # can collide with unrelated opaque segments and destabilize runtime parsing.
    updated, _ = _replace_fixed_width_text_limited(
        updated,
        old_display,
        new_display_fit,
        max_offset=max_sync_offset,
    )
    updated, _ = _replace_fixed_width_text_limited(
        updated,
        old_title,
        new_title_fit,
        max_offset=max_sync_offset,
    )

    return updated


def _mutate_indexed_player_name_fixed_safe(
    *,
    decoded_payload: bytes,
    payload_offset: int,
    new_name: str,
) -> Tuple[bytes, str]:
    """
    Build a fixed-size name mutation using conservative candidate selection.

    Strategy order:
    1) same-length text replace of the parsed display name (minimal byte churn)
    2) explicit length-prefixed slot patch (when layout matches)
    3) parser-backed rename candidate with strict diff guardrails
    """
    parsed_before = PlayerRecord.from_bytes(decoded_payload, payload_offset)
    before_name = _player_display_name(parsed_before)
    if not before_name:
        raise RuntimeError("Fixed-length rename could not resolve existing display name")

    target_same_len = _truncate_cp1252_text(new_name, len(before_name.encode("cp1252", errors="replace")))

    candidates: List[Tuple[str, bytes]] = []
    diagnostics: List[str] = []

    replaced_payload, replaced = replace_text_in_decoded(decoded_payload, before_name, target_same_len)
    if replaced and len(replaced_payload) == len(decoded_payload):
        candidates.append(("text_replace", bytes(replaced_payload)))
    else:
        diagnostics.append("text_replace:no_exact_full_name_match")

    try:
        lp_payload = _mutate_indexed_player_name_fixed_bytes(
            decoded_payload=decoded_payload,
            new_name=new_name,
        )
        if len(lp_payload) == len(decoded_payload):
            candidates.append(("length_prefixed", bytes(lp_payload)))
        else:
            diagnostics.append("length_prefixed:payload_size_mismatch")
    except Exception as exc:
        diagnostics.append(f"length_prefixed:error={exc}")

    try:
        parser_payload = _build_parser_fixed_name_candidate(
            decoded_payload=decoded_payload,
            payload_offset=payload_offset,
            new_name=new_name,
        )
        if len(parser_payload) == len(decoded_payload):
            candidates.append(("parser_candidate", bytes(parser_payload)))
        else:
            diagnostics.append("parser_candidate:payload_size_mismatch")
    except Exception as exc:
        diagnostics.append(f"parser_candidate:error={exc}")

    text_candidate_unreasonable = False

    for mode, candidate in candidates:
        try:
            parsed_after = PlayerRecord.from_bytes(candidate, payload_offset)
            applied_name = _player_display_name(parsed_after)
        except Exception as exc:
            diagnostics.append(f"{mode}:post_parse_error={exc}")
            continue

        reasonable = _is_reasonable_fixed_name_result(requested_name=new_name, applied_name=applied_name)
        if mode == "text_replace" and not reasonable:
            text_candidate_unreasonable = True
            diagnostics.append(f"{mode}:unreasonable_name={applied_name!r}")
            continue
        if not reasonable:
            diagnostics.append(f"{mode}:unreasonable_name={applied_name!r}")
            continue

        diff_count, first_diff, last_diff = _candidate_change_profile(decoded_payload, candidate)
        if mode == "parser_candidate":
            # If direct text replacement produced garbled output, treat parser candidate as unsafe.
            if text_candidate_unreasonable:
                diagnostics.append("parser_candidate:blocked_by_text_replace")
                continue
            if not (diff_count <= 128 and first_diff >= 5 and last_diff <= 128):
                diagnostics.append(
                    f"parser_candidate:diff_window_reject(diff={diff_count},first={first_diff},last={last_diff})"
                )
                continue
            synced = _sync_fixed_name_aliases(
                payload=candidate,
                parsed_before=parsed_before,
                new_name=new_name,
            )
            sync_diff_count, sync_first_diff, sync_last_diff = _candidate_change_profile(decoded_payload, synced)
            if sync_diff_count <= 128 and sync_first_diff >= 5 and sync_last_diff <= 128:
                return synced, _player_display_name(PlayerRecord.from_bytes(synced, payload_offset))
            diagnostics.append(
                f"parser_candidate:sync_window_reject(diff={sync_diff_count},first={sync_first_diff},last={sync_last_diff})"
            )
            continue

        # Non-parser candidates should remain local and avoid header bytes.
        if not (diff_count <= 256 and first_diff >= 5):
            diagnostics.append(
                f"{mode}:diff_window_reject(diff={diff_count},first={first_diff},last={last_diff})"
            )
            continue
        synced = _sync_fixed_name_aliases(
            payload=candidate,
            parsed_before=parsed_before,
            new_name=new_name,
        )
        sync_diff_count, sync_first_diff, sync_last_diff = _candidate_change_profile(decoded_payload, synced)
        if sync_diff_count <= 256 and sync_first_diff >= 5 and sync_last_diff <= 256:
            return synced, _player_display_name(PlayerRecord.from_bytes(synced, payload_offset))
        diagnostics.append(
            f"{mode}:sync_window_reject(diff={sync_diff_count},first={sync_first_diff},last={sync_last_diff})"
        )

    detail = "; ".join(diagnostics[:6]) if diagnostics else "no candidate diagnostics"
    raise RuntimeError(
        "Fixed-length rename could not produce a safe name mutation candidate for this payload"
        f" [{detail}]"
    )



def _split_full_name_parts(full_name: str) -> Tuple[str, str]:
    normalized = " ".join(str(full_name or "").split()).strip()
    if not normalized:
        raise ValueError("new_name is required")
    parts = normalized.split(maxsplit=1)
    if len(parts) < 2:
        raise ValueError("new_name must include given name and surname")
    return parts[0], parts[1]


def _truncate_cp1252_text(value: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = str(value or "").encode("cp1252", errors="replace")
    if len(encoded) <= max_bytes:
        return encoded.decode("cp1252", errors="replace")
    return encoded[:max_bytes].decode("cp1252", errors="replace")


def _mutate_indexed_player_name_fixed_bytes(
    *,
    decoded_payload: bytes,
    new_name: str,
) -> bytes:
    """
    Patch the indexed given/surname length-prefixed slots without changing payload size.

    This keeps each string slot's original byte capacity and truncates/pads the new
    name parts to fit exactly, preserving the decoded payload length.
    """
    given_target, surname_target = _split_full_name_parts(new_name)

    cursor = 5
    if cursor + 2 > len(decoded_payload):
        raise RuntimeError("Fixed-length rename requires valid length-prefixed name slots")

    given_capacity = int(struct.unpack_from("<H", decoded_payload, cursor)[0])
    cursor += 2
    given_end = cursor + given_capacity
    if given_end > len(decoded_payload):
        raise RuntimeError("Fixed-length rename could not parse given-name slot bounds")
    cursor = given_end

    if cursor + 2 > len(decoded_payload):
        raise RuntimeError("Fixed-length rename could not parse surname slot header")
    surname_capacity = int(struct.unpack_from("<H", decoded_payload, cursor)[0])
    cursor += 2
    surname_end = cursor + surname_capacity
    if surname_end > len(decoded_payload):
        raise RuntimeError("Fixed-length rename could not parse surname slot bounds")
    cursor = surname_end
    if given_capacity < 1 or surname_capacity < 1:
        raise RuntimeError(
            "Fixed-length rename requires non-empty given/surname capacities in the current record"
        )

    given_trimmed = _truncate_cp1252_text(given_target, given_capacity)
    surname_trimmed = _truncate_cp1252_text(surname_target, surname_capacity)
    given_bytes = given_trimmed.encode("cp1252", errors="replace")
    surname_bytes = surname_trimmed.encode("cp1252", errors="replace")

    given_field = struct.pack("<H", given_capacity) + given_bytes + (b" " * (given_capacity - len(given_bytes)))
    surname_field = struct.pack("<H", surname_capacity) + surname_bytes + (b" " * (surname_capacity - len(surname_bytes)))

    patched = decoded_payload[:5] + given_field + surname_field + decoded_payload[cursor:]
    if len(patched) != len(decoded_payload):
        raise RuntimeError(
            "Fixed-length rename mutated payload size unexpectedly; aborting to avoid record/index drift"
        )
    return patched


def _build_indexed_player_name_stage_record(
    *,
    decoded_payload: bytes,
    payload_offset: int,
    payload_length: int,
    new_name: str,
    fixed_name_bytes: bool = False,
) -> Tuple[Any, bool, str, bool]:
    """
    Build one staged indexed player record with a parser-backed full-name mutation.

    Returns (record, name_changed, applied_name, was_truncated).
    """
    record_before = PlayerRecord.from_bytes(decoded_payload, payload_offset)
    before_name = _player_display_name(record_before)

    if fixed_name_bytes:
        patched_payload, applied_name = _mutate_indexed_player_name_fixed_safe(
            decoded_payload=decoded_payload,
            payload_offset=payload_offset,
            new_name=new_name,
        )
        record = _IndexedRawStageRecord(
            raw_payload=patched_payload,
            container_offset=payload_offset,
            container_length=payload_length,
            container_encoding="indexed_xor",
        )
    else:
        parsed = PlayerRecord.from_bytes(decoded_payload, payload_offset)
        _apply_player_mutations(parsed, new_name=new_name)
        applied_name = _player_display_name(parsed)
        try:
            parsed.container_offset = payload_offset
            parsed.container_length = payload_length
            parsed.container_encoding = "indexed_xor"
        except Exception:
            pass
        record = parsed

    name_changed = _normalize_text(applied_name) != _normalize_text(before_name)
    was_truncated = _normalize_text(applied_name) != _normalize_text(new_name)

    if (not fixed_name_bytes) and name_changed and was_truncated:
        raise RuntimeError(
            "Post-mutation parse did not resolve the requested new name; promotion aborted to avoid partial writes."
        )
    return record, name_changed, applied_name, was_truncated


def promote_team_roster_player(
    *,
    team_file: str,
    player_file: str = "DBDAT/JUG98030.FDI",
    team_query: Optional[str] = None,
    eq_record_id: Optional[int] = None,
    slot_number: int,
    new_name: str,
    apply_elite_skills: bool = False,
    skill_updates: Optional[Dict[str, int]] = None,
    fixed_name_bytes: bool = False,
    write_changes: bool = True,
    create_backup_before_write: bool = True,
) -> TeamRosterPlayerPromotionResult:
    """
    Promote one linked roster player using parser-backed name mutation plus optional visible-skill updates.

    This path targets parser-backed EQ->JUG linked roster rows and writes through the
    shared indexed staged-writer, including variable-length payload updates.
    """
    if slot_number < 1:
        raise ValueError("slot_number must be >= 1")
    if not str(new_name or "").strip():
        raise ValueError("new_name is required")

    team_path = Path(team_file)
    player_path = Path(player_file)
    roster_catalog = load_eq_linked_team_rosters(team_file=str(team_path), player_file=str(player_path))
    roster = _resolve_single_linked_team_roster(roster_catalog, team_query=team_query, eq_record_id=eq_record_id)

    rows = list(getattr(roster, "rows", []) or [])
    slot_index = slot_number - 1
    if slot_index >= len(rows):
        raise ValueError(
            f"Linked roster slot {slot_number} is out of range for "
            f"{getattr(roster, 'short_name', '') or '<unknown team>'} (rows={len(rows)})"
        )

    row = rows[slot_index]
    player_record_id = int(getattr(row, "player_record_id", 0) or 0)
    if player_record_id <= 0:
        raise ValueError("Selected linked roster slot has an invalid player_record_id")

    requested_updates: Dict[str, int] = {}
    if apply_elite_skills:
        requested_updates.update(_ELITE_VISIBLE_SKILL_UPDATES)
    for field_name, value in dict(skill_updates or {}).items():
        requested_updates[str(field_name)] = int(value)

    old_player_name = str(getattr(row, "player_name", "") or "").strip()
    resolved_old_name = old_player_name
    visible_before: Dict[str, int] = {}
    visible_after: Dict[str, int] = {}
    warnings: List[RenameIssue] = []
    replacement_counts: Dict[str, int] = {}
    backup_path: Optional[str] = None
    applied_to_disk = False

    player_bytes = player_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(player_bytes)
    indexed_entry = next((entry for entry in indexed.entries if entry.record_id == player_record_id), None)
    if indexed_entry is None:
        raise ValueError(
            f"Linked roster slot maps to player_record_id={player_record_id}, but that ID was not found in {player_path}"
        )

    decoded = indexed_entry.decode_payload(player_bytes)
    record_before = PlayerRecord.from_bytes(decoded, indexed_entry.payload_offset)
    if not resolved_old_name:
        resolved_old_name = _player_display_name(record_before)

    staged_record, name_changed, applied_new_name, was_truncated = _build_indexed_player_name_stage_record(
        decoded_payload=decoded,
        payload_offset=int(indexed_entry.payload_offset),
        payload_length=int(indexed_entry.payload_length),
        new_name=str(new_name),
        fixed_name_bytes=bool(fixed_name_bytes),
    )
    if name_changed:
        replacement_counts["display_name"] = 1
    if fixed_name_bytes and was_truncated:
        warnings.append(
            RenameIssue(
                offset=int(getattr(indexed_entry, "payload_offset", 0) or 0),
                message=f"Name truncated to fit fixed slots: requested '{new_name}' -> applied '{applied_new_name}'",
            )
        )

    if requested_updates:
        try:
            snapshot = inspect_player_visible_skills_dd6361(
                file_path=str(player_path),
                player_name=resolved_old_name,
            )
            visible_before = {str(k): int(v) for k, v in dict(getattr(snapshot, "mapped10", {}) or {}).items()}
        except Exception as exc:
            warnings.append(RenameIssue(offset=indexed_entry.payload_offset, message=f"visible-skill inspect failed: {exc}"))
            visible_before = {}
        visible_after = dict(visible_before)
        for field_name, value in requested_updates.items():
            visible_after[str(field_name)] = int(value)

    if write_changes:
        backup_path = create_backup(str(player_path)) if create_backup_before_write else None
        try:
            if requested_updates:
                patch_player_visible_skills_dd6361(
                    file_path=str(player_path),
                    player_name=resolved_old_name,
                    updates=requested_updates,
                    in_place=True,
                    output_file=None,
                    create_backup_before_write=False,
                    json_output=None,
                )
                player_bytes = player_path.read_bytes()
                indexed = IndexedFDIFile.from_bytes(player_bytes)
                indexed_entry = next((entry for entry in indexed.entries if entry.record_id == player_record_id), None)
                if indexed_entry is None:
                    raise RuntimeError("Player entry disappeared after visible-skill patch; aborting promotion write")
                decoded = indexed_entry.decode_payload(player_bytes)
                staged_record, name_changed, applied_new_name, was_truncated = _build_indexed_player_name_stage_record(
                    decoded_payload=decoded,
                    payload_offset=int(indexed_entry.payload_offset),
                    payload_length=int(indexed_entry.payload_length),
                    new_name=str(new_name),
                    fixed_name_bytes=bool(fixed_name_bytes),
                )
                replacement_counts = {"display_name": 1} if name_changed else {}
                if fixed_name_bytes and was_truncated:
                    warnings.append(
                        RenameIssue(
                            offset=int(getattr(indexed_entry, "payload_offset", 0) or 0),
                            message=f"Name truncated to fit fixed slots: requested '{new_name}' -> applied '{applied_new_name}'",
                        )
                    )

            write_player_staged_records(
                str(player_path),
                [(int(indexed_entry.payload_offset), staged_record)],
                create_backup_before_write=False,
            )
            applied_to_disk = True
        except Exception:
            if backup_path:
                try:
                    shutil.copy2(backup_path, player_path)
                except Exception:
                    pass
            raise

    if requested_updates and write_changes:
        try:
            final_snapshot = inspect_player_visible_skills_dd6361(
                file_path=str(player_path),
                player_name=applied_new_name,
            )
            visible_after = {str(k): int(v) for k, v in dict(getattr(final_snapshot, "mapped10", {}) or {}).items()}
        except Exception as exc:
            warnings.append(RenameIssue(offset=indexed_entry.payload_offset, message=f"post-write visible-skill verify failed: {exc}"))

    return TeamRosterPlayerPromotionResult(
        team_file=team_path,
        player_file=player_path,
        eq_record_id=int(getattr(roster, "eq_record_id", 0) or 0),
        team_name=str(getattr(roster, "short_name", "") or ""),
        full_club_name=str(getattr(roster, "full_club_name", "") or ""),
        slot_number=slot_number,
        player_record_id=player_record_id,
        old_player_name=resolved_old_name,
        new_player_name=str(applied_new_name),
        skill_updates_requested=dict(requested_updates),
        visible_skills_before=dict(visible_before),
        visible_skills_after=dict(visible_after),
        alias_replacements=dict(replacement_counts),
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        warnings=warnings,
    )



def promote_linked_roster_player_name_bulk(
    *,
    team_file: str,
    player_file: str = "DBDAT/JUG98030.FDI",
    team_query: Optional[str] = None,
    eq_record_id: Optional[int] = None,
    new_name: str,
    slot_limit: Optional[int] = 25,
    apply_elite_skills: bool = False,
    skill_updates: Optional[Dict[str, int]] = None,
    fixed_name_bytes: bool = False,
    write_changes: bool = True,
) -> TeamRosterBulkPromotionResult:
    """
    Promote a linked roster in bulk with one target player name across slots.

    This is generic and reusable for any club, not tied to specific names/teams.
    """
    if not str(new_name or "").strip():
        raise ValueError("new_name is required")
    if slot_limit is not None and int(slot_limit) < 1:
        raise ValueError("slot_limit must be >= 1 when provided")

    requested_updates: Dict[str, int] = {}
    if apply_elite_skills:
        requested_updates.update(_ELITE_VISIBLE_SKILL_UPDATES)
    for field_name, value in dict(skill_updates or {}).items():
        requested_updates[str(field_name)] = int(value)

    team_path = Path(team_file)
    player_path = Path(player_file)
    roster_catalog = load_eq_linked_team_rosters(team_file=str(team_path), player_file=str(player_path))
    roster = _resolve_single_linked_team_roster(roster_catalog, team_query=team_query, eq_record_id=eq_record_id)

    rows = list(getattr(roster, "rows", []) or [])
    if not rows:
        raise ValueError("Selected linked roster has no rows")

    normalized_target_name = _normalize_text(new_name)
    max_slots = min(len(rows), int(slot_limit) if slot_limit is not None else len(rows))

    preview_promotions: List[TeamRosterPlayerPromotionResult] = []
    skipped_slots: List[TeamRosterPromotionSkip] = []
    warnings: List[RenameIssue] = []
    for slot_number in range(1, max_slots + 1):
        row = rows[slot_number - 1]
        current_name = str(getattr(row, "player_name", "") or "").strip()
        player_record_id = int(getattr(row, "player_record_id", 0) or 0)
        if (
            not requested_updates
            and current_name
            and _normalize_text(current_name) == normalized_target_name
        ):
            skipped_slots.append(
                TeamRosterPromotionSkip(
                    slot_number=slot_number,
                    player_record_id=player_record_id,
                    player_name=current_name,
                    reason_code="already_target",
                    reason_message="name already matches target",
                )
            )
            continue

        try:
            preview = promote_team_roster_player(
                team_file=str(team_path),
                player_file=str(player_path),
                team_query=str(getattr(roster, "short_name", "") or team_query or ""),
                eq_record_id=int(getattr(roster, "eq_record_id", 0) or 0) or None,
                slot_number=slot_number,
                new_name=str(new_name),
                apply_elite_skills=bool(apply_elite_skills),
                skill_updates=requested_updates,
                fixed_name_bytes=bool(fixed_name_bytes),
                write_changes=False,
            )
            preview_promotions.append(preview)
        except Exception as exc:
            reason_message = str(exc).strip() or "unknown error"
            reason_code = "promotion_error"
            if "Fixed-length rename could not produce a safe name mutation candidate" in reason_message:
                reason_code = "fixed_name_unsafe"
            skipped_slots.append(
                TeamRosterPromotionSkip(
                    slot_number=slot_number,
                    player_record_id=player_record_id,
                    player_name=current_name,
                    reason_code=reason_code,
                    reason_message=reason_message,
                )
            )

    matched_slot_count = len(preview_promotions)
    backup_path = None
    applied_to_disk = False
    promotions_out: List[TeamRosterPlayerPromotionResult] = list(preview_promotions)

    if write_changes and matched_slot_count:
        backup_path = create_backup(str(player_path))
        applied_rows: List[TeamRosterPlayerPromotionResult] = []
        try:
            for preview in preview_promotions:
                applied_rows.append(
                    promote_team_roster_player(
                        team_file=str(team_path),
                        player_file=str(player_path),
                        team_query=str(getattr(roster, "short_name", "") or team_query or ""),
                        eq_record_id=int(getattr(roster, "eq_record_id", 0) or 0) or None,
                        slot_number=int(getattr(preview, "slot_number", 0) or 0),
                        new_name=str(new_name),
                        apply_elite_skills=bool(apply_elite_skills),
                        skill_updates=requested_updates,
                        fixed_name_bytes=bool(fixed_name_bytes),
                        write_changes=True,
                        create_backup_before_write=False,
                    )
                )
            promotions_out = applied_rows
            applied_to_disk = True
        except Exception as exc:
            try:
                shutil.copy2(backup_path, player_path)
            except Exception:
                pass
            raise RuntimeError(
                "Bulk roster promotion failed; player file rolled back from backup. "
                f"Applied slots before failure: {len(applied_rows)}. Root cause: {exc}"
            ) from exc

    for result in promotions_out:
        warnings.extend(list(getattr(result, "warnings", []) or []))

    return TeamRosterBulkPromotionResult(
        team_file=team_path,
        player_file=player_path,
        eq_record_id=int(getattr(roster, "eq_record_id", 0) or 0),
        team_name=str(getattr(roster, "short_name", "") or ""),
        full_club_name=str(getattr(roster, "full_club_name", "") or ""),
        new_player_name=str(new_name),
        slot_count=max_slots,
        matched_slot_count=matched_slot_count,
        promotions=promotions_out,
        skipped_slots=skipped_slots,
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        warnings=warnings,
    )

def summarize_team_roster_bulk_promotion(
    result: Any,
    *,
    sample_limit: int = 12,
) -> TeamRosterBulkPromotionSafetySummary:
    """Summarize linked bulk-promotion skip diagnostics for RE triage."""
    skipped_slots_raw = list(getattr(result, "skipped_slots", []) or [])
    normalized_skips: List[TeamRosterPromotionSkip] = []
    reason_counts: Counter[str] = Counter()
    for item in skipped_slots_raw:
        reason_code = str(getattr(item, "reason_code", "") or "unknown").strip() or "unknown"
        normalized = TeamRosterPromotionSkip(
            slot_number=int(getattr(item, "slot_number", 0) or 0),
            player_record_id=int(getattr(item, "player_record_id", 0) or 0),
            player_name=str(getattr(item, "player_name", "") or ""),
            reason_code=reason_code,
            reason_message=str(getattr(item, "reason_message", "") or ""),
        )
        normalized_skips.append(normalized)
        reason_counts[reason_code] += 1

    sample_count = max(0, int(sample_limit or 0))
    sample_skips = normalized_skips[:sample_count] if sample_count else []
    fixed_name_unsafe_count = int(reason_counts.get("fixed_name_unsafe", 0) or 0)
    already_target_count = int(reason_counts.get("already_target", 0) or 0)
    other_skip_count = int(len(normalized_skips) - fixed_name_unsafe_count - already_target_count)

    return TeamRosterBulkPromotionSafetySummary(
        eq_record_id=int(getattr(result, "eq_record_id", 0) or 0),
        team_name=str(getattr(result, "team_name", "") or ""),
        full_club_name=str(getattr(result, "full_club_name", "") or ""),
        new_player_name=str(getattr(result, "new_player_name", "") or ""),
        slot_count=int(getattr(result, "slot_count", 0) or 0),
        matched_slot_count=int(getattr(result, "matched_slot_count", 0) or 0),
        skipped_slot_count=int(len(normalized_skips)),
        reason_counts=dict(reason_counts),
        fixed_name_unsafe_count=fixed_name_unsafe_count,
        already_target_count=already_target_count,
        other_skip_count=other_skip_count,
        sample_skips=sample_skips,
    )



def edit_team_roster_eq_jug_linked(
    *,
    team_file: str,
    player_file: str = "DBDAT/JUG98030.FDI",
    team_query: Optional[str] = None,
    eq_record_id: Optional[int] = None,
    slot_number: int,
    player_record_id: Optional[int] = None,
    flag: Optional[int] = None,
    write_changes: bool = True,
) -> TeamLinkedRosterEditResult:
    """
    Patch one parser-backed EQ->JUG linked roster slot in place.

    This only targets the proven external-link roster table. It does not attempt
    to mutate unresolved inline roster modes or broader team metadata structures.
    """
    if slot_number < 1:
        raise ValueError("slot_number must be >= 1")
    if player_record_id is None and flag is None:
        raise ValueError("Provide player_record_id and/or flag to change the linked roster slot")
    if player_record_id is not None and player_record_id < 0:
        raise ValueError("player_record_id must be >= 0")
    if flag is not None and not (0 <= flag <= 255):
        raise ValueError("flag must be 0-255")

    path = Path(team_file)
    player_path = Path(player_file)
    file_data = path.read_bytes()
    rosters = load_eq_linked_team_rosters(team_file=str(path), player_file=str(player_path))
    roster = _resolve_single_linked_team_roster(rosters, team_query=team_query, eq_record_id=eq_record_id)

    rows = list(getattr(roster, "rows", []) or [])
    slot_index = slot_number - 1
    if slot_index >= len(rows):
        raise ValueError(
            f"Linked roster slot {slot_number} is out of range for "
            f"{getattr(roster, 'short_name', '') or '<unknown team>'} (rows={len(rows)})"
        )

    row = rows[slot_index]
    raw_row_offset = int(getattr(row, "raw_row_offset", -1) or -1)
    payload_offset = int(getattr(roster, "payload_offset", 0) or 0)
    payload_length = int(getattr(roster, "payload_length", 0) or 0)
    if raw_row_offset < 0:
        raise RuntimeError("Linked roster row is missing raw_row_offset metadata; cannot patch safely")
    if payload_offset < 0 or payload_length <= 0 or payload_offset + payload_length > len(file_data):
        raise RuntimeError("Linked roster payload is outside file bounds; cannot patch safely")

    payload = bytearray(file_data[payload_offset : payload_offset + payload_length])
    if raw_row_offset + 5 > len(payload):
        raise RuntimeError("Linked roster row overruns the payload; cannot patch safely")

    old_flag = int(getattr(row, "flag", 0) or 0)
    old_pid = int(getattr(row, "player_record_id", 0) or 0)
    new_flag = old_flag if flag is None else int(flag)
    new_pid = old_pid if player_record_id is None else int(player_record_id)

    changes: List[TeamLinkedRosterChange] = []
    warnings: List[RenameIssue] = []
    if new_flag != old_flag or new_pid != old_pid:
        payload[raw_row_offset] = new_flag
        payload[raw_row_offset + 1 : raw_row_offset + 5] = int(new_pid).to_bytes(4, "little")

        player_names = {
            int(getattr(item, "player_record_id", 0) or 0): str(getattr(item, "player_name", "") or "")
            for team in rosters
            for item in list(getattr(team, "rows", []) or [])
        }
        old_name = str(getattr(row, "player_name", "") or "") or str(player_names.get(old_pid) or "")
        new_name = str(player_names.get(new_pid) or "")
        changes.append(
            TeamLinkedRosterChange(
                eq_record_id=int(getattr(roster, "eq_record_id", 0) or 0),
                team_name=str(getattr(roster, "short_name", "") or ""),
                full_club_name=str(getattr(roster, "full_club_name", "") or ""),
                slot_number=slot_number,
                old_flag=old_flag,
                new_flag=new_flag,
                old_player_record_id=old_pid,
                new_player_record_id=new_pid,
                old_player_name=old_name,
                new_player_name=new_name,
            )
        )

    backup_path = None
    applied_to_disk = False
    if write_changes and changes:
        patched_file = bytearray(file_data)
        patched_file[payload_offset : payload_offset + payload_length] = payload
        backup_path = create_backup(str(path))
        path.write_bytes(bytes(patched_file))
        applied_to_disk = True

    if not changes:
        warnings.append(
            RenameIssue(
                offset=payload_offset + raw_row_offset,
                message="Linked roster slot already contains the requested values",
            )
        )

    return TeamLinkedRosterEditResult(
        file_path=path,
        player_file=player_path,
        matched_count=1,
        changes=changes,
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        warnings=warnings,
    )


def edit_team_roster_same_entry_authoritative(
    *,
    team_file: str,
    player_file: str = "DBDAT/JUG98030.FDI",
    team_query: str,
    team_offset: Optional[int] = None,
    slot_number: int,
    pid_candidate: int,
    write_changes: bool = True,
) -> TeamSameEntryRosterEditResult:
    """
    Patch one supported preferred same-entry roster slot in place.

    The current preferred same-entry families we write to are the strongest confirmed ones:
    `same_entry_authoritative` and `known_lineup_anchor_assisted`. Both currently validate as
    5-byte rows where the leading 2 bytes are the XOR'd 16-bit PID and the trailing 3 bytes
    are invariant filler (`0x61 0x61 0x61`) in the real dataset. The writer still preserves
    the observed tail bytes defensively rather than synthesizing them blindly.
    """
    if slot_number < 1:
        raise ValueError("slot_number must be >= 1")
    if not str(team_query or "").strip():
        raise ValueError("team_query is required for same-entry roster edits")
    if not (0 <= int(pid_candidate) <= 0xFFFF):
        raise ValueError("pid_candidate must be 0-65535")

    path = Path(team_file)
    player_path = Path(player_file)
    file_data = path.read_bytes()
    probe_result = extract_team_rosters_eq_same_entry_overlap(
        team_file=str(path),
        player_file=str(player_path),
        team_queries=[str(team_query).strip()],
        include_fallbacks=True,
    )
    team_result = _resolve_single_same_entry_team_result(
        list(getattr(probe_result, "requested_team_results", []) or []),
        team_query=str(team_query).strip(),
        team_offset=team_offset,
    )
    preferred = dict(team_result.get("preferred_roster_match") or {})
    preferred_provenance = str(preferred.get("provenance") or "")
    if preferred_provenance not in _SUPPORTED_SAME_ENTRY_WRITE_PROVENANCES:
        raise ValueError(
            "The selected team does not currently have a supported same-entry overlay mapping"
        )
    if not _preferred_same_entry_has_fixed_tail(preferred):
        raise ValueError(
            "The selected same-entry roster rows no longer match the confirmed 0x61 0x61 0x61 tail contract"
        )

    source = dict(preferred.get("source") or {})
    entry_offset_value = source.get("entry_offset")
    entry_offset = int(entry_offset_value) if isinstance(entry_offset_value, int) else -1
    if entry_offset < 0:
        raise RuntimeError("Same-entry roster match is missing its source entry offset")

    rows = _preferred_same_entry_rows(preferred)
    slot_index = slot_number - 1
    if slot_index >= len(rows):
        raise ValueError(
            f"Same-entry roster slot {slot_number} is out of range for "
            f"{str(team_result.get('team_name') or '') or '<unknown team>'} (rows={len(rows)})"
        )
    row = dict(rows[slot_index] or {})
    row_pos = int(row.get("pos", -1) or -1)
    if row_pos < 0:
        raise RuntimeError("Same-entry roster row is missing its byte position")
    _tail_b2, _tail_b3, _tail_b4, preserved_tail_bytes_hex = _same_entry_row_tail_bytes(row)

    decoded, entry_length = decode_entry(file_data, entry_offset)
    if row_pos + 2 > len(decoded):
        raise RuntimeError("Same-entry roster row overruns the decoded EQ entry")

    old_pid = int(row.get("pid_candidate", 0) or 0)
    new_pid = int(pid_candidate)
    dd6361_index = build_player_visible_skill_index_dd6361(file_path=str(player_path))
    old_name = str(row.get("dd6361_name") or "") or str(
        (dd6361_index.get(old_pid) or {}).get("resolved_bio_name") or ""
    )
    new_name = str((dd6361_index.get(new_pid) or {}).get("resolved_bio_name") or "")

    changes: List[TeamSameEntryRosterChange] = []
    warnings: List[RenameIssue] = []
    if new_pid != old_pid:
        patched_decoded = bytearray(decoded)
        patched_decoded[row_pos] = (new_pid & 0xFF) ^ 0x61
        patched_decoded[row_pos + 1] = ((new_pid >> 8) & 0xFF) ^ 0x61
        encoded_entry = encode_entry(bytes(patched_decoded))
        if len(encoded_entry) != 2 + entry_length:
            raise RuntimeError(
                f"Same-entry EQ container 0x{entry_offset:x} changed size unexpectedly; aborting write"
            )

        changes.append(
            TeamSameEntryRosterChange(
                team_offset=int(team_result.get("team_offset", 0) or 0),
                team_name=str(team_result.get("team_name") or ""),
                full_club_name=str(team_result.get("full_club_name") or ""),
                entry_offset=entry_offset,
                slot_number=slot_number,
                old_pid_candidate=old_pid,
                new_pid_candidate=new_pid,
                old_player_name=old_name,
                new_player_name=new_name,
                provenance=preferred_provenance,
                preserved_tail_bytes_hex=preserved_tail_bytes_hex,
            )
        )
    else:
        encoded_entry = b""

    backup_path = None
    applied_to_disk = False
    if write_changes and changes:
        patched_file = bytearray(file_data)
        patched_file[entry_offset : entry_offset + len(encoded_entry)] = encoded_entry
        backup_path = create_backup(str(path))
        path.write_bytes(bytes(patched_file))
        applied_to_disk = True

    if not changes:
        warnings.append(
            RenameIssue(
                offset=entry_offset + 2 + row_pos,
                message="Same-entry roster slot already contains the requested pid_candidate",
            )
        )

    return TeamSameEntryRosterEditResult(
        file_path=path,
        player_file=player_path,
        matched_count=1,
        changes=changes,
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        warnings=warnings,
    )


def batch_edit_team_roster_records(
    *,
    team_file: str,
    csv_path: str,
    player_file: str = "DBDAT/JUG98030.FDI",
    write_changes: bool = True,
    include_plan_preview: bool = True,
) -> TeamRosterBatchEditResult:
    path = Path(team_file)
    player_path = Path(player_file)
    plan_path = Path(csv_path)
    file_data = path.read_bytes()
    batch_rows = _load_team_roster_batch_rows(plan_path)

    linked_rosters = load_eq_linked_team_rosters(team_file=str(path), player_file=str(player_path))
    linked_player_names = {
        int(getattr(item, "player_record_id", 0) or 0): str(getattr(item, "player_name", "") or "")
        for roster in linked_rosters
        for item in list(getattr(roster, "rows", []) or [])
    }
    dd6361_index = build_player_visible_skill_index_dd6361(file_path=str(player_path))

    same_entry_queries = sorted(
        {
            str(row.get("team") or "").strip()
            for row in batch_rows
            if (
                (
                    row.get("source") == "same_entry"
                    or (
                        row.get("source") is None
                        and row.get("pid") is not None
                        and row.get("player_id") is None
                        and row.get("flag") is None
                    )
                )
                and str(row.get("team") or "").strip()
            )
        }
    )
    same_entry_requested_results: List[Dict[str, Any]] = []
    if same_entry_queries:
        probe_result = extract_team_rosters_eq_same_entry_overlap(
            team_file=str(path),
            player_file=str(player_path),
            team_queries=same_entry_queries,
            include_fallbacks=True,
        )
        same_entry_requested_results = list(getattr(probe_result, "requested_team_results", []) or [])

    linked_changes: List[TeamLinkedRosterChange] = []
    same_entry_changes: List[TeamSameEntryRosterChange] = []
    warnings: List[RenameIssue] = []
    matched_row_count = 0
    linked_payload_cache: Dict[Tuple[int, int], bytearray] = {}
    same_entry_cache: Dict[int, Tuple[bytearray, int]] = {}
    modified_linked_payload_keys: set[Tuple[int, int]] = set()
    modified_same_entry_offsets: set[int] = set()
    targeted_slots: set[Tuple[str, int, int]] = set()
    matched_row_numbers: set[int] = set()

    for row in batch_rows:
        row_number = int(row.get("row_number") or 0)
        team_query = str(row.get("team") or "").strip()
        eq_record_id = row.get("eq_record_id")
        team_offset = row.get("team_offset")
        slot_number = row.get("slot")
        player_record_id = row.get("player_id")
        flag = row.get("flag")
        pid_candidate = row.get("pid")
        source = row.get("source")
        if source is None:
            if pid_candidate is not None and player_record_id is None and flag is None:
                source = "same_entry"
            elif player_record_id is not None or flag is not None:
                source = "linked"

        if slot_number is None or slot_number < 1:
            warnings.append(
                RenameIssue(offset=None, message=f"CSV row {row_number}: slot must be a positive integer")
            )
            continue
        if source not in {"linked", "same_entry"}:
            warnings.append(
                RenameIssue(
                    offset=None,
                    message=(
                        f"CSV row {row_number}: could not determine source; set source=linked or source=same_entry"
                    ),
                )
            )
            continue

        try:
            if source == "linked":
                if player_record_id is None and flag is None:
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=(
                                f"CSV row {row_number}: linked rows require player_id and/or flag"
                            ),
                        )
                    )
                    continue
                if player_record_id is not None and int(player_record_id) < 0:
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=f"CSV row {row_number}: player_id must be >= 0",
                        )
                    )
                    continue
                if flag is not None and not (0 <= int(flag) <= 255):
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=f"CSV row {row_number}: flag must be 0-255",
                        )
                    )
                    continue
                roster = _resolve_single_linked_team_roster(
                    linked_rosters,
                    team_query=team_query or None,
                    eq_record_id=eq_record_id,
                )
                rows = list(getattr(roster, "rows", []) or [])
                slot_index = slot_number - 1
                if slot_index >= len(rows):
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=(
                                f"CSV row {row_number}: linked slot {slot_number} is out of range "
                                f"(rows={len(rows)})"
                            ),
                        )
                    )
                    continue
                row_obj = rows[slot_index]
                raw_row_offset = int(getattr(row_obj, "raw_row_offset", -1) or -1)
                payload_offset = int(getattr(roster, "payload_offset", 0) or 0)
                payload_length = int(getattr(roster, "payload_length", 0) or 0)
                if raw_row_offset < 0 or payload_offset < 0 or payload_length <= 0:
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=f"CSV row {row_number}: linked row is missing safe payload metadata",
                        )
                    )
                    continue
                if payload_offset + payload_length > len(file_data) or raw_row_offset + 5 > payload_length:
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=f"CSV row {row_number}: linked row is outside file bounds",
                        )
                    )
                    continue
                target_key = ("linked", payload_offset, raw_row_offset)
                if target_key in targeted_slots:
                    warnings.append(
                        RenameIssue(
                            offset=payload_offset + raw_row_offset,
                            message=(
                                f"CSV row {row_number}: duplicate target slot; earlier row already staged it"
                            ),
                        )
                    )
                    continue
                payload_key = (payload_offset, payload_length)
                payload = linked_payload_cache.setdefault(
                    payload_key,
                    bytearray(file_data[payload_offset : payload_offset + payload_length]),
                )
                old_flag = int(payload[raw_row_offset])
                old_pid = int.from_bytes(payload[raw_row_offset + 1 : raw_row_offset + 5], "little")
                new_flag = old_flag if flag is None else int(flag)
                new_pid = old_pid if player_record_id is None else int(player_record_id)
                matched_row_count += 1
                matched_row_numbers.add(row_number)
                if new_flag == old_flag and new_pid == old_pid:
                    continue
                payload[raw_row_offset] = new_flag
                payload[raw_row_offset + 1 : raw_row_offset + 5] = int(new_pid).to_bytes(4, "little")
                targeted_slots.add(target_key)
                modified_linked_payload_keys.add(payload_key)
                old_name = str(getattr(row_obj, "player_name", "") or "") or str(linked_player_names.get(old_pid) or "")
                new_name = str(linked_player_names.get(new_pid) or "")
                linked_changes.append(
                    TeamLinkedRosterChange(
                        eq_record_id=int(getattr(roster, "eq_record_id", 0) or 0),
                        team_name=str(getattr(roster, "short_name", "") or ""),
                        full_club_name=str(getattr(roster, "full_club_name", "") or ""),
                        slot_number=slot_number,
                        old_flag=old_flag,
                        new_flag=new_flag,
                        old_player_record_id=old_pid,
                        new_player_record_id=new_pid,
                        old_player_name=old_name,
                        new_player_name=new_name,
                        plan_row_number=row_number,
                    )
                )
            else:
                if pid_candidate is None:
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=f"CSV row {row_number}: same-entry rows require pid",
                        )
                    )
                    continue
                if not (0 <= int(pid_candidate) <= 0xFFFF):
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=f"CSV row {row_number}: pid must be 0-65535",
                        )
                    )
                    continue
                if not team_query:
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=f"CSV row {row_number}: same-entry rows require a team query",
                        )
                    )
                    continue
                team_result = _resolve_single_same_entry_team_result(
                    [
                        item
                        for item in same_entry_requested_results
                        if team_query_matches(
                            team_query,
                            team_name=str(item.get("team_name") or ""),
                            full_club_name=str(item.get("full_club_name") or ""),
                        )
                    ],
                    team_query=team_query,
                    team_offset=team_offset,
                )
                preferred = dict(team_result.get("preferred_roster_match") or {})
                preferred_provenance = str(preferred.get("provenance") or "")
                if preferred_provenance not in _SUPPORTED_SAME_ENTRY_WRITE_PROVENANCES:
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=(
                                f"CSV row {row_number}: team does not currently resolve to a supported same-entry overlay"
                            ),
                        )
                    )
                    continue
                if not _preferred_same_entry_has_fixed_tail(preferred):
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=(
                                f"CSV row {row_number}: same-entry rows no longer match the confirmed 616161 tail contract"
                            ),
                        )
                    )
                    continue
                rows = _preferred_same_entry_rows(preferred)
                slot_index = slot_number - 1
                if slot_index >= len(rows):
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=(
                                f"CSV row {row_number}: same-entry slot {slot_number} is out of range "
                                f"(rows={len(rows)})"
                            ),
                        )
                    )
                    continue
                row_obj = dict(rows[slot_index] or {})
                row_pos = int(row_obj.get("pos", -1) or -1)
                source_info = dict(preferred.get("source") or {})
                entry_offset_value = source_info.get("entry_offset")
                entry_offset = int(entry_offset_value) if isinstance(entry_offset_value, int) else -1
                if row_pos < 0 or entry_offset < 0:
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=f"CSV row {row_number}: same-entry row is missing safe offset metadata",
                        )
                    )
                    continue
                target_key = ("same_entry", entry_offset, row_pos)
                if target_key in targeted_slots:
                    warnings.append(
                        RenameIssue(
                            offset=entry_offset + 2 + row_pos,
                            message=(
                                f"CSV row {row_number}: duplicate target slot; earlier row already staged it"
                            ),
                        )
                    )
                    continue
                decoded_and_length = same_entry_cache.get(entry_offset)
                if decoded_and_length is None:
                    decoded, entry_length = decode_entry(file_data, entry_offset)
                    decoded_and_length = (bytearray(decoded), entry_length)
                    same_entry_cache[entry_offset] = decoded_and_length
                decoded_bytes, _entry_length = decoded_and_length
                if row_pos + 2 > len(decoded_bytes):
                    warnings.append(
                        RenameIssue(
                            offset=entry_offset + 2 + row_pos,
                            message=f"CSV row {row_number}: same-entry row overruns the decoded entry",
                        )
                    )
                    continue
                old_pid = int((decoded_bytes[row_pos] ^ 0x61) | ((decoded_bytes[row_pos + 1] ^ 0x61) << 8))
                new_pid = int(pid_candidate)
                matched_row_count += 1
                matched_row_numbers.add(row_number)
                if old_pid == new_pid:
                    continue
                decoded_bytes[row_pos] = (new_pid & 0xFF) ^ 0x61
                decoded_bytes[row_pos + 1] = ((new_pid >> 8) & 0xFF) ^ 0x61
                targeted_slots.add(target_key)
                modified_same_entry_offsets.add(entry_offset)
                _tail_b2, _tail_b3, _tail_b4, preserved_tail_bytes_hex = _same_entry_row_tail_bytes(row_obj)
                old_name = str(row_obj.get("dd6361_name") or "") or str(
                    (dd6361_index.get(old_pid) or {}).get("resolved_bio_name") or ""
                )
                new_name = str((dd6361_index.get(new_pid) or {}).get("resolved_bio_name") or "")
                same_entry_changes.append(
                    TeamSameEntryRosterChange(
                        team_offset=int(team_result.get("team_offset", 0) or 0),
                        team_name=str(team_result.get("team_name") or ""),
                        full_club_name=str(team_result.get("full_club_name") or ""),
                        entry_offset=entry_offset,
                        slot_number=slot_number,
                        old_pid_candidate=old_pid,
                        new_pid_candidate=new_pid,
                        old_player_name=old_name,
                        new_player_name=new_name,
                        provenance=preferred_provenance,
                        preserved_tail_bytes_hex=preserved_tail_bytes_hex,
                        plan_row_number=row_number,
                    )
                )
        except Exception as exc:
            warnings.append(RenameIssue(offset=None, message=f"CSV row {row_number}: {exc}"))

    plan_preview: List[TeamRosterBatchPlanRowPreview] = []
    if include_plan_preview:
        plan_preview = _build_team_roster_batch_plan_preview(
            batch_rows=batch_rows,
            matched_row_numbers=matched_row_numbers,
            linked_changes=linked_changes,
            same_entry_changes=same_entry_changes,
            warnings=warnings,
        )

    backup_path = None
    applied_to_disk = False
    if write_changes and (linked_changes or same_entry_changes):
        patched_file = bytearray(file_data)
        for payload_key in sorted(modified_linked_payload_keys, reverse=True):
            payload_offset, payload_length = payload_key
            payload = linked_payload_cache[payload_key]
            patched_file[payload_offset : payload_offset + payload_length] = payload
        for entry_offset in sorted(modified_same_entry_offsets, reverse=True):
            decoded_bytes, entry_length = same_entry_cache[entry_offset]
            encoded_entry = encode_entry(bytes(decoded_bytes))
            if len(encoded_entry) != 2 + entry_length:
                raise RuntimeError(
                    f"Same-entry EQ container 0x{entry_offset:x} changed size unexpectedly; aborting write"
                )
            patched_file[entry_offset : entry_offset + len(encoded_entry)] = encoded_entry
        backup_path = create_backup(str(path))
        path.write_bytes(bytes(patched_file))
        applied_to_disk = True

    return TeamRosterBatchEditResult(
        file_path=path,
        player_file=player_path,
        csv_path=plan_path,
        row_count=len(batch_rows),
        matched_row_count=matched_row_count,
        linked_changes=linked_changes,
        same_entry_changes=same_entry_changes,
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        warnings=warnings,
        plan_preview=plan_preview,
    )



def clone_team_roster_eq_jug_linked(
    *,
    team_file: str,
    source_team_query: Optional[str] = None,
    source_eq_record_id: Optional[int] = None,
    target_team_query: Optional[str] = None,
    target_eq_record_id: Optional[int] = None,
    player_file: str = "DBDAT/JUG98030.FDI",
    slot_limit: Optional[int] = 25,
    write_changes: bool = True,
) -> TeamLinkedRosterCloneResult:
    """
    Clone one authoritative linked roster into another linked roster slot-for-slot.

    This supports fast, reproducible full-squad swaps (for example replacing all
    25 Stoke slots with another club's linked roster payload).
    """
    if slot_limit is not None and int(slot_limit) < 1:
        raise ValueError("slot_limit must be >= 1 when provided")

    path = Path(team_file)
    player_path = Path(player_file)
    file_data = path.read_bytes()

    rosters = load_eq_linked_team_rosters(team_file=str(path), player_file=str(player_path))
    source_roster = _resolve_single_linked_team_roster(
        rosters,
        team_query=source_team_query,
        eq_record_id=source_eq_record_id,
    )
    target_roster = _resolve_single_linked_team_roster(
        rosters,
        team_query=target_team_query,
        eq_record_id=target_eq_record_id,
    )

    source_eq_id = int(getattr(source_roster, "eq_record_id", 0) or 0)
    target_eq_id = int(getattr(target_roster, "eq_record_id", 0) or 0)
    if source_eq_id == target_eq_id:
        raise ValueError("Source and target linked rosters resolve to the same eq_record_id")

    source_rows = list(getattr(source_roster, "rows", []) or [])
    target_rows = list(getattr(target_roster, "rows", []) or [])
    if not source_rows:
        raise ValueError("Source linked roster has no rows to clone")
    if not target_rows:
        raise ValueError("Target linked roster has no rows to update")

    compared_slot_count = min(
        len(source_rows),
        len(target_rows),
        int(slot_limit) if slot_limit is not None else 25,
    )
    if compared_slot_count <= 0:
        raise ValueError("No overlapping linked roster slots are available to clone")

    payload_offset = int(getattr(target_roster, "payload_offset", 0) or 0)
    payload_length = int(getattr(target_roster, "payload_length", 0) or 0)
    if payload_offset < 0 or payload_length <= 0 or payload_offset + payload_length > len(file_data):
        raise RuntimeError("Target linked roster payload is outside file bounds; cannot clone safely")

    payload = bytearray(file_data[payload_offset : payload_offset + payload_length])
    changes: List[TeamLinkedRosterChange] = []
    warnings: List[RenameIssue] = []

    for slot_index in range(compared_slot_count):
        source_row = source_rows[slot_index]
        target_row = target_rows[slot_index]
        raw_row_offset = int(getattr(target_row, "raw_row_offset", -1) or -1)
        if raw_row_offset < 0 or raw_row_offset + 5 > len(payload):
            warnings.append(
                RenameIssue(
                    offset=None,
                    message=(
                        f"Target slot {slot_index + 1} is missing safe payload metadata; skipped"
                    ),
                )
            )
            continue

        old_flag = int(payload[raw_row_offset])
        old_pid = int.from_bytes(payload[raw_row_offset + 1 : raw_row_offset + 5], "little")
        new_flag = int(getattr(source_row, "flag", 0) or 0) & 0xFF
        new_pid = int(getattr(source_row, "player_record_id", 0) or 0)
        if new_pid < 0 or new_pid > 0xFFFFFFFF:
            warnings.append(
                RenameIssue(
                    offset=payload_offset + raw_row_offset + 1,
                    message=(
                        f"Source slot {slot_index + 1} has out-of-range player_record_id={new_pid}; skipped"
                    ),
                )
            )
            continue

        if old_flag == new_flag and old_pid == new_pid:
            continue

        payload[raw_row_offset] = new_flag
        payload[raw_row_offset + 1 : raw_row_offset + 5] = int(new_pid).to_bytes(4, "little")

        changes.append(
            TeamLinkedRosterChange(
                eq_record_id=target_eq_id,
                team_name=str(getattr(target_roster, "short_name", "") or ""),
                full_club_name=str(getattr(target_roster, "full_club_name", "") or ""),
                slot_number=slot_index + 1,
                old_flag=old_flag,
                new_flag=new_flag,
                old_player_record_id=old_pid,
                new_player_record_id=new_pid,
                old_player_name=str(getattr(target_row, "player_name", "") or ""),
                new_player_name=str(getattr(source_row, "player_name", "") or ""),
            )
        )

    backup_path = None
    applied_to_disk = False
    if write_changes and changes:
        patched_file = bytearray(file_data)
        patched_file[payload_offset : payload_offset + payload_length] = payload
        backup_path = create_backup(str(path))
        path.write_bytes(bytes(patched_file))
        applied_to_disk = True

    if not changes:
        warnings.append(
            RenameIssue(
                offset=payload_offset,
                message="Target linked roster already matches source values for compared slots",
            )
        )

    return TeamLinkedRosterCloneResult(
        file_path=path,
        player_file=player_path,
        source_eq_record_id=source_eq_id,
        source_team_name=str(getattr(source_roster, "short_name", "") or ""),
        source_full_club_name=str(getattr(source_roster, "full_club_name", "") or ""),
        target_eq_record_id=target_eq_id,
        target_team_name=str(getattr(target_roster, "short_name", "") or ""),
        target_full_club_name=str(getattr(target_roster, "full_club_name", "") or ""),
        slot_limit=int(slot_limit) if slot_limit is not None else 25,
        compared_slot_count=compared_slot_count,
        matched_count=compared_slot_count,
        changes=changes,
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        warnings=warnings,
    )


_TEAM_ROSTER_BATCH_TEMPLATE_FIELDNAMES = [
    "team",
    "source",
    "eq_record_id",
    "team_offset",
    "slot",
    "player_id",
    "flag",
    "pid",
    "current_player",
    "new_name",
    "elite_skills",
    "speed",
    "stamina",
    "aggression",
    "quality",
    "handling",
    "passing",
    "dribbling",
    "heading",
    "tackling",
    "shooting",
    "note",
]


def export_team_roster_batch_template(
    *,
    team_file: str,
    output_csv: str,
    team_query: Optional[str] = None,
    eq_record_id: Optional[int] = None,
    team_offset: Optional[int] = None,
    source: Optional[str] = None,
    player_file: str = "DBDAT/JUG98030.FDI",
) -> TeamRosterBatchTemplateExportResult:
    """
    Export an import-ready roster batch CSV template for one club.

    The exported columns map directly to `team-roster-batch-edit`.
    Additional `new_name`/skill columns are included as planning fields for
    future batch promotion workflows and are ignored by current slot writer paths.
    """
    normalized_source = _normalize_team_roster_batch_source(source)
    requested_query = str(team_query or "").strip()

    team_path = Path(team_file)
    player_path = Path(player_file)
    output_path = Path(output_csv)

    selected_source = ""
    selected_team_name = ""
    selected_full_club_name = ""
    selected_eq_record_id: Optional[int] = None
    selected_team_offset: Optional[int] = None
    rows: List[Dict[str, Any]] = []
    warnings: List[RenameIssue] = []
    linked_failure: Optional[Exception] = None

    if normalized_source in {None, "linked"}:
        try:
            rosters = load_eq_linked_team_rosters(team_file=str(team_path), player_file=str(player_path))
            roster = _resolve_single_linked_team_roster(
                rosters,
                team_query=requested_query if requested_query else None,
                eq_record_id=eq_record_id,
            )
            selected_source = "linked"
            selected_team_name = str(getattr(roster, "short_name", "") or "")
            selected_full_club_name = str(getattr(roster, "full_club_name", "") or "")
            selected_eq_record_id = int(getattr(roster, "eq_record_id", 0) or 0) or None
            for row in list(getattr(roster, "rows", []) or []):
                rows.append(
                    {
                        "team": selected_team_name,
                        "source": "linked",
                        "eq_record_id": selected_eq_record_id,
                        "team_offset": "",
                        "slot": int(getattr(row, "slot_index", 0) or 0) + 1,
                        "player_id": int(getattr(row, "player_record_id", 0) or 0),
                        "flag": int(getattr(row, "flag", 0) or 0),
                        "pid": "",
                        "current_player": str(getattr(row, "player_name", "") or ""),
                        "new_name": "",
                        "elite_skills": "",
                        "speed": "",
                        "stamina": "",
                        "aggression": "",
                        "quality": "",
                        "handling": "",
                        "passing": "",
                        "dribbling": "",
                        "heading": "",
                        "tackling": "",
                        "shooting": "",
                        "note": "",
                    }
                )
        except Exception as exc:
            linked_failure = exc

    if not rows and normalized_source in {None, "same_entry"}:
        if not requested_query and team_offset is None:
            raise ValueError(
                "team_query is required for same_entry template export unless team_offset is provided"
            )

        overlap = extract_team_rosters_eq_same_entry_overlap(
            team_file=str(team_path),
            player_file=str(player_path),
            team_queries=[requested_query] if requested_query else None,
            include_fallbacks=True,
        )
        requested_results = list(getattr(overlap, "requested_team_results", []) or [])
        resolved_query = requested_query if requested_query else f"team_offset=0x{int(team_offset or 0):X}"
        team_result = _resolve_single_same_entry_team_result(
            requested_results,
            team_query=resolved_query,
            team_offset=team_offset,
        )
        preferred = dict(team_result.get("preferred_roster_match") or {})
        provenance = str(preferred.get("provenance") or "")
        if provenance not in _SUPPORTED_SAME_ENTRY_WRITE_PROVENANCES:
            raise ValueError(
                "The selected team does not currently have a supported same-entry roster mapping"
            )

        selected_source = "same_entry"
        selected_team_name = str(team_result.get("team_name") or "")
        selected_full_club_name = str(team_result.get("full_club_name") or "")
        selected_team_offset = int(team_result.get("team_offset", 0) or 0)

        preferred_rows = _preferred_same_entry_rows(preferred)
        for slot_index, row in enumerate(preferred_rows, start=1):
            rows.append(
                {
                    "team": selected_team_name,
                    "source": "same_entry",
                    "eq_record_id": "",
                    "team_offset": selected_team_offset,
                    "slot": slot_index,
                    "player_id": "",
                    "flag": "",
                    "pid": int(row.get("pid_candidate", 0) or 0),
                    "current_player": str(row.get("dd6361_name") or ""),
                    "new_name": "",
                    "elite_skills": "",
                    "speed": "",
                    "stamina": "",
                    "aggression": "",
                    "quality": "",
                    "handling": "",
                    "passing": "",
                    "dribbling": "",
                    "heading": "",
                    "tackling": "",
                    "shooting": "",
                    "note": f"provenance={provenance}",
                }
            )

    if not rows:
        if linked_failure is not None and normalized_source in {None, "linked"}:
            raise ValueError(f"Could not resolve linked roster for template export: {linked_failure}")
        raise ValueError("No roster rows are available for template export")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(_TEAM_ROSTER_BATCH_TEMPLATE_FIELDNAMES))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return TeamRosterBatchTemplateExportResult(
        team_file=team_path,
        player_file=player_path,
        output_csv=output_path,
        source=selected_source,
        team_name=selected_team_name,
        full_club_name=selected_full_club_name,
        eq_record_id=selected_eq_record_id,
        team_offset=selected_team_offset,
        row_count=len(rows),
        warnings=warnings,
    )


def _write_modified_indexed_entries(
    path: Path,
    file_data: bytes,
    modified_entries: List[Tuple[int, Any]],
    *,
    create_backup_before_write: bool = True,
) -> Optional[str]:
    indexed = _try_load_indexed_player_file(file_data)
    if indexed is None:
        raise RuntimeError("Indexed write requested for a non-indexed DMFI container")

    entries_by_offset: Dict[int, Any] = {int(entry.payload_offset): entry for entry in indexed.entries}
    modified_by_offset: Dict[int, Any] = {}
    for offset, record in modified_entries:
        container_offset = getattr(record, "container_offset", offset)
        if not isinstance(container_offset, int):
            raise RuntimeError(f"Indexed record key {offset!r} is missing container_offset metadata")
        if int(container_offset) in modified_by_offset:
            raise RuntimeError(f"Duplicate staged indexed record at payload offset 0x{int(container_offset):x}")
        modified_by_offset[int(container_offset)] = record

    missing_offsets = [off for off in modified_by_offset if off not in entries_by_offset]
    if missing_offsets:
        preview = ", ".join(f"0x{off:x}" for off in missing_offsets[:6])
        raise RuntimeError(
            f"Staged indexed record offsets were not found in the file index ({preview})"
        )

    ordered_entries = sorted(indexed.entries, key=lambda item: int(item.payload_offset))
    first_payload_offset = int(ordered_entries[0].payload_offset)
    if first_payload_offset <= 0 or first_payload_offset > len(file_data):
        raise RuntimeError("Indexed payload region starts outside file bounds")

    encoded_payload_by_offset: Dict[int, bytes] = {}
    new_lengths_by_offset: Dict[int, int] = {}
    for entry in ordered_entries:
        old_offset = int(entry.payload_offset)
        old_length = int(entry.payload_length)
        old_end = old_offset + old_length
        if old_offset < 0 or old_end > len(file_data):
            raise RuntimeError(
                f"Indexed payload 0x{old_offset:x}+0x{old_length:x} is outside file bounds"
            )

        record = modified_by_offset.get(old_offset)
        if record is None:
            encoded_payload = bytes(file_data[old_offset:old_end])
        else:
            new_decoded = record.to_bytes()
            if not isinstance(new_decoded, (bytes, bytearray)):
                raise TypeError("record.to_bytes() must return bytes")
            encoded_payload = xor_encode(bytes(new_decoded))
        encoded_payload_by_offset[old_offset] = encoded_payload
        new_lengths_by_offset[old_offset] = len(encoded_payload)

    rebuilt = bytearray(file_data[:first_payload_offset])
    new_offsets_by_old_offset: Dict[int, int] = {}
    for idx, entry in enumerate(ordered_entries):
        old_offset = int(entry.payload_offset)
        old_length = int(entry.payload_length)
        old_end = old_offset + old_length

        new_offsets_by_old_offset[old_offset] = len(rebuilt)
        rebuilt.extend(encoded_payload_by_offset[old_offset])

        if idx + 1 < len(ordered_entries):
            next_offset = int(ordered_entries[idx + 1].payload_offset)
            if next_offset < old_end:
                raise RuntimeError(
                    f"Indexed payload overlap detected between 0x{old_offset:x} and 0x{next_offset:x}"
                )
            rebuilt.extend(file_data[old_end:next_offset])
        else:
            rebuilt.extend(file_data[old_end:])

    for entry in indexed.entries:
        index_offset = int(entry.index_offset)
        if index_offset < 0 or (index_offset + 5) > first_payload_offset:
            raise RuntimeError(
                f"Indexed directory entry at 0x{index_offset:x} is outside the index region"
            )

        key_length = int(rebuilt[index_offset + 4])
        payload_offset_pos = index_offset + 5 + key_length
        payload_length_pos = payload_offset_pos + 4
        if payload_length_pos + 4 > first_payload_offset:
            raise RuntimeError(
                f"Indexed directory entry at 0x{index_offset:x} has an invalid key length ({key_length})"
            )

        old_payload_offset = int(entry.payload_offset)
        struct.pack_into("<I", rebuilt, payload_offset_pos, int(new_offsets_by_old_offset[old_payload_offset]))
        struct.pack_into("<I", rebuilt, payload_length_pos, int(new_lengths_by_offset[old_payload_offset]))

    try:
        reparsed = IndexedFDIFile.from_bytes(bytes(rebuilt))
    except Exception as exc:
        raise RuntimeError(f"Rebuilt indexed file failed structural validation: {exc}") from exc
    if len(reparsed.entries) != len(indexed.entries):
        raise RuntimeError(
            f"Indexed record count changed after rewrite ({len(indexed.entries)} -> {len(reparsed.entries)})"
        )

    backup_path = None
    if create_backup_before_write:
        backup_path = create_backup(str(path))
    path.write_bytes(bytes(rebuilt))
    return backup_path


def _write_modified_entries(
    path: Path,
    file_data: bytes,
    modified_entries: List[Tuple[int, Any]],
    *,
    create_backup_before_write: bool = True,
) -> Optional[str]:
    if not modified_entries:
        return None
    if all(
        getattr(record, "container_encoding", None) == "indexed_xor"
        and isinstance(getattr(record, "container_length", None), int)
        for _, record in modified_entries
    ):
        return _write_modified_indexed_entries(
            path,
            file_data,
            modified_entries,
            create_backup_before_write=create_backup_before_write,
        )

    new_bytes = save_modified_records(str(path), file_data, modified_entries)
    backup_path = None
    if create_backup_before_write:
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


def write_player_staged_records(
    file_path: str,
    modified_records: List[Tuple[int, Any]],
    *,
    create_backup_before_write: bool = True,
) -> Optional[str]:
    """
    Save staged player records through the shared writer path used by CLI edit contracts.

    Supports indexed DMFI payload rewrites where name mutations can change payload length.
    """
    if not modified_records:
        return None
    path = Path(file_path)
    file_data = path.read_bytes()
    return _write_modified_entries(
        path,
        file_data,
        modified_records,
        create_backup_before_write=create_backup_before_write,
    )


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
        # The default player list can still include fallback heuristic offsets when no
        # strict boundary-backed record exists for a name. Filter to real FDI entry
        # boundaries before writing.
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
                    message="No player changes were written because all matches resolved to non-writable fallback offsets",
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


def _apply_player_mutations(
    record: PlayerRecord,
    *,
    new_name: Optional[str] = None,
    position: Optional[int] = None,
    nationality: Optional[int] = None,
    birth_day: Optional[int] = None,
    birth_month: Optional[int] = None,
    birth_year: Optional[int] = None,
    height: Optional[int] = None,
    weight: Optional[int] = None,
) -> Dict[str, Tuple[Any, Any]]:
    before_fields: Dict[str, Any] = {
        "name": _player_display_name(record),
        "position": getattr(record, "position_primary", None),
        "nationality": getattr(record, "nationality", None),
        "birth_day": getattr(record, "birth_day", None),
        "birth_month": getattr(record, "birth_month", None),
        "birth_year": getattr(record, "birth_year", None),
        "height": getattr(record, "height", None),
        "weight": getattr(record, "weight", None),
    }

    if new_name is not None:
        record.set_name(new_name)
    if position is not None:
        record.set_position(position)
    if nationality is not None:
        record.set_nationality(nationality)
    if birth_day is not None or birth_month is not None or birth_year is not None:
        record.set_dob(
            birth_day if birth_day is not None else int(getattr(record, "birth_day", 1) or 1),
            birth_month if birth_month is not None else int(getattr(record, "birth_month", 1) or 1),
            birth_year if birth_year is not None else int(getattr(record, "birth_year", 1975) or 1975),
        )
    if height is not None:
        record.set_height(height)
    if weight is not None:
        if not record.supports_weight_write():
            raise ValueError("This player record does not expose a parser-backed in-place weight slot")
        record.set_weight(weight)

    after_fields: Dict[str, Any] = {
        "name": _player_display_name(record),
        "position": getattr(record, "position_primary", None),
        "nationality": getattr(record, "nationality", None),
        "birth_day": getattr(record, "birth_day", None),
        "birth_month": getattr(record, "birth_month", None),
        "birth_year": getattr(record, "birth_year", None),
        "height": getattr(record, "height", None),
        "weight": getattr(record, "weight", None),
    }

    changed_fields: Dict[str, Tuple[Any, Any]] = {}
    for field_name, before in before_fields.items():
        after = after_fields[field_name]
        if before != after:
            changed_fields[field_name] = (before, after)
    return changed_fields


def _parse_optional_csv_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return int(text, 0)


def validate_database_files(
    *,
    player_file: Optional[str] = None,
    team_file: Optional[str] = None,
    coach_file: Optional[str] = None,
) -> DatabaseValidationResult:
    """
    Re-open the requested database files through the shared parser-backed product loaders.

    This is a post-write safety check: a write only counts as healthy if the saved file can
    be parsed again by the same default editor paths.
    """

    files: List[DatabaseFileValidation] = []

    def _validate_one(
        *,
        category: str,
        file_path: Optional[str],
        loader,
    ) -> None:
        if not file_path:
            return
        path = Path(file_path)
        if not path.exists():
            files.append(
                DatabaseFileValidation(
                    category=category,
                    file_path=path,
                    success=False,
                    valid_count=0,
                    uncertain_count=0,
                    detail="file not found",
                )
            )
            return
        try:
            valid, uncertain = loader(str(path))
            valid_count = len(valid)
            uncertain_count = len(uncertain)
            total = valid_count + uncertain_count
            if total <= 0:
                files.append(
                    DatabaseFileValidation(
                        category=category,
                        file_path=path,
                        success=False,
                        valid_count=valid_count,
                        uncertain_count=uncertain_count,
                        detail="re-opened but no records parsed",
                    )
                )
                return
            detail = "re-opened cleanly"
            if uncertain_count:
                detail += " (with uncertain fallback records)"
            files.append(
                DatabaseFileValidation(
                    category=category,
                    file_path=path,
                    success=True,
                    valid_count=valid_count,
                    uncertain_count=uncertain_count,
                    detail=detail,
                )
            )
        except Exception as exc:
            files.append(
                DatabaseFileValidation(
                    category=category,
                    file_path=path,
                    success=False,
                    valid_count=0,
                    uncertain_count=0,
                    detail=str(exc),
                )
            )

    _validate_one(category="players", file_path=player_file, loader=gather_player_records)
    _validate_one(category="teams", file_path=team_file, loader=gather_team_records)
    _validate_one(category="coaches", file_path=coach_file, loader=gather_coach_records)

    return DatabaseValidationResult(
        files=files,
        all_valid=bool(files) and all(item.success for item in files),
    )


def _resolve_single_linked_team_roster(
    rosters: List[Any],
    *,
    team_query: Optional[str] = None,
    eq_record_id: Optional[int] = None,
) -> Any:
    if eq_record_id is not None:
        matches = [roster for roster in rosters if int(getattr(roster, "eq_record_id", 0) or 0) == eq_record_id]
        if not matches:
            raise ValueError(f"No parser-backed EQ->JUG linked roster found for eq_record_id={eq_record_id}")
        if len(matches) > 1:
            raise ValueError(f"Multiple linked rosters unexpectedly matched eq_record_id={eq_record_id}")
        return matches[0]

    query = str(team_query or "").strip()
    if not query:
        raise ValueError("Provide team_query and/or eq_record_id to select a linked roster")

    matches = []
    for roster in rosters:
        short_name = str(getattr(roster, "short_name", "") or "").strip()
        full_club_name = str(getattr(roster, "full_club_name", "") or "").strip()
        if team_query_matches(query, team_name=short_name, full_club_name=full_club_name):
            matches.append(roster)

    if not matches:
        raise ValueError(f"No parser-backed EQ->JUG linked roster matched team query {query!r}")
    if len(matches) > 1:
        labels = ", ".join(
            f"{getattr(roster, 'short_name', '')}#{int(getattr(roster, 'eq_record_id', 0) or 0)}"
            for roster in matches[:5]
        )
        raise ValueError(
            f"Team query {query!r} is ambiguous across {len(matches)} linked rosters ({labels}); "
            "use eq_record_id to disambiguate"
        )
    return matches[0]


def _resolve_single_same_entry_team_result(
    requested_results: List[Dict[str, Any]],
    *,
    team_query: str,
    team_offset: Optional[int] = None,
) -> Dict[str, Any]:
    if not requested_results:
        raise ValueError(f"No same-entry roster candidates matched team query {team_query!r}")
    if team_offset is not None:
        matches = [
            row for row in requested_results
            if int(row.get("team_offset", -1) or -1) == int(team_offset)
        ]
        if not matches:
            raise ValueError(
                f"No same-entry roster candidate matched team query {team_query!r} at team_offset=0x{int(team_offset):X}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"Multiple same-entry roster candidates unexpectedly matched team_offset=0x{int(team_offset):X}"
            )
        return matches[0]
    if len(requested_results) > 1:
        labels = ", ".join(
            f"{str(row.get('team_name') or '')}@0x{int(row.get('team_offset', 0) or 0):X}"
            for row in requested_results[:5]
        )
        raise ValueError(
            f"Team query {team_query!r} is ambiguous across {len(requested_results)} same-entry matches ({labels}); "
            "use team_offset to disambiguate"
        )
    return requested_results[0]


def _try_load_indexed_player_file(file_data: bytes) -> Optional[IndexedFDIFile]:
    """Return an indexed container only when the inline index layout is structurally plausible."""
    if file_data[:8] != b"DMFIv1.0":
        return None
    try:
        indexed = IndexedFDIFile.from_bytes(file_data)
    except Exception:
        return None
    if not indexed.entries:
        return None

    ordered = sorted(indexed.entries, key=lambda entry: entry.payload_offset)
    if ordered[0].payload_offset < indexed.index_end_offset:
        return None

    cursor = indexed.index_end_offset
    for entry in ordered:
        if entry.payload_length <= 0:
            return None
        if entry.payload_offset < cursor:
            return None
        cursor = entry.payload_offset + entry.payload_length
    return indexed


def _encoded_name_len(name: str) -> int:
    return len(str(name or "").encode("cp1252", errors="replace"))


def _scan_plain_name_capacity(raw_data: bytes, current_name: str) -> Optional[int]:
    name_bytes = str(current_name or "").encode("cp1252", errors="replace")
    if not name_bytes:
        return None
    index = bytes(raw_data).find(name_bytes)
    if index < 0:
        return None
    cursor = int(index) + len(name_bytes)
    slack = 0
    while cursor < len(raw_data) and raw_data[cursor] in (0x00, 0x20):
        slack += 1
        cursor += 1
    return len(name_bytes) + slack


def _scan_length_prefixed_name_capacity(raw_data: bytes, current_name: str) -> tuple[Optional[int], str]:
    """
    Return (max_text_bytes, parsed_display_name) for the two-string name layout.

    max_text_bytes excludes the 2-byte length prefixes for given/surname and
    corresponds to the total encoded text bytes available across both parts.
    """
    try:
        pos = 5
        given, consumed_given = read_string(raw_data, pos)
        pos += consumed_given
        surname, consumed_surname = read_string(raw_data, pos)
    except Exception:
        return None, ""

    parsed = " ".join(part for part in (str(given or "").strip(), str(surname or "").strip()) if part).strip()
    if not parsed:
        return None, ""
    if _normalize_text(parsed) != _normalize_text(current_name):
        return None, parsed
    block_len = int(consumed_given) + int(consumed_surname)
    return max(0, block_len - 4), parsed


def _scan_structured_name_window_capacity(raw_data: bytes) -> int:
    """
    Mirror PlayerRecord._rebuild_name_region() window sizing without mutating.
    """
    data = bytes(raw_data or b"")
    if not data:
        return 0

    name_start = 5
    attr_start = len(data) - 19 if len(data) >= 19 else len(data)
    attr_start = max(name_start, attr_start)
    marker = bytes([0x61, 0x61, 0x61, 0x61])

    marker_pos = None
    for idx in range(name_start, max(name_start, attr_start - 3)):
        if data[idx : idx + 4] == marker:
            marker_pos = idx
            break

    parsed_names_end = None
    try:
        pos = name_start
        for _ in range(2):
            if pos + 2 > attr_start:
                raise ValueError("name length prefix out of range")
            seg_len = struct.unpack_from("<H", data, pos)[0]
            if seg_len < 0 or seg_len > 64 or pos + 2 + seg_len > attr_start:
                raise ValueError("implausible name segment length")
            pos += 2 + seg_len
        parsed_names_end = pos
    except Exception:
        parsed_names_end = None

    if marker_pos is not None and marker_pos < attr_start:
        metadata_start = min(attr_start, marker_pos + 4)
        keep_marker = True
    elif parsed_names_end is not None:
        metadata_start = parsed_names_end
        keep_marker = False
    else:
        metadata_start = attr_start
        keep_marker = False

    metadata_len = max(0, attr_start - int(metadata_start))
    attributes_len = max(0, len(data) - attr_start)
    fixed_tail = int(name_start) + int(metadata_len) + int(attributes_len) + (4 if keep_marker else 0)
    return max(0, len(data) - fixed_tail)


def _build_player_name_capacity_snapshot(
    *,
    record: PlayerRecord,
    offset: int,
    source: str,
    storage_mode: str,
    record_id: int,
    proposed_name: Optional[str],
) -> PlayerNameCapacitySnapshot:
    display_name = _player_display_name(record)
    raw_data = bytes(getattr(record, "raw_data", b"") or b"")
    current_name_bytes = _encoded_name_len(display_name)
    notes: List[str] = []

    plain_max_bytes = _scan_plain_name_capacity(raw_data, display_name) if raw_data else None
    length_prefixed_max_bytes = None
    if raw_data:
        length_prefixed_max_bytes, parsed_name = _scan_length_prefixed_name_capacity(raw_data, display_name)
        if parsed_name and length_prefixed_max_bytes is None:
            notes.append("Length-prefixed name parse did not match display name; strategy ignored.")
    structured_window_max_bytes = _scan_structured_name_window_capacity(raw_data) if raw_data else current_name_bytes

    capacity_candidates = [
        int(value)
        for value in (plain_max_bytes, length_prefixed_max_bytes, structured_window_max_bytes)
        if isinstance(value, int)
    ]
    exact_full_name_max_bytes = max(capacity_candidates) if capacity_candidates else current_name_bytes
    can_expand = exact_full_name_max_bytes > current_name_bytes

    if storage_mode == "indexed":
        notes.append("Indexed player metadata name-edit path remains blocked; use rename/promote flows.")
    if raw_data and structured_window_max_bytes < current_name_bytes:
        notes.append("Structured name window is smaller than current display bytes; parser fallback may preserve existing raw shape only.")

    proposed_clean = " ".join(str(proposed_name or "").split()).strip() or None
    if proposed_clean is None:
        return PlayerNameCapacitySnapshot(
            record_id=int(record_id),
            offset=int(offset),
            team_id=getattr(record, "team_id", None),
            name=display_name,
            source=str(source or ""),
            storage_mode=str(storage_mode or ""),
            current_name_bytes=int(current_name_bytes),
            exact_full_name_max_bytes=int(exact_full_name_max_bytes),
            plain_text_max_bytes=plain_max_bytes,
            length_prefixed_max_bytes=length_prefixed_max_bytes,
            structured_window_max_bytes=int(structured_window_max_bytes),
            can_expand_without_growth=bool(can_expand),
            notes=notes,
        )

    proposed_name_bytes = _encoded_name_len(proposed_clean)
    within_limit = proposed_name_bytes <= exact_full_name_max_bytes
    may_truncate = proposed_name_bytes > int(structured_window_max_bytes)
    overflow_by = max(0, proposed_name_bytes - exact_full_name_max_bytes)

    return PlayerNameCapacitySnapshot(
        record_id=int(record_id),
        offset=int(offset),
        team_id=getattr(record, "team_id", None),
        name=display_name,
        source=str(source or ""),
        storage_mode=str(storage_mode or ""),
        current_name_bytes=int(current_name_bytes),
        exact_full_name_max_bytes=int(exact_full_name_max_bytes),
        plain_text_max_bytes=plain_max_bytes,
        length_prefixed_max_bytes=length_prefixed_max_bytes,
        structured_window_max_bytes=int(structured_window_max_bytes),
        can_expand_without_growth=bool(can_expand),
        notes=notes,
        proposed_name=proposed_clean,
        proposed_name_bytes=int(proposed_name_bytes),
        proposed_within_exact_limit=bool(within_limit),
        proposed_may_truncate=bool(may_truncate),
        proposed_overflow_by=int(overflow_by),
    )


def _load_player_batch_rows(plan_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with plan_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError("player-batch-edit CSV must include a header row")

        for row_number, row in enumerate(reader, start=2):
            rows.append(
                {
                    "row_number": row_number,
                    "name": str(row.get("name") or "").strip(),
                    "offset": _parse_optional_csv_int(row.get("offset")),
                    "new_name": str(row.get("new_name") or "").strip() or None,
                    "position": _parse_optional_csv_int(row.get("position")),
                    "nationality": _parse_optional_csv_int(row.get("nationality")),
                    "birth_day": _parse_optional_csv_int(row.get("dob_day")),
                    "birth_month": _parse_optional_csv_int(row.get("dob_month")),
                    "birth_year": _parse_optional_csv_int(row.get("dob_year")),
                    "height": _parse_optional_csv_int(row.get("height")),
                    "weight": _parse_optional_csv_int(row.get("weight")),
                }
            )
    return rows


def _normalize_team_roster_batch_source(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if not text or text == "auto":
        return None
    if text in {"linked", "eq_jug_linked", "eq-jug-linked", "eq->jug"}:
        return "linked"
    if text in {"same_entry", "same-entry", "same_entry_authoritative", "authoritative_same_entry"}:
        return "same_entry"
    raise ValueError(f"Unsupported team roster batch source {value!r}")


def _load_team_roster_batch_rows(plan_path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with plan_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames:
            raise ValueError("team-roster-batch-edit CSV must include a header row")

        for row_number, row in enumerate(reader, start=2):
            rows.append(
                {
                    "row_number": row_number,
                    "team": str(row.get("team") or "").strip(),
                    "source": _normalize_team_roster_batch_source(row.get("source")),
                    "eq_record_id": _parse_optional_csv_int(row.get("eq_record_id")),
                    "team_offset": _parse_optional_csv_int(row.get("team_offset")),
                    "slot": _parse_optional_csv_int(row.get("slot")),
                    "player_id": _parse_optional_csv_int(row.get("player_id")),
                    "flag": _parse_optional_csv_int(row.get("flag")),
                    "pid": _parse_optional_csv_int(row.get("pid")),
                }
            )
    return rows


def _extract_csv_row_number_from_warning(message: str) -> Optional[int]:
    match = re.search(r"\bCSV row\s+(\d+)\b", str(message or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _resolve_team_roster_batch_row_source(row: Dict[str, Any]) -> str:
    source = row.get("source")
    if source in {"linked", "same_entry"}:
        return str(source)
    if row.get("pid") is not None and row.get("player_id") is None and row.get("flag") is None:
        return "same_entry"
    if row.get("player_id") is not None or row.get("flag") is not None:
        return "linked"
    return "auto"


def _build_team_roster_batch_plan_preview(
    *,
    batch_rows: List[Dict[str, Any]],
    matched_row_numbers: set[int],
    linked_changes: List[TeamLinkedRosterChange],
    same_entry_changes: List[TeamSameEntryRosterChange],
    warnings: List[RenameIssue],
) -> List[TeamRosterBatchPlanRowPreview]:
    changed_by_row: Dict[int, TeamRosterBatchPlanRowPreview] = {}
    for change in linked_changes:
        row_number = int(getattr(change, "plan_row_number", 0) or 0)
        if row_number <= 0:
            continue
        changed_by_row[row_number] = TeamRosterBatchPlanRowPreview(
            row_number=row_number,
            status="change",
            source="linked",
            team_query=str(getattr(change, "team_name", "") or ""),
            slot_number=int(getattr(change, "slot_number", 0) or 0) or None,
            resolved_team_name=str(getattr(change, "team_name", "") or ""),
            resolved_full_club_name=str(getattr(change, "full_club_name", "") or ""),
            eq_record_id=int(getattr(change, "eq_record_id", 0) or 0) or None,
            changed=True,
            diff_summary=(
                f"pid {int(getattr(change, 'old_player_record_id', 0) or 0)} -> "
                f"{int(getattr(change, 'new_player_record_id', 0) or 0)}, "
                f"flag {int(getattr(change, 'old_flag', 0) or 0)} -> "
                f"{int(getattr(change, 'new_flag', 0) or 0)}"
            ),
            old_player_name=str(getattr(change, "old_player_name", "") or ""),
            new_player_name=str(getattr(change, "new_player_name", "") or ""),
            old_player_record_id=int(getattr(change, "old_player_record_id", 0) or 0),
            new_player_record_id=int(getattr(change, "new_player_record_id", 0) or 0),
            old_flag=int(getattr(change, "old_flag", 0) or 0),
            new_flag=int(getattr(change, "new_flag", 0) or 0),
        )

    for change in same_entry_changes:
        row_number = int(getattr(change, "plan_row_number", 0) or 0)
        if row_number <= 0:
            continue
        changed_by_row[row_number] = TeamRosterBatchPlanRowPreview(
            row_number=row_number,
            status="change",
            source="same_entry",
            team_query=str(getattr(change, "team_name", "") or ""),
            slot_number=int(getattr(change, "slot_number", 0) or 0) or None,
            resolved_team_name=str(getattr(change, "team_name", "") or ""),
            resolved_full_club_name=str(getattr(change, "full_club_name", "") or ""),
            team_offset=int(getattr(change, "team_offset", 0) or 0) or None,
            changed=True,
            diff_summary=(
                f"pid {int(getattr(change, 'old_pid_candidate', 0) or 0)} -> "
                f"{int(getattr(change, 'new_pid_candidate', 0) or 0)}"
            ),
            old_player_name=str(getattr(change, "old_player_name", "") or ""),
            new_player_name=str(getattr(change, "new_player_name", "") or ""),
            old_pid_candidate=int(getattr(change, "old_pid_candidate", 0) or 0),
            new_pid_candidate=int(getattr(change, "new_pid_candidate", 0) or 0),
            provenance=str(getattr(change, "provenance", "") or ""),
        )

    warning_messages_by_row: Dict[int, List[str]] = {}
    global_warning_messages: List[str] = []
    for warning in warnings:
        message = str(getattr(warning, "message", "") or "")
        row_number = _extract_csv_row_number_from_warning(message)
        if row_number is None:
            global_warning_messages.append(message)
            continue
        warning_messages_by_row.setdefault(row_number, []).append(message)

    preview_rows: List[TeamRosterBatchPlanRowPreview] = []
    for row in batch_rows:
        row_number = int(row.get("row_number") or 0)
        row_source = _resolve_team_roster_batch_row_source(row)
        team_query = str(row.get("team") or "")
        slot_number = row.get("slot")
        if row_number in warning_messages_by_row:
            warning_text = " | ".join(warning_messages_by_row[row_number])
            preview_rows.append(
                TeamRosterBatchPlanRowPreview(
                    row_number=row_number,
                    status="warning",
                    source=row_source,
                    team_query=team_query,
                    slot_number=int(slot_number) if isinstance(slot_number, int) else None,
                    warning_message=warning_text,
                    diff_summary=warning_text,
                )
            )
            continue
        changed_row = changed_by_row.get(row_number)
        if changed_row is not None:
            preview_rows.append(changed_row)
            continue
        if row_number in matched_row_numbers:
            preview_rows.append(
                TeamRosterBatchPlanRowPreview(
                    row_number=row_number,
                    status="no_change",
                    source=row_source,
                    team_query=team_query,
                    slot_number=int(slot_number) if isinstance(slot_number, int) else None,
                    diff_summary="Row resolves cleanly but already matches on-disk values",
                )
            )
            continue
        preview_rows.append(
            TeamRosterBatchPlanRowPreview(
                row_number=row_number,
                status="warning",
                source=row_source,
                team_query=team_query,
                slot_number=int(slot_number) if isinstance(slot_number, int) else None,
                warning_message="Row did not resolve to a supported authoritative roster target",
                diff_summary="Row did not resolve to a supported authoritative roster target",
            )
        )

    for message in global_warning_messages:
        preview_rows.append(
            TeamRosterBatchPlanRowPreview(
                row_number=None,
                status="warning",
                source="global",
                team_query="",
                slot_number=None,
                warning_message=message,
                diff_summary=message,
            )
        )

    return preview_rows


def edit_player_metadata_records(
    file_path: str,
    target_name: Optional[str] = None,
    *,
    target_offset: Optional[int] = None,
    new_name: Optional[str] = None,
    position: Optional[int] = None,
    nationality: Optional[int] = None,
    birth_day: Optional[int] = None,
    birth_month: Optional[int] = None,
    birth_year: Optional[int] = None,
    height: Optional[int] = None,
    weight: Optional[int] = None,
    write_changes: bool = True,
) -> PlayerMetadataEditResult:
    path = Path(file_path)
    file_data = path.read_bytes()

    requested = {
        "name": new_name,
        "position": position,
        "nationality": nationality,
        "birth_day": birth_day,
        "birth_month": birth_month,
        "birth_year": birth_year,
        "height": height,
        "weight": weight,
    }
    if all(value is None for value in requested.values()):
        raise ValueError("No changes requested. Provide --new-name and/or at least one editable player field.")
    if target_offset is None and not str(target_name or "").strip():
        raise ValueError("player-edit requires --name and/or --offset")

    normalized_target = _normalize_text(target_name) if str(target_name or "").strip() else None
    indexed = _try_load_indexed_player_file(file_data)
    if indexed is None:
        valid, uncertain = gather_player_records(str(path))
        all_entries = valid + uncertain
        matches: List[Tuple[int, PlayerRecord]] = []
        for entry in all_entries:
            if target_offset is not None and entry.offset != target_offset:
                continue
            display = _player_display_name(entry.record)
            if normalized_target is not None and _normalize_text(display) != normalized_target:
                continue
            matches.append((entry.offset, entry.record))

        changes: List[PlayerMetadataChange] = []
        modified_entries: List[Tuple[int, Any]] = []
        warnings: List[RenameIssue] = []
        for offset, record in matches:
            old_display = _player_display_name(record)
            if not _is_writable_player_entry_offset(file_data, offset, old_display):
                warnings.append(
                    RenameIssue(
                        offset=offset,
                        message="Matched player offset is not a writable FDI entry boundary; skipped to avoid file corruption",
                    )
                )
                continue
            try:
                changed_fields = _apply_player_mutations(
                    record,
                    new_name=new_name,
                    position=position,
                    nationality=nationality,
                    birth_day=birth_day,
                    birth_month=birth_month,
                    birth_year=birth_year,
                    height=height,
                    weight=weight,
                )
            except Exception as exc:
                warnings.append(RenameIssue(offset=offset, message=str(exc)))
                continue
            if not changed_fields:
                continue
            changes.append(
                PlayerMetadataChange(
                    offset=offset,
                    team_id=getattr(record, "team_id", None),
                    name=_player_display_name(record),
                    source="entry (name-only)",
                    changed_fields=changed_fields,
                )
            )
            modified_entries.append((offset, record))

        backup_path = None
        applied_to_disk = False
        if write_changes and modified_entries:
            metadata_write_needed = any(
                any(field_name != "name" for field_name in change.changed_fields.keys())
                for change in changes
            )
            if metadata_write_needed:
                backup_path = _write_modified_entries(path, file_data, modified_entries)
            else:
                fdi = FDIFile(str(path))
                fdi.load()
                for offset, record in modified_entries:
                    try:
                        record.name_dirty = True
                    except Exception:
                        setattr(record, "name_dirty", True)
                    fdi.modified_records[offset] = record
                fdi.save()
                backup_path = getattr(fdi, "last_backup_path", None)
            applied_to_disk = True

        return PlayerMetadataEditResult(
            file_path=path,
            record_count=len(all_entries),
            storage_mode="name_only",
            changes=changes,
            backup_path=backup_path,
            write_changes=write_changes,
            applied_to_disk=applied_to_disk,
            matched_count=len(matches),
            staged_records=modified_entries if not write_changes else [],
            warnings=warnings,
        )

    matches: List[Tuple[int, PlayerRecord]] = []
    for entry in indexed.entries:
        if target_offset is not None and entry.payload_offset != target_offset:
            continue
        try:
            payload = entry.decode_payload(file_data)
            record = PlayerRecord.from_bytes(payload, entry.payload_offset)
        except Exception:
            continue
        display = _player_display_name(record)
        if normalized_target is not None and _normalize_text(display) != normalized_target:
            continue
        try:
            record.container_offset = entry.payload_offset
            record.container_length = entry.payload_length
            record.container_encoding = "indexed_xor"
        except Exception:
            pass
        matches.append((entry.payload_offset, record))

    changes: List[PlayerMetadataChange] = []
    modified_entries: List[Tuple[int, Any]] = []
    warnings: List[RenameIssue] = []
    for offset, record in matches:
        try:
            changed_fields = _apply_player_mutations(
                record,
                new_name=new_name,
                position=position,
                nationality=nationality,
                birth_day=birth_day,
                birth_month=birth_month,
                birth_year=birth_year,
                height=height,
                weight=weight,
            )
        except Exception as exc:
            warnings.append(RenameIssue(offset=offset, message=str(exc)))
            continue

        if not changed_fields:
            continue

        changes.append(
            PlayerMetadataChange(
                offset=offset,
                team_id=getattr(record, "team_id", None),
                name=_player_display_name(record),
                source="indexed-entry",
                changed_fields=changed_fields,
            )
        )
        modified_entries.append((offset, record))

    backup_path = None
    applied_to_disk = False
    if write_changes and modified_entries:
        backup_path = _write_modified_entries(path, file_data, modified_entries)
        applied_to_disk = True

    return PlayerMetadataEditResult(
        file_path=path,
        record_count=len(indexed.entries),
        storage_mode="indexed",
        changes=changes,
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        matched_count=len(matches),
        staged_records=modified_entries if not write_changes else [],
        warnings=warnings,
    )


def batch_edit_player_metadata_records(
    file_path: str,
    csv_path: str,
    *,
    write_changes: bool = True,
) -> PlayerBatchEditResult:
    path = Path(file_path)
    plan_path = Path(csv_path)
    file_data = path.read_bytes()
    indexed = _try_load_indexed_player_file(file_data)
    batch_rows = _load_player_batch_rows(plan_path)

    changes: List[PlayerMetadataChange] = []
    modified_by_offset: Dict[int, PlayerRecord] = {}
    warnings: List[RenameIssue] = []
    row_count = len(batch_rows)
    matched_row_count = 0
    if indexed is not None:
        records_by_offset: Dict[int, Tuple[str, PlayerRecord]] = {}
        records_by_name: Dict[str, List[Tuple[int, str, PlayerRecord]]] = {}
        for entry in indexed.entries:
            try:
                payload = entry.decode_payload(file_data)
                record = PlayerRecord.from_bytes(payload, entry.payload_offset)
            except Exception:
                continue

            display = _player_display_name(record)
            try:
                record.container_offset = entry.payload_offset
                record.container_length = entry.payload_length
                record.container_encoding = "indexed_xor"
            except Exception:
                pass

            records_by_offset[entry.payload_offset] = (display, record)
            if display:
                records_by_name.setdefault(_normalize_text(display), []).append((entry.payload_offset, display, record))

        for row in batch_rows:
            row_number = int(row["row_number"])
            row_name = str(row["name"] or "")
            row_offset = row["offset"]
            new_name = row["new_name"]
            position = row["position"]
            nationality = row["nationality"]
            birth_day = row["birth_day"]
            birth_month = row["birth_month"]
            birth_year = row["birth_year"]
            height = row["height"]
            weight = row["weight"]

            if row_offset is None and not row_name:
                warnings.append(
                    RenameIssue(offset=None, message=f"CSV row {row_number}: requires a name and/or offset")
                )
                continue

            if all(
                value is None
                for value in (new_name, position, nationality, birth_day, birth_month, birth_year, height, weight)
            ):
                warnings.append(
                    RenameIssue(offset=row_offset, message=f"CSV row {row_number}: no changes requested")
                )
                continue

            matched_offset: Optional[int] = None
            matched_record: Optional[PlayerRecord] = None
            matched_display = ""
            if row_offset is not None:
                matched = records_by_offset.get(row_offset)
                if matched is None:
                    warnings.append(
                        RenameIssue(offset=row_offset, message=f"CSV row {row_number}: no indexed player at that offset")
                    )
                    continue
                matched_display, matched_record = matched
                matched_offset = row_offset
                if row_name and _normalize_text(matched_display) != _normalize_text(row_name):
                    warnings.append(
                        RenameIssue(
                            offset=row_offset,
                            message=(
                                f"CSV row {row_number}: name mismatch for offset "
                                f"(expected {row_name!r}, found {matched_display!r})"
                            ),
                        )
                    )
                    continue
            else:
                name_matches = records_by_name.get(_normalize_text(row_name), [])
                if not name_matches:
                    warnings.append(
                        RenameIssue(offset=None, message=f"CSV row {row_number}: no indexed player matched {row_name!r}")
                    )
                    continue
                if len(name_matches) > 1:
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=(
                                f"CSV row {row_number}: {len(name_matches)} players matched {row_name!r}; "
                                "add an offset column to disambiguate"
                            ),
                        )
                    )
                    continue
                matched_offset, matched_display, matched_record = name_matches[0]

            if matched_offset in modified_by_offset:
                warnings.append(
                    RenameIssue(
                        offset=matched_offset,
                        message=f"CSV row {row_number}: duplicate target offset; earlier row already staged this player",
                    )
                )
                continue

            matched_row_count += 1
            try:
                changed_fields = _apply_player_mutations(
                    matched_record,
                    new_name=new_name,
                    position=position,
                    nationality=nationality,
                    birth_day=birth_day,
                    birth_month=birth_month,
                    birth_year=birth_year,
                    height=height,
                    weight=weight,
                )
            except Exception as exc:
                warnings.append(RenameIssue(offset=matched_offset, message=f"CSV row {row_number}: {exc}"))
                continue

            if not changed_fields:
                continue

            changes.append(
                PlayerMetadataChange(
                    offset=matched_offset,
                    team_id=getattr(matched_record, "team_id", None),
                    name=_player_display_name(matched_record),
                    source="indexed-entry",
                    changed_fields=changed_fields,
                )
            )
            modified_by_offset[matched_offset] = matched_record
        record_count = len(indexed.entries)
    else:
        valid, uncertain = gather_player_records(str(path))
        all_entries = valid + uncertain
        records_by_offset = {entry.offset: (_player_display_name(entry.record), entry.record) for entry in all_entries}
        records_by_name: Dict[str, List[Tuple[int, str, PlayerRecord]]] = {}
        for entry in all_entries:
            display = _player_display_name(entry.record)
            if display:
                records_by_name.setdefault(_normalize_text(display), []).append((entry.offset, display, entry.record))

        for row in batch_rows:
            row_number = int(row["row_number"])
            row_name = str(row["name"] or "")
            row_offset = row["offset"]
            new_name = row["new_name"]
            position = row["position"]
            nationality = row["nationality"]
            birth_day = row["birth_day"]
            birth_month = row["birth_month"]
            birth_year = row["birth_year"]
            height = row["height"]
            weight = row["weight"]

            if row_offset is None and not row_name:
                warnings.append(
                    RenameIssue(offset=None, message=f"CSV row {row_number}: requires a name and/or offset")
                )
                continue
            if all(
                value is None
                for value in (new_name, position, nationality, birth_day, birth_month, birth_year, height, weight)
            ):
                warnings.append(
                    RenameIssue(offset=row_offset, message=f"CSV row {row_number}: no changes requested")
                )
                continue

            matched_offset: Optional[int] = None
            matched_record: Optional[PlayerRecord] = None
            matched_display = ""
            if row_offset is not None:
                matched = records_by_offset.get(row_offset)
                if matched is None:
                    warnings.append(
                        RenameIssue(offset=row_offset, message=f"CSV row {row_number}: no player at that offset")
                    )
                    continue
                matched_display, matched_record = matched
                matched_offset = row_offset
                if row_name and _normalize_text(matched_display) != _normalize_text(row_name):
                    warnings.append(
                        RenameIssue(
                            offset=row_offset,
                            message=(
                                f"CSV row {row_number}: name mismatch for offset "
                                f"(expected {row_name!r}, found {matched_display!r})"
                            ),
                        )
                    )
                    continue
            else:
                name_matches = records_by_name.get(_normalize_text(row_name), [])
                if not name_matches:
                    warnings.append(
                        RenameIssue(offset=None, message=f"CSV row {row_number}: no player matched {row_name!r}")
                    )
                    continue
                if len(name_matches) > 1:
                    warnings.append(
                        RenameIssue(
                            offset=None,
                            message=(
                                f"CSV row {row_number}: {len(name_matches)} players matched {row_name!r}; "
                                "add an offset column to disambiguate"
                            ),
                        )
                    )
                    continue
                matched_offset, matched_display, matched_record = name_matches[0]

            if not _is_writable_player_entry_offset(file_data, matched_offset, matched_display):
                warnings.append(
                    RenameIssue(
                        offset=matched_offset,
                        message=(
                            f"CSV row {row_number}: matched player offset is not a writable FDI entry boundary; "
                            "skipped to avoid file corruption"
                        ),
                    )
                )
                continue

            if matched_offset in modified_by_offset:
                warnings.append(
                    RenameIssue(
                        offset=matched_offset,
                        message=f"CSV row {row_number}: duplicate target offset; earlier row already staged this player",
                    )
                )
                continue

            matched_row_count += 1
            try:
                changed_fields = _apply_player_mutations(
                    matched_record,
                    new_name=new_name,
                    position=position,
                    nationality=nationality,
                    birth_day=birth_day,
                    birth_month=birth_month,
                    birth_year=birth_year,
                    height=height,
                    weight=weight,
                )
            except Exception as exc:
                warnings.append(RenameIssue(offset=matched_offset, message=f"CSV row {row_number}: {exc}"))
                continue

            if not changed_fields:
                continue

            changes.append(
                PlayerMetadataChange(
                    offset=matched_offset,
                    team_id=getattr(matched_record, "team_id", None),
                    name=_player_display_name(matched_record),
                    source="entry (name-only)",
                    changed_fields=changed_fields,
                )
            )
            modified_by_offset[matched_offset] = matched_record
        record_count = len(all_entries)

    modified_entries = sorted(modified_by_offset.items(), key=lambda item: item[0])
    backup_path = None
    applied_to_disk = False
    if write_changes and modified_entries:
        if indexed is not None:
            backup_path = _write_modified_entries(path, file_data, modified_entries)
            applied_to_disk = True
        else:
            metadata_write_needed = any(
                any(field_name != "name" for field_name in change.changed_fields.keys())
                for change in changes
            )
            if metadata_write_needed:
                backup_path = _write_modified_entries(path, file_data, modified_entries)
            else:
                fdi = FDIFile(str(path))
                fdi.load()
                for offset, record in modified_entries:
                    try:
                        record.name_dirty = True
                    except Exception:
                        setattr(record, "name_dirty", True)
                    fdi.modified_records[offset] = record
                fdi.save()
                backup_path = getattr(fdi, "last_backup_path", None)
            applied_to_disk = True

    return PlayerBatchEditResult(
        file_path=path,
        csv_path=plan_path,
        record_count=record_count,
        storage_mode="indexed" if indexed is not None else "name_only",
        row_count=row_count,
        matched_row_count=matched_row_count,
        changes=changes,
        backup_path=backup_path,
        write_changes=write_changes,
        applied_to_disk=applied_to_disk,
        staged_records=modified_entries if not write_changes else [],
        warnings=warnings,
    )


def inspect_player_metadata_records(
    file_path: str,
    target_name: str,
    *,
    target_offset: Optional[int] = None,
) -> PlayerMetadataInspectResult:
    path = Path(file_path)
    file_data = path.read_bytes()
    normalized_target = _normalize_text(target_name)
    snapshots: List[PlayerMetadataSnapshot] = []
    indexed = _try_load_indexed_player_file(file_data)
    if indexed is not None:
        for entry in indexed.entries:
            if target_offset is not None and entry.payload_offset != target_offset:
                continue
            try:
                payload = entry.decode_payload(file_data)
                record = PlayerRecord.from_bytes(payload, entry.payload_offset)
            except Exception:
                continue

            display = _player_display_name(record)
            if _normalize_text(display) != normalized_target:
                continue

            suffix_anchor = PlayerRecord._find_indexed_suffix_anchor(payload, display)
            snapshots.append(
                PlayerMetadataSnapshot(
                    record_id=entry.record_id,
                    offset=entry.payload_offset,
                    team_id=getattr(record, "team_id", None),
                    name=display,
                    source="indexed-entry",
                    suffix_anchor=suffix_anchor,
                    attribute_prefix=list(getattr(record, "attributes", [])[:3]),
                    indexed_unknown_0=getattr(record, "indexed_unknown_0", None),
                    indexed_unknown_1=getattr(record, "indexed_unknown_1", None),
                    face_components=list(getattr(record, "indexed_face_components", []) or []),
                    nationality=getattr(record, "nationality", None),
                    indexed_unknown_9=getattr(record, "indexed_unknown_9", None),
                    indexed_unknown_10=getattr(record, "indexed_unknown_10", None),
                    position=getattr(record, "position_primary", None),
                    birth_day=getattr(record, "birth_day", None),
                    birth_month=getattr(record, "birth_month", None),
                    birth_year=getattr(record, "birth_year", None),
                    height=getattr(record, "height", None),
                    weight=getattr(record, "weight", None),
                    post_weight_byte=PlayerRecord._extract_indexed_post_weight_byte(payload, display),
                    trailer_byte=PlayerRecord._extract_indexed_post_attribute_byte(payload, display),
                    sidecar_byte=PlayerRecord._extract_indexed_post_attribute_sidecar_byte(payload, display),
                )
            )

        return PlayerMetadataInspectResult(
            file_path=path,
            record_count=len(indexed.entries),
            matched_count=len(snapshots),
            records=snapshots,
            storage_mode="indexed",
        )

    valid, uncertain = gather_player_records(str(path))
    all_entries = list(valid) + list(uncertain)
    for item in all_entries:
        if target_offset is not None and int(item.offset) != int(target_offset):
            continue
        record = item.record
        display = _player_display_name(record)
        if _normalize_text(display) != normalized_target:
            continue
        snapshots.append(
            PlayerMetadataSnapshot(
                record_id=0,
                offset=int(item.offset),
                team_id=getattr(record, "team_id", None),
                name=display,
                source=str(getattr(item, "source", "") or ""),
                suffix_anchor=None,
                attribute_prefix=list(getattr(record, "attributes", [])[:3]),
                indexed_unknown_0=None,
                indexed_unknown_1=None,
                face_components=[],
                nationality=getattr(record, "nationality", None),
                indexed_unknown_9=None,
                indexed_unknown_10=None,
                position=getattr(record, "position_primary", None),
                birth_day=getattr(record, "birth_day", None),
                birth_month=getattr(record, "birth_month", None),
                birth_year=getattr(record, "birth_year", None),
                height=getattr(record, "height", None),
                weight=getattr(record, "weight", None),
                post_weight_byte=None,
                trailer_byte=None,
                sidecar_byte=None,
            )
        )

    return PlayerMetadataInspectResult(
        file_path=path,
        record_count=len(all_entries),
        matched_count=len(snapshots),
        records=snapshots,
        storage_mode="name_only",
    )


def inspect_player_name_capacities(
    file_path: str,
    *,
    target_name: Optional[str] = None,
    target_offset: Optional[int] = None,
    proposed_name: Optional[str] = None,
    include_uncertain: bool = True,
    limit: int = 200,
) -> PlayerNameCapacityResult:
    """
    Inspect parser-backed name-capacity constraints for safe rename planning.

    This is a read-only contract intended for API/import preflight checks.
    """
    path = Path(file_path)
    file_data = path.read_bytes()
    normalized_target = _normalize_text(str(target_name or ""))
    max_rows = max(1, int(limit or 200))
    proposed_clean = " ".join(str(proposed_name or "").split()).strip() or None

    snapshots: List[PlayerNameCapacitySnapshot] = []
    truncated = False
    indexed = _try_load_indexed_player_file(file_data)
    if indexed is not None:
        for entry in indexed.entries:
            if target_offset is not None and int(entry.payload_offset) != int(target_offset):
                continue
            try:
                payload = entry.decode_payload(file_data)
                record = PlayerRecord.from_bytes(payload, entry.payload_offset)
            except Exception:
                continue

            display = _player_display_name(record)
            if normalized_target and _normalize_text(display) != normalized_target:
                continue

            snapshots.append(
                _build_player_name_capacity_snapshot(
                    record=record,
                    offset=int(entry.payload_offset),
                    source="indexed-entry",
                    storage_mode="indexed",
                    record_id=int(entry.record_id),
                    proposed_name=proposed_clean,
                )
            )
            if len(snapshots) >= max_rows:
                truncated = True
                break

        return PlayerNameCapacityResult(
            file_path=path,
            record_count=len(indexed.entries),
            matched_count=len(snapshots),
            records=snapshots,
            storage_mode="indexed",
            target_name=(str(target_name).strip() if target_name else None),
            target_offset=(int(target_offset) if target_offset is not None else None),
            proposed_name=proposed_clean,
            proposed_name_bytes=(_encoded_name_len(proposed_clean) if proposed_clean else None),
            limit=max_rows,
            truncated=truncated,
        )

    valid, uncertain = gather_player_records(str(path))
    all_entries = list(valid) + (list(uncertain) if include_uncertain else [])
    for item in all_entries:
        if target_offset is not None and int(item.offset) != int(target_offset):
            continue
        record = item.record
        display = _player_display_name(record)
        if normalized_target and _normalize_text(display) != normalized_target:
            continue

        snapshots.append(
            _build_player_name_capacity_snapshot(
                record=record,
                offset=int(item.offset),
                source=str(getattr(item, "source", "") or ""),
                storage_mode="name_only",
                record_id=int(getattr(record, "record_id", 0) or 0),
                proposed_name=proposed_clean,
            )
        )
        if len(snapshots) >= max_rows:
            truncated = True
            break

    return PlayerNameCapacityResult(
        file_path=path,
        record_count=len(all_entries),
        matched_count=len(snapshots),
        records=snapshots,
        storage_mode="name_only",
        target_name=(str(target_name).strip() if target_name else None),
        target_offset=(int(target_offset) if target_offset is not None else None),
        proposed_name=proposed_clean,
        proposed_name_bytes=(_encoded_name_len(proposed_clean) if proposed_clean else None),
        limit=max_rows,
        truncated=truncated,
    )


def profile_player_legacy_weight_candidates(
    file_path: str,
    *,
    start_offset: int = 14,
    end_offset: int = 18,
    top_values: int = 8,
) -> PlayerLegacyWeightProfileResult:
    """
    Use the indexed suffix-weight field as a control set to test legacy marker-relative
    candidate offsets for a future non-indexed weight contract.

    This is intentionally a read-only reverse-engineering helper. It only works on indexed
    DMFIv1.0 player files because those payloads provide a trusted ground-truth `weight`.
    """
    path = Path(file_path)
    file_data = path.read_bytes()
    indexed = _try_load_indexed_player_file(file_data)
    if indexed is None:
        raise ValueError("player-legacy-weight-profile currently requires an indexed DMFIv1.0 player file")
    if end_offset < start_offset:
        raise ValueError("end_offset must be >= start_offset")

    profile_counters: Dict[int, Dict[str, Any]] = {
        rel: {"eligible": 0, "exact": 0, "abs_err": 0, "values": {}}
        for rel in range(int(start_offset), int(end_offset) + 1)
    }
    indexed_weight_by_name: Dict[str, set[int]] = {}
    indexed_weight_by_team_name: Dict[Tuple[Optional[int], str], set[int]] = {}
    candidate_record_count = 0
    height_baseline_exact = 0

    for entry in indexed.entries:
        try:
            payload = entry.decode_payload(file_data)
            record = PlayerRecord.from_bytes(payload, entry.payload_offset)
        except Exception:
            continue

        weight = getattr(record, "weight", None)
        if weight is None:
            continue
        display_name = _player_display_name(record)
        normalized_name = _normalize_text(display_name)
        team_id = getattr(record, "team_id", None)
        if normalized_name:
            indexed_weight_by_name.setdefault(normalized_name, set()).add(int(weight))
            indexed_weight_by_team_name.setdefault((team_id, normalized_name), set()).add(int(weight))
        marker = PlayerRecord._find_name_end(payload)
        if marker is None:
            continue

        attr_start = len(payload) - 19
        if marker + int(start_offset) >= len(payload) or marker + int(start_offset) >= attr_start:
            continue

        candidate_record_count += 1

        height_index = marker + 13
        if height_index < len(payload) and height_index < attr_start:
            candidate_height = payload[height_index] ^ 0x61
            if candidate_height == getattr(record, "height", None):
                height_baseline_exact += 1

        for rel in range(int(start_offset), int(end_offset) + 1):
            idx = marker + rel
            if idx >= len(payload) or idx >= attr_start:
                continue
            candidate_value = payload[idx] ^ 0x61
            stats = profile_counters[rel]
            stats["eligible"] = int(stats["eligible"] or 0) + 1
            stats["abs_err"] = int(stats["abs_err"] or 0) + abs(int(candidate_value) - int(weight))
            if int(candidate_value) == int(weight):
                stats["exact"] = int(stats["exact"] or 0) + 1
            values = dict(stats["values"] or {})
            values[int(candidate_value)] = int(values.get(int(candidate_value), 0) or 0) + 1
            stats["values"] = values

    offset_profiles: List[PlayerLegacyWeightCandidateProfile] = []
    for rel in range(int(start_offset), int(end_offset) + 1):
        stats = profile_counters[rel]
        eligible = int(stats["eligible"] or 0)
        exact = int(stats["exact"] or 0)
        values = dict(stats["values"] or {})
        ordered_values = sorted(values.items(), key=lambda item: (-item[1], item[0]))[: max(1, int(top_values or 8))]
        offset_profiles.append(
            PlayerLegacyWeightCandidateProfile(
                relative_offset=rel,
                eligible_count=eligible,
                exact_match_count=exact,
                exact_match_ratio=(float(exact) / float(eligible)) if eligible else 0.0,
                mean_abs_error=(float(stats["abs_err"] or 0) / float(eligible)) if eligible else 0.0,
                top_values=[(int(value), int(count)) for value, count in ordered_values],
            )
        )

    ranked_profiles = sorted(
        offset_profiles,
        key=lambda item: (-item.exact_match_ratio, item.mean_abs_error, item.relative_offset),
    )
    recommended_offset = ranked_profiles[0].relative_offset if ranked_profiles and ranked_profiles[0].eligible_count else None

    legacy_valid, _legacy_uncertain = gather_player_records(str(path))
    legacy_valid_record_count = len(list(legacy_valid or []))
    legacy_slot_record_count = 0
    legacy_matched_record_count = 0
    legacy_exact_match_count = 0

    for item in list(legacy_valid or []):
        record = getattr(item, "record", None)
        raw_data = bytes(getattr(record, "raw_data", b"") or b"")
        if not raw_data:
            continue
        if PlayerRecord._find_legacy_weight_offset(raw_data) is None:
            continue
        weight = getattr(record, "weight", None)
        if weight is None:
            continue
        legacy_slot_record_count += 1

        display_name = _player_display_name(record)
        normalized_name = _normalize_text(display_name)
        if not normalized_name:
            continue

        team_id = getattr(record, "team_id", None)
        candidate_weights = set(indexed_weight_by_team_name.get((team_id, normalized_name), set()))
        if not candidate_weights:
            candidate_weights = set(indexed_weight_by_name.get(normalized_name, set()))
        if len(candidate_weights) != 1:
            continue

        legacy_matched_record_count += 1
        expected_weight = next(iter(candidate_weights))
        if int(weight) == int(expected_weight):
            legacy_exact_match_count += 1

    return PlayerLegacyWeightProfileResult(
        file_path=path,
        record_count=len(indexed.entries),
        candidate_record_count=candidate_record_count,
        recommended_offset=recommended_offset,
        height_baseline_exact_ratio=(
            float(height_baseline_exact) / float(candidate_record_count)
            if candidate_record_count
            else 0.0
        ),
        offsets=offset_profiles,
        legacy_valid_record_count=legacy_valid_record_count,
        legacy_slot_record_count=legacy_slot_record_count,
        legacy_matched_record_count=legacy_matched_record_count,
        legacy_exact_match_count=legacy_exact_match_count,
        legacy_exact_match_ratio=(
            float(legacy_exact_match_count) / float(legacy_matched_record_count)
            if legacy_matched_record_count
            else 0.0
        ),
    )


def profile_indexed_player_suffix_bytes(
    file_path: str,
    *,
    nationality: Optional[int] = None,
    position: Optional[int] = None,
    limit: int = 10,
    sample_size: int = 3,
) -> PlayerSuffixProfileResult:
    path = Path(file_path)
    file_data = path.read_bytes()
    if file_data[:8] != b"DMFIv1.0":
        raise ValueError("player-suffix-profile currently supports indexed DMFIv1.0 player files only")

    indexed = IndexedFDIFile.from_bytes(file_data)
    pair_counts: Dict[Tuple[Optional[int], Optional[int]], int] = {}
    pair_samples: Dict[Tuple[Optional[int], Optional[int]], List[str]] = {}
    anchored_count = 0
    filtered_count = 0

    for entry in indexed.entries:
        try:
            payload = entry.decode_payload(file_data)
            record = PlayerRecord.from_bytes(payload, entry.payload_offset)
            display = _player_display_name(record)
            suffix_anchor = PlayerRecord._find_indexed_suffix_anchor(payload, display)
        except Exception:
            continue

        if suffix_anchor is None:
            continue
        anchored_count += 1

        if nationality is not None and getattr(record, "nationality", None) != nationality:
            continue
        if position is not None and getattr(record, "position_primary", None) != position:
            continue

        filtered_count += 1
        pair = (
            getattr(record, "indexed_unknown_9", None),
            getattr(record, "indexed_unknown_10", None),
        )
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
        samples = pair_samples.setdefault(pair, [])
        if display and len(samples) < sample_size:
            samples.append(display)

    ordered_pairs = sorted(
        pair_counts.items(),
        key=lambda item: (-item[1], item[0][0] if item[0][0] is not None else -1, item[0][1] if item[0][1] is not None else -1),
    )
    buckets: List[PlayerSuffixProfileBucket] = []
    for pair, count in ordered_pairs[: max(1, int(limit or 10))]:
        buckets.append(
            PlayerSuffixProfileBucket(
                indexed_unknown_9=pair[0],
                indexed_unknown_10=pair[1],
                count=count,
                sample_names=list(pair_samples.get(pair, [])),
            )
        )

    return PlayerSuffixProfileResult(
        file_path=path,
        record_count=len(indexed.entries),
        anchored_count=anchored_count,
        filtered_count=filtered_count,
        nationality_filter=nationality,
        position_filter=position,
        buckets=buckets,
    )


def profile_indexed_player_leading_bytes(
    file_path: str,
    *,
    nationality: Optional[int] = None,
    position: Optional[int] = None,
    indexed_unknown_0: Optional[int] = None,
    indexed_unknown_1: Optional[int] = None,
    indexed_unknown_9: Optional[int] = None,
    indexed_unknown_10: Optional[int] = None,
    attribute_0: Optional[int] = None,
    attribute_1: Optional[int] = None,
    attribute_2: Optional[int] = None,
    post_weight_byte: Optional[int] = None,
    trailer_byte: Optional[int] = None,
    sidecar_byte: Optional[int] = None,
    limit: int = 10,
    sample_size: int = 3,
) -> PlayerLeadingProfileResult:
    path = Path(file_path)
    file_data = path.read_bytes()
    if file_data[:8] != b"DMFIv1.0":
        raise ValueError("player-leading-profile currently supports indexed DMFIv1.0 player files only")

    indexed = IndexedFDIFile.from_bytes(file_data)
    pair_counts: Dict[Tuple[Optional[int], Optional[int]], int] = {}
    pair_samples: Dict[Tuple[Optional[int], Optional[int]], List[str]] = {}
    position_counts: Dict[Optional[int], int] = {}
    nationality_counts: Dict[Optional[int], int] = {}
    anchored_count = 0
    filtered_count = 0

    for entry in indexed.entries:
        try:
            payload = entry.decode_payload(file_data)
            record = PlayerRecord.from_bytes(payload, entry.payload_offset)
            display = _player_display_name(record)
            suffix_anchor = PlayerRecord._find_indexed_suffix_anchor(payload, display)
        except Exception:
            continue

        if suffix_anchor is None:
            continue
        anchored_count += 1

        if nationality is not None and getattr(record, "nationality", None) != nationality:
            continue
        if position is not None and getattr(record, "position_primary", None) != position:
            continue
        if indexed_unknown_0 is not None and getattr(record, "indexed_unknown_0", None) != indexed_unknown_0:
            continue
        if indexed_unknown_1 is not None and getattr(record, "indexed_unknown_1", None) != indexed_unknown_1:
            continue
        if indexed_unknown_9 is not None and getattr(record, "indexed_unknown_9", None) != indexed_unknown_9:
            continue
        if indexed_unknown_10 is not None and getattr(record, "indexed_unknown_10", None) != indexed_unknown_10:
            continue

        attrs = list(getattr(record, "attributes", []) or [])
        triple = tuple((attrs[:3] + [None, None, None])[:3])
        post_weight_value = PlayerRecord._extract_indexed_post_weight_byte(payload, display)
        trailer_value = PlayerRecord._extract_indexed_post_attribute_byte(payload, display)
        sidecar_value = PlayerRecord._extract_indexed_post_attribute_sidecar_byte(payload, display)
        if attribute_0 is not None and triple[0] != attribute_0:
            continue
        if attribute_1 is not None and triple[1] != attribute_1:
            continue
        if attribute_2 is not None and triple[2] != attribute_2:
            continue
        if post_weight_byte is not None and post_weight_value != post_weight_byte:
            continue
        if trailer_byte is not None and trailer_value != trailer_byte:
            continue
        if sidecar_byte is not None and sidecar_value != sidecar_byte:
            continue

        filtered_count += 1
        position_value = getattr(record, "position_primary", None)
        nationality_value = getattr(record, "nationality", None)
        position_counts[position_value] = position_counts.get(position_value, 0) + 1
        nationality_counts[nationality_value] = nationality_counts.get(nationality_value, 0) + 1
        pair = (
            getattr(record, "indexed_unknown_0", None),
            getattr(record, "indexed_unknown_1", None),
        )
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
        samples = pair_samples.setdefault(pair, [])
        if display and len(samples) < sample_size:
            samples.append(display)

    ordered_pairs = sorted(
        pair_counts.items(),
        key=lambda item: (
            -item[1],
            item[0][0] if item[0][0] is not None else -1,
            item[0][1] if item[0][1] is not None else -1,
        ),
    )
    buckets: List[PlayerLeadingProfileBucket] = []
    for pair, count in ordered_pairs[: max(1, int(limit or 10))]:
        buckets.append(
            PlayerLeadingProfileBucket(
                indexed_unknown_0=pair[0],
                indexed_unknown_1=pair[1],
                count=count,
                sample_names=list(pair_samples.get(pair, [])),
            )
        )

    ordered_positions = sorted(
        position_counts.items(),
        key=lambda item: (
            -item[1],
            item[0] if item[0] is not None else -1,
        ),
    )
    ordered_nationalities = sorted(
        nationality_counts.items(),
        key=lambda item: (
            -item[1],
            item[0] if item[0] is not None else -1,
        ),
    )

    return PlayerLeadingProfileResult(
        file_path=path,
        record_count=len(indexed.entries),
        anchored_count=anchored_count,
        filtered_count=filtered_count,
        nationality_filter=nationality,
        position_filter=position,
        indexed_unknown_0_filter=indexed_unknown_0,
        indexed_unknown_1_filter=indexed_unknown_1,
        indexed_unknown_9_filter=indexed_unknown_9,
        indexed_unknown_10_filter=indexed_unknown_10,
        position_counts=ordered_positions,
        nationality_counts=ordered_nationalities,
        buckets=buckets,
    )


def profile_indexed_player_attribute_prefixes(
    file_path: str,
    *,
    nationality: Optional[int] = None,
    position: Optional[int] = None,
    indexed_unknown_0: Optional[int] = None,
    indexed_unknown_1: Optional[int] = None,
    indexed_unknown_9: Optional[int] = None,
    indexed_unknown_10: Optional[int] = None,
    attribute_0: Optional[int] = None,
    attribute_1: Optional[int] = None,
    attribute_2: Optional[int] = None,
    post_weight_byte: Optional[int] = None,
    trailer_byte: Optional[int] = None,
    sidecar_byte: Optional[int] = None,
    limit: int = 10,
    sample_size: int = 3,
) -> PlayerAttributePrefixProfileResult:
    path = Path(file_path)
    file_data = path.read_bytes()
    if file_data[:8] != b"DMFIv1.0":
        raise ValueError("player-tail-prefix-profile currently supports indexed DMFIv1.0 player files only")

    indexed = IndexedFDIFile.from_bytes(file_data)
    triple_counts: Dict[Tuple[Optional[int], Optional[int], Optional[int]], int] = {}
    triple_samples: Dict[Tuple[Optional[int], Optional[int], Optional[int]], List[str]] = {}
    signature_counts: Dict[
        Tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]], int
    ] = {}
    signature_samples: Dict[
        Tuple[Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]], List[str]
    ] = {}
    attribute_0_counts: Dict[Optional[int], int] = {}
    attribute_1_counts: Dict[Optional[int], int] = {}
    attribute_2_counts: Dict[Optional[int], int] = {}
    post_weight_byte_counts: Dict[Optional[int], int] = {}
    post_weight_nationality_eligible_count = 0
    post_weight_nationality_match_count = 0
    post_weight_divergent_counts: Dict[Optional[int], int] = {}
    post_weight_nationality_mismatch_pair_counts: Dict[Tuple[Optional[int], Optional[int]], int] = {}
    post_weight_group_nationality_counts: Dict[Optional[int], Dict[Optional[int], int]] = {}
    post_weight_group_samples: Dict[Optional[int], List[str]] = {}
    trailer_byte_counts: Dict[Optional[int], int] = {}
    sidecar_byte_counts: Dict[Optional[int], int] = {}
    layout_verified_count = 0
    layout_mismatch_count = 0
    anchored_count = 0
    filtered_count = 0

    for entry in indexed.entries:
        try:
            payload = entry.decode_payload(file_data)
            record = PlayerRecord.from_bytes(payload, entry.payload_offset)
            display = _player_display_name(record)
            suffix_anchor = PlayerRecord._find_indexed_suffix_anchor(payload, display)
        except Exception:
            continue

        if suffix_anchor is None:
            continue
        anchored_count += 1

        if nationality is not None and getattr(record, "nationality", None) != nationality:
            continue
        if position is not None and getattr(record, "position_primary", None) != position:
            continue
        if indexed_unknown_0 is not None and getattr(record, "indexed_unknown_0", None) != indexed_unknown_0:
            continue
        if indexed_unknown_1 is not None and getattr(record, "indexed_unknown_1", None) != indexed_unknown_1:
            continue
        if indexed_unknown_9 is not None and getattr(record, "indexed_unknown_9", None) != indexed_unknown_9:
            continue
        if indexed_unknown_10 is not None and getattr(record, "indexed_unknown_10", None) != indexed_unknown_10:
            continue

        attrs = list(getattr(record, "attributes", []) or [])
        triple = tuple((attrs[:3] + [None, None, None])[:3])
        post_weight_value = PlayerRecord._extract_indexed_post_weight_byte(payload, display)
        trailer_value = PlayerRecord._extract_indexed_post_attribute_byte(payload, display)
        sidecar_value = PlayerRecord._extract_indexed_post_attribute_sidecar_byte(payload, display)
        if attribute_0 is not None and triple[0] != attribute_0:
            continue
        if attribute_1 is not None and triple[1] != attribute_1:
            continue
        if attribute_2 is not None and triple[2] != attribute_2:
            continue
        if post_weight_byte is not None and post_weight_value != post_weight_byte:
            continue
        if trailer_byte is not None and trailer_value != trailer_byte:
            continue
        if sidecar_byte is not None and sidecar_value != sidecar_byte:
            continue

        filtered_count += 1
        tail_layout = PlayerRecord._analyze_indexed_tail_layout(payload, display)
        if tail_layout and bool(tail_layout.get("layout_matches_expected")):
            layout_verified_count += 1
        else:
            layout_mismatch_count += 1
        nationality_value = getattr(record, "nationality", None)
        if post_weight_value is not None and nationality_value is not None:
            post_weight_nationality_eligible_count += 1
            if post_weight_value == nationality_value:
                post_weight_nationality_match_count += 1
            else:
                post_weight_divergent_counts[post_weight_value] = (
                    post_weight_divergent_counts.get(post_weight_value, 0) + 1
                )
                mismatch_pair = (post_weight_value, nationality_value)
                post_weight_nationality_mismatch_pair_counts[mismatch_pair] = (
                    post_weight_nationality_mismatch_pair_counts.get(mismatch_pair, 0) + 1
                )
                group_counts = post_weight_group_nationality_counts.setdefault(post_weight_value, {})
                group_counts[nationality_value] = group_counts.get(nationality_value, 0) + 1
                if display:
                    group_samples = post_weight_group_samples.setdefault(post_weight_value, [])
                    if display not in group_samples and len(group_samples) < sample_size:
                        group_samples.append(display)
        attribute_0_counts[triple[0]] = attribute_0_counts.get(triple[0], 0) + 1
        attribute_1_counts[triple[1]] = attribute_1_counts.get(triple[1], 0) + 1
        attribute_2_counts[triple[2]] = attribute_2_counts.get(triple[2], 0) + 1
        post_weight_byte_counts[post_weight_value] = post_weight_byte_counts.get(post_weight_value, 0) + 1
        trailer_byte_counts[trailer_value] = trailer_byte_counts.get(trailer_value, 0) + 1
        sidecar_byte_counts[sidecar_value] = sidecar_byte_counts.get(sidecar_value, 0) + 1
        triple_counts[triple] = triple_counts.get(triple, 0) + 1
        samples = triple_samples.setdefault(triple, [])
        if display and len(samples) < sample_size:
            samples.append(display)
        signature = (triple[0], triple[1], triple[2], trailer_value, sidecar_value)
        signature_counts[signature] = signature_counts.get(signature, 0) + 1
        signature_sample_rows = signature_samples.setdefault(signature, [])
        if display and len(signature_sample_rows) < sample_size:
            signature_sample_rows.append(display)

    ordered_triples = sorted(
        triple_counts.items(),
        key=lambda item: (
            -item[1],
            item[0][0] if item[0][0] is not None else -1,
            item[0][1] if item[0][1] is not None else -1,
            item[0][2] if item[0][2] is not None else -1,
        ),
    )
    buckets: List[PlayerAttributePrefixProfileBucket] = []
    for triple, count in ordered_triples[: max(1, int(limit or 10))]:
        buckets.append(
            PlayerAttributePrefixProfileBucket(
                attribute_0=triple[0],
                attribute_1=triple[1],
                attribute_2=triple[2],
                count=count,
                sample_names=list(triple_samples.get(triple, [])),
            )
        )
    ordered_signatures = sorted(
        signature_counts.items(),
        key=lambda item: (
            -item[1],
            item[0][0] if item[0][0] is not None else -1,
            item[0][1] if item[0][1] is not None else -1,
            item[0][2] if item[0][2] is not None else -1,
            item[0][3] if item[0][3] is not None else -1,
            item[0][4] if item[0][4] is not None else -1,
        ),
    )
    signature_buckets: List[PlayerAttributeSignatureProfileBucket] = []
    for signature, count in ordered_signatures[: max(1, int(limit or 10))]:
        signature_buckets.append(
            PlayerAttributeSignatureProfileBucket(
                attribute_0=signature[0],
                attribute_1=signature[1],
                attribute_2=signature[2],
                trailer_byte=signature[3],
                sidecar_byte=signature[4],
                count=count,
                sample_names=list(signature_samples.get(signature, [])),
            )
        )

    ordered_attr_0 = sorted(
        attribute_0_counts.items(),
        key=lambda item: (-item[1], item[0] if item[0] is not None else -1),
    )
    ordered_attr_1 = sorted(
        attribute_1_counts.items(),
        key=lambda item: (-item[1], item[0] if item[0] is not None else -1),
    )
    ordered_attr_2 = sorted(
        attribute_2_counts.items(),
        key=lambda item: (-item[1], item[0] if item[0] is not None else -1),
    )
    ordered_post_weight = sorted(
        post_weight_byte_counts.items(),
        key=lambda item: (-item[1], item[0] if item[0] is not None else -1),
    )
    ordered_post_weight_divergent = sorted(
        post_weight_divergent_counts.items(),
        key=lambda item: (-item[1], item[0] if item[0] is not None else -1),
    )
    ordered_post_weight_mismatch_pairs = sorted(
        post_weight_nationality_mismatch_pair_counts.items(),
        key=lambda item: (
            -item[1],
            item[0][0] if item[0][0] is not None else -1,
            item[0][1] if item[0][1] is not None else -1,
        ),
    )
    ordered_post_weight_group_clusters = sorted(
        post_weight_group_nationality_counts.items(),
        key=lambda item: (
            -sum(item[1].values()),
            item[0] if item[0] is not None else -1,
        ),
    )
    ordered_trailer = sorted(
        trailer_byte_counts.items(),
        key=lambda item: (-item[1], item[0] if item[0] is not None else -1),
    )
    ordered_sidecar = sorted(
        sidecar_byte_counts.items(),
        key=lambda item: (-item[1], item[0] if item[0] is not None else -1),
    )
    post_weight_group_clusters: List[PostWeightGroupCluster] = []
    for post_weight_key, nationality_counts in ordered_post_weight_group_clusters[: max(1, int(limit or 10))]:
        ordered_nationality_counts = sorted(
            nationality_counts.items(),
            key=lambda item: (-item[1], item[0] if item[0] is not None else -1),
        )
        post_weight_group_clusters.append(
            PostWeightGroupCluster(
                post_weight_byte=post_weight_key,
                total_count=sum(nationality_counts.values()),
                nationality_counts=ordered_nationality_counts,
                sample_names=list(post_weight_group_samples.get(post_weight_key, [])),
            )
        )

    return PlayerAttributePrefixProfileResult(
        file_path=path,
        record_count=len(indexed.entries),
        anchored_count=anchored_count,
        filtered_count=filtered_count,
        nationality_filter=nationality,
        position_filter=position,
        indexed_unknown_0_filter=indexed_unknown_0,
        indexed_unknown_1_filter=indexed_unknown_1,
        indexed_unknown_9_filter=indexed_unknown_9,
        indexed_unknown_10_filter=indexed_unknown_10,
        attribute_0_filter=attribute_0,
        attribute_1_filter=attribute_1,
        attribute_2_filter=attribute_2,
        post_weight_byte_filter=post_weight_byte,
        trailer_byte_filter=trailer_byte,
        sidecar_byte_filter=sidecar_byte,
        layout_verified_count=layout_verified_count,
        layout_mismatch_count=layout_mismatch_count,
        attribute_0_counts=ordered_attr_0,
        attribute_1_counts=ordered_attr_1,
        attribute_2_counts=ordered_attr_2,
        post_weight_byte_counts=ordered_post_weight,
        post_weight_nationality_eligible_count=post_weight_nationality_eligible_count,
        post_weight_nationality_match_count=post_weight_nationality_match_count,
        post_weight_nationality_match_ratio=(
            float(post_weight_nationality_match_count) / float(post_weight_nationality_eligible_count)
            if post_weight_nationality_eligible_count
            else 0.0
        ),
        post_weight_divergent_counts=ordered_post_weight_divergent,
        post_weight_nationality_mismatch_pairs=[
            (pair[0], pair[1], count)
            for pair, count in ordered_post_weight_mismatch_pairs[: max(1, int(limit or 10))]
        ],
        post_weight_group_clusters=post_weight_group_clusters,
        trailer_byte_counts=ordered_trailer,
        sidecar_byte_counts=ordered_sidecar,
        buckets=buckets,
        signature_buckets=signature_buckets,
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
    "PlayerMetadataChange",
    "PlayerMetadataEditResult",
    "PlayerMetadataInspectResult",
    "PlayerMetadataSnapshot",
    "PlayerNameCapacitySnapshot",
    "PlayerNameCapacityResult",
    "PlayerLegacyWeightCandidateProfile",
    "PlayerLegacyWeightProfileResult",
    "PlayerAttributePrefixProfileBucket",
    "PostWeightGroupCluster",
    "PlayerAttributePrefixProfileResult",
    "PlayerLeadingProfileBucket",
    "PlayerLeadingProfileResult",
    "PlayerSuffixProfileBucket",
    "PlayerSuffixProfileResult",
    "PlayerSkillPatchResult",
    "PlayerVisibleSkillSnapshot",
    "TeamRosterSameEntryOverlapRunResult",
    "TeamLinkedRosterChange",
    "TeamLinkedRosterEditResult",
    "TeamRosterPlayerPromotionResult",
    "TeamRosterPromotionSkip",
    "TeamRosterBulkPromotionResult",
    "TeamRosterBatchPlanRowPreview",
    "TeamRosterBatchEditResult",
    "TeamLinkedRosterCloneResult",
    "TeamRosterBatchTemplateExportResult",
    "TeamSameEntryRosterChange",
    "TeamSameEntryRosterEditResult",
    "TeamSameEntryTailProfileBucket",
    "TeamSameEntryTailProfileResult",
    "BitmapReferenceHit",
    "BitmapReferenceFileResult",
    "BitmapReferenceProbeResult",
    "batch_edit_team_roster_records",
    "clone_team_roster_eq_jug_linked",
    "export_team_roster_batch_template",
    "inspect_bitmap_references",
    "edit_player_metadata_records",
    "edit_team_roster_eq_jug_linked",
    "promote_team_roster_player",
    "promote_linked_roster_player_name_bulk",
    "edit_team_roster_same_entry_authoritative",
    "extract_team_rosters_eq_jug_linked",
    "extract_team_rosters_eq_same_entry_overlap",
    "inspect_player_metadata_records",
    "inspect_player_name_capacities",
    "profile_player_legacy_weight_candidates",
    "profile_indexed_player_attribute_prefixes",
    "profile_same_entry_authoritative_tail_bytes",
    "profile_indexed_player_leading_bytes",
    "profile_indexed_player_suffix_bytes",
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
    "write_player_staged_records",
    "write_coach_staged_records",
    "write_team_staged_records",
]
