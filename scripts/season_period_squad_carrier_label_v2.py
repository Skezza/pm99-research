"""Restore original-carrier labels from complete authored annual cohorts.

This is NOT opening-XI certification. Reparse the dated annual, bind every
resident, and corroborate the retained original coach/ground independently.
V1's Soccerbase-specific opening contract remains untouched.
"""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from scripts import season_original_carrier_label_restoration_v1 as prior

registry,pipeline=prior.registry,prior.pipeline
SCHEMA='pm99-unanimous-raw-period-squad-original-carrier-label-v2'


def coach_alias(native,full):
    if not native or not full or (native!=full and not full.endswith(' '+native)):
        raise ValueError('retained coach needs a literal published full-name/surname alias, never initial expansion')


def dated_annual_title(path,season,group):
    if path.suffix!='.txt':raise ValueError('this typed annual policy requires a literal dated FootballSquads source, not an unreviewed HTML adapter')
    title=next((line for line in path.read_text().splitlines() if line.strip()),'')
    match=prior.old.roster.csv_source._TITLE.fullmatch(title)
    if match is None:raise ValueError('literal dated annual title missing')
    label=match.group(3);year=int(season[:4])
    if int(label[:4])!=year:raise ValueError('annual year differs from target start year; no ending-year substitution')
    calendar=group in prior.old.roster.ntf_source.CALENDAR_YEAR_COUNTRIES
    if calendar:
        if label!=str(year):raise ValueError('calendar-country label needs its literal target year, not a split-year surrogate')
    else:
        if '/' not in label:raise ValueError('split-year league requires a literal complete season title')
        end=label.split('/')[1]
        if int(end)!=(year+1 if len(end)==4 else (year+1)%100):raise ValueError('annual title has another ending season')
    return label


def ground(raw,review,target,native,year):
    if review['kind']=='wikipedia-closed-tenancy-v1':
        return prior.ground(raw,native,target,year)
    if (review['kind']!='official-Hertha-Olympiastadion-continuity-v1'
            or review['original']['url']!='https://www.herthabsc.com/de/club/olympiastadion'
            or target!='Hertha Berlin' or native!='Olympiastadion'):
        raise ValueError('unsupported typed ground evidence, not a name similarity guess')
    page=BeautifulSoup(raw,'lxml');text=' '.join(page.get_text(' ',strip=True).split())
    if ([h.get_text(' ',strip=True) for h in page.select('h1')]!=['Olympiastadion']
            or not all(s in text for s in ('Hertha BSC','seit 1963','1986 und 1988'))
            or year<1963 or 1986<=year<=1988):
        raise ValueError('official ground history does not cover target year or its explicit exceptions')
    return dict(from_year=1963,excluded_years=[1986,1987,1988],target_year=year,
        kind=review['kind'],exact_target_season_capacity_not_approved=True)


