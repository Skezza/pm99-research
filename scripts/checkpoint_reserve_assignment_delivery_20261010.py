"""Checkpoint delivered cases without resetting the fixed 82-case baseline."""
import copy
from datetime import UTC, datetime
import json
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / '.local/consolidated-audit-20261009'


def binding(path):
    return {'path': registry.relative_workspace_path(path),
            'sha256': registry.sha256_file(path)}


def run():
    previous = AUDIT / 'release-delivery-checklist-v3.json'
    original = json.loads(previous.read_text())
    result = copy.deepcopy(original)
    cases = {r['id']: r for r in result['within_club_cases']}
    evidence = AUDIT / 'reserve-assignment-delivery'
    native = json.loads((evidence / 'native-byte-proof-v1.json').read_text())
    replay = json.loads((evidence / 'rebuild-proof-v2.json').read_text())
    profiles = json.loads((evidence / 'live-profile-proof-v1.json').read_text())
    changed = set()
    new_repairs = []
    for row in native['rows']:
        season = row['season']
        release = registry.load_preferred_release(season)
        if release.release_id != row['release_id']:
            raise ValueError('checkpoint baseline changed; use a new checkpoint version')
        if not row['all_player_bytes_unchanged'] or not row['whole_native_idempotence']:
            raise ValueError('native byte evidence did not pass')
        if not registry.validate_preferred_release(season, level='playable')['valid']:
            raise ValueError('current changed game integrity failed')
        if registry._validate_runtime_attestation(release):
            raise ValueError('current changed game lacks exact runtime attestation')
        repeats = [r for r in replay['rows'] if r['season'] == season]
        screens = [r for r in profiles['rows'] if r['season'] == season]
        if (len(repeats) != 1 or not repeats[0]['complete_game_inventory_identical']
                or not repeats[0]['complete_recipe_identical'] or len(screens) != 1
                or not screens[0]['all_nine_uploaded_hashes_match']
                or not screens[0]['original_image_visually_inspected']):
            raise ValueError('missing identical rebuild or genuine profile evidence')
        for name in ('screenshot', 'source_plan_binding', 'summary_binding'):
            b = screens[0][name]
            if registry.sha256_file(ROOT / b['path']) != b['sha256']:
                raise ValueError('live evidence changed')
        plan = json.loads((release.package_path.parent /
                           'sourced-profile-assignment-pruning.json').read_text())
        for fixed in plan['fixed_cases']:
            case = cases[fixed['id']]
            if case['status'] != 'open-source-and-ownership-review':
                raise ValueError('case already disposed; cannot count twice')
            case['status'] = 'confirmed-fault-repaired-current-game'
            case['delivery'] = dict(release_id=release.release_id,
                source_plan=binding(release.package_path.parent /
                                    'sourced-profile-assignment-pruning.json'),
                native_proof=binding(evidence / 'native-byte-proof-v1.json'),
                replay_proof=binding(evidence / 'rebuild-proof-v2.json'),
                live_profile_proof=binding(evidence / 'live-profile-proof-v1.json'),
                runtime_attestation=binding(evidence /
                    ('current-runtime-attestation-' + season + '-v1.json')),
                scope='Duplicate reserve roster links and corresponding recipe assignments only; all native player bytes unchanged.')
            new_repairs.append(case['id'])
        changed.add(season)
    namesake_path = AUDIT / 'original-first-XI-namesake-dispositions-v1.json'
    namesakes = json.loads(namesake_path.read_text())
    for row in namesakes['rows']:
        case = cases[row['case_id']]
        if case['status'] != 'open-source-and-ownership-review' or not row['duplicate_suspicion_cleared']:
            raise ValueError('invalid new namesake disposition')
        case['status'] = 'legitimate-namesakes-source-proved'
        case['delivery'] = dict(evidence=binding(namesake_path),
            scope='Distinct original numeric identities both in the first XI; preserve both. Existing fact/role/photo queues remain.',
            native_date_disagreements=row['native_date_disagreements'])
    old = {b['season']: b for b in original['current_release_bindings']}
    current = []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        b = dict(season=season, release_id=release.release_id,
            manifest_sha256=registry.sha256_file(release.release_manifest_path),
            inventory_sha256=registry.sha256_file(release.inventory_path),
            package_sha256=registry.sha256_file(release.package_path),
            layers=[dict(label='main', path=str(release.package_path),
                         sha256=registry.sha256_file(release.package_path))])
        if season not in changed and b != old[season]:
            raise ValueError('unrelated current release binding changed')
        current.append(b)
    progress = result['within_club_progress']
    progress.update(confirmed_faults_repaired=15, disposed=62,
        legitimate_namesake_cases=21, open_real_club_cases=20)
    if len(cases) != 82 or len(new_repairs) != 14 or len(namesakes['rows']) != 4:
        raise ValueError('fixed-baseline count drift')
    if sum(c['status'] == 'open-source-and-ownership-review' for c in cases.values()) != 20:
        raise ValueError('open case count differs')
    proof = dict(schema='pm99-current26-reserve-assignment-incremental-proof-v1',
        utc=datetime.now(UTC).isoformat(), fresh_all26_sweep=False,
        previous_current26_proof=binding(AUDIT / 'maccabi-name-delivery/current26-binding-proof.json'),
        changed_seasons_fresh_runtime_attested=sorted(changed),
        unchanged22_exact_bindings=[s for s in registry.supported_seasons() if s not in changed],
        current_release_bindings=current)
    proof_path = evidence / 'current26-binding-proof-v1.json'
    pipeline.write_canonical_json(proof_path, proof)
    result.update(utc=proof['utc'], previous_checklist=binding(previous),
        current_release_bindings=current,
        fresh_runtime_runs_this_checklist=sorted(changed),
        next_batch='Remaining 20 real-club cases: deliver Bursa2002 positive numeric-identity reserve proof, then source-bound starter/legacy/club-label cases; other original required queues remain.',
        all_required_work_complete=False)
    result['delivered_evidence'].extend(binding(p) for p in (
        evidence / 'native-byte-proof-v1.json', evidence / 'live-profile-proof-v1.json',
        evidence / 'rebuild-proof-v2.json', namesake_path, proof_path))
    output = AUDIT / 'release-delivery-checklist-v4.json'
    pipeline.write_canonical_json(output, result)
    print(json.dumps(dict(checklist=binding(output), within_club_progress=progress)))


if __name__ == '__main__':
    run()
