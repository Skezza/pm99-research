#!/usr/bin/env python3
"""Build each new immutable plan as it completes; retain unchanged releases."""
import argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import closeout_duplicate_ownership_batch_v1 as batch
from scripts import season_release_registry_v1 as registry


def ordered_seasons(pending,priority=()):
    if len(priority)!=len(set(priority)) or set(priority)-set(registry.supported_seasons()):
        raise ValueError('priority seasons must be distinct supported seasons')
    ranks={s:i for i,s in enumerate(priority)}
    return sorted(pending,key=lambda s:(ranks.get(s,len(ranks)),s))


def run(plan_root,release_id,jobs,priority=()):
    ordered_seasons(set(registry.supported_seasons()),priority)
    pending=set(registry.supported_seasons());active={};done=[]
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        while pending or active:
            for season in ordered_seasons(pending,priority):
                if len(active)>=jobs:break
                path=plan_root/season/'ownership-plan.json'
                if not path.is_file():continue
                try:plan=json.loads(path.read_text())
                except json.JSONDecodeError:continue
                if plan['season']!=season:raise ValueError('streamed ownership plan belongs to another season')
                if not plan['updates']:
                    pending.remove(season);done.append(season)
                    print(json.dumps({'season':season,'status':'unchanged-existing-game-preserved'}),flush=True)
                    continue
                active[pool.submit(batch.build_one,season,plan_root,release_id)]=season
                pending.remove(season)
            completed,_=wait(active,timeout=5,return_when=FIRST_COMPLETED) if active else (set(),set())
            for future in completed:
                season=active.pop(future);result=future.result();done.append(season)
                print(json.dumps({'season':season,'unpromoted_build':result}),flush=True)
            if not active:time.sleep(5)
    print(json.dumps({'completed_unpromoted_or_preserved_seasons':len(done)}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan-root',type=Path,required=True);p.add_argument('--release-id',required=True)
    p.add_argument('--jobs',type=int,choices=(1,2),default=2)
    p.add_argument('--priority-season',action='append',default=[],help='Build these exact seasons first; never change their plan or repeat completed work')
    args=p.parse_args();run(args.plan_root,args.release_id,args.jobs,args.priority_season)
