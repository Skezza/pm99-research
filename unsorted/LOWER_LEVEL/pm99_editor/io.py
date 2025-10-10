"""File I/O operations for PM99 FDI database files.

Handles reading, parsing, and writing FDI files with proper directory management.
"""

from pathlib import Path
from typing import List, Iterator, Tuple
import struct
import shutil

from .models import FDIHeader, DirectoryEntry, PlayerRecord
from .xor import decode_entry


class FDIFile:
    """Reader/writer for PM99 FDI database files."""
    
    def __init__(self, path: Path):
        """
        Initialize FDI file handler.
        
        Args:
            path: Path to FDI file
        """
        self.path = Path(path)
        self.header: FDIHeader = None
        self.directory: List[DirectoryEntry] = []
        self.records: List[PlayerRecord] = []
        self._raw_data: bytes = None
    
    def load(self) -> None:
        """Load and parse the complete FDI file."""
        if not self.path.exists():
            raise FileNotFoundError(f"FDI file not found: {self.path}")
        
        self._raw_data = self.path.read_bytes()
        
        # Parse header
        self.header = FDIHeader.from_bytes(self._raw_data)
        
        # Parse directory entries
        self.directory = self._parse_directory()
        
        # Parse player records
        self.records = list(self._iter_records())
    
    def _parse_directory(self) -> List[DirectoryEntry]:
        """Parse directory entries from file header."""
        entries = []
        pos = 0x20  # Directory starts after 32-byte header
        
        # Read entries until we hit the directory size limit
        while pos < 0x20 + self.header.dir_size:
            if pos + 8 > len(self._raw_data):
                break
            
            entry = DirectoryEntry.from_bytes(self._raw_data, pos)
            entries.append(entry)
            pos += 8
        
        return entries
    
    def _iter_records(self) -> Iterator[PlayerRecord]:
        """
        Iterate through all player records by scanning file sections.
        
        Uses the same proven approach as the working GUI parser:
        - Scans from 0x400 onwards
        - Decodes sections with XOR 0x61
        - Looks for separator pattern 0xdd 0x63 0x60
        - Parses clean player records (50-200 bytes)
        
        Yields:
            PlayerRecord instances
        """
        separator = bytes([0xdd, 0x63, 0x60])
        pos = 0x400  # Skip header/directory
        record_id = 0
        
        while pos < len(self._raw_data) - 1000:
            try:
                # Read section length (uint16 LE)
                if pos + 2 > len(self._raw_data):
                    break
                    
                length = struct.unpack_from("<H", self._raw_data, pos)[0]
                
                # Valid section lengths: 1000 < length < 100000
                if 1000 < length < 100000:
                    # Decode section with XOR 0x61
                    section_start = pos + 2
                    section_end = section_start + length
                    
                    if section_end > len(self._raw_data):
                        pos += 1
                        continue
                    
                    encoded = self._raw_data[section_start:section_end]
                    decoded = bytes(b ^ 0x61 for b in encoded)
                    
                    # Look for separator pattern
                    if separator in decoded:
                        # Split into records
                        parts = decoded.split(separator)
                        
                        for part in parts:
                            # Only handle clean player records (50-200 bytes)
                            if 50 <= len(part) <= 200:
                                try:
                                    record = PlayerRecord.from_bytes(
                                        part,
                                        pos,  # Section offset for error reporting
                                        version=self.header.version
                                    )
                                    
                                    # Validate name
                                    if record.given_name and record.given_name not in ["Unknown Player", "Parse Error"]:
                                        # Normalize implausible team IDs to avoid misleading values in clean pass too
                                        if getattr(record, 'team_id', 0) > 5000:
                                            record.team_id = 0
                                        record.record_id = record_id
                                        record_id += 1
                                        yield record
                                except Exception:
                                    # Skip unparseable records
                                    pass
                    
                    pos += length + 2
                else:
                    pos += 1
            except Exception:
                pos += 1

        # Additional pass: embedded player records in large sections without separators
        pos = 0x400
        while pos < len(self._raw_data) - 1000:
            try:
                if pos + 2 > len(self._raw_data):
                    break
                length = struct.unpack_from("<H", self._raw_data, pos)[0]
                if 5000 < length < 200000:
                    section_start = pos + 2
                    section_end = section_start + length
                    if section_end > len(self._raw_data):
                        pos += 1
                        continue

                    encoded = self._raw_data[section_start:section_end]
                    decoded = bytes(b ^ 0x61 for b in encoded)

                    import re
                    # Match: [abbrev][1–2 non-letters or letters]+ 'a' + [Full Name (0–3 middles) + SURNAME]
                    embedded_pattern = r'([A-Z][a-z]{2,20})((?:[a-z~@\x7f]{1,2}|[^A-Za-z]{1,2})a)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+[A-Z]{3,20})'
                    for match in re.finditer(embedded_pattern, decoded.decode('latin-1', errors='ignore')):
                        byte_pos = match.start()

                        # Scan around the abbreviated name to find a plausible record start
                        scan_start = max(0, byte_pos - 50)
                        candidate_chunk = decoded[scan_start:byte_pos + 70]

                        best_record = None
                        best_score = -1

                        for offset in range(min(50, len(candidate_chunk) - 80)):
                            test_chunk = candidate_chunk[offset:offset + 80]
                            if len(test_chunk) >= 80:
                                try:
                                    test_record = PlayerRecord.from_bytes(
                                        test_chunk,
                                        pos + scan_start + offset,
                                        version=self.header.version
                                    )

                                    # Validate against the matched full name
                                    full_name_match = match.group(3).strip()
                                    full_nm = f"{test_record.given_name} {test_record.surname}".strip()
                                    if full_name_match.upper() not in full_nm.upper():
                                        continue

                                    # Require plausible attributes and position
                                    if not (len(test_record.skills) >= 10 and all(0 <= a <= 100 for a in test_record.skills)):
                                        continue
                                    if not (0 <= test_record.position_primary <= 3):
                                        continue

                                    # Prefer alignments where name starts near byte 5
                                    name_start_in_chunk = byte_pos - (scan_start + offset)
                                    alignment_score = abs(name_start_in_chunk - 5)
                                    score = 1000 - (alignment_score * 10)

                                    if score > best_score:
                                        best_score = score
                                        best_record = test_record
                                except Exception:
                                    continue

                        if best_record:
                            # Normalize implausible embedded-derived team IDs to avoid misleading values
                            if getattr(best_record, 'team_id', 0) > 5000:
                                best_record.team_id = 0
                            best_record.record_id = record_id
                            record_id += 1
                            yield best_record

                    pos += length + 2
                else:
                    pos += 1
            except Exception:
                pos += 1

    def find_by_id(self, record_id: int) -> PlayerRecord:
        """
        Find a player record by ID.
        
        Args:
            record_id: Player record ID to find
            
        Returns:
            PlayerRecord instance
            
        Raises:
            ValueError: If record not found
        """
        for record in self.records:
            if record.record_id == record_id:
                return record
        raise ValueError(f"Player record {record_id} not found")
    
    def find_by_name(self, name: str) -> List[PlayerRecord]:
        """
        Search for players by name (case-insensitive substring match).
        Deduplicates by merging similar entries (e.g., middle name variants).
        
        Args:
            name: Name substring to search for
            
        Returns:
            List of unique matching PlayerRecord instances
        """
        name_lower = name.lower()
        candidates = []
        
        for record in self.records:
            full_name = f"{record.given_name} {record.surname}".lower()
            if name_lower in full_name:
                # Normalize name for dedup: remove middle names, focus on first + last
                norm_parts = full_name.split()
                norm_name = f"{norm_parts[0]} {norm_parts[-1]}"
                candidates.append((norm_name, record))
        
        # Deduplicate: group by normalized name, keep the one with most complete data (longer skills, etc.)
        from collections import defaultdict
        groups = defaultdict(list)
        for norm, rec in candidates:
            groups[norm].append(rec)
        
        unique_matches = []
        for norm, recs in groups.items():
            if len(recs) > 1:
                # Merge: prefer record with valid team_id (!=0), then non-default position, then longer skills
                best = max(recs, key=lambda r: (r.team_id != 0, r.position_primary != 0, len(r.skills)))
                unique_matches.append(best)
                print(f"Merged {len(recs)} duplicates for {norm} into {best.given_name} {best.surname}")
            else:
                unique_matches.append(recs[0])
        
        return unique_matches
    
    def save(self, output_path: Path = None, backup: bool = True) -> None:
        """
        Write modified FDI file to disk.
        
        Args:
            output_path: Output file path (default: overwrite original)
            backup: Create .bak backup of original file
        """
        output_path = Path(output_path) if output_path else self.path
        
        # Create backup if requested
        if backup and output_path.exists() and output_path == self.path:
            backup_path = output_path.with_suffix('.fdi.bak')
            shutil.copy2(output_path, backup_path)
            print(f"Backup created: {backup_path}")
        
        # Rebuild file from records
        rebuilt = self._rebuild_file()
        
        # Write to disk
        output_path.write_bytes(rebuilt)
        print(f"Saved {len(self.records)} records to {output_path}")
    
    def _rebuild_file(self) -> bytes:
        """
        Rebuild complete FDI file from current records.
        
        Returns:
            Complete file bytes with header, directory, and records
        """
        # Start with header
        parts = [self.header.to_bytes()]
        
        # Rebuild directory
        directory_entries = []
        current_offset = 0x20 + len(self.directory) * 8  # After header + directory
        
        for i, record in enumerate(self.records):
            # Serialize record
            record_bytes = record.to_bytes()
            
            # Create directory entry
            tag = ord('P') if i < len(self.directory) else 0
            index = i
            entry = DirectoryEntry(
                offset=current_offset,
                tag=tag,
                index=index
            )
            directory_entries.append(entry)
            
            # Track offset for next record
            current_offset += len(record_bytes)
        
        # Update header with new record count
        self.header.record_count = len(self.records)
        self.header.dir_size = len(directory_entries) * 8
        parts[0] = self.header.to_bytes()
        
        # Append directory
        for entry in directory_entries:
            parts.append(entry.to_bytes())
        
        # Append all records
        for record in self.records:
            parts.append(record.to_bytes())
        
        return b''.join(parts)
    
    def list_players(self, limit: int = None) -> List[str]:
        """
        Get formatted list of players.
        
        Args:
            limit: Maximum number of players to return
            
        Returns:
            List of formatted player strings
        """
        results = []
        for i, record in enumerate(self.records):
            if limit and i >= limit:
                break
            results.append(str(record))
        return results