#!/usr/bin/env python3
"""Prepare a complete, sourced replacement for a duplicated non-playable club.

Only original first-fixture players and positively dated opening reserves are
eligible. No native publication, club deletion, fictitious people or implicit
approval occurs here. A full fixed-capacity allocation precedes any transaction.
"""
import argparse
import copy
import datetime as dt
from functools import lru_cache
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_published_person_identity_v1 as persons
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_published_display_names_v1 as aliases
from scripts import season_published_family_component_v1 as families
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
from scripts import season_english_result_date_binding_v1 as club_entities
from scripts import season_duplicate_ownership_delta_v1 as delta
from app.fdi_indexed import IndexedFDIFile

SCHEMA = 'pm99-duplicate-whole-club-disposition-source-plan-v1'


def club_keys(name, full_name=''):
    """Use explicit existing aliases in both directions, never fuzzy names."""
    aliases=tuple((short,tuple(full)) for short,full in soccerbase.CLUB_ALIASES.items())
    return set(_club_keys(name,full_name,aliases))


@lru_cache(maxsize=8192)
def _club_keys(name,full_name,aliases):
    # Copy on return above: a caller may mutate its set without changing later
    # identity decisions. Alias-table changes select a distinct cache entry.
    keys = roster.club_names('england', name, full_name)
    for group in _alias_groups(aliases):
        if keys & group: keys.update(group)
    return frozenset(keys)


@lru_cache(maxsize=8)
def _alias_groups(aliases):
    return tuple(frozenset().union(*(roster.club_names('england', value)
        for value in (short,*full))) for short,full in aliases)


def minimum_assignment(costs):
    """Stable square minimum-cost assignment; missing edges cannot be selected."""
    n = len(costs)
    if not n or any(len(row) != n for row in costs):
        raise ValueError('whole-club allocation requires a nonempty square capacity')
    infinity = 10**12
    values = [[infinity if c is None else c for c in row] for row in costs]
    u = [0]*(n+1); v = [0]*(n+1); owner = [0]*(n+1); route = [0]*(n+1)
    for row in range(1, n+1):
        owner[0] = row; column = 0; used = [False]*(n+1); distances = [infinity]*(n+1)
        while True:
            used[column] = True; current = owner[column]; step = infinity; next_column = 0
            for candidate in range(1, n+1):
                if used[candidate]: continue
                cost = values[current-1][candidate-1]-u[current]-v[candidate]
                if cost < distances[candidate]:
                    distances[candidate] = cost; route[candidate] = column
                if distances[candidate] < step:
                    step = distances[candidate]; next_column = candidate
            if next_column == 0:
                raise ValueError('actual opening roster cannot fit the native name windows')
            for candidate in range(n+1):
                if used[candidate]:
                    u[owner[candidate]] += step; v[candidate] -= step
                else:
                    distances[candidate] -= step
            column = next_column
            if owner[column] == 0: break
        while column:
            previous = route[column]; owner[column] = owner[previous]; column = previous
    result = [None]*n
    for column in range(1, n+1): result[owner[column]-1] = column-1
    if any(costs[i][j] is None for i, j in enumerate(result)):
        raise ValueError('actual opening roster cannot fit the native name windows')
    return result


