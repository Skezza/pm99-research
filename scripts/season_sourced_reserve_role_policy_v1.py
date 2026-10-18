"""A positively sourced outfield reserve keeps their own position.

Never convert goalkeeper slots, replace a declared starting XI, or admit an
unlisted reserve just to fill capacity. Same-position selection remains the
default and first preference; this explicit policy is a bounded fallback.
"""
POLICY = 'published-opening-outfield-substitute-position-v1'
RESOLUTION = 'original-public-person-history-and-sourced-outfield-bench-position-v9'
DATED_POLICY = 'published-squad-and-strict-dated-opening-outfield-reserve-position-v2'
DATED_RESOLUTION = 'original-public-person-history-and-dated-outfield-reserve-position-v10'


def dated_membership(replacement, opening=None):
    """Check the strict interval shape; callers independently replay raw facts.

    An annual squad list alone is never sufficient. Entry and departure must
    agree on this club and strictly bracket its independently sourced fixture.
    No keeper conversions, source starters or unknown roles are admitted here.
    """
    proof = replacement.get('opening_eligibility', {})
    if proof.get('method') != 'dated-opening-reserve-entry-exit-bracket':
        return False
    interval = proof.get('interval', {})
    entry, departure = interval.get('entry', {}), interval.get('departure', {})
    day = proof.get('date'); club = proof.get('source_club_id')
    if not isinstance(day, str) or club is None:
        return False
    import datetime as dt
    try:
        day_value = dt.date.fromisoformat(day)
        entry_value = dt.date.fromisoformat(entry['date'])
        exit_value = dt.date.fromisoformat(departure['date'])
    except (ValueError, KeyError, TypeError):
        return False
    if not (interval.get('status') == 'recorded-entry-and-exit-bracket-fixture'
            and interval.get('source_owner_club_id') == club
            and entry.get('to_club_id') == club == departure.get('from_club_id')
            and entry_value < day_value < exit_value):
        return False
    if opening is not None:
        person_id = str(replacement['source_person']['source_player_id'])
        if ((day, club) != (opening.get('date'), opening.get('source_club_id'))
                or person_id in opening['starting_xi']):
            return False
    return True


def eligible(before, replacement, enabled=False, dated_enabled=False):
    old, new = before['facts'].get('primary_position'), replacement['source_player']['position']
    return old == new or bool(enabled and old in {'D', 'M', 'F'} and new in {'D', 'M', 'F'} and
        (replacement.get('opening_eligibility', {}).get('method') == 'positive-first-fixture-substitute-id'
         or (dated_enabled and dated_membership(replacement))))


def recognised(plan):
    return plan.get('resolution_policy') in (RESOLUTION, DATED_RESOLUTION)


def policy_for(plan):
    return DATED_POLICY if plan.get('resolution_policy') == DATED_RESOLUTION else POLICY


def validate(plan, row, club):
    before, replacement = row['before'], row['replacement']
    old, new = before['facts'].get('primary_position'), replacement['source_player']['position']
    if old == new:
        return
    dated_enabled = bool(plan.get('allow_dated_outfield_reserve_role_changes'))
    if (not recognised(plan) or
            (plan.get('resolution_policy') == DATED_RESOLUTION) != dated_enabled or
            plan.get('bindings', {}).get('reserve_role_policy') != policy_for(plan) or
            not all(plan.get('bindings', {}).get(key) for key in
                    ('published_person_supplement', 'published_transfer_supplement')) or
            not plan.get('allow_sourced_outfield_reserve_role_changes') or
            not eligible(before, replacement, True, dated_enabled)):
        raise ValueError('replacement must preserve the displaced slot broad role unless explicitly sourced outfield bench policy applies')
    expected = {'before': old, 'after': new, 'policy': policy_for(plan)}
    if row.get('reserve_role_change') != expected:
        raise ValueError('declared reserve role change differs from sourced positions')
    if row['player_id'] in club.get('opening', {}).get('starting_xi_player_ids', []):
        raise ValueError('a sourced reserve role change cannot replace an opening starter')
    opening = row['replacement_opening_evidence']
    id = str(replacement['source_person']['source_player_id'])
    method = replacement.get('opening_eligibility', {}).get('method')
    if method == 'dated-opening-reserve-entry-exit-bracket':
        if not dated_enabled or not dated_membership(replacement, opening):
            raise ValueError('a reserve role change requires consistent dated opening membership')
        if replacement.get('raw_evidence', {}).get('status') != 'raw-source-reparsed':
            raise ValueError('a dated reserve role change requires independently reparsed squad facts')
    elif id not in opening['substitutes'] or id in opening['starting_xi']:
        raise ValueError('a reserve role change requires an original non-starter substitute ID')
