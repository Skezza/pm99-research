"""Capture retained remote inputs and assemble reviewed profile evidence.

This evidence-only probe never changes a release or publication catalogue.
Use --reviewed only after directly viewing the final profile screenshot.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts.season_within_club_reserve_repair_v1 import native_facts
from scripts.season_pipeline_v2 import assert_tree_matches_inventory


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f'Refusing to replace evidence: {path}')
    path.write_text(json.dumps(data, sort_keys=True) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('season', choices=['2005-06', '2006-07'])
    parser.add_argument('--reviewed', action='store_true')
    args = parser.parse_args()
    season = args.season
    person, carrier, club, primary, role = (
        ('guardalben', 4267, 'Palermo', 0, 'KEEPER') if season == '2005-06'
        else ('ventola', 14677, 'Atalanta', 8, 'CENTRE FORWARD'))
    tag = f'italian_r55_{season.replace("-", "_")}_{person}_profile_recovery_20261008'
    release = 'sourced-italian-opening-primary-roles-20261008-r55a'
    locator_path = Path(f'.local/season-release-registry-v1/releases/{season}/{release}/locator.json')
    locator = json.loads(locator_path.read_text())
    game = Path(locator['game_path'])
    output = Path(f'.local/opening-xi-repairs-20261008/italian-delivery/{season}')
    runtime = Path(f'.local/italian-delivery/runtime/{tag}/{tag}')
    remote = f'/home/joe/pm99-runner/namespaces/pm99-research-main/workspace/runs/{tag}/game-merged/'
    files = ['MANAGPRE.EXE'] + ['DBDAT/' + file for file in (
        'JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF',
        'BIGCAMP.PKF', 'BIGESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF')]
    proof_path = output / f'{person}-r55-recovery-remote-input-proof.json'
    if not proof_path.exists():
        result = subprocess.run(['ssh', '-o', 'BatchMode=yes', 'joe@192.168.1.175',
                                 'sha256sum ' + ' '.join(remote + file for file in files)],
                                check=True, text=True, capture_output=True)
        observed = {line.split()[1].removeprefix(remote): line.split()[0]
                    for line in result.stdout.splitlines()}
        expected = {file: digest(game / file) for file in files}
        assert observed == expected, (observed, expected)
        save(proof_path, dict(run_tag=tag, season=season, release_id=release,
             sha256=observed, raw_remote_sha256sum=result.stdout,
             all_visible_input_hashes_match_candidate=True,
             remote_visible_source='SSH independently re-read retained run game-merged',
             utc_time=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    if not args.reviewed:
        print(proof_path)
        return
    verified_inventory = assert_tree_matches_inventory(
        game, json.loads(Path(locator['inventory_path']).read_text()))
    summary_path = runtime / 'summary.json'
    summary = json.loads(summary_path.read_text())
    assert summary['success'] and summary['player_profile']['expected_name_token_satisfied']
    shot = runtime / 'screens' / Path(summary['player_profile']['screenshot']).name
    assert shot.is_file()
    jug = (game / 'DBDAT/JUG98030.FDI').read_bytes()
    entries = [entry for entry in IndexedFDIFile.from_bytes(jug).entries if entry.record_id == carrier]
    assert len(entries) == 1
    role_offset, roles = read_indexed_native_roles(entries[0].decode_payload(jug), carrier)
    assert roles[0] == primary, roles
    native = native_facts(jug, carrier)
    save(output / f'{person}-r55-recovery-final-profile-proof.json', dict(
        schema_version='pm99-Italian-final-affected-profile-proof-v1',
        season=season, release_id=release, run_tag=tag, carrier_id=carrier,
        native_identity=native, native_roles=dict(name_end=role_offset, roles=roles), profile_passed=True,
        visually_verified=True, visible_review=dict(club=club, role=role),
        wrapper_success=True, offer_submitted=False, XI_screen_proof=False,
        gameplay_proof=False, source_game_files_changed=False,
        post_run_inventory_verified=True,
        post_run_inventory_fingerprint=verified_inventory['files_fingerprint'],
        screenshot_path=str(shot), screenshot_sha256=digest(shot),
        runner_summary_path=str(summary_path), runner_summary_sha256=digest(summary_path),
        remote_input_proof_path=str(proof_path), remote_input_proof_sha256=digest(proof_path),
        release_manifest_sha256=digest(Path(locator['release_manifest_path'])),
        game_inventory_fingerprint=locator['game_inventory_fingerprint'],
        utc_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        machine='joe-Vostro-3350', source_session='01a0592d-fcd5-7262-a637-743a8253d9b4'))


if __name__ == '__main__':
    main()
