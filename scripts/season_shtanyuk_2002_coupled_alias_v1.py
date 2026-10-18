"""Correct both wrong2002 owners, keeping the actual Stoke defender intact.

The Shinnik copy is a starter. Its replacement is explicitly sourced as an
actual2002 Shinnik player, not misrepresented as an unused native bench slot
or a claim of a complete first-fixture XI. All native orders/tactics stay exact.
"""
import copy
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_opening_order_repair_v1 as owners
from scripts import season_soccerbase_duplicate_source_policy_v1 as starting
from scripts import season_within_club_reserve_repair_v1 as native
from scripts import prepare_stoke_alias_identity_evidence_20261016 as identity
from scripts import prepare_stoke_vandeurzen_reserve_20261016 as vandeurzen
from scripts import prepare_shinnik_khomukha_reserve_20261016 as khomukha

SCHEMA = 'pm99-original-Shtanyuk2002-coupled-Stoke-Shinnik-actors-v1'


def guard(actors, clubs, facts, owner_map, Stoke_XI, Shinnik_XI):
    expected = {10542: ('Sergey Shtanyuk','sergeyshtanyuk','1973-08-13',348),
        10580: ('Siarhei Shtaniuk','siarheishtaniuk','1972-01-11',348),
        7972: ('Sergey Shtanyuk','shtanyuk','1900-01-01',757)}
    for carrier,(name, native_name, birthday, club) in expected.items():
        actor = actors[carrier]
        if ((actor.get('source_name') or actor['name']) != name
                or roster.normalise(facts[carrier]['name']) != native_name
                or facts[carrier]['birth_date'] != birthday or facts[carrier]['position'] != 'D'
                or actor['club_id'] != clubs[club]['id'] or owner_map.get(carrier) != {club}
                or clubs[club]['roster_player_ids'].count(actor['id']) != 1):
            raise ValueError('coupled native alias identity, preimage or exclusive owner differs')
    if (len(Stoke_XI) != 11 or 10542 not in Stoke_XI or 10580 in Stoke_XI
            or facts[10580]['startup_order'] <= 11 or len(Shinnik_XI) != 11
            or 7972 not in Shinnik_XI or facts[7972]['startup_order'] != 8):
        raise ValueError('coupled correction must explicitly identify its one changed starter')


