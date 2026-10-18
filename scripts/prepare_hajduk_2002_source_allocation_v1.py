"""Source-only fixed18 feasibility retaining one published surname-only actor.

An unknown first name/DOB is not substituted with a present-day namesake.
Native compilation must separately declare how an unavailable DOB is handled.
"""
import copy
import hashlib
from scripts import hajduk_2002_original_opening_v1 as opening
from scripts import season_august_source_fallback_v1 as fallback
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_display_names_v1 as display
from scripts import season_original_fixture_display_v1 as fixture_display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_historical_roster_audit_v1 as roster
from scripts.capture_tachira_2014_original_people_v1 import source_rows

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1'
KEYS = ['dekisa-original-2003-12003-htm','partizanopedia-2002-original-season',
    'hajduk-2002-original-opening-manager-chronology']
DOCUMENTS = ['hajduk-2002-original-person-candidates-v1.json',
    'hajduk-2002-original-additional-person-candidates-v1.json']
HISTORIES = ['hajduk-2002-original-candidate-histories-v1.json',
    'hajduk-2002-additional-original-histories-v1.json']
XI_IDS = [1514015,35918,10290,28688,None,35921,35929,145641,35932,36121,212936]
RESERVES = [6623,35926,35938,1390740,1391105,1514016]
ROLES = {1514015:'G',35918:'D',10290:'D',28688:'M',35921:'D',35929:'M',
    145641:'M',35932:'D',36121:'M',212936:'F',87808:'M',6623:'D',35926:'G',
    35938:'D',1390740:'M',1391105:'M',1514016:'F'}


