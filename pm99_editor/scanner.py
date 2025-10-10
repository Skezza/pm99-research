"""Scanner for embedded player records.

Provides find_player_records(file_data) -> List[(offset, PlayerRecord)]
so IO and tools can discover player records without importing the GUI.

OPTIMIZED VERSION: Single-pass scanning with early deduplication.
"""

import struct
import re
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional, Set, Dict, Iterable

from pm99_editor.models import PlayerRecord
from pm99_editor.xor import xor_decode

logger = logging.getLogger(__name__)


class PlayerScanError(RuntimeError):
    """Raised when the scanner encounters structural issues."""

    def __init__(self, issues: Iterable["PlayerScanIssue"]) -> None:
        self.issues = list(issues)
        summary = ", ".join(issue.reason for issue in self.issues[:3])
        if len(self.issues) > 3:
            summary += f" (+{len(self.issues) - 3} more)"
        super().__init__(f"Player scan reported {len(self.issues)} issue(s): {summary}")


@dataclass
class PlayerScanIssue:
    """Captures metadata about a failed record decode attempt."""

    offset: int
    reason: str
    context: bytes

# Pre-compiled regex patterns for performance
_EMBEDDED_PATTERN = re.compile(
    r'([A-Z][a-z]{2,20})((?:[a-z~@\x7f]{1,2}|[^A-Za-z]{1,2})a)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+[A-Z]{3,20})'
)


def _normalize_name(name: str) -> str:
    """Normalize name for deduplication (lowercase, stripped)."""
    return name.strip().upper()


def _calculate_confidence(record: PlayerRecord, alignment_score: int) -> int:
    """Calculate confidence score for a player record."""
    base_conf = max(5, min(100, int(alignment_score / 10)))
    
    if getattr(record, 'team_id', 0) not in (0, None) and getattr(record, 'team_id', 0) < 5000:
        base_conf = min(100, base_conf + 10)
    
    try:
        attrs = getattr(record, 'attributes', [])
        if len(attrs) >= 10:
            base_conf = min(100, base_conf + 5)
    except Exception:
        pass
    
    if getattr(record, 'position', 0) not in (0, None):
        base_conf = min(100, base_conf + 5)
    
    return base_conf


def find_player_records(
    file_data: bytes,
    *,
    strict: bool = True,
    quarantine: Optional[List[PlayerScanIssue]] = None,
) -> List[Tuple[int, PlayerRecord]]:
    """Scan ``file_data`` for player records.

    The scanner now surfaces structured issues instead of silently skipping
    failures.  Callers can disable strict handling or inspect the optional
    ``quarantine`` list for forensic analysis.
    """

    seen_names: Set[str] = set()
    records_by_name: Dict[str, Tuple[int, PlayerRecord, int]] = {}
    issues: List[PlayerScanIssue] = []

    separator = bytes([0xdd, 0x63, 0x60])
    file_len = len(file_data)
    pos = 0x400
    sections_scanned = 0
    max_sections = 500

    while pos < file_len - 1000 and sections_scanned < max_sections:
        try:
            length = struct.unpack_from("<H", file_data, pos)[0]
        except struct.error as exc:
            issues.append(
                PlayerScanIssue(
                    offset=pos,
                    reason=f"failed to unpack section length: {exc}",
                    context=file_data[pos : pos + 16],
                )
            )
            pos += 1
            continue

        if not (100 < length < 200000) or pos + 2 + length > file_len:
            pos += 1
            continue

        encoded = file_data[pos + 2 : pos + 2 + length]
        decoded = xor_decode(encoded, 0x61)

        if 1000 < length < 100000 and separator in decoded:
            parts = decoded.split(separator)
            for part in parts:
                if 50 <= len(part) <= 200:
                    if b"\x61\x61\x61\x61" not in part:
                        continue
                    try:
                        rec = PlayerRecord.from_bytes(part, pos)
                    except Exception as exc:
                        issues.append(
                            PlayerScanIssue(
                                offset=pos,
                                reason=f"separated chunk parse failure: {exc}",
                                context=part[:64],
                            )
                        )
                        continue

                    if rec.name and rec.name != "Unknown Player" and len(rec.name) > 3:
                        norm_name = _normalize_name(rec.name)
                        if norm_name not in seen_names:
                            rec.confidence = 95
                            rec.suppressed = False
                            seen_names.add(norm_name)
                            records_by_name[norm_name] = (pos, rec, 95)
            sections_scanned += 1

        if 1000 < length < 200000:
            try:
                text = decoded.decode("latin-1")
            except UnicodeDecodeError as exc:
                issues.append(
                    PlayerScanIssue(
                        offset=pos,
                        reason=f"latin-1 decode failure: {exc}",
                        context=decoded[:32],
                    )
                )
                pos += length + 2
                continue

            for match in _EMBEDDED_PATTERN.finditer(text):
                byte_pos = match.start()
                scan_start = max(0, byte_pos - 50)
                candidate = decoded[scan_start : byte_pos + 70]

                best_record: Optional[PlayerRecord] = None
                best_score = -1

                min_chunk = 62
                max_offset = max(1, min(50, max(0, len(candidate) - min_chunk + 1)))
                for off in range(max_offset):
                    test_chunk = candidate[off : off + 80]
                    if len(test_chunk) < min_chunk:
                        continue
                    if b"\x61\x61\x61\x61" not in test_chunk:
                        continue

                    try:
                        test_rec = PlayerRecord.from_bytes(
                            test_chunk, pos + scan_start + off
                        )
                    except Exception as exc:
                        issues.append(
                            PlayerScanIssue(
                                offset=pos + scan_start + off,
                                reason=f"embedded chunk parse failure: {exc}",
                                context=test_chunk[:64],
                            )
                        )
                        continue

                    full_name_match = match.group(3).strip()
                    test_name_norm = _normalize_name(test_rec.name)
                    match_name_norm = _normalize_name(full_name_match)

                    if match_name_norm not in test_name_norm:
                        continue

                    attrs = getattr(test_rec, "attributes", getattr(test_rec, "skills", []))
                    if not (len(attrs) >= 10 and all(0 <= a <= 100 for a in attrs)):
                        continue
                    position_value = getattr(test_rec, "position", getattr(test_rec, "position_primary", 0))
                    if not (0 <= position_value <= 3):
                        continue

                    name_start_in_chunk = byte_pos - (scan_start + off)
                    alignment_score = 1000 - abs(name_start_in_chunk - 5) * 10

                    if alignment_score > best_score:
                        best_score = alignment_score
                        best_record = test_rec

                if best_record:
                    if getattr(best_record, "team_id", 0) > 5000:
                        best_record.team_id = 0

                    confidence = _calculate_confidence(best_record, best_score)
                    best_record.confidence = confidence
                    best_record.suppressed = False

                    norm_name = _normalize_name(best_record.name)
                    approx_offset = pos + scan_start + max(0, byte_pos - scan_start - 5)

                    if norm_name not in seen_names:
                        seen_names.add(norm_name)
                        records_by_name[norm_name] = (approx_offset, best_record, confidence)
                    elif confidence > records_by_name[norm_name][2]:
                        records_by_name[norm_name] = (approx_offset, best_record, confidence)

        pos += length + 2

    if quarantine is not None:
        quarantine.extend(issues)

    if strict and issues:
        raise PlayerScanError(issues)

    return [(offset, rec) for offset, rec, _ in records_by_name.values()]