def matchday_people(actual, annual, *, identity_resolutions=None, people=None,
                    exclude_unpublished_bench_birth_dates=False, role_resolutions=None):
    result = []
    consumed_role_resolutions = set()
    for group in ('starting_xi', 'published_bench'):
        for row in actual['identity_bridges'][group]:
            bio = row['soccerbase_person']; person = row['transfermarkt_person'] or dict(bio, source_provider='soccerbase')
            canonical_date=bio['birth_date'];resolution=None
            reviewed=(identity_resolutions or {}).get(bio['source_player_id'])
            if (group == 'published_bench' and bio['birth_date'] is None
                    and reviewed is None and exclude_unpublished_bench_birth_dates):
                continue
            if reviewed is not None:
                if (reviewed['name'],reviewed['published_birth_date'])!=(bio['name'],bio['birth_date']):
                    raise ValueError('reviewed provider identity differs from original full biography')
                canonical_date=reviewed['canonical_birth_date']
                if reviewed.get('prior_delivered_birthday_witness') is not None:
                    from scripts import season_prior_delivered_birthday_witness_v1 as prior_date
                    person=prior_date.resolve(reviewed,bio,annual)
                elif reviewed.get('secondary_birthday_policy') is not None:
                    from scripts import season_external_soccerbase_birthday_v1 as secondary
                    from scripts import season_external_soccerbase_birthday_v2 as secondary_v2
                    if reviewed['secondary_birthday_policy'] == secondary_v2.POLICY:
                        secondary = secondary_v2
                    person=secondary.resolve(reviewed,bio,actual)
                else:
                    person=transfer.unique_person({'name':bio['name'],'facts':{'birth_date':canonical_date}},people or {})
                if person is None or person['source_player_id']!=reviewed['canonical_source_player_id']:
                    raise ValueError('reviewed provider identity lacks the exact independent publisher person')
                resolution=copy.deepcopy(reviewed)
            if bio['birth_date'] is None and resolution is None:
                raise ValueError('missing provider DOB needs an explicit independently confirmed annual/public identity review')
            dt.date.fromisoformat(canonical_date)
            matching = [p for p in annual['players'] if
                (roster.normalise(p['name']), p.get('birth_date')) ==
                (roster.normalise(bio['name']), canonical_date)]
            if len(matching) > 1: raise ValueError('annual facts identify multiple same-name/DOB people')
            if resolution is not None and len(matching)!=1:
                # An annual provider can also publish the wrong birthday.
                # Retaining an independently confirmed original identity is
                # explicit; never copy secondary facts from the rejected row.
                conflicting = [p for p in annual['players'] if
                    roster.normalise(p['name']) == roster.normalise(bio['name'])
                    and p.get('birth_date') == resolution.get('rejected_annual_birth_date')]
                external_missing_annual=(resolution.get('secondary_birthday_policy') is not None
                    and not any(p.get('birth_date') for p in annual['players']
                        if roster.normalise(p['name'])==roster.normalise(bio['name'])))
                prior_verified_annual=(resolution.get('prior_delivered_birthday_witness') is not None)
                if not (external_missing_annual or prior_verified_annual) and (resolution.get('annual_fact_policy') != 'discard-conflicting-annual-biography'
                        or canonical_date != bio['birth_date'] or len(conflicting) != 1):
                    raise ValueError('reviewed provider DOB lacks one independently reparsed annual source agreement')
            facts = copy.deepcopy(matching[0]) if matching else {}
            named_annual = [p for p in annual['players'] if
                roster.normalise(p['name']) == roster.normalise(bio['name'])
                and p.get('birth_date')]
            if resolution is None and named_annual and not matching:
                raise ValueError('provider birthday conflicts with annual same-name biography; explicit identity review required')
            role = row['dated_match_position']
            annual_role = False
            secondary_role = None
            if role not in ('G','D','M','F') and bio['source_player_id'] in (role_resolutions or {}):
                from scripts import season_original_secondary_bench_role_v1 as bench_roles
                secondary_role = bench_roles.resolve(role_resolutions[bio['source_player_id']], bio, actual)
                role = secondary_role['primary_position']
                consumed_role_resolutions.add(bio['source_player_id'])
            if role not in ('G','D','M','F'):
                if len(matching)==1 and matching[0].get('position') in ('G','D','M','F'):
                    role = matching[0]['position']; annual_role = True
                else:
                    if group == 'starting_xi': raise ValueError('actual starting XI has an unsourced role')
                    continue
            facts.update(name=bio['name'], birth_date=canonical_date, position=role)
            for field in ('nationality', 'height_cm', 'weight_kg', 'shirt_number'): facts.setdefault(field, None)
            original = next(s for s in actual['raw_sources'] if s['url'] == bio['source_profile_url'])
            replacement = {'source_person': copy.deepcopy(person), 'source_player': facts,
                'raw_evidence': {'status': 'raw-source-reparsed', 'local_path': original['path'],
                    'source_sha256': original['sha256']}, 'membership': group,
                'source_display_aliases': {'policy': soccerbase.POLICY,
                    'source_provider_person_id': bio['source_player_id'],
                    'source_person_id': person['source_player_id'], 'birth_date': canonical_date,
                    'names': [{'field': 'dated-match-label', 'name': row['published_match_name']}]}}
            if resolution is not None:
                replacement['source_identity_resolution']=resolution
                replacement['source_display_aliases']['published_birth_date']=bio['birth_date']
            if annual_role:
                replacement['source_role_basis']={
                    'policy':'exact-full-name-canonical-DOB-target-season-annual-broad-role-v1',
                    'original_match_role':row['dated_match_position'],
                    'annual_broad_role':role,'exact_match_deployment_claimed':False}
            if secondary_role is not None:
                replacement['source_role_basis'] = secondary_role
            result.append(replacement)
    starters = [r for r in result if r['membership'] == 'starting_xi']
    if consumed_role_resolutions != set(role_resolutions or {}):
        raise ValueError('secondary bench-role review is unused or tries to override a published role')
    if len(starters) != 11 or starters[0]['source_player']['position'] != 'G' or sum(
            p['source_player']['position'] == 'G' for p in starters) != 1:
        raise ValueError('the exact first fixture needs eleven identified players and one starting keeper')
    return result


def minimum_reserve_pool_assignment(costs, mandatory):
    """Choose a capacity-sized subset without dropping any mandatory column."""
    n=len(costs);m=len(mandatory)
    if not n or n>m or any(len(row)!=m for row in costs) or sum(mandatory)>n:
        raise ValueError('reserve pool has an invalid capacity or mandatory set')
    padded=costs+[[None if required else 0 for required in mandatory] for _ in range(m-n)]
    return minimum_assignment(padded)[:n]


def validate_opening_birth_dates(desired, fixture_date):
    """Reject obviously recycled biographies, not ordinary teenage players.

    A sourced professional opening squad cannot silently acquire a child from
    a present-day namesake profile. Twelve is a deliberately conservative
    floor, not an assumption that all first-team players are at least sixteen.
    Resolve the original identity instead of substituting an invented DOB.
    """
    day = dt.date.fromisoformat(fixture_date)
    for person in desired:
        bio = person['source_player']
        born = dt.date.fromisoformat(bio['birth_date'])
        age = day.year - born.year - ((day.month, day.day) < (born.month, born.day))
        if age < 12:
            raise ValueError('opening biography identifies a child/future namesake; explicit identity review required: '
                + bio['name'])


