"""Fit the period August cup16 without substituting modern Gomez or coach.

Source-only feasibility. Independent publisher DOBs are secondary facts, not
proof of membership; the original CONMEBOL fixture supplies membership.
"""
import copy

from bs4 import BeautifulSoup

from scripts import estudiantes_2000_original_august_v1 as opening
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import season_original_fixture_display_v1 as fixture_display
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_historical_roster_audit_v1 as roster
from scripts.capture_tachira_2014_original_people_v1 import source_rows

ROOT=opening.ROOT
IDS=[380346,74114,99208,147523,902032,1298268,None,1446560,710805,767240,99295,
     710826,99194,901937,1446563,1446565]
ROLES=['G','D','D','D','D','M','M','M','M','F','F','D','G','F','M','D']


def prepare(output,baseline_release_id=None):
    if output.exists():raise ValueError('source allocation is immutable')
    review_path=ROOT/'estudiantes-2000-original-magazine66-August2-visual-review-v1.json'
    actual=opening.replay(review_path)
    _,catalogue,catalogue_binding=source_rows('estudiantes-2000-original-linked-identity-catalogue')
    page=BeautifulSoup(catalogue,'html.parser')
    if page.title is None or 'Estudiantes de Mérida - Plantilla detallada 2000' not in page.title.get_text():
        raise ValueError('original calendar-year identity catalogue belongs to another club/season')
    labels=[p['published_match_name'] for p in actual['starting_xi']+actual['used_substitutes']]+actual['unused_substitutes']
    biography=ROOT/'estudiantes-2000-original-person-candidates-v1.json'
    document=pipeline.read_json_file(biography);people.merge({},document)
    persons={p['source_player_id']:p for b in document['batches'] for p in b['people']}
    desired=[]
    for n,(id,role) in enumerate(zip(IDS,ROLES)):
        if id is None:
            person=opening.unresolved_gomez();fixture_display.verify_actor(person)
        else:
            person=copy.deepcopy(persons[id]);person.pop('published_name_variants',None)
            linked={roster.normalise(a.get_text(' ',strip=True))
                for a in page.select(f'a[href*="/profil/spieler/{id}"]') if a.get_text(' ',strip=True)}
            if roster.normalise(person['name']) not in linked:
                raise ValueError('selected person lacks exact original annual identity link')
        desired.append(dict(source_person=person,
            source_player=dict(name=person['name'],birth_date=person['birth_date'],position=role,
                nationality=None,height_cm=None,weight_kg=None,shirt_number=None),
            membership='starting_xi' if n<11 else ('used-August-cup-substitute' if n==11 else 'unused-original-August-cup-reserve'),
            original_published_match_name=labels[n],
            raw_evidence=dict(status='original-PDF-page-visually-reviewed',
                local_path=registry.relative_workspace_path(ROOT/'estudiantes-2000-original-CONMEBOL-magazine66.pdf'),
                source_sha256=opening.PDF_SHA),
            source_role_basis=dict(role=role,policy='explicit-editorial-broad-role-from-period-XI-order',
                exact_fine_position_sourced=False),secondary_facts_status='unpublished-log-no-current-facts'))
    allocation.validate_opening_birth_dates([r for r in desired if r['source_person']['birth_date']],actual['fixture_date'])
    release=(registry.load_registered_release('2000-01',baseline_release_id)
        if baseline_release_id else registry.load_preferred_release('2000-01'))
    layers=list(planner.package_layers(release))
    owners=[(label,p,path,c) for label,p,path in layers for c in p['clubs'] if c['carrier_id']==2953]
    if len(owners)!=1:raise ValueError('obsolete native club has multiple owners')
    layer,package,path,club=owners[0]
    if roster.normalise(club['name'])!='minerven' or any('estudiantes' in roster.normalise(c['name'])
        for _,p,_ in layers for c in p['clubs']):raise ValueError('club changed or target already represented')
    slots=[p for p in package['players'] if p['club_id']==club['id']]
    if len(slots)!=16:raise ValueError('fixed16 capacity changed')
    jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    fitted=allocation.allocate(jug,slots,desired,display.claims(biography),
        published_families=families.claims(biography,[id for id in IDS if id is not None]),
        opening_slot_orders=allocation.startup_orders(jug,slots),allow_keeper_order_exchange=True)
    index,_=identities.load_identity_snapshot();index,review=people.merge(index,document)
    if any(r['player_id'] in IDS for r in review['refused']):raise ValueError('selected biography conflicts')
    outside=[]
    for _,p,_ in layers:
        for player in p['players']:
            key=identities.key(player,index)
            if player['club_id']!=club['id'] and key and key[0]=='published-person' and key[1] in IDS:
                outside.append(dict(carrier_id=player['carrier_id'],source_player_id=key[1],club_id=player['club_id']))
    result=dict(schema_version='pm99-private-original-estudiantes2000-fixed16-feasibility-v1',
        season='2000-01',baseline_release_id=release.release_id,layer=layer,before_club=club,
        new_club='Estudiantes de Mérida',country='venezuela',transfermarkt_club_id=14555,
        first_fixture=dict(date=actual['fixture_date']),original_opening=actual,
        baseline_package=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
        original_bindings=[dict(path=registry.relative_workspace_path(f),sha256=registry.sha256_file(f))
            for f in [ROOT/'estudiantes-2000-original-CONMEBOL-magazine66.pdf',review_path,biography]]+[catalogue_binding],
        biography_input=dict(path=registry.relative_workspace_path(biography),sha256=registry.sha256_file(biography)),
        desired_people=desired,allocation=fitted,outside_identity_owners=outside,
        source_gaps=['Javier Gomez provider identity and birthday unresolved; no modern namesake birthday imported.',
            'Original Buitriago spelling retained in fixture; independent publisher identity spells Buitrago.',
            'Exact fine positions/physical facts/nationalities/portraits/kit artwork unapproved.'],
        native_writes=0,closed_duplicate_cases=0,publication_authorised=False,
        remaining=['native unknown-DOB handling','period kit/source replay','native and identity proof','runner/frozen delivery'])
    pipeline.write_canonical_json(output,result)
    return result


if __name__=='__main__':
    r=prepare(ROOT/'estudiantes-2000-fixed16-source-feasibility-v1.json')
    print(dict(people=len(r['desired_people']),outside_owners=len(r['outside_identity_owners']),
        native_writes=0,closed_duplicate_cases=0),flush=True)
