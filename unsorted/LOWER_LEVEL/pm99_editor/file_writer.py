"""
File writing utilities for FDI files
Handles backup, modification, and safe writing
"""
import struct
import shutil
import logging
from pathlib import Path
from typing import Tuple, List

from .models import FDIHeader, DirectoryEntry

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
        logger.info("Replacing record at 0x%X: old_size=%d new_size=%d delta=%d", offset, old_record_size, new_record_size, delta)

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
        logger.info("FDI write complete. Wrote %s (backup: %s)", filepath, backup_path)
        return True

    except Exception as e:
        logger.exception("Error writing FDI record: %s", e)
        return False