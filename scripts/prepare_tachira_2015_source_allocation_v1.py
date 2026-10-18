"""Replay positive first14 plus two dated reserves into the fixed16 carrier.

Source-only feasibility. Does not close a case, mutate a release or treat a
calendar catalogue/current profile as opening membership.
"""
import copy

from scripts.capture_tachira_2015_original_people_v1 import join
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_historical_roster_audit_v1 as roster


def prepare(output, baseline_release_id=None):
    if output.exists():
        raise ValueError('source-only allocation is immutable')
    actual, matched, bindings = join()
    biography = ROOT.parent/'tachira-2015-original-person-identities-v1.json'
    document = pipeline.read_json_file(biography)
    if document['historical_opening_inputs'] != bindings:
        raise ValueError('original person query used different historical inputs')
    index, _ = identities.load_identity_snapshot()
    index, review = people.merge(index, document)
    if review['refused']:
        raise ValueError('original biographies conflict with pinned publisher identities')
    persons = {p['source_player_id']:p for b in document['batches'] for p in b['people']}
    ids = [r['source_player_id'] for r in matched]
    if set(persons)!=set(ids) or any(persons[r['source_player_id']]['birth_date']!=r['birth_date'] for r in matched):
        raise ValueError('confirmed original16 biographies incomplete or conflicting')
    release = (registry.load_registered_release('2015-16',baseline_release_id) if baseline_release_id
        else registry.load_preferred_release('2015-16'))
    layers = list(planner.package_layers(release))
    owners = [(label,p,path,c) for label,p,path in layers for c in p['clubs'] if c['carrier_id']==2953]
    if len(owners)!=1:
        raise ValueError('fixed native carrier has multiple recipe owners')
    layer, package, package_path, club = owners[0]
    if club['name']!='Minervén' or any('tachira' in roster.normalise(c['name']) for _,p,_ in layers for c in p['clubs']):
        raise ValueError('original stock club changed or replacement already represented')
    slots = [p for p in package['players'] if p['club_id']==club['id']]
    if len(slots)!=16:
        raise ValueError('fixed16 stock capacity changed')
    jug = (release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    orders = allocation.startup_orders(jug,slots)
    desired = []
    for row in matched:
        person = {k:copy.deepcopy(v) for k,v in persons[row['source_player_id']].items() if k!='published_name_variants'}
        desired.append(dict(source_person=person,
            source_player=dict(name=person['name'],birth_date=person['birth_date'],position=row['position'],
                nationality=None,height_cm=None,weight_kg=None,shirt_number=None),
            membership=row['membership'],raw_evidence=dict(status='raw-source-reparsed',local_path=bindings[0]['path'],source_sha256=bindings[0]['sha256']),
            source_role_basis=dict(role=row['position'],basis='original-dated-match-role' if 'original_match_person' in row else 'uncontested-explicit-secondary-catalogue-broad-role',
                original_person_identity=row),secondary_facts_status='unconfirmed-log-not-inherit-as-source-fact'))
    allocation.validate_opening_birth_dates(desired,actual['fixture_date'])
    fitted = allocation.allocate(jug,slots,desired,display.claims(biography),
        published_families=families.claims(biography,ids),opening_slot_orders=orders,allow_keeper_order_exchange=True)
    outside = []
    for _,p,_ in layers:
        clubs = {c['id']:c['name'] for c in p['clubs']}
        for player in p['players']:
            key = identities.key(player,index)
            if player['club_id']!=club['id'] and key and key[0]=='published-person' and key[1] in ids:
                outside.append(dict(source_player_id=key[1],carrier_id=player['carrier_id'],club=clubs[player['club_id']],native_recipe_player=player))
    result = dict(schema_version='pm99-private-original-tachira2015-fixed16-feasibility-v1',season='2015-16',
        policy='original-dated-match-XI-used-subs-plus-bracketed-reserves-fixed-capacity-v1',baseline_release_id=release.release_id,
        layer=layer,baseline_package=dict(path=registry.relative_workspace_path(package_path),sha256=registry.sha256_file(package_path)),
        before_club=club,new_club='Deportivo Tachira',country='venezuela',transfermarkt_club_id=13297,
        original_opening=actual,original_bindings=bindings,
        biography_input=dict(path=registry.relative_workspace_path(biography),sha256=registry.sha256_file(biography)),
        desired_people=desired,allocation=fitted,selected_bench_ids=ids[11:],
        capacity_selection_policy='Exact firstXI11 and three used substitutes plus two positive bracketed opening members; no invented unused opening bench.',
        role_disagreements=[],outside_identity_owners=outside,native_writes=0,publication_authorised=False,
        remaining=['secondary facts','dated manager/ground/kits','native compilation/readback','exact source reconstruction','actual runtime proof'])
    pipeline.write_canonical_json(output,result)
    return result


if __name__=='__main__':
    result=prepare(ROOT.parent/'tachira-2015-fixed16-source-feasibility-v1.json')
    print(dict(people=len(result['desired_people']),outside_owners=len(result['outside_identity_owners']),native_writes=0),flush=True)
