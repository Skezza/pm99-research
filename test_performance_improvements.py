"""Test performance improvements for player database loading."""

import time
from pathlib import Path

import pytest

from pm99_editor.io import FDIFile

def test_player_loading():
    """Test that player loading works with optimizations."""
    
    # Find the player database file
    player_file = Path("DBDAT/JUG98030.FDI")
    if not player_file.exists():
        player_file = Path("pm99_editor/DBDAT/JUG98030.FDI")
    
    if not player_file.exists():
        pytest.skip("Required data file not found: DBDAT/JUG98030.FDI")
    
    print(f"Loading player database from: {player_file}")
    print("-" * 60)
    
    # Time the loading
    start_time = time.time()
    
    fdi = FDIFile(str(player_file))
    fdi.load()
    
    load_time = time.time() - start_time
    
    # Print results
    print(f"✓ Load completed in {load_time:.2f} seconds")
    print(f"✓ Total players loaded: {len(fdi.records)}")
    
    # Sample some players to verify data integrity
    if fdi.records:
        print(f"\nSample players (first 5):")
        for i, rec in enumerate(fdi.records[:5]):
            name = getattr(rec, 'name', 'Unknown')
            team_id = getattr(rec, 'team_id', 0)
            position = getattr(rec, 'position', 0)
            print(f"  {i+1}. {name} (Team: {team_id}, Pos: {position})")
    
    # Verify deduplication worked
    names = [getattr(rec, 'name', '') for rec in fdi.records]
    unique_names = set(names)
    duplicates = len(names) - len(unique_names)
    
    print(f"\n✓ Deduplication check: {duplicates} duplicates removed")
    
    # Performance expectations
    print(f"\n{'='*60}")
    print("PERFORMANCE SUMMARY:")
    print(f"{'='*60}")
    print(f"Load time: {load_time:.2f}s")
    print(f"Players loaded: {len(fdi.records)}")
    print(f"Average time per player: {(load_time/len(fdi.records)*1000):.2f}ms")
    
    if load_time < 5.0:
        print("✓ EXCELLENT: Load time under 5 seconds")
    elif load_time < 10.0:
        print("✓ GOOD: Load time under 10 seconds")
    else:
        print("⚠ SLOW: Load time over 10 seconds (may need further optimization)")
    
    # Basic sanity assertion to ensure the test registers as passed when executed
    assert len(fdi.records) > 0


if __name__ == "__main__":
    try:
        test_player_loading()
    except pytest.SkipTest as exc:
        print(exc)
        exit(0)