"""Source-only fixed18 feasibility, with outside ownership explicitly exposed."""
import copy
import itertools
import tempfile
from pathlib import Path

from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import capture_ofk_2015_original_roster_v1 as capture
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_published_transfer_history_v1 as histories


def prepare(output, *, baseline_release_id=None):
    if output.exists(): raise ValueError('2015 source allocation evidence is immutable')
    path = source.AUDIT / 'ofk-2015-original-opening-and-history-v1.json'
    claims = pipeline.read_json_file(path)
    schedule, schedule_binding = source.original('ofk-beograd-2015-schedule')
    report, report_binding = source.original('ofk-first-fixture-2015-2598829')
    class Offline:
        def get(self, url, key):
            if url == schedule_binding['url']: return schedule
            if url == report_binding['url']: return report
            raise ValueError('2015 original source URL changed')
    ref = capture.openings.TeamRef('OFK Beograd','OFK Beograd',53,
        '/ofk-belgrad/startseite/verein/53','exact-original-club-id')
    fixture = capture.openings._first_fixture(ref,season_start_year=2015,competition_code='SER1',cache=Offline())
    opening = capture.openings._lineup_from_report(ref,fixture,Offline())
    if (fixture != claims['first_fixture'] or opening != claims['original_opening']
            or claims['matchday_person_ids'] != [int(p['source_player_id']) for p in opening['starting_xi']+opening['substitutes']]):
        raise ValueError('2015 original fixture/XI/bench claims changed')
    # Reparse the already captured originals/histories; the acquisition helper
    # skips the completed52-person source ledger, never refetches originals.
    with tempfile.TemporaryDirectory(prefix='pm99-ofk2015-source-replay-') as temporary:
        # Capture's final output is deliberately immutable. Reuse its parsers
        # directly here instead of replacing/relabeling the saved source ledger.
        annual, annual_binding = capture.original_ids(2015)
        if claims['original_bindings'] != [annual_binding,schedule_binding,report_binding]:
            raise ValueError('2015 original claim bindings changed')
        raw, _ = source.original('ofk-beograd-2015')
        roles = source.annual_roles(raw, expected_year=2015)
        events, _ = histories.merge({}, pipeline.read_json_file(source.AUDIT / 'ofk-2015-target-annual-history-v1.json'))
        reserves = source.select_reserves(events, annual, claims['first_fixture']['date'], set(claims['matchday_person_ids']))
        if reserves != claims['positive_dated_extra_reserves'] or roles != {int(k):v for k,v in claims['annual_broad_roles'].items()}:
            raise ValueError('2015 original roles/dated reserve claims changed')
    biography = source.AUDIT / 'ofk-2015-original-person-identities-v1.json'
    document = pipeline.read_json_file(biography)
    expected_inputs = claims['original_bindings'] + [dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))]
    if document['historical_opening_inputs'] != expected_inputs: raise ValueError('2015 biography query input differs')
    index, _ = identities.load_identity_snapshot()
    index, review = people.merge(index, document)
    if review['refused']: raise ValueError('2015 original biographies conflict with pinned identities')
    rows = {p['source_player_id']:p for b in document['batches'] for p in b['people']}
    wanted = set(claims['matchday_person_ids']) | {r['source_player_id'] for r in reserves}
    if set(rows) != wanted: raise ValueError('2015 original biography people differ')
    release = (registry.load_registered_release('2015-16',baseline_release_id) if baseline_release_id
        else registry.load_preferred_release('2015-16'))
    layers = list(planner.package_layers(release))
    owners = [(label, package, path, club) for label,package,path in layers
        for club in package['clubs'] if club['carrier_id']==706]
    if len(owners)!=1: raise ValueError('2015 fixed club has multiple recipe owners')
    label, package, package_path, club = owners[0]
    if club['name']!='Becej': raise ValueError('2015 fixed baseline club changed')
    if any(c['name'].casefold()=='ofk beograd' for _,p,_ in layers for c in p['clubs']):
        raise ValueError('2015 proposed club already exists')
    slots = [p for p in package['players'] if p['club_id']==club['id']]
    if len(slots)!=18: raise ValueError('2015 fixed roster capacity changed')
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    orders = allocation.startup_orders(jug,slots)
    def desired(ids):
        result=[]
        for n,id in enumerate(ids):
            person={k:copy.deepcopy(v) for k,v in rows[id].items() if k!='published_name_variants'}
            result.append(dict(source_person=person,
                source_player=dict(name=person['name'],birth_date=person['birth_date'],position=roles[id],
                    nationality=None,height_cm=None,weight_kg=None,shirt_number=None),
                membership='starting_xi' if n<11 else ('published-opening-match-substitute' if n<14 else 'positive-original-dated-opening-reserve'),
                raw_evidence=dict(status='raw-source-reparsed',local_path=annual_binding['path'],source_sha256=annual_binding['sha256']),
                source_role_basis='original-target-annual-broad-group',
                secondary_facts_status='unconfirmed; current annual flag may reflect later citizenship'))
        return result
    failures=[]
    for extra in itertools.combinations([r['source_player_id'] for r in reserves],4):
        ids=claims['matchday_person_ids']+list(extra)
        selected=desired(ids)
        allocation.validate_opening_birth_dates(selected,claims['first_fixture']['date'])
        try:
            fitted=allocation.allocate(jug,slots,selected,display.claims(biography),
                published_families=families.claims(biography,ids),opening_slot_orders=orders,allow_keeper_order_exchange=True)
        except ValueError as exc:
            failures.append(dict(extra_ids=list(extra),reason=str(exc)))
            continue
        break
    else: raise ValueError('no positive2015 fixed18 set fits published display windows')
    outside=[]
    for _,p,_ in layers:
        clubs={c['id']:c['name'] for c in p['clubs']}
        for player in p['players']:
            key=identities.key(player,index)
            if (player['club_id']!=club['id'] and key and key[0]=='published-person' and key[1] in ids):
                outside.append(dict(source_player_id=key[1],carrier_id=player['carrier_id'],club_id=player['club_id'],club=clubs[player['club_id']],
                    identity_source_name=rows[key[1]]['name'],native_recipe_player=player))
    result=dict(schema_version='pm99-private-original-ofk2015-fixed18-feasibility-v1',
        policy=source.POLICY,season='2015-16',baseline_release_id=release.release_id,layer=label,
        baseline_package=dict(path=registry.relative_workspace_path(package_path),sha256=registry.sha256_file(package_path)),
        before_club=club,new_club='OFK Beograd',country='serbia',transfermarkt_club_id=53,
        first_fixture=claims['first_fixture'],original_opening=claims['original_opening'],
        desired_people=selected,allocation=fitted,selected_extra_source_ids=list(extra),
        capacity_selection_policy='lexicographically first source-ID combination of4 strictly dated reserves that fits all18 published display windows',
        unsuccessful_capacity_sets=failures,outside_identity_owners=outside,
        original_source_claims=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)),
        biography_input=dict(path=registry.relative_workspace_path(biography),sha256=registry.sha256_file(biography)),
        native_writes=0,publication_authorised=False,
        remaining=['Coupled source-backed disposition of outside player owners; no new cross-club duplicates.',
            'Dated nationality review: Cancarevic annual Armenian flag is later citizenship, not2015 proof.',
            'Native source identities/coach/ground/three kit sizes/replay/actual runtime proof.'])
    pipeline.write_canonical_json(output,result)
    return result


if __name__=='__main__':
    result=prepare(source.AUDIT/'ofk-2015-fixed18-source-feasibility-v1.json')
    print(dict(people=len(result['desired_people']),outside_owners=len(result['outside_identity_owners']),
        extra_ids=result['selected_extra_source_ids'],native_writes=0),flush=True)
