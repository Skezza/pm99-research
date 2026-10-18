"""Explicit source-bound foreign roster pruning and complete opening XI layer.

Separate from the frozen complete-graph fixed-count transaction: first remove
source-reviewed stale links from its exact native preimage, then use unchanged
compiler guards. Shared JUG records are never rewritten. Source review is
independently rederived against the immutable source release, not preferred.
"""
import copy
import importlib
import json
from pathlib import Path

from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.eq_roster_pruning import prune_visible_mode1_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_primary_roles
from app.player_initial_order import OrderReplacement, patch_owned_mode1_complete_orders
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA = 'pm99-original-Italian-source-bound-pruning-and-complete-XI-v1'
ROLE_SCHEMA = 'pm99-original-Italian-source-bound-pruning-XI-and-primary-role-v2'
ROLE_POLICY = 'original-source-XI-broad-role-primary-only-R53-plus-defender-central-midfield-conflict-v2'
PREFIX = 'sourced-italian-opening-xi-'
FILENAME = 'sourced-italian-opening-xi.json'
REVIEWERS = {'2006-07': 'scripts.season_atalanta_opening_review_v1',
             '2000-01': 'scripts.season_milan_opening_review_v1',
             '2005-06': 'scripts.season_palermo_opening_review_v1'}


def roster_rows(eq, club_id):
    indexed = IndexedFDIFile.from_bytes(eq)
    entries = [e for e in indexed.entries if e.record_id == club_id]
    if len(entries) != 1:
        raise ValueError('opening layer needs one exact native club')
    entry = entries[0]
    raw = eq[entry.payload_offset:entry.payload_offset + entry.payload_length]
    roster = parse_eq_external_team_roster_payload(raw, {})
    if roster is None or roster.mode_byte != 1 or any(r.flag for r in roster.rows):
        raise ValueError('opening layer supports only visible mode1 rows')
    return indexed, raw, [(r.player_record_id, r.flag) for r in roster.rows]


def reviewed(release, review_path):
    review = json.loads(review_path.read_text())
    module = importlib.import_module(REVIEWERS[release.season])
    if module.prepare(release=release) != review:
        raise ValueError('original Italian source review does not independently reproduce')
    if (review['season'], review['source_release_id'], review['source_package_sha256']) != (
            release.season, release.release_id, registry.sha256_file(release.package_path)):
        raise ValueError('Italian source review baseline differs')
    return review


def conservative_primary_role(position, role):
    from scripts.season_tff_sourced_opening_xi_v1 import conservative_role
    # An explicit local policy correction, not a silent change to frozen R53.
    if position == 'D' and role == 9:
        return 4
    return conservative_role(position, role)


def _primary_role_changes(jug, factory_jug, xi, players):
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    factory = {e.record_id: e for e in IndexedFDIFile.from_bytes(factory_jug).entries}
    changes = []
    for witness in xi:
        id = witness['carrier_id']
        native = facts.native_facts(jug, id)
        position = witness['source']['position']
        if position != native['position'] or players[id]['facts']['primary_position'] != position:
            raise ValueError('source XI primary role needs matching native/recipe broad position')
        _, before = read_indexed_native_roles(index[id].decode_payload(jug), id)
        target = conservative_primary_role(position, before[0])
        if target is None:
            continue
        _, factory_before = read_indexed_native_roles(factory[id].decode_payload(factory_jug), id)
        after = [target] + before[1:]
        recipe_after = [r for r in after if r != 98]
        if len(recipe_after) != len(set(recipe_after)):
            raise ValueError('primary role correction cannot represent repeated secondary roles')
        changes.append({'carrier_id': id, 'player_id': players[id]['id'],
            'native_name': native['name'], 'birth_date': native['birth_date'],
            'source_position': position, 'before': before[0], 'after': target,
            'factory_before': factory_before[0], 'native_roles_before': before,
            'factory_roles_before': factory_before,
            'native_roles_after': after,
            'recipe_fine_roles_before': players[id]['facts'].get('fine_roles'),
            'recipe_fine_roles_after': recipe_after,
            'authority': 'positive original first-XI identity and broad role; conservative primary label is editorial; DOB conflict is not overwritten'})
    return changes