def original_matchday_club_witness(actual, desired):
    """Use one provider's dated complete XI/bench without guessing a TM club ID.

    This applies only to a complete fixed-capacity matchday replacement. It
    never authorises annual-only reserves, a cross-provider ownership claim,
    or a single displaced-player swap. Originals are independently replayed
    by prepare and again by the private native builder.
    """
    match = actual['original_match']
    found = re.fullmatch(r'soccerbase/team/([1-9][0-9]*)/august',actual['source_capture']['source_path'])
    if (found is None or match.get('provider_club_id') != 'soccerbase:'+found.group(1)
            or match.get('date') != actual['fixture']['date']
            or match.get('fixture_date_published_on_original_schedule') is not True):
        raise ValueError('matchday-only club identity lacks exact original provider/date binding')
    original_xi = {row['source_player_id'] for row in match['starting_xi']}
    original_bench = {row['source_player_id'] for row in match['published_bench']}
    selected_xi, selected_bench = set(), set()
    for person in desired:
        provider = person.get('source_display_aliases',{}).get('source_provider_person_id')
        if person['membership']=='starting_xi': selected_xi.add(provider)
        elif person['membership']=='published_bench': selected_bench.add(provider)
        else: raise ValueError('matchday-only club identity cannot admit annual-only reserves')
    if (len(original_xi)!=11 or selected_xi!=original_xi
            or not selected_bench<=original_bench or None in selected_bench
            or len(selected_xi|selected_bench)!=len(desired)):
        raise ValueError('matchday-only replacement differs from the complete original XI/bench')
    return {'source_club_id':match['provider_club_id'],'date':actual['fixture']['date'],
        'historical_identity_selection_basis':'complete-original-provider-matchday-only-v1',
        'original_source_capture':copy.deepcopy(actual['source_capture']),
        'selected_original_starting_xi':sorted(selected_xi),
        'selected_original_bench':sorted(selected_bench),
        'cross_provider_club_identity_claimed':False,'annual_reserve_ownership_authorised':False}


def reserve_people(annual, raw, people, events, source_club_id, day, selected):
    used = {(roster.normalise(p['source_player']['name']), p['source_player']['birth_date']) for p in selected}
    # Conflicting provider birthdays do not create a second roster place for
    # an already selected full name. Keep the original conflict for review;
    # never silently reinterpret either birthday to manufacture a reserve.
    used_names = {name for name, _dob in used}
    result = []
    for player in annual['players']:
        key = roster.normalise(player['name']), player.get('birth_date')
        if key in used or key[0] in used_names or player['position'] not in ('G','D','M','F'): continue
        person = transfer.unique_person({'name': player['name'], 'facts': player}, people)
        if person is None: continue
        interval = transfer.transfer_interval(events.get(person['source_player_id'], []), day)
        if interval.get('status') != 'recorded-entry-and-exit-bracket-fixture' or interval['source_owner_club_id'] != source_club_id:
            continue
        result.append({'source_person': copy.deepcopy(person), 'source_player': copy.deepcopy(player),
            'raw_evidence': copy.deepcopy(raw), 'membership': 'positive-annual-and-dated-opening-reserve',
            'opening_interval': interval})
    return sorted(result, key=lambda r: soccerbase.person_sort_key(r['source_person']['source_player_id']))


def original_matchday_career_club_witness(actual, desired):
    """One provider's exact dated match plus independently reparsed careers.

    No Transfermarkt club identity is inferred. Each extra reserve must have
    an explicit interval at this exact original numerical Soccerbase team.
    """
    from scripts import season_original_soccerbase_reserves_v1 as originals
    matchday = [r for r in desired if r['membership'] in ('starting_xi','published_bench')]
    reserves = [r for r in desired if r['membership']=='positive-original-provider-dated-opening-reserve']
    if len(matchday)+len(reserves)!=len(desired) or not reserves:
        raise ValueError('original career witness requires matchday plus positive career reserves only')
    witness=original_matchday_club_witness(actual,matchday)
    for row in reserves:originals.verify_reserve(row,actual)
    witness.update(historical_identity_selection_basis='complete-original-provider-matchday-and-dated-career-reserves-v1',
        original_provider_career_reserves=copy.deepcopy(reserves),
        annual_reserve_ownership_authorised=False)
    return witness


def match_family_names(replacement):
    """Entire family component from the replayed full biography + match label.

    A full surname is not guessed from its last token. Both original fields
    must explicitly agree on the initial and the entire remaining component;
    multiword family names keep that initial for the native two-string split.
    The caller must retain/replay the original match identity bridge.
    """
    person=replacement['source_person']
    source=replacement.get('source_display_aliases')
    if not source:return []
    soccerbase.explicit_display_names(replacement)
    result=[]
    for alias in source['names']:
        raw={'name':person['name'],'displayName':alias['name']}
        for component in families.components(raw):
            name=component['name']
            if ' ' in name:name=component['explicit_given_component'][0]+'. '+name
            result.append((name,'entire-family-from-replayed-biography-and-match-label'))
    return result


