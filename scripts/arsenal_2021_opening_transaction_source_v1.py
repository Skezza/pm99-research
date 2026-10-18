"""Independently replay Arsenal25 and four positive paired replacement actors.

No native writes. Club membership is from exact numeric first fixtures or the
original Genoa sheet, never from the other-club annual used for facts.
"""
import copy
import re
from bs4 import BeautifulSoup
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_historical_transfer_review_v1 as identities
from scripts import season_published_person_identity_v1 as people_source
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import prepare_arsenal_opening25_20261016 as arsenal
from scripts import capture_arsenal_coupled_primary_sources_20261016 as primary
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.backfill_exact_opening_club_aliases_v1 import unique_capture

KEY='Arsenal2021-original-opening25-four-paired-reserves'
PAIR_ACTORS=((9080,308,665390),(21228,220,617170),(14650,207,525704),(30550,802,595238))


def bound(path):return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))


def grid(raw,club_id,formation,expected):
    page=BeautifulSoup(raw,'html.parser')
    def same(box):
        ids={int(m[1]) for a in box.select('a[href]')
            if (m:=re.search(r'/startseite/verein/(\d+)(?:/|$)',a['href']))}
        return ids=={club_id}
    boxes=[b for b in page.select('.aufstellung-box') if same(b)]
    if not boxes:boxes=[b for b in page.select('.large-6') if same(b)]
    if len(boxes)!=1:raise ValueError('formation grid requires one exact numeric source-club side')
    box=boxes[0];heading=box.select_one('.formation-subtitle')
    if heading is None or heading.get_text(' ',strip=True)!='Starting Line-up: '+formation:
        raise ValueError('published formation differs')
    rows=[]
    for node in box.select('.formation-player-container'):
        a=node.select_one('a[href*="/profil/spieler/"]')
        if a is None:continue
        id=re.search(r'/profil/spieler/([1-9][0-9]*)(?:/|$)',a['href'])
        coordinates={k:float(v) for k,v in re.findall(r'(top|left):\s*([0-9]+(?:\.[0-9]+)?)%',node.get('style',''))}
        if id is None or set(coordinates)!={'top','left'} or any(not 0<=v<=100 for v in coordinates.values()):
            raise ValueError('source grid has missing/unsupported explicit percentages')
        rows.append(dict(source_player_id=int(id[1]),**coordinates))
    if len(rows)!=11 or {r['source_player_id'] for r in rows}!=set(expected):
        raise ValueError('source grid is not the exact original eleven')
    ordered=sorted(rows,key=lambda r:(-r['top'],-r['left']))
    result=[];cursor=0
    # TM faces upward; PM99 faces downward. Right-side players therefore
    # sort by descending source-left within each published formation band.
    for count in [1,*map(int,formation.split('-'))]:
        band=ordered[cursor:cursor+count]
        if len(band)!=count or len({r['left'] for r in band})!=count:
            raise ValueError('source formation band is incomplete or laterally ambiguous')
        if cursor+count<11 and min(r['top'] for r in band)<=ordered[cursor+count]['top']:
            raise ValueError('source formation bands overlap at the boundary')
        result.extend(sorted(band,key=lambda r:-r['left']));cursor+=count
    return result


def published_index():
    people,_=people_source.merge({},pipeline.read_json_file(arsenal.PUBLIC))
    extra=arsenal.ROOT/'geusens-original-person-identity.json'
    people,_=people_source.merge(people,pipeline.read_json_file(extra))
    by={id:p for rows in people.values() for id,p in rows.items()}
    aliases={id:set() for id in by}
    for (name,_),rows in people.items():
        for id in rows:aliases[id].add(name)
    return people,by,aliases


def philogene(person,captures,verifier):
    _,raw,biography=source_rows('arsenal-paired-Philogene-original-full-birth-name-20261016')
    box=BeautifulSoup(raw,'html.parser').select_one('table.infobox')
    if (box is None or [b.get_text(strip=True) for b in box.select('.bday')]!=[person['birth_date']]
        or person['birth_date']!='2002-02-08'
        or 'jadenrichardphilogenebidace' not in roster.normalise(box.get_text(' ',strip=True))):
        raise ValueError('Philogene full birth-name/DOB alias bridge does not reproduce')
    rows=[]
    for capture in captures:
        for row in capture['players']:
            if (row['name'],row.get('birth_date'))==('Jaden Philogene-Bidace','2002-05-18'):
                proof=verifier.verify(capture)
                if proof['status']=='raw-source-reparsed':rows.append((row,proof))
    if len(rows)!=1:raise ValueError('one literal wrong-date period Philogene row required')
    row,proof=rows[0];row=copy.deepcopy(row)
    if row['position']!='M':raise ValueError('period broad Philogene role differs')
    row.update(birth_date=person['birth_date'],shirt_number=None)
    return row,dict(policy='explicit-full-birth-name-bridge-and-confirmed-original-person-DOB',
        period_raw_evidence=proof,original_biography=biography,
        annual_birth_date='2002-05-18',confirmed_birth_date=person['birth_date'],
        other_club_membership_or_shirt_number_not_used=True)


