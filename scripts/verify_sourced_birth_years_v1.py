"""Independent source, native-byte and unchanged-recipe proof for DOB repairs."""
import json
from pathlib import Path
from datetime import date

from app.fdi_indexed import IndexedFDIFile
from scripts import season_sourced_birth_years_v1 as source
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.audit_compiled_player_birth_dates_v1 import inspect


def verify(season, release_id, plan_path, output):
    if output.exists():
        raise ValueError('birth-year verification evidence is immutable')
    plan = json.loads(plan_path.read_text())
    from scripts import season_biographic_birth_years_v1 as biographic
    reader = biographic if plan.get('policy') == biographic.POLICY else source
    from scripts import season_cross_period_birth_years_v1 as cross_period
    if plan.get('policy') == cross_period.POLICY:
        reader = cross_period
    from scripts import season_original_person_birth_years_v1 as original_person
    if plan.get('policy') == original_person.POLICY:
        reader = original_person
    base = registry.load_registered_release(season, plan['release_id'])
    release = registry.load_registered_release(season, release_id)
    reader.verify(base, plan)
    saved = registry.ROOT / release.locator['sourced_birth_year_plan_path']
    if json.loads(saved.read_text()) != plan:
        raise ValueError('compiled birth-year plan differs')
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    after = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    if len(before) != len(after):
        raise ValueError('birth-year repair changed native file length')
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(before).entries}
    allowed = set()
    for row in plan['updates']:
        entry = entries[row['carrier_id']]
        old = entry.decode_payload(before)
        native = audit.native_player(old, row['carrier_id'])
        end = native['name_end']
        born = date.fromisoformat(row['birth_date'])
        first = entry.payload_offset + end + 14
        if after[first:first+2] != born.year.to_bytes(2, 'little'):
            raise ValueError('actual stored birth year differs from original source')
        if (old[end+12] ^ 0x61, old[end+13] ^ 0x61) != (born.day, born.month):
            raise ValueError('repair changes more than the birth year')
        allowed.update((first, first+1))
    changed = {i for i, (a,b) in enumerate(zip(before,after)) if a != b}
    if not changed <= allowed:
        raise ValueError('birth-year repair changed other native bytes')
    unchanged = {}
    for name in ('DBDAT/EQ98030.FDI','DBDAT/ENT98030.FDI','DBDAT/MINIFOTO.PKF',
                 'DBDAT/RIDIESC.PKF','DBDAT/MINIESC.PKF','DBDAT/NANOESC.PKF','MANAGPRE.EXE'):
        digest = registry.sha256_file(release.game_path/name)
        if digest != registry.sha256_file(base.game_path/name):
            raise ValueError('birth-year repair changed another native file or executable')
        unchanged[name] = digest
    original = json.loads(base.package_path.read_text())
    package = json.loads(release.package_path.read_text())
    without_new_artifact = dict(package)
    added_artifact = reader.artifact_id(plan) if hasattr(reader, 'artifact_id') else reader.PREFIX+season
    without_new_artifact['artifacts'] = [a for a in package['artifacts'] if a['id'] != added_artifact]
    if without_new_artifact != original:
        raise ValueError('birth-year repair changed unrelated recipe facts or evidence')
    before_readback, after_readback = inspect(original,before), inspect(package,after)
    repaired_ids = {row['carrier_id'] for row in plan['updates']}
    if any(row['carrier_id'] in repaired_ids for row in after_readback['failures']):
        raise ValueError('selected birthday still fails independent native readback')
    if before_readback['failure_count'] - after_readback['failure_count'] != len(plan['updates']):
        raise ValueError('birthday repair count does not match the measured reduction')
    result = {'schema_version':'pm99-sourced-birth-year-independent-readback-v1',
        'season':season,'release_id':release_id,'source_release_id':base.release_id,
        'corrected_birth_years':len(plan['updates']),'native_bytes_changed':len(changed),
        'before_birthday_disagreements':before_readback['failure_count'],
        'after_birthday_disagreements':after_readback['failure_count'],
        'all_other_native_bytes_identical':True,'all_other_recipe_facts_ratings_identical':True,
        'unchanged_native_hashes':unchanged,'source_plan_sha256':registry.sha256_file(saved),
        'JUG_sha256':registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
        'package_sha256':registry.sha256_file(release.package_path),
        'scope':'original sourced modern birth years only; not roster/skills/kit/portrait clearance'}
    pipeline.write_canonical_json(output,result)
    return result
