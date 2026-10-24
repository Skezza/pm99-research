"""Private source-bound reserve identity adapter; existing player byte compiler only."""
from __future__ import annotations
import copy, datetime as dt, hashlib, json
from pathlib import Path
from bs4 import BeautifulSoup
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_rating_calibration_v3 as rating
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from app.fdi_indexed import IndexedFDIFile

SCHEMA='pm99-ballymena-shevlin-reserve-replacement-v1'
MODE='known-good-baseline-source-bound-ballymena-shevlin-reserve-replacement-v1'
SCOPE='Only replace source-wrong Ballymena reserve carrier19829 with sourced Matthew Shevlin and clear old-identity photo metadata; retain order12, all EQ, XI, tactics, managers, all other actors and game bytes. Unknown physical/shirt fields remain explicit native fallbacks.'
PREFIX='ballymena-shevlin-reserve-'
PARENT='sourced-coady-defence-cascade-20261024-r218a'
TARGET=19829
CLUB=1904
EXPECTED_PACKAGE='ed4e69657873d66a154066380aaef65be9de9df07b8bdca3c5d59075fcca1cf4'
EXPECTED_JUG='a08425767060e83e0eb4b68d543849837bf8c3c7d7c5eff132c8bfe3390f11d0'
EXPECTED_EQ='2d0cddf307e775f1b500d641c63d0ccd96f9f28c22dbf1fa345a48877762106a'
EXPECTED_MINIFOTO='0520190d77a7bef7a3924397e1d45053cefcb1e2b24aef47eba146fb31ee1b32'
EXPECTED_NAME='Matthew Shevlin'
NATIVE_NAME='Shevlin'
EXPECTED_DOB='1998-12-07'
EXPECTED_PROFILE_SHA='b59334300dfb68db7ba554d775b70373e03f722b6fc8a501989447e9b7a55d8f'
EXPECTED_MATCH_SHA='7aa19b38e3f5ab9002a0069e6274eaaea114a99d829f07e8c29ba7f9713fd8e6'
EXPECTED_SEASON_SHA='13f9ecb0359a072fabc3a06196eff8c38043064691baea230e381ce9dbb77299'
EXPECTED_RTE_SHA='0fb0ddaf27ad283b72026747383351cb508e6a2a7d689279038b1a34c168e435'
EXPECTED_LOI_SHA='b19dafe0d9dd3debe5a2114b27673c8dc8029ec29e1fc56ec8a8458e3bb20d16'


def digest(raw: bytes) -> str: return hashlib.sha256(raw).hexdigest()
def canon(value) -> bytes: return packages.canonical_json_bytes(value)
def _path(value):
    p=(registry.ROOT/value['path']).resolve(strict=True)
    if not p.is_relative_to(registry.ROOT.resolve()) or digest(p.read_bytes())!=value['sha256']:
        raise ValueError('Ballymena original source path/hash binding differs')
    return p

def _source(request,key,sha,url):
    v=request['sources'][key]
    if (v.get('sha256'),v.get('url'))!=(sha,url): raise ValueError(f'{key} source hash/URL pin differs')
    return _path(v)

def _text(path): return ' '.join(BeautifulSoup(path.read_bytes(),'html.parser').get_text(' ',strip=True).split())

