"""Original Soccerbase evidence bridge for a future explicit repair opt-in.

No native writes. Reconstruct every identity from raw source URL/SHA receipts,
require a complete independent full-name/DOB bridge, and preserve date provider
semantics. Current public club names are stable-ID discovery, not dated player
membership. An ambiguous lifecycle or unmatched club remains a gap.
"""
import copy
import collections
import json
import re
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import season_english_result_date_binding_v1 as club_entities
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_release_registry_v1 as registry

POLICY = 'replayed-original-Soccerbase-complete-full-name-DOB-bridges-and-exact-fixture-v1'
PERSON_POLICY = 'original-Soccerbase-full-biography-name-DOB-identity-no-provider-ID-conflation-v1'
# Explicit provider label differences. These discover a candidate stable ID;
# only the original historical sheet supplies dated player membership.
CLUB_ALIASES = {
    'Doncaster': ('Doncaster R.', 'Doncaster Rovers', 'Doncaster Rovers Football Club'),
    'Boreham W': ('Boreham Wood', 'Boreham Wood FC'),
    'Aldershot': ('Aldershot Town', 'Aldershot Town FC'),
    'Kettering': ('Kettering Town', 'Kettering Town FC'),
    'Dover': ('Dover Athletic', 'Dover Athletic FC'),
    'Forest Green': ('Forest Green Rovers', 'Forest Green Rovers FC'),
    'Dag & Red': ('Dagenham & Redbridge', 'Dagenham & Redbridge FC'),
    'Boston Utd': ('Boston United', 'Boston United FC'),
    'Kidderminster': ('Kidderminster Harriers', 'Kidderminster Harriers FC'),
    'Morecambe': ('Morecambe FC',),
    'Northwich': ('Northwich Victoria', 'Northwich Victoria FC'),
    'Nuneaton': ('Nuneaton Borough', 'Nuneaton Borough FC'),
    'Stevenage': ('Stevenage FC', 'Stevenage Borough'),
    'Altrincham': ('Altrincham FC',),
    'Gateshead': ('Gateshead FC',),
    'Tamworth': ('Tamworth FC',),
    'Braintree': ('Braintree Town', 'Braintree Town FC'),
    'Rushden': ('Rushden & Diamonds',),
    'Gravesend': ('Gravesend & Northfleet',),
    'York': ('York City', 'York City FC'),
    'Woking': ('Woking FC',),
    'Welling': ('Welling United', 'Welling United FC'),
    'Southport': ('Southport FC',),
    'Wrexham': ('Wrexham AFC',),
    # Original entity response 3822 publishes "Weymouth FC". The exact
    # historical first sheet plus consistent dated starter brackets must
    # still establish membership; this alias alone approves nothing.
    'Weymouth': ('Weymouth FC',),
    # The same 5 August 2017 opener is "Fylde" on Soccerbase and "AFC
    # Fylde" in Boreham Wood's original match report. Do not propose a
    # second club merely because its short provider label omits AFC.
    'Fylde': ('AFC Fylde',),
    'Chester': ('Chester FC',),
    'Barrow': ('Barrow AFC',),
    'Torquay': ('Torquay United', 'Torquay United FC'),
    'Hartlepool': ('Hartlepool United', 'Hartlepool United FC'),
    'Lincoln': ('Lincoln City', 'Lincoln City FC'),
    'Macclesfield': ('Macclesfield Town', 'Macclesfield Town FC'),
    'Telford': ('Telford United',),
    'Leigh Genesis': ('Leigh RMI', 'Leigh Genesis FC'),
    'Hednesford': ('Hednesford Town',),
    'Hayes': ('Hayes FC',),
    'Kingstonian': ('Kingstonian FC',),
    'Scarborough': ('Scarborough FC',),
    'Halifax': ('Halifax Town', 'Halifax Town AFC', 'FC Halifax Town'),
}


