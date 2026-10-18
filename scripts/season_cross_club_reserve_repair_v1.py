"""Resolve a real cross-club copy using positive, dated senior ownership.

This is not a within-club waiver: the retained club must be different, each
native carrier must have its exclusive declared owner, and the same full-name
and DOB identity must be established independently. Only an unused reserve
carrier can be replaced. No transfer-day or first-XI appearance is invented.
"""
import copy
from datetime import date

from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import season_wikipedia_career_identity_v1 as wiki
from scripts import replay_original_soccerbase_openings_v1 as originals

SCHEMA = 'pm99-source-bound-cross-club-reserve-disposition-v1'
POLICY = 'exact-native-cross-club-copy-positive-interior-year-owner-and-unused-period-reserve-v1'


def identity_key(person):
    return roster.normalise(person.get('source_name') or person['name']), person['facts'].get('birth_date')


def guard_pair(before, keep, first, second, owners, displaced_club, retained_club):
    if (before['carrier_id'] == keep['carrier_id'] or before['club_id'] == keep['club_id']
            or displaced_club['carrier_id'] == retained_club['carrier_id']):
        raise ValueError('cross-club disposition needs two distinct player and club carriers')
    name, birthday = identity_key(before)
    if (identity_key(keep) != (name, birthday) or not isinstance(birthday, str)
            or first['birth_date'] != birthday or second['birth_date'] != birthday
            or any(roster.normalise(n['name']) != roster.normalise(p['name'])
                for n, p in ((first, before), (second, keep)))):
        raise ValueError('cross-club copies lack matching exact full-source-name and native DOB')
    for person, club in ((before, displaced_club), (keep, retained_club)):
        if (owners.get(person['carrier_id']) != {club['carrier_id']}
                or club['roster_player_ids'].count(person['id']) != 1):
            raise ValueError('cross-club copy lacks its one exclusive native and declared owner')
    if first['startup_order'] <= 11 or first['position'] == 'G':
        raise ValueError('cross-club reserve disposition cannot replace a starter or keeper')


def make_plan(release, displaced, retained, replacement_name, replacement_slug,
              duplicate_slug, cache, *, secondary_biography_id=None, output_review=None):
    layers = planner.package_layers(release)
    packages = [p for label, p, _ in layers if label == 'main']
    if len(packages) != 1:
        raise ValueError('cross-club disposition requires one main recipe')
    package = packages[0]
    by_carrier = {p['carrier_id']: p for p in package['players']}
    before, keep = by_carrier[displaced], by_carrier[retained]
    clubs = {c['id']: c for c in package['clubs']}
    club, retained_club = clubs[before['club_id']], clubs[keep['club_id']]
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    first, second = facts.native_facts(jug, displaced), facts.native_facts(jug, retained)
    owners = ownership.native_owners(eq)
    guard_pair(before, keep, first, second, owners, club, retained_club)
    name, birthday = identity_key(before)
    all_players = [p for _, layer, _ in layers for p in layer['players']]
    matching = [p for p in all_players if identity_key(p) == (name, birthday)]
    if {p['carrier_id'] for p in matching} != {displaced, retained}:
        raise ValueError('cross-club identity has additional represented copies; couple all owners first')
    if any(roster.normalise(p.get('source_name') or p['name']) == roster.normalise(replacement_name)
           for p in all_players):
        raise ValueError('proposed opening reserve is already represented')
    capture, annual_proof = facts.annual_capture(release.season, club)
    matching = [p for p in capture['players'] if roster.normalise(p['name']) == roster.normalise(replacement_name)]
    if len(matching) != 1 or matching[0].get('position') not in ('D', 'M', 'F'):
        raise ValueError('replacement needs one full-name period annual outfield identity')
    source = copy.deepcopy(matching[0])
    anchor = release.season[:4] + '-08-01'
    proofs = []
    raw, url = originals.read_original(cache, 'wiki', duplicate_slug, proofs)
    duplicate_person, duplicate_owner = wiki.read(raw, duplicate_slug, url, anchor,
        retained_club['name'], roster.club_group(retained_club),
        expected_name=before.get('source_name') or before['name'], allow_nonperson_infoboxes=True)
    if ((roster.normalise(duplicate_person['name']), duplicate_person['birth_date']) != (name, birthday)
            or roster.normalise(duplicate_owner['owner']['club']) in
                roster.club_names(roster.club_group(club), club['name'], club.get('full_name', ''))):
        raise ValueError('positive duplicate biography does not distinguish the retained historical club')
    raw, url = originals.read_original(cache, 'wiki', replacement_slug, proofs)
    person, owner = wiki.read(raw, replacement_slug, url, anchor, club['name'],
        roster.club_group(club), expected_name=source['name'], allow_nonperson_infoboxes=True)
    if (roster.normalise(person['name']), person['birth_date']) != (
            roster.normalise(source['name']), source.get('birth_date')):
        raise ValueError('reserve biography disagrees with the period annual full name and DOB')
    age = (date.fromisoformat(anchor) - date.fromisoformat(person['birth_date'])).days / 365.2425
    if not 12 <= age <= 50:
        raise ValueError('opening reserve identity is outside the plausible historical age range')
    if secondary_biography_id is not None:
        if type(secondary_biography_id) is not int or secondary_biography_id < 1:
            raise ValueError('secondary biography requires an explicit published numeric identity')
        from scripts import capture_soccerbase_august_squads_v1 as biographies
        from scripts.woking_original_nationalities_v1 import nationality
        raw, profile_url = originals.read_original(cache, 'player', secondary_biography_id, proofs)
        expected_url = ('https://www.soccerbase.com/players/player.sd?player_id='
            + str(secondary_biography_id) + '&season_id=' + str(int(release.season[:4]) - 1870))
        if profile_url != expected_url:
            raise ValueError('secondary biography URL is not the explicit target-season profile')
        bio = biographies.player_profile(raw, fallback_name='', fallback_position='?')
        if (roster.normalise(bio['name']), bio['birth_date']) != (
                roster.normalise(source['name']), source['birth_date']):
            raise ValueError('secondary nationality biography full name and DOB disagree')
        code = nationality(raw)
        if source.get('nationality') and source['nationality'] != code:
            raise ValueError('period annual and literal biography nationalities disagree')
        source['nationality'] = code
        source['unresolved_fields'] = [f for f in source.get('unresolved_fields', []) if f != 'nationality']
    row = dict(layer='main', player_id=before['id'], carrier_id=displaced, club_id=club['id'],
        before=copy.deepcopy(before), retained_owner_player_id=keep['id'], retained_carrier_id=retained,
        retained_owner_club_id=retained_club['id'], owner_evidence=owner,
        duplicate_source_person=duplicate_person, duplicate_owner_evidence=duplicate_owner,
        replacement_opening_evidence=dict(date=anchor, policy=POLICY,
            actual_first_fixture_claimed=False),
        replacement=dict(source_player=source, source_person=person, raw_evidence=annual_proof),
        duplicate_native_before=[first, second])
    document = dict(schema_version=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),
        jug_sha256=registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
        bindings=dict(snapshot=dict(project_url=url), original_profiles=proofs,
            annual_capture=capture, annual_proof=annual_proof,
            profile_cache=registry.relative_workspace_path(cache),
            replacement_slug=replacement_slug, duplicate_slug=duplicate_slug,
            secondary_biography_id=secondary_biography_id),
        updates=[row], unresolved=[], starting_XI_change_authorised=False,
        source_title='Original positive interior-year senior ownership and independent period reserve; exact cross-club native copy',
        proof_covers=['cross-club-native-copy-positive-retained-owner-and-unused-period-reserve'])
    if output_review is not None:
        from scripts import cross_club_replacement_output_v1 as output
        row['source_bound_replacement_output'] = output.review(release.season, club, source, person, output_review)
        document['bindings']['output_review'] = output_review
        document['proof_covers'].append('explicitly-reviewed-first-spell-winger-and-selected-reserve-v3-editorial-ratings')
    return document


