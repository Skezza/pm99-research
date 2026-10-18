"""Replay an August Sartid XI and positive reserve histories; no game writes.

The August19 report is round TWO, not an invented opening-day report. The
August12 opener is independently dated but its XI remains unavailable here.
All-time transfer catalogue rows provide identity links only, not membership.
"""
import copy
import re

from bs4 import BeautifulSoup

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import audit_published_player_identities_v1 as identities
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_original_fixture_display_v1 as fixture_display
from scripts.capture_tachira_2014_original_people_v1 import source_rows

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1'
MATCH_URL = 'https://www.partizanopedia.rs/0001.html'
LINE = ("Sartid: Lukić, Bulić, Sočanac (75' Radosavljević), Aleksić, Mrdak, "
        "Glogovac, Kocić, Vasković (68' Panić), Mudrinić, Bogdanović (34' Efimov), "
        "Zečević Trener: Slobodan Dogandžić")
XI = [('Lukić',171101,'G'),('Bulić',49774,'D'),('Sočanac',26087,'D'),
      ('Aleksić',635675,'D'),('Mrdak',60415,'D'),('Glogovac',179334,'D'),
      ('Kocić',26076,'M'),('Vasković',17185,'M'),('Mudrinić',26080,'M'),
      ('Bogdanović',26067,'M'),('Zečević',26090,'F')]
USED = [('Radosavljević',26083,'D',75),('Panić',635680,'M',68),('Efimov',519157,'F',34)]
RESERVES = [(26085,'G'),(26069,'M'),(34666,'M'),(12523,'D')]
DISPLAY_POLICY='original-sartid2000-literal-fixture-display-label-v1'


def parse_match(raw, *, url=MATCH_URL):
    if url != MATCH_URL or not isinstance(raw,bytes) or not 500 <= len(raw) <= 2*1024**2:
        raise ValueError('unexpected original Sartid source URL or size')
    page=BeautifulSoup(raw,'html.parser')
    headings=[h for h in page.select('h3')
              if h.get_text(' ',strip=True)=='Sartid - Partizan 3:2 (0:1)']
    if len(headings)!=1:
        raise ValueError('dated Sartid fixture missing or ambiguous')
    section=[]
    for item in headings[0].find_all_next(['h3','p']):
        if item.name=='h3': break
        section.append(re.sub(r'\s+',' ',item.get_text(' ',strip=True)))
    if (len(section)<3 or section[0]!='19. avgust 2000. 17.30 Gledalaca: 15 000'
            or section[1]!=LINE):
        raise ValueError('original Sartid date, XI, substitutions or manager changed')
    return dict(season='2000-01',fixture_date='2000-08-19',club='Sartid Smederevo',
        manager='Slobodan Dogandžić',starting_xi=[dict(published_match_name=n,source_player_id=i)
            for n,i,_ in XI],used_substitutes=[dict(published_match_name=n,source_player_id=i,minute=m)
            for n,i,_,m in USED],first_league_xi=False,round=2,
        limitations=['Original first-league XI on August12 is not supplied by this report.',
            'August19 XI is a declared later-August squad sample, never labelled round one.',
            'Formation and fine positions are not historically certified.'])


