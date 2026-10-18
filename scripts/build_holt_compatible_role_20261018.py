"""Replace one proved legacy defensive role set; preserve every other game byte."""
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_source_verified_player_changes_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/Holt2000-compatible-role-v1'
BASE = 'sourced-celtic-original-opening-reserve-20261018-r157a'
RELEASE = 'sourced-compatible-holt-midfield-20261018-r158a'
REPLAY = 'replayed-compatible-holt-midfield-20261018-r158b'


def run():
    if not (ROOT.parent / 'Celtic2000-opening-review-v1/complete-SOURCE-replay.json').exists():
        raise ValueError('parent Celtic source/native/full replay must complete first')
    base = registry.load_registered_release('2000-01', BASE)
    plan = source.prepare(base, ROOT / 'compatible-role-input-v2.json')
    path = ROOT / source.filename(plan)
    retained(path, plan)
    inert = ROOT / 'inert.json'
    retained(inert, dict(season='2000-01', release_id=BASE,
        package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[]))
    if not registry.locator_path('2000-01', RELEASE).exists():
        publisher.publish('2000-01', inert, release_id=RELEASE, source_release_id=BASE,
                          profile_assignment_plan_path=path)
    child = registry.load_registered_release('2000-01', RELEASE)
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    after = (child.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after_eq = (child.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(before, eq, plan) != (after, after_eq) or source.apply(after, after_eq, plan) != (after, after_eq):
        raise ValueError('actual role/native correction or idempotence differs')
    if source.bind(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(child.package_path):
        raise ValueError('actual recipe does not reproduce')
    masks = plan['updates'][0]['native_masks']
    if {i for i, (a, b) in enumerate(zip(before, after)) if a != b} != {m['file_offset'] for m in masks if m['before'] != m['after']}:
        raise ValueError('unselected native player/control byte changed')
    old = {f['path']: f['sha256'] for f in pipeline.read_json_file(base.inventory_path)['files']}
    new = {f['path']: f['sha256'] for f in pipeline.read_json_file(child.inventory_path)['files']}
    if any(old.get(k) != new.get(k) for k in set(old) | set(new) if k != 'DBDAT/JUG98030.FDI'):
        raise ValueError('another game file changed')
    valid = registry.validate_preferred_release('2000-01', release_id=RELEASE, level='playable')
    if not valid['valid']:
        raise ValueError('role child failed playable gate')
    retained(ROOT / 'native-and-unchanged-proof.json', dict(season='2000-01', release_id=RELEASE,
        source_release_id=BASE, carrier_id=12209, before_roles=[3, 5, 98, 98, 98, 98],
        after_roles=[9, 98, 98, 98, 98, 98], changed_native_bytes=sum(a != b for a, b in zip(before, after)),
        all_other_native_bytes_game_files_and_recipe_fields_unchanged=True, playable_validation=valid,
        scope='Original row/firstfixture confirms exact11689 identity, published biography supplies compatible midfield role; not exacteditionFIFA proof. Other eight original Holt actors already compatible and unchanged.'))
    if not (ROOT / 'complete-SOURCE-replay.json').exists():
        if registry.locator_path('2000-01', REPLAY).exists():
            raise ValueError('unreceipted SOURCE child exists; inspect without regeneration')
        retained(ROOT / 'complete-SOURCE-replay.json', source.reconstruction(child, REPLAY))
    print('Holt sole incompatible role actual native + full SOURCE PASS; private, runtime/promotion pending', flush=True)


if __name__ == '__main__':
    run()
