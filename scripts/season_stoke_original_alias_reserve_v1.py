"""Positive original transliteration identity despite a false duplicate DOB.

Do not relax equal-DOB duplicate policies or introduce fuzzy automatic merges.
This reviewed pair requires three independently retained original identity
sources, a dated Stoke spell, exact native owners and an unused dated reserve.
"""
import copy
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import season_soccerbase_duplicate_source_policy_v1 as starters
from scripts import prepare_stoke_alias_identity_evidence_20261016 as originals

SCHEMA = 'pm99-original-Stoke2001-false-DOB-transliteration-reserve-v1'


def pair_guard(season, club, before, keep, first, second, owners, starting):
    if (season != '2001-02' or club['name'] != 'Stoke City' or club['carrier_id'] != 375
            or (before['carrier_id'], keep['carrier_id']) != (27013, 27002)
            or before['club_id'] != club['id'] or keep['club_id'] != club['id']
            or [before.get('source_name') or before['name'], keep.get('source_name') or keep['name']]
                != ['Siarhei Shtaniuk', 'Sergey Shtanyuk']
            or [first['birth_date'], second['birth_date']] != ['1972-01-11', '1973-08-13']
            or [roster.normalise(first['name']), roster.normalise(second['name'])]
                != ['siarheishtaniuk', 'sergeyshtanyuk']):
        raise ValueError('outside the independently sourced exact native alias pair')
    for p in (before, keep):
        if owners.get(p['carrier_id']) != {375} or club['roster_player_ids'].count(p['id']) != 1:
            raise ValueError('native alias lacks one exclusive declared and actual owner')
    if len(starting) != 11 or before['carrier_id'] in starting or first['startup_order'] <= 11:
        raise ValueError('alias replacement cannot alter a native starter')
    if first['position'] == 'G' or second['position'] != 'D':
        raise ValueError('original alias defender/native reserve role mismatch')


def prepare(base):
    if base.season != '2001-02':
        raise ValueError('this original pair admits only Stoke2001; other owners need coupled evidence')
    evidence = originals.prepare()
    layers = planner.package_layers(base)
    packages = [p for label, p, _ in layers if label == 'main']
    if len(packages) != 1:
        raise ValueError('one native main recipe required')
    package = packages[0]
    people = {p['carrier_id']: p for p in package['players']}
    before, keep = people[27013], people[27002]
    club = next(c for c in package['clubs'] if c['id'] == before['club_id'])
    jug_path = base.game_path / 'DBDAT/JUG98030.FDI'
    eq_path = base.game_path / 'DBDAT/EQ98030.FDI'
    jug, eq = jug_path.read_bytes(), eq_path.read_bytes()
    first, second = facts.native_facts(jug, 27013), facts.native_facts(jug, 27002)
    starting, _ = starters.native_starters(base, club)
    pair_guard(base.season, club, before, keep, first, second, ownership.native_owners(eq), starting)
    names = {roster.normalise(n) for n in ('Sergey Shtanyuk', 'Sergei Shtanyuk',
        'Siarhei Shtaniuk', 'Syarhey Shtanyuk', 'Sergei Shtaniuk')}
    represented = [p for _, layer, _ in layers for p in layer['players']]
    aliases = [p['carrier_id'] for p in represented if any(roster.normalise(p.get(k)) in names
        for k in ('name', 'source_name'))]
    if set(aliases) != {27013, 27002} or len(aliases) != 2:
        raise ValueError('additional represented alias needs coupled owner correction')
    reserve = evidence['positive_2001_reserve']
    source = copy.deepcopy(reserve['annual']['person'])
    if any(roster.normalise(p.get('source_name') or p['name']) == roster.normalise(source['name'])
            for p in represented):
        raise ValueError('positive reserve is already represented; no new duplicate permitted')
    if (source['name'], source['birth_date'], source['position']) != ('Kris Commons', '1983-08-30', 'M'):
        raise ValueError('original positive reserve identity changed')
    person = dict(source_provider='soccerbase', source_player_id='soccerbase:28633',
        provider_player_id=28633, source_profile_url=reserve['original']['url'],
        name=source['name'], birth_date=source['birth_date'],
        identity_policy='original-numerical-person-profile-and-reparsed-target-annual-name-DOB-v1')
    row = dict(layer='main', player_id=before['id'], carrier_id=27013, club_id=club['id'],
        before=copy.deepcopy(before), retained_owner_player_id=keep['id'], retained_carrier_id=27002,
        duplicate_native_before=[first, second], duplicate_source_person=evidence['retained_person'],
        duplicate_owner_evidence=evidence['retained_person']['positive_Stoke_tenure'],
        owner_evidence=reserve['Stoke'],
        replacement_opening_evidence=dict(date='2001-08-01',
            policy='original-dated-career-and-unique-target-annual-reserve-v1', actual_first_fixture_claimed=False),
        replacement=dict(source_player=source, source_person=person, raw_evidence=reserve['annual']['original']))
    inputs = [Path(__file__), Path(originals.__file__)]
    return dict(schema_version=SCHEMA, season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path), jug_sha256=registry.sha256_file(jug_path),
        eq_sha256=registry.sha256_file(eq_path), updates=[row], unresolved=[], starting_XI_change_authorised=False,
        bindings=dict(snapshot=dict(project_url=reserve['original']['url']),
            original_source_admission=evidence,
            implementation_inputs=[dict(path=registry.relative_workspace_path(p), sha256=registry.sha256_file(p)) for p in inputs]),
        source_title='Three original Shtanyuk alias identities, exact dated Stoke tenure and unused Commons August reserve',
        proof_covers=['original-alias-despite-wrong-duplicate-DOB', 'exclusive-native-owners',
            'positive-dated-opening-reserve', 'native-starting-XI-preserved'])


def verify_plan(base, plan):
    if plan.get('schema_version') != SCHEMA or prepare(base) != plan:
        raise ValueError('original alias reserve plan does not independently reproduce')


def reconstruction(previous, release_id):
    path = previous.locator.get('ownership_plan_path')
    if not path:
        return None
    path = registry.ROOT / path
    plan = pipeline.read_json_file(path)
    if plan.get('schema_version') != SCHEMA:
        return None
    from scripts import season_duplicate_ownership_delta_v1 as delta
    from scripts import season_duplicate_layered_packages_v1 as layered
    from scripts import publish_historical_role_delta_v1 as publisher
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify_plan(base, plan)
    if path.resolve() != (previous.package_path.parent / delta.plan_filename(plan)).resolve():
        raise ValueError('original alias SOURCE input is not the release-local exact plan')
    expected, english, _, _ = layered.prepare(base, plan, (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes())
    if english is not None or expected != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited original alias recipe cannot discard changes during SOURCE replay')
    descriptor = path.with_name('original-alias-SOURCE-inert.json')
    retained(descriptor, dict(season=base.season, release_id=base.release_id,
        package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]))
    result = publisher.publish(base.season, descriptor, release_id=release_id,
        source_release_id=base.release_id, ownership_plan_path=path)
    rebuilt = registry.load_registered_release(base.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != pipeline.read_json_file(previous.package_path):
        raise ValueError('entire original alias SOURCE recipe differs')
    return dict(result, complete_game_inventory_identical=True, complete_recipe_identical=True)