def fixture_candidates(replacement):
    """A literal published fixture surname, not a newly inferred name part."""
    claim=replacement.get('original_fixture_display',{})
    if claim.get('policy')!=DISPLAY_POLICY: raise ValueError('unsupported Sartid display policy')
    _,raw,binding=source_rows('partizanopedia-2000-original-season')
    _,catalogue,catalogue_binding=source_rows('sartid-2000-original-alltransfers')
    if claim['original_bindings']!=[binding,catalogue_binding]:
        raise ValueError('Sartid display source bindings changed')
    parsed=parse_match(raw)
    labels=parsed['starting_xi']+parsed['used_substitutes'];index=claim['match_person_index']
    if type(index) is not int or not 0<=index<len(labels):
        raise ValueError('Sartid display index outside original XI/used substitutes')
    person=replacement['source_person'];actor=labels[index]
    if (claim['published_label']!=actor['published_match_name']
            or claim['source_player_id']!=person['source_player_id']
            or person['source_player_id']!=actor['source_player_id']):
        raise ValueError('Sartid display label is assigned to another fixture actor')
    _,confirmed=display.read_batch(claim['original_person_batch'])
    original=confirmed.get(person['source_player_id'])
    if original is None or any(original[k]!=person[k] for k in ('name','birth_date')):
        raise ValueError('Sartid fixture label is not bound to original person biography')
    links=BeautifulSoup(catalogue,'html.parser').select('a[href*="/profil/spieler/"]')
    aliases={roster.normalise(a.get_text(' ',strip=True)) for a in links
        if re.search(r'/profil/spieler/(\d+)',a['href'])[1]==str(person['source_player_id'])}
    if roster.normalise(person['name']) not in aliases:
        raise ValueError('Sartid fixture identity bridge lacks the original catalogue link')
    return [dict(name=actor['published_match_name'],
        method='original-published-fixture-label-not-full-family-claim')]


