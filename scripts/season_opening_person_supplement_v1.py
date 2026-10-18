"""Join published opening-sheet IDs to independently reparsed squad DOBs.

Older retired players can be absent from the pinned player dataset. Their
original match-sheet IDs still exist. An exact full-name join at the same club
plus a single independently published DOB can supply that missing identity.
Initials, ambiguous names/IDs, conflicting dates and unverified captures cannot.
This establishes identity only, never opening ownership or a transfer history.
"""
from __future__ import annotations

import collections
import copy
import datetime as dt
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer

POLICY = 'original-opening-full-name-and-independent-squad-DOB-v1'


def extend(people, clubs, evidence, captures, verifier):
    known = collections.defaultdict(dict)
    for entries in people.values():
        for id, person in entries.items():
            known[id][person['birth_date']] = person
    claims = collections.defaultdict(set)
    proofs = collections.defaultdict(list)
    names = {}
    for club in clubs:
        opening = evidence.get(club['id'])
        if opening is None:
            continue
        group = roster.club_group(club)
        labels = roster.club_names(group, club['name'], club.get('full_name', ''))
        matching = [r for r in captures if roster.source_group(r['country_catalog']) == group
                    and roster.normalise(r['club_name']) in labels]
        facts = collections.defaultdict(set)
        fact_proofs = collections.defaultdict(list)
        for row in matching:
            proof = verifier.verify(row)
            if proof['status'] != 'raw-source-reparsed':
                continue
            for player in row['players']:
                dob = player.get('birth_date')
                name = player.get('name')
                if not isinstance(dob, str) or not isinstance(name, str):
                    continue
                try:
                    dt.date.fromisoformat(dob)
                except ValueError:
                    continue
                key = transfer._normalise(name)
                facts[key].add(dob)
                fact_proofs[(key, dob)].append(proof)
        for field in ('starting_xi', 'substitutes'):
            for raw_id, name in opening[field].items():
                key = transfer._normalise(name)
                # A short name has no invented initial expansion. Exact
                # original labels are used; all conflicting DOBs stay visible.
                for dob in facts.get(key, ()):
                    id = int(raw_id)
                    claims[(key, dob)].add(id)
                    names[(key, dob)] = name
                    proofs[(key, dob, id)].extend(fact_proofs[(key, dob)])
    all_dates = collections.defaultdict(set)
    for (name, dob), ids in claims.items():
        for id in ids:
            all_dates[id].add(dob)
    # The pinned index can be large. Copy only its maps; unchanged person
    # records are read-only, and every added alias gets its own record below.
    result = {key: dict(entries) for key, entries in people.items()}
    added, refused = [], []
    supplemented_people = {}
    for key, ids in sorted(claims.items()):
        name, dob = key
        id = next(iter(ids)) if len(ids) == 1 else None
        prior_ids = set(result.get(key, {}))
        if (id is None or len(all_dates[id]) != 1 or prior_ids - {id}
                or (known.get(id) and set(known[id]) != {dob})):
            refused.append({'name': names[key], 'birth_date': dob, 'published_ids': sorted(ids),
                'reason': 'ambiguous-published-id-or-independent-DOB-conflict'})
            continue
        if id in result.get(key, {}):
            continue
        if id not in supplemented_people:
            supplemented_people[id] = (copy.deepcopy(known[id][dob]) if known.get(id) else {
                'source_player_id': id, 'name': names[key], 'given_name': None,
                'family_name': None, 'birth_date': dob,
                'source_profile_url': f'https://www.transfermarkt.com/-/profil/spieler/{id}'})
        person = copy.deepcopy(supplemented_people[id])
        result.setdefault(key, {})[id] = person
        added.append({'name': names[key], 'birth_date': dob, 'source_player_id': id,
            'basis': 'original-opening-matchsheet-full-name-plus-independent-raw-squad-DOB',
            'squad_proofs': proofs[(name, dob, id)]})
    return result, {'added_identities': added, 'refused_identity_claims': refused,
                    'ownership_established': False}
