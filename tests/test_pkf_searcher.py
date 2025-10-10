"""
Tests for PKF String Searcher functionality
"""

import pytest
from pathlib import Path
import tempfile
import shutil

from pm99_editor.pkf_searcher import PKFSearcher, SearchResult
from pm99_editor.pkf import PKFFile


@pytest.fixture
def temp_pkf_dir(tmp_path):
    """Create a temporary directory with test PKF files."""
    # Create a simple test PKF file with known content
    test_dir = tmp_path / "test_pkf"
    test_dir.mkdir()
    
    # Create PKF file with some test data
    test_data = b"Hello World! This is a test. Player: Beckham. Team: Manchester United."
    
    # Create a simple PKF structure (single entry)
    count = 1
    offset = 4 + count * 8  # header + TOC
    length = len(test_data)
    
    pkf_bytes = (
        count.to_bytes(4, 'little') +
        offset.to_bytes(4, 'little') +
        length.to_bytes(4, 'little') +
        test_data
    )
    
    pkf_file1 = test_dir / "test1.pkf"
    pkf_file1.write_bytes(pkf_bytes)
    
    # Create another PKF with different content
    test_data2 = b"Another test file with Beckham mentioned again."
    length2 = len(test_data2)
    
    pkf_bytes2 = (
        count.to_bytes(4, 'little') +
        offset.to_bytes(4, 'little') +
        length2.to_bytes(4, 'little') +
        test_data2
    )
    
    pkf_file2 = test_dir / "test2.pkf"
    pkf_file2.write_bytes(pkf_bytes2)
    
    return test_dir


def test_pkf_searcher_initialization(temp_pkf_dir):
    """Test PKF searcher initialization."""
    searcher = PKFSearcher(temp_pkf_dir)
    assert searcher.directory == temp_pkf_dir
    assert searcher.recursive is True
    assert searcher.max_results == 1000
    assert searcher.context_size == 32


def test_find_pkf_files(temp_pkf_dir):
    """Test finding PKF files in directory."""
    searcher = PKFSearcher(temp_pkf_dir)
    files = searcher.find_pkf_files()
    
    assert len(files) == 2
    assert all(f.suffix == ".pkf" for f in files)
    assert all(f.exists() for f in files)


def test_search_text_basic(temp_pkf_dir):
    """Test basic text search."""
    searcher = PKFSearcher(temp_pkf_dir)
    results = searcher.search_text("Beckham")
    
    assert len(results) == 2  # Found in both files
    assert all(isinstance(r, SearchResult) for r in results)
    assert all(b"Beckham" in r.match_bytes for r in results)


def test_search_text_case_insensitive(temp_pkf_dir):
    """Test case-insensitive text search."""
    searcher = PKFSearcher(temp_pkf_dir)
    
    # Search for lowercase when text has uppercase
    results = searcher.search_text("beckham", case_sensitive=False)
    assert len(results) == 2
    
    # Case-sensitive should find 0 (since we wrote "Beckham" not "beckham")
    results_sensitive = searcher.search_text("beckham", case_sensitive=True)
    assert len(results_sensitive) == 0


def test_search_hex(temp_pkf_dir):
    """Test hex pattern search."""
    searcher = PKFSearcher(temp_pkf_dir)
    
    # Search for "Beckham" in hex: 42 65 63 6B 68 61 6D
    results = searcher.search_hex("4265636B68616D")
    assert len(results) == 2
    assert all(b"Beckham" in r.match_bytes for r in results)


def test_search_regex(temp_pkf_dir):
    """Test regex pattern search."""
    searcher = PKFSearcher(temp_pkf_dir)
    
    # Search for "Team:" followed by any characters
    results = searcher.search_regex(b"Team: [A-Za-z ]+")
    assert len(results) >= 1
    assert any(b"Team:" in r.match_bytes for r in results)


def test_search_result_properties(temp_pkf_dir):
    """Test SearchResult properties."""
    searcher = PKFSearcher(temp_pkf_dir, context_size=10)
    results = searcher.search_text("Beckham")
    
    assert len(results) > 0
    result = results[0]
    
    # Check result properties
    assert result.file_path.exists()
    assert result.entry_index >= 0
    assert result.match_offset >= 0
    assert len(result.match_bytes) > 0
    assert len(result.context_before) <= 10
    assert len(result.context_after) <= 10


def test_search_result_format_preview(temp_pkf_dir):
    """Test result preview formatting."""
    searcher = PKFSearcher(temp_pkf_dir)
    results = searcher.search_text("Beckham")
    
    assert len(results) > 0
    result = results[0]
    
    preview = result.format_preview(width=16)
    assert isinstance(preview, str)
    assert len(preview) > 0
    # Should contain hex addresses
    assert "0x" in preview.lower() or any(c in preview for c in "0123456789ABCDEF")


