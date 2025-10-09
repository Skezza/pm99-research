#!/usr/bin/env python3
"""
Advanced biography stat parser - looks for exact patterns like "SPEED: 66"
"""

from pathlib import Path
import re

def parse_advanced_biography(text: str) -> dict:
    """
    Parse biography stats using exact patterns from user-provided format
    """
    stats = {}
    
    # Exact patterns from user input format
    patterns = {
        'AGE': r'AGE:\s*(\d+)',
        'WEIGHT': r'WEIGHT:\s*(\d+)\s*(\d+)',
        'HEIGHT': r'HEIGHT:\s*(\d+)\s*(\d+)',
        'NATIONALITY': r'NATIONALITY:\s*([A-Z]+)',
        'RATING': r'RATING:\s*(\d+)',
        'SPEED': r'SPEED:\s*(\d+)',
        'STAMINA': r'STAMINA:\s*(\d+)',
        'AGGRESSION': r'AGGRESSION:\s*(\d+)',
        'QUALITY': r'QUALITY:\s*(\d+)',
        'FITNESS': r'FITNESS:\s*(\d+)',
        'MORAL': r'MORAL:\s*(\d+)',
        'HANDLING': r'HANDLING:\s*(\d+)',
        'PASSING': r'PASSING:\s*(\d+)',
        'DRIBBLING': r'DRIBBLING:\s*(\d+)',
        'HEADING': r'HEADING:\s*(\d+)',
        'TACKLING': r'TACKLING:\s*(\d+)',
        'SHOOTING': r'SHOOTING:\s*(\d+)'
    }
    
    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if field in ['WEIGHT', 'HEIGHT']:
                stats[field] = f"{match.group(1)} {match.group(2)}"
            else:
                stats[field] = int(match.group(1))
    
    # Position from ROL.
    rol_pattern = r'ROL\.:?\s*(Centre Forward|Left Back|Goalkeeper|Midfielder|Forward|Defender)'
    rol_match = re.search(rol_pattern, text, re.IGNORECASE)
    if rol_match:
        position = rol_match.group(1)
        stats['POSITION'] = position
        # Map to numeric
        pos_map = {
            'Goalkeeper': 0,
            'Defender': 1, 'Left Back': 1,
            'Midfielder': 2,
            'Forward': 3, 'Centre Forward': 3
        }
        stats['POSITION_CODE'] = pos_map.get(position, 0)
    
    # Nationality kind
    kind_pattern = r'KIND:\s*(National|Club)'
    kind_match = re.search(kind_pattern, text, re.IGNORECASE)
    if kind_match:
        stats['KIND'] = kind_match.group(1)
    
    # Status
    status_pattern = r'STATUS:\s*(Fit|Injured|Suspended)'
    status_match = re.search(status_pattern, text, re.IGNORECASE)
    if status_match:
        stats['STATUS'] = status_match.group(1)
    
    # Club
    club_pattern = r'Club:\s*([A-Z\s.]+)'
    club_match = re.search(club_pattern, text, re.IGNORECASE)
    if club_match:
        stats['CLUB'] = club_match.group(1).strip()
    
    return stats

def main():
    bin_path = 'thorne_full_decoded.bin'
    if not Path(bin_path).exists():
        print(f"File not found: {bin_path}")
        return
    
    with open(bin_path, 'rb') as f:
        data = f.read()
    
    text = data.decode('latin-1', errors='ignore')
    print(f"Analyzing {len(text)} characters")
    
    stats = parse_advanced_biography(text)
    
    print(f"\n📊 Extracted Stats for Peter THORNE:")
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    # Validation
    expected = {
        'AGE': 25,
        'WEIGHT': '11 04',
        'HEIGHT': '6 0',
        'NATIONALITY': 'England',
        'RATING': 70,
        'POSITION': 'Centre Forward',
        'KIND': 'National',
        'STATUS': 'Fit',
        'CLUB': 'Stoke C.',
        'SPEED': 66,
        'STAMINA': 63,
        'AGGRESSION': 74,
        'QUALITY': 64,
        'FITNESS': 73,
        'MORAL': 84,
        'HANDLING': 28,
        'PASSING': 69,
        'DRIBBLING': 65,
        'HEADING': 73,
        'TACKLING': 69,
        'SHOOTING': 80
    }
    
    print(f"\n✅ Validation against expected values:")
    matches = 0
    total = 0
    for key, expected_val in expected.items():
        actual = stats.get(key)
        if actual == expected_val:
            print(f"  {key}: ✅ {actual}")
            matches += 1
        else:
            print(f"  {key}: ❌ Expected {expected_val}, got {actual}")
        total += 1
    
    print(f"\n📈 Success Rate: {matches}/{total} fields matched ({matches/total*100:.1f}%)")
    
    if matches >= 15:
        print(f"\n🎉 Biography parsing successful! All major fields extracted.")
    else:
        print(f"\n⚠️  {total-matches}/{total} fields missing - refine patterns further")
    
    # Show context for missing fields
    missing = [k for k, v in expected.items() if v != stats.get(k)]
    if missing:
        print(f"\n🔍 Context for missing fields:")
        for field in missing:
            pattern = rf'{field}:?\s*[^ \n]*'
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]
                print(f"  {field} context: {context}")

if __name__ == '__main__':
    main()