def club_candidates(name, entities):
    wanted = roster.club_names('england', name)
    wanted.update(roster.normalise(n) for n in CLUB_ALIASES.get(name, ()))
    # Type 0/main 0 can describe retired historic clubs. They are discovery
    # candidates only: the original league sheet and dated starter brackets
    # must positively establish their historical identity before use.
    return [e for e in entities.values() if e['country_id'] in (189,191)
        and not e['is_national_team']
        and ((e['club_type_id']==1 and str(e['main_club_id'])==str(e['source_club_id']))
             or (e['club_type_id']==0 and str(e['main_club_id'])=='0'))
        and any(roster.normalise(n) in wanted for n in e['published_names'])]


def discover_club_id(name, entities):
    matches = club_candidates(name, entities)
    if len(matches)!=1:
        raise ValueError('Soccerbase club lacks one exact stable-ID candidate; lifecycle/name ambiguity remains')
    return matches[0]['source_club_id']


def confirm_club_mapping(actual, entities, events):
    """Corroborate the cross-provider club ID at the original fixture date.

    Name discovery alone is insufficient, especially for liquidated/reformed
    clubs. Require at least two distinct sourced starters with independent
    bracketing histories at this ID, and refuse any contrary complete bracket.
    Missing histories never count as positive votes.
    """
    candidates=club_candidates(actual['club'],entities)
    day=actual['fixture']['date']; brackets=[]
    for row in actual['identity_bridges']['starting_xi']:
        person=row['transfermarkt_person']
        if person is None:
            continue
        interval=transfer.transfer_interval(events.get(person['source_player_id'],[]),day)
        if interval['status']!='recorded-entry-and-exit-bracket-fixture':
            continue
        brackets.append({'source_player_id':person['source_player_id'],'interval':interval})
    eligible=[]
    for entity in candidates:
        id=entity['source_club_id']
        positives=[b for b in brackets if b['interval']['source_owner_club_id']==id]
        if len({p['source_player_id'] for p in positives})>=2 and len(positives)==len(brackets):
            eligible.append((id,positives))
    if len(eligible)!=1:
        raise ValueError('Soccerbase club identity lacks two consistent dated starter ownership brackets')
    id,positives=eligible[0]
    return {'source_club_id':id,'date':day,'positive_starter_brackets':positives,
            'candidate_club_ids':sorted(e['source_club_id'] for e in candidates),
            'historical_identity_selection_basis':'original-league-sheet-and-consistent-dated-starter-brackets',
            'club_name_discovery_is_not_dated_membership':True}


def native_starters(release, club, native=None):
    """Read encoded EQ roster plus decoded JUG order; never recipe absence.

    A caller may retain the indexes between clubs. Failure is a refusal, not
    permission to assume that a non-playable club has no native starters.
    """
    from scripts import season_contextual_tactics_v1 as tactics
    from app.fdi_indexed import IndexedFDIFile
    if native is None:
        eq=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
        jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        native=(eq,jug,{e.record_id:e for e in IndexedFDIFile.from_bytes(eq).entries},
                      {e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries})
    eq,jug,eqs,jugs=native
    entry=eqs[club['carrier_id']]
    encoded=eq[entry.payload_offset:entry.payload_offset+entry.payload_length]
    return {id for id,_ in tactics.native_xi(encoded,jug,jugs)},native


