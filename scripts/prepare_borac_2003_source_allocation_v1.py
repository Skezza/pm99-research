"""Propose a source-bound fixed18 repair; never build or promote a game."""
import copy

from scripts import borac_2003_original_opening_v1 as opening
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_published_person_identity_v1 as biographies
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_historical_roster_audit_v1 as roster

SOURCE_KEYS = ['dekisa-original-borac-htm', 'dekisa-original-12004-htm',
    'borac-2003-original-opening-manager-chronology', 'partizanopedia-2003-original-season']
RESERVE_IDS = [46117, 28703, 35984, 34401, 36047]
DOCUMENTS = ['borac-2003-original-person-candidates-v1.json',
    'borac-2003-original-additional-person-candidates-v1.json']
HISTORIES = ['borac-2003-original-candidate-histories-v1.json',
    'borac-2003-original-additional-candidate-histories-v1.json']
POLICY = 'original-first-XI-used-subs-plus-positive-dated-reserves-fixed18-v1'


def source18():
    sources = [source_rows(key) for key in SOURCE_KEYS]
    actual = opening.parse(*[row[1] for row in sources])
    documents = [pipeline.read_json_file(ROOT.parent / name) for name in DOCUMENTS]
    combined = copy.deepcopy(documents[0])
    for document in documents[1:]:
        combined['batches'] += copy.deepcopy(document['batches'])
        combined['historical_opening_inputs'] += copy.deepcopy(document['historical_opening_inputs'])
    biographies.merge({}, combined)
    for binding in combined['historical_opening_inputs']:
        if registry.sha256_file(registry.ROOT / binding['path']) != binding['sha256']:
            raise ValueError('original identity query input changed')
    persons = {p['source_player_id']: p for b in combined['batches'] for p in b['people']}
    events = {}
    for name in HISTORIES:
        events, review = histories.merge(events, pipeline.read_json_file(ROOT.parent / name))
        if any(r['reason'] == 'original-history-conflicts-with-a-pinned-dated-edge' for r in review['refused']):
            raise ValueError('original dated membership sources conflict')
    matched = []
    for row in actual['starting_xi'] + actual['used_substitutes']:
        candidates = [p for p in persons.values() if roster.normalise(p['name']) == roster.normalise(row['name'])
            and p['birth_date'] == row['birth_date']]
        if len(candidates) != 1:
            raise ValueError('original match name and literal birthday lack one independent person')
        matched.append(dict(source_player_id=candidates[0]['source_player_id'], original_person=row,
            membership='starting_xi' if len(matched) < 11 else 'used-opening-substitute'))
    for id in RESERVE_IDS:
        person = persons[id]
        catalogue = [p for p in actual['annual_identity_catalogue']
            if roster.normalise(p['name']) == roster.normalise(person['name'])
            and p['birth_date'] == person['birth_date']]
        bracket = transfer.transfer_interval(events[id], actual['fixture_date'])
        if (len(catalogue) != 1 or bracket.get('status') != 'recorded-entry-and-exit-bracket-fixture'
                or bracket['source_owner_club_id'] != 2209):
            raise ValueError('reserve identity or positively bracketed opening membership not confirmed')
        matched.append(dict(source_player_id=id, original_person=catalogue[0],
            membership='positive-original-dated-opening-reserve', bracket=bracket))
    if len(matched) != 18 or len({r['source_player_id'] for r in matched}) != 18:
        raise ValueError('positive fixed18 incomplete or repeated')
    bindings = [s[2] for s in sources] + [dict(path=registry.relative_workspace_path(ROOT.parent / name),
        sha256=registry.sha256_file(ROOT.parent / name)) for name in DOCUMENTS + HISTORIES]
    return actual, matched, persons, combined, bindings


