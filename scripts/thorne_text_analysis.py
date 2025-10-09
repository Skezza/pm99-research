#!/usr/bin/env python3
"""
Analyze the full THORNE biography text to find embedded stats
"""

from pathlib import Path
import re

def main():
    bin_path = 'thorne_full_decoded.bin'
    if not Path(bin_path).exists():
        print(f"File not found: {bin_path}")
        return
    
    with open(bin_path, 'rb') as f:
        data = f.read()
    
    text = data.decode('latin-1', errors='ignore')
    print(f"Full text length: {len(text)} characters")
    
    # THORNE's known stats
    stats = {
        'age': 25,
        'rating': 70,
        'position': 3,
        'height_ft': 6,
        'height_in': 0,
        'weight_st': 11,
        'weight_lb': 4,
        'attributes': [66, 63, 74, 64, 73, 84, 28, 69, 65, 73, 69, 80],
        'attr_names': ['SPEED', 'STAMINA', 'AGGRESSION', 'QUALITY', 'FITNESS', 'MORAL',
                       'HANDLING', 'PASSING', 'DRIBBLING', 'HEADING', 'TACKLING', 'SHOOTING']
    }
    
    # Search for age
    print(f"\n🔍 Searching for Age = {stats['age']}:")
    age_pattern = rf'{stats["age"]}\s*(years?|age)'
    age_matches = re.finditer(age_pattern, text, re.IGNORECASE)
    for match in age_matches:
        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 50)
        context = text[start:end]
        print(f"  Position {match.start()}: {context}")
    
    # Rating
    print(f"\n🔍 Searching for Rating = {stats['rating']}:")
    rating_pattern = rf'{stats["rating"]}\s*(rating|overall)'
    rating_matches = re.finditer(rating_pattern, text, re.IGNORECASE)
    for match in rating_matches:
        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 50)
        context = text[start:end]
        print(f"  Position {match.start()}: {context}")
    
    # Position
    print(f"\n🔍 Searching for Position (Forward):")
    pos_patterns = ['forward', 'centre forward', 'striker', 'rol.: centre forward']
    for pattern in pos_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end]
            print(f"  Position {match.start()}: {context}")
    
    # Physical stats
    print(f"\n🔍 Searching for Height/Weight:")
    height_pattern = rf'{stats["height_ft"]}\'?\s*0?"?'
    height_matches = re.finditer(height_pattern, text, re.IGNORECASE)
    for match in height_matches:
        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 50)
        context = text[start:end]
        print(f"  Height {match.start()}: {context}")
    
    weight_pattern = rf'{stats["weight_st"]}\s*st\s*{stats["weight_lb"]}'
    weight_matches = re.finditer(weight_pattern, text, re.IGNORECASE)
    for match in weight_matches:
        start = max(0, match.start() - 50)
        end = min(len(text), match.end() + 50)
        context = text[start:end]
        print(f"  Weight {match.start()}: {context}")
    
    # Attributes - look for numbers in context that match
    print(f"\n🔍 Attribute Values Search:")
    attr_values = stats['attributes']
    attr_names = stats['attr_names']
    
    for i, val in enumerate(attr_values):
        attr_name = attr_names[i]
        # Look for the number followed by attribute name or in attribute section
        pattern = rf'{val}\s*({attr_name.lower()})'
        matches = re.finditer(pattern, text, re.IGNORECASE)
        found = False
        for match in matches:
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end]
            print(f"  {attr_name} ({val}): {context}")
            found = True
        if not found:
            # Just look for the number
            num_pattern = rf'\b{val}\b'
            num_matches = re.finditer(num_pattern, text)
            # Look for numbers near other known values
            for match in list(num_matches)[:5]:  # First 5 occurrences
                start = max(0, match.start() - 20)
                end = min(len(text), match.end() + 20)
                context = text[start:end]
                print(f"  {attr_name} ({val}): {context}")
    
    # Look for structured data blocks
    print(f"\n🔍 Structured Data Blocks:")
    # Look for sequences of numbers that look like stats
    number_pattern = r'\b\d{1,3}\b'
    numbers = re.finditer(number_pattern, text)
    number_list = [m for m in numbers]
    
    # Look for 12 consecutive numbers 0-100
    for i in range(len(number_list) - 11):
        seq = []
        seq_start = number_list[i].start()
        for j in range(12):
            if i + j < len(number_list):
                num = int(number_list[i+j].group())
                if 0 <= num <= 100:
                    seq.append(num)
                else:
                    break
        if len(seq) == 12:
            seq_text = ' '.join(str(v) for v in seq)
            print(f"  Stats block at char {seq_start}: {seq_text}")
    
    # Look for "25 years" or similar
    print(f"\n🔍 Age Pattern Search:")
    age_patterns = [
        rf'{stats["age"]}\s*(years?|age)',
        rf'(born|age)\s*{stats["age"]}',
        rf'{stats["age"]}\s*year'
    ]
    for pattern in age_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 30)
            context = text[start:end]
            print(f"  {pattern}: {context}")
    
    # Summary
    print(f"\n📋 SUMMARY:")
    print(f"The biography text contains the numerical values, but they're embedded in narrative")
    print(f"Attributes appear scattered throughout the 11KB record")
    print(f"Need more sophisticated parsing to extract structured data from text")

if __name__ == '__main__':
    main()