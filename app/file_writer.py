"""
File writing utilities for FDI files
Handles backup, modification, and safe writing
"""
import struct
import shutil
import logging
from pathlib import Path
from typing import Tuple, List

from app.models import FDIHeader, DirectoryEntry
from app.xor import encode_entry, decode_entry
from app.settings import SAVE_NAME_ONLY, ALLOW_FULL_RECORD_REWRITE_ON_EXPANSION

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def create_backup(filepath: str) -> str:
    """Create a backup of the file before modification"""
    path = Path(filepath)
    backup_path = path.with_suffix(path.suffix + '.backup')
    
    # Don't overwrite existing backups
    counter = 1
    while backup_path.exists():
        backup_path = path.with_suffix(f'{path.suffix}.backup{counter}')
        counter += 1
    
    shutil.copy2(filepath, backup_path)
    return str(backup_path)


def replace_text_in_decoded(decoded: bytes, old_text: str, new_text: str) -> Tuple[bytes, bool]:
    """
    Replace text in decoded data, handling padding and variable-length replacements where possible.

    Args:
        decoded: The decoded (XOR'd) data
        old_text: Text to find and replace
        new_text: Replacement text

    Returns:
        (modified_data, success)
        - If replacement changes length, success==True indicates the decoded payload was updated,
          but callers must handle container-level size changes (record rewrite).
    """
    old_bytes = old_text.encode('latin1')
    if old_bytes not in decoded:
        return decoded, False

    new_bytes = new_text.encode('latin1')

    # Exact-length swap is trivial
    if len(old_bytes) == len(new_bytes):
        return decoded.replace(old_bytes, new_bytes), True

    # Try simple in-place strategies:
    # - If new is shorter: replace and pad with spaces so record length stays constant.
    # - If new is longer: only allow if immediate following bytes are slack (0x00 or 0x20) to absorb growth.
    idx = decoded.find(old_bytes)
    if idx == -1:
        return decoded, False

    pre = decoded[:idx]
    post = decoded[idx + len(old_bytes):]

    if len(new_bytes) < len(old_bytes):
        pad = b' ' * (len(old_bytes) - len(new_bytes))
        return pre + new_bytes + pad + post, True

    # new_bytes longer
    needed = len(new_bytes) - len(old_bytes)
    if len(post) >= needed and all(b in (0x00, 0x20) for b in post[:needed]):
        return pre + new_bytes + post[needed:], True

    # Can't safely expand in-place
    return decoded, False


def _parse_directory_entries(data: bytes, header: FDIHeader) -> List[tuple]:
    """Return list of (DirectoryEntry, entry_pos) parsed from the header's directory block."""
    entries = []
    dir_pos = 0x20
    count = header.dir_size // 8 if header.dir_size else 0
    for i in range(count):
        pos = dir_pos + i * 8
        try:
            entry = DirectoryEntry.from_bytes(data, pos)
            entries.append((entry, pos))
        except Exception:
            logger.warning("Failed to parse directory entry at 0x%X", pos)
    return entries


def _get_record_size_at(data: bytes, offset: int) -> int:
    """Return total record size (length prefix + payload) at offset, or 0 if unreadable."""
    if offset + 2 > len(data):
        return 0
    length = struct.unpack_from("<H", data, offset)[0]
    return 2 + length


