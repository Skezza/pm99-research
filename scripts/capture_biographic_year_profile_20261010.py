"""Capture an actual corrected modern age after the seven startup runs finish."""
import subprocess
import time

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_biographic_year_startups_20261010 import ROOT, RELEASE


def main():
    deadline = time.monotonic() + 45 * 60
    while True:
        paths = [ROOT / (f'{year}-{str(year+1)[-2:]}-startup-transport.json')
                 for year in range(2019, 2026)]
        if all(path.exists() for path in paths):
            if any(pipeline.read_json_file(path)['exit_code'] for path in paths):
                raise ValueError('a preceding startup transport failed')
            break
        if time.monotonic() >= deadline:
            raise ValueError('startup batch did not finish within the bounded wait')
        time.sleep(10)
    candidate = ROOT / '2020-21-profile-candidate'
    receipt = pipeline.read_json_file(candidate / 'candidate-receipt.json')
    release = registry.load_registered_release('2020-21', RELEASE)
    if receipt['release_manifest_sha256'] != release.manifest_sha256:
        raise ValueError('age candidate belongs to another release')
    evidence = ROOT / 'runtime/bursik_age_2020_r67a_20261010'
    if evidence.exists():
        raise ValueError('age evidence exists; inspect instead of overwrite')
    command = [str(registry.ROOT / 'scripts/run_stars_player_offer_probe_direct.sh'),
        '--run-tag', 'bursik_age_2020_r67a_20261010',
        '--local-game-dir', str(candidate / 'game'),
        '--local-artifact-dir', str(evidence),
        '--player-search', 'Bursik', '--player-label', 'bursik',
        '--profile-name-token', 'Bursik', '--profile-only',
        '--provenance-file', str(candidate / 'candidate-receipt.json')]
    result = subprocess.run(command, check=False)
    pipeline.write_canonical_json(ROOT / 'bursik-profile-transport.json',
        dict(season='2020-21', release_id=RELEASE, exit_code=result.returncode,
             evidence=registry.relative_workspace_path(evidence),
             visually_approved=False, age_approved=False, installed=False))
    if result.returncode:
        raise ValueError('corrected age profile transport failed')
    print(dict(captured=True, age_approved=False, installed=False), flush=True)


if __name__ == '__main__':
    main()
