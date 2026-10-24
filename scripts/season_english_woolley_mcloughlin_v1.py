"""Isolated source-bound two-carrier replacement proposal for 2000-01.
Uses existing duplicate-delta recipe/native APIs; no publication dispatch is installed.
"""
from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_package_v2 as package_v2
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline

MODE='known-good-baseline-source-bound-english-woolley-mcloughlin-v1'
SCHEMA='pm99-source-bound-english-opening-reserve-replacement-v1'
PREFIX='english-opening-reserve-replacement-'
SOURCE_DIR=Path('.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/four-crossclub-replacement-web-v2')
PARENT_PREFIX='sourced-evers-mcclune-opening-20261024-r217'
CASES=(
    {'case_id':'b8fc12b1cf0d099454e4d4f6f01aa4e38619ad8a01a35230975056d0a621d086','carrier':32952,'club_carrier':382,'club_id':'english-club-382','club':'Macclesfield Town','old_name':'Stuart Whittaker','old_dob':'1975-01-02','keep_carrier':11069,'keep_club_id':'club-3316','keep_name':'Whittaker','keep_source_name':'Stuart Whittaker','keep_dob':'1975-01-02','name':'Matt Woolley','source_name':'Matt Woolley','dob':'1982-02-22','position':'M','nationality':'ENG','height_cm':178,'weight_kg':71,'shirt_number':None,'source_person_id':'11v11:8864','provider':'11v11','profile_file':'matt_woolley_11v11_profile.html','profile_url':'https://www.11v11.com/players/matt-woolley-8864/','positive_file':'matt_woolley_11v11_profile.html','positive_url':'https://www.11v11.com/players/matt-woolley-8864/','positive_claim':'Dated club-history membership 19 Jul 1999–31 Mar 2003 and profile text states youth/reserve team membership. Reserve/youth identity only; not August first-team appearance.'},
    {'case_id':'c7ac9751404ffef105eee3b8be15a710666224f4d412b9cb0734ec5a5804a187','carrier':33162,'club_carrier':386,'club_id':'english-club-386','club':'Wigan Athletic','old_name':'Ged Brannan','old_dob':'1972-01-15','keep_carrier':12147,'keep_club_id':'club-1253','keep_name':'Ged Brannan','keep_source_name':'Ged Brannan','keep_dob':'1972-01-15','name':'Alan McLoughlin','source_name':'Alan Francis McLoughlin','dob':'1967-04-20','position':'M','nationality':'IRL','height_cm':173,'weight_kg':None,'shirt_number':None,'source_person_id':'wigan-athletic-heritage:281','provider':'Wigan Athletic Heritage','profile_file':'wigan_alan_mcloughlin_profile.html','profile_url':'https://www.wiganathleticheritage.co.uk/player-profile/281/alan-mcloughlin','positive_file':'wigan_carlisle_2000_friendly.html','positive_url':'https://www.wiganathleticheritage.co.uk/match-report/3523/2000-2001-carlisle-united-1-wigan-athletic-3','positive_claim':'Official 5 Aug 2000 pre-season friendly report lists Alan McLoughlin as used substitute for Neil Redfearn at 76 minutes.'},
)

def sha(b): return hashlib.sha256(b).hexdigest()
def path_sha(p): return sha(Path(p).read_bytes())
def filename(plan):
    if plan.get('schema_version')!=SCHEMA or plan.get('mode')!=MODE: raise ValueError('wrong source plan schema/mode')
    return PREFIX+sha(package_v2.canonical_json_bytes(plan))[:12]+'.json'
def _text(path):
    page=BeautifulSoup(Path(path).read_bytes(),'lxml')
    return page, ' '.join(page.get_text(' ',strip=True).split())