def write_fdi_record(filepath: str, offset: int, new_data: bytes) -> bool:
    """
    Write a modified record back to an FDI file, adjusting directory offsets when record size changes.

    Args:
        filepath: Path to FDI file
        offset: Offset where record starts (points to 2-byte length prefix)
        new_data: New decoded payload (NOT length-prefixed; will be XOR-encoded before writing)

    Returns:
        True if successful
    """
    try:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(filepath)

        raw = bytearray(path.read_bytes())

        # Parse header & directory
        header = FDIHeader.from_bytes(raw)
        entries = _parse_directory_entries(raw, header)

        if offset + 2 > len(raw):
            raise ValueError("Offset out of bounds")

        old_length = struct.unpack_from("<H", raw, offset)[0]
        old_record_size = 2 + old_length

        # Build encoded record (length prefix + XOR payload)
        encoded_payload = bytes(b ^ 0x61 for b in new_data)
        new_length = len(encoded_payload)
        new_record = struct.pack("<H", new_length) + encoded_payload
        new_record_size = len(new_record)

        delta = new_record_size - old_record_size
        logger.debug("Replacing record at 0x%X: old_size=%d new_size=%d delta=%d", offset, old_record_size, new_record_size, delta)

        # Construct new file bytes
        new_file = bytearray()
        new_file.extend(raw[:offset])
        new_file.extend(new_record)
        new_file.extend(raw[offset + old_record_size:])

        # Adjust directory entry offsets for entries that point after the changed record
        for entry, entry_pos in entries:
            if entry.offset > offset:
                old_off = entry.offset
                entry.offset = entry.offset + delta
                logger.debug("Adjusting directory entry at 0x%X: 0x%X -> 0x%X", entry_pos, old_off, entry.offset)
            # Repack the directory entry (offset, tag, index)
            struct.pack_into("<IHH", new_file, entry_pos, entry.offset, entry.tag, entry.index)

        # Recompute header.max_offset as end-of-last-record (safe)
        max_end = 0
        for entry, _ in entries:
            rec_size = _get_record_size_at(new_file, entry.offset)
            if rec_size:
                max_end = max(max_end, entry.offset + rec_size)
            else:
                max_end = max(max_end, entry.offset)

        header.max_offset = max_end if max_end > 0 else len(new_file)

        # Overwrite header bytes with updated header
        new_file[0:0x20] = header.to_bytes()

        # Backup original and write updated file
        backup_path = create_backup(filepath)
        path.write_bytes(bytes(new_file))
        logger.debug("FDI write complete. Wrote %s (backup: %s)", filepath, backup_path)
        return True

    except Exception as e:
        logger.exception("Error writing FDI record: %s", e)
        return False


# Helper: conservative name-only write
def write_name_only_record(filepath: str, offset: int, old_name: str, new_name: str) -> bool:
    """
    Attempt a conservative in-place update of a player name within a decoded entry payload.
    - Uses `replace_text_in_decoded` to ensure changes do not expand/reflow fields unless safe.
    - If the in-place replacement succeeds, delegates to `write_fdi_record` to persist the entry.
    - If in-place replacement is unsafe, will fail unless `ALLOW_FULL_RECORD_REWRITE_ON_EXPANSION` is True,
      in which case a best-effort full-record rewrite is attempted (risky).
    Returns True on success, False otherwise.
    """
    try:
        if not SAVE_NAME_ONLY:
            logger.debug("write_name_only_record called while SAVE_NAME_ONLY is False; refusing to proceed.")
            return False

        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(filepath)

        raw = path.read_bytes()

        # Decode entry at offset
        decoded, length = decode_entry(raw, offset)
        if decoded is None:
            logger.debug("Failed to decode entry at offset 0x%X", offset)
            return False

        # Attempt safe replacement
        modified_decoded, success = replace_text_in_decoded(decoded, old_name, new_name)
        if success:
            # Persist using the existing safe writer (handles encoding and directory adjustment)
            return write_fdi_record(filepath, offset, modified_decoded)

        # Not safe to update in-place
        logger.warning(
            "Name replacement not safe in-place at 0x%X: '%s' -> '%s'",
            offset, old_name, new_name
        )

        if not ALLOW_FULL_RECORD_REWRITE_ON_EXPANSION:
            # Fail-safe: do not attempt risky full-rewrite
            return False

        # Fallback: perform a best-effort full rewrite by replacing the bytes (first occurrence)
        old_bytes = old_name.encode('latin1')
        new_bytes = new_name.encode('latin1')
        if old_bytes not in decoded:
            logger.warning("Old name bytes not found in decoded payload; aborting full-rewrite fallback.")
            return False

        new_decoded = decoded.replace(old_bytes, new_bytes, 1)
        logger.info("Attempting full-record rewrite at 0x%X to persist expanded name", offset)
        return write_fdi_record(filepath, offset, new_decoded)

    except Exception as e:
        logger.exception("Error writing name-only record: %s", e)
        return False

