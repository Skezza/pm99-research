"""Narrow source admission for the Lee Flynn birthday disagreement.

It reproduces the original numeric opening identity and conflicting biographies.
It adds no native writer; common source-verified writer bind/apply is reused.
"""
from __future__ import annotations

import copy
import hashlib
from datetime import date, datetime
from pathlib import Path
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_soccerbase_original_opening_v1 as soccerbase
from scripts import season_original_soccerbase_reserves_v1 as careers
from scripts import season_opening_order_repair_v1 as ownership
from scripts.season_historical_roster_audit_v1 import native_player
from scripts.season_within_club_reserve_repair_v1 import native_facts

ROOT = registry.ROOT
KIND = 'source-backed-known-dob-disagreement'
INPUT_PATH = ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/horne/hayes-flynn-dob-common-input-r188-v1.json'
INPUT_SHA256 = '83f46b47d52dc92ee8c431e471478e00283b671d916ff49535f3b232490e52b9'
RELEASE_ID = 'sourced-hayes-original-label-20261023-r188a'
CARRIER = 10904
OLD_DOB = '1962-11-07'
NEW_DOB = '1973-09-04'
FULL_NAME = 'Lee Flynn'
TEAM_ID, FIXTURE_ID, PROFILE_ID = 1197, 286457, 11256
SOURCES = {
    'team': {'path':'.local/season-2000-01/soccerbase-august-cache-v1/team/1197.html','sha256':'40f702235d7687b6bc9fbd3c072e2262923aa9ccf8f397ab7b8ba531bac9e74f','receipt_path':'.local/season-2000-01/soccerbase-august-cache-v1/team/1197.html.source.json','receipt_sha256':'430dfade84c0b0e76a9dd3439dafd4369aafa76d3b6056d97262fcc2a220be1d','url':'https://www.soccerbase.com/teams/team.sd?season_id=130&team_id=1197&teamTabs=results'},
    'match': {'path':'.local/season-2000-01/soccerbase-august-cache-v1/match/286457.html','sha256':'f3159a2eede245b651b300d0a7fb655cd6885e48960d4603d6e3bb011507cb3b','receipt_path':'.local/season-2000-01/soccerbase-august-cache-v1/match/286457.html.source.json','receipt_sha256':'2d19d0076788083ec083e05eece03c3e3e94e6e4754944667219a0ce137bfee6','url':'https://www.soccerbase.com/matches/additional_information.sd?id_game=286457'},
    'soccerbase_profile': {'path':'.local/season-2000-01/soccerbase-august-cache-v1/player/11256.html','sha256':'96c73e962aad2f7df18e1ed71e6d957ccf12b1e681d1549f69f41982f27fe9e4','receipt_path':'.local/season-2000-01/soccerbase-august-cache-v1/player/11256.html.source.json','receipt_sha256':'947448c785f36845893963ec21b67850c89225295c63b40caa789b57d60a6fd6','url':'https://www.soccerbase.com/players/player.sd?player_id=11256'},
    'eleven_v_eleven': {'path':'.local/consolidated-audit-20261009/parallel-rc-20261023/reconcile/hayes-adapter-proposal/originals-11v11/dd2c644bbea717e72d76b96b29a84b47fc5a7ec3a0788c28e672bc0bcfa5cdb4.html','sha256':'119639148d0afa000364f43ded535ebaf0927bff281beaff801c3906cbfe345b','receipt_path':'.local/consolidated-audit-20261009/parallel-rc-20261023/reconcile/hayes-adapter-proposal/originals-11v11/dd2c644bbea717e72d76b96b29a84b47fc5a7ec3a0788c28e672bc0bcfa5cdb4.source.json','receipt_sha256':'1264a3f32abcd87bfb5dc8fbebe9a3f7a483a78f7f62daa992aae4aabc6da840','url':'https://www.11v11.com/players/lee-flynn-10370/'},
    'barnet_archive': {'path':'.local/consolidated-audit-20261009/stock-club-history-v1/replacement-candidates/barnet-archive-flynn-original-20261016.html','sha256':'4c29b1fa1f6dca93aa8bbecef235f8107a517125b8ed450576adfd4bf798c7b8','receipt_path':'.local/consolidated-audit-20261009/stock-club-history-v1/replacement-candidates/barnet-archive-flynn-original-20261016.source.json','receipt_sha256':'04a18d293bb1f634a002342b21543c97ee9ab2e3fe2b12a307c62d33712d0f1f','url':'https://www.downhillsecondhalf.co.uk/football/ViewPerson.aspx?PersonID=35'}
}
_NATIVE_FACT_CACHE = {}