def extend_original_people(people, document):
    """Add original provider identities without inventing Transfermarkt IDs.

    The original review is already hash-bound by the caller. Independently
    read every used biography/receipt again, reject inconsistent dates or
    shared name/DOB aliases, and preserve known Transfermarkt identities.
    This is identity only, never an opening-ownership decision.
    """
    claims=collections.defaultdict(dict);dates=collections.defaultdict(set)
    for section in document['seasons']:
        for row in section['clubs']:
            if row['status']!='original-first-fixture-reparsed':continue
            by_url={s['url']:s for s in row['raw_sources']}
            for entries in row['identity_bridges'].values():
                for entry in entries:
                    if entry['transfermarkt_person'] is not None:continue
                    person=entry['soccerbase_person'];id=person['source_player_id']
                    if not re.fullmatch(r'soccerbase:\d+',id):
                        raise ValueError('original Soccerbase person lacks a proper provider namespace')
                    key=(transfer._normalise(person['name']),person['birth_date'])
                    source=by_url.get(person['source_profile_url'])
                    if source is None:raise ValueError('original Soccerbase identity lacks its raw biography proof')
                    dates[id].add(person['birth_date'])
                    claims[id][key]=(person,source)
    alias_ids=collections.defaultdict(set)
    for id,rows in claims.items():
        for key in rows:alias_ids[key].add(id)
    result={key:dict(rows) for key,rows in people.items()};added=[];refused=[]
    for id,aliases in sorted(claims.items()):
        if len(dates[id])!=1 or any(len(alias_ids[key])!=1 for key in aliases):
            refused.append({'source_player_id':id,'reason':'conflicting-original-DOB-or-shared-full-name-DOB'})
            continue
        if any(people.get(key) for key in aliases):
            # Known cross-provider people and ambiguous publisher matches are
            # not assigned a competing second identity.
            continue
        for key,(person,source) in sorted(aliases.items()):
            path=registry.ROOT/source['path']
            receipt=registry.ROOT/source['source_receipt_path']
            if (registry.sha256_file(path)!=source['sha256']
                    or registry.sha256_file(receipt)!=source['source_receipt_sha256']
                    or json.loads(receipt.read_text())!={'url':source['url'],'sha256':source['sha256']}):
                raise ValueError('original Soccerbase identity biography URL/SHA changed')
            actual=original.profile(path.read_bytes(),{'source_player_id':id,
                'provider_player_id':person['provider_player_id']},source['url'])
            if actual!=person:raise ValueError('Soccerbase identity does not reproduce from original full biography')
        person=aliases[sorted(aliases)[0]][0]
        canonical={'source_player_id':id,'source_provider':'soccerbase','name':person['name'],
            'given_name':None,'family_name':None,'birth_date':person['birth_date'],
            'source_profile_url':person['source_profile_url']}
        for key in aliases:result.setdefault(key,{})[id]=copy.deepcopy(canonical)
        added.append({'source_player_id':id,'birth_date':person['birth_date'],
                      'published_full_name_aliases':sorted(p['name'] for p,_ in aliases.values())})
    return result,{'policy':PERSON_POLICY,'added':added,'refused':refused,'ownership_established':False}


def person_id(person):
    id=person['source_player_id']
    if person.get('identity_policy')=='original-City2024-August-primary-member-literal-Wikipedia-DOB-v1':
        from scripts import season_city_2024_opening_exchange_v1 as city
        return city.verify_person(person)
    if person.get('identity_policy') in ('original-Monagas2003-person-ID-and-explicit-unpublished-DOB-v1', 'original-Monagas2002-person-ID-and-explicit-unpublished-DOB-v1'):
        from scripts import season_monagas_2003_missing_birthday_v1 as missing
        return missing.verify(person)
    if isinstance(id,str) and id.startswith('fixture-actor:'):
        from scripts import season_original_fixture_display_v1 as fixture_display
        return fixture_display.verify_actor(person)
    if type(id) is int and id>0:return 'person-transfermarkt-'+str(id)
    if (isinstance(id,str) and re.fullmatch(r'soccerbase:\d+',id)
            and person.get('source_provider')=='soccerbase'):
        return 'person-soccerbase-'+id.split(':')[1]
    if (isinstance(id,str) and id.startswith('wikipedia:') and person.get('source_provider')=='wikipedia'
            and person.get('source_profile_url')=='https://en.wikipedia.org/wiki/'+id.split(':',1)[1]
            and person.get('identity_policy') in ('original-Wikipedia-full-name-DOB-unique-senior-interior-year-v1',
                'original-Wikipedia-full-name-DOB-explicit-entry-month-v1')
            and person.get('name') and person.get('birth_date')):
        import hashlib
        return 'person-wikipedia-'+hashlib.sha256((id+'|'+person['birth_date']).encode()).hexdigest()[:24]
    raise ValueError('unsupported or unconfirmed replacement person provider namespace')


