"""Source-bound Walsall two-person prepare adapter using existing native writers."""
from __future__ import annotations
import copy, hashlib, json
from pathlib import Path
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts.season_opening_order_repair_v1 import native_owners

ROOT=registry.ROOT
HERE='.local/consolidated-audit-20261009/parallel-rc-20261023/horne/source/walsall-two-new-person-v4/'
SIGGI_ROOT='.local/consolidated-audit-20261009/parallel-rc-20261023/horne/source/walsall-two-new-person-v2/'
PARENT='sourced-ftc-csank-manager-20261023-r201a'
PACKAGE_SHA='15cc70523e096395b3cb66c6e70afb5d5ef70405ffb299a0bbe5dfb139e9c92d'
JUG_SHA='2e2e7634b155946ff577e3cc5866c1434976a5a59fc4a680201357105f1ff5c4'
EQ_SHA='3e1d02092aee521845a218003e6b401a05f0a70b2350f6965a9ef75fd2e5c7d1'
SIGGI={
    'siggi-eyjolfsson-11v11-profile.html':('https://www.11v11.com/players/siggi-eyjolfsson-1204/','5b8a3fba9aebb280072ae63667bd49a0436c05f3501ec7eda8df5f83835167a8','8d09374e6060b8fff7a7501faf69b737564734391f281044f8bff4fe1f3965d3'),
    'siggi-walsall-kidderminster-11v11-match-937.html':('https://www.11v11.com/matches/walsall-v-kidderminster-harriers-22-august-2000-937/','b52cf1a2381e1ac4e989b17fa8510ab633629429a879a467ecb72aeee3d751f0','c6b4849937d3e14a4ce769f0a06d78e5e504f172d63aa287a486a302356e9758'),
    'siggi-sky-profile.html':('https://www.skysports.com/football/player/77548/siggi-eyjolfsson','989b05b26dc1450e24f378876800dc8dece4cda89e4c286dd058d0bfbfae92cd','e73ae96e18a500d056c2acb695747c3363823303fccfce17ef74ede155e317dc'),
    'sigurthur-wikipedia.html':('https://en.wikipedia.org/wiki/Sigur%C3%B0ur_Ragnar_Eyj%C3%B3lfsson','f5ba0acd19c0fff6950aed6a8c599012e798a9b91658fc96d50bda28aeedf7d1','7961dc8c3569e0562fd0731989f5b749e05a2e306f07798da6002e2ab051a56c')}

def strict_11v11_carter_person_id(person):
    expected_evidence={'policy':'source-profile-explicit-DOB-conflict-v1',
        'path':'.local/consolidated-audit-20261009/parallel-rc-20261023/reconcile/originals-v1/alfie-carter-11v11-identity-candidate.html',
        'sha256':'45949e0e147b7654570f7841efc562e71f5f184e48c957fb89029cc7edc7945e',
        'url':'https://www.11v11.com/players/alfie-carter-949/','published_name':'Alfie Carter',
        'published_birth_date':'1980-08-23','selected_birth_date':'1980-09-30',
        'selected_birth_date_status':'target-year-annual-source-prioritised-but-disputed-not-verified'}
    if (person.get('identity_policy')!='original-11v11-player-949-profile-explicit-DOB-conflict-v1'
                    or person.get('source_player_id')!='11v11:949' or person.get('source_provider')!='11v11'
                    or person.get('source_profile_url')!=expected_evidence['url']
                    or person.get('source_profile_sha256')!=expected_evidence['sha256']
                    or person.get('name')!='Alfie Carter' or person.get('birth_date')!='1980-09-30'
                    or person.get('identity_evidence')!=expected_evidence):
        raise ValueError('11v11 Carter namespace, source binding, or DOB conflict disclosure differs')
    body=_raw(expected_evidence['path'],expected_evidence['sha256'])
    text=' '.join(BeautifulSoup(body,'lxml').get_text(' ',strip=True).split())
    page=BeautifulSoup(body,'lxml'); title=page.title.get_text(' ',strip=True) if page.title else ''
    if title!='Alfie Carter Football Player Statistics | 11v11.com' or not all(x in text for x in ('Alfie Carter','23 August 1980','Nationality English')):
        raise ValueError('11v11 retained profile identity does not reproduce')
    return 'person-11v11-949'