def prepare(output, baseline_release_id=None):
    if output.exists(): raise ValueError('original source allocation is immutable')
    _,raw,match_binding=source_rows('partizanopedia-2000-original-season')
    receipt=pipeline.read_json_file(ROOT/'replacement-candidates/partizanopedia-2000-original-season.source.json')
    actual=parse_match(raw,url=receipt['url'])
    _,catalogue,catalogue_binding=source_rows('sartid-2000-original-alltransfers')
    receipt=pipeline.read_json_file(ROOT/'replacement-candidates/sartid-2000-original-alltransfers.source.json')
    if receipt['url']!='https://www.transfermarkt.es/fk-smederevo/alletransfers/verein/3544':
        raise ValueError('identity catalogue URL differs from the original club')
    page=BeautifulSoup(catalogue,'html.parser')
    if page.title is None or 'FK Smederevo 1924' not in page.title.get_text():
        raise ValueError('original identity catalogue belongs to another club')
    aliases={}
    for link in page.select('a[href*="/profil/spieler/"]'):
        id=int(re.search(r'/profil/spieler/(\d+)',link['href'])[1])
        name=link.get_text(' ',strip=True)
        if name: aliases.setdefault(id,set()).add(roster.normalise(name))
    biography=ROOT/'sartid-2000-original-person-candidates-v1.json'
    document=pipeline.read_json_file(biography)
    people.merge({},document)  # independently reparse original identity responses
    persons={p['source_player_id']:p for b in document['batches'] for p in b['people']}
    history=ROOT/'sartid-2000-original-reserve-histories-v1.json'
    events,_=histories.merge({},pipeline.read_json_file(history))
    desired=[]
    actors=[(n,i,r) for n,i,r in XI]+[(n,i,r) for n,i,r,_ in USED]+[(None,i,r) for i,r in RESERVES]
    for order,(label,id,role) in enumerate(actors):
        person=copy.deepcopy(persons[id]);person.pop('published_name_variants',None)
        if roster.normalise(person['name']) not in aliases.get(id,set()):
            raise ValueError('person lacks an exact independently linked catalogue name')
        if label and roster.normalise(label)!=roster.normalise(person['name'].split()[-1]):
            raise ValueError('original fixture surname cannot be assigned to this identity')
        interval=transfer.transfer_interval(events.get(id,[]),actual['fixture_date']) if order>=14 else None
        if order>=14 and (interval['status']!='recorded-entry-and-exit-bracket-fixture'
                          or interval['source_owner_club_id']!=3544):
            raise ValueError('reserve lacks a positive Sartid August membership interval')
        desired.append(dict(source_person=person,
            source_player=dict(name=person['name'],birth_date=person['birth_date'],position=role,
                nationality=None,height_cm=None,weight_kg=None,shirt_number=None),
            membership=('starting_xi' if order<11 else 'August-round2-used-substitute'
                        if order<14 else 'positive-original-dated-August-reserve'),
            fixture_scope='August19-round2-not-first-league-XI',
            opening_interval=interval,
            raw_evidence=dict(status='raw-source-reparsed',local_path=match_binding['path'],
                source_sha256=match_binding['sha256']),
            source_role_basis=dict(role=role,policy='explicit-editorial-broad-role-not-current-feed',
                exact_fine_position_sourced=False),secondary_facts_status='unreviewed-log-no-current-import'))
        if label:
            batch=next(b for b in document['batches'] if id in b['requested_ids']
                and any(p['source_player_id']==id for p in b['people']))
            desired[-1]['original_fixture_display']=dict(policy=DISPLAY_POLICY,
                match_person_index=order,published_label=label,source_player_id=id,
                original_bindings=[match_binding,catalogue_binding],
                original_person_batch={k:copy.deepcopy(batch[k]) for k in display.BATCH_KEYS})
            fixture_display.candidates(desired[-1])
    allocation.validate_opening_birth_dates(desired,actual['fixture_date'])
    release=(registry.load_registered_release('2000-01',baseline_release_id)
             if baseline_release_id else registry.load_preferred_release('2000-01'))
    layers=list(planner.package_layers(release))
    owners=[(l,p,path,c) for l,p,path in layers for c in p['clubs'] if c['carrier_id']==706]
    if len(owners)!=1: raise ValueError('carrier lacks a unique recipe owner')
    layer,package,path,club=owners[0]
    if club['name']!='Becej' or any(roster.normalise(c['name']) in
            {'sartid','sartid smederevo','fk sartid smederevo','smederevo','fk smederevo'}
            for _,p,_ in layers for c in p['clubs']):
        raise ValueError('obsolete club changed or replacement already represented')
    slots=[p for p in package['players'] if p['club_id']==club['id']]
    if len(slots)!=18: raise ValueError('fixed18 capacity changed')
    jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    ids={i for _,i,_ in actors}
    fitted=allocation.allocate(jug,slots,desired,display.claims(biography),
        published_families=families.claims(biography,ids),
        opening_slot_orders=allocation.startup_orders(jug,slots),allow_keeper_order_exchange=True)
    index,_=identities.load_identity_snapshot();index,review=people.merge(index,document)
    if any(r['player_id'] in ids for r in review['refused']): raise ValueError('selected biography conflicts')
    outside=[]
    for _,p,_ in layers:
        for player in p['players']:
            key=identities.key(player,index)
            if player['club_id']!=club['id'] and key and key[0]=='published-person' and key[1] in ids:
                outside.append(dict(carrier_id=player['carrier_id'],source_player_id=key[1],club_id=player['club_id']))
    result=dict(schema_version='pm99-private-original-sartid2000-fixed18-feasibility-v1',
        season='2000-01',baseline_release_id=release.release_id,layer=layer,before_club=club,
        new_club='Sartid Smederevo',country='serbia',transfermarkt_club_id=3544,
        baseline_package=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
        first_fixture=dict(date=actual['fixture_date'],first_league_xi=False,round=2),
        original_opening=actual,original_bindings=[match_binding,catalogue_binding]+[
            dict(path=registry.relative_workspace_path(p),sha256=registry.sha256_file(p)) for p in [biography,history]],
        biography_input=dict(path=registry.relative_workspace_path(biography),sha256=registry.sha256_file(biography)),
        desired_people=desired,allocation=fitted,outside_identity_owners=outside,
        source_gaps=actual['limitations']+['Secondary nationality/height/weight/kit/ground not approved here.',
            'Reserve Nenad Mirosavljevic positively sourced but not selected: his available published display names compete with an original used substitute for one native name window. Ivan Krizmanic independently dated at Sartid selected instead; no original XI/used substitute omitted.'],
        native_writes=0,closed_duplicate_cases=0,publication_authorised=False)
    pipeline.write_canonical_json(output,result)
    return result


if __name__=='__main__':
    result=prepare(ROOT/'sartid-2000-fixed18-source-feasibility-v1.json')
    print(dict(people=len(result['desired_people']),allocation=len(result['allocation']),
        outside_owners=result['outside_identity_owners'],native_writes=0),flush=True)