def prepare(base,inputs):
    pre=prior.checked(inputs['preallocation']);fixed_path=prior.checked(inputs['fixed_registry'])
    if fixed_path.resolve()!=(registry.ROOT/'seasons'/base.season/'fixed-carrier-registry.json').resolve():
        raise ValueError('requires this season original registry, not an arbitrary club mapping')
    fixed=pipeline.read_json_file(fixed_path)
    if fixed['schema_version']!='pm99-world-fixed-carrier-registry-v2':raise ValueError('unsupported original registry schema')
    specs=inputs['clubs']
    if not specs or len({r['carrier_id'] for r in specs})!=len(specs):raise ValueError('explicit distinct label carriers required')
    package=pipeline.read_json_file(base.package_path);aid='opening-squad-preallocation-'+base.season
    descriptor=next(a for a in package['artifacts'] if a['id']==aid)
    if registry.sha256_file(pre)!=descriptor['sha256']:raise ValueError('source cohort rows differ from current recipe artifact')
    index,sources=prior.old.indexed_claims(pipeline.read_json_file(pre))
    captures,_=prior.old.roster.load_sources(base.season)
    verifier=prior.old.roster.SourceVerifier(base.season)
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes();jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entries={e.record_id:e for e in prior.IndexedFDIFile.from_bytes(eq).entries}
    people={e.record_id:e for e in prior.IndexedFDIFile.from_bytes(jug).entries}
    owners=prior.owners.native_owners(eq)
    holders,names=prior.old._manager_graph(eq_path=base.game_path/'DBDAT/EQ98030.FDI',ent_path=base.game_path/'DBDAT/ENT98030.FDI')
    managers={m['id']:m for m in package['managers']};updates=[];witnesses=[]
    for spec in sorted(specs,key=lambda r:r['carrier_id']):
        carrier=spec['carrier_id'];club=next(c for c in package['clubs'] if c['carrier_id']==carrier)
        residents=[p for p in package['players'] if p['club_id']==club['id']]
        if {p['id'] for p in residents}!=set(club['roster_player_ids']):raise ValueError('authored cohort and declared roster differ')
        authored=prior.cohort_source(club,residents,aid,index,sources);target=authored['selector']['club_name']
        group=prior.old.roster.club_group(club)
        if prior.old.roster.club_names(group,target)&prior.old.roster.club_names(group,club['name']):
            raise ValueError('declared spelling alias does not justify renaming an existing club')
        original=next(c for c in fixed['carriers'] if c['carrier_id']==carrier)
        if (original['record_mode']!=1 or prior.old.builder._normalise_club_name(original['baseline_club']['name'])
                !=prior.old.builder._normalise_club_name(target)):
            raise ValueError('source club is not this original fixed carrier identity')
        if any(c['id']!=club['id'] and prior.old.roster.club_group(c)==group
                and prior.old.roster.club_names(group,c['name'])&prior.old.roster.club_names(group,target) for c in package['clubs']):
            raise ValueError('another represented target club requires paired identity adjudication')
        matched=[c for c in captures if prior.old.selector_key(c)==prior.old.selector_key(authored['selector'])]
        if len(matched)!=1:raise ValueError('one exact dated source-squad capture required')
        raw=verifier.verify(matched[0])
        if raw['status']!='raw-source-reparsed':raise ValueError('original target-season squad does not reparse')
        source_period=dated_annual_title(registry.ROOT/raw['local_path'],base.season,group)
        for p in residents:
            native=prior.old.roster.native_player(people[p['carrier_id']].decode_payload(jug),p['carrier_id'])
            if owners.get(p['carrier_id'])!={carrier} or prior.old.roster.normalise(native['name'])!=prior.old.roster.normalise(p['name']):
                raise ValueError('native person or exclusive club ownership differs')
        payload=entries[carrier].decode_payload(eq);short,full,_=prior.labels.prefix_parts(payload)
        marker=payload.find(bytes.fromhex('dd6361'));_,_,end=prior._read_eq_inline_string(payload,marker+4)
        native_ground=prior._read_eq_inline_string(payload,end)[0];manager=managers[club['manager_id']]
        if (short!=club['name'] or native_ground!=original['baseline_club']['ground_name']
                or manager['carrier_id']!=original['baseline_club']['active_manager_carrier_id']
                or names.get(manager['carrier_id'])!=manager['name']
                or [c['carrier_id'] for c in holders.get(manager['carrier_id'],[])]!=[carrier]):
            raise ValueError('current label/retained original ground/coach/exclusive owner differs')
        coach=spec['coach'];coach_alias(manager['name'],coach['published_full_name'])
        if not (prior.old.roster.club_names(group,target)&prior.old.roster.club_names(group,coach['published_club_name'])):
            link=coach.get('club_alias_original')
            if (not link or link['kind']!='UEFA-Hertha-Roeber-2002-departure-v1'
                    or link['original']['url']!='https://www.uefa.com/news-media/news/0182-0f8fa91fd1a5-7a9ecf722c9e-1000--early-hertha-release-for-rober/'
                    or target!='Hertha Berlin' or coach['published_club_name']!='Hertha BSC'
                    or coach['published_full_name']!='Jürgen Röber'):
                raise ValueError('coach source club lacks an explicit original target-club alias witness')
            linked_raw=prior.originals.publisher_original(link['original'])
            linked_text=' '.join(BeautifulSoup(linked_raw,'lxml').get_text(' ',strip=True).split())
            if (b'2002-02-06' not in linked_raw or not all(s in linked_text for s in ('Jürgen Röber','Hertha BSC Berlin','after six years in charge'))
                    or prior.old.builder._normalise_club_name(original['baseline_club']['full_name'])!='herthabscberlin'):
                raise ValueError('original UEFA club/coach/departure/full original name differs')
        if urlparse(coach['original']['url']).netloc!='en.wikipedia.org':raise ValueError('unsupported dated coach publisher')
        year=int(base.season[:4])
        coach_spell=prior.coach(prior.originals.publisher_original(coach['original']),coach['published_full_name'],coach['published_club_name'],year)
        ground_review=ground(prior.originals.publisher_original(spec['ground']['original']),spec['ground'],target,native_ground,year)
        updates.append(dict(club_id=club['id'],carrier_id=carrier,before=club['name'],before_full=club.get('full_name'),
            after=target,identity_after=prior.old.builder._source_club_identity_id(group,target),
            native_before=short,native_full_before=full,native_after=prior.labels.compiler._pm99_text(target,label='original annual source club')))
        witnesses.append(dict(carrier_id=carrier,represented_source_and_native_people=len(residents),
            source_selector=authored['selector'],raw_period_squad=raw,literal_period_title=source_period,retained_native_coach=manager['name'],
            published_full_coach=coach['published_full_name'],coach_spell=coach_spell,retained_ground=native_ground,
            ground_review=ground_review,complete_opening_XI_or_historical_kit_design_approved=False))
    return dict(schema_version=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI'),ent_sha256=registry.sha256_file(base.game_path/'DBDAT/ENT98030.FDI'),
        source_inputs=inputs,updates=updates,witnesses=witnesses,
        implementation_inputs=[prior.bind(Path(m.__file__)) for m in (prior,prior.old,prior.labels,prior.originals)]+[prior.bind(Path(__file__))],
        scope='Short/full original-carrier club labels and recipe identity/proof only. All represented native people, facts, skills, coaches, ground, capacity, rosters, tactics, assets and EXE preserved. Annual membership is NOT complete opening-XI or historical kit-design certification.')


def verify(base,plan):
    if plan.get('schema_version')!=SCHEMA or prepare(base,plan['source_inputs'])!=plan:
        raise ValueError('typed original period-squad club-label source/native plan does not reproduce')
