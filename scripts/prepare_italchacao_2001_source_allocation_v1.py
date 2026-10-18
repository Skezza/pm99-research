"""Replay the approved August cup XI and friendly additions into fixed16.

Source-only allocation: no release registration or duplicate closure. Current
publisher attributes are not historical membership or opening-position proof.
"""
import copy
import re
from pathlib import Path
from bs4 import BeautifulSoup

from scripts import italchacao_2001_original_august_v1 as opening
from scripts import bidoglio_original_birthday_resolution_v1 as birthday
from scripts import season_august_source_fallback_v1 as fallback
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_historical_roster_audit_v1 as roster
from scripts.capture_tachira_2014_original_people_v1 import source_rows

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1'
POLICY = 'approved-original-August-cup-XI-and-friendly-additions-fixed16-v1'
KEYS = ['italchacao-2001-original-official-august-match',
    'italchacao-2001-original-official-opening-friendly',
    'italchacao-2001-original-official-calendar',
    'italchacao-2001-original-first-league-result']
# Broad deployment inferred from the two literal reports. This is expressly
# editorial where the report omits role headings, not imported current roles.
ROLES = {350368:'G', 77943:'D', 147691:'D', 140127:'D', 954596:'D',
    824124:'M', 172115:'M', 140144:'M', 880823:'M', 511731:'M', 72532:'F',
    350175:'M', 347836:'M', 123498:'M', 351335:'D', 112276:'F'}


def original_people():
    sources = [source_rows(key) for key in KEYS]
    actual = opening.parse(*(row[1] for row in sources))
    path = ROOT / 'italchacao-2001-original-person-candidates-v1.json'
    document = pipeline.read_json_file(path)
    people.merge({}, document)
    joined = opening.join_people(actual, document)
    resolutions = [source_rows(key) for key in birthday.KEYS]
    resolved = birthday.parse(*(row[1] for row in resolutions))
    persons = {p['source_player_id']:p for b in document['batches'] for p in b['people']}
    if persons[347836]['birth_date'] != resolved['birth_date']:
        raise ValueError('Bidoglio independent birthday disagrees with original publisher')
    policy = fallback.lineup(season='2001-02', fixture_date=actual['cup_date'],
        competition='cup', source_binding=sources[0][2], missing_league_xi=True)
    return actual, joined, document, persons, path, [s[2] for s in sources], resolved, [r[2] for r in resolutions], policy


def original_club_id():
    path, raw, binding = source_rows('italchacao-2001-original-linked-identity-catalogue')
    receipt = pipeline.read_json_file(path.with_suffix('.source.json'))
    page = BeautifulSoup(raw, 'html.parser')
    expected = 'https://www.transfermarkt.com/deportivo-italchacao/kader/verein/21800/saison_id/2001/plus/1'
    if (receipt['url'] != expected or page.title is None or
            page.title.get_text(' ', strip=True) != 'Deportivo Italchacao - Detailed squad 01/02 (Detailed view) | Transfermarkt'):
        raise ValueError('original club identity catalogue URL/title/period differs')
    return int(re.search(r'/verein/(\d+)/', expected)[1]), binding


