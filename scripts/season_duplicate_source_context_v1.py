"""Read-only reconstruction of bound duplicate inputs, without appearance scans.

Duplicate decisions use published people, original first fixtures and transfers.
The million-row whole-season appearance join proves none of those decisions;
this explicit loader omits it, while retaining exact snapshot hash/version and
all person/transfer rows. It does not change the legacy snapshot loader.
"""
import collections
import json
from pathlib import Path

from scripts import season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_opening_person_supplement_v1 as supplement
from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase


def load_snapshot(database, receipt_path):
    import duckdb
    receipt = json.loads(receipt_path.read_text()); source = receipt['source']
    expected = source['database_sha256']
    if registry.sha256_file(database) != expected:
        raise ValueError('duplicate snapshot differs from the immutable original pin')
    connection = duckdb.connect(str(database), read_only=True)
    connection.execute("SET memory_limit='256MB'"); connection.execute('SET threads=2')
    try:
        if connection.execute('SELECT * FROM version').fetchall() != [(source['database_version'],)]:
            raise ValueError('duplicate snapshot version differs from its immutable pin')
        people = transfer.person_index(connection.execute(
            'SELECT player_id,name,first_name,last_name,date_of_birth,url FROM players').fetchall())
        events = collections.defaultdict(list)
        for id, day, old, new, old_name, new_name in connection.execute(
                'SELECT player_id,transfer_date,from_club_id,to_club_id,from_club_name,to_club_name '
                'FROM transfers ORDER BY player_id,transfer_date').fetchall():
            if day and old is not None and new is not None:
                events[int(id)].append({'date': day.isoformat(), 'from_club_id': int(old),
                    'to_club_id': int(new), 'from_club': old_name, 'to_club': new_name})
    finally:
        connection.close()
    binding = {'path': registry.relative_workspace_path(database), 'sha256': expected,
        'version': source['database_version'], 'project_url': source['dataset_project_url'],
        'pinned_receipt_path': registry.relative_workspace_path(receipt_path),
        'pinned_receipt_sha256': registry.sha256_file(receipt_path)}
    return people, events, binding


def context(plan, snapshot_people, snapshot_events, snapshot_binding, progress=None):
    report=progress or (lambda stage:None)
    if snapshot_binding != plan['bindings']['snapshot']:
        raise ValueError('source reconstruction snapshot differs from the bound plan')
    release = registry.load_registered_release(plan['season'], plan['release_id'])
    if (registry.sha256_file(release.package_path), registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')) != (
            plan['package_sha256'], plan['jug_sha256']):
        raise ValueError('source reconstruction original release changed')
    report('original-release-rehashed')
    layers = planner.package_layers(release)
    clubs = {c['id']:c for _,p,_ in layers for c in p['clubs']}
    players = {p['id']:p for _,pkg,_ in layers for p in pkg['players']}
    layer_by_id = {p['id']:label for label,pkg,_ in layers for p in pkg['players']}
    carrier_layers = collections.defaultdict(set)
    for label,pkg,_ in layers:
        for p in pkg['players']: carrier_layers[p['carrier_id']].add(label)
    bindings = plan['bindings']; carriers = {c['carrier_id']:c for c in clubs.values()}
    inputs = [(bindings['opening_path'], bindings['opening_sha256'])]
    if bindings.get('supplemental_opening'):
        extra = bindings['supplemental_opening']; inputs.append((extra['path'],extra['sha256']))
    evidence = {}
    for path, expected in inputs:
        path = registry.ROOT/path
        if registry.sha256_file(path) != expected: raise ValueError('bound original opening review changed')
        doc = json.loads(path.read_text()); transfer.verify_opening_sources(doc)
        for row in doc['clubs']:
            club = carriers.get(row['carrier_id'])
            if club and club['name'] == row['club'] and row['status'] == 'original-first-fixture-reparsed':
                evidence[club['id']] = planner.source_evidence(row, doc)
    report('original-opening-reviews-rehashed')
    captures, capture_bindings = roster.load_sources(plan['season'])
    if capture_bindings != bindings['captures']: raise ValueError('bound original squad captures changed')
    previous = registry.ROOT/bindings['review_path']
    if registry.sha256_file(previous) != bindings['review_sha256']: raise ValueError('bound prior roster review changed')
    verifier = roster.SourceVerifier(plan['season'], json.loads(previous.read_text()), capture_bindings)
    report('original-squad-captures-rehashed')
    people, events, _ = public.merge_bound(snapshot_people, snapshot_events, bindings)
    report('original-public-person-and-transfer-inputs-replayed')
    raw_identity_people = people
    if bindings.get('opening_person_supplement_policy') != supplement.POLICY:
        raise ValueError('read-only context requires the explicitly bound original identity supplement')
    people, _ = supplement.extend(people,list(clubs.values()),evidence,captures,verifier)
    report('opening-full-name-DOB-identities-replayed')
    people, _ = soccerbase.bound_people(people,bindings)
    evidence, gaps = soccerbase.attach(bindings,plan['season'],list(clubs.values()),captures,people,events,evidence,
                                       raw_identity_people=raw_identity_people)
    report('original-Soccerbase-sources-replayed')
    return {'release':release,'clubs':clubs,'players':players,'layer_by_id':layer_by_id,
        'carrier_layers':carrier_layers,'people':people,'events':events,'evidence':evidence,
        'captures':captures,'verifier':verifier,'source_gaps':gaps}


def reserves(ctx, club_id):
    cached = ctx.setdefault('reserve_cache',{})
    if club_id not in cached:
        cached[club_id] = planner.verified_replacements(ctx['clubs'][club_id],ctx['evidence'][club_id],
            ctx['captures'],ctx['verifier'],ctx['people'],ctx['events'])
    return cached[club_id]


def actual_starters(ctx, club_id):
    cached = ctx.setdefault('actual_starter_cache',{})
    if club_id not in cached:
        cached[club_id], ctx['native_guard_cache'] = soccerbase.native_starters(
            ctx['release'],ctx['clubs'][club_id],ctx.get('native_guard_cache'))
    return cached[club_id]
