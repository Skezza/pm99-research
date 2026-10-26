"""Detect newly increased exact source-name/DOB collisions before a reserve edit.

This is a regression guard, not historical identity certification. It does not
merge aliases, resolve loans or declare existing candidates legitimate.
"""
from collections import defaultdict
from datetime import date
import hashlib
import json
import re
import unicodedata


def _groups(package):
    groups = defaultdict(list)
    for actor in package['players']:
        name = actor.get('source_name')
        birth = actor.get('facts', {}).get('birth_date')
        if not isinstance(name, str) or not isinstance(birth, str):
            continue
        name = re.sub(r'^#\d+\s*', '', name).strip()
        words = name.split()
        # A native initial/surname alone cannot establish a full identity.
        if len(words) < 2 or len(words[0].rstrip('.')) < 2:
            continue
        try:
            date.fromisoformat(birth)
        except ValueError:
            continue
        normalized = re.sub(r'[^a-z0-9]', '', unicodedata.normalize(
            'NFKD', name).encode('ascii', 'ignore').decode().casefold())
        groups[normalized, birth].append({
            'player_id': actor['id'], 'carrier_id': actor['carrier_id'],
            'club_id': actor['club_id'], 'source_name': name})
    return groups


def new_collisions(before, after):
    old, new = _groups(before), _groups(after)
    result = []
    for key, actors in sorted(new.items()):
        if len(actors) <= max(1, len(old.get(key, []))):
            continue
        identity = json.dumps(key, separators=(',', ':')).encode()
        result.append({
            'case_id': 'new-source-person-collision-' + hashlib.sha256(identity).hexdigest()[:20],
            'normalized_source_name': key[0], 'birth_date': key[1],
            'before_count': len(old.get(key, [])), 'after_count': len(actors),
            'actors': sorted(actors, key=lambda a: a['carrier_id'])})
    return result


def require_no_new_collisions(before, after):
    collisions = new_collisions(before, after)
    if collisions:
        raise ValueError('new source-person collisions require dated disposition: '
                         + ', '.join(row['case_id'] for row in collisions))
    return {'new_exact_source_name_DOB_collisions': 0,
            'limits': 'Full source names and dated biographies only; unchanged '
                      'duplicates, aliases, missing facts and loans are not cleared.'}