def prepare(base):
    if base.season != '2002-03':
        raise ValueError('positive coupled original identities admit only2002')
    duplicate = identity.prepare()['retained_person']
    reserve = vandeurzen.prepare()
    foreign = khomukha.prepare()
    layers = planner.package_layers(base)
    package = next(p for label,p,_ in layers if label == 'main')
    represented = [p for _,layer,_ in layers for p in layer['players']]
    actors = {p['carrier_id']:p for p in represented}
    clubs = {c['carrier_id']:c for c in package['clubs']}
    if (clubs[348]['name'],clubs[757]['name']) != ('Stoke City','Shinnik Yaroslavl'):
        raise ValueError('positive numerical owner clubs changed')
    names = {roster.normalise(n) for n in ('Sergey Shtanyuk','Sergei Shtanyuk',
        'Siarhei Shtaniuk','Syarhey Shtanyuk','Sergei Shtaniuk')}
    found = [p['carrier_id'] for p in represented if any(roster.normalise(p.get(k)) in names
        for k in ('source_name','name'))]
    if set(found) != {10542,10580,7972} or len(found) != 3:
        raise ValueError('coupled correction must account for every represented alias owner')
    jug = (base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    fields = {c:native.native_facts(jug,c) for c in found}
    Stoke_XI,_ = starting.native_starters(base,clubs[348])
    Shinnik_XI,_ = starting.native_starters(base,clubs[757])
    guard(actors,clubs,fields,owners.native_owners(eq),Stoke_XI,Shinnik_XI)
    targets = [dict(carrier=10580,club=348,source=reserve['admitted']['source_player'],
        person=reserve['admitted']['source_person'],owner=reserve['admitted']['owner_evidence'],
        raw=reserve['historical_annual']['original'],is_starter=False),
        dict(carrier=7972,club=757,source=foreign['source_player'],person=foreign['source_person'],
            owner=foreign['owner_evidence'],raw=foreign['originals'][1],is_starter=True)]
    updates=[]
    for target in targets:
        source=copy.deepcopy(target['source']); person=copy.deepcopy(target['person'])
        replacement_names={roster.normalise(source['name'])}
        if target['carrier']==7972:
            replacement_names.add(roster.normalise('Dmitriy Khomukha'))
        if any(roster.normalise(p.get('source_name') or p['name']) in replacement_names for p in represented):
            raise ValueError('positive replacement is already represented')
        if target['carrier']==7972:
            # Explicitly reviewed published two-component Latin heading, not
            # an automated split of an arbitrary compound name or old alias.
            if person['name']!='Dmitri Khomukha':raise ValueError('published Latin components changed')
            person.update(given_name='Dmitri',family_name='Khomukha')
        before=actors[target['carrier']]
        updates.append(dict(layer='main',player_id=before['id'],carrier_id=target['carrier'],
            club_id=before['club_id'],before=copy.deepcopy(before),retained_owner_player_id=actors[10542]['id'],
            retained_carrier_id=10542,duplicate_source_person=duplicate,
            duplicate_owner_evidence=duplicate['positive_Stoke_tenure'],owner_evidence=target['owner'],
            replacement_opening_evidence=dict(date='2002-08-01',actual_first_fixture_claimed=False,
                policy='positive-original-senior-interior-year-and-dated-appearance-v1',
                selected_native_starter_explicit=target['is_starter']),
            replacement=dict(source_player=source,source_person=person,raw_evidence=target['raw']),
            duplicate_native_before=[fields[target['carrier']],fields[10542]]))
    return dict(schema_version=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI'),updates=updates,unresolved=[],
        starting_XI_change_authorised=True,explicitly_selected_native_starter=7972,
        entire_historical_starting_XI_approved=False,
        bindings=dict(snapshot=dict(project_url=khomukha.BIO),original_duplicate_identity=duplicate,
            original_Stoke_reserve=reserve,original_Shinnik_actor=foreign,
            implementation_inputs=[dict(path=registry.relative_workspace_path(p),sha256=registry.sha256_file(p))
                for p in (Path(__file__),Path(identity.__file__),Path(vandeurzen.__file__),Path(khomukha.__file__))]),
        source_title='Coupled2002 Shtanyuk owners; original Vandeurzen August substitution and Khomukha target-year registration/positive playing spell',
        proof_covers=['all-three-native-alias-owners-accounted-for','retained-Stoke-defender-unchanged',
            'positive-dated-replacement-people','one-selected-starter-explicit-not-a-bench-waiver',
            'all-unrelated-native-orders-tactics-players-managers-and-artwork-preserved'])


def verify_plan(base,plan):
    if plan.get('schema_version')!=SCHEMA or prepare(base)!=plan:
        raise ValueError('coupled original identities/owners/selected-starter plan does not independently reproduce')


def reconstruction(previous,release_id):
    path=previous.locator.get('ownership_plan_path')
    if not path:return None
    path=registry.ROOT/path;plan=pipeline.read_json_file(path)
    if plan.get('schema_version')!=SCHEMA:return None
    from scripts import season_duplicate_ownership_delta_v1 as delta
    from scripts import season_duplicate_layered_packages_v1 as layered
    from scripts import publish_historical_role_delta_v1 as publisher
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify_plan(base,plan)
    if path.resolve()!=(previous.package_path.parent/delta.plan_filename(plan)).resolve():
        raise ValueError('coupled SOURCE input is not release-local')
    expected,english,_,_=layered.prepare(base,plan,(base.game_path/'DBDAT/JUG98030.FDI').read_bytes())
    if english is not None or expected!=pipeline.read_json_file(previous.package_path):
        raise ValueError('edited coupled recipe cannot silently discard changes')
    descriptor=path.with_name('coupled-alias-SOURCE-inert.json')
    retained(descriptor,dict(season=base.season,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    result=publisher.publish(base.season,descriptor,release_id=release_id,source_release_id=base.release_id,ownership_plan_path=path)
    rebuilt=registry.load_registered_release(base.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=pipeline.read_json_file(previous.package_path):
        raise ValueError('entire coupled SOURCE recipe differs')
    return dict(result,complete_game_inventory_identical=True,complete_recipe_identical=True)
