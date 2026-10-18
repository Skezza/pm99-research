#!/usr/bin/env python3
"""Apply small artwork patches with a verified rollback, not another full game.

The transaction holds a season lock, retains every overwritten/removed byte,
checks the complete game inventory and publishes fresh release metadata. A
crash leaves a journal which must be restored before another transaction.
"""
import argparse
import fcntl
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_visual_patch_v1 as art
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry


def atomic_bytes(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def reconstruct_before(current, rollback):
    """Rebuild the old inventory from physical unchanged files and saved deltas."""
    previous = {r['path']: r for r in rollback['before_inventory']['files']}
    files = {r['path']: r for r in current['files']}
    root = Path(rollback['root'])
    for name in rollback['allowed']:
        if not art.PATCH_FILE.fullmatch(name):
            raise ValueError('rollback contains an unrelated path')
        if name in previous:
            saved = root / 'originals' / name
            if not saved.is_file() or art.sha(saved) != previous[name]['sha256']:
                raise ValueError('rollback bytes are missing or changed: ' + name)
            files[name] = previous[name]
        else:
            files.pop(name, None)
    ordered = [files[k] for k in sorted(files)]
    expected = rollback['before_inventory']
    if ordered != expected['files']:
        raise ValueError('unrelated game files changed during artwork transaction')
    pipeline.validate_inventory(expected)
    return expected


def verified_base_inventory(application, game):
    path = Path(application['compact_rollback_path'])
    path.resolve().relative_to(ROOT.resolve())
    if art.sha(path) != application['compact_rollback_sha256']:
        raise ValueError('compact rollback receipt changed')
    rollback = json.loads(path.read_text())
    if rollback['game'] != str(game) or rollback['season'] != application['season']:
        raise ValueError('rollback belongs to another game')
    return reconstruct_before(pipeline.build_tree_inventory(game), rollback)


def restore(root, restore_catalog=True):
    """Explicit recovery; reject later artwork/unrelated changes before restoring."""
    rollback = json.loads((root / 'rollback.json').read_text())
    lock = ROOT / '.local/season-art-transactions-v1/locks' / (rollback['season'] + '.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if _active_game(Path(rollback['game'])):
            raise ValueError('close the game before restoring its artwork')
        return _restore_locked(root, restore_catalog)


def _restore_locked(root, restore_catalog=True):
    """Internal recovery when install already holds the season lock."""
    rollback = json.loads((root / 'rollback.json').read_text())
    game = Path(rollback['game'])
    current = pipeline.build_tree_inventory(game)
    reconstruct_before(current, rollback)
    before = {r['path']: r for r in rollback['before_inventory']['files']}
    for row in current['files']:
        name = row['path']
        if name in rollback['allowed'] and row['sha256'] not in {
                before.get(name, {}).get('sha256'), rollback['outputs'].get(name)}:
            raise ValueError('later artwork changes must be undone first: ' + name)
    for name in rollback['allowed']:
        if name in before:
            atomic_bytes(game / name, (root / 'originals' / name).read_bytes())
        elif (game / name).exists():
            (game / name).unlink()
    pipeline.assert_tree_matches_inventory(game, rollback['before_inventory'])
    if restore_catalog:
        catalog = registry.load_catalog()
        catalog[rollback['season']] = rollback['catalog_entry']
        atomic_bytes(registry.CATALOG_PATH, pipeline.canonical_json_bytes({
            'schema_version': registry.CATALOG_SCHEMA, 'seasons': [catalog[s] for s in sorted(catalog)]}))
        atomic_bytes(Path(rollback['old_locator_path']), (root / 'old-locator.json').read_bytes())
    atomic_bytes(root / 'journal.json', pipeline.canonical_json_bytes({'state': 'restored', 'season': rollback['season']}))
    return {'season': rollback['season'], 'state': 'restored'}


def _active_game(game):
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            command = (proc / 'cmdline').read_bytes().lower()
            cwd = (proc / 'cwd').resolve()
            if b'managpre' in command and (cwd == game.resolve() or str(game).encode() in command):
                return True
        except (OSError, RuntimeError):
            continue
    return False


def install(plan_path, patch_root, transaction_root, release_id):
    plan = json.loads(plan_path.read_text())
    season = plan['season']
    lock = ROOT / '.local/season-art-transactions-v1/locks' / (season + '.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for journal in (ROOT / '.local/season-art-transactions-v1').glob('*/' + season + '/journal.json'):
            if json.loads(journal.read_text()).get('state') == 'prepared':
                raise ValueError('recover the interrupted artwork transaction first: ' + str(journal.parent))
        return _install_locked(plan_path, patch_root, transaction_root, release_id, plan)


def _install_locked(plan_path, patch_root, root, release_id, plan):
    release = registry.load_preferred_release(plan['season'])
    root.resolve().relative_to(ROOT.resolve())
    if root.resolve().is_relative_to(release.game_path.resolve()):
        raise ValueError('rollback artifacts must be outside the playable game')
    if root.exists():
        raise ValueError('transaction already exists; inspect journal or restore it')
    if registry.locator_path(plan['season'], release_id).parent.exists():
        raise ValueError('release already exists')
    if _active_game(release.game_path):
        raise ValueError('close the game before updating its artwork')
    receipt_path = patch_root / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    if (plan['inputs']['release_id'] != release.release_id or receipt['plan_sha256'] != art.sha(plan_path)
            or plan['inputs']['package_sha256'] != art.sha(release.package_path)
            or receipt['archive_before_sha256'] != art.sha(release.game_path / 'DBDAT/MINIFOTO.PKF')):
        raise ValueError('artwork patch base is stale')
    outputs = receipt['outputs']
    for name, digest in outputs.items():
        if not art.PATCH_FILE.fullmatch(name) or art.sha(patch_root / name) != digest:
            raise ValueError('invalid artwork output')
    for name, digest in receipt.get('kit_before_sha256s', {}).items():
        if not art.PATCH_FILE.fullmatch(name) or art.sha(release.game_path / name) != digest:
            raise ValueError('kit base is stale')
    removals = [f"DBDAT/MINIFOTO/J96{int(r['carrier_id']):05d}.BMP" for r in plan['no_photo']]
    if set(removals) & set(outputs):
        raise ValueError('patch both removes and replaces a portrait')
    before, runtime = art.source_inventory(release)
    previous = {r['path']: r for r in before['files']}
    allowed = sorted(set(outputs) | set(removals))
    required = sum(previous[n]['size'] for n in allowed if n in previous) + sum(
        (patch_root / n).stat().st_size for n in outputs) + 16 * 1024**2
    if shutil.disk_usage(ROOT).free < required + 512 * 1024**2:
        raise ValueError('compact artwork transaction would breach the 512 MiB disk reserve')
    root.mkdir(parents=True)
    for name in allowed:
        if name in previous:
            target = root / 'originals' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(release.game_path / name, target)
            if art.sha(target) != previous[name]['sha256']:
                raise ValueError('rollback copy verification failed')
    old_locator = registry.locator_path(plan['season'], release.release_id)
    shutil.copyfile(old_locator, root / 'old-locator.json')
    rollback = {'schema_version': 'pm99-art-rollback-v1', 'season': plan['season'],
                'game': str(release.game_path), 'root': str(root.resolve()), 'allowed': allowed,
                'before_inventory': before, 'outputs': outputs, 'old_locator_path': str(old_locator),
                'catalog_entry': registry.load_catalog()[plan['season']]}
    art.save(root / 'rollback.json', rollback)
    art.save(root / 'journal.json', {'state': 'prepared', 'season': plan['season']})
    try:
        for name in outputs:
            atomic_bytes(release.game_path / name, (patch_root / name).read_bytes())
        for name in removals:
            if (release.game_path / name).exists():
                (release.game_path / name).unlink()
        after = pipeline.build_tree_inventory(release.game_path)
        difference = art.assert_artwork_only_difference(before, after, allowed)
        reconstruct_before(after, rollback)
        application = {'schema_version': 'pm99-season-visual-patch-application-v1', 'season': plan['season'],
                       'plan_sha256': art.sha(plan_path), 'materialisation_sha256': art.sha(receipt_path),
                       'materialisation_path': str(receipt_path.resolve()),
                       'base_inventory_fingerprint': before['files_fingerprint'], 'output_inventory': after,
                       'registered_base_inventory_fingerprint': release.locator['game_inventory_fingerprint'],
                       'existing_runtime_config_difference': runtime, 'difference': difference,
                       'included_visual_patch_plan_sha256s': plan.get('included_visual_patch_plan_sha256s', []),
                       'game': str(release.game_path), 'unrelated_files_unchanged': True,
                       'compact_rollback_path': str((root / 'rollback.json').resolve()),
                       'compact_rollback_sha256': art.sha(root / 'rollback.json')}
        art.save(root / 'visual-patch-application.json', application)
        result = art.publish(plan['season'], release.game_path, release_id, register=True,
                             application_path=root / 'visual-patch-application.json')
        archived = dict(release.locator)
        archived.update(technical_status='archived-artwork-delta',
                        compact_rollback_path=registry.relative_workspace_path(root / 'rollback.json'))
        atomic_bytes(old_locator, pipeline.canonical_json_bytes(archived))
        atomic_bytes(root / 'journal.json', pipeline.canonical_json_bytes({'state': 'committed', 'season': plan['season'], 'release_id': release_id}))
        return result
    except BaseException:
        _restore_locked(root)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['install', 'restore'])
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--patch-root', type=Path)
    parser.add_argument('--transaction-root', type=Path, required=True)
    parser.add_argument('--release-id')
    args = parser.parse_args()
    if args.command == 'install' and not all((args.plan, args.patch_root, args.release_id)):
        parser.error('install needs --plan, --patch-root, --release-id')
    print(json.dumps(install(args.plan, args.patch_root, args.transaction_root, args.release_id)
                     if args.command == 'install' else restore(args.transaction_root)))
