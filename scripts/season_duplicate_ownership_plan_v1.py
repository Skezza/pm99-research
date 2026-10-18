#!/usr/bin/env python3
"""Plan evidence-bound opening-squad replacements, never choose by club order.

An opening matchday appearance alone does not exclude a subsequent transfer
between different club opening dates. Require consistent transfer brackets
at every affected club's opening date OR exactly one positive first XI at a
shared independently published date. Always require an unused, independently
reparsed opening bench member or dated reserve at the displaced club. Missing evidence stays in
the queue. This planner does not write recipes or native game files.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_common_date_ownership_v1 as common_date
from scripts import season_sourced_reserve_role_policy_v1 as reserve_roles

SCHEMA = 'pm99-season-duplicate-ownership-plan-v1'
POLICY = 'dated-transfer-brackets-or-positive-common-date-xi-and-opening-reserves-v6'


def package_layers(release):
    """Read the current English overlay, not a superseded legacy manifest."""
    package = json.loads(release.package_path.read_text())
    layers = [('main', package, release.package_path)]
    for artifact in package['artifacts']:
        if artifact['id'] == 'english-contextual-package-2015-16':
            path = release.package_path.parent / artifact['relative_path']
            if registry.sha256_file(path) != artifact['sha256']:
                raise ValueError('current English overlay hash changed')
            layers.append(('english', json.loads(path.read_text()), path))
    return layers


def source_evidence(row, document):
    """Preserve bound original evidence and protect unresolved raw appearances."""
    result = copy.deepcopy(row['evidence'])
    pending = document.get('used_substitute_refresh', {}).get('summary', {}).get('unresolved', [])
    events = [event for problem in pending if problem.get('carrier_id') == row['carrier_id']
              for event in problem.get('events', [])]
    if events:
        result['unresolved_substitution_events'] = events
    return result


def decide_owner(candidates, evidence, person, events):
    """Positive membership plus consistent dated chronology, not absence."""
    if person is None:
        return None, 'person-identity-unmatched-or-ambiguous'
    sources = [evidence.get(p['club_id']) for p in candidates]
    if any(s is None for s in sources):
        return None, 'an-affected-club-lacks-a-verified-opening-source'
    if person.get('source_provider') == 'soccerbase':
        from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
        if any(s.get('source_provider_policy') != soccerbase.POLICY for s in sources):
            return None, 'Soccerbase-person-needs-same-provider-opening-identities-at-every-affected-club'
    if len({s['source_club_id'] for s in sources}) < len({p['club_id'] for p in candidates}):
        return None, 'duplicate-real-club-carriers-need-a-whole-club-disposition'
    if common_date.uncertain_appearance(sources, person['source_player_id']):
        return None, 'original-substitution-appearance-needs-reconciliation'
    intervals = [transfer.transfer_interval(events, s['date']) for s in sources]
    if any(i['status'] != 'recorded-entry-and-exit-bracket-fixture' for i in intervals):
        positive, basis = common_date.decide(candidates, evidence, person, events)
        if positive is not None:
            return positive, basis
        return None, 'dated-transfer-interval-incomplete-or-ambiguous'
    owners = {i['source_owner_club_id'] for i in intervals}
    if len(owners) != 1:
        return None, 'ownership-differs-between-club-opening-dates'
    source_owner = next(iter(owners))
    matches = [(p, s) for p, s in zip(candidates, sources) if s['source_club_id'] == source_owner]
    if len(matches) != 1:
        return None, 'dated-owner-not-one-unique-represented-club'
    player, source = matches[0]
    match_ids = set(source['starting_xi']) | set(source['substitutes'])
    if str(person['source_player_id']) not in match_ids:
        return None, 'dated-owner-lacks-positive-opening-matchday-person-id'
    if any(p['id'] != player['id'] and str(person['source_player_id']) in (set(s['starting_xi']) | set(s['substitutes']))
           for p, s in zip(candidates, sources)):
        return None, 'contradictory-positive-opening-matchday-member-protected'
    return player, 'positive-opening-membership-and-consistent-dated-transfer-brackets'


def candidate_groups(players, people):
    """A unique published person ID can join full-name spelling variants."""
    groups = collections.defaultdict(list)
    for player in players:
        person = transfer.unique_person(player, people)
        key = ('published-person', person['source_player_id']) if person else roster.person_identity_key(player)
        if key is not None:
            groups[key].append(player)
    return [rows for _, rows in sorted(groups.items(), key=lambda pair: str(pair[0]))
            if len({p['carrier_id'] for p in rows}) > 1]


def verified_replacements(club, source, captured, verifier, people, events=None):
    """Reparsed squad facts plus matchday membership OR dated opening ownership.

    Whole-season membership alone never admits a later signing. A reserve not
    on the first bench must have the same entry/exit continuity proof used for
    duplicate ownership, at this club's independently established opening date.
    """
    from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
    if source.get('source_provider_policy') == soccerbase.POLICY:
        return copy.deepcopy(source['soccerbase_verified_replacements'])
    names = roster.club_names(roster.club_group(club), club['name'], club.get('full_name', ''))
    result = {}
    for capture in captured:
        if roster.source_group(capture['country_catalog']) != roster.club_group(club):
            continue
        if roster.normalise(capture['club_name']) not in names:
            continue
        proof = verifier.verify(capture)
        if proof['status'] != 'raw-source-reparsed':
            continue
        for raw in capture['players']:
            facts = raw
            if not isinstance(facts.get('birth_date'), str) or facts.get('position') not in ('G', 'D', 'M', 'F'):
                continue
            probe = {'name': facts['name'], 'facts': facts}
            person = transfer.unique_person(probe, people)
            if person is None:
                continue
            id_string = str(person['source_player_id'])
            if id_string in source['starting_xi']:
                # A missing starter needs a separately reconciled XI, not a
                # reserve replacement that silently changes startup order.
                continue
            if id_string in source['substitutes']:
                eligibility = {'method': 'positive-first-fixture-substitute-id', 'date': source['date'],
                               'source_club_id': source['source_club_id']}
            else:
                interval = transfer.transfer_interval((events or {}).get(person['source_player_id'], []), source['date'])
                if (interval['status'] != 'recorded-entry-and-exit-bracket-fixture' or
                        interval['source_owner_club_id'] != source['source_club_id']):
                    continue
                eligibility = {'method': 'dated-opening-reserve-entry-exit-bracket', 'date': source['date'],
                               'source_club_id': source['source_club_id'], 'interval': interval}
            # Published matchday membership or a dated ownership bracket
            # agrees with the independent full-name/DOB join. No initial guess
            # or whole-season-only inference.
            key = person['source_player_id']
            result.setdefault(key, []).append({'source_player': raw, 'source_person': person,
                'source_capture': {k: capture[k] for k in ('source_path', 'source_sha256', 'club_name')},
                'raw_evidence': proof, 'opening_eligibility': eligibility})
    resolved = []
    for id, alternatives in sorted(result.items(), key=lambda item: soccerbase.person_sort_key(item[0])):
        identities = {(row['source_player']['name'], row['source_player']['birth_date'],
                       row['source_player']['position']) for row in alternatives}
        if len(identities) == 1:
            resolved.append(alternatives[0])
    return resolved


def plan(season, people, events, snapshot_binding, source_root, output, supplemental_opening_path=None,
         with_opening_person_supplement=False, published_person_path=None, published_transfer_path=None,
         allow_sourced_outfield_reserve_role_changes=False, allow_published_display_aliases=False,
         allow_dated_reserve_owners=False, soccerbase_review_path=None, soccerbase_club_entities_path=None,
         allow_dated_outfield_reserve_role_changes=False):
    from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
    if bool(soccerbase_review_path) != bool(soccerbase_club_entities_path):
        raise ValueError('Soccerbase opening source policy requires original review AND club identity inputs')
    if allow_dated_outfield_reserve_role_changes and not allow_sourced_outfield_reserve_role_changes:
        raise ValueError('dated reserve position changes require the explicit sourced outfield reserve policy')
    if soccerbase_review_path is not None and not (
            with_opening_person_supplement and published_person_path is not None and published_transfer_path is not None):
        raise ValueError('Soccerbase source policy requires independently replayed original person/history inputs')
    if allow_dated_reserve_owners and not (
            with_opening_person_supplement and published_person_path is not None and published_transfer_path is not None):
        raise ValueError('dated reserve owners require independently replayed public person/history inputs')
    if allow_published_display_aliases and not (with_opening_person_supplement and published_person_path is not None):
        raise ValueError('published display aliases require independently replayed public person input')
    if allow_sourced_outfield_reserve_role_changes and not (
            with_opening_person_supplement and published_person_path is not None and published_transfer_path is not None):
        raise ValueError('sourced outfield reserve role policy requires independently replayed public person/history inputs')
    release = registry.load_preferred_release(season)
    layers = package_layers(release)
    clubs = [c for _, package, _ in layers for c in package['clubs']]
    players = [p for _, package, _ in layers for p in package['players']]
    club_by_id = {c['id']: c for c in clubs}
    layer_by_id = {p['id']: label for label, package, _ in layers for p in package['players']}
    carrier_layers = collections.defaultdict(set)
    for label, package, _ in layers:
        for player in package['players']:
            carrier_layers[player['carrier_id']].add(label)
    opening_path = source_root / 'opening' / season / 'opening-review.json'
    opening = json.loads(opening_path.read_text())
    transfer.verify_opening_sources(opening)
    evidence = {}
    opening_rows = [(row, opening) for row in opening['clubs']]
    if supplemental_opening_path is not None:
        extra = json.loads(supplemental_opening_path.read_text())
        if extra['season'] != season:
            raise ValueError('supplemental opening review belongs to another season')
        transfer.verify_opening_sources(extra)
        opening_rows += [(row, extra) for row in extra['clubs']]
    for row, original_review in opening_rows:
        if row['status'] != 'original-first-fixture-reparsed':
            continue
        club = club_by_id.get(row['club_id'])
        # 2015's old reviewer used legacy IDs. Rebind only exact native club
        # carrier + current label, with the raw source bytes rehashed above.
        if club is None and season == '2015-16':
            matches = [c for c in clubs if (c['carrier_id'], c['name']) == (row['carrier_id'], row['club'])]
            club = matches[0] if len(matches) == 1 else None
        if club is not None and (club['carrier_id'], club['name']) == (row['carrier_id'], row['club']):
            evidence[club['id']] = source_evidence(row, original_review)
    captures, capture_bindings = roster.load_sources(season)
    report_path = source_root / 'reviews' / season / 'report.json'
    if not report_path.exists() and season == '2015-16':
        report_path = source_root / 'reviews' / season / 'roster-audit.json'
    previous = json.loads(report_path.read_text())
    verifier = roster.SourceVerifier(season, previous, capture_bindings)
    identity_supplement = None
    resolution_policy = POLICY
    public_bindings, public_summary = {}, None
    soccerbase_binding, soccerbase_identity_summary, soccerbase_source_gaps = None, None, []
    raw_identity_people = people
    if published_person_path is not None or published_transfer_path is not None:
        from scripts import season_public_identity_and_history_inputs_v1 as public
        from scripts import season_published_person_identity_v1 as identities
        from scripts import season_published_transfer_history_v1 as histories
        if not with_opening_person_supplement:
            raise ValueError('public source inputs require independent opening identity verification')
        for key, supplied, policy in (
                ('published_person_supplement', published_person_path, identities.POLICY),
                ('published_transfer_supplement', published_transfer_path, histories.POLICY)):
            if supplied is not None:
                public_bindings[key] = public.binding(supplied, policy)
        people, events, public_summary = public.merge_bound(people, events, public_bindings)
        raw_identity_people = people
    if with_opening_person_supplement:
        from scripts import season_opening_person_supplement_v1 as supplement
        people, identity_supplement = supplement.extend(people, clubs, evidence, captures, verifier)
        resolution_policy = 'independent-opening-person-DOB-joins-and-dated-ownership-v7'
        if public_bindings:
            resolution_policy = 'original-public-person-and-complete-history-with-independent-opening-evidence-v8'
        if allow_sourced_outfield_reserve_role_changes:
            resolution_policy = (reserve_roles.DATED_RESOLUTION if allow_dated_outfield_reserve_role_changes
                                 else reserve_roles.RESOLUTION)
    if soccerbase_review_path is not None:
        soccerbase_binding = {'policy': soccerbase.POLICY, 'person_policy': soccerbase.PERSON_POLICY,
            'review': public.binding(soccerbase_review_path, soccerbase.POLICY),
            'club_entities': public.binding(soccerbase_club_entities_path, 'original-explicit-club-identity-discovery-v1')}
        source_bindings = dict(public_bindings, snapshot=snapshot_binding, soccerbase_opening_sources=soccerbase_binding)
        people, soccerbase_identity_summary = soccerbase.bound_people(people, source_bindings)
        evidence, soccerbase_source_gaps = soccerbase.attach(source_bindings, season, clubs, captures,
            people, events, evidence, raw_identity_people=raw_identity_people)
    path = output / season / 'ownership-plan.json'
    if path.exists():
        completed = json.loads(path.read_text())
        expected = (release.release_id, registry.sha256_file(release.package_path),
                    registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
                    registry.sha256_file(opening_path), registry.sha256_file(report_path), snapshot_binding, capture_bindings)
        actual = (completed['release_id'], completed['package_sha256'], completed['jug_sha256'],
                  completed['bindings']['opening_sha256'], completed['bindings']['review_sha256'],
                  completed['bindings']['snapshot'], completed['bindings']['captures'])
        expected_extra = {'path': registry.relative_workspace_path(supplemental_opening_path),
            'sha256': registry.sha256_file(supplemental_opening_path)} if supplemental_opening_path else None
        actual_extra = completed['bindings'].get('supplemental_opening')
        if actual_extra is not None:
            actual_extra = {k: actual_extra[k] for k in ('path', 'sha256')}
        if (completed['schema_version'] != SCHEMA or completed.get('resolution_policy') != resolution_policy or
                bool(completed.get('allow_sourced_outfield_reserve_role_changes')) != allow_sourced_outfield_reserve_role_changes or
                bool(completed.get('allow_published_display_aliases')) != allow_published_display_aliases or
                bool(completed.get('allow_dated_reserve_owners')) != allow_dated_reserve_owners or
                bool(completed.get('allow_dated_outfield_reserve_role_changes')) != allow_dated_outfield_reserve_role_changes or
                completed['bindings'].get('soccerbase_opening_sources') != soccerbase_binding or
                actual != expected or actual_extra != expected_extra or any(
                    completed['bindings'].get(key) != public_bindings.get(key)
                    for key in ('published_person_supplement', 'published_transfer_supplement'))):
            raise ValueError('completed ownership plan inputs changed; use a new output root')
        return dict(completed['summary'], season=season, reused_completed=True)
    published_display_claims = {}
    if allow_published_display_aliases:
        from scripts import season_published_display_names_v1 as display_names
        published_display_claims = display_names.claims(published_person_path)
    used_people = {p['source_player_id'] for row in players if (p := transfer.unique_person(row, people))}
    used_identity = {roster.person_identity_key(p) for p in players}
    updates, unresolved, reserves = [], [], {}
    native_starter_sets, native_guard_cache = {}, None
    used_dates, undated_names = soccerbase.existing_identity_protection(players)
    groups = candidate_groups(players, people)
    for candidates in groups:
        person = transfer.unique_person(candidates[0], people)
        person_events = events.get(person['source_player_id'], []) if person else []
        annual_owner_witness = None
        if allow_dated_reserve_owners:
            from scripts import season_dated_reserve_owner_v1 as annual_owners
            winner, reason, annual_owner_witness = annual_owners.decide(
                candidates, evidence, person, person_events, club_by_id, captures, verifier, people)
        else:
            winner, reason = decide_owner(candidates, evidence, person, person_events)
        queue = {'identity': {'source_name': candidates[0].get('source_name', candidates[0]['name']),
                             'birth_date': candidates[0]['facts'].get('birth_date'), 'source_person': person},
                 'candidates': [{'player_id': p['id'], 'carrier_id': p['carrier_id'], 'club_id': p['club_id'],
                                 'club': club_by_id[p['club_id']]['name']} for p in candidates]}
        if winner is None:
            unresolved.append(dict(queue, reason=reason))
            continue
        for loser in candidates:
            if loser['id'] == winner['id']:
                continue
            club = club_by_id[loser['club_id']]
            source = evidence[club['id']]
            if str(person['source_player_id']) in set(source['starting_xi']) | set(source['substitutes']):
                unresolved.append(dict(queue, reason='conflicting-positive-opening-matchday-member-protected', player_id=loser['id']))
                continue
            if layer_by_id[loser['id']] != 'main':
                unresolved.append(dict(queue, reason='english-overlay-requires-separately-bound-transaction', player_id=loser['id']))
                continue
            if len(carrier_layers[loser['carrier_id']]) != 1:
                unresolved.append(dict(queue, reason='shared-overlay-carrier-requires-recipe-reconciliation', player_id=loser['id']))
                continue
            if loser['id'] in club.get('opening', {}).get('starting_xi_player_ids', []):
                unresolved.append(dict(queue, reason='displaced-starter-requires-opening-xi-reconciliation', player_id=loser['id']))
                continue
            if soccerbase_binding is not None:
                if club['id'] not in native_starter_sets:
                    try:
                        native_starter_sets[club['id']], native_guard_cache = soccerbase.native_starters(
                            release, club, native_guard_cache)
                    except ValueError:
                        native_starter_sets[club['id']] = None
                actual_starters = native_starter_sets[club['id']]
                if actual_starters is None or loser['carrier_id'] in actual_starters:
                    unresolved.append(dict(queue, reason=('actual-native-starter-requires-opening-xi-reconciliation'
                        if actual_starters is not None else 'actual-native-opening-xi-could-not-be-proved'), player_id=loser['id']))
                    continue
            if club['id'] not in reserves:
                reserves[club['id']] = verified_replacements(club, source, captures, verifier, people, events)
            eligible = []
            for replacement in reserves[club['id']]:
                replacement_person = replacement['source_person']
                identity = (roster.normalise(replacement_person['name']), replacement_person['birth_date'])
                if (replacement_person['source_player_id'] not in used_people and identity not in used_identity and
                        not (soccerbase_binding is not None and roster.normalise(replacement['source_player']['name']) in undated_names) and
                        not (replacement_person.get('source_provider') == 'soccerbase' and replacement_person['birth_date'] in used_dates) and
                        reserve_roles.eligible(loser, replacement, allow_sourced_outfield_reserve_role_changes,
                                               allow_dated_outfield_reserve_role_changes)):
                    eligible.append(replacement)
            if not eligible:
                unresolved.append(dict(queue, reason='owner-proven-but-no-unused-role-compatible-opening-substitute', player_id=loser['id']))
                continue
            eligible.sort(key=lambda row: (
                row['source_player']['position'] != loser['facts'].get('primary_position'),
                row['opening_eligibility']['method'] != 'positive-first-fixture-substitute-id',
                soccerbase.person_sort_key(row['source_person']['source_player_id'])))
            # A small carrier cannot accept every surname. Try all sourced,
            # role-compatible reserves before declaring that club blocked.
            from scripts import season_duplicate_ownership_delta_v1 as delta
            original = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
            replacement = None
            selected_display_claim = None
            for option in eligible:
                try:
                    view = {'players': [{'id': loser['id'], 'source_name': option['source_player']['name'],
                        'name': delta.compiler._pm99_text(option['source_player']['name'], label='replacement')}]}
                    trial = {'player_id': loser['id'], 'carrier_id': loser['carrier_id'], 'replacement': option}
                    display_claim = published_display_claims.get(option['source_person']['source_player_id'])
                    if display_claim is not None and display_claim['birth_date'] != option['source_person']['birth_date']:
                        display_claim = None
                    if display_claim is not None:
                        trial['published_display_names'] = display_claim
                    delta.fit_display_names(original, view, {'updates': [trial]})
                except ValueError:
                    continue
                replacement = copy.deepcopy(option)
                selected_display_claim = display_claim
                break
            if replacement is None:
                unresolved.append(dict(queue, reason='owner-proven-but-all-eligible-replacement-surnames-exceed-native-window',
                                       player_id=loser['id'], eligible_source_person_ids=[r['source_person']['source_player_id'] for r in eligible]))
                continue
            used_people.add(replacement['source_person']['source_player_id'])
            used_dates.add(replacement['source_person']['birth_date'])
            used_identity.add((roster.normalise(replacement['source_person']['name']), replacement['source_person']['birth_date']))
            updates.append({'player_id': loser['id'], 'carrier_id': loser['carrier_id'], 'club_id': club['id'],
                'club': club['name'], 'layer': layer_by_id[loser['id']], 'before': loser,
                'ownership_basis': reason,
                'duplicate_source_person': person,
                'retained_owner_player_id': winner['id'], 'owner_evidence': evidence[winner['club_id']],
                'transfer_intervals': [transfer.transfer_interval(events.get(person['source_player_id'], []), evidence[p['club_id']]['date']) for p in candidates],
                'replacement': replacement, 'replacement_opening_evidence': source,
                'portrait_policy': 'remove-displaced-person-portrait-native-no-photo'})
            if selected_display_claim is not None:
                updates[-1]['published_display_names'] = selected_display_claim
            if annual_owner_witness is not None:
                updates[-1]['retained_owner_squad_membership'] = copy.deepcopy(annual_owner_witness)
            if replacement['source_player']['position'] != loser['facts'].get('primary_position'):
                updates[-1]['reserve_role_change'] = {'before': loser['facts']['primary_position'],
                    'after': replacement['source_player']['position'], 'policy': (
                        reserve_roles.DATED_POLICY if allow_dated_outfield_reserve_role_changes else reserve_roles.POLICY)}
    document = {'schema_version': SCHEMA, 'resolution_policy': resolution_policy, 'season': season, 'release_id': release.release_id,
        'package_sha256': registry.sha256_file(release.package_path),
        'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
        'bindings': {'snapshot': snapshot_binding, 'opening_path': registry.relative_workspace_path(opening_path),
            'opening_sha256': registry.sha256_file(opening_path), 'captures': capture_bindings,
            'review_path': registry.relative_workspace_path(report_path), 'review_sha256': registry.sha256_file(report_path)},
        'summary': {'candidate_groups': len(groups), 'replacement_slots': len(updates), 'unresolved_entries': len(unresolved),
                    'unresolved_reasons': dict(collections.Counter(row['reason'] for row in unresolved))},
        'updates': updates, 'unresolved': unresolved, 'historical_verification_complete': False}
    if public_summary is not None:
        document['bindings'].update(public_bindings)
        document['original_public_input_summary'] = public_summary
    if soccerbase_binding is not None:
        document['bindings']['soccerbase_opening_sources'] = soccerbase_binding
        document['soccerbase_original_person_summary'] = soccerbase_identity_summary
        document['soccerbase_original_source_gaps'] = soccerbase_source_gaps
    if allow_sourced_outfield_reserve_role_changes:
        document['allow_sourced_outfield_reserve_role_changes'] = True
        document['bindings']['reserve_role_policy'] = (reserve_roles.DATED_POLICY
            if allow_dated_outfield_reserve_role_changes else reserve_roles.POLICY)
    if allow_dated_outfield_reserve_role_changes:
        document['allow_dated_outfield_reserve_role_changes'] = True
    if allow_published_display_aliases:
        document['allow_published_display_aliases'] = True
        document['bindings']['published_display_policy'] = display_names.POLICY
    if allow_dated_reserve_owners:
        from scripts import season_dated_reserve_owner_v1 as annual_owners
        document['allow_dated_reserve_owners'] = True
        document['bindings']['dated_reserve_owner_policy'] = annual_owners.POLICY
    if identity_supplement is not None:
        document['bindings']['opening_person_supplement_policy'] = supplement.POLICY
        used = {r['duplicate_source_person']['source_player_id'] for r in updates}
        used.update(r['replacement']['source_person']['source_player_id'] for r in updates)
        document['opening_person_supplement'] = {
            'added_identity_count': len(identity_supplement['added_identities']),
            'refused_identity_claim_count': len(identity_supplement['refused_identity_claims']),
            'used_added_identity_proofs': [r for r in identity_supplement['added_identities']
                                         if r['source_player_id'] in used],
            'ownership_established_by_identity_join': False}
    if supplemental_opening_path is not None:
        document['bindings']['supplemental_opening'] = {'path': registry.relative_workspace_path(supplemental_opening_path),
            'sha256': registry.sha256_file(supplemental_opening_path),
            'limit': 'Earliest fixture present in pinned source, not a claim that all loans or every fixture are represented.'}
    if path.exists():
        raise ValueError('never overwrite a completed ownership plan')
    path.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(path, document)
    return dict(document['summary'], season=season)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--supplemental-opening', type=Path,
                        help='bound extra opening review; applied only to its declared season')
    parser.add_argument('--with-opening-person-supplement', action='store_true',
                        help='join original opening IDs to independently reparsed squad DOBs')
    parser.add_argument('--published-person-supplement', type=Path)
    parser.add_argument('--published-transfer-supplement', type=Path)
    parser.add_argument('--allow-sourced-outfield-reserve-role-changes', action='store_true')
    parser.add_argument('--allow-published-display-aliases', action='store_true')
    parser.add_argument('--allow-dated-reserve-owners', action='store_true')
    parser.add_argument('--allow-dated-outfield-reserve-role-changes', action='store_true',
                        help='keep a positively dated non-starter reserve\'s sourced outfield position')
    parser.add_argument('--soccerbase-opening-review', type=Path)
    parser.add_argument('--soccerbase-club-entities', type=Path)
    args = parser.parse_args()
    people, events, _, binding = transfer.load_snapshot(
        ROOT / '.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb',
        ROOT / '.local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json')
    extra_season = json.loads(args.supplemental_opening.read_text())['season'] if args.supplemental_opening else None
    for season in registry.supported_seasons() if args.season == 'all' else [args.season]:
        extra = args.supplemental_opening if extra_season == season else None
        print(json.dumps(plan(season, people, events, binding, args.source_root, args.output, extra,
                              args.with_opening_person_supplement, args.published_person_supplement,
                              args.published_transfer_supplement, args.allow_sourced_outfield_reserve_role_changes,
                              args.allow_published_display_aliases, args.allow_dated_reserve_owners,
                              args.soccerbase_opening_review, args.soccerbase_club_entities,
                              args.allow_dated_outfield_reserve_role_changes)), flush=True)


if __name__ == '__main__':
    main()
