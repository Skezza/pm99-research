#!/usr/bin/env python3
"""
Parse biography records by looking for attribute names and extracting numbers
"""

from pathlib import Path
import re

def parse_biography_stats(text: str) -> dict:
    """
    Parse stats from biography text by looking for patterns like:
    "SPEED: 66" or "66 speed" or "speed 66"
    """
    stats = {}
    
    # Attribute names and their expected patterns
    attributes = {
        'SPEED': 'SPEED',
        'STAMINA': 'STAMINA',
        'AGGRESSION': 'AGGRESSION',
        'QUALITY': 'QUALITY',
        'FITNESS': 'FITNESS',
        'MORAL': 'MORAL',
        'HANDLING': 'HANDLING',
        'PASSING': 'PASSING',
        'DRIBBLING': 'DRIBBLING',
        'HEADING': 'HEADING',
        'TACKLING': 'TACKLING',
        'SHOOTING': 'SHOOTING'
    }
    
    # For each attribute, look for the name followed by a number
    for attr_name in attributes:
        # Pattern: attribute name (case insensitive) followed by colon and number
        pattern1 = rf'{attr_name}\s*:\s*(\d+)'
        # Pattern: number followed by attribute name
        pattern2 = rf'(\d+)\s+{attr_name}'
        # Pattern: attribute name in text near number
        pattern3 = rf'{attr_name}.*?(\d+)'
        
        for pattern in [pattern1, pattern2, pattern3]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = int(match.group(1))
                    if 0 <= value <= 100:
                        stats[attr_name] = value
                        break
                except ValueError:
                    continue
    
    # Age pattern
    age_pattern = r'(?:age|born)\s*:?\s*(\d{1,2})'
    age_match = re.search(age_pattern, text, re.IGNORECASE)
    if age_match:
        stats['AGE'] = int(age_match.group(1))
    
    # Rating pattern
    rating_pattern = r'(?:rating|overall)\s*:?\s*(\d{1,3})'
    rating_match = re.search(rating_pattern, text, re.IGNORECASE)
    if rating_match:
        stats['RATING'] = int(rating_match.group(1))
    
    # Position pattern
    pos_patterns = {
        'Goalkeeper': r'(?:goalkeeper|keeper)',
        'Defender': r'(?:defender|back)',
        'Midfielder': r'(?:midfielder|mid)',
        'Forward': r'(?:forward|striker)'
    }
    for pos_name, pattern in pos_patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            stats['POSITION'] = pos_name
            break
    
    # Height pattern (feet inches)
    height_pattern = r'(\d+)\'?\s*(\d?)?"?'
    height_match = re.search(height_pattern, text)
    if height_match:
        feet = int(height_match.group(1))
        inches = int(height_match.group(2)) if height_match.group(2) else 0
        stats['HEIGHT'] = f"{feet}'{inches}\""
    
    # Weight pattern (stone pounds)
    weight_pattern = r'(\d+)\s*st\s*(\d+)'
    weight_match = re.search(weight_pattern, text, re.IGNORECASE)
    if weight_match:
        stone = int(weight_match.group(1))
        pounds = int(weight_match.group(2))
        stats['WEIGHT'] = f"{stone}st {pounds}lb"
    
    # Nationality
    nationality_pattern = r'(?:nationality|nation)\s*:?\s*([A-Z\s]+)'
    nat_match = re.search(nationality_pattern, text, re.IGNORECASE)
    if nat_match:
        stats['NATIONALITY'] = nat_match.group(1).strip()
    
    return stats

def main():
    bin_path = 'thorne_full_decoded.bin'
    if not Path(bin_path).exists():
        print(f"File not found: {bin_path}")
        return
    
    with open(bin_path, 'rb') as f:
        data = f.read()
    
    text = data.decode('latin-1', errors='ignore')
    print(f"Analyzing {len(text)} characters of biography text")
    
    stats = parse_biography_stats(text)
    
    print(f"\n📊 Extracted Stats:")
    for key, value in stats.items():
        print(f"{key}: {value}")
    
    # Validation with known THORNE stats
    known_thorne = {
        'AGE': 25,
        'RATING': 70,
        'POSITION': 'Forward',
        'HEIGHT': "6'0\"",
        'WEIGHT': "11st 4lb",
        'NATIONALITY': 'England'
    }
    
    print(f"\n✅ Matches with known THORNE stats:")
    for key, known_val in known_thorne.items():
        if key in stats and stats[key] == known_val:
            print(f"  {key}: ✅ {stats[key]}")
        else:
            print(f"  {key}: ❌ Expected {known_val}, got {stats.get(key, 'Not found')}")
    
    # Attributes
    print(f"\n📈 Attributes:")
    attr_count = 0
    for attr in ['SPEED', 'STAMINA', 'AGGRESSION', 'QUALITY', 'FITNESS', 'MORAL',
                 'HANDLING', 'PASSING', 'DRIBBLING', 'HEADING', 'TACKLING', 'SHOOTING']:
        if attr in stats:
            print(f"  {attr}: {stats[attr]}")
            attr_count += 1
        else:
            print(f"  {attr}: Not found")
    
    print(f"\n📊 Summary:")
    print(f"Total attributes found: {attr_count}/12")
    print(f"Core stats extracted: {len([k for k in known_thorne if k in stats])}/6")
    
    if attr_count >= 8:
        print(f"\n💡 The biography text contains structured stats!")
        print(f"Pattern: Attribute names followed by numbers")
        print(f"This confirms gameplay data is stored as formatted text in biography records")
    else:
        print(f"\n⚠️  Only {attr_count}/12 attributes found - may need refined patterns")

if __name__ == '__main__':
    main()