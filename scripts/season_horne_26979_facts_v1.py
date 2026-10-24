"""Isolated source-replay candidate for Barry Horne facts on 2000 club 374.

The public API is shaped for the existing publisher profile-assignment SOURCE
seam. It writes no files from prepare/bind/apply and uses only exact parent,
recipe, native, source-body, source-receipt and owner preconditions.
"""
from __future__ import annotations
import copy, hashlib, json
from datetime import date
from pathlib import Path
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline, season_package_v2 as packages
from scripts import season_package_compiler_v2 as compiler
from scripts import season_source_verified_player_changes_v1 as common
from scripts.season_historical_roster_audit_v1 import native_player, normalise
from scripts.season_opening_order_repair_v1 import native_owners
from scripts.season_within_club_reserve_repair_v1 import native_facts

MODE = 'source-backed-horne-26979-dob-wal-20261024-v1'
SCHEMA = 'pm99-source-bound-horne-26979-facts-v1'
KIND = 'source-bound-horne-26979-dob-wal-v1'
PREFIX = 'source-backed-horne-26979-'
RELEASE_ID = 'sourced-walsall-opening-ownership-20261023-r207a'
SEASON = '2000-01'
CARRIER_ID = 26979
CLUB_CARRIER_ID = 374
FULL_NAME = 'Barry Horne'
AFTER = {'birth_date': '1962-05-18', 'nationality': 'WAL'}
SCOPE = 'Only Barry Horne record 26979 birth_date and nationality; preserve broad/fine roles, all ratings, physical facts, shirt number, every owner/order field and all other bytes.'

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def filename(plan): return PREFIX + plan['transaction_id'] + '.json'
def artifact_id(plan): return PREFIX + plan['transaction_id']
def _rel(path): return registry.relative_workspace_path(Path(path))
def _read_bound(root, ref):
    if ref.get('url') not in ('https://www.11v11.com/players/barry-horne-400/','https://www.premierleague.com/en/players/1054/barry-horne/career'):
        raise ValueError('unexpected Horne source URL')
    p=(registry.ROOT/ref['path']).resolve(); rp=(registry.ROOT/ref['receipt_path']).resolve()
    if (not p.is_relative_to(registry.ROOT.resolve()) or not rp.is_relative_to(registry.ROOT.resolve())
        or (registry.ROOT/ref['path']).is_symlink() or (registry.ROOT/ref['receipt_path']).is_symlink()
        or digest(p.read_bytes())!=ref['sha256'] or digest(rp.read_bytes())!=ref['receipt_sha256']):
        raise ValueError('source or receipt bytes differ from bound original')
    r=pipeline.read_json_file(rp)
    if r.get('url')!=ref['url'] or r.get('body_sha256')!=ref['sha256']:
        raise ValueError('original source URL/body receipt differs')
    return p.read_bytes()

def _source_facts(request):
    refs=request['source_bindings']
    eleven=_read_bound(registry.ROOT,refs['eleven_v_eleven'])
    page=BeautifulSoup(eleven,'lxml'); text=' '.join(page.get_text(' ',strip=True).split())
    if refs['eleven_v_eleven']['url']!='https://www.11v11.com/players/barry-horne-400/' or not all(s in text for s in ('Barry Horne','Date of birth 18 May 1962','Nationality Welsh','Position Midfielder','Kidderminster Harriers','12 Jul 2000','07 Mar 2001')):
        raise ValueError('11v11 identity, exact facts, or Kidderminster dates differ')
    pl=_read_bound(registry.ROOT,refs['premier_league'])
    plpage=BeautifulSoup(pl,'lxml')
    canonical=plpage.select_one('link[rel~=canonical]')
    title=' '.join((plpage.title.get_text(' ',strip=True) if plpage.title else '').split())
    # This official profile is server-rendered without its dynamic DOB/nationality
    # payload. Those claims are recorded from the reviewed browser page, while the
    # canonical raw page binds profile identity/title independently.
    if (refs['premier_league']['url']!='https://www.premierleague.com/en/players/1054/barry-horne/career'
        or canonical is None or canonical.get('href')!=refs['premier_league']['url'] or 'Barry Horne' not in title or 'Midfielder' not in title):
        raise ValueError('official Premier League canonical identity/profile title differs')
    if request.get('reviewed_official_profile_claims') != {'name':FULL_NAME,'birth_date':'18/05/1962','nationality':'Wales','position':'Midfielder'}:
        raise ValueError('reviewed official Premier League claim record differs')
    return {'birth_date':'1962-05-18','nationality':'WAL','primary_position':'M','source_identity':'Barry Horne / 11v11 profile 400 / official Premier League profile 1054'}

def _parent_guard(base, request):
    if (base.season!=SEASON or base.release_id!=RELEASE_ID
        or base.manifest_sha256!=request['parent']['manifest_sha256']
        or registry.sha256_file(base.package_path)!=request['parent']['package_sha256']):
        raise ValueError('exact r207a current parent binding required')
    if registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI')!=request['parent']['jug_sha256'] or registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI')!=request['parent']['eq_sha256']:
        raise ValueError('exact r207a JUG/EQ preimage required')

