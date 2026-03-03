"""Fallback heuristic scanner for embedded player records.

Provides find_player_records(file_data) -> List[(offset, PlayerRecord)]
for investigation paths and load-time augmentation when strict entry-boundary
parsing does not recover a named player record.
"""

import struct
import re
import logging
from typing import List, Tuple, Optional, Set, Dict
from collections import defaultdict

from app.models import PlayerRecord
from app.xor import xor_decode

logger = logging.getLogger(__name__)

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


def find_player_records(file_data: bytes) -> List[Tuple[int, PlayerRecord]]:
    """Find player records in an FDI/PKF file image.
    
    OPTIMIZED: Single-pass scanning with early hash-based deduplication.

    Returns:
        List of (offset, PlayerRecord) tuples. Uses heuristic scanning and
        embedded-pattern discovery adapted from the legacy tool.
    """
    # Early deduplication using normalized names as keys
    seen_names: Set[str] = set()
    records_by_name: Dict[str, Tuple[int, PlayerRecord, int]] = {}  # name -> (offset, record, score)
    
    separator = bytes([0xdd, 0x63, 0x60])
    file_len = len(file_data)
    pos = 0x400
    sections_scanned = 0
    max_sections = 500
    
    # Single coordinated pass through the file
    while pos < file_len - 1000 and sections_scanned < max_sections:
        try:
            # Read section length
            length = struct.unpack_from("<H", file_data, pos)[0]
            
            # Skip invalid lengths
            if not (100 < length < 200000) or pos + 2 + length > file_len:
                pos += 1
                continue
            
            encoded = file_data[pos + 2 : pos + 2 + length]
            decoded = xor_decode(encoded, 0x61)

            found_separated = False
            # Process separated player records (high confidence)
            if 1000 < length < 100000 and separator in decoded:
                parts = decoded.split(separator)
                for part in parts:
                    if 50 <= len(part) <= 200:
                        try:
                            rec = PlayerRecord.from_bytes(part, pos)
                            if rec.name and rec.name != "Unknown Player" and len(rec.name) > 3:
                                norm_name = _normalize_name(rec.name)

                                # Early deduplication - only keep best version
                                if norm_name not in seen_names:
                                    rec.confidence = 95
                                    rec.suppressed = False
                                    seen_names.add(norm_name)
                                    records_by_name[norm_name] = (pos, rec, 95)
                        except Exception:
                            pass
                found_separated = True
                sections_scanned += 1

            # Process embedded records in medium/large sections (lower confidence)
            # Skip embedded scan for sections that yielded separated records, unless section is large enough
            if (not found_separated and 1000 < length < 200000) or (found_separated and 10000 < length < 200000):
                try:
                    text = decoded.decode("latin-1", errors="ignore")
                    
                    # Use pre-compiled pattern for performance
                    for match in _EMBEDDED_PATTERN.finditer(text):
                        byte_pos = match.start()
                        scan_start = max(0, byte_pos - 50)
                        candidate = decoded[scan_start : byte_pos + 70]
                        
                        best_record: Optional[PlayerRecord] = None
                        best_score = -1
                        
                        # Find best-aligned window
                        min_chunk = 62
                        max_offset = max(1, min(50, max(0, len(candidate) - min_chunk + 1)))
                        for off in range(max_offset):
                            test_chunk = candidate[off : off + 80]
                            if len(test_chunk) < min_chunk:
                                continue
                            
                            try:
                                test_rec = PlayerRecord.from_bytes(test_chunk, pos + scan_start + off)
                                full_name_match = match.group(3).strip()
                                
                                # Quick validation using normalized names
                                test_name_norm = _normalize_name(test_rec.name)
                                match_name_norm = _normalize_name(full_name_match)
                                
                                if match_name_norm not in test_name_norm:
                                    continue
                                
                                # Validate attributes & position
                                attrs = test_rec.attributes
                                if not (len(attrs) >= 10 and all(0 <= a <= 100 for a in attrs)):
                                    continue
                                if not (0 <= test_rec.position <= 3):
                                    continue
                                
                                # Score alignment
                                name_start_in_chunk = byte_pos - (scan_start + off)
                                alignment_score = 1000 - abs(name_start_in_chunk - 5) * 10
                                
                                if alignment_score > best_score:
                                    best_score = alignment_score
                                    best_record = test_rec
                            except Exception:
                                continue
                        
                        if best_record:
                            # Normalize team ID
                            if getattr(best_record, 'team_id', 0) > 5000:
                                best_record.team_id = 0
                            
                            # Calculate confidence
                            confidence = _calculate_confidence(best_record, best_score)
                            best_record.confidence = confidence
                            best_record.suppressed = False
                            
                            norm_name = _normalize_name(best_record.name)
                            approx_offset = pos + scan_start + max(0, byte_pos - scan_start - 5)
                            
                            # Early deduplication - keep higher confidence version
                            if norm_name not in seen_names:
                                seen_names.add(norm_name)
                                records_by_name[norm_name] = (approx_offset, best_record, confidence)
                            elif confidence > records_by_name[norm_name][2]:
                                # Replace with higher confidence version
                                records_by_name[norm_name] = (approx_offset, best_record, confidence)
                except Exception:
                    pass
            
            pos += length + 2
        except Exception:
            pos += 1
    
    # Convert dict back to list of tuples (already deduplicated by normalized name)
    return [(offset, rec) for offset, rec, _ in records_by_name.values()]
