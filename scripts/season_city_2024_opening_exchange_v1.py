"""Atomic six-slot City/Barcelona/Palmeiras/Lens opening correction.

Keep native carrier families in their original playable/non-playable lanes.
Reassign three existing identities without creating another represented copy;
only three wrong reserve identities at their destination clubs are retired.
Every preimage, original source and the full source reconstruction is checked.
"""
import copy
from datetime import date
import hashlib
import re

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages, season_duplicate_ownership_delta_v1 as delta
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import savio_bobb_2024_original_alias_v1 as reports
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA='pm99-original-City2024-atomic-opening-identity-exchange-v1'
PREFIX='sourced-city2024-opening-exchange-'
FILENAME='sourced-city2024-opening-exchange.json'
MODE='known-good-baseline-source-bound-City2024-atomic-opening-exchange'
PERSON_POLICY='original-City2024-August-primary-member-literal-Wikipedia-DOB-v1'
# Current City carrier, destination carrier, destination club, new City member.
SWAPS=((9244,16,1,'Kyle Walker'),(9245,8564,2802,"Nico O'Reilly"),
       (9250,19441,504,'Josh Wilson-Esbrand'))
SOURCES={
 'city-opening-gundogan-barcelona-arrival':'https://www.fcbarcelona.com/en/football/first-team/news/3552719/fcilkay-gundogan-joins-fc-barcelona/featured',
 'city-opening-gundogan-barcelona-departure':'https://www.fcbarcelona.com/en/news/4091996/agreement-with-manchester-city-for-transfer-of-gundoan',
 'city-opening-reis-palmeiras-departure':'https://www.palmeiras.com.br/noticias/cria-da-academia-vitor-reis-se-despede-do-palmeiras-minha-segunda-familia/',
 'city-opening-khusanov-lens-arrival':'https://www.rclens.fr/fr/news/mercato-rclens-arrivee-abdukodir-khusanov-20230724',
 'city-opening-khusanov-wikipedia':'https://en.wikipedia.org/wiki/Abdukodir_Khusanov',
 'city-opening-khusanov-pl-arrival':'https://www.premierleague.com/news/3960097',
 'city-opening-micael-palmeiras-arrival':'https://www.palmeiras.com.br/noticias/palmeirense-desde-a-infancia-zagueiro-micael-reforca-o-verdao-sempre-quis-jogar-aqui/',
 'city-opening-celik-lens-arrival':'https://www.rclens.fr/fr/news/mercato-nidal-celik-rclens-20250203',
 'city-opening-walker-wikipedia':'https://en.wikipedia.org/wiki/Kyle_Walker',
 'city-opening-oreilly-wikipedia':"https://en.wikipedia.org/wiki/Nico_O%27Reilly",
 'city-opening-wilson-esbrand-wikipedia':'https://en.wikipedia.org/wiki/Josh_Wilson-Esbrand',
}


def digest(data):return hashlib.sha256(data).hexdigest()


def original(key,proofs):
    path,raw,binding=source_rows(key)
    receipt=path.with_suffix('.source.json');doc=pipeline.read_json_file(receipt)
    if doc['url']!=SOURCES[key]:raise ValueError('opening exchange original URL differs')
    proofs.append(dict(binding,url=doc['url'],receipt_path=registry.relative_workspace_path(receipt),
        receipt_sha256=registry.sha256_file(receipt)))
    return BeautifulSoup(raw,'lxml'),raw


def require_text(page,*anchors):
    text=' '.join(page.get_text(' ',strip=True).split())
    if any(' '.join(a.split()) not in text for a in anchors):
        raise ValueError('opening exchange original lacks its positive historical anchors')
    return text