def verify_sources(root=registry.ROOT):
    out=[]
    for c in CASES:
        prof=root/SOURCE_DIR/c['profile_file']; pp,pt=_text(prof)
        pos=root/SOURCE_DIR/c['positive_file']; op,ot=_text(pos)
        if path_sha(prof)=='' or path_sha(pos)=='': raise ValueError('source body missing')
        if c['carrier']==32952:
            title=pp.title.get_text(' ',strip=True) if pp.title else ''
            if title!='Matt Woolley Date of birth 22 February 1982' and not (title.startswith('Matt Woolley')): raise ValueError('Woolley original profile title mismatch')
            if not all(x in pt for x in ('22 February 1982','Nationality English','Position Midfielder','youth and reserve teams','Macclesfield Town 19 Jul 1999 31 Mar 2003')): raise ValueError('Woolley source identity/period/reserve evidence changed')
        else:
            title=pp.title.get_text(' ',strip=True) if pp.title else ''
            if not all(x in pt for x in ('Alan Francis McLoughlin','Born: 20/04/1967','Nationality: Ireland','Position: Midfield','Signed: 09/12/1999','Left: 25/10/2001')): raise ValueError('Wigan profile identity/tenure changed')
            title2=op.title.get_text(' ',strip=True) if op.title else ''
            if '5th August 2000' not in title2 or not all(x in ot for x in ('Alan McLoughlin','76 minutes')): raise ValueError('Wigan dated friendly membership changed')
        out.append({'case_id':c['case_id'],'profile':{'path':str(prof.relative_to(root)),'url':c['profile_url'],'sha256':path_sha(prof)},'positive':{'path':str(pos.relative_to(root)),'url':c['positive_url'],'sha256':path_sha(pos)},'claim':c['positive_claim']})
    return out

def _owner_review(root=registry.ROOT):
    path=root/'.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/dated-chronology-review-v1.json'
    doc=json.loads(path.read_text()); rows={r['case_id']:r for r in doc.get('findings',[]) if r.get('case_id') in {c['case_id'] for c in CASES}}
    if set(rows)!={c['case_id'] for c in CASES}: raise ValueError('approved wrong-owner chronology review rows missing')
    by=[]
    for c in CASES:
        row=rows[c['case_id']]
        if row.get('season')!='2000-01' or not row.get('career_disposition'): raise ValueError('wrong-owner chronology review is not exact season/case')
        players=row['assigned_rows']['case']['players']
        if {p['carrier_id'] for p in players}!={c['carrier'],c['keep_carrier']}: raise ValueError('wrong-owner review does not bind both exact frozen carriers')
        by.append({'case_id':c['case_id'],'career_disposition':row['career_disposition'],'assigned_rows':copy.deepcopy(row['assigned_rows']['case']['players'])})
    return {'path':str(path.relative_to(root)),'sha256':path_sha(path),'cases':by}

def _read_parent(base):
    if base.season!='2000-01' or not base.release_id.startswith(PARENT_PREFIX): raise ValueError('requires exact current 2000-01 parent family')
    reg=registry.load_registered_release(base.season,base.release_id)
    if (reg.package_path!=base.package_path or reg.game_path!=base.game_path or reg.manifest_sha256!=base.manifest_sha256): raise ValueError('release object differs from registry')
    package=json.loads(base.package_path.read_text()); game=base.game_path
    return package,game

def _native_preimage(base):
    game=base.game_path; jug=(game/'DBDAT/JUG98030.FDI').read_bytes(); eq=(game/'DBDAT/EQ98030.FDI').read_bytes()
    idx=IndexedFDIFile.from_bytes(jug); es={e.record_id:e for e in idx.entries}; out=[]
    for c in CASES:
        payload=es[c['carrier']].decode_payload(jug); fact=roster.native_player(payload,c['carrier']); end=fact['name_end']
        dob={'day':payload[end+12]^0x61,'month':payload[end+13]^0x61,'year':int.from_bytes(bytes(x^0x61 for x in payload[end+14:end+16]),'little')}
        if fact['name'].casefold()!=c['old_name'].casefold() or dob!=dict(year=int(c['old_dob'][:4]),month=int(c['old_dob'][5:7]),day=int(c['old_dob'][8:10])): raise ValueError('native carrier no longer matches expected preimage')
        out.append({'carrier_id':c['carrier'],'name':fact['name'],'birth_date':c['old_dob'],'position':fact['position'],'roles':fact['roles'],'payload_sha256':sha(payload)})
    return {'native_files':{'JUG98030.FDI':sha(jug),'EQ98030.FDI':sha(eq),'MINIFOTO.PKF':path_sha(game/'DBDAT/MINIFOTO.PKF')},'target_native_preimage':out}

