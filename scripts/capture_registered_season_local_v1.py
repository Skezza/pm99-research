"""Run current canonical PM99 drivers locally against a disposable release copy.

No database compilation, privileged overlay mounts, remote host or original ZIP
is required. The existing launcher owns the local Docker worker lease.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from scripts import season_disk_budget_v1 as disk_budget
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_registered_season_runtime_v1 import _selector
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

RESERVE = 8 * 1024 ** 3
INITIAL_BUDGET = 2 * 1024 ** 3


def summary_matches(summary, release, *, profile=False, selector=None):
    if summary.get('success') is not True:
        return False
    if profile:
        observed = summary.get('player_profile', {})
        expected = observed.get('expected_name_token')
        name = observed.get('player_name_ocr_normalized')
        if (observed.get('expected_name_token_satisfied') is not True
                or not isinstance(expected, str) or not expected.strip()
                or not isinstance(name, str)):
            return False
        pattern = r'(?<!\w)' + re.escape(expected.strip()) + r'(?!\w)'
        if re.search(pattern, name) is not None:
            return True
        # A narrow name crop can misread a final I as E. The retained header
        # probes independently read the same name on their first line. Never
        # accept a token occurring only in the body of a profile or other UI.
        screen = summary.get('final_screen_classification', {})
        if screen.get('screen') != 'player_profile_screen':
            return False
        for probe in screen.get('probes', []):
            if probe.get('probe_name') not in {'configuration_header', 'name_team_header'}:
                continue
            lines = str(probe.get('raw_text', '')).strip().splitlines()
            if lines and re.search(pattern, lines[0].casefold()) is not None:
                return True
        return False
    team = summary.get('route_summaries', {}).get('line_up', {}).get('team_identity', {})
    if selector is not None:
        coordinates = {key: selector[key] for key in (
            'team_select_x', 'team_select_y', 'division_select_x', 'division_select_y')}
        return (summary.get('release_manifest_sha256') == release.manifest_sha256
                and summary.get('output_inventory_fingerprint') == release.locator['game_inventory_fingerprint']
                and summary.get('phase_reached') == 'return_from_line_up'
                and summary.get('mode') == 'generic-club-route-capture'
                and summary.get('team_name') == selector['team_name']
                and summary.get('team_selection') == coordinates
                and team.get('expected') == selector['team_name']
                and team.get('matched') is True
                and bool(team.get('expected_normalized'))
                and team.get('observed_normalized') == team.get('expected_normalized'))
    return (summary.get('release_manifest_sha256') == release.manifest_sha256
            and summary.get('output_inventory_fingerprint') == release.locator['game_inventory_fingerprint']
            and summary.get('phase_reached') == 'return_from_line_up'
            and team.get('matched') is True
            and 'stoke' in team.get('observed_normalized', '').split())


def validate_selector(release, selector):
    keys = {'club_carrier_id', 'team_name', 'team_select_x', 'team_select_y',
            'division_select_x', 'division_select_y'}
    if not isinstance(selector, dict) or set(selector) != keys:
        raise ValueError('explicit club selector fields required')
    if type(selector['club_carrier_id']) is not int or not isinstance(selector['team_name'], str):
        raise ValueError('exact club selector identity required')
    for key in keys - {'club_carrier_id', 'team_name'}:
        maximum = 640 if key.endswith('_x') else 480
        if type(selector[key]) is not int or not 0 <= selector[key] < maximum:
            raise ValueError('club selector coordinate outside native screen')
    from scripts.season_duplicate_ownership_plan_v1 import package_layers
    clubs = [club for _, package, _ in package_layers(release) for club in package['clubs']
             if club['carrier_id'] == selector['club_carrier_id']]
    if len(clubs) != 1 or clubs[0]['name'] != selector['team_name']:
        raise ValueError('club selector must match one exact registered recipe club')


def driver_args(release, *, carrier=None, label=None, token=None, search_result_row=1, selector=None, search_text=None):
    if search_text is not None:
        if (carrier is None or not isinstance(search_text, str) or not search_text.strip()
                or len(search_text) > 64 or any(ord(c) < 32 for c in search_text)):
            raise ValueError('explicit printable player-search text requires a profile carrier')
        search_text.encode('cp1252')
    if type(search_result_row) is not int or not 1 <= search_result_row <= 10:
        raise ValueError('explicit visible search result row must be 1..10')
    if selector is not None:
        if carrier is not None:
            raise ValueError('club selector cannot be combined with a player profile')
        validate_selector(release, selector)
    if carrier is None:
        s = _selector(release.season) if selector is None else selector
        args = ['python3', '/workspace/repo/scripts/pm99_runner/stoke_season_driver.py',
                '--game-dir', '/workspace/game', '--artifacts-dir', '/workspace/artifacts',
                '--release-manifest-sha256', release.manifest_sha256,
                '--output-inventory-fingerprint', release.locator['game_inventory_fingerprint'],
                '--manager-name', 'AI', '--team-name', s['team_name'],
                '--profile-count', '0', '--capture-routes-only', '--capture-route', 'line_up']
        for flag, key in (('team-select-x', 'team_select_x'), ('team-select-y', 'team_select_y'),
                          ('division-select-x', 'division_select_x'), ('division-select-y', 'division_select_y')):
            args += ['--' + flag, str(s[key])]
        if selector is not None:
            args += ['--proof-mode', 'generic_club_route_capture']
        return args
    if not label or not re.fullmatch(r'[a-z][a-z0-9_]*', label) or not token:
        raise ValueError('explicit safe profile label and identity token required')
    actors = pipeline.read_json_file(release.package_path)['players']
    matches = [p for p in actors if p['carrier_id'] == carrier]
    if len(matches) != 1:
        raise ValueError('one exact recipe carrier required')
    # OCR removes diacritics; remove combining marks before its ASCII tokeniser
    # can turn Köhn into two tokens, while typing the real native name unchanged.
    token = ''.join(char for char in unicodedata.normalize('NFKD', token)
                    if not unicodedata.combining(char))
    args = ['python3', '/workspace/repo/scripts/pm99_runner/premier_offer_capture_driver.py',
            '--game-dir', '/workspace/game', '--artifacts-dir', '/workspace/artifacts',
            '--window-timeout', '120', '--team-slot', '1', '--skip-team-probe-ocr',
            '--success-mode', 'final_step', '--expected-profile-token', token]
    steps = ['continue_retry|native_input_click|561,442,1|8.0',
             'select_transfers|native_input_click|223,318,1|1.0',
             'open_transfers|native_double_click|223,318,1|6.0',
             'return_to_transfers|native_input_click|573,466,1|2.5',
             'open_offers_button|native_double_click|564,372,1|2.5',
             'open_player_name_search|native_input_click|565,360,1|2.5',
             'focus_search_name_field|native_input_click|238,141,1|0.8']
    for i, char in enumerate(matches[0]['name'] if search_text is None else search_text):
        key = ('Space' if char == ' ' else char.upper() if char.isascii() and char.isalnum()
               else 'CP1252:' + char.encode('cp1252').hex().upper())
        steps.append(f'name_{label}_{i:02d}|native_key|{key}|0.1')
    steps += [f'submit_{label}_search|native_double_click|486,142,1|3.5',
              f'select_{label}_row|native_input_click|120,{166 + 16 * (search_result_row - 1)},1|1.0',
              f'open_{label}_row|native_input_key|Return|5.0',
              f'inspect_{label}_profile|native_inspect|ignored|0.5',
              f'profile_only_{label}_done|native_inspect|ignored|0.5']
    for step in steps:
        args += ['--post-step', step]
    return args


def capture(season, release_id, tag, *, carrier=None, label=None, token=None, search_result_row=1, selector=None, search_text=None, minimum_free_bytes=RESERVE):
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,95}', tag):
        raise ValueError('safe unique capture tag required')
    release = registry.load_registered_release(season, release_id)
    driver = driver_args(release, carrier=carrier, label=label, token=token, search_result_row=search_result_row, selector=selector, search_text=search_text)
    inventory = pipeline.read_json_file(release.inventory_path)
    pipeline.assert_tree_matches_inventory(release.game_path, inventory)
    workspace = registry.ROOT / '.local/local-runner-v1' / season / release_id
    evidence = registry.ROOT / '.local/runlogs/pm99_runner' / tag
    if evidence.exists():
        raise ValueError('existing evidence must never be overwritten')
    marker = dict(season=season, release_id=release_id,
                  release_manifest_sha256=release.manifest_sha256)
    first = not (workspace / 'wine-prefix/.pm99_runner_initialized').exists()
    game = workspace / 'game'
    copy_budget = sum((release.game_path / row['path']).stat().st_size
                      for row in inventory['files']) if not game.exists() else 0
    budget = max(INITIAL_BUDGET if first else 0, copy_budget + 128 * 1024 ** 2)
    capacity = disk_budget.require_space(registry.ROOT, budget,
        minimum_free_bytes=minimum_free_bytes, context="local capture")
    workspace.mkdir(parents=True, exist_ok=True)
    retained(workspace / 'release-binding.json', marker)
    if not game.exists():
        shutil.copytree(release.game_path, game, copy_function=shutil.copy2)
    pipeline.assert_tree_matches_inventory(game, inventory)
    for name in ('wine-prefix', 'home', 'support'):
        (workspace / name).mkdir(exist_ok=True)
    evidence.mkdir(parents=True)
    shutil.copy2(release.compiler_receipt_path, evidence / 'input-provenance.json')
    hashes = ''.join(registry.sha256_file(game / row['path']) + '  ' + row['path'] + '\n'
                     for row in inventory['files'] if row['path'].startswith('DBDAT/'))
    (evidence / 'dbdat_override.sha256').write_text(hashes)
    retained(evidence / 'local-input-binding.json', dict(**marker,
        sealed_source=str(release.game_path), disposable_copy=str(game),
        complete_input_inventory_verified=True, uses_source_hardlinks=False))
    runner = registry.ROOT / 'upstream/pm99-runner'
    editor = registry.ROOT / 'upstream/pm99-skezmod-db-editor'
    command = [sys.executable, str(runner / 'scripts/pm99_runner/remote_runner_entrypoint.py'),
        'run-once', '--run-tag', tag, '--worker', 'local-vostro', '--lane-count', '1',
        '--launcher', 'capture_registered_season_local_v1', '--owner', 'pm99-research',
        '--container-name', 'pm99-agent-' + tag, '--artifacts-dir', str(evidence),
        '--lease-root', str(registry.ROOT / '.local/local-runner-v1/leases'),
        '--image', 'pm99-runner:latest', '--user', 'CURRENT_USER', '--workdir', '/workspace/repo']
    for value in ('HOME=/workspace/home', 'WINEPREFIX=/workspace/wine-prefix',
                  'WINEDEBUG=-all', 'PM99_EDITOR_ROOT=/workspace/editor',
                  'PYTHONPATH=/workspace/repo:/workspace/editor',
                  'PM99_NATIVE_INPUT_HELPER=/workspace/support/pm99-winmsg-driver.exe'):
        command += ['--env', value]
    for source, target in ((runner, 'repo:ro'), (editor, 'editor:ro'), (game, 'game'),
                           (workspace / 'wine-prefix', 'wine-prefix'), (workspace / 'home', 'home'),
                           (workspace / 'support', 'support'), (evidence, 'artifacts')):
        command += ['--volume', str(source) + ':/workspace/' + target]
    # Rebuild the tiny input helper from CURRENT source, not the old image copy.
    command += ['--', 'sh', '-c',
        'i686-w64-mingw32-gcc -O2 -s -o /workspace/support/pm99-winmsg-driver.exe '
        '/workspace/repo/scripts/pm99_runner/image/winmsg_driver.c && exec "$@"',
        'local-capture', *driver]
    retained(evidence / 'local-launch.json', dict(**marker, argv=command))
    completed = subprocess.run(command, env=dict(os.environ, DOCKER_HOST='unix:///var/run/docker.sock'))
    pipeline.assert_tree_matches_inventory(release.game_path, inventory)
    summary_path = evidence / 'summary.json'
    summary = pipeline.read_json_file(summary_path) if summary_path.exists() else {}
    passed = completed.returncode == 0 and summary_matches(summary, release, profile=carrier is not None, selector=selector)
    retained(evidence / 'local-transport.json', dict(**marker, exit_code=completed.returncode,
        evidence=registry.relative_workspace_path(evidence), source_inventory_preserved=True,
        summary_validation_passed=passed, visually_approved=False, disk_capacity=capacity,
        **({'team_selector': selector} if selector is not None else {})))
    if not passed:
        raise ValueError('local runner failed; original evidence preserved at ' + str(evidence))
    return str(evidence)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--release-id', required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--carrier', type=int)
    parser.add_argument('--label')
    parser.add_argument('--token')
    parser.add_argument('--search-result-row', type=int, default=1)
    parser.add_argument('--search-text')
    parser.add_argument('--selector-json', type=Path)
    args = parser.parse_args()
    print(capture(args.season, args.release_id, args.tag,
                  carrier=args.carrier, label=args.label, token=args.token, search_result_row=args.search_result_row,
                  selector=pipeline.read_json_file(args.selector_json) if args.selector_json else None,
                  search_text=args.search_text), flush=True)
