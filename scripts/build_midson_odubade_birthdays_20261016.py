"""Deliver only the nine source-admitted birthday fields and exact SOURCE games."""
import argparse
import os
import shutil

from scripts import season_kit_render_bindings_v1
from app.fdi_indexed import IndexedFDIFile
from scripts import season_source_bound_birthday_disagreements_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.inspect_midson_odubade_birthdays_20261016 import ROOT, TARGETS

RELEASE = 'sourced-original-birthday-disagreements-20261016-r114a'
REPLAY = 'replayed-original-birthday-disagreements-20261016-r114b'


def proof(base, actual, plan, root):
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after = (actual.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if source.apply(before, eq, plan) != (after, eq):
        raise ValueError('actual birthday bytes differ from exact source-bound delta')
    index = {e.record_id: e for e in IndexedFDIFile.from_bytes(before).entries}
    row = plan['updates'][0]; entry = index[row['carrier_id']]
    payload = entry.decode_payload(before)
    end = source.admission.roster.native_player(payload, row['carrier_id'])['name_end']
    allowed = set(range(entry.payload_offset + end + 12, entry.payload_offset + end + 16))
    changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
    expected_count = 1 if 'Odubade' in row['before_player']['source_name'] else 2
    if len(before) != len(after) or len(changed) != expected_count or not changed <= allowed:
        raise ValueError('birthday changed unexpected native fields or byte count')
    left = {r['path']: r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right = {r['path']: r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if any(left.get(k) != right.get(k) for k in set(left) | set(right) if k != 'DBDAT/JUG98030.FDI'):
        raise ValueError('birthday changed another game file')
    if source.bind(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(actual.package_path):
        raise ValueError('actual birthday recipe differs from exact admitted correction')
    retained(root / 'native-byte-proof.json', dict(season=base.season, release_id=RELEASE,
        manifest_sha256=actual.manifest_sha256, source_plan_sha256=registry.sha256_file(root / 'birthday-plan.json'),
        carrier_id=row['carrier_id'], native_name=row['native_name'], birth_date=row['birth_date'],
        changed_native_byte_offsets=sorted(changed), changed_native_bytes=len(changed),
        allowed_complete_date_field_offsets=sorted(allowed), all_other_native_bytes_identical=True,
        all_other_game_files_identical=True, complete_recipe_exact=True,
        names_ownership_ten_skills_roles_tactics_managers_portraits_kits_preserved=True))


def build(season):
    root = ROOT / season; root.mkdir(parents=True, exist_ok=True)
    candidates = pipeline.read_json_file(ROOT / 'nine-current-native-candidates.json')['records']
    candidate = next(r for r in candidates if r['season'] == season)
    base = registry.load_registered_release(season, candidate['release_id'])
    path = root / 'birthday-plan.json'
    if path.exists():
        plan = pipeline.read_json_file(path); source.verify(base, plan)
    else:
        plan = source.prepare(base)
        source.bind(pipeline.read_json_file(base.package_path), plan)
        source.apply((base.game_path / 'DBDAT/JUG98030.FDI').read_bytes(),
                     (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes(), plan)
        retained(path, plan)
    descriptor = root / 'inert.json'
    retained(descriptor, dict(season=season, release_id=base.release_id,
        package_sha256=plan['package_sha256'], jug_sha256=plan['jug_sha256'], updates=[], unresolved=[]))
    if not registry.locator_path(season, RELEASE).exists():
        publisher.publish(season, descriptor, release_id=RELEASE, source_release_id=base.release_id,
                          profile_assignment_plan_path=path)
    actual = registry.load_registered_release(season, RELEASE)
    if not (root / 'native-byte-proof.json').exists():
        proof(base, actual, plan, root)
    if not (root / 'complete-SOURCE-replay.json').exists():
        if registry.locator_path(season, REPLAY).exists():
            raise ValueError('unreceipted birthday replay exists; inspect before proceeding')
        retained(root / 'complete-SOURCE-replay.json', source.reconstruction(actual, REPLAY))
    # Existing manager delivery uses this same verified immutable sharing.
    # Keep both paths/data/receipts; do not spend another full recipe per replay.
    rebuilt = registry.load_registered_release(season, REPLAY)
    for a, b in ((actual.package_path, rebuilt.package_path),
                 (actual.game_path / 'DBDAT/JUG98030.FDI', rebuilt.game_path / 'DBDAT/JUG98030.FDI')):
        if registry.sha256_file(a) != registry.sha256_file(b):
            raise ValueError('completed birthday replay sharing has different bytes')
        if a.stat().st_ino != b.stat().st_ino:
            temporary = b.with_name(b.name + '.verified-birthday-link')
            if temporary.exists():
                raise ValueError('unreceipted birthday sharing temporary')
            os.link(a, temporary); os.replace(temporary, b)
    print(dict(season=season, actual_game_built=True, literal_birthday=plan['updates'][0]['birth_date'],
        complete_SOURCE_game_and_recipe_exact=True, preferred_unchanged=True), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons', nargs='*')
    args = parser.parse_args()
    seasons = args.seasons or [r[0] for r in TARGETS]
    if not set(seasons) <= {r[0] for r in TARGETS}:
        raise ValueError('only the nine explicitly admitted seasons may build')
    for season in seasons:
        # Native publisher has its own measured transaction guard as well.
        if shutil.disk_usage(ROOT).free < 8 * 1024**3 + 64 * 1024**2:
            raise ValueError('birthday batch would exhaust the reserved workspace')
        build(season)


if __name__ == '__main__':
    main()
