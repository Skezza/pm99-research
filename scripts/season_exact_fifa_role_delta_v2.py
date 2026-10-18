"""Exact-edition roles, retaining native CB side where FIFA gives no side.

V1 is retained unchanged as rejected-trial source authority. A generic CB is
not evidence for changing an existing right-centre role to left-centre.
"""
from scripts import season_exact_fifa_role_delta_v1 as prior
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_package_v2 as packages

SCHEMA = 'pm99-exact-target-FIFA-six-role-only-delta-v2'
MODE = 'known-good-baseline-exact-target-FIFA-role-only-v2'
filename = prior.filename
bind = prior.bind
apply = prior.apply
reject_factory_recipe = prior.reject_factory_recipe


def preserve_cb_side(row):
    """Both native4/5 are central defenders; FIFA CB supplies no laterality."""
    roles = list(row['fine_roles'])
    old = row['before_native_roles']
    if 'CB' in row['source']['player_positions'].split(', ') and 5 in old and 4 not in old:
        roles = [5 if r == 4 else r for r in roles]
    return roles


def prepare(base):
    plan = prior.prepare(base)
    plan.pop('transaction_id')
    people = {p['carrier_id']:p for p in pipeline.read_json_file(base.package_path)['players']}
    rows = []
    protected = 0
    for row in plan['updates']:
        roles = preserve_cb_side(row)
        protected += roles != row['fine_roles']
        row = dict(row, fine_roles=roles)
        active = [r for r in row['before_native_roles'] if r != 98]
        if active == roles and people[row['carrier_id']]['facts'].get('fine_roles') == roles:
            continue
        rows.append(row)
    plan.update(schema=SCHEMA, updates=rows, native_CB_side_preferences_preserved=protected,
        policy='target-edition-FIFA-role-sets-with-existing-CB-side-retained-v2')
    path=registry.ROOT/'scripts/season_exact_fifa_role_delta_v2.py'
    plan['source_bindings'].append(dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path)))
    plan['transaction_id']=prior.digest(plan)[:24]
    return plan


def verify(base,plan):
    if plan.get('schema') != SCHEMA or packages.canonical_json_bytes(prepare(base)) != packages.canonical_json_bytes(plan):
        raise ValueError('conservative role plan no longer reproduces')


def reconstruction(previous,release_id):
    relative=previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative:return None
    path=registry.ROOT/relative;plan=pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA:return None
    from scripts import publish_historical_role_delta_v1 as publisher
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    package=pipeline.read_json_file(previous.package_path)
    if bind(pipeline.read_json_file(base.package_path),plan) != package:
        raise ValueError('conservative role SOURCE would discard recipe edits')
    artifact=next(a for a in package['artifacts'] if a['id']==prior.PREFIX+plan['transaction_id'])
    if path.resolve() != (previous.package_path.parent/filename(plan)).resolve() or registry.sha256_file(path)!=artifact['sha256']:
        raise ValueError('conservative role SOURCE artifact differs')
    for r in (base,previous):pipeline.assert_tree_matches_inventory(r.game_path,pipeline.read_json_file(r.inventory_path))
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor) != dict(season=base.season,release_id=base.release_id,
        package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('conservative role SOURCE descriptor differs')
    publisher.publish(previous.season,descriptor,release_id=release_id,
        source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=package:raise ValueError('conservative role SOURCE recipe differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,complete_recipe_identical=True)