def _native_fact(jug, carrier):
    """Cache decoded facts only under the complete native JUG content hash."""
    key=(hashlib.sha256(jug).hexdigest(),carrier)
    cached=_NATIVE_FACT_CACHE.get(key)
    if cached is None:
        cached=native_facts(jug,carrier)
        if len(_NATIVE_FACT_CACHE)>=8: _NATIVE_FACT_CACHE.clear()
        _NATIVE_FACT_CACHE[key]=cached
    return cached

def _binding(source):
    return {k:source[k] for k in ('path','sha256','receipt_path','receipt_sha256','url')}

def _body(key):
    source=SOURCES[key]; p=ROOT/source['path']; r=ROOT/source['receipt_path']
    if registry.sha256_file(p)!=source['sha256'] or registry.sha256_file(r)!=source['receipt_sha256']:
        raise ValueError('original source body or receipt hash differs')
    receipt=pipeline.read_json_file(r)
    if receipt.get('url')!=source['url'] or receipt.get('sha256')!=source['sha256']:
        raise ValueError('original receipt URL/body binding differs')
    if 'status' in receipt and receipt['status']!='original-captured':
        raise ValueError('source is not retained as original capture')
    return p.read_bytes()

def verify_sources():
    schedule=_body('team')
    fixture=soccerbase.first_fixture(schedule,TEAM_ID,'2000-01','Football Conference','Hayes',SOURCES['team']['url'])
    if fixture != {'date':'2000-08-19','game_id':FIXTURE_ID,'sides':[{'team_id':2546,'name':'Telford'},{'team_id':TEAM_ID,'name':'Hayes'}],'score':[2,0]}:
        raise ValueError('original schedule does not reproduce exact dated opening fixture')
    match=soccerbase.match(_body('match'),fixture,TEAM_ID,SOURCES['match']['url'],allow_declared_unknown_details=True)
    actors=[r for r in match['starting_xi'] if r.get('provider_player_id')==PROFILE_ID]
    if len(actors)!=1 or actors[0].get('published_match_name')!='L Flynn' or actors[0].get('position')!='M':
        raise ValueError('opening match sheet does not bind one exact Flynn identity')
    sb_body=_body('soccerbase_profile')
    sb=soccerbase.profile(sb_body,actors[0],SOURCES['soccerbase_profile']['url'])
    if sb.get('name')!=FULL_NAME or sb.get('birth_date')!=OLD_DOB:
        raise ValueError('linked numeric Soccerbase profile conflict differs')
    career=careers.career_interval(sb_body,TEAM_ID,'2000-08-19')
    if career != {'from_date':'1995-08-01','to_date':'2001-01-10','provider_team_id':TEAM_ID,'fixture_date':'2000-08-19'}:
        raise ValueError('numeric Soccerbase biography does not positively span Hayes fixture')
    eleven=BeautifulSoup(_body('eleven_v_eleven'),'lxml')
    eleven_text=' '.join(eleven.get_text(' ',strip=True).split())
    if (eleven.title.get_text(' ',strip=True)!='Lee Flynn Football Player Statistics | 11v11.com'
                    or [h.get_text(' ',strip=True) for h in eleven.select('h1')]!=[FULL_NAME]
                    or 'Date of birth 04 September 1973' not in eleven_text
                    or 'Place of birth Hampstead' not in eleven_text
                    or 'Flynn joined Barnet from Conference club Hayes in January 2001' not in eleven_text):
        raise ValueError('independent 11v11 full-name DOB/career evidence differs')
    receipt=pipeline.read_json_file(ROOT/SOURCES['barnet_archive']['receipt_path'])
    barnet=BeautifulSoup(_body('barnet_archive'),'lxml'); text=' '.join(barnet.get_text(' ',strip=True).split())
    if (not barnet.title or barnet.title.get_text(' ',strip=True)!=receipt.get('original_title')
                    or 'Lee FLYNN' not in text or 'Born In Hampstead On 04/09/1973' not in text
                    or 'Joined the club from Hayes in January 2001 for £13500' not in text
                    or 'First Appearance Score Gls York City H 13/01/2001' not in text):
        raise ValueError('independent Barnet archive identity/date/career evidence differs')
    return {'fixture':fixture,'profile_id':PROFILE_ID,'soccerbase_dob':OLD_DOB,'independent_dobs':[NEW_DOB,NEW_DOB],
        'identity_basis':'numeric Soccerbase match-sheet profile binding plus full-name biographies, Hampstead, and Hayes-to-Barnet January 2001 chronology; provider IDs remain distinct',
        'source_bindings':{k:_binding(v) for k,v in SOURCES.items()}}

