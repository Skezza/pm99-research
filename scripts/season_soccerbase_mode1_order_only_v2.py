"""Typed Soccerbase Hayes XI order-only adapter for existing opening APIs.

Canonical-ready proposal. The adapter validates its own exact request and
source bindings, builds an exchange-shaped plan, then delegates package and
native transforms to season_opening_identity_exchange_v1.bind/apply and
season_complete_mode1_opening_v1.apply. It defines no native writer.
"""
from __future__ import annotations
import copy
import hashlib
from pathlib import Path
from app.fdi_indexed import IndexedFDIFile
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.player_initial_order import read_initial_order
from scripts import capture_soccerbase_august_squads_v1 as profile_parser
from scripts import season_complete_mode1_opening_v1 as complete
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_soccerbase_original_opening_v1 as soccerbase
from scripts.season_historical_roster_audit_v1 import normalise
from scripts.season_within_club_reserve_repair_v1 import native_facts as _decode_native_facts

ROOT=registry.ROOT
KIND='typed-soccerbase-mode1-opening-xi-order-only-v2'
SEASON='2000-01'
TEAM_ID=1197
CLUB_CARRIER=3307
FIXTURE_ID=286457
EXPECTED_XI_IDS=[10932,21295,18004,11244,22262,14701,18072,8909,17879,11256,18995]
TEAM_SOURCE={'path':'.local/season-2000-01/soccerbase-august-cache-v1/team/1197.html','sha256':'40f702235d7687b6bc9fbd3c072e2262923aa9ccf8f397ab7b8ba531bac9e74f','receipt_path':'.local/season-2000-01/soccerbase-august-cache-v1/team/1197.html.source.json','receipt_sha256':'430dfade84c0b0e76a9dd3439dafd4369aafa76d3b6056d97262fcc2a220be1d','url':'https://www.soccerbase.com/teams/team.sd?season_id=130&team_id=1197&teamTabs=results'}
MATCH_SOURCE={'path':'.local/season-2000-01/soccerbase-august-cache-v1/match/286457.html','sha256':'f3159a2eede245b651b300d0a7fb655cd6885e48960d4603d6e3bb011507cb3b','receipt_path':'.local/season-2000-01/soccerbase-august-cache-v1/match/286457.html.source.json','receipt_sha256':'2d19d0076788083ec083e05eece03c3e3e94e6e4754944667219a0ce137bfee6','url':'https://www.soccerbase.com/matches/additional_information.sd?id_game=286457'}
TARGET={'native_club_carrier_id':3307,'recipe_club_id':'club-3307','expected_club_label':'Hayes','mode_byte':1,'roster_capacity':18,'expected_native_roster_flags':0}
FIXTURE={'competition':'Football Conference','date':'2000-08-19','fixture_id':286457,'home_name':'Telford','away_name':'Hayes','score':[2,0],'source_team_id':1197,'source_season_id':130}
SOURCE_ORDER_POLICY='Exact dated original Soccerbase opening-XI order through numeric profile IDs and exact full names; do not read source-profile DOB as a replacement value; preserve recipe/native DOB preimages.'
RESERVE_POLICY='Preserve relative native order of non-XI owned actors; do not claim published bench order.'
SCOPE='Startup-order bytes for all 18 current exclusively owned compact native rows and recipe roster order only; all player identities/facts, skills, roles, EQ links/flags, managers, tactics, kit and assets unchanged.'
EXCLUDED=['identity','name','birth_date','position','nationality','skills','ownership','EQ links','EQ flags','manager','tactics','kit','artwork','bench-order claim']
_EMPTY={'moves':[],'new_people':[],'orders':[],'retirements':[]}
_COMPLETE_INPUT={'policy':complete.ORDER_ONLY_POLICY,'club_carrier_id':3307,'match_evidence_key':'soccerbase_match_sheet','opening_xi_source_order_count':11,'order_all_roster_members':True,'reserve_tail':'stable-old-relative-order'}
_NATIVE_CACHE={}

def _native(jug,carrier):
    key=(hashlib.sha256(jug).hexdigest(),carrier)
    row=_NATIVE_CACHE.get(key)
    if row is None:
        row=_decode_native_facts(jug,carrier)
        if len(_NATIVE_CACHE)>=40: _NATIVE_CACHE.clear()
        _NATIVE_CACHE[key]=row
    return row

def _file_binding(path,body_sha,receipt_path,receipt_sha,url):
    return {'path':path,'sha256':body_sha,'receipt_path':receipt_path,'receipt_sha256':receipt_sha,'url':url}

