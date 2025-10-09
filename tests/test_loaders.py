"""
Tests for the shared loaders module.

These tests verify that the team and coach loaders correctly:
1. Load data from FDI files
2. Apply strict validation filters
3. Reject garbage entries
4. Return only valid, deduplicated records
"""

import pytest
from pathlib import Path
from pm99_editor.loaders import load_teams, load_coaches


def test_load_teams():
    """Test team loading with strict filtering."""
    team_file = "DBDAT/EQ98030.FDI"
    
    if not Path(team_file).exists():
        pytest.skip(f"Team file not found: {team_file}")
    
    # Load teams
    teams = load_teams(team_file)
    
    # Should have found teams
    assert len(teams) > 0, "No teams loaded"
    
    # All teams should have valid names
    for offset, team in teams:
        name = getattr(team, 'name', None)
        assert name is not None, f"Team at offset {offset:x} has no name"
        assert name not in ("Unknown Team", "Parse Error", ""), \
            f"Team at offset {offset:x} has placeholder name: {name}"
        
        # Length checks
        assert 4 <= len(name) <= 60, \
            f"Team name length out of range: {len(name)} chars: {name}"
        
        # Must start with uppercase
        assert name[0].isupper(), \
            f"Team name doesn't start with uppercase: {name}"
        
        # Must contain letters
        assert any(c.isalpha() for c in name), \
            f"Team name has no letters: {name}"
        
        # ASCII ratio
        ascii_count = sum(1 for c in name if 32 <= ord(c) < 127)
        ascii_ratio = ascii_count / len(name)
        assert ascii_ratio >= 0.85, \
            f"Team name has low ASCII ratio ({ascii_ratio:.2f}): {name}"
        
        # Not too many 'a's
        a_ratio = name.count('a') / len(name)
        assert a_ratio <= 0.5, \
            f"Team name has too many 'a's ({a_ratio:.2f}): {name}"
    
    # Check for deduplication (no duplicate names)
    names = [getattr(team, 'name', None) for _, team in teams]
    unique_names = set(names)
    assert len(names) == len(unique_names), \
        f"Duplicate team names found: {len(names)} total, {len(unique_names)} unique"
    
    print(f"\n✓ Loaded {len(teams)} valid teams")
    
    # Print first 10 teams as sample
    print("\nSample teams:")
    for offset, team in teams[:10]:
        name = getattr(team, 'name', 'Unknown')
        team_id = getattr(team, 'team_id', 0)
        print(f"  {name} (ID: {team_id}, offset: 0x{offset:x})")


def test_load_coaches():
    """Test coach loading with strict filtering."""
    coach_file = "DBDAT/ENT98030.FDI"
    
    if not Path(coach_file).exists():
        pytest.skip(f"Coach file not found: {coach_file}")
    
    # Load coaches
    coaches = load_coaches(coach_file)
    
    # Should have found coaches
    assert len(coaches) > 0, "No coaches loaded"
    
    # All coaches should have valid names
    for offset, coach in coaches:
        name = getattr(coach, 'full_name', '')
        assert name, f"Coach at offset {offset:x} has no name"
        assert name not in ("Unknown Coach", "Parse Error", ""), \
            f"Coach at offset {offset:x} has placeholder name: {name}"
        
        # Length checks
        assert 6 <= len(name) <= 40, \
            f"Coach name length out of range: {len(name)} chars: {name}"
        
        # Must start with uppercase and have space
        assert name[0].isupper(), \
            f"Coach name doesn't start with uppercase: {name}"
        assert ' ' in name, \
            f"Coach name has no space: {name}"
        
        # Check name parts
        parts = name.split()
        assert len(parts) >= 2, \
            f"Coach name has less than 2 parts: {name}"
        
        for part in parts:
            assert 2 <= len(part) <= 20, \
                f"Coach name part length out of range: {part} in {name}"
            assert part[0].isupper(), \
                f"Coach name part doesn't start with uppercase: {part} in {name}"
        
        # ASCII ratio
        ascii_count = sum(1 for ch in name if 32 <= ord(ch) < 127)
        ascii_ratio = ascii_count / len(name)
        assert ascii_ratio >= 0.85, \
            f"Coach name has low ASCII ratio ({ascii_ratio:.2f}): {name}"
        
        # Not too many 'a's
        a_ratio = name.count('a') / len(name)
        assert a_ratio <= 0.6, \
            f"Coach name has too many 'a's ({a_ratio:.2f}): {name}"
    
    # Check for deduplication (no duplicate names)
    names = [getattr(coach, 'full_name', '') for _, coach in coaches]
    unique_names = set(names)
    assert len(names) == len(unique_names), \
        f"Duplicate coach names found: {len(names)} total, {len(unique_names)} unique"
    
    print(f"\n✓ Loaded {len(coaches)} valid coaches")
    
    # Print first 10 coaches as sample
    print("\nSample coaches:")
    for offset, coach in coaches[:10]:
        name = getattr(coach, 'full_name', 'Unknown')
        print(f"  {name} (offset: 0x{offset:x})")


def test_teams_reject_garbage():
    """Verify that garbage team entries are rejected."""
    team_file = "DBDAT/EQ98030.FDI"
    
    if not Path(team_file).exists():
        pytest.skip(f"Team file not found: {team_file}")
    
    teams = load_teams(team_file)
    
    # Check that no garbage prefixes are present (unless they have team words)
    garbage_prefixes = [
        'Baaa', 'Caaa', 'Daaa', 'Eaaa', 'Faaa', 'Gaaa',
        'Haaa', 'Iaaa', 'Jaaa', 'Kaaa', 'Laaa', 'Maaa'
    ]
    
    for offset, team in teams:
        name = getattr(team, 'name', '')
        for prefix in garbage_prefixes:
            if name.startswith(prefix):
                # If it starts with garbage prefix, must contain team words
                team_words = [
                    'FC', 'United', 'City', 'Town', 'Athletic',
                    'Football', 'Club', 'Rovers', 'Wanderers'
                ]
                assert any(word in name for word in team_words), \
                    f"Garbage prefix '{prefix}' in team name without team words: {name}"


def test_coaches_reject_garbage():
    """Verify that the most obvious garbage coach entries are rejected."""
    coach_file = "DBDAT/ENT98030.FDI"
    
    if not Path(coach_file).exists():
        pytest.skip(f"Coach file not found: {coach_file}")
    
    coaches = load_coaches(coach_file)
    
    # Verify we have a reasonable number (not too many garbage entries)
    assert 100 <= len(coaches) <= 500, \
        f"Coach count out of reasonable range: {len(coaches)}"
    
    # Check that obvious non-name phrases are filtered out
    obvious_garbage = [
        'premier league', 'first division', 'world cup', 'european cup',
        'league cup', 'champions league'
    ]
    
    for offset, coach in coaches:
        name = getattr(coach, 'full_name', '').lower()
        for garbage in obvious_garbage:
            assert garbage not in name, \
                f"Obvious garbage phrase '{garbage}' found in coach name: {name}"


if __name__ == "__main__":
    # Run tests directly
    print("Testing team loader...")
    test_load_teams()
    
    print("\n" + "="*60)
    print("Testing coach loader...")
    test_load_coaches()
    
    print("\n" + "="*60)
    print("Testing garbage rejection for teams...")
    test_teams_reject_garbage()
    
    print("\n" + "="*60)
    print("Testing garbage rejection for coaches...")
    test_coaches_reject_garbage()
    
    print("\n" + "="*60)
    print("✓ All loader tests passed!")