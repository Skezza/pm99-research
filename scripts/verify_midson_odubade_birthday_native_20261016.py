"""Independent literal native readback, without invoking the birthday writer."""
import copy
from datetime import date

from scripts import season_kit_render_bindings_v1
from app.fdi_indexed import IndexedFDIFile
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained
from scripts.build_midson_odubade_birthdays_20261016 import ROOT, RELEASE, TARGETS


def verify(season):
    root = ROOT / season
    plan = pipeline.read_json_file(root / 'birthday-plan.json')
    base = registry.load_registered_release(season, plan['release_id'])
    actual = registry.load_registered_release(season, RELEASE)
    old = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    new = (actual.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    row = plan['updates'][0]; carrier = row['carrier_id']
    entry = next(e for e in IndexedFDIFile.from_bytes(new).entries if e.record_id == carrier)
    payload = entry.decode_payload(new)
    native = roster.native_player(payload, carrier)
    end = native['name_end']
    observed = date(int.from_bytes(bytes(v ^ 0x61 for v in payload[end+14:end+16]), 'little'),
                    payload[end+13] ^ 0x61, payload[end+12] ^ 0x61).isoformat()
    allowed = set(range(entry.payload_offset + end + 12, entry.payload_offset + end + 16))
    changed = {i for i, (a, b) in enumerate(zip(old, new)) if a != b}
    if (len(old) != len(new) or not changed or not changed <= allowed
            or observed != row['birth_date'] or native['name'] != row['native_name']):
        raise ValueError('independent target name/literal birthday/unchanged-byte readback failed')
    before = pipeline.read_json_file(base.package_path)
    after = pipeline.read_json_file(actual.package_path)
    expected_players = copy.deepcopy(before['players'])
    player = next(p for p in expected_players if p['carrier_id'] == carrier)
    player['facts']['birth_date'] = row['birth_date']
    if 'fact_fallbacks' in player:
        player['fact_fallbacks'] = [f for f in player['fact_fallbacks'] if f['field'] != 'birth_date']
    if expected_players != after['players'] or before['clubs'] != after['clubs']:
        raise ValueError('independent whole player/club recipe preservation failed')
    left = {r['path']: r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right = {r['path']: r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if {k for k in set(left) | set(right) if left.get(k) != right.get(k)} != {'DBDAT/JUG98030.FDI'}:
        raise ValueError('independent game inventory preservation failed')
    retained(root / 'independent-literal-readback.json', dict(season=season, release_id=RELEASE,
        manifest_sha256=actual.manifest_sha256, carrier_id=carrier, native_name=native['name'],
        actual_literal_birth_date=observed, actual_changed_offsets=sorted(changed),
        writer_not_called=True, all_other_native_bytes_identical=True,
        all_other_player_facts_skills_names_clubs_identical=True, all_non_JUG_game_files_identical=True,
        source_plan_sha256=registry.sha256_file(root / 'birthday-plan.json')))
    print(dict(season=season, independently_read_literal_birth_date=observed), flush=True)


if __name__ == '__main__':
    for season, *_ in TARGETS:
        verify(season)