def _read_source(binding):
    body=ROOT/binding['path']; receipt_path=ROOT/binding['receipt_path']
    if registry.sha256_file(body)!=binding['sha256'] or registry.sha256_file(receipt_path)!=binding['receipt_sha256']:
        raise ValueError('bound SoccerBase original or receipt hash changed')
    receipt=pipeline.read_json_file(receipt_path)
    if receipt != {'url':binding['url'],'sha256':binding['sha256']}:
        raise ValueError('bound SoccerBase URL/body receipt differs')
    return body.read_bytes()

def _exact_request(request):
    expected_keys={'schema','proposal_kind','season','release_id','expected_package_sha256','expected_jug_sha256','expected_eq_sha256','target','fixture','source_order_policy','reserve_tail_policy','scope','excluded','source_bindings','empty_transactions','complete_mode1_opening'}
    if set(request)!=expected_keys or request.get('schema')!=exchange.INPUT_SCHEMA or request.get('proposal_kind')!=KIND:
        raise ValueError('typed Hayes order request has unknown/missing fields or wrong schema')
    if request.get('season')!=SEASON or request.get('target')!=TARGET or request.get('fixture')!=FIXTURE:
        raise ValueError('typed Hayes target/fixture metadata must match reviewed descriptive contract')
    if (request.get('source_order_policy')!=SOURCE_ORDER_POLICY or request.get('reserve_tail_policy')!=RESERVE_POLICY
        or request.get('scope')!=SCOPE or request.get('excluded')!=EXCLUDED
        or request.get('empty_transactions')!=_EMPTY or request.get('complete_mode1_opening')!=_COMPLETE_INPUT):
        raise ValueError('typed Hayes policy/scope/empty transaction contract differs')
    bindings=request.get('source_bindings')
    if not isinstance(bindings,dict) or set(bindings)!={'soccerbase_team_results','soccerbase_match_sheet','soccerbase_profiles'}:
        raise ValueError('typed Hayes request requires exact schedule, match, and all player profile bindings')
    if bindings['soccerbase_team_results']!=TEAM_SOURCE or bindings['soccerbase_match_sheet']!=MATCH_SOURCE:
        raise ValueError('typed Hayes schedule/match source binding differs')
    profiles=bindings['soccerbase_profiles']
    if not isinstance(profiles,list) or len(profiles)!=11 or [p.get('provider_player_id') for p in profiles]!=EXPECTED_XI_IDS:
        raise ValueError('typed Hayes request requires all 11 numeric original profile bindings in XI order')

def _source_and_xi(request):
    bind=request['source_bindings']
    schedule=_read_source(bind['soccerbase_team_results'])
    fixture=soccerbase.first_fixture(schedule,TEAM_ID,SEASON,FIXTURE['competition'],FIXTURE['away_name'],TEAM_SOURCE['url'])
    if fixture!={'date':FIXTURE['date'],'game_id':FIXTURE_ID,'sides':[{'team_id':2546,'name':'Telford'},{'team_id':TEAM_ID,'name':'Hayes'}],'score':[2,0]}:
        raise ValueError('original Soccerbase schedule does not reproduce exact Hayes opener')
    match=soccerbase.match(_read_source(bind['soccerbase_match_sheet']),fixture,TEAM_ID,MATCH_SOURCE['url'],allow_declared_unknown_details=True)
    xi=match['starting_xi']; ids=[r['provider_player_id'] for r in xi]
    if len(xi)!=11 or ids!=EXPECTED_XI_IDS:
        raise ValueError('dated original Soccerbase match sheet differs from full expected XI order')
    profiles=[]
    for match_row,source in zip(xi,bind['soccerbase_profiles']):
        pid=source['provider_player_id']
        expected_path=f'.local/season-2000-01/soccerbase-august-cache-v1/player/{pid}.html'
        expected_url=f'https://www.soccerbase.com/players/player.sd?player_id={pid}'
        if source.get('path')!=expected_path or source.get('url')!=expected_url:
            raise ValueError('numeric SoccerBase profile path/URL is not exact provider ID')
        raw=_read_source(source)
        profile=profile_parser.player_profile(raw,fallback_name='',fallback_position='?')
        if profile.get('name')!=source.get('full_name') or profile.get('position')!=source.get('position'):
            raise ValueError('numeric profile full name/position differs from retained request')
        if profile.get('position')!=match_row.get('position'):
            raise ValueError('numeric profile and dated XI broad positions differ')
        # The provider DOB is deliberately not consumed: it may be disputed and
        # never replaces the exact current recipe/native DOB preimage.
        profiles.append({'provider_player_id':pid,'path':source['path'],'sha256':source['sha256'],
          'receipt_path':source['receipt_path'],'receipt_sha256':source['receipt_sha256'],'url':source['url'],
          'full_name':profile['name'],'source_position':profile['position']})
    return fixture,xi,profiles

