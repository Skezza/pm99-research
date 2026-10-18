"""Deliver one dated Celtic reserve correction; never regenerate unaffected games."""
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_opening_identity_exchange_v1 as source
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from scripts.season_within_club_reserve_repair_v1 import native_facts

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/Celtic2000-opening-review-v1'
BASE = 'sourced-norwich-original-opening-reserve-20261018-r154a'
RELEASE = 'sourced-celtic-original-opening-reserve-20261018-r157a'
REPLAY = 'replayed-celtic-original-opening-reserve-20261018-r157b'


def run():
    base = registry.load_registered_release('2000-01', BASE)
    plan = source.prepare(base, ROOT / 'lennon-burchill-request-v3.json')
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
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    after = (child.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after_eq = (child.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(jug, eq, plan) != (after, after_eq) or source.apply(after, after_eq, plan) != (after, after_eq):
        raise ValueError('actual Celtic identity bytes/idempotence differ')
    preserve_other_records(jug, after, {19261})
    old = pipeline.read_json_file(base.package_path)
    new = pipeline.read_json_file(child.package_path)
    if source.bind(old, plan) != new:
        raise ValueError('actual Celtic recipe differs from admitted source plan')
    old_players = {p['carrier_id']: p for p in old['players']}
    new_players = {p['carrier_id']: p for p in new['players']}
    if any(new_players[c] != value for c, value in old_players.items() if c != 19261):
        raise ValueError('unselected recipe player changed')
    observed = native_facts(after, 19261)
    if (observed['name'].casefold() != 'burchill' or observed['birth_date'] != '1980-08-18'
            or observed['position'] != 'F' or observed['startup_order'] != 18):
        raise ValueError('replacement actual native facts/order differ')
    if (native_facts(after, 9130) != native_facts(jug, 9130)
            or old_players[9130] != new_players[9130]):
        raise ValueError('correct Leicester Lennon changed')
    before = {f['path']: f['sha256'] for f in pipeline.read_json_file(base.inventory_path)['files']}
    final = {f['path']: f['sha256'] for f in pipeline.read_json_file(child.inventory_path)['files']}
    allowed = {'DBDAT/JUG98030.FDI', 'DBDAT/MINIFOTO.PKF', 'DBDAT/MINIFOTO/J9619261.BMP'}
    if any(before.get(k) != final.get(k) for k in set(before) | set(final) if k not in allowed):
        raise ValueError('unrelated actual game file changed')
    valid = registry.validate_preferred_release('2000-01', release_id=RELEASE, level='playable')
    if not valid['valid']:
        raise ValueError('actual child not playable')
    retained(ROOT / 'native-and-unchanged-proof.json', dict(season='2000-01', release_id=RELEASE,
        source_release_id=BASE, replaced_carrier=19261, retained_lennon=9130, native_new_person=observed,
        all_unselected_actors_exact=True, all_unselected_player_records_exact=True,
        correct_Leicester_Lennon_exact=True, eq_ent_managers_kits_exe_unchanged=True,
        original_first_XI_and_orders_unchanged=True, playable_validation=valid,
        case_id='47ca91f51d09393fdb65c808c77cc8adf34715d2400f39aedd61587bc6b52c1b'))
    if not (ROOT / 'complete-SOURCE-replay.json').exists():
        if registry.locator_path('2000-01', REPLAY).exists():
            raise ValueError('unreceipted replay exists; inspect without regenerating')
        retained(ROOT / 'complete-SOURCE-replay.json', source.reconstruction(child, REPLAY))
    print('Celtic actual Lennon/Burchill native + full SOURCE replay PASS; private, runtime/promotion pending', flush=True)


if __name__ == '__main__':
    run()
