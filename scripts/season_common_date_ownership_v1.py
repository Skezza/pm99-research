"""Positive first-XI ownership at one independently published common date.

This is a playing-squad snapshot, not a claim about the parent contract. It is
deliberately unavailable when clubs' opening dates differ, either original
report lacks an independently published date, or source evidence conflicts.
"""
import json
from scripts import season_historical_transfer_review_v1 as transfer

BASIS = 'unique-positive-first-xi-at-common-independently-published-date'


def uncertain_appearance(sources, person_id):
    id = str(person_id)
    return any(id in source.get('unresolved_person_id_candidates', []) for source in sources) or any(id in event.get(field, {}) for source in sources
               for event in source.get('unresolved_substitution_events', [])
               for field in ('incoming_player_ids', 'outgoing_player_ids'))


def decide(candidates, evidence, person, events):
    if person is None:
        return None, 'common-date-person-unresolved'
    sources = [evidence.get(p['club_id']) for p in candidates]
    if any(source is None for source in sources):
        return None, 'common-date-opening-source-missing'
    if (len({s['source_club_id'] for s in sources}) != len(sources)
            or len({s['date'] for s in sources}) != 1):
        return None, 'common-date-distinct-clubs-and-one-date-required'
    from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
    if person.get('source_provider') == 'soccerbase' and any(
            s.get('source_provider_policy') != soccerbase.POLICY for s in sources):
        return None, 'common-date-Soccerbase-person-needs-same-provider-opening-identities'
    if any(not soccerbase.verified_date(s) or len(s['starting_xi']) != 11
           for s in sources):
        return None, 'common-date-original-dated-eleven-required'
    id = str(person['source_player_id'])
    if uncertain_appearance(sources, id):
        return None, 'common-date-unresolved-original-substitution-appearance'
    positives = [(p, s) for p, s in zip(candidates, sources)
                 if id in set(s['starting_xi']) | set(s['substitutes'])]
    if len(positives) != 1 or id not in positives[0][1]['starting_xi']:
        return None, 'common-date-one-positive-starting-eleven-required'
    player, source = positives[0]
    interval = transfer.transfer_interval(events, source['date'])
    if (interval['status'] == 'recorded-entry-and-exit-bracket-fixture'
            and interval['source_owner_club_id'] != source['source_club_id']):
        return None, 'common-date-transfer-source-conflicts-with-positive-xi'
    return player, BASIS