def prepare(base,input_path,request_doc=None):
    path=Path(input_path)
    if not path.is_absolute(): path=ROOT/path
    path=path.resolve()
    if not path.is_file() or not path.is_relative_to(ROOT.resolve()): raise ValueError('order request must be a retained workspace file')
    request=pipeline.read_json_file(path) if request_doc is None else request_doc
    if request!=pipeline.read_json_file(path): raise ValueError('supplied request differs from retained request file')
    _exact_request(request)
    if (base.season!=SEASON or base.release_id!=request.get('release_id')
        or registry.sha256_file(base.package_path)!=request.get('expected_package_sha256')):
        raise ValueError('exact explicit parent season/release/package pin differs')
    jug_path=base.game_path/'DBDAT/JUG98030.FDI'; eq_path=base.game_path/'DBDAT/EQ98030.FDI'
    jug=jug_path.read_bytes(); eq=eq_path.read_bytes()
    if registry.sha256_file(jug_path)!=request.get('expected_jug_sha256') or registry.sha256_file(eq_path)!=request.get('expected_eq_sha256'):
        raise ValueError('exact explicit native JUG/EQ parent pins differ')
    fixture,source_xi,profile_bindings=_source_and_xi(request)
    package=pipeline.read_json_file(base.package_path)
    clubs=[c for c in package['clubs'] if c.get('carrier_id')==CLUB_CARRIER]
    if len(clubs)!=1: raise ValueError('native club carrier 3307 must map to one recipe club')
    club=clubs[0]
    if club.get('id')!=request['target']['recipe_club_id'] or club.get('name')!=request['target']['expected_club_label']:
        raise ValueError('native club/recipe ID and source-verified club label must match request')
    actors=[p for p in package['players'] if p.get('club_id')==club['id']]
    if len(actors)!=18 or {p['id'] for p in actors}!=set(club['roster_player_ids']):
        raise ValueError('Hayes recipe roster must contain exactly 18 unique actors')
    by_full_name={}
    for actor in actors: by_full_name.setdefault(actor.get('source_name') or actor['name'],[]).append(actor)
    source_to_carrier={}; profile_rows=[]
    for match_row,source_profile in zip(source_xi,profile_bindings):
        names=by_full_name.get(source_profile['full_name'],[])
        if len(names)!=1: raise ValueError('full source profile name must identify one exact recipe actor')
        actor=names[0]; facts=_native(jug,actor['carrier_id'])
        if (normalise(facts['name'])!=normalise(actor['name'])
            or facts['position']!=actor['facts'].get('primary_position')
            or facts['position']!=match_row['position']
                or not complete.retained_field_matches(actor['facts'].get('birth_date'),facts['birth_date'])):
            raise ValueError('current recipe/native exact name, position, and DOB preimage differs')
        source_to_carrier[match_row['provider_player_id']]=actor['carrier_id']
        profile_rows.append(dict(**source_profile,carrier_id=actor['carrier_id']))
    if len(source_to_carrier)!=11 or len(set(source_to_carrier.values()))!=11:
        raise ValueError('11 distinct numeric source profiles must map to 11 distinct recipe/native actors')
    eq_index=IndexedFDIFile.from_bytes(eq); eq_entries={e.record_id:e for e in eq_index.entries}
    club_entry=eq_entries.get(CLUB_CARRIER)
    if club_entry is None: raise ValueError('native club 3307 record is absent')
    roster=parse_eq_external_team_roster_payload(eq[club_entry.payload_offset:club_entry.payload_offset+club_entry.payload_length],{})
    if (roster is None or roster.mode_byte!=TARGET['mode_byte'] or len(roster.rows)!=TARGET['roster_capacity']
        or any(row.flag!=TARGET['expected_native_roster_flags'] for row in roster.rows)
        or {row.player_record_id for row in roster.rows}!={p['carrier_id'] for p in actors}):
        raise ValueError('native club must be exact visible mode1 18-person zero-flag roster')
    owner_sets=ownership.native_owners(eq)
    if any(owner_sets.get(p['carrier_id'])!={CLUB_CARRIER} for p in actors):
        raise ValueError('all 18 native actors must be exclusively owned by 3307')
    jug_index=IndexedFDIFile.from_bytes(jug); jug_entries={e.record_id:e for e in jug_index.entries}
    native_by_carrier={}
    orders_by_carrier={}
    for actor in actors:
        cid=actor['carrier_id']; entry=jug_entries.get(cid)
        if entry is None: raise ValueError('one of 18 recipe actors lacks a native JUG carrier')
        nf=_native(jug,cid); payload=entry.decode_payload(jug); field=read_initial_order(payload)
        if field.family!='dd6360' or normalise(field.name)!=normalise(actor['name']):
            raise ValueError('all 18 exact actor preimages must be compact and full-name matched')
        if (not complete.retained_field_matches(actor['facts'].get('birth_date'),nf['birth_date'])
            or not complete.retained_field_matches(actor['facts'].get('primary_position'),nf['position'])):
            raise ValueError('all current native recipe DOB/position preimages must agree')
        native_by_carrier[cid]=nf; orders_by_carrier[cid]=field
    starters=[source_to_carrier[row['provider_player_id']] for row in source_xi]
    tail=sorted((p['carrier_id'] for p in actors if p['carrier_id'] not in set(starters)),
        key=lambda cid:(native_by_carrier[cid]['startup_order'],cid))
    full_order=starters+tail
    if len(full_order)!=18 or len(set(full_order))!=18: raise ValueError('XI plus reserve tail is not exact 18-person permutation')
    order_rows=[{'carrier_id':cid,'native_name':orders_by_carrier[cid].name,'before':orders_by_carrier[cid].order,'after':n}
        for n,cid in enumerate(full_order,1)]
    complete_plan={'policy':complete.ORDER_ONLY_POLICY,'club_carrier_id':CLUB_CARRIER,'club_id':club['id'],'orders':order_rows,
        'starting_xi':starters,'fixture_date':fixture['date'],'published_bench_ids':[],
        'reserve_policy':'preserve-relative-native-order-not-published-bench-order','opaque_tactics_unchanged':True,
        'source_match_id':fixture['game_id'],'source_player_bindings':profile_rows}
    proposed_jug=complete.apply(jug,eq,complete_plan)
    offsets=[i for i,(a,b) in enumerate(zip(jug,proposed_jug)) if a!=b]
    order_masks=[]
    for row in order_rows:
        cid=row['carrier_id']; entry=jug_entries[cid]; field=orders_by_carrier[cid]
        offset=entry.payload_offset+field.offset
        order_masks.append({'carrier_id':cid,'native_name':field.name,'record_offset':field.offset,'file_offset':offset,
            'before':row['before'],'after':row['after'],'changed':row['before']!=row['after']})
    expected_offsets=sorted(m['file_offset'] for m in order_masks if m['changed'])
    if offsets!=expected_offsets or len(offsets)!=14:
        raise ValueError(f'native postimage must change exactly the 14 bound order masks; changed={offsets}; masks={expected_offsets}')
    req_for_exchange=copy.deepcopy(request)
    req_for_exchange.update(copy.deepcopy(_EMPTY))
    plan={'schema':exchange.SCHEMA,'season':base.season,'release_id':base.release_id,
      'source_input':exchange.binding(path),'package_sha256':request['expected_package_sha256'],
      'jug_sha256':request['expected_jug_sha256'],'eq_sha256':request['expected_eq_sha256'],
      'request':req_for_exchange,'updates':[],'decisions':[],'bindings':{'snapshot':{'project_url':'https://www.soccerbase.com/'}},
      'source_title':'SoccerBase dated Hayes opening starting XI order only',
      'proof_covers':['original-first-league-XI-order-only','all-player-facts-and-EQ-assets-preserved'],
      'scope':SCOPE,'complete_mode1_opening':complete_plan,'native_order_masks':sorted(order_masks,key=lambda m:m['file_offset']),
      'source_verification':{'fixture':fixture,'source_ids':[r['provider_player_id'] for r in source_xi],
       'source_full_names':[r['full_name'] for r in profile_rows],'recipe_carriers':starters+tail,
       'native_roster_mode':roster.mode_byte,'native_roster_count':len(roster.rows),
       'native_roster_flags':[r.flag for r in roster.rows],
       'native_owner_sets':{str(p['carrier_id']):sorted(owner_sets[p['carrier_id']]) for p in actors},
       'native_changed_offsets':offsets,'stable_reserve_tail':tail,
       'scope_note':'Player profile DOB fields were not consumed; current recipe/native DOBs are exact immutable preimages.'}}
    plan['transaction_id']=exchange.digest(packages.canonical_json_bytes(plan))[:24]
    # Exercise the established recipe binder as a preflight before returning plan.
    exchange.bind(package,plan)
    return plan

def verify(base,plan):
    if plan.get('schema')!=exchange.SCHEMA or prepare(base,plan['source_input']['path'])!=plan:
        raise ValueError('typed SoccerBase order-only plan does not independently reproduce')

def bind(package,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    verify(base,plan)
    return exchange.bind(package,plan)

def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    verify(base,plan)
    return exchange.apply(jug,eq,plan)

def filename(plan): return exchange.filename(plan)
def artifact_id(plan): return exchange.PREFIX+plan['transaction_id']
def reject_factory_recipe(package): return exchange.reject_factory_recipe(package)
def reconstruction(previous,release_id): return exchange.reconstruction(previous,release_id)
