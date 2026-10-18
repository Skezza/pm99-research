"""Positive published squad membership plus strict dated opening ownership.

A retained owner need not have appeared in the opening match. This policy is
only an alternative to the existing missing-matchday-positive refusal, never
to an ambiguous person, missing fixture, contradictory appearance or incomplete
transfer history. The annual source supplies positive membership; independently
bracketing transfers establish the date. Annual membership alone proves neither.
No recipe or native game writes occur here.
"""
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer

POLICY = 'original-full-name-DOB-squad-membership-and-all-opening-transfer-brackets-v1'
BASIS = 'positive-reparsed-squad-membership-and-consistent-dated-opening-transfer-brackets'


def decide(candidates, evidence, person, events, clubs, captures, verifier, people):
    """Reparse a dated reserve owner's positive source; never use absence.

    Return the normal decision unchanged when it already succeeds. A new
    decision also returns its independently reconstructed annual witness.
    """
    from scripts import season_duplicate_ownership_plan_v1 as planner
    winner, reason = planner.decide_owner(candidates, evidence, person, events)
    if winner is not None or reason != 'dated-owner-lacks-positive-opening-matchday-person-id':
        return winner, reason, None
    sources = [evidence[p['club_id']] for p in candidates]
    from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
    if any(not soccerbase.verified_date(s) for s in sources):
        return None, 'dated-reserve-owner-needs-independently-published-opening-dates', None
    person_id = str(person['source_player_id'])
    if any(person_id in set(s['starting_xi']) | set(s['substitutes']) for s in sources):
        return None, 'contradictory-positive-opening-matchday-member-protected', None
    intervals = [transfer.transfer_interval(events, s['date']) for s in sources]
    # The base decision checks every interval, not merely the retained club's.
    # Keep an explicit check here so this helper cannot silently broaden after
    # an unrelated future change to the base refusal reasons.
    if (any(i['status'] != 'recorded-entry-and-exit-bracket-fixture' for i in intervals)
            or len({i['source_owner_club_id'] for i in intervals}) != 1):
        return None, 'dated-reserve-owner-needs-all-consistent-opening-brackets', None
    owner_id = intervals[0]['source_owner_club_id']
    matches = [p for p in candidates if evidence[p['club_id']]['source_club_id'] == owner_id]
    if len(matches) != 1:
        return None, 'dated-owner-not-one-unique-represented-club', None
    winner = matches[0]
    if transfer.unique_person(winner, people) != person:
        return None, 'dated-reserve-owner-native-person-does-not-match-bound-full-name-DOB', None
    club = clubs[winner['club_id']]
    names = roster.club_names(roster.club_group(club), club['name'], club.get('full_name', ''))
    witnesses = []
    for capture in sorted(captures, key=lambda c: (c['source_path'], c['club_name'])):
        if (roster.source_group(capture['country_catalog']) != roster.club_group(club)
                or roster.normalise(capture['club_name']) not in names):
            continue
        proof = verifier.verify(capture)
        if proof['status'] != 'raw-source-reparsed':
            continue
        matching_rows = [raw for raw in capture['players'] if
            transfer.unique_person({'name': raw['name'], 'facts': raw}, people) == person]
        if len(matching_rows) > 1:
            return None, 'dated-reserve-owner-has-ambiguous-published-squad-membership', None
        if matching_rows:
            witnesses.append({'source_player': matching_rows[0], 'source_person': person,
                'source_capture': {k: capture[k] for k in ('source_path', 'source_sha256', 'club_name')},
                'raw_evidence': proof, 'source_club_id': owner_id,
                'opening_dates': sorted({s['date'] for s in sources}), 'policy': POLICY})
    if not witnesses:
        return None, 'dated-reserve-owner-lacks-reparsed-full-name-DOB-squad-membership', None
    return winner, BASIS, witnesses[0]


def validate_binding(plan):
    """An annual-owner claim requires explicit original-input authorisation."""
    uses = any(r.get('ownership_basis') == BASIS or 'retained_owner_squad_membership' in r
               for r in plan.get('updates', []))
    enabled = plan.get('allow_dated_reserve_owners', False)
    bindings = plan.get('bindings', {})
    if not enabled and not uses and 'dated_reserve_owner_policy' not in bindings:
        return
    if (not enabled or bindings.get('dated_reserve_owner_policy') != POLICY
            or not bindings.get('opening_person_supplement_policy')
            or not bindings.get('published_person_supplement')
            or not bindings.get('published_transfer_supplement')):
        raise ValueError('dated reserve owner policy lacks explicit bound original person/history inputs')
    for row in plan.get('updates', []):
        if (row.get('ownership_basis') == BASIS) != ('retained_owner_squad_membership' in row):
            raise ValueError('dated reserve owner witness and decision basis disagree')
