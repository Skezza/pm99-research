"""Source-only fixed16 allocation, allowing proven missing secondary DOBs.

No native writes or release promotion. Raw dated reports prove membership;
original publisher rows identify people; unknown dates remain explicit gaps.
"""
import copy
import tempfile
from pathlib import Path

from scripts import prepare_monagas_2003_original_people_v1 as opening
from scripts import season_monagas_2003_missing_birthday_v1 as missing
from scripts import season_august_source_fallback_v1 as fallback
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_historical_roster_audit_v1 as roster

ROOT = opening.ROOT
SCHEMA = 'pm99-private-original-monagas2003-fixed16-feasibility-v1'
POLICY = 'original-August-cup-XI-adjoining-opening-players-and-explicit-secondary-gaps-fixed16-v1'
# Editorial broad deployment follows the original August report's groups.
# These are neither current-feed positions nor certified fine-role attributes.
ROLES = ['G', 'D', 'D', 'D', 'D', 'M', 'M', 'M', 'F', 'F', 'F', 'D', 'M', 'F', 'D', 'M']


def prepare(output, baseline_release_id=None):
    if output.exists():
        raise ValueError('original allocation evidence is immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-monagas-source-') as temporary:
        original = opening.prepare(Path(temporary) / 'original-links.json')
    actual = original['original_opening']
    biography = ROOT / 'monagas-2003-original-person-candidates-v1.json'
    document = pipeline.read_json_file(biography)
    persons = {person['source_player_id']: person for batch in document['batches'] for person in batch['people']}
    desired = []
    for role, actor in zip(ROLES, original['people'], strict=True):
        id = actor['source_player_id']
        person = ({key: copy.deepcopy(value) for key, value in persons[id].items()
                   if key != 'published_name_variants'} if id in persons
                  else missing.from_row(copy.deepcopy(actor), copy.deepcopy(original['original_bindings'])))
        if person['birth_date'] is None:
            missing.verify(person)
        desired.append(dict(source_person=person,
            source_player=dict(name=person['name'], birth_date=person['birth_date'], position=role,
                nationality=None, height_cm=None, weight_kg=None, shirt_number=None),
            membership=actor['membership'],
            raw_evidence=dict(status='raw-source-reparsed', local_path=original['original_bindings'][0]['path'],
                source_sha256=original['original_bindings'][0]['sha256']),
            source_role_basis=dict(role=role, policy='editorial-broad-deployment-from-original-August-groups',
                exact_fine_position_sourced=False, current_roles_imported=False),
            secondary_facts_status=dict(birth_date='original-independent-biography' if person['birth_date']
                else 'publisher-explicitly-unpublished-native-date-not-a-person-fact',
                nationality='unreviewed', height='unreviewed', weight='unreviewed')))
    allocation.validate_opening_birth_dates([row for row in desired if row['source_person']['birth_date']], actual['fixture_date'])
    release = (registry.load_registered_release('2003-04', baseline_release_id)
               if baseline_release_id else registry.load_preferred_release('2003-04'))
    layers = list(planner.package_layers(release))
    owners = [(label, package, path, club) for label, package, path in layers
              for club in package['clubs'] if club['carrier_id'] == 2953]
    if len(owners) != 1:
        raise ValueError('native fixed carrier lacks a unique recipe owner')
    label, package, package_path, club = owners[0]
    if (roster.normalise(club['name']) != 'minerven'
            or any(roster.normalise(c['name']) in {'monagas', 'monagas sc', 'monagas sport club'}
                   for _, pkg, _ in layers for c in pkg['clubs'])):
        raise ValueError('obsolete club changed or replacement already represented')
    slots = [person for person in package['players'] if person['club_id'] == club['id']]
    if len(slots) != 16:
        raise ValueError('native fixed16 capacity changed')
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    selected = {actor['source_player_id'] for actor in original['people']}
    fitted = allocation.allocate(jug, slots, desired, display.claims(biography),
        published_families=families.claims(biography, selected & persons.keys()),
        opening_slot_orders=allocation.startup_orders(jug, slots), allow_keeper_order_exchange=True)
    index, _ = identities.load_identity_snapshot()
    index, review = people.merge(index, document)
    if any(row['player_id'] in selected for row in review['refused']):
        raise ValueError('selected original biography conflicts with pinned source identity')
    outside = []
    for _, pkg, _ in layers:
        for player in pkg['players']:
            key = identities.key(player, index)
            # Exact provider ID remains useful for known-ID/unknown-DOB people,
            # even if the older snapshot cannot assign them a DOB identity key.
            explicit = player.get('person_id', '')
            if player['club_id'] != club['id'] and (
                    key and key[0] == 'published-person' and key[1] in selected
                    or explicit in {'person-transfermarkt-' + str(id) for id in selected}):
                outside.append(dict(carrier_id=player['carrier_id'], club_id=player['club_id'], person_id=explicit))
    policy = fallback.lineup(season='2003-04', fixture_date=actual['fixture_date'], competition='cup',
        source_binding=original['original_bindings'][0], missing_league_xi=True)
    report = dict(schema_version=SCHEMA, policy=POLICY, season='2003-04', baseline_release_id=release.release_id,
        layer=label, baseline_package=dict(path=registry.relative_workspace_path(package_path),
            sha256=registry.sha256_file(package_path)), before_club=club, new_club='Monagas SC',
        country='venezuela', transfermarkt_club_id=14596,
        first_fixture=dict(date=actual['fixture_date'], competition='cup', first_league_xi=False),
        original_opening=actual, original_bindings=original['original_bindings'],
        biography_input=dict(path=registry.relative_workspace_path(biography), sha256=registry.sha256_file(biography)),
        desired_people=desired, allocation=fitted, outside_identity_owners=outside, source_fallback=policy,
        source_gaps=actual['source_gaps'] + copy.deepcopy(original['missing_secondary_facts']),
        native_writes=0, closed_duplicate_cases=0, publication_authorised=False,
        remaining=['review/default secondary facts', 'period kit', 'native readback and exclusive ownership',
            'complete SOURCE replay', 'actual target profile and normal startup', 'final frozen checkpoint'])
    pipeline.write_canonical_json(output, report)
    return report


if __name__ == '__main__':
    result = prepare(ROOT / 'monagas-2003-fixed16-source-feasibility-v1.json')
    print(dict(people=len(result['desired_people']), outside_owners=len(result['outside_identity_owners']),
        allocation=len(result['allocation']), native_writes=0), flush=True)
