"""Shared bulk player rename/revert helpers used by scripts, CLI, and GUI."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from app.io import FDIFile


MAPPING_FIELDNAMES = [
    "record_index",
    "offset",
    "offset_hex",
    "team_id",
    "squad_no",
    "original_name",
    "new_name",
    "file",
]


@dataclass
class BulkFileResult:
    file: str
    total_players: int = 0
    changed_players: int = 0
    skipped_players: int = 0
    rows_written: int = 0
    warnings: List[str] = field(default_factory=list)


@dataclass
class BulkRenameResult:
    data_dir: Path
    map_output: Optional[Path]
    dry_run: bool
    integrity_checks: bool
    files_processed: int
    rows_written: int
    file_results: List[BulkFileResult]


@dataclass
class BulkRevertResult:
    data_dir: Path
    map_input: Path
    dry_run: bool
    files_processed: int
    rows_processed: int
    file_results: List[BulkFileResult]


def compute_new_name(index: int, length: int) -> str:
    """Return a deterministic, length-preserving token for a player name."""
    token = f"Z{index:08d}"
    if len(token) >= length:
        return token[:length]
    return token.ljust(length, "Z")


def get_display_name(rec) -> str:
    return getattr(rec, "name", "") or (
        f"{getattr(rec, 'given_name', '')} {getattr(rec, 'surname', '')}".strip()
    )


def _parse_optional_int(value) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text, 0)
    except ValueError:
        return None


def _validate_mapping_rows(rows: Iterable[dict], file_name: str) -> None:
    seen_offsets = set()
    seen_indexes = set()
    for row in rows:
        idx = row.get("record_index")
        if idx in seen_indexes:
            raise RuntimeError(f"Duplicate record_index in mapping for {file_name}: {idx}")
        seen_indexes.add(idx)
        off = row.get("offset")
        if off == "":
            continue
        if off in seen_offsets:
            raise RuntimeError(f"Duplicate offset in mapping for {file_name}: {off}")
        seen_offsets.add(off)


def process_player_file(
    file_path: Path,
    rows: List[dict],
    dry_run: bool = False,
    integrity_checks: bool = True,
) -> BulkFileResult:
    """Rename players in a single JUG*.FDI file and append mapping rows."""
    fdi = FDIFile(str(file_path))
    fdi.load()
    players = list(fdi.list_players())

    result = BulkFileResult(file=file_path.name, total_players=len(players))
    file_rows: List[dict] = []
    seen_offsets_in_file: set[int] = set()

    for idx, (offset, rec) in enumerate(players):
        if isinstance(offset, int):
            if offset in seen_offsets_in_file:
                result.skipped_players += 1
                result.warnings.append(
                    f"Skipped duplicate offset 0x{offset:08X} at record_index={idx} "
                    f"({get_display_name(rec) or '<unnamed>'})"
                )
                continue
            seen_offsets_in_file.add(offset)

        orig_name = get_display_name(rec)
        if not orig_name:
            result.skipped_players += 1
            continue

        new_name = compute_new_name(idx, len(orig_name))
        if len(new_name) != len(orig_name):
            raise RuntimeError(
                f"Name length mismatch for {file_path.name} record {idx}: "
                f"{len(orig_name)} -> {len(new_name)}"
            )
        if new_name == orig_name:
            result.skipped_players += 1
            continue

        row = {
            "record_index": idx,
            "offset": offset if isinstance(offset, int) else "",
            "offset_hex": f"0x{offset:x}" if isinstance(offset, int) else "",
            "team_id": getattr(rec, "team_id", ""),
            "squad_no": getattr(rec, "squad_number", ""),
            "original_name": orig_name,
            "new_name": new_name,
            "file": file_path.name,
        }
        file_rows.append(row)
        result.changed_players += 1

        if dry_run:
            continue

        if not isinstance(offset, int):
            raise RuntimeError(
                f"{file_path.name} record {idx} has unsupported offset {offset!r}; "
                "cannot save in name-only mode"
            )
        rec.name = new_name
        setattr(rec, "name_dirty", True)
        fdi.modified_records[offset] = rec

    if integrity_checks:
        _validate_mapping_rows(file_rows, file_path.name)

    rows.extend(file_rows)
    result.rows_written = len(file_rows)

    if not dry_run and fdi.modified_records:
        if integrity_checks and len(fdi.modified_records) != len(file_rows):
            raise RuntimeError(
                f"Modified-record count mismatch for {file_path.name}: "
                f"{len(fdi.modified_records)} vs {len(file_rows)}"
            )
        fdi.save()

    return result


def write_mapping_csv(rows: List[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=MAPPING_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def bulk_rename_players(
    data_dir: str | Path,
    map_output: str | Path,
    *,
    dry_run: bool = False,
    integrity_checks: bool = True,
) -> BulkRenameResult:
    """Bulk rename all players in JUG*.FDI files and write a mapping CSV."""
    base = Path(data_dir)
    if not base.is_dir():
        raise SystemExit(f"Not a directory: {base}")

    rows: List[dict] = []
    file_results: List[BulkFileResult] = []
    for file_path in sorted(base.glob("JUG*.FDI")):
        file_results.append(
            process_player_file(
                file_path=file_path,
                rows=rows,
                dry_run=dry_run,
                integrity_checks=integrity_checks,
            )
        )

    out_path = Path(map_output)
    write_mapping_csv(rows, out_path)
    return BulkRenameResult(
        data_dir=base,
        map_output=out_path,
        dry_run=dry_run,
        integrity_checks=integrity_checks,
        files_processed=len(file_results),
        rows_written=len(rows),
        file_results=file_results,
    )


def load_mapping_rows(map_input: Path) -> Dict[str, List[dict]]:
    rows_by_file: Dict[str, List[dict]] = defaultdict(list)
    with map_input.open("r", newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        fieldnames = reader.fieldnames or []
        missing = [field for field in ("file", "record_index", "original_name") if field not in fieldnames]
        if missing:
            raise SystemExit(f"Mapping CSV missing required columns: {', '.join(missing)}")
        for row in reader:
            file_name = (row.get("file") or "").strip()
            if not file_name:
                raise SystemExit(f"Mapping row missing file value: {row!r}")
            rows_by_file[file_name].append(row)
    return rows_by_file


def _resolve_row_record(players, row):
    offset = _parse_optional_int(row.get("offset"))
    if offset is None:
        offset = _parse_optional_int(row.get("offset_hex"))

    if offset is not None:
        for player_offset, rec in players:
            if player_offset == offset:
                return player_offset, rec

    idx = _parse_optional_int(row.get("record_index"))
    if idx is None:
        raise RuntimeError(f"Mapping row missing usable locator (offset/record_index): {row!r}")
    if idx < 0 or idx >= len(players):
        raise RuntimeError(
            f"record_index {idx} out of range for {row.get('file', '<unknown>')} "
            f"(players={len(players)})"
        )
    return players[idx]


def _row_locator_label(row) -> str:
    return str(row.get("offset_hex") or row.get("offset") or f"index {row.get('record_index')}")


def revert_player_file(
    file_path: Path,
    file_rows: List[dict],
    *,
    dry_run: bool = False,
    integrity_checks: bool = True,
) -> BulkFileResult:
    """Revert player names in a single file using mapping rows."""
    fdi = FDIFile(str(file_path))
    fdi.load()
    players = list(fdi.list_players())

    result = BulkFileResult(file=file_path.name, total_players=len(players))
    seen_rows = []

    for row in file_rows:
        offset, rec = _resolve_row_record(players, row)
        current_name = get_display_name(rec)
        original_name = (row.get("original_name") or "").strip()
        renamed_name = (row.get("new_name") or "").strip()

        if not original_name:
            raise RuntimeError(f"Mapping row missing original_name: {row!r}")
        if current_name == original_name:
            result.skipped_players += 1
            continue
        if integrity_checks and renamed_name and current_name and current_name != renamed_name:
            raise RuntimeError(
                f"Current name mismatch for {file_path.name} at {_row_locator_label(row)}: "
                f"expected renamed '{renamed_name}', found '{current_name}'"
            )
        if current_name and len(current_name) != len(original_name):
            raise RuntimeError(
                f"Name length mismatch for {file_path.name} at {_row_locator_label(row)}: "
                f"{len(current_name)} -> {len(original_name)}"
            )
        if not isinstance(offset, int):
            raise RuntimeError(
                f"Cannot revert {file_path.name} row {row.get('record_index')}: "
                f"resolved offset is not an int ({offset!r})"
            )

        seen_rows.append({"record_index": row.get("record_index"), "offset": offset})
        if dry_run:
            result.changed_players += 1
            continue

        rec.name = original_name
        setattr(rec, "name_dirty", True)
        fdi.modified_records[offset] = rec
        result.changed_players += 1

    if integrity_checks:
        _validate_mapping_rows(seen_rows, file_path.name)

    result.rows_written = len(file_rows)
    if not dry_run and fdi.modified_records:
        if integrity_checks and len(fdi.modified_records) != result.changed_players:
            raise RuntimeError(
                f"Modified-record count mismatch for revert in {file_path.name}: "
                f"{len(fdi.modified_records)} vs {result.changed_players}"
            )
        fdi.save()

    return result


def revert_player_renames(
    data_dir: str | Path,
    map_input: str | Path,
    *,
    dry_run: bool = False,
    integrity_checks: bool = True,
) -> BulkRevertResult:
    """Revert player bulk renames from a mapping CSV."""
    base = Path(data_dir)
    if not base.is_dir():
        raise SystemExit(f"Not a directory: {base}")

    map_path = Path(map_input)
    if not map_path.is_file():
        raise SystemExit(f"Mapping CSV not found: {map_path}")

    rows_by_file = load_mapping_rows(map_path)
    file_results: List[BulkFileResult] = []
    rows_processed = 0
    for file_name in sorted(rows_by_file):
        file_path = base / file_name
        if not file_path.is_file():
            raise SystemExit(f"Referenced FDI file not found: {file_path}")
        file_rows = rows_by_file[file_name]
        rows_processed += len(file_rows)
        file_results.append(
            revert_player_file(
                file_path,
                file_rows,
                dry_run=dry_run,
                integrity_checks=integrity_checks,
            )
        )

    return BulkRevertResult(
        data_dir=base,
        map_input=map_path,
        dry_run=dry_run,
        files_processed=len(file_results),
        rows_processed=rows_processed,
        file_results=file_results,
    )


__all__ = [
    "MAPPING_FIELDNAMES",
    "BulkFileResult",
    "BulkRenameResult",
    "BulkRevertResult",
    "bulk_rename_players",
    "revert_player_renames",
    "compute_new_name",
    "get_display_name",
    "load_mapping_rows",
    "process_player_file",
    "revert_player_file",
]
