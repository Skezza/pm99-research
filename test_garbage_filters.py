"""Test the new garbage filters against reported problematic entries."""

# Garbage entries reported from the GUI
import pytest


garbage_entries = [
    "Dea8iaa",
    "ZorrillawHvaReal Valladolid, S.A.D.",
    "TtaEverton Football Club",
    "TvaManchester United F. C.e",
    "AaJaCa",
    "TvaLiverpool Football ClubI",
    "UxaAston Villa Football Club",
    "R~aTottenham Hotspur Football Clubs",
    "R|aWest Ham United Football Club",
    "RvaWimbledon Football Club",
    "TwaSheffield Wednesday FC",
    "UzaCoventry City Football Club",
    "U}aLeicester City Football Club",
    "RoaCrystal PalaceA",
    "TwaBarnsley Football Club",
    "ZaYa.a",
    "MaioNHvaSporting Clube de Braga!",
    "GomesNGvaC.F. Estrela da Amadora",
    "Football AssociationA/aaaaaa'a",
]


def _apply_filters(name):
    """Apply all the filters from load_teams to a name."""
    
    # Length checks
    if len(name) < 5 or len(name) > 60:
        return False, "Length check"
    
    # Must start with uppercase letter
    if not name[0].isupper():
        return False, "Not uppercase start"
    
    # Must have at least one letter
    if not any(c.isalpha() for c in name):
        return False, "No letters"
    
    # Reject if contains numbers (except specific patterns)
    if any(c.isdigit() for c in name):
        if not (name[0].isdigit() and ' ' in name):
            return False, "Contains digits"
    
    # ASCII ratio check
    ascii_ratio = sum(1 for c in name if 32 <= ord(c) < 127) / len(name)
    if ascii_ratio < 0.90:
        return False, f"ASCII ratio too low ({ascii_ratio:.2f})"
    
    # Reject if too many 'a's
    if name.count('a') > len(name) * 0.4:
        return False, f"Too many 'a's ({name.count('a')}/{len(name)})"
    
    # Reject 3-letter garbage prefixes like "Tva"
    if len(name) >= 4:
        prefix = name[:3]
        if (prefix[0].isupper() and 
            prefix[1].islower() and 
            prefix[2] == 'a' and
            len(prefix) == 3):
            return False, f"3-letter garbage prefix: {prefix}"
    
    # Check for embedded garbage (wHva pattern)
    words = name.split()
    for word in words:
        if len(word) > 3:
            for i in range(1, len(word) - 1):
                if word[i-1].islower() and word[i].isupper():
                    return False, f"Embedded garbage in '{word}'"
            
            # Also check for consecutive uppercase letters in middle
            for i in range(1, len(word) - 2):
                if (word[i-1].islower() and
                    word[i].isupper() and
                    word[i+1].isupper()):
                    return False, f"Consecutive uppercase in '{word}'"
    
    # Reject if has suspicious trailing garbage
    if len(name) > 10:
        tail = name[-10:]
        if '/' in tail or tail.count('a') >= 5:
            return False, f"Trailing garbage pattern"
    
    # 2-letter garbage prefixes
    garbage_prefixes = [
        'Aa', 'Ba', 'Ca', 'Da', 'Ea', 'Fa', 'Ga', 'Ha',
        'Ia', 'Ja', 'Ka', 'La', 'Ma', 'Na', 'Oa', 'Pa',
        'Qa', 'Ra', 'Sa', 'Ta', 'Ua', 'Va', 'Wa', 'Xa',
        'Ya', 'Za'
    ]
    
    if len(name) >= 3:
        two_char = name[:2]
        if two_char in garbage_prefixes:
            team_starts = ['FC', 'AC', 'AS', 'CF', 'CD', 'SC', 'FK', 'SK']
            third_part = name[2:4] if len(name) >= 4 else name[2:]
            if third_part not in team_starts:
                return False, f"2-letter garbage prefix: {two_char}"
    
    # Random character patterns
    if len(words) >= 3:
        single_char_count = sum(1 for w in words if len(w) <= 2)
        if single_char_count >= len(words) * 0.6:
            return False, "Too many single-char words"
    
    return True, "PASSED"


@pytest.mark.parametrize("name", garbage_entries)
def test_filters_reject_garbage(name):
    result, reason = _apply_filters(name)
    assert not result, f"Expected garbage name to be rejected but filter returned {reason}: {name}"


if __name__ == "__main__":
    print("Testing garbage filters on reported problematic entries:\n")
    
    passed = 0
    failed = 0
    
    for entry in garbage_entries:
        result, reason = _apply_filters(entry)
        status = "✓ REJECTED" if not result else "✗ PASSED"
        
        if not result:
            passed += 1
        else:
            failed += 1
            
        print(f"{status:12} | {entry:45} | {reason}")
    
    print(f"\n{'='*80}")
    print(f"Correctly Rejected: {passed}/{len(garbage_entries)}")
    print(f"Incorrectly Passed: {failed}/{len(garbage_entries)}")
    
    if failed == 0:
        print("\n✓ All garbage entries correctly rejected!")
    else:
        print(f"\n✗ {failed} garbage entries still passing filters")