def _parse_sources(request):
    profile=_source(request,'shevlin_profile',EXPECTED_PROFILE_SHA,'https://www.bufchistory.com/player.php?id=35')
    match=_source(request,'opening_match',EXPECTED_MATCH_SHA,'https://www.bufchistory.com/matchdetails.php?id=456')
    season=_source(request,'season_archive',EXPECTED_SEASON_SHA,'https://www.bufchistory.com/season.php?id=9')
    rte=_source(request,'tom_derry_signing',EXPECTED_RTE_SHA,'https://www.rte.ie/sport/soccer/2017/0731/894245-loi-transfer-window-sligo-sign-moorhouse-and-mcdonagh/')
    loi=_source(request,'tom_transfer_list',EXPECTED_LOI_SHA,'https://www.leagueofireland.ie/news/complete-list-2018-transfers/')
    receipt=request['sources']['receipt']; rp=_path(receipt)
    if digest(rp.read_bytes())!='d394b203ce355c0412604931947f6c106e3145496ed3b9f47c071bb800e23961':
        raise ValueError('Ballymena original-source receipt differs')
    receipt_doc=json.loads(rp.read_text(encoding='utf-8'))
    bykey={x['key']:x for x in receipt_doc['receipts']}
    for key,path,sha,url in [('player-profile',profile,EXPECTED_PROFILE_SHA,'https://www.bufchistory.com/player.php?id=35'),('opening-match',match,EXPECTED_MATCH_SHA,'https://www.bufchistory.com/matchdetails.php?id=456'),('season-arrivals',season,EXPECTED_SEASON_SHA,'https://www.bufchistory.com/season.php?id=9')]:
        row=bykey.get(key)
        if not row or (row['sha256'],row['requested_url'],row['http_status'])!=(sha,url,200) or (registry.ROOT/row['path']).resolve()!=path:
            raise ValueError('fetch receipt does not bind exact requested original response')
    ps=BeautifulSoup(profile.read_bytes(),'html.parser')
    pcanon=ps.select_one('link[rel="canonical"]')
    if not pcanon or pcanon.get('href')!='https://bufchistory.com/player.php?id=35': raise ValueError('Shevlin archive profile canonical differs')
    pt=_text(profile)
    for value in ('Full name Matthew Shevlin','Position Forward','Nationality Northern Ireland','Born 7 Dec 1998','returned to the Showgrounds and signed a new two year deal with his hometown club in May 2017'):
        if value not in pt: raise ValueError('Shevlin archive profile fact/membership text differs')
    ms=BeautifulSoup(match.read_bytes(),'html.parser')
    mcanon=ms.select_one('link[rel="canonical"]')
    if not mcanon or mcanon.get('href')!='https://bufchistory.com/matchdetails.php?id=456': raise ValueError('opening match canonical differs')
    mt=_text(match)
    if not all(x in mt for x in ('11 Aug 2017','Ballymena United','Crusaders','Matthew Shevlin','55′')): raise ValueError('opening match date/club/person goal differs')
    sections=[]
    for s in ms.select('section.lineup-section-starting'):
        heading=s.select_one('h3')
        if heading and 'Ballymena United' in heading.get_text(' ',strip=True): sections.append(s)
    if len(sections)!=1: raise ValueError('one Ballymena archive starting-XI block required')
    xi=[]
    for li in sections[0].select('ul.lineup > li'):
        num=li.select_one('.shirt-number'); name=li.select_one('.lineup-name')
        if num is None or name is None: raise ValueError('Ballymena archive opening XI row lacks shirt/name')
        xi.append({'shirt':int(num.get_text(strip=True)),'name':name.get_text(' ',strip=True)})
    if len(xi)!=11 or sum(x['name']=='Matthew Shevlin' and x['shirt']==16 for x in xi)!=1:
        raise ValueError('Shevlin not uniquely present in original Aug11 starting XI as #16')
    st=_text(season)
    if not all(x in st for x in ('2017-2018','Thomas McDermott','29 Jan 2018')): raise ValueError('Ballymena season arrival evidence differs')
    rt=_text(rte)
    if 'Derry City have snapped up 19-year-old goalkeeper Tom McDermott until the end of the season' not in rt:
        raise ValueError('RTE Derry ownership/date evidence differs')
    lt=_text(loi)
    if 'Tom McDermott (Ballymena United)' not in lt: raise ValueError('League of Ireland 2018 transfer destination differs')
    return {'profile':profile,'match':match,'season':season,'rte':rte,'loi':loi,'xi':xi}

