"""Prove distinct namesakes actually appearing together in the first XI.

Two generated birth dates do not suffice. Require two distinct original match
IDs, source-bound recipe assignments and original profile birthdays. Native
date disagreements are reported separately, never silently approved here.
"""
from scripts import review_profile_addition_duplicate_assignments_v1 as sources
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

SCHEMA = 'pm99-original-positive-first-XI-distinct-namesake-review-v1'


def distinct_profiles(rows):
    if (len(rows) != 2 or len({r['source_player_id'] for r in rows}) != 2
            or any(not r.get('published_birth_date') for r in rows)
            or len({r['published_birth_date'] for r in rows}) != 2):
        raise ValueError('two distinct numeric profiles with different literal birthdays required')


def prepare(release, case, extra_root, extra_receipt, *, allow_recipe_birthday_conflicts=False):
    if release.season != case['season']:
        raise ValueError('namesake case season differs')
    package = pipeline.read_json_file(release.package_path)
    club = next(c for c in package['clubs'] if c['id'] == case['club_id'])
    ids = {p['carrier_id'] for p in case['players']}
    people = [p for p in package['players'] if p['carrier_id'] in ids]
    if len(people) != 2 or any(p['club_id'] != club['id'] for p in people):
        raise ValueError('namesakes not two exact current recipe club identities')
    root = registry.ROOT / '.local/transfermarkt-opening-plans-current-v1' / release.season
    pre_path = root / 'opening-squad-preallocation.json'
    artifact = next(a for a in package['artifacts'] if a['id'] == 'opening-squad-preallocation-' + release.season)
    if artifact['sha256'] != registry.sha256_file(pre_path):
        raise ValueError('namesake assignment artifact differs')
    pre = pipeline.read_json_file(pre_path)
    cap, annual = sources.bound_annual_capture(release, club, pre, root)
    def selected(c):
        return all(c[k] == cap[k] for k in ('club_name', 'country_catalog', 'competition_catalog'))
    projections = [c for c in pre['source_clubs'] if selected(c['selector'])]
    lineup_path = root / 'opening-lineups.json'
    lineup = pipeline.read_json_file(lineup_path)
    matches = [c for c in lineup['clubs'] if selected(c['source_selector'])]
    if len(matches) != 1 or len(projections) != 1:
        raise ValueError('namesakes require one exact selected original club')
    witness = sources.opening.verify_opening(matches[0], lineup, root / 'cache')
    projection = projections[0]
    if not projection['opening_xi_complete'] or projection['opening_fixture_date'] != witness['date']:
        raise ValueError('namesake projection first fixture differs')
    raw_match, _ = sources.opening.verified_page(root / 'cache', lineup['source']['cache_files'], matches[0]['lineup_source_url'])
    person_path = root / 'opening-lineup-person-evidence.json'
    person_doc = pipeline.read_json_file(person_path)
    extra = pipeline.read_json_file(extra_receipt)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    owners = sources.ownership.native_owners(eq)
    _, _, roster = sources.native.roster_rows(eq, club['carrier_id'])
    rows = []
    for person in people:
        assigned = [p for p in projection['players']
            if 'person-source-' + p['source_row_sha256'] == person['person_id']]
        if len(assigned) != 1 or not assigned[0].get('opening_source_player_id'):
            raise ValueError('namesake lacks one explicit first-match input assignment')
        row = assigned[0]
        id = row['opening_source_player_id']
        if id not in witness['starting_xi']:
            raise ValueError('namesake not positively published in original first XI')
        slug = sources.identity.original_person_links(raw_match, {id})[id]
        name = sources.identity.key(row['facts']['name'])
        if name != sources.identity.key(person.get('source_name', person['name'])):
            raise ValueError('namesake input/current full source name differs')
        candidates = []
        for cache_root, receipt in ((root / 'person-cache', person_doc['source']), (extra_root, extra)):
            urls = [r['url'] for r in receipt['cache_files'] if '/'+slug+'/profil/spieler/'+id == r['url'].removeprefix('https://www.transfermarkt.co.uk').rstrip('/')]
            for url in urls:
                raw, proof = sources.opening.verified_page(cache_root, receipt['cache_files'], url)
                candidates.append((raw, proof))
        if len(candidates) != 1:
            raise ValueError('namesake requires one independently bound original numeric profile')
        raw, proof = candidates[0]
        profile = sources._profile_facts(raw, player={'source_player_id': id})
        if sources.identity.key(profile['published_full_name']) != name:
            raise ValueError('original namesake full profile name differs')
        born = person['facts']['birth_date']
        if isinstance(born, str) and born != profile['published_birth_date'] and not allow_recipe_birthday_conflicts:
            raise ValueError('literal recipe birthday contradicts original numeric profile')
        carrier = person['carrier_id']
        if owners.get(carrier) != {club['carrier_id']} or roster.count((carrier, 0)) != 1:
            raise ValueError('namesake native club ownership is not exact')
        actual = sources.facts.native_facts(jug, carrier)
        rows.append(dict(carrier_id=carrier, recipe_person=person, source_player_id=id,
            published_full_name=profile['published_full_name'], published_birth_date=profile['published_birth_date'],
            original_profile=proof, original_assignment=row, native_before=actual,
            native_birthday_matches=actual['birth_date'] == profile['published_birth_date'],
            recipe_birthday_matches=born == profile['published_birth_date']))
    distinct_profiles(rows)
    return dict(schema=SCHEMA, case_id=case['id'], season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),
        jug_sha256=registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
        club_id=club['id'], original_annual_source=annual, first_fixture=witness, players=rows,
        source_bindings=[sources.binding(pre_path), sources.binding(lineup_path), sources.binding(person_path), sources.binding(extra_receipt)],
        duplicate_suspicion_cleared=all(r['recipe_birthday_matches'] for r in rows), positive_first_fixture_membership_proved=True,
        recipe_date_disagreements=[r['carrier_id'] for r in rows if not r['recipe_birthday_matches']],
        native_date_disagreements=[r['carrier_id'] for r in rows if not r['native_birthday_matches']],
        native_writes=0, scope='Distinct actual first-XI identities; not approval of all player facts, fine roles, stats or photos. Any listed native birthday disagreement remains to fix.')