def verify_plan(release, plan):
    if plan.get('schema_version') != SCHEMA or len(plan['updates']) != 1:
        raise ValueError('unsupported cross-club reserve disposition')
    row, bindings = plan['updates'][0], plan['bindings']
    actual = make_plan(release, row['carrier_id'], row['retained_carrier_id'],
        row['replacement']['source_player']['name'], bindings['replacement_slug'],
        bindings['duplicate_slug'], registry.ROOT / bindings['profile_cache'],
        secondary_biography_id=bindings['secondary_biography_id'], output_review=bindings.get('output_review'))
    if pipeline.canonical_json_bytes(actual) != pipeline.canonical_json_bytes(plan):
        raise ValueError('cross-club reserve plan does not independently reproduce from its sources')


def reconstruction(previous, release_id):
    path = previous.locator.get('ownership_plan_path')
    if not path:
        return None
    path = registry.ROOT / path
    plan = pipeline.read_json_file(path)
    if plan.get('schema_version') != SCHEMA:
        return None
    from scripts import publish_historical_role_delta_v1 as publisher
    from scripts import season_duplicate_ownership_delta_v1 as delta
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify_plan(base, plan)
    if path.resolve() != (previous.package_path.parent / delta.plan_filename(plan)).resolve():
        raise ValueError('cross-club SOURCE plan is not the release-local owned input')
    # Check the full expected recipe, not just the selected player's name.
    from scripts import season_duplicate_layered_packages_v1 as layered
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    expected, english, _, _ = layered.prepare(base, plan, original)
    if english is not None or pipeline.read_json_file(previous.package_path) != expected:
        raise ValueError('cross-club SOURCE recipe differs from complete source reconstruction')
    descriptor = path.with_name('cross-club-source-replay-inert.json')
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    retained(descriptor, dict(season=plan['season'], release_id=base.release_id,
        package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]))
    result = publisher.publish(plan['season'], descriptor, release_id=release_id,
        source_release_id=base.release_id, ownership_plan_path=path)
    rebuilt = registry.load_registered_release(plan['season'], release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != pipeline.read_json_file(previous.package_path):
        raise ValueError('cross-club SOURCE full recipe differs after replay')
    return result
