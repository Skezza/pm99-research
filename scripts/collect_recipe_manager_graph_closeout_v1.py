#!/usr/bin/env python3
"""Collect the manager reconciliation with unchanged 25-season evidence.

No builds, scraping or runner launches. Prior collections and source reports
are immutable. Explicitly derived 2015 player comparisons are kept separate.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def collect(args):
    if args.output.exists():
        raise ValueError('collection exists; never overwrite evidence')
    release = registry.load_preferred_release('2015-16')
    if not registry.validate_preferred_release('2015-16')['valid']:
        raise ValueError('reconciled 2015 release is not fully bound')
    qa_path = args.corrected_qa / '2015-16/qa-report.json'
    qa = json.loads(qa_path.read_text())
    if (qa['inputs']['package_sha256'] != registry.sha256_file(release.package_path)
            or qa['inputs']['game_tree'] != registry.relative_workspace_path(release.game_path)):
        raise ValueError('new QA does not describe the current recipe/game')
    args.output.mkdir(parents=True)
    review_root, opening_root, qa_root = [args.output / name for name in ('reviews', 'opening', 'qa')]
    for season in registry.supported_seasons():
        if season == '2015-16':
            source = args.corrected_review / season
            shutil.copytree(source, review_root / season, copy_function=os.link)
            target = opening_root / season; target.mkdir(parents=True)
            os.link(source / 'opening-review.json', target / 'opening-review.json')
            target = qa_root / season; target.mkdir(parents=True)
            qa['historical_revision_binding'] = {'release_id': release.release_id,
                'release_manifest_sha256': release.manifest_sha256,
                'package_sha256': registry.sha256_file(release.package_path)}
            qa['collected_qa_provenance'] = {'path': registry.relative_workspace_path(qa_path),
                                            'sha256': registry.sha256_file(qa_path)}
            pipeline.write_canonical_json(target / 'qa-report.json', qa)
        else:
            for source, target in [(args.prior_review, review_root), (args.prior_opening, opening_root),
                                    (args.prior_qa, qa_root)]:
                shutil.copytree(source / season, target / season, copy_function=os.link)
    command = [sys.executable, str(ROOT / 'scripts/closeout_historical_review_v1.py'),
               '--review-root', str(review_root), '--opening-root', str(opening_root),
               '--qa-root', str(qa_root), '--output', str(args.output / 'collection')]
    subprocess.run(command, cwd=ROOT, check=True)
    retained = json.loads((ROOT / 'data/retained-season-releases-v1.json').read_text())
    for row in retained['releases']:
        locator_path = ROOT / row['locator_path']
        if registry.sha256_file(locator_path) != row['locator_sha256']:
            raise ValueError('protected original backup locator changed')
        old = registry.load_registered_release(row['season'], row['release_id'])
        if registry.sha256_file(old.inventory_path) != row['inventory_sha256']:
            raise ValueError('protected original backup inventory changed')
        pipeline.assert_tree_matches_inventory(old.game_path, pipeline.read_json_file(old.inventory_path))
    pipeline.write_canonical_json(args.output / 'retained-release-verification.json', {
        'retained_releases': retained['releases'], 'full_original_inventory_unchanged': True,
        'current_game_shared_with_repaired_r16_baseline': True,
        'do_not_delete_current_or_retained_locator_dependencies': True})
    return {'collection': registry.relative_workspace_path(args.output / 'collection'),
            'original_backup_verified': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('prior-review', 'prior-opening', 'prior-qa', 'corrected-review', 'corrected-qa', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(collect(args)))


if __name__ == '__main__': main()