def person_sort_key(id):
    return (0,id) if type(id) is int else (1,str(id))


def existing_identity_protection(players):
    dates={p['facts']['birth_date'] for p in players if isinstance(p['facts'].get('birth_date'),str)}
    undated_names={roster.normalise(p.get('source_name') or p['name']) for p in players
        if not isinstance(p['facts'].get('birth_date'),str)}
    return dates,undated_names


def reconstruct(row, season, capture, people):
    """Compare saved claims to independently replayed raw pages, not summaries."""
    if row['status']!='original-first-fixture-reparsed':
        raise ValueError('Soccerbase source review is not a reparsed first fixture')
    if row.get('source_capture',{}).get('targeted_original_capture') is not None:
        from scripts import season_targeted_soccerbase_opening_replay_v1 as targeted
        return targeted.reconstruct(row,season,people)
    actual=replay.replay_club(season,capture,people,
        row.get('original_match',{}).get('policy')!=original.POLICY)
    # Source-review selection labels do not confer an identity or native proof.
    saved={k:v for k,v in row.items() if k!='represented_native_clubs'}
    if actual!=saved:
        raise ValueError('Soccerbase source review does not reproduce from original pages')
    if any(len(actual['identity_bridges'][field])!=len(actual['original_match'][field])
           for field in ('starting_xi','published_bench')):
        raise ValueError('Soccerbase matchday lacks a full-name/DOB original biography for every listed person')
    values=[p for ps in actual['identity_bridges'].values() for p in ps]
    ids=[p['transfermarkt_person']['source_player_id'] for p in values if p['transfermarkt_person'] is not None]
    if len(ids)!=len(set(ids)):
        raise ValueError('multiple Soccerbase people map to one independent person')
    return actual


def evidence(actual, club_witness, people=None):
    if any(g.get('reason')!='no-unique-independent-full-name-DOB-provider-bridge'
           for g in actual['identity_gaps']):
        raise ValueError('unidentified Soccerbase biographies cannot become complete ownership evidence')
    source_club_id=club_witness['source_club_id']
    if club_witness['date']!=actual['fixture']['date']:
        raise ValueError('Soccerbase club-ID witness belongs to another fixture date')
    groups=actual['identity_bridges']
    def resolved_person(p):
        target=p['transfermarkt_person']
        if target is None and people is not None:
            target=transfer.unique_person({'name':p['soccerbase_person']['name'],
                'facts':p['soccerbase_person']},people)
        return target
    def source_key(p):
        target=resolved_person(p)
        return str(target['source_player_id']) if target is not None else p['soccerbase_person']['source_player_id']
    xi={source_key(p):p['soccerbase_person']['name']
        for p in groups['starting_xi']}
    bench={source_key(p):p['soccerbase_person']['name']
        for p in groups['published_bench']}
    if len(xi)!=11 or set(xi)&set(bench):
        raise ValueError('Soccerbase bridged sheet does not contain eleven distinct actual starters')
    proofs=copy.deepcopy(actual['raw_sources'])
    result={'source_club_id':source_club_id,'date':actual['fixture']['date'],
        'starting_xi':xi,'substitutes':bench,'raw_sources':proofs,
        'match_page_date_independently_published':False,
        'fixture_date_published_on_original_schedule':True,
        'source_provider_policy':POLICY,
        'provider_club_id':actual['original_match']['provider_club_id'],
        'soccerbase_provider_club_identity_witness':copy.deepcopy(club_witness),
        'soccerbase_original_fixture':copy.deepcopy(actual['fixture']),
        'soccerbase_verified_replacements':[]}
    unbridged=[p['soccerbase_person'] for ps in groups.values() for p in ps
        if resolved_person(p) is None or type(resolved_person(p)['source_player_id']) is not int]
    if unbridged:
        if people is None:
            raise ValueError('unbridged original people require independent ambiguity protection')
        dates={p['birth_date'] for p in unbridged}
        # A missing cross-provider bridge is not evidence of absence. Protect
        # every independent source person with a matching DOB rather than
        # silently expand an initial, nickname or alternate name spelling.
        candidates={str(p['source_player_id']) for variants in people.values() for p in variants.values()
                    if type(p['source_player_id']) is int and p['birth_date'] in dates}
        result['unresolved_person_id_candidates']=sorted(candidates)
        result['unbridged_original_provider_people']=copy.deepcopy(unbridged)
    for person in groups['published_bench']:
        role=person['dated_match_position']
        if role not in ('G','D','M','F'):
            continue
        identity=person['soccerbase_person']; target=resolved_person(person)
        if target is None:continue
        path=next(p for p in proofs if p['url']==identity['source_profile_url'])
        result['soccerbase_verified_replacements'].append({
            'source_player':{'name':identity['name'],'birth_date':identity['birth_date'],
                'position':role,'nationality':None,'height_cm':None,'weight_kg':None,'shirt_number':None},
            'source_person':copy.deepcopy(target),
            'source_display_aliases':{'policy':POLICY,'source_provider_person_id':identity['source_player_id'],
                'source_person_id':target['source_player_id'],'birth_date':identity['birth_date'],
                'names':[{'field':'dated-match-label','name':person['published_match_name']}]},
            'source_capture':copy.deepcopy(actual['source_capture']),
            'raw_evidence':{'status':'raw-source-reparsed','local_path':path['path'],
                'source_path':path['path'],'source_sha256':path['sha256'],
                'soccerbase_source_policy':POLICY},
            'opening_eligibility':{'method':'positive-first-fixture-substitute-id',
                'date':result['date'],'source_club_id':source_club_id}})
    return result