def biography(key,name,birthday,position,proofs):
    page,raw=original(key,proofs)
    if [h.get_text(' ',strip=True) for h in page.select('h1')]!=[name]:
        raise ValueError('opening member original full heading differs')
    boxes=page.select('table.infobox')
    if len(boxes)!=1 or [b.get_text(strip=True) for b in boxes[0].select('.bday')]!=[birthday]:
        raise ValueError('opening member original literal DOB differs')
    # Football nationality is from dated England representation, not birthplace
    # or today's passport/current club. All three have explicit pre-2024 caps.
    text=boxes[0].get_text(' ',strip=True)
    if 'International career' not in text or not re.search(r'(?:201[0-9]|202[0-3]).{0,25}England',text):
        raise ValueError('opening member lacks positive pre-season England representation')
    slug=SOURCES[key].split('/wiki/')[1]
    person=dict(name=name,birth_date=birthday,source_player_id='wikipedia:'+slug,
        source_provider='wikipedia',source_profile_url=SOURCES[key],identity_policy=PERSON_POLICY)
    source=dict(name=name,birth_date=birthday,position=position,nationality='ENG',
        height_cm=None,weight_kg=None,shirt_number=None)
    # Heights/weights from today's pages are NOT treated as period facts.
    return dict(source_person=person,source_player=source,
        raw_evidence=dict(status='raw-source-reparsed',local_path=proofs[-1]['path'],
            source_sha256=proofs[-1]['sha256']),
        membership='positive-original-August-first-league-bench-or-friendly-XI')


def sources():
    proofs=[]
    page,_=original('city-opening-gundogan-barcelona-arrival',proofs)
    require_text(page,'26 Jun 23','FC Barcelona and Ilkay Gündoğan have reached an agreement',
        'through to 30 June 2025')
    page,_=original('city-opening-gundogan-barcelona-departure',proofs)
    require_text(page,'23 Aug 24','FC Barcelona and Manchester City have reached an agreement',
        'Gündoğan arrived at the club from Manchester City in the summer of 2023')
    page,_=original('city-opening-reis-palmeiras-departure',proofs)
    require_text(page,'21 de janeiro de 2025','Vitor Reis está de saída do Palmeiras',
        'clube que defende desde 2016','Manchester City')
    page,raw=original('city-opening-khusanov-wikipedia',proofs)
    if [h.get_text(' ',strip=True) for h in page.select('h1')]!=['Abdukodir Khusanov'] or [b.get_text(strip=True) for b in page.select('table.infobox .bday')]!=['2004-02-29']:
        raise ValueError('Khusanov opening identity differs')
    # His Lens B appearances overlap the first-team career. Do not weaken the
    # generic unique-owner policy: this transaction has primary Lens evidence.
    require_text(page,'2023–2025 Lens','2024 Lens B')
    require_text(page,'On 20 January 2025')
    page,_=original('city-opening-khusanov-lens-arrival',proofs)
    require_text(page,'24/07/2023','Abdukodir Khusanov','29 février 2004','jusqu’en 2027')
    page,_=original('city-opening-khusanov-pl-arrival',proofs)
    require_text(page,'24 Jan 2025','Manchester City signing Abdukodir Khusanov')
    page,_=original('city-opening-micael-palmeiras-arrival',proofs)
    require_text(page,'22 de fevereiro de 2025','contratação do zagueiro Micael',
        'Houston Dynamo','Em abril de 2022')
    page,_=original('city-opening-celik-lens-arrival',proofs)
    require_text(page,'03/02/2025','Nidal Celik','en provenance du FK Sarajevo')
    replacements={
        'Kyle Walker':biography('city-opening-walker-wikipedia','Kyle Walker','1990-05-28','D',proofs),
        "Nico O'Reilly":biography('city-opening-oreilly-wikipedia',"Nico O'Reilly",'2005-03-21','M',proofs),
        'Josh Wilson-Esbrand':biography('city-opening-wilson-esbrand-wikipedia','Josh Wilson-Esbrand','2002-12-26','D',proofs)}
    for key,opening in (('savio-alias-primary-opening-Chelsea2024',True),
                        ('oscar-bobb-primary-August3-2024-friendly',False)):
        raw=reports.original(key,proofs);reports.report(raw,opening=opening)
        require_text(BeautifulSoup(raw,'lxml'),
            "Unused substitutes : Ortega Moreno, Walker, Stones, Ake, Grealish, Nunes, O'Reilly, McAtee"
            if opening else "Manchester City starting XI: Ortega, Lewis, Phillips, Gvardiol, Wilson-Esbrand, Kovacic, O'Reilly, Bobb, McAtee, Grealish, Haaland")
    return replacements,proofs


