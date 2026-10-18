"""Positive raw cohort/dated-coach admission; no game or default mutations.

Unlike the frozen retained-coach label policy, this explicitly proves that
the old coach must change too. It must not certify an opening XI or kits.
"""
from datetime import date,datetime
from bs4 import BeautifulSoup
from scripts import season_period_squad_carrier_label_v2 as annual
from scripts.build_original_carrier_label_20261017 import external
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

prior=annual.prior
registry,pipeline=prior.registry,prior.pipeline
ROOT=registry.ROOT/'.local/consolidated-audit-20261009/hertha-dated-cohort-coach-20261017'


def dated_coach(raw,opening):
    page=BeautifulSoup(raw,'html.parser')
    if [h.get_text(' ',strip=True) for h in page.select('h1')]!=['List of Hertha BSC managers']:
        raise ValueError('manager history identifies another club')
    text=' '.join(page.get_text(' ',strip=True).split())
    if '10 March 2024' not in text or opening>date(2024,3,10):
        raise ValueError('target date exceeds the explicit history snapshot')
    tables=[]
    for table in page.select('table.wikitable'):
        heading=table.find_previous(['h2','h3'])
        if heading is None or heading.get_text(' ',strip=True)!='Tenure, wins, draws, losses and winning percentage':
            continue
        first=table.find('tr')
        if first and [c.get_text(' ',strip=True) for c in first.find_all(['th','td'],recursive=False)][:4]==['No.','Coach','From','To']:
            tables.append(table)
    if len(tables)!=1:raise ValueError('one literal dated coach chronology required')
    hits=[];invalid=[]
    for tr in tables[0].select('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['th','td'],recursive=False)]
        if len(cells)<4:continue
        try:
            start=datetime.strptime(cells[2],'%d %B %Y').date()
            end=datetime.strptime(cells[3],'%d %B %Y').date()
        except ValueError:continue
        if end<=start:
            invalid.append(cells[:4]);continue
        if start<=opening<end:
            hits.append(dict(name=cells[1],from_date=start.isoformat(),to_date=end.isoformat()))
    if len(hits)!=1:raise ValueError('no unique closed coach spell covers opening date')
    return dict(**hits[0],target_date=opening.isoformat(),ignored_invalid_historical_rows=invalid)


def stevens_originals(season):
    history=external('hertha-original-coach-list-asof2024')
    decision=dated_coach(prior.originals.publisher_original(history),date(int(season[:4]),8,1))
    if decision['name']!='Huub Stevens' or (decision['from_date'],decision['to_date'])!=('2002-07-01','2003-12-04'):
        raise ValueError('this typed corroboration covers only the closed Stevens spell')
    official=external('hertha-stevens-official-2002-2003-season-tenure')
    entry=external('hertha-stevens-2002-entry-uefa-original')
    exit=external('hertha-stevens-2003-exit-uefa-original')
    urls=[history['url'],official['url'],entry['url'],exit['url']]
    if urls!=[
        'https://en.wikipedia.org/wiki/List_of_Hertha_BSC_managers',
        'https://www.herthabsc.com/de/nachrichten/2014/11/6684-alles-gute-huub-und-dick',
        'https://www.uefa.com/news-media/news/025e-0f905aff01eb-2e838908ff54-1000--stevens-seals-hertha-switch/',
        'https://www.uefa.com/news-media/news/0198-0e6a7363167a-c0952ba4b73f-1000--thom-replaces-sacked-stevens/']:
        raise ValueError('dated manager original publisher URLs differ')
    for binding,phrases in [(official,('Huub Stevens übernahm Hertha BSC zur Saison 2002/03','am 4. Dezember 2003 beendet')),
            (entry,('Huub Stevens will take over as Hertha BSC Berlin coach in the summer.','January 10, 2002')),
            (exit,('Hertha BSC Berlin have sacked coach Huub Stevens','December 4, 2003'))]:
        text=' '.join(BeautifulSoup(prior.originals.publisher_original(binding),'html.parser').get_text(' ',strip=True).split())
        if not all(s in text for s in phrases):raise ValueError('literal primary coach tenure corroboration differs')
    return dict(decision=decision,originals=[history,official,entry,exit],
        exact_opening_XI_approved=False,current_manager_used=False)


def admit(base):
    if base.season not in ('2002-03','2003-04'):raise ValueError('explicit confirmed two-season scope required')
    coach=stevens_originals(base.season)
    package=pipeline.read_json_file(base.package_path)
    club=next(c for c in package['clubs'] if c['carrier_id']==421)
    people=[p for p in package['players'] if p['club_id']==club['id']]
    if {p['id'] for p in people}!=set(club['roster_player_ids']):raise ValueError('declared cohort and roster differ')
    aid='opening-squad-preallocation-'+base.season
    pre=registry.ROOT/'.local/transfermarkt-opening-plans-current-v1'/base.season/'opening-squad-preallocation.json'
    if next(a for a in package['artifacts'] if a['id']==aid)['sha256']!=registry.sha256_file(pre):
        raise ValueError('source cohort artifact no longer binds original preallocation')
    index,sources=prior.old.indexed_claims(pipeline.read_json_file(pre))
    authored=prior.cohort_source(club,people,aid,index,sources)
    if authored['selector']['club_name']!='Hertha Berlin':raise ValueError('full original cohort is not Hertha')
    captures,_=prior.old.roster.load_sources(base.season)
    matched=[c for c in captures if prior.old.selector_key(c)==prior.old.selector_key(authored['selector'])]
    if len(matched)!=1:raise ValueError('one original annual capture required')
    raw=prior.old.roster.SourceVerifier(base.season).verify(matched[0])
    if raw['status']!='raw-source-reparsed':raise ValueError('original annual no longer reparses')
    annual.dated_annual_title(registry.ROOT/raw['local_path'],base.season,prior.old.roster.club_group(club))
    fixed_path=registry.ROOT/'seasons'/base.season/'fixed-carrier-registry.json'
    fixed=pipeline.read_json_file(fixed_path)
    if fixed['schema_version']!='pm99-world-fixed-carrier-registry-v2':raise ValueError('original registry schema differs')
    original=next(c for c in fixed['carriers'] if c['carrier_id']==421)
    if original['record_mode']!=1 or prior.old.builder._normalise_club_name(original['baseline_club']['name'])!='herthaberlin':
        raise ValueError('source identity is not original fixed carrier')
    group=prior.old.roster.club_group(club)
    if any(c['id']!=club['id'] and prior.old.roster.club_group(c)==group and
           prior.old.roster.club_names(group,c['name'])&prior.old.roster.club_names(group,'Hertha Berlin') for c in package['clubs']):
        raise ValueError('another target club requires paired carrier adjudication')
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    entries={e.record_id:e for e in prior.IndexedFDIFile.from_bytes(jug).entries}
    owners=prior.owners.native_owners(eq)
    for person in people:
        native=prior.old.roster.native_player(entries[person['carrier_id']].decode_payload(jug),person['carrier_id'])
        if owners.get(person['carrier_id'])!={421} or prior.old.roster.normalise(native['name'])!=prior.old.roster.normalise(person['name']):
            raise ValueError('native cohort name/exclusive owner differs')
    entry=next(e for e in prior.IndexedFDIFile.from_bytes(eq).entries if e.record_id==421)
    payload=entry.decode_payload(eq);short,full,_=prior.labels.prefix_parts(payload)
    marker=payload.find(bytes.fromhex('dd6361'));_,_,end=prior._read_eq_inline_string(payload,marker+4)
    ground=prior._read_eq_inline_string(payload,end)[0]
    holders,names=prior.old._manager_graph(eq_path=base.game_path/'DBDAT/EQ98030.FDI',ent_path=base.game_path/'DBDAT/ENT98030.FDI')
    manager=next(m for m in package['managers'] if m['id']==club['manager_id'])
    if (short!=club['name'] or manager['carrier_id']!=1313 or names.get(1313)!='Röber' or manager['name']!='Röber'
            or original['baseline_club']['active_manager_carrier_id']!=1313
            or [c['carrier_id'] for c in holders.get(1313,[])]!=[421]
            or ground!=original['baseline_club']['ground_name']):
        raise ValueError('native label/original coach/ground or exclusive owner differs')
    for other in package['managers']:
        if other['id']!=manager['id'] and prior.old._normalise(other['name']) in ('stevens','huubstevens'):
            raise ValueError('Stevens already represented at another manager slot; resolve dated ownership first')
    ground_input=dict(kind='official-Hertha-Olympiastadion-continuity-v1',original=external('hertha2000-official-stadium-history'))
    ground_proof=annual.ground(prior.originals.publisher_original(ground_input['original']),ground_input,'Hertha Berlin',ground,int(base.season[:4]))
    return dict(season=base.season,release_id=base.release_id,package=prior.bind(base.package_path),
        jug=prior.bind(base.game_path/'DBDAT/JUG98030.FDI'),eq=prior.bind(base.game_path/'DBDAT/EQ98030.FDI'),
        ent=prior.bind(base.game_path/'DBDAT/ENT98030.FDI'),preallocation=prior.bind(pre),fixed_registry=prior.bind(fixed_path),
        club_id=club['id'],club_carrier_id=421,before_short=short,before_full=full,after_club='Hertha Berlin',
        manager=manager,native_before_manager=names[1313],published_full_coach='Huub Stevens',native_after_manager='Stevens',
        represented_source_and_native_people=len(people),raw_period_squad=raw,source_selector=authored['selector'],
        dated_coach=coach,ground_input=ground_input,ground_proof=ground_proof,
        correction_required='coupled-club-label-and-dated-coach-not-retained-coach-label-only',
        opening_XI_or_kits_approved=False,game_or_recipe_or_default_mutated=False)


if __name__=='__main__':
    for season in ('2002-03','2003-04'):
        result=admit(registry.load_preferred_release(season))
        (ROOT/season).mkdir(parents=True,exist_ok=True)
        retained(ROOT/season/'source-admission.json',result)
        print(dict(season=season,cohort_and_dated_coach_admitted=True,game_mutations=0),flush=True)
