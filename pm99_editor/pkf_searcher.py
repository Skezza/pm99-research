"""
PKF String Searcher - Search for strings/patterns across PKF archive files

This module provides comprehensive search capabilities across PKF files,
supporting text, regex, hex patterns, and XOR-decoded content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Iterator, Tuple, Union
import mmap
from concurrent.futures import ThreadPoolExecutor, as_completed

from .pkf import PKFFile, PKFEntry
from .xor import xor_decode


@dataclass
class SearchResult:
    """Container for a single search match result."""
    
    file_path: Path
    """Path to the PKF file containing the match"""
    
    entry_index: int
    """Index of the entry within the PKF file"""
    
    entry_offset: int
    """Offset of the entry in the file"""
    
    match_offset: int
    """Offset of the match within the entry"""
    
    absolute_offset: int
    """Absolute offset in the entire file"""
    
    match_bytes: bytes
    """The actual matched bytes"""
    
    context_before: bytes = field(default_factory=bytes)
    """Bytes before the match for context"""
    
    context_after: bytes = field(default_factory=bytes)
    """Bytes after the match for context"""
    
    encoding: Optional[str] = None
    """Encoding used if searching decoded text"""
    
    xor_key: Optional[int] = None
    """XOR key if searching XOR-decoded content"""
    
    def format_preview(self, width: int = 16) -> str:
        """Format match with context as hex dump."""
        data = self.context_before + self.match_bytes + self.context_after
        match_start = len(self.context_before)
        match_end = match_start + len(self.match_bytes)
        
        lines = []
        offset = self.absolute_offset - len(self.context_before)
        
        for i in range(0, len(data), width):
            chunk = data[i:i + width]
            hex_part = " ".join(f"{byte:02X}" for byte in chunk)
            ascii_part = "".join(
                chr(byte) if 32 <= byte < 127 else "." for byte in chunk
            )
            
            # Mark the match region
            marker = ""
            if i < match_end and i + width > match_start:
                start_mark = max(0, match_start - i)
                end_mark = min(width, match_end - i)
                marker = " " * start_mark + "^" * (end_mark - start_mark)
            
            line = f"{offset + i:08X}  {hex_part:<{width * 3 - 1}}  {ascii_part}"
            if marker:
                line += f"\n         {marker}"
            lines.append(line)
        
        return "\n".join(lines)
    
    def get_match_text(self, encoding: str = "utf-8") -> str:
        """Attempt to decode match bytes as text."""
        try:
            return self.match_bytes.decode(encoding, errors="replace")
        except Exception:
            return f"<binary: {self.match_bytes.hex()}>"


class PKFSearcher:
    """Search for strings and patterns across PKF archive files."""
    
    def __init__(
        self,
        directory: Union[str, Path],
        recursive: bool = True,
        file_pattern: str = "*.pkf",
        max_results: int = 1000,
        context_size: int = 32,
    ):
        """
        Initialize the PKF searcher.
        
        Args:
            directory: Directory to search for PKF files
            recursive: Whether to search subdirectories recursively
            file_pattern: Glob pattern for PKF files (default: "*.pkf")
            max_results: Maximum number of results to return
            context_size: Number of bytes before/after match for context
        """
        self.directory = Path(directory)
        self.recursive = recursive
        self.file_pattern = file_pattern
        self.max_results = max_results
        self.context_size = context_size
        self._results_count = 0
    
    def find_pkf_files(self) -> List[Path]:
        """Find all PKF files in the configured directory."""
        if self.recursive:
            return sorted(self.directory.rglob(self.file_pattern))
        else:
            return sorted(self.directory.glob(self.file_pattern))
    
    def search_text(
        self,
        query: str,
        case_sensitive: bool = False,
        encoding: str = "utf-8",
        use_parallel: bool = True,
    ) -> List[SearchResult]:
        """
        Search for plain text string across PKF files.
        
        Args:
            query: Text string to search for
            case_sensitive: Whether search is case-sensitive
            encoding: Character encoding to use
            use_parallel: Use parallel processing for multiple files
            
        Returns:
            List of SearchResult objects
        """
        if not query:
            return []
        
        # Convert query to bytes for searching
        try:
            query_bytes = query.encode(encoding)
        except UnicodeEncodeError:
            # Fallback to UTF-8 if encoding fails
            query_bytes = query.encode("utf-8", errors="replace")
        
        # For case-insensitive, we'll search both original and lowercase
        if not case_sensitive:
            return self._search_case_insensitive(query_bytes, encoding, use_parallel)
        
        return self._search_bytes_pattern(query_bytes, encoding=encoding, use_parallel=use_parallel)
    
    def search_regex(
        self,
        pattern: str,
        encoding: str = "utf-8",
        use_parallel: bool = True,
    ) -> List[SearchResult]:
        """
        Search using regular expression pattern.
        
        Args:
            pattern: Regex pattern string (or bytes)
            encoding: Character encoding to use
            use_parallel: Use parallel processing for multiple files
            
        Returns:
            List of SearchResult objects
        """
        try:
            # Handle both string and bytes patterns
            if isinstance(pattern, bytes):
                regex = re.compile(pattern)
            else:
                regex = re.compile(pattern.encode(encoding))
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")
        
        return self._search_regex_compiled(regex, encoding=encoding, use_parallel=use_parallel)
    
    def search_hex(self, hex_string: str, use_parallel: bool = True) -> List[SearchResult]:
        """
        Search for hexadecimal pattern.
        
        Args:
            hex_string: Hex string (e.g., "48656C6C6F" or "48 65 6C 6C 6F")
            use_parallel: Use parallel processing for multiple files
            
        Returns:
            List of SearchResult objects
        """
        # Clean hex string (remove spaces, 0x prefixes)
        cleaned = hex_string.replace(" ", "").replace("0x", "").replace("0X", "")
        
        if len(cleaned) % 2 != 0:
            raise ValueError("Hex string must have even number of characters")
        
        try:
            pattern_bytes = bytes.fromhex(cleaned)
        except ValueError as e:
            raise ValueError(f"Invalid hex string: {e}")
        
        return self._search_bytes_pattern(pattern_bytes, use_parallel=use_parallel)
    
    def search_with_xor(
        self,
        query: str,
        xor_key: int,
        encoding: str = "utf-8",
        use_parallel: bool = True,
    ) -> List[SearchResult]:
        """
        Search for string after XOR decoding.
        
        Args:
            query: Text string to search for
            xor_key: XOR key to apply before searching
            encoding: Character encoding to use
            use_parallel: Use parallel processing for multiple files
            
        Returns:
            List of SearchResult objects with xor_key set
        """
        if not 0 <= xor_key <= 255:
            raise ValueError("XOR key must be 0-255")
        
        try:
            query_bytes = query.encode(encoding)
        except UnicodeEncodeError:
            query_bytes = query.encode("utf-8", errors="replace")
        
        results = []
        pkf_files = self.find_pkf_files()
        
        if use_parallel and len(pkf_files) > 1:
            with ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(self._search_file_xor, fpath, query_bytes, xor_key, encoding): fpath
                    for fpath in pkf_files
                }
                for future in as_completed(futures):
                    results.extend(future.result())
                    if self._results_count >= self.max_results:
                        break
        else:
            for fpath in pkf_files:
                results.extend(self._search_file_xor(fpath, query_bytes, xor_key, encoding))
                if self._results_count >= self.max_results:
                    break
        
        return results[:self.max_results]
    
    def _search_bytes_pattern(
        self,
        pattern: bytes,
        encoding: Optional[str] = None,
        use_parallel: bool = True,
    ) -> List[SearchResult]:
        """Search for exact byte pattern across PKF files."""
        results = []
        pkf_files = self.find_pkf_files()
        
        if use_parallel and len(pkf_files) > 1:
            with ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(self._search_file_bytes, fpath, pattern, encoding): fpath
                    for fpath in pkf_files
                }
                for future in as_completed(futures):
                    results.extend(future.result())
                    if self._results_count >= self.max_results:
                        break
        else:
            for fpath in pkf_files:
                results.extend(self._search_file_bytes(fpath, pattern, encoding))
                if self._results_count >= self.max_results:
                    break
        
        return results[:self.max_results]
    
    def _search_case_insensitive(
        self,
        query_bytes: bytes,
        encoding: str,
        use_parallel: bool,
    ) -> List[SearchResult]:
        """Perform case-insensitive search by converting data to lowercase."""
        # For case-insensitive, we need to lowercase both query and data
        query_lower = query_bytes.lower()
        
        results = []
        pkf_files = self.find_pkf_files()
        
        for fpath in pkf_files:
            try:
                pkf_file = PKFFile.from_bytes(fpath.name, fpath.read_bytes())
                
                for entry in pkf_file.list_entries():
                    # Convert entry data to lowercase for comparison
                    data_lower = entry.raw_bytes.lower()
                    
                    # Find all occurrences
                    offset = 0
                    while offset < len(data_lower):
                        pos = data_lower.find(query_lower, offset)
                        if pos == -1:
                            break
                        
                        # Get original case match from original data
                        match_bytes = entry.raw_bytes[pos:pos + len(query_bytes)]
                        
                        result = self._create_result(
                            fpath, entry, pos, match_bytes, encoding=encoding
                        )
                        results.append(result)
                        self._results_count += 1
                        
                        if self._results_count >= self.max_results:
                            return results[:self.max_results]
                        
                        offset = pos + 1
            
            except Exception:
                # Skip files that can't be parsed
                continue
        
        return results[:self.max_results]
    
    def _search_regex_compiled(
        self,
        regex: re.Pattern,
        encoding: Optional[str] = None,
        use_parallel: bool = True,
    ) -> List[SearchResult]:
        """Search using compiled regex pattern."""
        results = []
        pkf_files = self.find_pkf_files()
        
        for fpath in pkf_files:
            try:
                pkf_file = PKFFile.from_bytes(fpath.name, fpath.read_bytes())
                
                for entry in pkf_file.list_entries():
                    # Find all regex matches
                    for match in regex.finditer(entry.raw_bytes):
                        result = self._create_result(
                            fpath, entry, match.start(), match.group(), encoding=encoding
                        )
                        results.append(result)
                        self._results_count += 1
                        
                        if self._results_count >= self.max_results:
                            return results[:self.max_results]
            
            except Exception:
                # Skip files that can't be parsed
                continue
        
        return results[:self.max_results]
    
    def _search_file_bytes(
        self,
        file_path: Path,
        pattern: bytes,
        encoding: Optional[str] = None,
    ) -> List[SearchResult]:
        """Search a single PKF file for byte pattern."""
        results = []
        
        try:
            pkf_file = PKFFile.from_bytes(file_path.name, file_path.read_bytes())
            
            for entry in pkf_file.list_entries():
                # Find all occurrences in this entry
                offset = 0
                while offset < len(entry.raw_bytes):
                    pos = entry.raw_bytes.find(pattern, offset)
                    if pos == -1:
                        break
                    
                    result = self._create_result(
                        file_path, entry, pos, pattern, encoding=encoding
                    )
                    results.append(result)
                    self._results_count += 1
                    
                    if self._results_count >= self.max_results:
                        return results
                    
                    offset = pos + 1
        
        except Exception:
            # Skip files that can't be parsed
            pass
        
        return results
    
    def _search_file_xor(
        self,
        file_path: Path,
        pattern: bytes,
        xor_key: int,
        encoding: Optional[str] = None,
    ) -> List[SearchResult]:
        """Search a single PKF file after XOR decoding."""
        results = []
        
        try:
            pkf_file = PKFFile.from_bytes(file_path.name, file_path.read_bytes())
            
            for entry in pkf_file.list_entries():
                # XOR decode the entry data
                decoded_data = xor_decode(entry.raw_bytes, xor_key)
                
                # Find all occurrences in decoded data
                offset = 0
                while offset < len(decoded_data):
                    pos = decoded_data.find(pattern, offset)
                    if pos == -1:
                        break
                    
                    result = self._create_result(
                        file_path, entry, pos, pattern, encoding=encoding, xor_key=xor_key
                    )
                    results.append(result)
                    self._results_count += 1
                    
                    if self._results_count >= self.max_results:
                        return results
                    
                    offset = pos + 1
        
        except Exception:
            # Skip files that can't be parsed
            pass
        
        return results
    
    def _create_result(
        self,
        file_path: Path,
        entry: PKFEntry,
        match_offset: int,
        match_bytes: bytes,
        encoding: Optional[str] = None,
        xor_key: Optional[int] = None,
    ) -> SearchResult:
        """Create a SearchResult with context extraction."""
        # Extract context
        start = max(0, match_offset - self.context_size)
        end = min(len(entry.raw_bytes), match_offset + len(match_bytes) + self.context_size)
        
        context_before = entry.raw_bytes[start:match_offset]
        context_after = entry.raw_bytes[match_offset + len(match_bytes):end]
        
        # If XOR key was used, decode context as well
        if xor_key is not None:
            context_before = xor_decode(context_before, xor_key)
            context_after = xor_decode(context_after, xor_key)
        
        return SearchResult(
            file_path=file_path,
            entry_index=entry.index,
            entry_offset=entry.offset,
            match_offset=match_offset,
            absolute_offset=entry.offset + match_offset,
            match_bytes=match_bytes,
            context_before=context_before,
            context_after=context_after,
            encoding=encoding,
            xor_key=xor_key,
        )


__all__ = ["PKFSearcher", "SearchResult"]