def _mask(jug):
    idx={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    if CARRIER not in idx: raise ValueError('native carrier is absent')
    entry=idx[CARRIER]; raw=entry.decode_payload(jug); obs=native_player(raw,CARRIER)
    if obs.get('name')!='Lee FLYNN' or _native_fact(jug,CARRIER).get('birth_date')!=OLD_DOB:
        raise ValueError('native exact identity or DOB preimage differs')
    start=obs['name_end']+12
    before=date.fromisoformat(OLD_DOB); after=date.fromisoformat(NEW_DOB)
    old=bytes([before.day,before.month])+before.year.to_bytes(2,'little')
    new=bytes([after.day,after.month])+after.year.to_bytes(2,'little')
    masks=[]; post=bytearray(jug)
    for i,(b,a) in enumerate(zip(old,new)):
        off=entry.payload_offset+start+i
        if jug[off]!=b: raise ValueError('indexed native birthday byte preimage differs')
        masks.append({'file':'DBDAT/JUG98030.FDI','record_offset':start+i,'file_offset':off,'before':b,'after':a})
        post[off]=a
    if _native_fact(bytes(post),CARRIER).get('birth_date')!=NEW_DOB:
        raise ValueError('indexed native birthday postimage does not decode')
    return masks

def prepare(base,input_path):
    path=Path(input_path)
    if not path.is_absolute(): path=ROOT/path
    path=path.resolve()
    if path!=INPUT_PATH.resolve() or registry.sha256_file(path)!=INPUT_SHA256:
        raise ValueError('exact retained r188 source input path/hash required')
    request=pipeline.read_json_file(path)
    import scripts.season_source_verified_player_changes_v1 as common
    if (request.get('schema')!=common.INPUT_SCHEMA or request.get('kind')!=KIND or request.get('season')!='2000-01'
                    or request.get('release_id')!=RELEASE_ID or base.season!='2000-01' or base.release_id!=RELEASE_ID
                    or len(request.get('changes',[]))!=1):
        raise ValueError('exact source-backed DOB request and r188 parent required')
    selection=request['changes'][0]
    if (selection.get('carrier_id')!=CARRIER or selection.get('field_mask')!=['birth_date']
                    or selection.get('before_birth_date')!=OLD_DOB or selection.get('birth_date')!=NEW_DOB
                    or selection.get('source_bindings')!={k:_binding(v) for k,v in SOURCES.items()}):
        raise ValueError('only exact Lee Flynn DOB correction and bound evidence is admitted')
    source=verify_sources()
    package=pipeline.read_json_file(base.package_path); hits=[p for p in package['players'] if p.get('carrier_id')==CARRIER]
    if len(hits)!=1: raise ValueError('exact recipe carrier must be unique')
    actor=hits[0]
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if (actor.get('name')!=FULL_NAME or actor.get('source_name')!=FULL_NAME
                    or actor.get('facts',{}).get('birth_date')!=OLD_DOB or _native_fact(jug,CARRIER).get('birth_date')!=OLD_DOB):
        raise ValueError('exact r188 recipe/native old DOB preimage differs')
    club = next(c for c in package['clubs'] if c['id'] == actor['club_id'])
    if (club['carrier_id'] != 3307 or club['name'] != 'Hayes'
            or ownership.native_owners(eq).get(CARRIER) != {3307}):
        raise ValueError('Flynn DOB correction requires the exact exclusive Hayes owner')
    masks=_mask(jug)
    row={'carrier_id':CARRIER,'before':copy.deepcopy(actor),'values':{'birth_date':NEW_DOB},'field_mask':['birth_date'],
        'native_masks':masks,'source_evidence':{'provider_dob':OLD_DOB,'independent_dobs':[NEW_DOB,NEW_DOB],
        'provider_profile_id':PROFILE_ID,'opening_match_id':FIXTURE_ID,'opening_fixture_date':'2000-08-19',
        'identity':'linked Soccerbase numeric opening-XI profile plus two independent full-name biography DOB claims'}}
    plan={'schema':common.SCHEMA,'season':base.season,'release_id':base.release_id,'kind':KIND,
        'source_input':common.binding(path),'package_sha256':registry.sha256_file(base.package_path),
        'jug_sha256':common.digest(jug),'eq_sha256':common.digest(eq),'updates':[row],
        'scope':'Only Lee Flynn birth_date and its exact four-byte indexed native DOB field; name, position, nationality, role, ownership, order, skills and all other data unchanged.',
        'source_policy':'typed-soccerbase-opening-XI-numeric-profile-plus-independent-original-biography-DOB-agreement-v1',
        'source_admission':source}
    plan['transaction_id']=common.digest(packages.canonical_json_bytes(plan))[:24]
    validate_mask(plan)
    return plan

def validate_mask(plan):
    import scripts.season_source_verified_player_changes_v1 as common
    if plan.get('schema')!=common.SCHEMA or plan.get('kind')!=KIND or len(plan.get('updates',[]))!=1:
        raise ValueError('one typed source-backed DOB disagreement required')
    row=plan['updates'][0]
    if (set(row)!={'carrier_id','before','values','field_mask','native_masks','source_evidence'}
                    or row.get('carrier_id')!=CARRIER or row.get('field_mask')!=['birth_date']
                    or row.get('values')!={'birth_date':NEW_DOB}
                    or row.get('before',{}).get('facts',{}).get('birth_date')!=OLD_DOB):
        raise ValueError('DOB-only exact actor field preimage required')
    if row['source_evidence']!={'provider_dob':OLD_DOB,'independent_dobs':[NEW_DOB,NEW_DOB],
            'provider_profile_id':PROFILE_ID,'opening_match_id':FIXTURE_ID,'opening_fixture_date':'2000-08-19',
            'identity':'linked Soccerbase numeric opening-XI profile plus two independent full-name biography DOB claims'}:
        raise ValueError('typed disagreement evidence record differs')
    masks=row['native_masks']; before=date.fromisoformat(OLD_DOB); after=date.fromisoformat(NEW_DOB)
    old=bytes([before.day,before.month])+before.year.to_bytes(2,'little'); new=bytes([after.day,after.month])+after.year.to_bytes(2,'little')
    if len(masks)!=4: raise ValueError('all four encoded DOB bytes must be bound')
    for i,m in enumerate(masks):
        if (set(m)!={'file','record_offset','file_offset','before','after'} or m['file']!='DBDAT/JUG98030.FDI'
                        or m['record_offset']!=masks[0]['record_offset']+i or m['file_offset']!=masks[0]['file_offset']+i
                        or m['before']!=old[i] or m['after']!=new[i]): raise ValueError('DOB field mask differs from exact encoded date')