def attach(bindings, season, clubs, captures, people, events, existing, raw_identity_people=None):
    """Fill missing evidence only after raw-page and cross-provider replay."""
    item=bindings.get('soccerbase_opening_sources')
    if item is None:
        return existing,[]
    if item.get('policy')!=POLICY:
        raise ValueError('unsupported Soccerbase duplicate source policy')
    for key in ('review','club_entities'):
        bound=item[key]
        if registry.sha256_file(registry.ROOT/bound['path'])!=bound['sha256']:
            raise ValueError('immutable Soccerbase source-policy input changed')
    document=json.loads((registry.ROOT/item['review']['path']).read_text())
    if document.get('policy')!=replay.POLICY:
        raise ValueError('unsupported original Soccerbase provider bridge review')
    if (document['snapshot_binding']!=bindings['snapshot'] or
            document['published_person_binding']!=bindings.get('published_person_supplement')):
        raise ValueError('Soccerbase independent person inputs differ from bound snapshot/public identities')
    sections=[s for s in document['seasons'] if s['season']==season]
    if len(sections)!=1:
        raise ValueError('Soccerbase source review lacks one exact season')
    section=sections[0]
    if not section['clubs']:
        return existing,[]
    pin=section.get('capture_input')
    if pin is not None:
        if registry.sha256_file(registry.ROOT/pin['path'])!=pin['sha256']:
            raise ValueError('Soccerbase original capture changed')
    elif any(r.get('status')=='original-first-fixture-reparsed'
             and r.get('source_capture',{}).get('targeted_original_capture') is None for r in section['clubs']):
        raise ValueError('legacy Soccerbase original source lacks its capture input binding')
    # A season without a legacy bundle can acquire independently bound
    # targeted originals. Each such raw URL/SHA is replayed below; never invent
    # a legacy capture_input or loosen its verification when it exists.
    entities=club_entities.read_entities(registry.ROOT/item['club_entities']['path'])
    result=dict(existing); unresolved=[]
    by_carrier={c['carrier_id']:c for c in clubs}
    for row in section['clubs']:
        represented=[by_carrier[r['carrier_id']] for r in row['represented_native_clubs']
            if r['carrier_id'] in by_carrier
            and by_carrier[r['carrier_id']]['id']==r['club_id']
            and by_carrier[r['carrier_id']]['name']==r['club']]
        missing=[c for c in represented if c['id'] not in result]
        if not missing:
            continue
        try:
            if row['status']!='original-first-fixture-reparsed':
                raise ValueError(row.get('reason','original Soccerbase first-fixture source gap'))
            if row.get('source_capture',{}).get('targeted_original_capture') is not None:
                capture=None  # Exact raw capture path/SHA is independently replayed above.
            else:
                matching=[c for c in captures if c['club_name']==row['club']
                    and all(c.get(k)==v for k,v in row['source_capture'].items())]
                if len(matching)!=1:
                    raise ValueError('Soccerbase raw historical capture selection is ambiguous')
                capture=matching[0]
            actual=reconstruct(row,season,capture,people if raw_identity_people is None else raw_identity_people)
            witness=confirm_club_mapping(actual,entities,events)
            rebuilt=evidence(actual,witness,people)
            for club in missing:
                result[club['id']]=copy.deepcopy(rebuilt)
        except (ValueError,OSError) as exc:
            unresolved.append({'club':row['club'],'carriers':[c['carrier_id'] for c in missing],
                               'reason':str(exc)})
    return result,unresolved