def _before(package,c):
    by={p['carrier_id']:p for p in package['players']}; clubs={x['id']:x for x in package['clubs']}
    old=by.get(c['carrier']); keep=by.get(c['keep_carrier']); club=clubs.get(c['club_id']); keepclub=clubs.get(c['keep_club_id'])
    if not old or not keep or not club or not keepclub: raise ValueError('expected target/counterpart disappeared')
    if (old['name']!=c['old_name'] or old.get('source_name')!=c['old_name'] or old['facts'].get('birth_date')!=c['old_dob'] or old['club_id']!=club['id'] or club['roster_player_ids'].count(old['id'])!=1): raise ValueError('wrong duplicate target differs')
    if (keep['name']!=c['keep_name'] or keep.get('source_name')!=c['keep_source_name'] or keep['facts'].get('birth_date')!=c['keep_dob'] or keep['club_id']!=keepclub['id'] or keepclub['roster_player_ids'].count(keep['id'])!=1): raise ValueError('correct counterpart preservation target differs')
    if any((p.get('source_name') or p['name']).casefold()==c['source_name'].casefold() and p['facts'].get('birth_date')==c['dob'] for p in package['players']): raise ValueError('replacement candidate already represented')
    if len(club['roster_player_ids']) not in (25,): raise ValueError('target roster size differs')
    return old,keep,club,keepclub

def _make_plan(base):
    root=registry.ROOT; sources=verify_sources(root); owner_review=_owner_review(root); package,game=_read_parent(base); native=_native_preimage(base)
    updates=[]
    for c,s in zip(CASES,sources):
        old,keep,club,keepclub=_before(package,c)
        updates.append({'case_id':c['case_id'],'layer':'main','player_id':old['id'],'carrier_id':c['carrier'],'club_id':club['id'],'club':club['name'],'before':copy.deepcopy(old),
            'wrong_owner_evidence':{'case_id':c['case_id'],'basis':'approved frozen cross-club duplicate review; exact opening owner is wrong','review_path':owner_review['path'],'review_sha256':owner_review['sha256'],'career_disposition':next(x['career_disposition'] for x in owner_review['cases'] if x['case_id']==c['case_id']),'preserved_counterpart':{'carrier_id':keep['carrier_id'],'player_id':keep['id'],'club_id':keepclub['id']},'raw_sources':[{'path':owner_review['path'],'sha256':owner_review['sha256']}],},
            'replacement':{'source_player':{'name':c['name'],'birth_date':c['dob'],'position':c['position'],'nationality':c['nationality'],'height_cm':c['height_cm'],'weight_kg':c['weight_kg']},
                'source_person':{'source_provider':c['provider'],'source_player_id':c['source_person_id'],'name':c['source_name'],'birth_date':c['dob'],'source_profile_url':c['profile_url'],'identity_policy':'original-retained-club-profile-exact-full-name-DOB-v1'},
                'raw_evidence':{'local_path':s['profile']['path'],'source_sha256':s['profile']['sha256'],'url':s['profile']['url']},
                'opening_eligibility':{'method':'dated-preseason-or-registration-positive-membership','date':'2000-08-01','source_club_id':c['club_id'],'claim':c['positive_claim']},
                'portrait_policy':'no-photo; do not inherit displaced identity portrait'},
            'replacement_opening_evidence':{'date':'2000-08-01','source_club_id':c['club_id'],'method':'dated-reserve-registration-or-preseason-used-sub','claim':c['positive_claim'],'raw_sources':[s['positive']]},
            'preserve_roster_order':True})
    plan={'schema_version':SCHEMA,'mode':MODE,'season':'2000-01','release_id':base.release_id,
        'parent':{'release_id':base.release_id,'manifest_path':str(base.release_manifest_path.relative_to(root)),'manifest_sha256':base.manifest_sha256,'package_path':str(base.package_path.relative_to(root)),'package_sha256':path_sha(base.package_path),'native_files':native['native_files'],'target_native_preimage':native['target_native_preimage']},
        'package_sha256':path_sha(base.package_path),'jug_sha256':native['native_files']['JUG98030.FDI'],'source_title':'Dated 2000 opening ownership corrections using retained full-name/DOB profiles and positive preseason/reserve evidence',
        'bindings':{'snapshot':{'project_url':'https://www.wiganathleticheritage.co.uk/match-report/3523/2000-2001-carlisle-united-1-wigan-athletic-3'},'source_capture_dir':str(SOURCE_DIR),'source_rows':sources,'wrong_owner_review':owner_review},'source_verification':sources,'updates':updates,
        'proof_covers':['exact-current-native-carriers','exact-full-name-and-DOB-profile-binding','positive-preseason-or-dated-reserve-membership','preserve-correct-cross-club-counterparts','editorial-ratings','no-photo-displaced-image-removal'],
        'scope':{'package_changes_only':[32952,33162],'native_player_payloads_only':[32952,33162],'EQ_unchanged':True,'roster_membership_order_unchanged':True,'historical_first_XI_or_bench_claim':False},
        'historical_verification_complete':False,'registered':False,'build_authorized':False,'publication_authorized':False}
    return plan