def prepare(release, review_path, *, repair_primary_roles=False):
    review = reviewed(release, review_path)
    package = json.loads(release.package_path.read_text())
    xi = review['approved_XI_identities']
    ids = [r['carrier_id'] for r in xi]
    players = {p['carrier_id']: p for p in package['players']}
    if len(ids) != 11 or len(set(ids)) != 11:
        raise ValueError('opening source must provide eleven distinct carrier identities')
    club = next(c for c in package['clubs'] if c['id'] == players[ids[0]]['club_id'])
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    _, _, before = roster_rows(eq, club['carrier_id'])
    from scripts.finalize_season_release_v1 import DEFAULT_BASE
    factory_jug_path = DEFAULT_BASE / 'DBDAT/JUG98030.FDI'
    factory_eq_path = DEFAULT_BASE / 'DBDAT/EQ98030.FDI'
    factory_jug = factory_jug_path.read_bytes()
    if roster_rows(factory_eq_path.read_bytes(), club['carrier_id'])[2] != before:
        raise ValueError('Italian pruning requires the exact same factory and runtime roster preimage')
    if [id for id, _ in before] != [next(p['carrier_id'] for p in package['players'] if p['id'] == id)
                                   for id in club['roster_player_ids']]:
        raise ValueError('recipe and inspected native roster differ')
    removed = sorted(r['carrier_id'] for r in review['reviewed_link_removals'])
    if len(set(removed)) != len(removed) or set(removed) & set(ids):
        raise ValueError('reviewed removals repeat IDs or remove a source starter')
    after = [row for row in before if row[0] not in removed]
    if not set(removed) <= {id for id, _ in before} or not set(ids) <= {id for id, _ in after}:
        raise ValueError('source identities/removals are outside the exact native target')
    owners = ownership.native_owners(eq)
    native = {id: facts.native_facts(jug, id) for id, _ in after}
    reserves = sorted(set(native) - set(ids), key=lambda id: (native[id]['startup_order'], id))
    orders = [{'carrier_id': id, 'player_id': players[id]['id'], 'native_name': native[id]['name'],
               'birth_date': native[id]['birth_date'], 'position': native[id]['position'],
               'before': native[id]['startup_order'], 'factory_before': facts.native_facts(factory_jug, id)['startup_order'], 'after': n}
              for n, id in enumerate(ids + reserves, 1)]
    output = {'schema_version': SCHEMA, 'season': release.season,
              'source_release_id': release.release_id,
              'source_package_sha256': registry.sha256_file(release.package_path),
              'source_jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
              'source_eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
              'review_path': registry.relative_workspace_path(review_path),
              'review_sha256': registry.sha256_file(review_path),
              'club_id': club['id'], 'club_carrier_id': club['carrier_id'],
              'before_club': club, 'before_rows': [list(r) for r in before], 'after_rows': [list(r) for r in after],
              'factory_binding': {registry.relative_workspace_path(path): registry.sha256_file(path)
                                  for path in (factory_jug_path, factory_eq_path)},
              'removed_player_ids': removed, 'starting_xi': ids, 'orders': orders,
              'removed_source_owners': {str(id): sorted(owners[id]) for id in removed},
              'removed_recipe_players': {str(id): players[id] for id in removed},
              'startup_order_policy': 'reviewed editorial slot order of the original starter set; reserves stable old-order/ID',
              'reserve_opening_membership_approved': False,
              'unrelated_native_records_must_remain_exact': True}
    if repair_primary_roles:
        output['schema_version'] = ROLE_SCHEMA
        output['primary_role_policy'] = ROLE_POLICY
        output['primary_role_changes'] = _primary_role_changes(jug, factory_jug, xi, players)
    candidate_eq = prune(eq, output)
    candidate_jug = order(jug, candidate_eq, output, exact_before=True)
    preserve_other_records(jug, candidate_jug, set(native))
    if order(candidate_jug, candidate_eq, output) != candidate_jug or prune(candidate_eq, output) != candidate_eq:
        raise ValueError('Italian layer is not idempotent')
    return output


