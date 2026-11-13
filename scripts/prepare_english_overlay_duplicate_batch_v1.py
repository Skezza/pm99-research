#!/usr/bin/env python3
"""Continue a completed batch and insert one exact precompiled English plan.

No source downloads or game rebuilds. Every previously completed slot is reused,
and the supplied 2015 proposal keeps its original hash and supplemental sources.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import json_storage_io_v1 as storage_io
from scripts import closeout_duplicate_ownership_batch_v1 as batch
from scripts import season_duplicate_english_overlay_v1 as overlay
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def prepare(input_root,english_plan_path,output):
    if storage_io.exists(output):raise ValueError('next batch plans are immutable')
    plan=json.loads(storage_io.read_text(english_plan_path));release=registry.load_preferred_release('2015-16')
    if plan['season']!='2015-16' or not plan['updates'] or any(r['layer']!='english' for r in plan['updates']):
        raise ValueError('requires the exact English-only 2015 correction proposal')
    if (plan['release_id'],plan['package_sha256'],plan['jug_sha256'])!=(
        release.release_id,registry.sha256_file(release.package_path),registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')):
        raise ValueError('English proposal starting release changed')
    overlay.validate_binding(release,plan)
    selected=[s for s in registry.supported_seasons() if s!='2015-16']
    batch.rebase_completed_plans(input_root,output,seasons=selected)
    if any(json.loads(storage_io.read_text(p))['updates'] for p in storage_io.glob(output, '*/ownership-plan.json')):
        raise ValueError('the preceding batch has not finished promotion; do not rebuild its slots')
    target=output/'2015-16/ownership-plan.json';target.parent.mkdir(parents=True)
    pipeline.write_canonical_json(target,plan)
    if registry.sha256_file(target)!=registry.sha256_file(english_plan_path):
        raise ValueError('English proposal bytes changed in batch continuation')
    pipeline.write_canonical_json(output/'continuation-receipt.json',{
        'source_plan_root':registry.relative_workspace_path(input_root),
        'English_plan_path':registry.relative_workspace_path(english_plan_path),
        'English_plan_sha256':registry.sha256_file(english_plan_path),
        'unchanged_seasons':selected,'source_downloads':0,'game_rebuilds':0})
    print(json.dumps({'new_English_slots':len(plan['updates']),'completed_seasons_preserved':len(selected)}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--English-plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.input_root,a.English_plan,a.output)