def prepare(base):
    plan=_make_plan(base)
    verify(base,plan)
    return plan

def _delta_plan(plan):
    q=copy.deepcopy(plan)
    # Existing ownership delta helper emits the approved generic player/rating/photo fields.
    # It requires a numeric namespace; this transient internal identity is never retained.
    for r,c in zip(q['updates'],CASES): r['replacement']['source_person']['source_player_id']=int(c['source_person_id'].split(':')[-1]) if c['carrier']==32952 else 281
    return q

_POST_CACHE={}
_POST_CACHE_MAX=2
def _postimage(package,plan):
    if plan.get('schema_version')!=SCHEMA or plan.get('mode')!=MODE: raise ValueError('unsupported plan')
    key=(plan.get('parent',{}).get('package_sha256'),sha(package_v2.canonical_json_bytes(plan)))
    if key in _POST_CACHE: return copy.deepcopy(_POST_CACHE[key])
    q=_delta_plan(plan); result=delta.updated_package(package,q)
    d=sha(package_v2.canonical_json_bytes(plan)); aid='english-reserve-plan-2000-01-'+d[:12]; sid='english-reserve-source-2000-01-'+d[:12]
    for c,row in zip(CASES,plan['updates']):
        p=next(x for x in result['players'] if x['carrier_id']==c['carrier'])
        p['person_id']='person-'+hashlib.sha256((c['provider']+'|'+c['source_person_id']+'|'+c['dob']).encode()).hexdigest()[:24]
        p['source_name']=c['source_name']; p['name']=c['name']
        source_id='english-reserve-source-2000-01-'+d[:12]
        p['ratings']['provenance']['source_ids']=[source_id]
        proof={'artifact_id':aid,'grade':'source-receipt'}; p['proof']=proof
        for fallback in p.get('fact_fallbacks',[]): fallback['proof']=proof
        for portrait in result['assets']['portraits']:
            if portrait['player_id']==p['id']: portrait['proof']=proof
    # Replace helper-generated plan provenance with this exact typed artifact binding.
    oldids={a['id'] for a in package['artifacts']}; result['artifacts']=[a for a in result['artifacts'] if a['id'] in oldids]
    result['sources']=copy.deepcopy(package['sources'])
    result['proofs']=copy.deepcopy(package['proofs'])
    artifact={'id':aid,'kind':'season-input','sha256':d,'media_type':'application/json','relative_path':filename(plan)}
    result['artifacts'].append(artifact); result['artifacts'].sort(key=lambda x:x['id'])
    result['sources'].append({'id':sid,'title':plan['source_title'],'uri':'local://bound-english-crossclub-sources-v1','proof_grade':'source-receipt','evidence_artifact_id':aid}); result['sources'].sort(key=lambda x:x['id'])
    result['proofs'].append({'id':'proof-'+aid,'artifact_id':aid,'grade':'source-receipt','covers':plan['proof_covers']}); result['proofs'].sort(key=lambda x:x['id'])
    package_v2.validate_package(result,strict=False)
    # Exact scope and counterpart preservation.
    if result['clubs']!=package['clubs'] or result['managers']!=package['managers']: raise ValueError('club/manager declarations changed')
    for c in CASES:
        if next(p for p in result['players'] if p['carrier_id']==c['keep_carrier']) != next(p for p in package['players'] if p['carrier_id']==c['keep_carrier']): raise ValueError('correct counterpart changed')
    for key in ('calendar','migration'):
        if result[key]!=package[key]: raise ValueError('unrelated package metadata changed')
    for p in package['players']:
        if p['carrier_id'] not in {c['carrier'] for c in CASES} and next(q for q in result['players'] if q['id']==p['id'])!=p: raise ValueError('unrelated player changed')
    for c in CASES:
        club=next(x for x in result['clubs'] if x['id']==c['club_id'])
        oldclub=next(x for x in package['clubs'] if x['id']==c['club_id'])
        if club['roster_player_ids']!=oldclub['roster_player_ids'] or len(club['roster_player_ids'])!=25: raise ValueError('roster membership/order changed')
    return result