def _validate_request(base,request_path):
    request=pipeline.read_json_file(request_path)
    if request.get('schema')!=SCHEMA or request.get('season')!=base.season or request.get('release_id')!=base.release_id:
        raise ValueError('Ballymena typed request schema/season/parent differs')
    if base.release_id!=PARENT or base.season!='2017-18': raise ValueError('Ballymena adapter is pinned to current 2017 parent')
    if registry.sha256_file(base.package_path)!=EXPECTED_PACKAGE: raise ValueError('Ballymena preferred parent recipe changed')
    if request.get('parent_package_sha256')!=EXPECTED_PACKAGE: raise ValueError('Ballymena request package binding differs')
    if request.get('parent_native_sha256')!={'DBDAT/JUG98030.FDI':EXPECTED_JUG,'DBDAT/EQ98030.FDI':EXPECTED_EQ}:
        raise ValueError('Ballymena request native pair binding differs')
    native={'DBDAT/JUG98030.FDI':base.game_path/'DBDAT/JUG98030.FDI','DBDAT/EQ98030.FDI':base.game_path/'DBDAT/EQ98030.FDI'}
    if {k:registry.sha256_file(v) for k,v in native.items()}!=request['parent_native_sha256']:
        raise ValueError('Ballymena current parent native pair differs')
    if request.get('parent_minifoto_sha256')!=EXPECTED_MINIFOTO:
        raise ValueError('Ballymena request MINIFOTO parent binding differs')
    if request.get('parent_loose_portrait')!={'path':'DBDAT/MINIFOTO/J9619829.BMP','present':False,'policy':'exact-parent-absence-required'}:
        raise ValueError('Ballymena loose portrait preimage declaration differs')
    photo_archive=base.game_path/'DBDAT/MINIFOTO.PKF'
    if registry.sha256_file(photo_archive)!=EXPECTED_MINIFOTO:
        raise ValueError('Ballymena current MINIFOTO parent differs')
    loose_photo=base.game_path/'DBDAT/MINIFOTO'/f'J96{TARGET:05d}.BMP'
    if loose_photo.exists():
        raise ValueError('unexpected loose donor portrait requires separately reviewed removal')
    return request

def _player_preimage(base,package,jug,eq):
    p=[x for x in package['players'] if x['carrier_id']==TARGET]
    c=[x for x in package['clubs'] if x['carrier_id']==CLUB]
    if len(p)!=1 or len(c)!=1 or p[0]['club_id']!=c[0]['id'] or p[0]['id'] not in c[0]['roster_player_ids']:
        raise ValueError('Ballymena target actor not exclusively present in club recipe')
    owners=exchange.roster
    from scripts.season_opening_order_repair_v1 import native_owners
    if native_owners(eq).get(TARGET)!={CLUB}: raise ValueError('Ballymena target actor is not exclusively EQ-owned')
    ix=IndexedFDIFile.from_bytes(jug); e=next(e for e in ix.entries if e.record_id==TARGET); raw=e.decode_payload(jug)
    native=roster.native_player(raw,TARGET); facts=exchange.facts.native_facts(jug,TARGET)
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    eqix=IndexedFDIFile.from_bytes(eq); ee=next(e for e in eqix.entries if e.record_id==CLUB)
    ep=eq[ee.payload_offset:ee.payload_offset+ee.payload_length]
    er=parse_eq_external_team_roster_payload(ep,{})
    rows=[x for x in er.rows if x.player_record_id==TARGET]
    if er.mode_byte!=1 or len(rows)!=1 or rows[0].flag!=0: raise ValueError('Ballymena target EQ mode/flag differs')
    expect={'player_id':p[0]['id'],'person_id':p[0]['person_id'],'carrier_id':TARGET,'club_id':c[0]['id'],'owner':CLUB,
        'order':facts['startup_order'],'native_name':native['name'],'position':native['position'],'role0':native['roles'][0],
        'birth_date':facts['birth_date'],'eq_flag':rows[0].flag,'recipe_player_sha256':digest(canon(p[0]))}
    if (expect['player_id'],expect['person_id'],expect['order'],expect['native_name'],expect['position'],expect['role0'],expect['birth_date'],expect['eq_flag'])!=('player-19829','person-source-8855fc7b169e52f8d3784f44fa54eb214d1662766b344ef1fb8ab77757ffad8a',12,'McDermott','G',1,'1978-03-01',0):
        raise ValueError('Ballymena current exact actor preimage changed')
    return p[0],c[0],expect