def prepare(base, input_path):
    p=Path(input_path)
    if not p.is_absolute(): p=registry.ROOT/p
    p=p.resolve()
    if not p.is_relative_to(registry.ROOT.resolve()) or p.is_symlink() or not p.is_file(): raise ValueError('input must be retained inside workspace')
    request=pipeline.read_json_file(p)
    if request.get('schema')!='pm99-horne-fact-delta-input-v1' or request.get('mode')!=MODE or request.get('season')!=SEASON or request.get('release_id')!=RELEASE_ID:
        raise ValueError('exact case-scoped Horne input required')
    _parent_guard(base,request); source=_source_facts(request)
    package=pipeline.read_json_file(base.package_path); jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    actors={x['carrier_id']:x for x in package['players']}; actor=actors[CARRIER_ID]
    if actor!=request['before'] or actor.get('id')!='english-player-26979' or actor.get('person_id')!='player-person-374-6' or actor.get('name')!=FULL_NAME or actor.get('source_name')!=FULL_NAME or actor.get('club_id')!='english-club-374':
        raise ValueError('exact Horne 26979 recipe identity preimage required')
    if actor['facts'] != request['before_facts'] or actor['facts']['primary_position']!='M' or actor['facts']['fine_roles']!=[9]:
        raise ValueError('exact Horne fact/role preimage required')
    if digest(jug)!=request['parent']['jug_sha256'] or digest(eq)!=request['parent']['eq_sha256'] or native_owners(eq).get(CARRIER_ID)!={CLUB_CARRIER_ID}:
        raise ValueError('exact native data and exclusive club374 ownership required')
    idx=IndexedFDIFile.from_bytes(jug); entry=next(e for e in idx.entries if e.record_id==CARRIER_ID); raw=entry.decode_payload(jug); identity=native_player(raw,CARRIER_ID); observed=native_facts(jug,CARRIER_ID); end=identity['name_end']
    if normalise(identity['name'])!=normalise(FULL_NAME) or observed['birth_date']!='1975-07-01' or actor['facts']['birth_date']!='1975-07-01' or raw[end+8]^0x61 != request['native_before']['country_code']:
        raise ValueError('exact native Horne identity/DOB/country preimage required')
    if request['native_before']!={'birth_date':'1975-07-01','country_label':'ENGLAND','country_code':compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')['ENGLAND']}:
        raise ValueError('native source country preimage assertion differs')
    codes=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF'); after_country=compiler._country_code('WAL',codes)
    dob=date.fromisoformat(AFTER['birth_date']); dobbytes=bytes([dob.day,dob.month])+dob.year.to_bytes(2,'little')
    offsets=[end+8,*range(end+12,end+16)]; afterbytes=[after_country,*dobbytes]; masks=[]
    for off,val in zip(offsets,afterbytes):
        absolute=entry.payload_offset+off
        masks.append({'file':'DBDAT/JUG98030.FDI','record_offset':off,'file_offset':absolute,'before':jug[absolute],'after':val})
    post=bytearray(jug)
    for m in masks: post[m['file_offset']]=m['after']
    after_facts=native_facts(bytes(post),CARRIER_ID)
    if after_facts['birth_date']!=AFTER['birth_date'] or (entry.decode_payload(bytes(post))[end+8]^0x61)!=after_country:
        raise ValueError('independent native postimage parse failed')
    row={'carrier_id':CARRIER_ID,'before':copy.deepcopy(actor),'values':copy.deepcopy(AFTER),'field_mask':['birth_date','nationality'],'native_masks':masks,'witness':{'values':copy.deepcopy(AFTER),'sources':copy.deepcopy(request['source_bindings']),'reviewed_official_profile_claims':copy.deepcopy(request['reviewed_official_profile_claims'])},'expected_owner':CLUB_CARRIER_ID}
    plan={'schema':SCHEMA,'season':SEASON,'release_id':RELEASE_ID,'kind':KIND,'source_input':{'path':_rel(p),'sha256':digest(p.read_bytes())},'package_sha256':registry.sha256_file(base.package_path),'jug_sha256':digest(jug),'eq_sha256':digest(eq),'textos_sha256':registry.sha256_file(base.game_path/'DBDAT/TEXTOS.PKF'),'updates':[row],'scope':SCOPE,'source_policy':'case-bound-Horne-full-name-date-nationality-two-profile-replay-v1','parent_manifest_sha256':base.manifest_sha256,'source_facts':source}
    plan['transaction_id']=digest(packages.canonical_json_bytes(plan))[:24]
    # Exercise the shared schema/mask validator; historical TM fixture witness is
    # deliberately not fabricated. This case adapter owns its source replay guard.
    _validate_shared_mask(plan)
    return plan

def verify(base,plan):
    if plan.get('schema')!=SCHEMA or plan.get('kind')!=KIND:
        raise ValueError('Horne source-replay plan schema/mode mismatch')
    source=registry.ROOT/plan['source_input']['path']
    if source.is_symlink() or digest(source.read_bytes())!=plan['source_input']['sha256'] or prepare(base,source)!=plan:
        raise ValueError('Horne plan/source input no longer independently reproduces')

def validate_mask(plan):
    if plan.get('schema')!=SCHEMA or plan.get('kind')!=KIND:
        raise ValueError('Horne unique schema/mode required')
    _validate_shared_mask(plan)
    row=plan['updates'][0]
    if len(plan['updates'])!=1 or row['carrier_id']!=CARRIER_ID or row['field_mask']!=['birth_date','nationality'] or row['values']!=AFTER or row['expected_owner']!=CLUB_CARRIER_ID or len(row['native_masks'])!=5:
        raise ValueError('only exact Horne two-fact correction permitted')

def _validate_shared_mask(plan):
    bridge=copy.deepcopy(plan); bridge['schema']=common.SCHEMA; bridge['kind']=common.ADJUDICATED_KIND
    common.validate_mask(bridge)

def bind(package,plan):
    validate_mask(plan); base=registry.load_registered_release(plan['season'],plan['release_id']); verify(base,plan)
    if package!=pipeline.read_json_file(base.package_path) or registry.sha256_file(base.package_path)!=plan['package_sha256']:
        raise ValueError('exact r207a whole package preimage required')
    result=copy.deepcopy(package); actor=next(x for x in result['players'] if x['carrier_id']==CARRIER_ID)
    if actor!=plan['updates'][0]['before']: raise ValueError('Horne actor preimage differs')
    actor['facts'].update(AFTER); actor['fact_fallbacks']=[f for f in actor.get('fact_fallbacks',[]) if f.get('field') not in AFTER]
    result['artifacts'].append({'id':artifact_id(plan),'kind':'season-input','relative_path':filename(plan),'sha256':digest(packages.canonical_json_bytes(plan)),'media_type':'application/json'})
    result['artifacts'].sort(key=lambda a:a['id']); packages.validate_package(result); return result

def reject_factory_recipe(package):
    if any(a.get('id','').startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('Horne fact delta requires source-bound reconstruction')

def reconstruction(previous,release_id):
    # Check the compilation mode before consulting inherited locator paths.
    receipt_path=getattr(previous,'compiler_receipt_path',None)
    if receipt_path is None: return None
    receipt=pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode')!=MODE: return None
    relative=getattr(previous,'locator',{}).get('sourced_profile_assignment_plan_path')
    if not relative: raise ValueError('Horne SOURCE receipt lacks assignment plan locator')
    plan_path=(registry.ROOT/relative).resolve(); plan=pipeline.read_json_file(plan_path)
    if plan.get('schema')!=SCHEMA or plan.get('kind')!=KIND:
        raise ValueError('Horne SOURCE receipt points to another plan')
    base=registry.load_registered_release(previous.season,plan['release_id']); verify(base,plan)
    if (plan_path!=(previous.package_path.parent/filename(plan)).resolve()
        or registry.sha256_file(plan_path)!=receipt.get('original_profile_assignment_plan_sha256')):
        raise ValueError('Horne SOURCE receipt plan path/SHA differs')
    package=pipeline.read_json_file(previous.package_path)
    if bind(pipeline.read_json_file(base.package_path),plan)!=package:
        raise ValueError('Horne SOURCE would discard recipe changes')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    expected={'season':base.season,'release_id':base.release_id,'package_sha256':plan['package_sha256'],
        'jug_sha256':plan['jug_sha256'],'updates':[],'unresolved':[]}
    if pipeline.read_json_file(descriptor)!=expected:
        raise ValueError('Horne SOURCE inert role descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,
        source_release_id=base.release_id,profile_assignment_plan_path=plan_path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():
        raise ValueError('Horne SOURCE complete package replay differs')
    return {'season':previous.season,'release_id':release_id,'complete_game_inventory_identical':True,
        'complete_recipe_identical':True,'compilation_mode':MODE}

def apply(jug,eq,plan):
    validate_mask(plan); base=registry.load_registered_release(plan['season'],plan['release_id']); verify(base,plan)
    source_jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); source_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if digest(source_jug)!=plan['jug_sha256'] or digest(source_eq)!=plan['eq_sha256'] or digest(eq)!=plan['eq_sha256']:
        raise ValueError('exact r207a whole JUG/EQ binding required')
    candidate=bytearray(source_jug)
    masks=plan['updates'][0]['native_masks']
    for m in masks:
        if source_jug[m['file_offset']]!=m['before']: raise ValueError('exact native field preimage differs')
        candidate[m['file_offset']]=m['after']
    expected=bytes(candidate); allowed={m['file_offset'] for m in masks if m['before']!=m['after']}; changed={i for i,(a,b) in enumerate(zip(source_jug,expected)) if a!=b}
    if len(expected)!=len(source_jug) or changed!=allowed: raise ValueError('Horne patch changed bytes outside exact five-field mask')
    if jug not in (source_jug,expected): raise ValueError('accept exact complete source preimage or complete postimage only')
    return expected,source_eq