def verify(base,plan):
    if plan.get('schema_version')!=SCHEMA or plan.get('mode')!=MODE: raise ValueError('unsupported typed plan')
    if _make_plan(base)!=plan: raise ValueError('typed plan does not reproduce from exact source, parent, and preimage')
    return {'ok':True,'case_ids':[c['case_id'] for c in CASES],'changed_carriers':[c['carrier'] for c in CASES]}

def bind(package,plan):
    if not isinstance(package,dict): raise ValueError('package must be a dict')
    current=registry.load_registered_release(plan.get('season'),plan.get('release_id')); verify(current,plan)
    parent=json.loads(current.package_path.read_text())
    if package==parent: return _postimage(parent,plan)
    post=_postimage(parent,plan)
    if package!=post: raise ValueError('bind accepts exact full parent package or exact postimage')
    return copy.deepcopy(post)

_NATIVE_CACHE={}
def apply(jug,eq,plan):
    base=registry.load_registered_release(plan.get('season'),plan.get('release_id')); verify(base,plan)
    parent=base.game_path/'DBDAT/JUG98030.FDI'; eqp=base.game_path/'DBDAT/EQ98030.FDI'
    old=parent.read_bytes(); oldeq=eqp.read_bytes()
    if eq!=oldeq: raise ValueError('candidate apply accepts exact parent EQ bytes')
    nkey=(sha(old),sha(package_v2.canonical_json_bytes(plan)))
    if nkey in _NATIVE_CACHE and jug==_NATIVE_CACHE[nkey]: return jug,eq
    already_post=(jug!=old)
    package=json.loads(base.package_path.read_text()); post=bind(package,plan)
    ids={p['id'] for p in post['players'] if p['carrier_id'] in {c['carrier'] for c in CASES}}
    codes=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    result=delta.compile_planned_players(old,post,ids,codes,_delta_plan(plan))
    if already_post and jug!=result: raise ValueError('candidate apply accepts only exact parent or exact typed postimage JUG bytes')
    if already_post:
        _NATIVE_CACHE[nkey]=result
        return result,eq
    before={e.record_id:e for e in IndexedFDIFile.from_bytes(old).entries}; after={e.record_id:e for e in IndexedFDIFile.from_bytes(result).entries}
    if before.keys()!=after.keys(): raise ValueError('indexed directory changed')
    changed=[cid for cid,e in before.items() if e.decode_payload(old)!=after[cid].decode_payload(result)]
    if changed!=[32952,33162]: raise ValueError('native postimage touched unexpected carriers: '+repr(changed))
    if eq!=oldeq: raise ValueError('EQ changed')
    for c in CASES:
        payload=after[c['carrier']].decode_payload(result); actual=roster.native_player(payload,c['carrier'])
        end=actual['name_end']; payload_dob={'day':payload[end+12]^0x61,'month':payload[end+13]^0x61,'year':int.from_bytes(bytes(x^0x61 for x in payload[end+14:end+16]),'little')}
        expected_dob={'day':int(c['dob'][8:10]),'month':int(c['dob'][5:7]),'year':int(c['dob'][:4])}
        if actual['name'].casefold()!=c['name'].casefold() or actual['position']!=c['position'] or payload_dob!=expected_dob: raise ValueError('native identity/position/DOB readback mismatch')
    _NATIVE_CACHE[nkey]=result
    return result,eq

