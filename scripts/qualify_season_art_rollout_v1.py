#!/usr/bin/env python3
"""Qualify preferred games through worker-managed lanes; reuse valid proofs."""
import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes
from scripts import season_pipeline_v2 as pipeline


def one(season,args):
    log=args.output_root/(season+'.log')
    environment=os.environ.copy()
    environment['PM99_RUNNER_WORKER_LANE_COUNT']=str(args.lanes)
    command=[str(ROOT/'pm99-season'),'prove',season,'--worker',args.worker,'--run-tag',
             f'real_photos_{season.replace("-","_")}_20261003_r9','--execute','--attest']
    with log.open('w') as handle:
        run=subprocess.run(command,cwd=ROOT,env=environment,stdout=handle,stderr=subprocess.STDOUT)
    result={'season':season,'returncode':run.returncode,'log':str(log)}
    print(json.dumps(result),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',default='linux-runner')
    parser.add_argument('--lanes',type=int,default=2,choices=(1,2))
    parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args()
    args.output_root.mkdir(parents=True,exist_ok=True)
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.lanes) as pool:
        futures={pool.submit(one,s,args):s for s in registry.supported_seasons()}
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            atomic_bytes(args.output_root/'qualification.json',pipeline.canonical_json_bytes({
                'schema_version':'pm99-art-rollout-runtime-qualification-v1','completed':len(results),
                'results':sorted(results,key=lambda r:r['season'])}))
    raise SystemExit(any(r['returncode'] for r in results))
