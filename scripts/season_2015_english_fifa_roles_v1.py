"""Source-bound six-role updates for the separate2015 English recipe layer."""
import copy
from scripts import season_exact_fifa_role_delta_v2 as roles
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages
from scripts.season_2015_english_rating_calibration_v3 import overlay, ARTIFACT
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles

SCHEMA='pm99-exact-target-FIFA-English-overlay-six-role-only-v1'
MODE='known-good-baseline-exact-target-FIFA-English-role-only-v1'
filename=roles.filename
apply=roles.apply
prior=roles.prior


def compatible(primary,role):
    # A forward can legitimately have a published RM/LM role; native broad
    # position stays unchanged. This is an explicit supported taxonomy overlap,
    # not an inferred side or permission to turn a striker into a defender.
    return prior.compatible(primary,role) or primary=='F' and role in (6,10)


def prepare(base):
    document,path=overlay(base)
    raw=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(raw).entries}
    source=prior.index(registry.sha256_file(prior.identity.old.FIFA))
    updates=[];skipped=0;protected=0
    for player in document['players']:
        if player.get('policy')=='preserve-existing-mode1':continue
        row=prior.match(player,'2015-16',source)
        if row is None:continue
        labels=[p.strip() for p in row['player_positions'].split(',')]
        if not labels or any(p not in prior.ROLE_MAP for p in labels):raise ValueError('unknown English source role')
        target=list(dict.fromkeys(prior.ROLE_MAP[p] for p in labels))[:6]
        if not compatible(player['facts'].get('primary_position'),target[0]):
            skipped+=1;continue
        carrier=player['carrier_id'];payload=entries[carrier].decode_payload(raw)
        actual=prior.roster.native_player(payload,carrier);end,old=read_indexed_native_roles(payload,carrier)
        born=prior.date(int.from_bytes(bytes(b^0x61 for b in payload[end+14:end+16]),'little'),
            payload[end+13]^0x61,payload[end+12]^0x61).isoformat()
        if (born!=player['facts'].get('birth_date') or actual['position']!=player['facts']['primary_position']
                or prior.roster.normalise(actual['name'])!=prior.roster.normalise(player['name'])):
            raise ValueError('English literal native identity/primary preimage differs')
        target_row=dict(before_native_roles=old,fine_roles=target,source=row)
        safe=roles.preserve_cb_side(target_row);protected+=safe!=target;target=safe
        if [r for r in old if r!=98]==target and player['facts'].get('fine_roles')==target:continue
        updates.append(dict(carrier_id=carrier,player_id=player['id'],name=player['name'],
            before_player_sha256=prior.digest(player),before_native_roles=old,fine_roles=target,
            source=dict(row,edition=16)))
    doc=dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        english_package_sha256=registry.sha256_file(path),updates=updates,skipped_primary_reviews=skipped,
        native_CB_side_preferences_preserved=protected,
        source_bindings=[dict(path=registry.relative_workspace_path(p),sha256=registry.sha256_file(p))
            for p in (path,prior.identity.old.FIFA,registry.ROOT/'scripts/season_exact_fifa_role_delta_v1.py',
                registry.ROOT/'scripts/season_exact_fifa_role_delta_v2.py',registry.ROOT/'scripts/season_2015_english_fifa_roles_v1.py')],
        scope='Only separate2015 English six fine-role bytes and their recipe declarations; RM/LM allowed for an existing forward, broad native position unchanged; all skills, identity/facts, orders, ownership, tactics, managers, images, EXE and foreign main players preserved.')
    doc['transaction_id']=prior.digest(doc)[:24]
    return doc


def verify(base,plan):
    if plan.get('schema')!=SCHEMA or packages.canonical_json_bytes(prepare(base))!=packages.canonical_json_bytes(plan):
        raise ValueError('English role sources/preimage do not reproduce')


def evidence(plan):
    return dict(id=prior.PREFIX+plan['transaction_id'],kind='season-input',relative_path=filename(plan),
        sha256=prior.digest(plan),media_type='application/json')


def updated_english(plan):
    base=registry.load_registered_release(plan['season'],plan['release_id']);document,path=overlay(base)
    if registry.sha256_file(path)!=plan['english_package_sha256']:raise ValueError('English role recipe preimage differs')
    result=copy.deepcopy(document);people={p['carrier_id']:p for p in result['players']}
    for row in plan['updates']:
        player=people[row['carrier_id']]
        if prior.digest(player)!=row['before_player_sha256']:raise ValueError('English role person preimage differs')
        player['facts']['fine_roles']=list(row['fine_roles'])
    result['artifacts'].append(evidence(plan));result['artifacts'].sort(key=lambda a:a['id'])
    packages.validate_package(result)
    return result


def bind(package,plan):
    updated=updated_english(plan);result=copy.deepcopy(package)
    artifact=next(a for a in result['artifacts'] if a['id']==ARTIFACT)
    artifact['sha256']=prior.digest(updated)
    result['artifacts'].append(evidence(plan));result['artifacts'].sort(key=lambda a:a['id'])
    packages.validate_package(result)
    return result


def reconstruction(previous,release_id):
    relative=previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative:return None
    path=registry.ROOT/relative;plan=pipeline.read_json_file(path)
    if plan.get('schema')!=SCHEMA:return None
    from scripts import publish_historical_role_delta_v1 as publisher
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    if (bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(previous.package_path)
            or updated_english(plan)!=overlay(previous)[0]):raise ValueError('English role SOURCE would discard edits')
    artifact=next(a for a in pipeline.read_json_file(previous.package_path)['artifacts'] if a['id']==evidence(plan)['id'])
    if path.resolve()!=(previous.package_path.parent/filename(plan)).resolve() or registry.sha256_file(path)!=artifact['sha256']:
        raise ValueError('English role SOURCE artifact differs')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('English role SOURCE descriptor differs')
    for r in (base,previous):pipeline.assert_tree_matches_inventory(r.game_path,pipeline.read_json_file(r.inventory_path))
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if (pipeline.read_json_file(rebuilt.package_path)!=pipeline.read_json_file(previous.package_path)
            or overlay(rebuilt)[0]!=overlay(previous)[0]):raise ValueError('English role full SOURCE recipe differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,complete_recipe_identical=True)
