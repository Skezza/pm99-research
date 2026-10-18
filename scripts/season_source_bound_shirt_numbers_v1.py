"""A source-bound full-layout shirt-byte delta, not another squad compile."""
import copy
import hashlib

from app.indexed_jug_shirt_number import rewrite_indexed_native_shirt_numbers
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages
from scripts import arsenal_2021_shirt_source_v1 as admission

SCHEMA='pm99-original-full-layout-mode0-shirt-number-only-v1'
PREFIX='source-bound-shirt-numbers-'
FILENAME='source-bound-shirt-numbers.json'
MODE='known-good-baseline-source-bound-full-layout-shirt-numbers-v1'


def digest(raw):return hashlib.sha256(raw).hexdigest()
def filename(plan):return FILENAME


def prepare(base):
    original=admission.prepare(base)
    return dict(schema=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI'),
        source_admission=original,updates=original['updates'],
        native_byte_changes=sum(r['before_number']!=r['number'] for r in original['updates']),
        implementation_bindings=[admission.actors.bound(registry.ROOT/path) for path in (
            'scripts/season_source_bound_shirt_numbers_v1.py','scripts/arsenal_2021_shirt_source_v1.py',
            'upstream/pm99-skezmod-db-editor/app/indexed_jug_shirt_number.py')],scope=original['scope'])


def verify(base,plan):
    if plan.get('schema')!=SCHEMA or prepare(base)!=plan:
        raise ValueError('original source shirt numbers/preimage do not independently reproduce')


def bind(package,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    if registry.sha256_file(base.package_path)!=plan['package_sha256'] or pipeline.read_json_file(base.package_path)!=package:
        raise ValueError('shirt recipe preimage changed')
    result=copy.deepcopy(package);by={p['carrier_id']:p for p in result['players']}
    aid=PREFIX+plan['season'];proof=dict(artifact_id=aid,grade='source-receipt')
    if any(a['id']==aid for a in result['artifacts']):raise ValueError('shirt layer already exists')
    for row in plan['updates']:
        p=by[row['carrier_id']]
        if p!=row['before_player']:raise ValueError('shirt target is not exact prior player')
        p['facts']['shirt_number']=row['number'];p['proof']=dict(proof)
        if 'fact_fallbacks' in p:p['fact_fallbacks']=[f for f in p['fact_fallbacks'] if f['field']!='shirt_number']
    result['artifacts'].append(dict(id=aid,kind='season-input',sha256=digest(packages.canonical_json_bytes(plan)),
        media_type='application/json',relative_path=FILENAME))
    result['sources'].append(dict(id=aid+'-source',title='Original first-league numeric shirts and target-season reserve number/DOB rows',
        uri=admission.URL,proof_grade='source-receipt',evidence_artifact_id=aid))
    result['proofs'].append(dict(id='proof-'+aid,artifact_id=aid,grade='source-receipt',
        covers=['selected-full-layout-shirt-numbers-only; other original facts/skills/identities preserved, not re-approved']))
    for key in ('artifacts','sources','proofs'):result[key].sort(key=lambda r:r['id'])
    packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    original=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    original_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if (digest(original),digest(original_eq))!=(plan['jug_sha256'],plan['eq_sha256']) or eq!=original_eq:
        raise ValueError('shirt-only immutable native source changed')
    updates={r['carrier_id']:{k:r[k] for k in ('native_name','before_number','number')} for r in plan['updates']}
    if len(updates)!=len(plan['updates']):raise ValueError('duplicate shirt targets')
    candidate,changes=rewrite_indexed_native_shirt_numbers(original,updates)
    if len(changes)!=plan['native_byte_changes']:raise ValueError('actual shirt byte count differs')
    if jug not in (original,candidate):raise ValueError('shirt delta accepts exact pre/postimages only')
    if rewrite_indexed_native_shirt_numbers(candidate,updates)!=(candidate,[]):raise ValueError('shirt delta not idempotent')
    return candidate,original_eq


def reconstruction(previous,release_id):
    receipt_path=getattr(previous,'compiler_receipt_path',None)
    if receipt_path is None or pipeline.read_json_file(receipt_path).get('compilation_mode')!=MODE:return None
    from scripts import publish_historical_role_delta_v1 as publisher
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    package=pipeline.read_json_file(previous.package_path)
    artifact=next(a for a in package['artifacts'] if a['id']==PREFIX+previous.season)
    if path.resolve()!=(previous.package_path.parent/FILENAME).resolve() or registry.sha256_file(path)!=artifact['sha256']:
        raise ValueError('shirt original input artifact changed')
    if bind(pipeline.read_json_file(base.package_path),plan)!=package:raise ValueError('edited shirt recipe cannot be silently replayed')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    expected=dict(season=previous.season,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[])
    if pipeline.read_json_file(descriptor)!=expected:raise ValueError('shirt reconstruction descriptor differs')
    for release in (base,previous):pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,
        profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=package:raise ValueError('full shirt SOURCE recipe differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,
        complete_recipe_identical=True,reused=False,compilation_mode=MODE)