def opening_edge(order,replacement, *, allow_keeper_order_exchange=False):
    """Keep sourced starters in startup slots; never inherit a bench first XI."""
    starter=replacement['membership']=='starting_xi'
    role=replacement['source_player']['position']
    if allow_keeper_order_exchange and 1<=order<=11:
        return starter and role in ('G','D','M','F')
    if order==1:return starter and role=='G'
    if 2<=order<=11:return starter and role in ('D','M','F')
    return not starter


def keeper_exchange(allocation):
    """Describe at most one reciprocal swap within the already sourced XI."""
    starters=[r for r in allocation if r['replacement']['membership']=='starting_xi']
    if len(starters)!=11 or sorted(r['native_startup_order_before'] for r in starters)!=list(range(1,12)):
        raise ValueError('keeper exchange needs the complete XI in existing distinct starter slots')
    keepers=[r for r in starters if r['replacement']['source_player']['position']=='G']
    if len(keepers)!=1:raise ValueError('keeper exchange requires exactly one sourced starting goalkeeper')
    keeper=keepers[0];order=keeper['native_startup_order_before']
    if order==1:return []
    outfielder=next(r for r in starters if r['native_startup_order_before']==1)
    if outfielder['replacement']['source_player']['position'] not in ('D','M','F'):
        raise ValueError('keeper exchange cannot infer an unknown outfield role')
    return [{'carrier_id':r['carrier_id'],'expected_name':r['display']['display_name'],
             'before':r['native_startup_order_before'],'after':n}
            for r,n in sorted([(keeper,1),(outfielder,order)],key=lambda pair:pair[0]['carrier_id'])]


def startup_orders(original,slots):
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(original).entries}
    result={}
    for slot in slots:
        raw=entries[slot['carrier_id']].decode_payload(original)
        end=roster.native_player(raw,slot['carrier_id'])['name_end']
        result[slot['carrier_id']]=raw[end]^0x61
    selected=[order for order in result.values() if 1<=order<=11]
    if sorted(selected)!=list(range(1,12)):
        raise ValueError('whole-club allocation lacks eleven distinct existing startup slots')
    return result


def plausible_unknown_birthday_slot(raw, carrier, reference):
    """Do not let a missing source date inherit a blank/centenarian seed date.

    This certifies plausibility only, never the new person's actual birthday.
    The optional caller contract currently applies only to compact dd6360.
    """
    if raw[2:5]!=bytes.fromhex('dd6360'):return False
    try:
        end=roster.native_player(raw,carrier)['name_end']
        born=dt.date(int.from_bytes(bytes(b^0x61 for b in raw[end+14:end+16]),'little'),
            raw[end+13]^0x61,raw[end+12]^0x61)
        age=reference.year-born.year-((reference.month,reference.day)<(born.month,born.day))
        return 15<=age<=45
    except (ValueError,TypeError,KeyError,IndexError):return False