def prepare(output, baseline_release_id=None):
    if output.exists():
        raise ValueError('source allocation evidence is immutable')
    actual, matched, persons, combined, bindings = source18()
    biography = ROOT.parent / 'borac-2003-combined-original-identities-v1.json'
    if biography.exists():
        if pipeline.read_json_file(biography) != combined:
            raise ValueError('retained combined original biography changed')
    else:
        pipeline.write_canonical_json(biography, combined)
    index, _ = identities.load_identity_snapshot()
    index, review = biographies.merge(index, combined)
    if review['refused']:
        raise ValueError('original biographies conflict with pinned source identities')
    release = registry.load_registered_release('2003-04', baseline_release_id) if baseline_release_id else registry.load_preferred_release('2003-04')
    layers = list(planner.package_layers(release))
    owners = [(label, package, path, club) for label, package, path in layers
        for club in package['clubs'] if club['carrier_id'] == 706]
    if len(owners) != 1:
        raise ValueError('native706 must have one recipe owner')
    layer, package, path, club = owners[0]
    if club['name'] != 'Becej' or any('borac' in c['name'].casefold() for _, p, _ in layers for c in p['clubs']):
        raise ValueError('stock carrier changed or proposed club already represented')
    slots = [p for p in package['players'] if p['club_id'] == club['id']]
    if len(slots) != 18:
        raise ValueError('fixed native roster capacity changed')
    native = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    desired = []
    for row in matched:
        person = {k: copy.deepcopy(v) for k, v in persons[row['source_player_id']].items() if k != 'published_name_variants'}
        original = row['original_person']
        desired.append(dict(source_person=person, source_player=dict(name=person['name'],
            birth_date=person['birth_date'], position=original['position'], nationality='SRB',
            height_cm=None, weight_kg=None, shirt_number=original['shirt_number']), membership=row['membership'],
            raw_evidence=dict(status='raw-source-reparsed', local_path=bindings[0]['path'], source_sha256=bindings[0]['sha256']),
            source_role_basis=dict(role=original['position'], basis='explicit archived catalogue broad role, not finer position', identity=row),
            secondary_facts_status=dict(nationality='published Scg represented as native YUGOSLAVIA',
                height='unpublished; declared native fallback', weight='unpublished; declared native fallback',
                shirt_number='later catalogue number, not certified opening number', portraits='no inherited portraits')))
    allocation.validate_opening_birth_dates(desired, actual['fixture_date'])
    ids = [r['source_player_id'] for r in matched]
    fitted = allocation.allocate(native, slots, desired, display.claims(biography),
        published_families=families.claims(biography, ids), opening_slot_orders=allocation.startup_orders(native, slots),
        allow_keeper_order_exchange=True)
    outside = []
    for _, p, _ in layers:
        clubs = {c['id']: c['name'] for c in p['clubs']}
        for player in p['players']:
            key = identities.key(player, index)
            if player['club_id'] != club['id'] and key and key[0] == 'published-person' and key[1] in ids:
                outside.append(dict(source_player_id=key[1], carrier_id=player['carrier_id'],
                    club=clubs[player['club_id']], native_recipe_player=player))
    result = dict(schema_version='pm99-private-original-borac2003-fixed18-feasibility-v1', season='2003-04', policy=POLICY,
        baseline_release_id=release.release_id, layer=layer,
        baseline_package=dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path)),
        before_club=club, new_club='Borac Cacak', country='serbia', transfermarkt_club_id=2209,
        original_opening=actual, first_fixture=dict(date=actual['fixture_date']), original_bindings=bindings,
        biography_input=dict(path=registry.relative_workspace_path(biography), sha256=registry.sha256_file(biography)),
        desired_people=desired, allocation=fitted, selected_bench_ids=ids[11:], outside_identity_owners=outside,
        capacity_selection_policy='Original firstXI11/used2 plus five positive bracketed reserves; no invented unused opening bench.',
        role_disagreements=[], native_writes=0, publication_authorised=False,
        remaining=['dated home ground/period kits', 'native readback', 'complete source replay', 'runtime proof'])
    pipeline.write_canonical_json(output, result)
    return result