def _raw(path,sha):
    p=(ROOT/path).resolve(strict=True)
    if not p.is_relative_to(ROOT.resolve()) or registry.sha256_file(p)!=sha: raise ValueError('Walsall source body hash/path mismatch')
    return p.read_bytes()
def _receipt(bodypath,bodysha,receiptsha,url):
    rp=ROOT/(bodypath.removesuffix('.html')+'.source.json')
    if registry.sha256_file(rp)!=receiptsha: raise ValueError('Siggi source receipt hash mismatch')
    d=json.loads(rp.read_text())
    if d.get('schema_version')!='pm99-original-source-body-receipt-v1' or d.get('path')!=bodypath or d.get('sha256')!=bodysha or d.get('url')!=url: raise ValueError('Siggi receipt/body binding differs')
def _text(path,sha): return ' '.join(BeautifulSoup(_raw(path,sha),'lxml').get_text(' ',strip=True).split())
def prepare(base,input_path):
    req=pipeline.read_json_file(input_path)
    expected_input_keys={'schema','proposal_kind','season','release_id','scope','source_policy','target_carriers','protected_other_owner_carriers','carter_birth_date_status','carter_weight_policy','siggi_sources_require_body_and_receipt_hashes'}
    if set(req)!=expected_input_keys or req.get('schema')!='pm99-walsall-opening-two-person-v4' or req.get('proposal_kind')!='typed-walsall-two-local-slot-source-admission-v4' or req.get('season')!='2000-01' or req.get('release_id')!=PARENT or req.get('target_carriers')!=[21064,21065] or req.get('protected_other_owner_carriers')!=[10955,30432] or req.get('carter_birth_date_status')!='selected-from-target-year-FootballSquads-annual-row-but-disputed-and-not-verified' or req.get('carter_weight_policy')!='existing-footballsquads-season-st-lb-conversion-v1' or req.get('siggi_sources_require_body_and_receipt_hashes') is not True or base.release_id!=PARENT or base.season!='2000-01': raise ValueError('exact Walsall r201a request required')
    if (registry.sha256_file(base.package_path),registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI'))!=(PACKAGE_SHA,JUG_SHA,EQ_SHA): raise ValueError('Walsall native parent differs')
    package=pipeline.read_json_file(base.package_path); players={p['carrier_id']:p for p in package['players']}; club=next(c for c in package['clubs'] if c['carrier_id']==364)
    if (club['name'],len(club['roster_player_ids']))!=('Walsall',25): raise ValueError('Walsall roster count/preimage differs')
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    owners=native_owners(eq)
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    ix=IndexedFDIFile.from_bytes(eq); eqentry=next((e for e in ix.entries if e.record_id==364),None)
    if eqentry is None: raise ValueError('Walsall EQ record absent')
    eqpayload=eq[eqentry.payload_offset:eqentry.payload_offset+eqentry.payload_length]
    native_roster=parse_eq_external_team_roster_payload(eqpayload,{})
    roster_carriers=[next(p['carrier_id'] for p in players.values() if p['id']==pid) for pid in club['roster_player_ids']]
    if (len(roster_carriers)!=25 or len(set(roster_carriers))!=25 or native_roster is None or native_roster.mode_byte!=0
                    or any(r.flag for r in native_roster.rows) or {r.player_record_id for r in native_roster.rows}!=set(roster_carriers)
                    or any(owners.get(c)!={364} for c in roster_carriers)):
        raise ValueError('exact 25-actor exclusive-owned Walsall mode0 roster required')
    for carrier,expect in ((21064,('Barry Horne','1962-05-18')),(21065,('Fitzroy Simpson','1970-02-26'))):
        p=players[carrier]
        if (p['source_name'],p['facts']['birth_date'])!=expect or owners.get(carrier)!={364}: raise ValueError('exact target actor/owner guard failed')
    # Immutable source/receipt bindings: target-year roster, dated Sky five-player sheet and Carter profile.
    annualpath='.local/consolidated-audit-20261009/parallel-rc-20261023/horne/source/cache-v1/blobs/67/670ca39197af1e31d087597663ecb76bb266b17f37176d527625e172790d3cb4'
    annualsha='670ca39197af1e31d087597663ecb76bb266b17f37176d527625e172790d3cb4'
    annual=_text(annualpath,annualsha)
    annual_path=(ROOT/annualpath); annual_page=BeautifulSoup(annual_path.read_bytes(),'lxml')
    annual_rows=[' '.join(tr.get_text(' ',strip=True).split()) for tr in annual_page.find_all('tr')]
    if sum("16 Siggi Eyjolfsson M 6'02\" 12 09 01-12-73 Reykjavik RC Harelebeke" in x for x in annual_rows)!=1 or sum("23 Alfonso Carter M 5'10\" 10 05 30-09-80 Birmingham" in x for x in annual_rows)!=1: raise ValueError('exact target-year annual source rows unavailable')
    from scripts.capture_footballsquads_season import _weight_kg
    carter_weight=_weight_kg('10 05',label='Walsall Alfonso Carter target-year annual row')
    siggi_weight=_weight_kg('12 09',label='Walsall Siggi Eyjolfsson target-year annual row')
    if (carter_weight,siggi_weight)!=(66,80): raise ValueError('FootballSquads period weight conversion differs')
    alfie_path='.local/consolidated-audit-20261009/parallel-rc-20261023/horne/source/cache-v1/blobs/3d/3d4989a46351967c6c4eceb0d34eed8bc9cb4aeb62225ec295a26ebcd41f23b3'; alfie_sha='3d4989a46351967c6c4eceb0d34eed8bc9cb4aeb62225ec295a26ebcd41f23b3'
    alfie_page=BeautifulSoup(_raw(alfie_path,alfie_sha),'lxml'); alfie_rows=[' '.join(tr.get_text(' ',strip=True).split()) for tr in alfie_page.find_all('tr')]
    if sum("23 Alfie Carter F 5'10\" 10 05 30-09-80 Birmingham" in x for x in alfie_rows)!=1: raise ValueError('Carter prior-year alias row does not reproduce')
    correction_path='.local/consolidated-audit-20261009/parallel-rc-20261023/horne/alfie-carter-source-correction-v3.json'; correction_sha='032cf33117c1b7dcd65697d3cfe29117585610af634674c7ac345278d795eaf6'
    if registry.sha256_file(ROOT/correction_path)!=correction_sha: raise ValueError('frozen Carter DOB conflict/alias report changed')
    skypath='.local/consolidated-audit-20261009/parallel-rc-20261023/reconcile/originals-v1/sky-walsall-opening-team-sheet-113585.html'; skysha='e6aac609fb2588582d7702ea320244314dd642239216f19049b8835f1166b594'
    sky=_text(skypath,skysha)
    if not all(s.casefold() in sky.casefold() for s in ('12.08.2000','Walsall','Carter','Byfield','Emberson','Keates','Wrack')): raise ValueError('Sky opening team sheet does not bind Carter and five substitutes')
    carterpath='.local/consolidated-audit-20261009/parallel-rc-20261023/reconcile/originals-v1/alfie-carter-11v11-identity-candidate.html'; cartersha='45949e0e147b7654570f7841efc562e71f5f184e48c957fb89029cc7edc7945e'
    carter=_text(carterpath,cartersha)
    carter_page=BeautifulSoup(_raw(carterpath,cartersha),'lxml')
    profile_title=carter_page.title.get_text(' ',strip=True) if carter_page.title else ''
    if profile_title!='Alfie Carter Football Player Statistics | 11v11.com': raise ValueError('11v11 profile title/provider ID binding differs')
    if not all(s in carter for s in ('Alfie Carter','English','Forward','23 August 1980','66 kg')): raise ValueError('Carter profile identity/nationality/role/DOB/weight conflict witness differs')
    for name,(url,sha,rsha) in SIGGI.items():
        path=SIGGI_ROOT+name; _raw(path,sha); _receipt(path,sha,rsha,url)
    sigprofile=_text(SIGGI_ROOT+'siggi-eyjolfsson-11v11-profile.html',SIGGI['siggi-eyjolfsson-11v11-profile.html'][1])
    sigmatch=_text(SIGGI_ROOT+'siggi-walsall-kidderminster-11v11-match-937.html',SIGGI['siggi-walsall-kidderminster-11v11-match-937.html'][1])
    wiki=_text(SIGGI_ROOT+'sigurthur-wikipedia.html',SIGGI['sigurthur-wikipedia.html'][1])
    if not all(s in sigprofile for s in ('01 December 1973','Icelandic','Forward','1.88 m')): raise ValueError('Siggi identity profile differs')
    if not all(s in sigmatch for s in ('22 August 2000','Walsall','Kidderminster Harriers','Siggi Eyjolfsson','Jorge Leitao')): raise ValueError('Siggi dated Walsall appearance differs')
    if not all(s in wiki for s in ('Sigurður Ragnar Eyjólfsson','1 December 1973','Icelandic')): raise ValueError('Siggi formal identity witness differs')
    # Build the normal exchange plan data shape; new-person facts are reconstructed below by delta.updated_package.
    evidence={
        'annual':dict(path=annualpath,sha256=annualsha,url='https://www.footballsquads.co.uk/eng/2000-2001/d2/walsall.htm'),
        'alfie_prior_annual':dict(path=alfie_path,sha256=alfie_sha,url='https://www.footballsquads.co.uk/eng/1999-2000/d1/walsall.htm'),
        'carter_identity_adjudication':dict(path=correction_path,sha256=correction_sha),
        'sky':dict(path=skypath,sha256=skysha,url='https://www.skysports.com/football/rotherham-united-vs-walsall/teams/113585'),
        'carter_profile':dict(path=carterpath,sha256=cartersha,url='https://www.11v11.com/players/alfie-carter-949/'),
        'siggi_profile':dict(path=SIGGI_ROOT+'siggi-eyjolfsson-11v11-profile.html',sha256=SIGGI['siggi-eyjolfsson-11v11-profile.html'][1],url=SIGGI['siggi-eyjolfsson-11v11-profile.html'][0],receipt_path=SIGGI_ROOT+'siggi-eyjolfsson-11v11-profile.source.json',receipt_sha256=SIGGI['siggi-eyjolfsson-11v11-profile.html'][2]),
        'siggi_match':dict(path=SIGGI_ROOT+'siggi-walsall-kidderminster-11v11-match-937.html',sha256=SIGGI['siggi-walsall-kidderminster-11v11-match-937.html'][1],url=SIGGI['siggi-walsall-kidderminster-11v11-match-937.html'][0],receipt_path=SIGGI_ROOT+'siggi-walsall-kidderminster-11v11-match-937.source.json',receipt_sha256=SIGGI['siggi-walsall-kidderminster-11v11-match-937.html'][2]),
        'siggi_sky':dict(path=SIGGI_ROOT+'siggi-sky-profile.html',sha256=SIGGI['siggi-sky-profile.html'][1],url=SIGGI['siggi-sky-profile.html'][0],receipt_path=SIGGI_ROOT+'siggi-sky-profile.source.json',receipt_sha256=SIGGI['siggi-sky-profile.html'][2]),
        'siggi_wiki':dict(path=SIGGI_ROOT+'sigurthur-wikipedia.html',sha256=SIGGI['sigurthur-wikipedia.html'][1],url=SIGGI['sigurthur-wikipedia.html'][0],receipt_path=SIGGI_ROOT+'sigurthur-wikipedia.source.json',receipt_sha256=SIGGI['sigurthur-wikipedia.html'][2])}
    decisions=[]; updates=[]
    specs=[(21064,'Alfie Carter','1980-09-30','11v11:949','F','ENG',178,carter_weight,23,'source-selected-disputed-target-year-table-DOB-v1'),
                                (21065,'Siggi Eyjolfsson','1973-12-01','wikipedia:Sigur%C3%B0ur_Ragnar_Eyj%C3%B3lfsson','F','ISL',188,siggi_weight,16,'original-Wikipedia-full-name-DOB-unique-senior-interior-year-v1')]
    for carrier,name,dob,pid,pos,country,height,weight,shirt,policy in specs:
        old=players[carrier]
        person=dict(name=('Alfie Carter' if carrier==21064 else 'Sigurður Ragnar Eyjólfsson'),birth_date=dob,source_player_id=pid,
            source_provider=('11v11' if pid=='11v11:949' else 'wikipedia'),source_profile_url=('https://www.11v11.com/players/alfie-carter-949/' if pid=='11v11:949' else SIGGI['sigurthur-wikipedia.html'][0]),identity_policy=('original-11v11-player-949-profile-explicit-DOB-conflict-v1' if pid=='11v11:949' else policy),source_profile_sha256=(cartersha if pid=='11v11:949' else None))
        if pid=='11v11:949':
            person['identity_evidence']=dict(policy='source-profile-explicit-DOB-conflict-v1',path=carterpath,sha256=cartersha,
                url='https://www.11v11.com/players/alfie-carter-949/',published_name='Alfie Carter',published_birth_date='1980-08-23',
                selected_birth_date='1980-09-30',selected_birth_date_status='target-year-annual-source-prioritised-but-disputed-not-verified')
            strict_11v11_carter_person_id(person)
        source_player=dict(name=name,birth_date=dob,position=pos,nationality=country,height_cm=height,weight_kg=weight)
        source_player['shirt_number']=shirt
        replacement=dict(source_person=person,source_player=source_player,raw_evidence=dict(status='raw-source-reparsed',local_path=HERE,source_inputs=evidence,
            decision='DOB selected from 2000/01 annual #23 Birmingham Alfie/Alfonso identity row; DOB is disputed and not verified' if carrier==21064 else '22-August Walsall used substitute; annual row and four body+receipt pairs retained',
            weight_projection=dict(value=weight,source_weight= '10 05' if carrier==21064 else '12 09',policy='existing-footballsquads-season-st-lb-conversion-v1',
                            formula='round(stones * 6.35029318 + pounds * 0.45359237)',profile_weight_kg=66 if carrier==21064 else 76,
                            annual_position='M',source_row='target-year FootballSquads past-player row'),
            role_projection=dict(value='F',policy='profile-derived-compatible-broad-forward-not-target-year-annual-position-v1',role_is_historical_fact=False,
                primary_profile='11v11 explicit Forward' if carrier==21064 else '11v11 explicit Forward; Sky says Striker',annual_counterclaim='FootballSquads target-year past-player row says M')))
        updates.append(dict(layer='main',player_id=old['id'],carrier_id=carrier,before=old,replacement=replacement,replacement_opening_evidence=dict(date='2000-08-12' if carrier==21064 else '2000-08-22')))
        decisions.append(dict(carrier_id=carrier,preserved_source_carrier=None,before=old,fine_roles=[12 if pos=='F' else 9]))
    # Bench order: exact five source-named substitutes; all remaining 9 roster actors retained as tail extras.
    oldroster=[p['carrier_id'] for p in sorted((p for p in players.values() if p['club_id']==club['id']),key=lambda p: p['carrier_id'])]
    # Native startup order establishes immutable XI and pre-existing tail order.
    from scripts.season_within_club_reserve_repair_v1 import native_facts
    ordered=sorted(oldroster,key=lambda x:native_facts(jug,x)['startup_order'])
    xi=ordered[:11]; tail=[x for x in ordered[11:] if x not in {21058,21060,21061,21062,21064,21065,21066}]
    full=xi+[21060,21064,21066,21062,21058]+tail+[21061,21065]
    if len(full)!=25 or set(full)!=set(oldroster): raise ValueError('25-player order does not retain exact full roster')
    # Parse only Walsall's exact named five-player source bench, not the opponent column.
    sky_page=BeautifulSoup(_raw(skypath,skysha),'lxml')
    walsall_cols=[c for c in sky_page.select('div.sdc-site-team-lineup__col') if c.select_one('h4.sdc-site-team-lineup__team-name') and c.select_one('h4.sdc-site-team-lineup__team-name').get_text(' ',strip=True)=='Walsall']
    if len(walsall_cols)!=1: raise ValueError('exact single Sky Walsall team column required')
    walsall_bench=walsall_cols[0].select('dl.sdc-site-team-lineup__players--subs dd.sdc-site-team-lineup__player-name')
    if [x.get_text(' ',strip=True) for x in walsall_bench]!=['D Byfield','A Carter','C Emberson','D Keates','D Wrack']:
        raise ValueError('exact five original Sky Walsall substitutes required')
    walsall_xi=[x.get_text(' ',strip=True) for x in walsall_cols[0].select('dl.sdc-site-team-lineup__players:not(.sdc-site-team-lineup__players--subs) dd.sdc-site-team-lineup__player-name')]
    if walsall_xi!=['B Angell','T Bennett','I Brightwell','G Bukran','P Hall','J Leitao','P Matias','I Roper','J Walker','A Tillson','Z Aranalde']:
        raise ValueError('exact original Sky Walsall starting XI required')
    request=dict(schema=req['schema'],season='2000-01',release_id=PARENT,evidence=evidence,moves=[],new_people=[],retirements=[],orders=[],
        source_disposition=dict(replaced_local_slots=[21064,21065],preserve_other_owner_carriers=[10955,30432],career_retirements_claimed=False),
        bench=dict(source='Sky 2000-08-12 published sheet',five=[21060,21064,21066,21062,21058],full_order=full,tail_extras=tail+[21061,21065]))
    plan=dict(schema=exchange.SCHEMA,season='2000-01',release_id=PARENT,source_input=exchange.binding(input_path),package_sha256=PACKAGE_SHA,jug_sha256=JUG_SHA,eq_sha256=EQ_SHA,request=request,updates=updates,decisions=decisions,
        bindings=dict(snapshot=dict(project_url='https://www.11v11.com/')),source_title='Walsall target-year annual identities and dated August source membership',proof_covers=['two exact Walsall local actor-slot replacements','five source-listed August substitutes and retained roster tail'],scope='Replace only Walsall actor copies 21064 and 21065; preserve valid separate Horne10955/Simpson30432 actors and all 25 native roster links; no career-retirement claims.')
    plan['transaction_id']=hashlib.sha256(packages.canonical_json_bytes(plan)).hexdigest()[:24]
    return plan

def validate_plan_bench(plan,package,jug,eq):
    if plan.get('schema')!=exchange.SCHEMA or plan.get('release_id')!=PARENT or plan.get('package_sha256')!=PACKAGE_SHA or plan.get('jug_sha256')!=JUG_SHA or plan.get('eq_sha256')!=EQ_SHA:
        raise ValueError('Walsall plan/native parent binding differs')
    req=plan.get('request',{}); bench=req.get('bench')
    if set(bench or {})!={'source','five','full_order','tail_extras'} or bench.get('source')!='Sky 2000-08-12 published sheet' or bench.get('five')!=[21060,21064,21066,21062,21058]:
        raise ValueError('Walsall bench fields/source/five-player mapping differ')
    if len(bench['full_order'])!=25 or len(set(bench['full_order']))!=25 or set(bench['full_order'])!={p['carrier_id'] for p in package['players'] if p['club_id']=='english-club-364'}:
        raise ValueError('Walsall full order must cover its exact 25 unique actor carriers')
    if bench['full_order'][11:16]!=bench['five'] or bench['tail_extras']!=bench['full_order'][16:]:
        raise ValueError('Walsall bench/tail boundary differs')
    if hashlib.sha256(jug).hexdigest()!=JUG_SHA or hashlib.sha256(eq).hexdigest()!=EQ_SHA:
        raise ValueError('Walsall exact JUG/EQ source preimage differs')
    ix=IndexedFDIFile.from_bytes(eq); entry=next(e for e in ix.entries if e.record_id==364)
    raw=eq[entry.payload_offset:entry.payload_offset+entry.payload_length]
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    native=parse_eq_external_team_roster_payload(raw,{})
    if native is None or native.mode_byte!=0 or any(r.flag for r in native.rows) or {r.player_record_id for r in native.rows}!=set(bench['full_order']):
        raise ValueError('Walsall native mode0 owner rows/preimage differ')
    if any(native_owners(eq).get(c)!={364} for c in bench['full_order']): raise ValueError('Walsall actors must remain exclusively owned')
    source=plan.get('source_input',{})
    path=registry.ROOT/source.get('path','')
    if registry.sha256_file(path)!=source.get('sha256'): raise ValueError('Walsall typed source request binding changed')
    base=registry.load_registered_release('2000-01',PARENT)
    if prepare(base,path)!=plan: raise ValueError('Walsall typed plan does not replay from its exact source request')

def bind_bench(result,plan):
    players={p['carrier_id']:p for p in result['players']}
    club=next(c for c in result['clubs'] if c['carrier_id']==364)
    full=plan['request']['bench']['full_order']
    club['roster_player_ids']=[players[x]['id'] for x in full]
    club['opening']['substitute_player_ids']=[players[x]['id'] for x in plan['request']['bench']['five']]
    return result

def bind(package,plan,exchange_impl=None):
    base=registry.load_registered_release('2000-01',PARENT)
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    validate_plan_bench(plan,package,jug,eq)
    result=(exchange_impl or exchange.bind)(package,plan)
    return bind_bench(result,plan)

def apply_bench(candidate,eq,plan):
    validate_plan_bench(plan,pipeline.read_json_file(registry.ROOT/registry.load_registered_release('2000-01',PARENT).package_path),
                    (registry.load_registered_release('2000-01',PARENT).game_path/'DBDAT/JUG98030.FDI').read_bytes(),
                    (registry.load_registered_release('2000-01',PARENT).game_path/'DBDAT/EQ98030.FDI').read_bytes())
    from scripts import season_opening_order_repair_v1 as ordering
    from app.fdi_indexed import IndexedFDIFile
    from app.player_initial_order import read_initial_order
    from app.xor import xor_decode
    ix=IndexedFDIFile.from_bytes(candidate); entries={e.record_id:e for e in ix.entries}
    full=plan['request']['bench']['full_order']; changes=[]
    for n,carrier in enumerate(full,1):
        field=read_initial_order(entries[carrier].decode_payload(candidate))
        changes.append(dict(native_player_id=carrier,native_name=field.name,before=field.order,after=n))
    layer=dict(schema_version=ordering.SCHEMA,clubs=[dict(carrier_id=364,players=changes)])
    ordered=ordering.apply_layer(eq,candidate,layer,allow_compact=True)
    # Reuse exchange's exact fixed-capacity mode0 EQ tail writer for the same full order.
    from scripts.season_package_compiler_v2 import parse_eq_external_team_roster_payload
    ix_eq=IndexedFDIFile.from_bytes(eq); eqentry=next(e for e in ix_eq.entries if e.record_id==364)
    eqpayload=eq[eqentry.payload_offset:eqentry.payload_offset+eqentry.payload_length]
    parsed=parse_eq_external_team_roster_payload(eqpayload,{})
    if parsed is None or parsed.mode_byte!=0 or any(r.flag for r in parsed.rows) or {r.player_record_id for r in parsed.rows}!=set(full): raise ValueError('exact Walsall mode0 roster preimage required')
    patched_eq=delta.compiler._rebuild_indexed(eq,ix_eq,{364:xor_decode(delta.compiler._rewrite_roster_tail(eqpayload,full))})
    old={e.record_id:e for e in IndexedFDIFile.from_bytes(candidate).entries}
    new={e.record_id:e for e in IndexedFDIFile.from_bytes(ordered).entries}
    for carrier in full:
        exchange.verify_order_only_record(old[carrier].decode_payload(candidate),new[carrier].decode_payload(ordered))
    return ordered,patched_eq