def allocate(original, displaced, desired, published_aliases, *, published_families=None, capacity_bundle=None,
             opening_slot_orders=None, allow_keeper_order_exchange=False,
             unknown_birthday_reference_date=None, fit_reserve_pool=False):
    reference=(dt.date.fromisoformat(unknown_birthday_reference_date)
               if unknown_birthday_reference_date is not None else None)
    if allow_keeper_order_exchange and opening_slot_orders is None:
        raise ValueError('keeper exchange cannot guess native starter membership')
    if len(displaced) != len(desired) and not (fit_reserve_pool and len(desired)>len(displaced)):
        raise ValueError('whole-club roster must fill the exact native capacity')
    if fit_reserve_pool and (opening_slot_orders is None
            or sum(p['membership']=='starting_xi' for p in desired)!=11):
        raise ValueError('reserve pool requires the complete sourced XI and native starter slots')
    slots = sorted(displaced, key=lambda p: p['carrier_id'])
    people = sorted(desired, key=lambda p: soccerbase.person_sort_key(p['source_person']['source_player_id']))
    if len({p['source_person']['source_player_id'] for p in people}) != len(people):
        raise ValueError('whole-club roster contains a duplicate provider person')
    indexed = IndexedFDIFile.from_bytes(original); entries = {e.record_id: e for e in indexed.entries}
    # Reuse the actual immutable native index. Calling the whole-file delta
    # wrapper for every matrix edge would parse all game players n*n times.
    # Each source alias is still independently verified once, and each native
    # payload is still checked through the exact existing variable-name API.
    candidates = {}
    for j, replacement in enumerate(people):
        person = replacement['source_person']; text = delta.compiler._pm99_text
        names = [(text(replacement['source_player']['name'], label='whole-club player'), 'full-sourced-name')]
        given, family = person.get('given_name'), person.get('family_name')
        if family:
            surname = text(family, label='published surname')
            if given: names.append((text(given[0], label='published initial')+'. '+surname,'published-given-initial-and-full-surname'))
            names.append((surname,'published-full-surname'))
        claim = published_aliases.get(person['source_player_id'])
        if claim is not None and claim['birth_date'] == person['birth_date']:
            names += [(text(a['name'],label='published display name'),'original-explicit-'+a['field'])
                      for a in aliases.verify(claim,person)]
        names += [(text(a['name'],label='original match display name'),'original-Soccerbase-'+a['field'])
                  for a in soccerbase.explicit_display_names(replacement)]
        if (published_families is not None
                and (family_claim:=published_families.get(person['source_player_id'])) is not None
                and family_claim['birth_date']==person['birth_date']):
            names += [(text(a['name'],label='whole original family'),'original-'+a['field'])
                      for a in families.native_candidates(family_claim,person)]
        names += [(text(name,label='entire original match family'),method)
                  for name,method in match_family_names(replacement)]
        from scripts import season_original_fixture_display_v1 as fixture_display
        names += [(text(row['name'],label='published fixture display label'),row['method'])
                  for row in fixture_display.candidates(replacement)]
        if person.get('identity_policy') in ('original-Monagas2003-person-ID-and-explicit-unpublished-DOB-v1', 'original-Monagas2002-person-ID-and-explicit-unpublished-DOB-v1'):
            from scripts import season_monagas_2003_missing_birthday_v1 as missing
            names += [(text(row['name'], label='original unknown-DOB publisher alias'), row['method'])
                      for row in missing.display_candidates(person)]
        candidates[j] = names
    options = {}; costs = [[None]*len(people) for _ in slots]
    for i, slot in enumerate(slots):
        raw = entries[slot['carrier_id']].decode_payload(original)
        streams=[(raw,None)]
        if capacity_bundle is not None:
            from scripts import season_same_carrier_name_capacity_v1 as capacity
            try:
                restored,claim=capacity.recover_slot(original,slot['carrier_id'],capacity_bundle)
                streams.append((entries[slot['carrier_id']].decode_payload(restored),claim))
            except (ValueError,RuntimeError):pass
        old_role = roster.native_player(raw, slot['carrier_id'])['position']
        for j, replacement in enumerate(people):
            if reference is not None and replacement['source_person']['birth_date'] is None:
                if not plausible_unknown_birthday_slot(raw,slot['carrier_id'],reference):continue
            if opening_slot_orders is not None and not opening_edge(opening_slot_orders[slot['carrier_id']],replacement,
                    allow_keeper_order_exchange=allow_keeper_order_exchange):
                continue
            trial = {'player_id': slot['id'], 'carrier_id': slot['carrier_id'], 'replacement': replacement}
            person = replacement['source_person']; claim = published_aliases.get(person['source_player_id'])
            if claim is not None and claim['birth_date'] == person['birth_date']: trial['published_display_names'] = claim
            display = None;capacity_claim=None
            for prepared,claim in streams:
                current = delta.compiler._player_name(prepared, record_id=slot['carrier_id'])
                for name, method in candidates[j]:
                    try:
                        if name.casefold() != current.casefold():
                            delta.compiler._patch_indexed_player_variable_name_payload(prepared,current,name)
                    except (ValueError,RuntimeError): continue
                    display = {'carrier_id':slot['carrier_id'],'source_name':replacement['source_player']['name'],
                               'display_name':name,'method':method}
                    capacity_claim=claim;break
                if display is not None:break
            if display is None: continue
            new_role = replacement['source_player']['position']
            # A whole-club transaction can change the keeper count, but must
            # also explicitly rewrite its complete XI/order/tactics. No reserve
            # swap caller may use this allocation to bypass starter protection.
            costs[i][j] = 10000*int(old_role != new_role) + 1000*int(('G' in (old_role,new_role)) and old_role != new_role) + abs(i-j)
            if fit_reserve_pool and replacement['membership'] not in ('starting_xi','published_bench'):
                costs[i][j] += 1000000  # Prefer usable original bench, never discard a starter.
            options[i,j] = dict(trial, before_recipe=copy.deepcopy(slot), display=display,
                native_broad_role_before=old_role, native_broad_role_after=new_role)
            if opening_slot_orders is not None:
                options[i,j]['native_startup_order_before']=opening_slot_orders[slot['carrier_id']]
            if capacity_claim is not None:options[i,j]['same_carrier_name_capacity']=capacity_claim
    try:
        # Dummy rows can discard surplus reserves, but NEVER an original XI
        # member. The existing exact square solver still proves a full fit.
        selected = (minimum_reserve_pool_assignment(costs,[p['membership']=='starting_xi' for p in people])
            if fit_reserve_pool else minimum_assignment(costs))
    except ValueError as exc:
        details = [(p['source_player']['name'], sum((i,j) in options for i in range(len(slots))))
                   for j,p in enumerate(people)]
        raise ValueError(str(exc)+'; independently fitted carrier counts='+str(details)) from exc
    result=[options[i,j] for i,j in enumerate(selected)]
    if allow_keeper_order_exchange:
        exchange={r['carrier_id']:r['after'] for r in keeper_exchange(result)}
        for row in result:
            row['native_startup_order_after']=exchange.get(row['carrier_id'],row['native_startup_order_before'])
        if any(not opening_edge(r['native_startup_order_after'],r['replacement']) for r in result):
            raise ValueError('bounded keeper exchange does not restore the exact one-keeper source XI')
    return result


def opening_pool_for_capacity(desired, capacity, *, fit_verified_reserve_pool=False):
    """Keep all published bench alternatives until exact native fitting.

    The legacy route retains its original first-N policy for SOURCE replay.
    The opted-in route must not silently discard a later published bench
    member merely because an earlier name cannot fit the native window.
    """
    if capacity < 11:
        raise ValueError('native capacity cannot contain the exact first XI')
    if fit_verified_reserve_pool:
        if sum(p['membership'] == 'starting_xi' for p in desired) != 11:
            raise ValueError('reserve pool requires eleven original starters')
        return list(desired), max(0, capacity-len(desired))
    return list(desired[:capacity]), max(0, capacity-len(desired))