def test_search_result_get_match_text(temp_pkf_dir):
    """Test getting match as decoded text."""
    searcher = PKFSearcher(temp_pkf_dir)
    results = searcher.search_text("Beckham")
    
    assert len(results) > 0
    result = results[0]
    
    text = result.get_match_text("utf-8")
    assert "Beckham" in text


def test_max_results_limit(temp_pkf_dir):
    """Test that max_results limit is respected."""
    searcher = PKFSearcher(temp_pkf_dir, max_results=1)
    results = searcher.search_text("e")  # Common letter, should find many
    
    # Should be limited to 1 result even though there are more matches
    assert len(results) <= 1


def test_search_nonexistent_pattern(temp_pkf_dir):
    """Test searching for pattern that doesn't exist."""
    searcher = PKFSearcher(temp_pkf_dir)
    results = searcher.search_text("NONEXISTENT_PATTERN_XYZ123")
    
    assert len(results) == 0


def test_invalid_hex_string():
    """Test that invalid hex strings raise errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        searcher = PKFSearcher(tmpdir)
        
        with pytest.raises(ValueError):
            searcher.search_hex("ZZZZ")  # Invalid hex
        
        with pytest.raises(ValueError):
            searcher.search_hex("ABC")  # Odd number of chars


def test_invalid_regex():
    """Test that invalid regex patterns raise errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        searcher = PKFSearcher(tmpdir)
        
        with pytest.raises(ValueError):
            searcher.search_regex("[invalid(regex")


def test_xor_search(temp_pkf_dir):
    """Test XOR-decoded search."""
    # Create a PKF with XOR-encoded data
    from pm99_editor.xor import xor_decode
    
    test_data = b"Secret message encoded with XOR"
    xor_key = 0x5A
    encoded_data = xor_decode(test_data, xor_key)  # XOR is symmetric
    
    # Create PKF with encoded data
    count = 1
    offset = 4 + count * 8
    length = len(encoded_data)
    
    pkf_bytes = (
        count.to_bytes(4, 'little') +
        offset.to_bytes(4, 'little') +
        length.to_bytes(4, 'little') +
        encoded_data
    )
    
    xor_file = temp_pkf_dir / "xor_test.pkf"
    xor_file.write_bytes(pkf_bytes)
    
    # Search with XOR decoding
    searcher = PKFSearcher(temp_pkf_dir)
    results = searcher.search_with_xor("Secret", xor_key, encoding="utf-8")
    
    assert len(results) >= 1
    assert results[0].xor_key == xor_key


def test_parallel_search_disabled(temp_pkf_dir):
    """Test that search works with parallel processing disabled."""
    searcher = PKFSearcher(temp_pkf_dir)
    results = searcher.search_text("Beckham", use_parallel=False)
    
    assert len(results) == 2


def test_context_size(temp_pkf_dir):
    """Test different context sizes."""
    # Small context
    searcher_small = PKFSearcher(temp_pkf_dir, context_size=5)
    results_small = searcher_small.search_text("Beckham")
    assert len(results_small[0].context_before) <= 5
    
    # Large context
    searcher_large = PKFSearcher(temp_pkf_dir, context_size=50)
    results_large = searcher_large.search_text("Beckham")
    assert len(results_large[0].context_before) <= 50


def test_recursive_vs_non_recursive(tmp_path):
    """Test recursive directory scanning."""
    # Create nested directory structure
    root = tmp_path / "root"
    root.mkdir()
    subdir = root / "sub"
    subdir.mkdir()
    
    # Create PKF in root
    test_data = b"Root file data"
    count = 1
    offset = 12
    pkf_root = root / "root.pkf"
    pkf_root.write_bytes(
        count.to_bytes(4, 'little') +
        offset.to_bytes(4, 'little') +
        len(test_data).to_bytes(4, 'little') +
        test_data
    )
    
    # Create PKF in subdirectory
    test_data2 = b"Sub file data"
    pkf_sub = subdir / "sub.pkf"
    pkf_sub.write_bytes(
        count.to_bytes(4, 'little') +
        offset.to_bytes(4, 'little') +
        len(test_data2).to_bytes(4, 'little') +
        test_data2
    )
    
    # Recursive search should find both
    searcher_rec = PKFSearcher(root, recursive=True)
    files_rec = searcher_rec.find_pkf_files()
    assert len(files_rec) == 2
    
    # Non-recursive should find only root
    searcher_non_rec = PKFSearcher(root, recursive=False)
    files_non_rec = searcher_non_rec.find_pkf_files()
    assert len(files_non_rec) == 1
    assert files_non_rec[0].parent == root


if __name__ == "__main__":
    pytest.main([__file__, "-v"])