def prepare(output, baseline_release_id=None):
    if output.exists():
        raise ValueError('source-only allocation is immutable')
    actual, joined, document, persons, biography, bindings, resolved, resolution_bindings, policy = original_people()
    club_id, club_binding = original_club_id()
    index, _ = identities.load_identity_snapshot()
    index, review = people.merge(index, document)
    selected = {r['source_player_id'] for r in joined}
    if any(r['player_id'] in selected for r in review['refused']):
        raise ValueError('selected source person disagrees with pinned identity')
    release = (registry.load_registered_release('2001-02', baseline_release_id)
        if baseline_release_id else registry.load_preferred_release('2001-02'))
    layers = list(planner.package_layers(release))
    owners = [(label, package, path, club) for label, package, path in layers
        for club in package['clubs'] if club['carrier_id'] == 2953]
    if len(owners) != 1:
        raise ValueError('native fixed carrier needs exactly one recipe owner')
    layer, package, package_path, club = owners[0]
    if (roster.normalise(club['name']) != roster.normalise('Minervén') or
            any('italchacao' in roster.normalise(c['name']) for _, p, _ in layers for c in p['clubs'])):
        raise ValueError('obsolete club changed or replacement already exists')
    slots = [p for p in package['players'] if p['club_id'] == club['id']]
    if len(slots) != 16:
        raise ValueError('fixed16 capacity changed')
    desired = []
    for n, row in enumerate(joined):
        id = row['source_player_id']
        person = {k:copy.deepcopy(v) for k,v in persons[id].items() if k != 'published_name_variants'}
        desired.append(dict(source_person=person,
            source_player=dict(name=person['name'], birth_date=person['birth_date'], position=ROLES[id],
                nationality=None, height_cm=None, weight_kg=None, shirt_number=None),
            membership='starting_xi' if n < 11 else ('published-August-cup-used-substitute' if n < 14 else 'published-August-friendly-player'),
            raw_evidence=dict(status='raw-source-reparsed', local_path=bindings[0 if n < 14 else 1]['path'],
                source_sha256=bindings[0 if n < 14 else 1]['sha256']),
            source_role_basis=dict(role=ROLES[id], policy='editorial-broad-deployment-from-reparsed-August-reports',
                exact_fine_position_sourced=False, current_roles_imported=False),
            secondary_facts_status='unconfirmed-log-not-inherit-as-source-fact'))
    allocation.validate_opening_birth_dates(desired, actual['cup_date'])
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    fitted = allocation.allocate(jug, slots, desired, display.claims(biography),
        published_families=families.claims(biography, selected),
        opening_slot_orders=allocation.startup_orders(jug, slots), allow_keeper_order_exchange=True)
    outside = []
    for _, p, _ in layers:
        clubs = {c['id']:c['name'] for c in p['clubs']}
        for player in p['players']:
            key = identities.key(player, index)
            if player['club_id'] != club['id'] and key and key[0] == 'published-person' and key[1] in selected:
                outside.append(dict(source_player_id=key[1], carrier_id=player['carrier_id'],
                    club=clubs[player['club_id']], native_recipe_player=player))
    result = dict(schema_version='pm99-private-original-italchacao2001-fixed16-feasibility-v1',
        season='2001-02', policy=POLICY, baseline_release_id=release.release_id, layer=layer,
        baseline_package=dict(path=registry.relative_workspace_path(package_path), sha256=registry.sha256_file(package_path)),
        before_club=club, new_club='Deportivo Italchacao', country='venezuela', transfermarkt_club_id=club_id,
        first_fixture=dict(date=actual['cup_date'], competition='cup', first_league_xi=False),
        original_opening=actual, original_bindings=bindings + resolution_bindings + [club_binding],
        biography_input=dict(path=registry.relative_workspace_path(biography), sha256=registry.sha256_file(biography)),
        desired_people=desired, allocation=fitted, outside_identity_owners=outside,
        source_fallback=policy, birthday_resolution=resolved,
        source_gaps=['First league XI missing; approved August cup XI used.',
            'Cup report does not publish a formation; broad roles inferred from two August reports.',
            'One goalkeeper among16 positively sourced players; no second keeper invented.',
            'Secondary nationality/physical facts not yet reviewed; inherited values are not evidence.'],
        native_writes=0, closed_duplicate_cases=0, publication_authorised=False,
        remaining=['dated manager/ground/kit', 'secondary facts', 'native readback and exclusive ownership',
            'complete SOURCE replay', 'actual runtime and final frozen checkpoint'])
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    result = prepare(ROOT / 'italchacao-2001-fixed16-source-feasibility-v2.json')
    print(dict(people=len(result['desired_people']), outside_owners=len(result['outside_identity_owners']),
        native_writes=0, closed_duplicate_cases=0), flush=True)