def verify_person(person):
    replacements,_=sources()
    expected=replacements.get(person.get('name'),{}).get('source_person')
    if expected!=person:raise ValueError('City August member identity/source does not reproduce')
    return 'person-wikipedia-'+digest((person['source_player_id']+'|'+person['birth_date']).encode())[:24]


def native_rows(eq,carrier):
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    ix=IndexedFDIFile.from_bytes(eq);entry=next(e for e in ix.entries if e.record_id==carrier)
    raw=eq[entry.payload_offset:entry.payload_offset+entry.payload_length]
    parsed=parse_eq_external_team_roster_payload(raw,{})
    if parsed is None or any(r.flag for r in parsed.rows):raise ValueError('opening exchange needs visible native roster')
    return ix,raw,parsed


def prepare(release):
    if release.season!='2024-25':raise ValueError('original City opening policy is 2024 only')
    replacement,proofs=sources()
    package=pipeline.read_json_file(release.package_path)
    players={p['carrier_id']:p for p in package['players']}
    clubs={c['carrier_id']:c for c in package['clubs']}
    if {c:clubs[c]['name'] for c in (313,1,2802,504)}!={313:'Manchester City',1:'Barcelona',2802:'Palmeiras',504:'Lens'}:
        raise ValueError('opening exchange club identities changed')
    jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    from scripts import season_opening_order_repair_v1 as ownership
    owners=ownership.native_owners(eq)
    expected={9244:('ilkaygundogan','1990-10-24'),9245:('vitorreis','2006-01-12'),
        9250:('abdukodirkhusanov','2004-02-29'),16:('luisenriquemartinezgarcia','1970-05-08'),
        8564:('16micael','2000-08-12'),19441:('nidalcelik','2006-07-17')}
    for carrier,(name,birthday) in expected.items():
        current=facts.native_facts(jug,carrier);p=players[carrier]
        if (roster.normalise(p.get('source_name') or p['name']),current['birth_date'])!=(name,birthday):
            raise ValueError('opening exchange exact displaced/retained identity changed')
        if current['startup_order']<=11:raise ValueError('opening exchange cannot change a starter')
    # The old Luis Enrique slot is explicitly an untouched whole-record factory
    # fallback, not a sourced 2024 identity to retire on a name/age guess.
    if players[16].get('policy')!='preserve-existing-mode1':raise ValueError('retired Barcelona carrier is no longer whole-record fallback')
    for name,row in replacement.items():
        if any(roster.normalise(p.get('source_name') or p['name'])==roster.normalise(name) for p in package['players']):
            raise ValueError('new City opening member already represented elsewhere')
    rows=[]
    for city,destination,club,name in SWAPS:
        old,new=players[city],players[destination]
        if (old['club_id'],new['club_id'])!=(clubs[313]['id'],clubs[club]['id']) or owners.get(city)!={313} or owners.get(destination)!={club}:
            raise ValueError('opening exchange source ownership is not exclusive')
        rows.append(dict(city_carrier=city,destination_carrier=destination,destination_club=club,
            moved_before=old,retired_before=new,replacement=replacement[name],
            city_order=facts.native_facts(jug,city)['startup_order'],
            destination_order=facts.native_facts(jug,destination)['startup_order']))
    from scripts import season_same_carrier_name_capacity_v1 as capacity
    from scripts import season_stevenage_opening_repair_v1 as core
    bundle=pipeline.read_json_file(core.CAPACITY_PROOF)['bindings']['same_carrier_name_capacity']
    _,claim=capacity.recover_slot(jug,19441,bundle)
    return dict(schema=SCHEMA,season=release.season,release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),jug_sha256=digest(jug),eq_sha256=digest(eq),
        source_proofs=proofs,exchanges=rows,before_clubs=[clubs[k] for k in (1,313,504,2802)],
        same_carrier_capacity=dict(bundle=bundle,claim=claim),
        opening_anchor='2024-08-01',positive_City_dates=['2024-08-03','2024-08-18'],
        scope='Six player identities and four fixed-size club roster rows only. Every starter/order/tactic, manager, kit and unrelated person unchanged. Moved people retain their prior ten skills/facts. New City reserves use deterministic editorial ratings; unsourced secondary facts and blank photos explicit.')