def verify(release, plan):
    if plan.get('schema_version') not in (SCHEMA, ROLE_SCHEMA):
        raise ValueError('unsupported Italian opening layer')
    if (release.release_id, registry.sha256_file(release.package_path),
            registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
            registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI')) != (
            plan['source_release_id'], plan['source_package_sha256'],
            plan['source_jug_sha256'], plan['source_eq_sha256']):
        raise ValueError('Italian opening layer baseline changed')
    path = registry.ROOT / plan['review_path']
    registry.relative_workspace_path(path)
    if registry.sha256_file(path) != plan['review_sha256'] or prepare(
            release, path, **({'repair_primary_roles': True} if plan['schema_version'] == ROLE_SCHEMA else {})) != plan:
        raise ValueError('Italian opening plan source review or derived plan changed')


def prune(eq, plan):
    if plan.get('schema_version') not in (SCHEMA, ROLE_SCHEMA):
        raise ValueError('unsupported Italian roster pruning plan')
    club_id = plan['club_carrier_id']
    indexed, raw, actual = roster_rows(eq, club_id)
    before = [tuple(row) for row in plan['before_rows']]
    after = [tuple(row) for row in plan['after_rows']]
    removed = plan['removed_player_ids']
    if (not removed or len(set(removed)) != len(removed)
            or after != [r for r in before if r[0] not in removed]
            or not set(removed) <= {id for id, _ in before}):
        raise ValueError('Italian pruning does not describe the exact reviewed subset')
    if actual == after:
        return eq
    if actual != before:
        raise ValueError('Italian pruning native ordered preimage differs')
    # Existing native compiler is the indexed-container serializer, not a new
    # product implementation in PM99RE. All other decoded records stay exact.
    from scripts import season_package_compiler_v2 as compiler
    changed = prune_visible_mode1_roster_payload(raw, expected_rows=before,
                                               removed_player_ids=removed)
    result = compiler._rebuild_indexed(eq, indexed, {club_id: compiler.xor_decode(changed)})
    preserve_other_records(eq, result, {club_id})
    old_owners, new_owners = ownership.native_owners(eq), ownership.native_owners(result)
    if any(new_owners.get(id, set()) != old_owners.get(id, set()) - {club_id} for id in removed):
        raise ValueError('Italian pruning changed another club ownership link')
    return result


def order(jug, eq, plan, *, exact_before=False):
    if plan.get('schema_version') not in (SCHEMA, ROLE_SCHEMA):
        raise ValueError('unsupported Italian opening layer')
    if plan.get('schema_version') == SCHEMA and plan.get('primary_role_changes'):
        raise ValueError('v1 Italian plan cannot authorize primary role changes')
    _, _, rows = roster_rows(eq, plan['club_carrier_id'])
    if rows != [tuple(r) for r in plan['after_rows']]:
        raise ValueError('Italian startup layer requires its exact pruned roster')
    orders = plan['orders']
    if ({r['carrier_id'] for r in orders} != {id for id, _ in rows}
            or len(orders) != len(rows)
            or [r['after'] for r in orders] != list(range(1, len(rows) + 1))
            or [r['carrier_id'] for r in orders[:11]] != plan['starting_xi']):
        raise ValueError('Italian startup layer is not a complete source-XI permutation')
    replacements = []
    for row in orders:
        native = facts.native_facts(jug, row['carrier_id'])
        if (native['name'], native['birth_date'], native['position']) != (
                row['native_name'], row['birth_date'], row['position']):
            raise ValueError('Italian startup identity/DOB/broad role changed')
        if exact_before and native['startup_order'] != row['before']:
            raise ValueError('Italian startup exact baseline order changed')
        if native['startup_order'] not in {row['before'], row['factory_before'], row['after']}:
            raise ValueError('Italian startup order is outside source/factory/target preimages')
        replacements.append(OrderReplacement(row['carrier_id'], row['native_name'],
                                            native['startup_order'], row['after']))
    # Caller proves original person identities; strict writer still proves all
    # ownership and one-byte-only scope. Cold compile orders may differ from
    # runtime baseline orders and are not falsely labelled exact preimages.
    result = patch_owned_mode1_complete_orders(jug, eq, club_record_id=plan['club_carrier_id'],
                                              replacements=replacements)
    if plan.get('schema_version') == ROLE_SCHEMA:
        result = _apply_primary_roles(result, plan, exact_before=exact_before)
    return result


