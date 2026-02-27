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
    extract_team_rosters_eq_same_entry_overlap,
    inspect_main_dat_prefix,
    parse_player_skill_patch_assignments,
    patch_main_dat_prefix,
    patch_player_visible_skills_dd6361,
    rename_coach_records,
    rename_player_records,
    rename_team_records,
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
    gather_player_records_strict,
    gather_team_records,
)
from .io import FDIFile
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


def _gather_player_entries_for_cli(args):
    if getattr(args, "strict", False):
        return gather_player_records_strict(
            args.file,
            require_team_id=getattr(args, "require_team_id", False),
        )
    return gather_player_records(args.file)


def _player_entry_payload(entry):
    return {
        "offset": entry.offset,
        "name": _player_display_name(entry.record),
        "team_id": getattr(entry.record, "team_id", None),
        "squad_number": getattr(entry.record, "squad_number", None),
        "source": entry.source,
    }


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
    """Rename player by ID"""
    fdi = FDIFile(args.file)
    fdi.load()
    target_offset = _parse_int_auto(getattr(args, "offset", None))
    target = None
    for offset, record in fdi.list_players():
        if target_offset is not None and offset == target_offset:
            target = (offset, record)
            break
        if target_offset is None and getattr(record, "team_id", None) == args.id:
            target = (offset, record)
            break
    if not target:
        print(f"Player {args.id} not found")
        return

    offset, record = target
    try:
        record.set_name(args.name)
        setattr(record, "name_dirty", True)
    except Exception:
        record.name = args.name
        setattr(record, "name_dirty", True)
    fdi.modified_records[offset] = record
    fdi.save()
    print(f"Renamed player at 0x{offset:08X} to {args.name}")


def cmd_player_list(args):
    cmd_list(args)


def cmd_player_search(args):
    cmd_search(args)


def cmd_player_investigate(args):
    query = (args.name or "").strip()
    lower_query = query.lower()

    heuristic_valid, heuristic_uncertain = gather_player_records(args.file)
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
        heuristic_valid, heuristic_uncertain = gather_player_records(args.file)
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
    if not result.changes:
        print("No player records changed.")
        return
    print(
        f"{'Staged' if args.dry_run else 'Renamed'} {len(result.changes)} player record(s) "
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
                print(f"  {marker} pid={pid:5d}  {name_part}")
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
                    print(f"  {marker} pid={pid:5d}  {name_part}")
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
                print(f"  {marker} pid={pid:5d}  {name_part}")
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
                print(f"  {marker} pid={pid:5d}  {name_part}")
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
                print(f"  {marker} pid={pid:5d}  {name_part}")
                shown += 1

    if args.json_output:
        print(f"\nReport: {args.json_output}")


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
        help="Extract team roster via EQ same-entry overlap (experimental, read-only)",
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
