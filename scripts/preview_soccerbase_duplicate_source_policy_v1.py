#!/usr/bin/env python3
"""Measure newly recovered original evidence; do not write recipes or games."""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import season_soccerbase_duplicate_source_policy_v1 as policy
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_release_registry_v1 as registry
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_published_person_identity_v1 as identities
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_pipeline_v2 as pipeline


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original-review',type=Path,required=True)
    p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--club-entities',type=Path,required=True)
    p.add_argument('--history',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('source-policy preview is immutable')
    original=json.loads(args.original_review.read_text());pin=original['snapshot_binding']
    people,events,_,actualpin=transfer.load_snapshot(ROOT/pin['path'],ROOT/pin['pinned_receipt_path'])
    if actualpin!=pin:raise ValueError('source preview snapshot binding changed')
    bindings={'snapshot':pin,'published_person_supplement':original['published_person_binding'],
        'published_transfer_supplement':public.binding(args.history,histories.POLICY),
        'soccerbase_opening_sources':{'policy':policy.POLICY,
            'review':public.binding(args.original_review,policy.POLICY),
            'club_entities':public.binding(args.club_entities,'original-explicit-club-identity-discovery-v1')}}
    people,events,_=public.merge_bound(people,events,bindings)
    rows=[];totals=collections.Counter()
    for season in registry.supported_seasons():
        release=registry.load_preferred_release(season)
        layers=planner.package_layers(release)
        clubs=[c for _,pkg,_ in layers for c in pkg['clubs']]
        players=[q for _,pkg,_ in layers for q in pkg['players']]
        by_id={c['id']:c for c in clubs}
        opening=json.loads((args.source_root/'opening'/season/'opening-review.json').read_text())
        transfer.verify_opening_sources(opening)
        existing={r['club_id']:planner.source_evidence(r,opening) for r in opening['clubs']
            if r['status']=='original-first-fixture-reparsed' and r['club_id'] in by_id
            and (by_id[r['club_id']]['name'],by_id[r['club_id']]['carrier_id'])==(r['club'],r['carrier_id'])}
        captures,_=roster.load_sources(season)
        extended,gaps=policy.attach(bindings,season,clubs,captures,people,events,existing)
        new=sorted(set(extended)-set(existing))
        groups=planner.candidate_groups(players,people)
        unlocked=sum(any(p['club_id'] not in existing for p in g)
            and all(p['club_id'] in extended for p in g) for g in groups)
        summary={'new-original-opening-club-sources':len(new),
            'missing-opening-groups-with-all-sources-now-present':unlocked,
            'source-policy-refusals':len(gaps)}
        totals.update(summary)
        row={'season':season,'release_id':release.release_id,
            'package_sha256':registry.sha256_file(release.package_path),
            'summary':summary,'added_source_clubs':[{'club_id':id,'club':by_id[id]['name'],
                'carrier_id':by_id[id]['carrier_id'],'date':extended[id]['date'],
                'source_club_id':extended[id]['source_club_id']} for id in new],
            'source_refusals':gaps}
        rows.append(row)
        print(json.dumps({'season':season,**summary}),flush=True)
    pipeline.write_canonical_json(args.output,{'policy':policy.POLICY,'bindings':bindings,
        'seasons':rows,'summary':dict(totals),'native_games_modified':0,
        'ownership_decisions_or_native_slots_approved':0})


if __name__=='__main__':main()