def _build_plan(base,input_path):
    request=_validate_request(base,input_path)
    package=pipeline.read_json_file(base.package_path);jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    actor,club,pre=_player_preimage(base,package,jug,eq); parsed=_parse_sources(request)
    replacement=request['replacement']
    if replacement!=dict(profile_key='shevlin_profile',match_key='opening_match',season_key='season_archive',full_name=EXPECTED_NAME,birth_date=EXPECTED_DOB,nationality='NIR',nationality_label='Northern Ireland',broad_position='F',fine_role=12,fine_role_policy='editorial-compatible-central-striker-from-source-broad-forward-v1',native_order_policy='preserve-exact-reserve-order-12; source membership proof is not native-XI representation',unknown_secondary_fact_policy='explicit-native-preserve-existing-fallback-not-identity-claim',ratings_policy='season_rating_calibration_v3 editorial formula; fixed 2017-08-01 snapshot, strength 60 default for northern-ireland, status unknown, no FIFA match, no unsubstantiated starting/reserve penalty'):
        raise ValueError('Ballymena replacement/request semantics differ')
    person_material={'source_provider':'bufchistory','provider_player_id':'35','profile_url':request['sources']['shevlin_profile']['url'],'profile_sha256':EXPECTED_PROFILE_SHA,'full_name':EXPECTED_NAME,'birth_date':EXPECTED_DOB}
    person_id='person-bufchistory-player-35'
    model_player=copy.deepcopy(actor); model_player.update({'person_id':person_id,'source_name':EXPECTED_NAME,'name':NATIVE_NAME})
    model_player['facts']={'birth_date':EXPECTED_DOB,'primary_position':'F','fine_roles':[12], 'height_cm':None,'nationality':'NIR'}
    vals=rating.editorial(model_player,60,'unknown',dt.date(2017,8,1)); vals['handling']=max(1,min(20,vals['handling']))
    plan={'schema':SCHEMA,'mode':MODE,'season':base.season,'release_id':base.release_id,'source_input':exchange.binding(input_path),
        'parent':{'package_sha256':registry.sha256_file(base.package_path),'jug_sha256':digest(jug),'eq_sha256':digest(eq),'minifoto_sha256':EXPECTED_MINIFOTO},
        'target':{'carrier_id':TARGET,'club_carrier_id':CLUB,'before':pre,'after':{'full_name':EXPECTED_NAME,'native_display_name':NATIVE_NAME,'person_id':person_id,'birth_date':EXPECTED_DOB,'nationality':'NIR','primary_position':'F','fine_roles':[12],'shirt_number':{'policy':'preserve-existing-mode1'},'height_cm':{'policy':'preserve-existing-mode1'},'weight_kg':{'policy':'preserve-existing-mode1'},'native_startup_order':12}},
        'photo_scope':{'selected_carriers':[TARGET],'minifoto_sha256':EXPECTED_MINIFOTO,'loose_file':'DBDAT/MINIFOTO/J9619829.BMP','loose_file_preimage':'absent'},
        'source_bindings':copy.deepcopy(request['sources']),'source_claims':{'tom_preopening_rejection':'Derry signing 2017-07-31 until end season; Ballymena 2017/18 archived arrival 2018-01-29; 2018 League of Ireland transfer list places Tom at Ballymena.','shevlin_positive_membership':'Ballymena United Archive match page 2017-08-11 lists Matthew Shevlin #16 in starting XI and match goal; archive profile gives DOB/nationality/broad Forward and biography says returned and renewed in May 2017.','source_xi':parsed['xi'],'not_claimed':'This one-actor reserve replacement does not reproduce the full Aug11 starting XI or tactics.'},
        'person_id_material':person_material,'rating':{'method':'identity-club-role-age-optional-editorial-calibration-v3','source_id':rating.SOURCE_ID,'snapshot':'2017-08-01','club_strength':60,'opening_state':'unknown','source_identity_match':None,'values':vals},
        'native_policy':{'display_name':NATIVE_NAME,'source_full_name':EXPECTED_NAME,'full_name_cp1252_bytes':len(EXPECTED_NAME.encode('cp1252')),'display_name_policy':'surname-only because full name exceeds this native record stable string window','native_order_policy':'preserve reserve order12; no XI/tactics edits','identity_portrait':'clear old identity portrait, native-no-photo','unknown_fields':'height/weight explicit preserve-existing fallback; native shirt bytes preserved because foreign shirt-number write is unsupported, despite source #16; DOB/country/role sourced'} }
    plan['transaction_id']=digest(canon(plan))[:24]
    return plan

def prepare(base,input_path):
    return _build_plan(base,input_path)

def verify(base,plan):
    if plan.get('schema')!=SCHEMA or _build_plan(base,registry.ROOT/plan['source_input']['path'])!=plan:
        raise ValueError('Ballymena original request does not reprepare exactly')

def filename(plan): return PREFIX+plan['transaction_id']+'.json'
def artifact_id(plan): return PREFIX+plan['transaction_id']
def source_artifact(plan):
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    data=canon(plan)
    return {'filename':filename(plan),'document':copy.deepcopy(plan),'sha256':digest(data),'bytes':data}