def verify(release,plan):
    if plan.get('schema')!=SCHEMA or prepare(release)!=plan:
        raise ValueError('opening exchange source/preimage does not independently reproduce')


def bind(package,plan):
    if digest(packages.canonical_json_bytes(package))!=plan['package_sha256']:
        # Package files include a newline, unlike the canonical artifact digest.
        baseline=registry.load_registered_release(plan['season'],plan['release_id'])
        if pipeline.read_json_file(baseline.package_path)!=package or registry.sha256_file(baseline.package_path)!=plan['package_sha256']:
            raise ValueError('opening exchange recipe preimage differs')
    result=copy.deepcopy(package);by={p['carrier_id']:p for p in result['players']}
    # Stage the target-owned reserve rows for the existing facts/rating writer.
    # Keep IDs/families anchored to each native slot; no layout conversion.
    updates=[]
    for row in plan['exchanges']:
        city,dest=row['city_carrier'],row['destination_carrier']
        moved=copy.deepcopy(row['moved_before']);retired=by[dest]
        keep={k:retired[k] for k in ('id','carrier_id','carrier_family','club_id')}
        retired.clear();retired.update(moved);retired.update(keep)
        retired['facts']['shirt_number']={'policy':'preserve-existing-mode1'}
        retired['fact_fallbacks']=[f for f in retired.get('fact_fallbacks',[]) if f['field']!='shirt_number']
        retired['fact_fallbacks'].append(dict(field='shirt_number',method='preserve-existing-mode1',
            proof=copy.deepcopy(moved['proof']),
            value={'policy':'preserve-existing-mode1'},reason='Foreign shirt-number storage is unproven; preserve destination carrier byte, not a historical claim.'))
        retired['fact_fallbacks'].sort(key=lambda f:f['field'])
        replacement=row['replacement']
        updates.append(dict(layer='main',player_id=by[city]['id'],carrier_id=city,
            club_id=by[city]['club_id'],before=copy.deepcopy(by[city]),replacement=replacement,
            replacement_opening_evidence=dict(date='2024-08-18')))
    composition=dict(season=plan['season'],bindings=dict(snapshot=dict(project_url='https://www.chelseafc.com/')),
        updates=updates,source_title='Original August City bench/friendly plus independently dated opening club ownership',
        proof_covers=['three-atomic-opening-owner-corrections; three-positive-August-City-members; NOT-global-historical-approval'])
    result=delta.updated_package(result,composition)
    old_artifact=next(a for a in result['artifacts'] if a.get('relative_path')==delta.plan_filename(composition))
    old_id=old_artifact['id'];aid=PREFIX+plan['season'];old_artifact.update(id=aid,relative_path=FILENAME,sha256=digest(packages.canonical_json_bytes(plan)))
    for row in result['players']:
        if row['carrier_id'] in {r['destination_carrier'] for r in plan['exchanges']}:
            row['proof']=dict(artifact_id=aid,grade='source-receipt')
            next(f for f in row['fact_fallbacks'] if f['field']=='shirt_number')['proof']=dict(row['proof'])
        if row.get('proof',{}).get('artifact_id')==old_id:row['proof']['artifact_id']=aid
        for fallback in row.get('fact_fallbacks',[]):
            if fallback.get('proof',{}).get('artifact_id')==old_id:fallback['proof']['artifact_id']=aid
    for collection in ('sources','proofs'):
        for row in result[collection]:
            for key in ('artifact_id','evidence_artifact_id'):
                if row.get(key)==old_id:row[key]=aid
    selected={r[k] for r in plan['exchanges'] for k in ('city_carrier','destination_carrier')}
    ids={p['id'] for p in result['players'] if p['carrier_id'] in selected}
    portraits=result['assets']['portraits'];portraits[:]=[p for p in portraits if p['player_id'] not in ids]
    portraits.extend(dict(player_id=id,status='native-no-photo',proof=dict(artifact_id=aid,grade='source-receipt'),
        review_reason='Atomic identity reassignment: old slot photo cleared; portrait not claimed sourced for this new slot.') for id in sorted(ids))
    portraits.sort(key=lambda p:p['player_id'])
    # Correct the declared bench to the original first-league report, not a
    # later whole-season list containing Rodri (absent from this match bench).
    city=next(c for c in result['clubs'] if c['carrier_id']==313)
    people={p['carrier_id']:p for p in result['players']}
    city['opening']['substitute_player_ids']=[people[k]['id'] for k in (9241,9243,9244,9237,9238,9240,9247,9245,9239)]
    city['opening']['proof']=dict(artifact_id=aid,grade='source-receipt')
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    baseline=registry.load_registered_release(plan['season'],plan['release_id'])
    original=(baseline.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    original_eq=(baseline.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if (digest(original),digest(original_eq))!=(plan['jug_sha256'],plan['eq_sha256']):raise ValueError('opening exchange immutable native source changed')
    package=bind(pipeline.read_json_file(baseline.package_path),plan)
    selected={p['id'] for p in package['players'] if p['carrier_id'] in {r[k] for r in plan['exchanges'] for k in ('city_carrier','destination_carrier')}}
    countries=delta.compiler._extract_country_codes_from_textos(baseline.game_path/'DBDAT/TEXTOS.PKF')
    from scripts import season_same_carrier_name_capacity_v1 as capacity
    prepared,claim=capacity.recover_slot(original,19441,plan['same_carrier_capacity']['bundle'])
    if claim!=plan['same_carrier_capacity']['claim']:raise ValueError('City Lens name-window recovery does not reproduce')
    candidate=delta.compile_players(prepared,package,selected,countries)
    # Allocation never changes: City stays at9244/9245/9250; destination clubs
    # stay at16/8564/19441. Thus all six startup bytes and all four EQ records
    # must remain EXACT. This also avoids mixing compact/full playable layouts.
    if eq!=original_eq or jug not in (original,candidate):raise ValueError('opening exchange accepts only exact complete pre/postimages')
    preserve_other_records(original,candidate,{r[k] for r in plan['exchanges'] for k in ('city_carrier','destination_carrier')})
    return candidate,original_eq


def filename(plan):return FILENAME


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('atomic City ownership recipe requires exact source-bound reconstruction')


def reconstruction(previous,release_id):
    from scripts import publish_historical_role_delta_v1 as publisher
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    baseline=registry.load_registered_release(previous.season,plan['release_id']);verify(baseline,plan)
    package=pipeline.read_json_file(previous.package_path)
    artifacts=[a for a in package['artifacts'] if a['id']==PREFIX+previous.season]
    if len(artifacts)!=1 or path.resolve()!=(previous.package_path.parent/FILENAME).resolve() or registry.sha256_file(path)!=artifacts[0]['sha256']:
        raise ValueError('atomic City source replay artifact changed')
    if bind(pipeline.read_json_file(baseline.package_path),plan)!=package:raise ValueError('edited City recipe cannot be silently reconstructed')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    expected=dict(season=previous.season,release_id=baseline.release_id,
        package_sha256=registry.sha256_file(baseline.package_path),
        jug_sha256=registry.sha256_file(baseline.game_path/'DBDAT/JUG98030.FDI'),updates=[],unresolved=[])
    if pipeline.read_json_file(descriptor)!=expected:raise ValueError('City replay descriptor differs')
    for release in (baseline,previous):
        pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season,previous.package_path.parent/'role-delta-input.json',
        release_id=release_id,profile_assignment_plan_path=path,source_release_id=baseline.release_id)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=package:raise ValueError('complete City recipe replay differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,
        complete_recipe_identical=True,reused=False,compilation_mode=MODE)