def save_modified_records(file_path: str, file_data: bytes,
                          modified_records: List[tuple]) -> bytes:
    """
    Apply multiple modified records to an FDI file image (in-memory) and return
    the updated file bytes. This mirrors the behaviour of write_fdi_record but
    operates on the provided `file_data` buffer and supports applying multiple
    edits in a single pass.

    This variant includes verbose logging per-record to aid debugging when
    record payloads or directory offset adjustments produce unexpected results.

    Args:
        file_path: Path (used only for backup naming when callers choose to write)
        file_data: Original file bytes
        modified_records: List of (original_offset, PlayerRecord) tuples

    Returns:
        Modified file bytes
    """
    try:
        raw = bytearray(file_data)

        # Parse header & directory
        header = FDIHeader.from_bytes(raw)
        entries = _parse_directory_entries(raw, header)

        # Sort records by original offset (ascending) so we can track cumulative shifts
        modified_sorted = sorted(modified_records, key=lambda x: x[0])
        cumulative_delta = 0

        logger.debug("Applying %d modified record(s) to %s", len(modified_sorted), file_path)

        for orig_offset, record in modified_sorted:
            logger.debug("Processing modified record at original offset 0x%X", orig_offset)
            adj_offset = orig_offset + cumulative_delta

            if adj_offset + 2 > len(raw):
                raise ValueError("Offset out of bounds when applying modifications")

            old_length = struct.unpack_from("<H", raw, adj_offset)[0]
            old_record_size = 2 + old_length

            # Snapshot old bytes for diagnostic preview
            old_slice = bytes(raw[adj_offset:adj_offset + old_record_size])
            logger.debug("Old record @0x%X: old_length=%d old_record_size=%d preview=%s",
                         adj_offset, old_length, old_record_size, old_slice[:64].hex())

            # Prepare new record bytes. record.to_bytes() may return either:
            # - a decoded payload (raw bytes, no length-prefix, no XOR), or
            # - a fully encoded FDI entry (2-byte length prefix + XOR'd payload).
            new_entry = record.to_bytes()
            if not isinstance(new_entry, (bytes, bytearray)):
                raise TypeError("record.to_bytes() must return bytes")
 
            # Heuristic: if the first uint16 equals len(entry) - 2, treat as already-encoded
            maybe_encoded = False
            decoded_payload = b''
            decoded_len = 0
            if len(new_entry) >= 2:
                try:
                    possible_len = struct.unpack_from("<H", new_entry, 0)[0]
                    if possible_len == len(new_entry) - 2:
                        # Already encoded entry (length-prefixed + XOR)
                        new_record = bytes(new_entry)
                        maybe_encoded = True
                        # Attempt to decode for diagnostics
                        try:
                            decoded_payload, _ = decode_entry(new_record, 0)
                            decoded_len = len(decoded_payload)
                        except Exception:
                            decoded_payload = b''
                            decoded_len = possible_len
                    else:
                        # Treat as decoded payload
                        decoded_payload = bytes(new_entry)
                        decoded_len = len(decoded_payload)
                        new_record = encode_entry(decoded_payload)
                except Exception:
                    # Fallback: treat as decoded payload
                    decoded_payload = bytes(new_entry)
                    decoded_len = len(decoded_payload)
                    new_record = encode_entry(decoded_payload)
            else:
                # Too short to be encoded entry; assume decoded payload
                decoded_payload = bytes(new_entry)
                decoded_len = len(decoded_payload)
                new_record = encode_entry(decoded_payload)
 
            new_record_size = len(new_record)
            delta = new_record_size - old_record_size
 
            logger.debug(
                "Replacing record at 0x%X: old_size=%d new_size=%d delta=%d (decoded_len=%d)",
                adj_offset, old_record_size, new_record_size, delta, decoded_len
            )
            logger.debug("New encoded record preview (hex): %s", new_record[:64].hex())

            # Rebuild buffer with replaced record
            new_file = bytearray()
            new_file.extend(raw[:adj_offset])
            new_file.extend(new_record)
            new_file.extend(raw[adj_offset + old_record_size:])

            raw = new_file

            # Adjust directory offsets for entries that point after the changed record
            for entry, entry_pos in entries:
                if entry.offset > adj_offset:
                    old_off = entry.offset
                    entry.offset = entry.offset + delta
                    logger.debug("Adjusting directory entry at 0x%X: 0x%X -> 0x%X", entry_pos, old_off, entry.offset)
                # Repack the directory entry (offset, tag, index) into the buffer
                struct.pack_into("<IHH", raw, entry_pos, entry.offset, entry.tag, entry.index)

            cumulative_delta += delta

        # Recompute header.max_offset as end-of-last-record (safe)
        max_end = 0
        for entry, _ in entries:
            rec_size = _get_record_size_at(raw, entry.offset)
            if rec_size:
                max_end = max(max_end, entry.offset + rec_size)
            else:
                max_end = max(max_end, entry.offset)

        header.max_offset = max_end if max_end > 0 else len(raw)

        # Overwrite header bytes with updated header
        raw[0:0x20] = header.to_bytes()

        logger.debug("Completed applying modifications; final file size=%d", len(raw))
        return bytes(raw)

    except Exception:
        logger.exception("Error applying modified records in-memory")
        raise