def bound_people(people, bindings):
    item=bindings.get('soccerbase_opening_sources')
    if item is None:return people,None
    if item.get('policy')!=POLICY or item.get('person_policy')!=PERSON_POLICY:
        raise ValueError('unsupported original Soccerbase person policy')
    bound=item['review'];path=registry.ROOT/bound['path']
    if registry.sha256_file(path)!=bound['sha256']:
        raise ValueError('immutable Soccerbase identity input changed')
    doc=json.loads(path.read_text())
    if (doc['policy']!=replay.POLICY or doc['snapshot_binding']!=bindings['snapshot']
            or doc['published_person_binding']!=bindings.get('published_person_supplement')):
        raise ValueError('Soccerbase original identity inputs differ from bound snapshot/public identities')
    return extend_original_people(people,doc)


def verified_date(source):
    return bool(source.get('match_page_date_independently_published') or
        (source.get('source_provider_policy')==POLICY
         and source.get('fixture_date_published_on_original_schedule') is True
         and source.get('soccerbase_original_fixture',{}).get('date')==source.get('date')))


def validate_binding(plan):
    bindings=plan.get('bindings',{});item=bindings.get('soccerbase_opening_sources')
    uses=any(e.get('source_provider_policy')==POLICY for r in plan.get('updates',[])
        for e in (r.get('owner_evidence',{}),r.get('replacement_opening_evidence',{})))
    uses = uses or any(r.get('replacement',{}).get('source_display_aliases') or
        r.get('replacement',{}).get('source_person',{}).get('source_provider')=='soccerbase' or
        r.get('duplicate_source_person',{}).get('source_provider')=='soccerbase' for r in plan.get('updates',[]))
    if item is None and not uses:
        return
    if (item is None or item.get('policy')!=POLICY or item.get('person_policy')!=PERSON_POLICY or
            not bindings.get('published_person_supplement') or not bindings.get('published_transfer_supplement')
            or not bindings.get('opening_person_supplement_policy')):
        raise ValueError('Soccerbase source policy requires explicit bound original person/history inputs')


def explicit_display_names(replacement):
    claim=replacement.get('source_display_aliases')
    if claim is None:return []
    person=replacement['source_person']
    if (claim.get('policy')!=POLICY or (claim.get('source_person_id'),claim.get('birth_date'))!=
            (person['source_player_id'],person['birth_date']) or
            not re.fullmatch(r'soccerbase:\d+',claim.get('source_provider_person_id','')) or
            (person.get('source_provider')=='soccerbase' and claim.get('source_provider_person_id')!=person['source_player_id'])):
        raise ValueError('original Soccerbase match display alias identifies another provider person or DOB')
    names=claim.get('names')
    if (not isinstance(names,list) or len(names)!=1 or names[0].get('field')!='dated-match-label'
            or not isinstance(names[0].get('name'),str) or not names[0]['name'].strip()):
        raise ValueError('original Soccerbase display alias lacks one published match label')
    return names