def prepare(output, baseline_release_id=None):
    if output.exists(): raise ValueError('source-only allocation is immutable')
    originals = [source_rows(key) for key in KEYS]
    actual = opening.parse(*(r[1] for r in originals))
    documents = [pipeline.read_json_file(ROOT/name) for name in DOCUMENTS]
    combined = copy.deepcopy(documents[0])
    combined['batches'] += copy.deepcopy(documents[1]['batches'])
    combined['historical_opening_inputs'] += copy.deepcopy(documents[1]['historical_opening_inputs'])
    people.merge({},combined)
    biography = ROOT/'hajduk-2002-combined-original-identities-v1.json'
    if biography.exists():
        if pipeline.read_json_file(biography) != combined: raise ValueError('combined biography changed')
    else: pipeline.write_canonical_json(biography,combined)
    persons = {p['source_player_id']:p for batch in combined['batches'] for p in batch['people']}
    events = {}
    for name in HISTORIES: events,_ = histories.merge(events,pipeline.read_json_file(ROOT/name))
    declaration = fallback.surname(published_surname='Trajkovic',provider='dekisa',
        club='Hajduk Kula',fixture_date=actual['fixture_date'],source_binding=originals[0][2])
    actor_key = 'fixture-actor:'+hashlib.sha256(pipeline.canonical_json_bytes(declaration)).hexdigest()[:24]
    desired = []
    for n,id in enumerate(XI_IDS + [87808] + RESERVES):
        if id is None:
            person = dict(source_player_id=actor_key,source_provider='original-fixture',
                name='Trajkovic',given_name=None,family_name='Trajkovic',birth_date=None,
                identity_policy=fallback.SCHEMA,identity_evidence=declaration,
                original_fixture_bindings=[r[2] for r in originals])
            fixture_display.verify_actor(person)
            role='D';membership='starting_xi';interval=None
        else:
            person={k:copy.deepcopy(v) for k,v in persons[id].items() if k!='published_name_variants'}
            role=ROLES[id]
            membership='starting_xi' if n<11 else ('used-opening-substitute' if n==11 else 'positive-original-dated-opening-reserve')
            interval=transfer.transfer_interval(events.get(id,[]),actual['fixture_date'])
            if n>=12 and (interval.get('status')!='recorded-entry-and-exit-bracket-fixture' or interval['source_owner_club_id']!=3140):
                raise ValueError('reserve lacks positive target-club opening interval')
            if n<11 and opening.XI[n].casefold() not in person['name'].casefold():
                raise ValueError('published opening surname does not match independent person')
        desired.append(dict(source_person=person,
            source_player=dict(name=person['name'],birth_date=person['birth_date'],position=role,
                nationality=None,height_cm=None,weight_kg=None,shirt_number=None),
            membership=membership,opening_interval=interval,
            raw_evidence=dict(status='raw-source-reparsed',local_path=originals[0][2]['path'],source_sha256=originals[0][2]['sha256']),
            source_role_basis=dict(role=role,policy='explicit-editorial-broad-role-not-current-feed',exact_fine_position_sourced=False),
            secondary_facts_status='unpublished-log-no-current-attribute-import'))
        if id is not None and n<=11:
            batch=next(b for b in combined['batches'] if id in b['requested_ids'] and any(p['source_player_id']==id for p in b['people']))
            desired[-1]['original_fixture_display']=dict(policy=fixture_display.POLICY,
                match_person_index=n,published_label=(actual['starting_xi']+actual['used_substitutes'])[n]['published_match_name'],
                source_player_id=id,original_bindings=[r[2] for r in originals],
                original_person_batch={key:copy.deepcopy(batch[key]) for key in display.BATCH_KEYS})
    allocation.validate_opening_birth_dates([r for r in desired if r['source_person']['birth_date']],actual['fixture_date'])
    release=(registry.load_registered_release('2002-03',baseline_release_id) if baseline_release_id else registry.load_preferred_release('2002-03'))
    layers=list(planner.package_layers(release))
    owners=[(label,p,path,c) for label,p,path in layers for c in p['clubs'] if c['carrier_id']==706]
    if len(owners)!=1: raise ValueError('native club has multiple recipe owners')
    layer,package,path,club=owners[0]
    if club['name']!='Becej' or any(roster.normalise(c['name']) in {'hajduk kula','fk hajduk kula','hajduk rodic mb kula'}
            for _,p,_ in layers for c in p['clubs']):
        raise ValueError('obsolete club changed or Hajduk already represented')
    slots=[p for p in package['players'] if p['club_id']==club['id']]
    if len(slots)!=18:raise ValueError('fixed18 capacity changed')
    jug=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    ids=[id for id in XI_IDS+[87808]+RESERVES if id is not None]
    fitted=allocation.allocate(jug,slots,desired,display.claims(biography),
        published_families=families.claims(biography,ids),opening_slot_orders=allocation.startup_orders(jug,slots),
        allow_keeper_order_exchange=True)
    index,_=identities.load_identity_snapshot();index,review=people.merge(index,combined)
    if any(r['player_id'] in ids for r in review['refused']):raise ValueError('selected biography conflicts')
    outside=[]
    for _,p,_ in layers:
        for player in p['players']:
            key=identities.key(player,index)
            if player['club_id']!=club['id'] and key and key[0]=='published-person' and key[1] in ids:
                outside.append(dict(carrier_id=player['carrier_id'],source_player_id=key[1],club_id=player['club_id']))
    result=dict(schema_version='pm99-private-original-hajduk2002-fixed18-feasibility-v1',season='2002-03',
        baseline_release_id=release.release_id,layer=layer,before_club=club,new_club='Hajduk Kula',country='serbia',
        transfermarkt_club_id=3140,first_fixture=dict(date=actual['fixture_date']),
        baseline_package=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
        original_opening=actual,original_bindings=[r[2] for r in originals]+[
            dict(path=registry.relative_workspace_path(ROOT/name),sha256=registry.sha256_file(ROOT/name)) for name in DOCUMENTS+HISTORIES],
        biography_input=dict(path=registry.relative_workspace_path(biography),sha256=registry.sha256_file(biography)),
        desired_people=desired,allocation=fitted,outside_identity_owners=outside,published_surname_fallback=declaration,
        source_gaps=['Trajkovic first name and birthday unavailable; no current namesake or birthday invented.',
            'Secondary facts and precise formation unavailable; broad roles explicitly editorial.',
            'Unused opening bench unpublished; six reserves have positive dated club intervals.'],
        native_writes=0,closed_duplicate_cases=0,publication_authorised=False,
        remaining=['explicit native unknown-DOB handling','dated ground/period kit','native/source replay/runtime/final checkpoint'])
    pipeline.write_canonical_json(output,result)
    return result


if __name__=='__main__':
    result=prepare(ROOT/'hajduk-2002-fixed18-source-feasibility-v1.json')
    print(dict(people=len(result['desired_people']),outside_owners=len(result['outside_identity_owners']),
        unknown_full_names=1,native_writes=0,closed_duplicate_cases=0),flush=True)