def verify_plan_claims(release, plan):
    """Reconstruct common-date decisions from original bound inputs, not claims.

    The caller has already rehashed the snapshot, captures and opening review.
    Read every baseline carrier in the identity group, including third claims;
    checking only the selected owner/displaced pair would miss conflicts.
    """
    from scripts import season_duplicate_ownership_plan_v1 as planner
    from scripts import season_release_registry_v1 as registry
    from scripts import season_dated_reserve_owner_v1 as annual_owners
    annual_owners.validate_binding(plan)
    from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
    soccerbase.validate_binding(plan)
    supplemented = plan.get('bindings', {}).get('opening_person_supplement_policy')
    rows = (plan['updates'] if supplemented else
            [r for r in plan['updates'] if r.get('ownership_basis') == BASIS])
    if not rows:
        return
    pin = plan['bindings']['snapshot']
    people, events, _, actual_pin = transfer.load_snapshot(
        registry.ROOT / pin['path'], registry.ROOT / pin['pinned_receipt_path'])
    if actual_pin != pin:
        raise ValueError('common-date person snapshot binding differs')
    from scripts import season_public_identity_and_history_inputs_v1 as public
    people, events, _ = public.merge_bound(people, events, plan['bindings'])
    raw_identity_people = people
    clubs, players = {}, []
    for _, package, _ in planner.package_layers(release):
        clubs.update({c['id']: c for c in package['clubs']})
        players.extend(package['players'])
    by_carrier = {c['carrier_id']: c for c in clubs.values()}
    opening = json.loads((registry.ROOT / plan['bindings']['opening_path']).read_text())
    originals = [(row, opening) for row in opening['clubs']]
    extra = plan['bindings'].get('supplemental_opening')
    if extra:
        extra_document = json.loads((registry.ROOT / extra['path']).read_text())
        originals += [(row, extra_document) for row in extra_document['clubs']]
    evidence = {}
    for row, original_review in originals:
        club = by_carrier.get(row['carrier_id'])
        if (row['status'] == 'original-first-fixture-reparsed' and club is not None
                and club['name'] == row['club']):
            evidence[club['id']] = planner.source_evidence(row, original_review)
    if supplemented:
        from scripts import season_opening_person_supplement_v1 as supplement
        from scripts import season_historical_roster_audit_v1 as roster
        if supplemented != supplement.POLICY:
            raise ValueError('unsupported opening identity supplement policy')
        captures, bindings = roster.load_sources(plan['season'])
        if bindings != plan['bindings']['captures']:
            raise ValueError('opening identity source captures differ from bound inputs')
        previous = json.loads((registry.ROOT / plan['bindings']['review_path']).read_text())
        verifier = roster.SourceVerifier(plan['season'], previous, bindings)
        people, _ = supplement.extend(people, list(clubs.values()), evidence, captures, verifier)
    if plan['bindings'].get('soccerbase_opening_sources') is not None:
        people, _ = soccerbase.bound_people(people, plan['bindings'])
        evidence, _ = soccerbase.attach(plan['bindings'], plan['season'], list(clubs.values()), captures,
            people, events, evidence, raw_identity_people=raw_identity_people)
    indexed = {}
    for player in players:
        person = transfer.unique_person(player, people)
        if person:
            indexed.setdefault(person['source_player_id'], []).append((player, person))
    for row in rows:
        source_person = row['duplicate_source_person']
        candidates = indexed.get(source_person['source_player_id'], [])
        if len({p['club_id'] for p, _ in candidates}) < 2 or any(person != source_person for _, person in candidates):
            raise ValueError('common-date identity does not match pinned full-name/DOB inputs')
        if plan.get('allow_dated_reserve_owners'):
            winner, basis, witness = annual_owners.decide([p for p, _ in candidates], evidence, source_person,
                events.get(source_person['source_player_id'], []), clubs, captures, verifier, people)
        else:
            decision = planner.decide_owner if supplemented else decide
            winner, basis = decision([p for p, _ in candidates], evidence, source_person,
                                    events.get(source_person['source_player_id'], []))
        if winner is None or basis != row['ownership_basis'] or winner['id'] != row['retained_owner_player_id']:
            raise ValueError('common-date ownership cannot be reproduced from every original club claim')
        if plan.get('allow_dated_reserve_owners') and witness != row.get('retained_owner_squad_membership'):
            raise ValueError('annual owner witness does not reproduce from original full-name/DOB squad source')
        if (row['owner_evidence'] != evidence[winner['club_id']]
                or row['replacement_opening_evidence'] != evidence.get(row['club_id'])):
            raise ValueError('common-date declared evidence differs from original source review')
        if supplemented:
            replacement = row['replacement']
            matched = transfer.unique_person({'name': replacement['source_player']['name'],
                'facts': replacement['source_player']}, people)
            if matched != replacement['source_person']:
                raise ValueError('replacement identity does not reproduce from independent bound source inputs')
            from scripts import season_sourced_reserve_role_policy_v1 as reserve_roles
            if reserve_roles.recognised(plan):
                reserve_roles.validate(plan, row, clubs[row['club_id']])
                actual = planner.verified_replacements(clubs[row['club_id']], evidence[row['club_id']],
                    captures, verifier, people, events)
                if replacement not in actual:
                    raise ValueError('replacement facts or position do not reproduce from original opening squad source')
            if replacement['source_person']['source_player_id'] in indexed:
                raise ValueError('sourced reserve replacement is already represented in the original recipe')
    if plan['bindings'].get('soccerbase_opening_sources') is not None:
        native, starters = None, {}
        occupied_dates, undated_names = soccerbase.existing_identity_protection(players)
        for row in rows:
            club = clubs[row['club_id']]
            if club['id'] not in starters:
                starters[club['id']], native = soccerbase.native_starters(release, club, native)
            if row['carrier_id'] in starters[club['id']]:
                raise ValueError('Soccerbase duplicate replacement would change an actual native opening starter')
            person = row['replacement']['source_person']
            if roster.normalise(row['replacement']['source_player']['name']) in undated_names:
                raise ValueError('sourced replacement might duplicate an existing same-name identity with unproven DOB')
            if person.get('source_provider') == 'soccerbase' and person['birth_date'] in occupied_dates:
                raise ValueError('unbridged Soccerbase replacement could duplicate an existing same-DOB identity')
            occupied_dates.add(person['birth_date'])