def _apply_primary_roles(jug, plan, *, exact_before=False):
    if plan.get('primary_role_policy') != ROLE_POLICY:
        raise ValueError('unapproved Italian primary-role policy')
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    updates = {}
    for row in plan['primary_role_changes']:
        id = row['carrier_id']
        native = facts.native_facts(jug, id)
        if id in updates or id not in plan['starting_xi']:
            raise ValueError('primary-role changes require distinct original starters')
        if (native['name'], native['birth_date'], native['position']) != (
                row['native_name'], row['birth_date'], row['source_position']):
            raise ValueError('primary-role identity/DOB/broad position differs')
        if conservative_primary_role(row['source_position'], row['before']) != row['after']:
            raise ValueError('primary role is not the source-compatible conservative correction')
        _, roles = read_indexed_native_roles(index[id].decode_payload(jug), id)
        if exact_before and roles != row['native_roles_before']:
            raise ValueError('primary role exact source window changed')
        if tuple(roles) not in {tuple(row['native_roles_before']),
                tuple(row['factory_roles_before']), tuple(row['native_roles_after'])}:
            raise ValueError('primary role is outside source/factory/target preimages')
        updates[id] = (roles[0], row['after'])
    result, _ = rewrite_indexed_native_primary_roles(jug, updates)
    return result