def source_artifact(plan):
    verify(registry.load_registered_release(plan['season'],plan['release_id']),plan)
    document=copy.deepcopy(plan); return {'filename':filename(plan),'document':document,'sha256':sha(package_v2.canonical_json_bytes(document))}
def selected_carriers(plan):
    if plan.get('schema_version')!=SCHEMA or plan.get('mode')!=MODE: raise ValueError('wrong plan')
    return {32952,33162}
def apply_minifoto(archive,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id']); verify(base,plan)
    original=(base.game_path/'DBDAT/MINIFOTO.PKF').read_bytes()
    if archive!=original: raise ValueError('portrait API accepts exact pinned parent')
    result,offsets=delta.no_photo_archive(original,selected_carriers(plan))
    if result!=original or any(offsets.values()): raise ValueError('unexpected target photo requires explicit review')
    for c in CASES:
        if (base.game_path/'DBDAT/MINIFOTO'/f'J96{c["carrier"]:05d}.BMP').exists(): raise ValueError('loose target portrait exists')
    return result

def reject_factory_recipe(package):
    if any(a.get('relative_path','').startswith(PREFIX) for a in package.get('artifacts',[])): raise ValueError('typed source reconstruction required')

def reconstruction(previous,release_id):
    rp=getattr(previous,'compiler_receipt_path',None)
    if rp is None:return None
    receipt=pipeline.read_json_file(rp)
    if receipt.get('compilation_mode')!=MODE:return None
    loc=previous.locator or {}; relative=loc.get('sourced_profile_assignment_plan_path')
    if not relative: raise ValueError('SOURCE missing typed plan locator')
    path=(registry.ROOT/relative).resolve()
    if not path.is_relative_to(registry.ROOT.resolve()) or path.is_symlink(): raise ValueError('SOURCE plan locator escaped workspace or is a symlink')
    plan=pipeline.read_json_file(path)
    expected_path=(previous.package_path.parent/filename(plan)).resolve()
    if path!=expected_path or registry.sha256_file(path)!=receipt.get('original_profile_assignment_plan_sha256'): raise ValueError('SOURCE artifact receipt mismatch')
    artifact=source_artifact(plan); ap=previous.package_path.parent/artifact['filename']
    if ap.is_symlink() or not ap.is_file() or registry.sha256_file(ap)!=artifact['sha256'] or ap.read_bytes()!=package_v2.canonical_json_bytes(plan): raise ValueError('SOURCE artifact bytes/hash mismatch')
    base=registry.load_registered_release(plan['season'],plan['parent']['release_id']); verify(base,plan)
    expected=bind(json.loads(base.package_path.read_text()),plan)
    previous_bytes=previous.package_path.read_bytes()
    if pipeline.read_json_file(previous.package_path)!=expected or previous_bytes!=package_v2.canonical_json_bytes(expected): raise ValueError('SOURCE package does not replay exactly')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    expected_descriptor={'season':plan['season'],'release_id':base.release_id,'package_sha256':plan['parent']['package_sha256'],'jug_sha256':plan['parent']['native_files']['JUG98030.FDI'],'updates':[],'unresolved':[]}
    if descriptor.is_symlink() or not descriptor.is_file() or pipeline.read_json_file(descriptor)!=expected_descriptor: raise ValueError('SOURCE inert role descriptor differs from exact parent')
    previous_inventory=pipeline.read_json_file(previous.inventory_path)
    pipeline.assert_tree_matches_inventory(previous.game_path,previous_inventory)
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,previous_inventory)
    rebuilt_bytes=rebuilt.package_path.read_bytes()
    if pipeline.read_json_file(rebuilt.package_path)!=expected or rebuilt_bytes!=previous_bytes: raise ValueError('complete SOURCE replay recipe differs')
    return {'season':previous.season,'release_id':release_id,'compilation_mode':MODE,'complete_game_inventory_identical':True,'complete_recipe_identical':True}