def admission(base):
    if base.season!='2021-22':raise ValueError('this original source package is2021 only')
    # Recompute, then compare the immutable source package. No network fetch
    # occurs and no finished game is regenerated.
    arsenal.main()
    source_path=arsenal.ROOT/'source-package.json';source=pipeline.read_json_file(source_path)
    package=pipeline.read_json_file(base.package_path)
    club=next(c for c in package['clubs'] if c['carrier_id']==309)
    if club['name']!='Arsenal':raise ValueError('native target label differs')
    players={p['carrier_id']:p for p in package['players']};clubs={c['carrier_id']:c for c in package['clubs']}
    people,by,aliases=published_index()
    report_path=registry.ROOT/'.local/duplicate-ownership-v3/exact-side-opening-source-repairs-r4/opening/2021-22/opening-review.json'
    report=pipeline.read_json_file(report_path)
    capture_path=registry.ROOT/report['bindings']['opening_capture_path']
    if registry.sha256_file(capture_path)!=report['bindings']['opening_capture_sha256']:
        raise ValueError('paired opening capture changed')
    capture=pipeline.read_json_file(capture_path)
    raw,raw_proof=opening.verified_page(capture_path.parent/'cache',capture['source']['cache_files'],
        'https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/3583476')
    desired=copy.deepcopy(source['desired_people'])
    ids=[r['source_person']['source_player_id'] for r in desired[:11]]
    coordinates=grid(raw,11,source['formation'],ids)
    by_desired={r['source_person']['source_player_id']:r for r in desired}
    desired=[by_desired[r['source_player_id']] for r in coordinates]+desired[11:]
    all_captures,_=roster.load_sources('2021-22');verifier=roster.SourceVerifier('2021-22')
    paired=[]
    for carrier,cid,id in PAIR_ACTORS:
        current=players[carrier];target=clubs[cid]
        if current['club_id']!=target['id']:raise ValueError('paired current owner changed')
        # Source current outside actor belongs in the independently sourced
        # Arsenal25. All later absence/collision checks are global.
        moved=identities.unique_person(current,people)
        if moved is None or moved['source_player_id'] not in by_desired:
            raise ValueError('paired displaced player does not identify one sourced Arsenal actor')
        if cid==207:
            _,primary_raw,primary_binding=source_rows('genoa-2021-primary-opening-Inter20261016-v2')
            original=primary.genoa(primary_raw)
            if not any(r['published_match_name']=='Rovella' and r['shirt_number']==65 for r in original['starting_xi']):
                raise ValueError('Genoa source lacks the positive original Rovella member')
            evidence=dict(original=original,raw_source=primary_binding,source_player_id=id,
                independent_identity=by[id])
        else:
            captured=unique_capture(target,capture['clubs'])
            if captured is None:raise ValueError('paired club has no unique captured numerical identity')
            evidence=opening.verify_opening(captured,capture,capture_path.parent/'cache')
            if evidence['date'][:4]!='2021' or str(id) not in evidence['substitutes']:
                raise ValueError('replacement is not on the actual target-year opening bench')
        if id==665390:row,fact_origin=philogene(by[id],all_captures,verifier)
        else:row,fact_origin=arsenal.other_period_facts(by[id],aliases[id],all_captures,verifier)
        replacement=dict(source_person=by[id],source_player=row,membership='positive-original-opening-member',
            raw_evidence=fact_origin,opening_evidence=evidence)
        paired.append(dict(carrier_id=carrier,club_carrier_id=cid,moved_source_player_id=moved['source_player_id'],
            replacement=replacement))
    return dict(source_key=KEY,target_club_carrier_id=309,target_club=club,
        desired_people=desired,paired=paired,source_grid=coordinates,
        formation=source['formation'],opening_date=source['first_league_fixture_date'],
        source_bindings=[bound(source_path),bound(arsenal.PUBLIC),bound(report_path),raw_proof,
            bound(arsenal.ROOT/'geusens-original-person-identity.json'),
            bound(arsenal.ROOT/'geusens-identity-exclusion-proof.json'),
            *[bound(registry.ROOT/'scripts'/n) for n in (
                'arsenal_2021_opening_transaction_source_v1.py','prepare_arsenal_opening25_20261016.py',
                'capture_arsenal_coupled_primary_sources_20261016.py')]],
        source_annual_birth_conflicts=3,source_secondary_facts_not_membership=True)


if __name__=='__main__':
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    base=registry.load_registered_release('2021-22','sourced-year-bound-managers-20261016-r110a')
    doc=admission(base)
    retained(arsenal.ROOT/'coupled-source-admission.json',doc)
    print(dict(Arsenal_players=len(doc['desired_people']),paired_positive_members=len(doc['paired']),
        source_annual_date_conflicts=doc['source_annual_birth_conflicts'],native_writes=0),flush=True)