def bind(package, plan):
    if plan.get('schema_version') not in (SCHEMA, ROLE_SCHEMA):
        raise ValueError('unsupported Italian opening layer')
    if plan.get('schema_version') == ROLE_SCHEMA and plan.get('primary_role_policy') != ROLE_POLICY:
        raise ValueError('unapproved Italian primary-role policy')
    if plan.get('schema_version') == SCHEMA and plan.get('primary_role_changes'):
        raise ValueError('v1 Italian plan cannot authorize primary role changes')
    result = copy.deepcopy(package)
    club = next(c for c in result['clubs'] if c['id'] == plan['club_id'])
    if club != plan['before_club']:
        raise ValueError('Italian recipe club preimage changed')
    removed = set(plan['removed_player_ids'])
    by_id = {p['id']: p for p in result['players']}
    club['roster_player_ids'] = [id for id in club['roster_player_ids'] if by_id[id]['carrier_id'] not in removed]
    if 'shared_preserve_player_ids' in club:
        club['shared_preserve_player_ids'] = [id for id in club['shared_preserve_player_ids'] if id in club['roster_player_ids']]
    for player in result['players']:
        if player['carrier_id'] not in removed or player['club_id'] != club['id']:
            continue
        other = [c for c in result['clubs'] if c['id'] != club['id'] and player['id'] in c['roster_player_ids']]
        if other:
            # Metadata affiliation follows a surviving native owner; never
            # imply that surviving carrier's old fallback is historically fixed.
            player['club_id'] = sorted(other, key=lambda c: c['carrier_id'])[0]['id']
    referenced = {id for c in result['clubs'] for id in c['roster_player_ids']}
    orphan_ids = {p['id'] for p in result['players'] if p['carrier_id'] in removed and p['id'] not in referenced}
    result['players'] = [p for p in result['players'] if p['id'] not in orphan_ids]
    for row in plan.get('primary_role_changes', []):
        player = by_id[row['player_id']]
        if player['facts'].get('fine_roles') != row['recipe_fine_roles_before']:
            raise ValueError('primary-role recipe preimage differs')
        player['facts']['fine_roles'] = list(row['recipe_fine_roles_after'])
    if 'portraits' in result:
        result['portraits'] = [p for p in result['portraits'] if p['player_id'] not in orphan_ids]
    if 'portraits' in result.get('assets', {}):
        result['assets']['portraits'] = [p for p in result['assets']['portraits'] if p['player_id'] not in orphan_ids]
    # Keep old source artifact bytes and references, but stop its conflicting
    # two-slot replay after the full-XI layer supersedes it.
    from scripts import season_mode1_sourced_keeper_slot_v1 as keeper
    old_id = keeper.PREFIX + plan['season'] + '-' + str(plan['club_carrier_id'])
    retained_id = 'retained-' + old_id
    for artifact in result['artifacts']:
        if artifact['id'] == old_id:
            artifact['id'] = retained_id
    def references(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in ('artifact_id', 'evidence_artifact_id') and child == old_id:
                    value[key] = retained_id
                else:
                    references(child)
        elif isinstance(value, list):
            for child in value:
                references(child)
    references(result)
    artifact_id = PREFIX + plan['season'] + '-' + str(plan['club_carrier_id'])
    result['artifacts'].append({'id': artifact_id, 'kind': 'season-input', 'relative_path': FILENAME,
                                'sha256': packages.sha256_bytes(packages.canonical_json_bytes(plan)),
                                'media_type': 'application/json'})
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def layers(package, package_path):
    found = []
    for artifact in package['artifacts']:
        if not artifact['id'].startswith(PREFIX):
            continue
        rel = Path(artifact['relative_path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('unsafe Italian opening artifact path')
        path = package_path.parent / rel
        if registry.sha256_file(path) != artifact['sha256']:
            raise ValueError('Italian recipe-local plan hash changed')
        plan = json.loads(path.read_text())
        if plan['season'] != f"{package['season']['start_year']}-{str(package['season']['end_year'])[-2:]}":
            raise ValueError('Italian opening artifact season differs')
        baseline = registry.load_registered_release(plan['season'], plan['source_release_id'])
        verify(baseline, plan)
        club = next(c for c in package['clubs'] if c['id'] == plan['club_id'])
        carriers = {p['id']: p['carrier_id'] for p in package['players']}
        if [carriers[id] for id in club['roster_player_ids']] != [id for id, _ in plan['after_rows']]:
            raise ValueError('Italian recipe roster changed after source approval')
        old_id = 'mode1-sourced-keeper-slot-' + plan['season'] + '-' + str(plan['club_carrier_id'])
        if any(a['id'] == old_id for a in package['artifacts']):
            raise ValueError('superseded keeper replay is still active')
        baseline_package = json.loads(baseline.package_path.read_text())
        expected = bind(baseline_package, plan)
        expected_club = next(c for c in expected['clubs'] if c['id'] == plan['club_id'])
        if club.get('shared_preserve_player_ids', []) != expected_club.get('shared_preserve_player_ids', []):
            raise ValueError('Italian recipe shared preservation declarations changed')
        people = {p['carrier_id']: p for p in package['players']}
        expected_people = {p['carrier_id']: p for p in expected['players']}
        for id in plan['removed_player_ids']:
            wanted = expected_people.get(id)
            actual = people.get(id)
            if wanted is None and actual is not None:
                raise ValueError('retired exclusive duplicate is still declared in recipe')
            if wanted is not None and (actual is None or actual['club_id'] != wanted['club_id']
                    or actual.get('policy') != wanted.get('policy')):
                raise ValueError('surviving shared player affiliation/preservation changed')
        for row in plan['orders']:
            actual = people.get(row['carrier_id'])
            if actual is None or actual['id'] != row['player_id'] or actual['club_id'] != plan['club_id']:
                raise ValueError('source starter/reserve recipe identity or affiliation changed')
        for row in plan.get('primary_role_changes', []):
            if people[row['carrier_id']]['facts'].get('fine_roles') != row['recipe_fine_roles_after']:
                raise ValueError('source-compatible primary-role recipe changed')
        found.append(plan)
    if len({p['club_carrier_id'] for p in found}) != len(found):
        raise ValueError('multiple Italian opening layers target the same club')
    return found
