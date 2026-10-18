"""Fit August round2 XI, used substitutes and four positively dated reserves.

Unresolved fixture surnames do not acquire a namesake's first name or birthday.
"""
import copy
import re
from bs4 import BeautifulSoup
from scripts import mladost_2001_original_august_v1 as opening
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_historical_roster_audit_v1 as roster
from scripts.capture_tachira_2014_original_people_v1 import source_rows

ROOT=opening.ROOT
IDS=[41796,1301045,None,None,35938,60454,None,None,147163,None,None,46178,None,None]+opening.RESERVES
ROLES=['G','D','D','D','D','M','M','M','F','F','F','D','M','F','F','M','D','M']
BIO_STEMS=['original-person-candidates','additional-original-person-candidates','third-original-person-candidates']
HISTORY_STEMS=['original-candidate-histories','additional-original-histories','third-original-histories']


def prepare(output,baseline_release_id=None):
    if output.exists():raise ValueError('Mladost source allocation is immutable')
    path,raw,binding=source_rows('partizanopedia-2001-original-season')
    actual=opening.parse_match(raw,url=pipeline.read_json_file(path.with_suffix('.source.json'))['url'])
    path,raw,catalogue_binding=source_rows('mladost-apatin-2001-original-alltransfers')
    if pipeline.read_json_file(path.with_suffix('.source.json'))['url']!='https://www.transfermarkt.es/fk-mladost-apatin/alletransfers/verein/904':
        raise ValueError('Mladost identity catalogue club differs')
    page=BeautifulSoup(raw,'html.parser');aliases={}
    if page.title is None or 'Mladost Apatin' not in page.title.get_text():raise ValueError('Mladost catalogue title differs')
    for link in page.select('a[href*="/profil/spieler/"]'):
        id=int(re.search(r'/profil/spieler/(\d+)',link['href'])[1]);name=link.get_text(' ',strip=True)
        if name:aliases.setdefault(id,set()).add(roster.normalise(name))
    docs=[ROOT/f'mladost-2001-{stem}-v1.json' for stem in BIO_STEMS]
    history_paths=[ROOT/f'mladost-2001-{stem}-v1.json' for stem in HISTORY_STEMS]
    persons={};events={};merged={'schema_version':'pm99-published-person-identities-v1','batches':[]}
    documents=[]
    for doc in docs:
        data=pipeline.read_json_file(doc);people.merge({},data);documents.append(data)
        merged['batches'].extend(copy.deepcopy(data['batches']))
        for batch in data['batches']:
            for person in batch['people']:persons[person['source_player_id']]=person
    # Preserve the actual shared schema and outer metadata of the original batch.
    merged=copy.deepcopy(documents[0]);merged['batches']=sum([copy.deepcopy(d['batches']) for d in documents],[])
    biography=ROOT/'mladost-2001-combined-original-person-candidates-v1.json'
    if biography.exists():
        if pipeline.read_json_file(biography)!=merged:raise ValueError('retained combined original biography differs')
    else:pipeline.write_canonical_json(biography,merged)
    people.merge({},merged)
    for doc in history_paths:events,_=histories.merge(events,pipeline.read_json_file(doc))
    desired=[];labels=actual['starting_xi']+actual['used_substitutes']
    for order,(id,role) in enumerate(zip(IDS,ROLES)):
        interval=None
        if id is None:person=opening.unresolved_actor(order)
        else:
            person=copy.deepcopy(persons[id]);person.pop('published_name_variants',None)
            if roster.normalise(person['name']) not in aliases.get(id,set()):raise ValueError('missing exact original Mladost identity link')
            if order<14:
                label=labels[order]['published_match_name']
                # Serbian Dj/Đ publisher transliteration is explicitly equivalent.
                normal=lambda s:roster.normalise(s.replace('Đ','Dj').replace('đ','dj')).replace('dj','d')
                if normal(label)!=normal(person['name'].split()[-1]):raise ValueError('fixture surname differs from linked biography')
            if order in (0,1,8,11) or order>=14:
                interval=transfer.transfer_interval(events.get(id,[]),actual['fixture_date'])
                if interval.get('status')!='recorded-entry-and-exit-bracket-fixture' or interval['source_owner_club_id']!=904:
                    raise ValueError('selected dated Mladost identity lacks positive August ownership')
        desired.append(dict(source_person=person,source_player=dict(name=person['name'],birth_date=person['birth_date'],
            position=role,nationality=None,height_cm=None,weight_kg=None,shirt_number=None),
            membership='starting_xi' if order<11 else ('August-round2-used-substitute' if order<14 else 'positive-original-dated-August-reserve'),
            original_published_match_name=labels[order]['published_match_name'] if order<14 else None,
            opening_interval=interval,raw_evidence=dict(status='raw-source-reparsed',local_path=binding['path'],source_sha256=binding['sha256']),
            source_role_basis=dict(role=role,policy='explicit-editorial-broad-role-from-period-XI-order',exact_fine_position_sourced=False),
            secondary_facts_status='unpublished-log-no-current-import'))
    allocation.validate_opening_birth_dates([r for r in desired if r['source_person']['birth_date']],actual['fixture_date'])
    release=registry.load_registered_release('2001-02',baseline_release_id) if baseline_release_id else registry.load_preferred_release('2001-02')
    layers=list(planner.package_layers(release));owners=[(l,p,path,c) for l,p,path in layers for c in p['clubs'] if c['carrier_id']==706]
    if len(owners)!=1:raise ValueError('carrier lacks unique recipe owner')
    layer,package,path,club=owners[0]
    if club['name']!='Becej' or any('mladost apatin' in roster.normalise(c['name']) for _,p,_ in layers for c in p['clubs']):
        raise ValueError('obsolete club changed or replacement already represented')
    slots=[p for p in package['players'] if p['club_id']==club['id']]
    if len(slots)!=18:raise ValueError('fixed18 capacity changed')
    jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    fitted=allocation.allocate(jug,slots,desired,display.claims(biography),published_families=families.claims(biography,[i for i in IDS if i]),
        opening_slot_orders=allocation.startup_orders(jug,slots),allow_keeper_order_exchange=True,
        unknown_birthday_reference_date=actual['fixture_date'])
    index,_=identities.load_identity_snapshot();index,review=people.merge(index,merged)
    if any(r['player_id'] in IDS for r in review['refused']):raise ValueError('selected biography conflicts')
    outside=[]
    for _,p,_ in layers:
        for player in p['players']:
            key=identities.key(player,index)
            if player['club_id']!=club['id'] and key and key[0]=='published-person' and key[1] in IDS:
                outside.append(dict(carrier_id=player['carrier_id'],source_player_id=key[1],club_id=player['club_id']))
    result=dict(schema_version='pm99-private-original-mladost2001-fixed18-feasibility-v1',season='2001-02',
        baseline_release_id=release.release_id,layer=layer,before_club=club,new_club='Mladost Apatin',country='serbia',transfermarkt_club_id=904,
        baseline_package=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
        first_fixture=dict(date=actual['fixture_date'],first_league_xi=False,round=2),original_opening=actual,
        original_bindings=[binding,catalogue_binding]+[dict(path=registry.relative_workspace_path(p),sha256=registry.sha256_file(p)) for p in docs+history_paths],
        biography_input=dict(path=registry.relative_workspace_path(biography),sha256=registry.sha256_file(biography)),
        desired_people=desired,allocation=fitted,outside_identity_owners=outside,
        source_gaps=actual['limitations']+['Eight original fixture actors have unknown full identities and birthdays; native dates preserved as unsourced fallbacks.',
            'Nurkovic538007 is not silently identified as goalkeeper Elvis Nurkovic1986; reserve role M explicitly editorial.'],
        native_writes=0,closed_duplicate_cases=0,publication_authorised=False)
    pipeline.write_canonical_json(output,result);return result


if __name__=='__main__':
    r=prepare(ROOT/'mladost-2001-fixed18-source-feasibility-v1.json')
    print(dict(people=len(r['desired_people']),outside_owners=r['outside_identity_owners'],allocation=len(r['allocation'])),flush=True)