def reject_factory_recipe(package):
    if any(a.get('id','').startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('Ballymena typed correction requires exact source reconstruction')

def bind(package,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify_light(base,plan,package)
    result=copy.deepcopy(package); actors={p['carrier_id']:p for p in result['players']}; target=actors[TARGET]
    new_id=plan['target']['after']['person_id']; old_id=target['id']; aid=artifact_id(plan)
    target.update({'person_id':new_id,'name':NATIVE_NAME,'source_name':EXPECTED_NAME,'facts':{'birth_date':EXPECTED_DOB,'fine_roles':[12],'height_cm':{'policy':'preserve-existing-mode1'},'nationality':'NIR','primary_position':'F','shirt_number':{'policy':'preserve-existing-mode1'},'weight_kg':{'policy':'preserve-existing-mode1'}},
        'ratings':{'profile':'pm99-visible-skills-v1','values':copy.deepcopy(plan['rating']['values']),'provenance':{'method':plan['rating']['method'],'proof_grade':'reviewed-editorial','source_ids':[plan['rating']['source_id']]}},
        'fact_fallbacks':[{'field':field,'method':'preserve-existing-mode1','proof':{'artifact_id':aid,'grade':'source-receipt'},'value':{'policy':'preserve-existing-mode1'},'reason':('Source does not publish this secondary fact; preserve native bytes as an unverified fallback.' if field!='shirt_number' else 'Original match publishes Shevlin shirt 16, but foreign native shirt-number writes are unsupported; preserve donor slot bytes without claiming them as Shevlin shirt.') } for field in ('height_cm','shirt_number','weight_kg')],
        'proof':{'artifact_id':aid,'grade':'source-receipt'}})
    portraits=result['assets']['portraits'];portraits[:]=[x for x in portraits if x.get('player_id')!=old_id]
    portraits.append({'player_id':old_id,'status':'native-no-photo','proof':{'artifact_id':aid,'grade':'source-receipt'},'review_reason':'Old McDermott identity image cleared; no Shevlin image sourced.'});portraits.sort(key=lambda x:x['player_id'])
    raw=canon(plan);result['artifacts'].append({'id':aid,'kind':'season-input','sha256':digest(raw),'media_type':'application/json','relative_path':filename(plan)});result['artifacts'].sort(key=lambda x:x['id'])
    result['sources'].append({'id':'source-'+aid,'title':'Ballymena Aug2017 membership and Tom McDermott late-arrival correction','uri':plan['source_bindings']['opening_match']['url'],'proof_grade':'source-receipt','evidence_artifact_id':aid});result['sources'].sort(key=lambda x:x['id'])
    result['proofs'].append({'id':'proof-'+aid,'artifact_id':aid,'grade':'source-receipt','covers':['Shevlin identity/DOB/nationality/broad-forward','Aug2017-positive-membership','McDermott-late-arrival-not-opening-owner']});result['proofs'].sort(key=lambda x:x['id'])
    packages.validate_package(result,strict=False)
    return result

def verify_light(base,plan,package):
    if (base.release_id!=plan['release_id'] or registry.sha256_file(base.package_path)!=plan['parent']['package_sha256']
            or registry.sha256_file(base.package_path)!=plan.get('parent',{}).get('package_sha256')
            or package!=pipeline.read_json_file(base.package_path)):
        raise ValueError('Ballymena bind needs exact registered parent package')
    if registry.sha256_file(registry.ROOT/plan['source_input']['path'])!=plan['source_input']['sha256']:
        raise ValueError('Ballymena source request changed')
    if _build_plan(base,registry.ROOT/plan['source_input']['path'])!=plan:
        raise ValueError('Ballymena binding plan does not reprepare')
    if _player_preimage(base,package,(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(),(base.game_path/'DBDAT/EQ98030.FDI').read_bytes())[2]!=plan['target']['before']:
        raise ValueError('Ballymena target actor preimage changed')

def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    oldj=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();olde=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if (digest(oldj),digest(olde))!=(plan['parent']['jug_sha256'],plan['parent']['eq_sha256']): raise ValueError('Ballymena paired parent native bytes changed')
    if eq!=olde: raise ValueError('Ballymena correction requires the exact unchanged parent EQ payload')
    package=pipeline.read_json_file(base.package_path);result=bind(package,plan)
    codes=delta.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    candidate=delta.compile_players(oldj,result,{'player-19829'},codes)
    preserve_other_records(oldj,candidate,{TARGET})
    ix=IndexedFDIFile.from_bytes(candidate); entries={e.record_id:e for e in ix.entries}; after=entries[TARGET].decode_payload(candidate)
    native=roster.native_player(after,TARGET); facts=exchange.facts.native_facts(candidate,TARGET)
    if (native['name'],native['position'],native['roles'][0],facts['birth_date'],facts['startup_order'])!=(NATIVE_NAME,'F',12,EXPECTED_DOB,12):
        raise ValueError('Ballymena native replacement readback differs')
    end=native['name_end']
    if after[end+8]^0x61 != delta.compiler._country_code('NIR',dict(codes)):
        raise ValueError('Ballymena nationality readback differs')
    if jug not in (oldj,candidate): raise ValueError('Ballymena adapter accepts only exact parent or complete post JUG')
    return candidate,olde

def selected_carriers(plan):
    if plan.get('schema')!=SCHEMA or plan.get('mode')!=MODE:
        raise ValueError('Ballymena portrait selection needs exact schema/mode')
    return {TARGET}

def apply_minifoto(data,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    original=(base.game_path/'DBDAT/MINIFOTO.PKF').read_bytes()
    if digest(original)!=plan['parent']['minifoto_sha256']:
        raise ValueError('Ballymena exact MINIFOTO parent differs')
    expected,_=delta.no_photo_archive(original,selected_carriers(plan))
    if data not in (original,expected):
        raise ValueError('Ballymena MINIFOTO accepts only exact preimage or selected no-photo postimage')
    return expected

def photo_offsets(plan):
    if selected_carriers(plan)!={TARGET}:raise ValueError('Ballymena photo-offset scope differs')
    return {TARGET:[]}

def reconstruction(previous,release_id):
    receipt_path=getattr(previous,'compiler_receipt_path',None)
    if receipt_path is None:return None
    receipt=pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode')!=MODE:return None
    relative=getattr(previous,'locator',{}).get('sourced_profile_assignment_plan_path')
    if not relative:raise ValueError('Ballymena SOURCE receipt lacks the standard profile-assignment plan locator')
    path=(registry.ROOT/relative).resolve()
    if not path.is_relative_to(registry.ROOT.resolve()):raise ValueError('Ballymena SOURCE plan escaped workspace')
    plan=pipeline.read_json_file(path)
    if plan.get('schema')!=SCHEMA or plan.get('mode')!=MODE:raise ValueError('Ballymena SOURCE locator points to another plan schema/mode')
    expected_path=(previous.package_path.parent/filename(plan)).resolve()
    if (path!=expected_path or registry.sha256_file(path)!=receipt.get('original_profile_assignment_plan_sha256')):
        raise ValueError('Ballymena SOURCE plan path/SHA differs from compiler receipt')
    artifact=source_artifact(plan)
    artifact_path=previous.package_path.parent/artifact['filename']
    if not artifact_path.is_file() or registry.sha256_file(artifact_path)!=artifact['sha256']:
        raise ValueError('Ballymena retained recipe source artifact hash differs')
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    pipeline.assert_tree_matches_inventory(base.game_path,pipeline.read_json_file(base.inventory_path))
    pipeline.assert_tree_matches_inventory(previous.game_path,pipeline.read_json_file(previous.inventory_path))
    expected_package=bind(pipeline.read_json_file(base.package_path),plan)
    expected_bytes=packages.canonical_json_bytes(expected_package)
    if previous.package_path.read_bytes()!=expected_bytes:raise ValueError('Ballymena SOURCE recipe does not reproduce exact canonical bytes')
    descriptor_path=previous.package_path.parent/'role-delta-input.json'
    descriptor=pipeline.read_json_file(descriptor_path)
    wanted={'season':plan['season'],'release_id':base.release_id,'package_sha256':plan['parent']['package_sha256'],
        'jug_sha256':plan['parent']['jug_sha256'],'updates':[],'unresolved':[]}
    if descriptor!=wanted:raise ValueError('Ballymena SOURCE inert role descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor_path,release_id=release_id,source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=expected_bytes:raise ValueError('Ballymena complete SOURCE recipe replay differs')
    return {'season':previous.season,'release_id':release_id,'complete_game_inventory_identical':True,
        'complete_recipe_identical':True,'compilation_mode':MODE}