def prepare(season, carrier, new_club, person_path, history_path, entity_path, output, *, capacity_bundle=None,
            baseline_release_id=None, inspect_collisions=False, snapshot_binding=None,
            allow_keeper_order_exchange=False, snapshot_loader=None, public_loader=None,
            identity_review_path=None, allow_original_matchday_only_club_identity=False,
            allow_original_provider_career_reserves=False, retained_source_label_review_path=None,
            exclude_unpublished_bench_birth_dates=False, fit_verified_reserve_pool=False):
    if allow_keeper_order_exchange and not inspect_collisions:
        raise ValueError('keeper startup exchange is limited to complete coupled source transactions')
    if allow_original_matchday_only_club_identity and not inspect_collisions:
        raise ValueError('original matchday-only identity is limited to complete source transactions')
    if allow_original_provider_career_reserves and not inspect_collisions:
        raise ValueError('original career reserves require a complete source transaction')
    if retained_source_label_review_path is not None and not inspect_collisions:
        raise ValueError('retained authored identity is limited to source-only collision diagnostics')
    if exclude_unpublished_bench_birth_dates and not (inspect_collisions and identity_review_path is not None):
        raise ValueError('optional bench exclusions require a complete source transaction and explicit identity review')
    if fit_verified_reserve_pool and not (inspect_collisions and allow_original_provider_career_reserves):
        raise ValueError('reserve pool fitting requires a complete source transaction and dated provider reserve authority')
    if output.exists(): raise ValueError('whole-club source proposal is immutable')
    output.parent.mkdir(parents=True,exist_ok=True)
    # Source-only preparation may overlap an independently checked pending
    # build. Bind its exact registered bytes; never promote it here.
    release = (registry.load_registered_release(season,baseline_release_id) if baseline_release_id
               else registry.load_preferred_release(season))
    layers = list(planner.package_layers(release)); clubs = [c for _,p,_ in layers for c in p['clubs']]
    players = [x for _,p,_ in layers for x in p['players']]
    old = [c for c in clubs if c['carrier_id'] == carrier]
    if len(old) != 1 or not 3300 <= carrier <= 3331: raise ValueError('only one declared non-playable English club can be replaced')
    old = old[0]
    same = [c for c in clubs if c['carrier_id'] != carrier and club_keys(old['name'],old.get('full_name','')) &
            club_keys(c['name'],c.get('full_name',''))]
    retained_binding = None
    if not same and retained_source_label_review_path is not None:
        from scripts import season_retained_duplicate_club_identity_v1 as retained_identity
        retained,retained_binding=retained_identity.verified_retained(release,old,retained_source_label_review_path)
        same=[retained]
    elif retained_source_label_review_path is not None:
        raise ValueError('retained authored identity review is unnecessary for already matching native labels')
    if not same: raise ValueError('old carrier does not demonstrably duplicate another declared real club')
    if any(club_keys(new_club) & club_keys(c['name'],c.get('full_name','')) for c in clubs):
        raise ValueError('proposed target club is already represented')
    bindings = {'published_person_supplement': public.binding(person_path, persons.POLICY),
        'published_transfer_supplement': public.binding(history_path, histories.POLICY)}
    if retained_binding is not None:bindings['retained_duplicate_label_review']=retained_binding
    people,events={},{}
    if snapshot_binding is not None:
        from scripts import season_duplicate_source_context_v1 as context
        loader = snapshot_loader or context.load_snapshot
        people,events,actual_pin=loader(ROOT/snapshot_binding['path'],
            ROOT/snapshot_binding['pinned_receipt_path'])
        if actual_pin!=snapshot_binding:raise ValueError('whole-club original person/history snapshot changed')
        bindings['snapshot']=copy.deepcopy(snapshot_binding)
    people, events, _ = (public_loader or public.merge_bound)(people, events, bindings)
    captures, _ = roster.load_sources(season)
    source_names = club_keys(new_club)
    opening = [c for c in captures if c['source_path'].startswith('soccerbase/team/') and
        source_names & club_keys(c['club_name'])]
    annuals = [c for c in captures if c['source_path'].endswith('.txt') and
        roster.source_group(c['country_catalog'])=='england' and source_names & club_keys(c['club_name'])]
    if not opening or len(annuals)>1:
        raise ValueError('target needs one original first-fixture capture and unambiguous optional annual facts')
    review = json.loads(identity_review_path.read_text()) if identity_review_path is not None else None
    allow_missing_birthday = bool(review and (review.get('allow_explicitly_reviewed_missing_provider_birth_date')
        or exclude_unpublished_bench_birth_dates))
    equivalent_openings = None
    if len(opening) > 1:
        from scripts import season_equivalent_soccerbase_openings_v1 as equivalents
        chosen, actual, equivalent_openings = equivalents.select(opening,
            lambda capture: replay.replay_club(season, capture, people, True,
                allow_missing_birth_date=allow_missing_birthday))
        opening = [chosen]
    else:
        actual = replay.replay_club(season, opening[0], people, True,
                                   allow_missing_birth_date=allow_missing_birthday)
    entities = club_entities.read_entities(entity_path)
    witness = None
    try:
        witness = soccerbase.confirm_club_mapping(actual, entities, events)
    except ValueError as exc:
        if not (allow_original_matchday_only_club_identity and str(exc)==
                'Soccerbase club identity lacks two consistent dated starter ownership brackets'):
            raise
    annual=annuals[0] if annuals else None
    raw=roster.SourceVerifier(season).verify(annual) if annual is not None else {
        'status':'secondary-fact-source-not-captured',
        'reason':'Use independently replayed biographies and first-fixture roles; log other facts as missing.'}
    if annual is not None and raw['status'] != 'raw-source-reparsed':
        raise ValueError('annual source facts do not independently reparse')
    resolutions={}
    role_resolutions={}
    if identity_review_path is not None:
        if review.get('schema_version')!='pm99-explicit-provider-person-identity-resolution-v1':
            raise ValueError('unsupported provider identity resolution review')
        if review.get('season')!=season or review.get('club')!=new_club:
            raise ValueError('provider identity review describes another season or club')
        for item in review['resolutions']:
            id=item['source_provider_person_id']
            if id in resolutions:raise ValueError('provider identity review repeats a person')
            if not item.get('reason') or not item.get('corroboration_url'):
                raise ValueError('provider identity resolution lacks an explicit editorial reason/source')
            resolutions[id]=item
        known={r['soccerbase_person']['source_player_id'] for group in actual['identity_bridges'].values() for r in group}
        if not set(resolutions)<=known:raise ValueError('identity review contains a person absent from the original fixture')
        for item in review.get('bench_role_resolutions', []):
            id = item['source_provider_person_id']
            if id in role_resolutions or id not in known:
                raise ValueError('secondary bench role repeats or names an absent original player')
            role_resolutions[id] = item
        bindings['provider_identity_review']=public.binding(identity_review_path,review['schema_version'])
    if exclude_unpublished_bench_birth_dates:
        from scripts import derive_provider_identity_resolutions_v1 as derivation
        independently_derived, gaps = derivation.derive(season,new_club,actual,annual or {'players':[]},people,
            exclude_unpublished_bench_birth_dates=True)
        if gaps or independently_derived != review:
            raise ValueError('optional bench exclusion review does not independently reproduce or omits identity gaps')
    elif review and 'optional_bench_exclusions' in review:
        raise ValueError('optional bench exclusion review requires its explicit complete-club policy')
    desired = matchday_people(actual, annual or {'players':[]},identity_resolutions=resolutions,people=people,
        exclude_unpublished_bench_birth_dates=exclude_unpublished_bench_birth_dates,
        role_resolutions=role_resolutions)
    capacity = len(old['roster_player_ids'])
    desired, needed = opening_pool_for_capacity(desired, capacity,
        fit_verified_reserve_pool=fit_verified_reserve_pool)
    if witness is None:
        if needed>0 or fit_verified_reserve_pool:
            if not allow_original_provider_career_reserves:
                raise ValueError('matchday-only complete source lacks enough published opening bench places; dated reserves need a separate club bridge')
            from scripts import season_original_soccerbase_reserves_v1 as originals
            original_matchday_club_witness(actual,desired)
            reserves=originals.candidates(season,opening[0],actual,desired,
                **({'annual':annual} if fit_verified_reserve_pool else {}))
            if len(reserves)<needed:
                raise ValueError('original provider lacks enough positive dated opening reserves')
            desired += reserves if fit_verified_reserve_pool else reserves[:needed];needed=0
            witness=original_matchday_career_club_witness(actual,desired)
        else:
            witness = original_matchday_club_witness(actual,desired)
    if needed>0 or (fit_verified_reserve_pool and witness.get('historical_identity_selection_basis') not in (
            'complete-original-provider-matchday-and-dated-career-reserves-v1',)):
        reserves = reserve_people(annual or {'players':[]},raw,people,events,witness['source_club_id'],actual['fixture']['date'],desired)
        if allow_original_provider_career_reserves and (len(reserves)<needed or fit_verified_reserve_pool):
            from scripts import season_original_soccerbase_reserves_v1 as originals
            provider_reserves=originals.candidates(season,opening[0],actual,desired+reserves,
                **({'annual':annual} if fit_verified_reserve_pool else {}))
            occupied={(roster.normalise(r['source_player']['name']),r['source_player']['birth_date']) for r in reserves}
            reserves += [r for r in provider_reserves if (roster.normalise(r['source_player']['name']),
                r['source_player']['birth_date']) not in occupied]
        if len(reserves) < needed:
            raise ValueError(f'fixed capacity lacks {needed-len(reserves)} positively dated opening reserves')
        desired += reserves if fit_verified_reserve_pool else reserves[:needed]
    validate_opening_birth_dates(desired, actual['fixture']['date'])
    outside = [p for p in players if p['club_id'] != old['id']]
    collisions = []
    for wanted in desired:
        person = wanted['source_person']; bio = wanted['source_player']
        for player in outside:
            observed = transfer.unique_person(player, people)
            secondary_name_collision=(any(wanted.get('source_identity_resolution',{}).get(key) is not None
                    for key in ('secondary_birthday_policy','prior_delivered_birthday_witness'))
                and roster.normalise(player.get('source_name') or player['name'])==roster.normalise(bio['name']))
            if secondary_name_collision or (observed is not None and observed['source_player_id'] == person['source_player_id']) or (
                    roster.person_identity_key(player) == (roster.normalise(bio['name']),bio['birth_date'])):
                collisions.append({'source_player_id': person['source_player_id'], 'other_player_id': player['id'],
                    'other_club_id': player['club_id']})
    if collisions and not inspect_collisions:
        raise ValueError('incoming players have other-club copies requiring a paired transaction: '+str(collisions))
    original = (release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    displaced=[p for p in players if p['club_id']==old['id']]
    opening_slot_orders=startup_orders(original,displaced)
    allocation_gap = None
    try:
        allocation = allocate(original,displaced,desired,aliases.claims(person_path),
            published_families=families.claims(person_path,{r['source_person']['source_player_id'] for r in desired
                                                         if type(r['source_person']['source_player_id']) is int}),
            capacity_bundle=capacity_bundle,opening_slot_orders=opening_slot_orders,
            allow_keeper_order_exchange=allow_keeper_order_exchange,fit_reserve_pool=fit_verified_reserve_pool)
    except ValueError as exc:
        allocation = []; allocation_gap = str(exc)
    reserve_pool = copy.deepcopy(desired) if fit_verified_reserve_pool else None
    if fit_verified_reserve_pool and allocation:
        selected_ids={r['replacement']['source_person']['source_player_id'] for r in allocation}
        desired=[r for r in desired if r['source_person']['source_player_id'] in selected_ids]
        collisions=[r for r in collisions if r['source_player_id'] in selected_ids]
        if witness.get('historical_identity_selection_basis')=='complete-original-provider-matchday-and-dated-career-reserves-v1':
            witness=original_matchday_career_club_witness(actual,desired)
    document = {'schema_version':SCHEMA,'season':season,'release_id':release.release_id,
        'package_sha256':registry.sha256_file(release.package_path),'jug_sha256':registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
        'eq_sha256':registry.sha256_file(release.game_path/'DBDAT/EQ98030.FDI'), 'before_club':old,
        'retained_duplicate_clubs':same,'new_club':new_club,'club_witness':witness,
        'bindings':bindings,'entity_binding':public.binding(entity_path,'published-club-discovery-only'),
        'opening_capture':opening[0], 'annual_capture':annual, 'annual_raw':raw,
        'original_opening':actual,'desired_people':desired,'allocation':allocation,'allocation_gap':allocation_gap,
        'native_opening_slot_policy':'sourced-XI-in-preserved-distinct-startup-slots-one-keeper-in-slot-one-v1',
        'required_followup':['independent raw replay','dated manager','explicit XI/order/tactics transaction',
            'kit and ground fallback declarations','native preservation/readback','runner evidence','no-new-duplicate audit'],
        'native_games_modified':0,'approved_for_native_publication':False}
    if equivalent_openings is not None:
        document['equivalent_original_opening_captures'] = equivalent_openings
    if allow_keeper_order_exchange:
        document['native_opening_slot_policy']='complete-sourced-XI-with-bounded-owned-mode1-reciprocal-keeper-order-exchange-v1'
        document['allow_keeper_order_exchange']=True
        document['startup_order_exchange']=keeper_exchange(allocation) if allocation else []
    if capacity_bundle is not None:
        document['capacity_policy_bundle']=copy.deepcopy(capacity_bundle)
    if allow_original_matchday_only_club_identity:
        document['allow_original_matchday_only_club_identity']=True
    if allow_original_provider_career_reserves:
        document['allow_original_provider_career_reserves']=True
    if exclude_unpublished_bench_birth_dates:
        document['exclude_unpublished_bench_birth_dates']=True
        document['optional_bench_exclusions']=copy.deepcopy(review['optional_bench_exclusions'])
    if fit_verified_reserve_pool:
        document['fit_verified_reserve_pool']=True
        document['verified_reserve_pool']=reserve_pool
        document['reserve_pool_selection_policy']='exact-native-fit-all-eleven-starters-mandatory-prefer-published-bench-v1'
    if inspect_collisions:
        # A diagnostic proposal deliberately uses a DIFFERENT schema. The
        # native candidate builder must reject it, even when collisions happen
        # to be empty. It supplies no exception to native publication guards.
        document['schema_version']='pm99-whole-club-collision-diagnostic-only-v1'
        document['outside_collisions']=collisions
        document['collision_inspection_only']=True
    pipeline.write_canonical_json(output,document)
    return {'season':season,'old_club':old['name'],'new_club':new_club,'allocated_native_slots':len(allocation),
        'original_XI':11,'published_bench':sum(r['membership']=='published_bench' for r in desired),
        'dated_reserves':sum(r['membership']=='positive-annual-and-dated-opening-reserve' for r in desired),
        'allocation_gap':allocation_gap,'native_games_modified':0,'approved_for_native_publication':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--season',required=True); parser.add_argument('--carrier',type=int,required=True)
    parser.add_argument('--club',required=True); parser.add_argument('--people',type=Path,required=True)
    parser.add_argument('--histories',type=Path,required=True); parser.add_argument('--entities',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    print(json.dumps(prepare(args.season,args.carrier,args.club,args.people,args.histories,args.entities,args.output)))
