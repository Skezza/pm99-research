#!/usr/bin/env python3
"""Continue an original-source review: retain good work, retry detail gaps only.

Explicit missing opponent badges and unknown roles remain labelled as such.
Never invent a role or an independently published match-fragment date. No
network, native game or recipe writes; all retained source bytes are rehashed.
"""
import argparse
import collections
import copy
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_published_person_identity_v1 as identities
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline


def rehash_retained(row):
    for source in row['raw_sources']:
        if (registry.sha256_file(ROOT/source['path'])!=source['sha256'] or
                registry.sha256_file(ROOT/source['source_receipt_path'])!=source['source_receipt_sha256']
                or json.loads((ROOT/source['source_receipt_path']).read_text())!=
                    {'url':source['url'],'sha256':source['sha256']}):
            raise ValueError('previously reparsed original Soccerbase evidence changed')


def revise(document,people):
    result=copy.deepcopy(document);counts=collections.Counter();recovered=[]
    for section in result['seasons']:
        if not section['clubs']:
            continue
        pin=section['capture_input'];source=ROOT/pin['path']
        if registry.sha256_file(source)!=pin['sha256']:
            raise ValueError('original Soccerbase capture changed during continued review')
        capture=json.loads(source.read_text())
        for i,row in enumerate(section['clubs']):
            if row['status']=='original-first-fixture-reparsed':
                rehash_retained(row)
                counts['retained-completed-source-reparses']+=1
                continue
            eligible=row.get('reason') in (
                'original Soccerbase report club sides/names/score disagree with schedule',
                'original lineup row lacks one numeric identity and dated role')
            if not eligible:
                continue
            matching=[c for c in capture['clubs'] if c['club_name']==row['club']]
            if len(matching)!=1:
                raise ValueError('detail-gap source capture is ambiguous')
            try:
                updated=replay.replay_club(section['season'],matching[0],people,True)
                updated['represented_native_clubs']=row['represented_native_clubs']
                section['clubs'][i]=updated
                recovered.append({'season':section['season'],'club':row['club']})
            except (ValueError,OSError) as exc:
                row['reason']=str(exc)
            counts['detail-gaps-retried']+=1
        print(json.dumps({'season':section['season'],'continued_source_review':dict(counts),
            'recovered_original_match_sheets':len(recovered)}),flush=True)
    result['summary']=summary(result)
    result['detail_gap_continuation']={'counts':dict(counts),'recovered_original_match_sheets':recovered,
        'source_dates_roles_and_both_provider_namespaces_preserved':True}
    return result


def summary(document):
    counts=collections.Counter()
    for s in document['seasons']:
        for row in s['clubs']:
            counts[row['status']]+=1
            if row['status']!='original-first-fixture-reparsed':continue
            counts['published-XI-people']+=len(row['original_match']['starting_xi'])
            counts['independently-identified-XI-people']+=len(row['identity_bridges']['starting_xi'])
            for values in row['identity_bridges'].values():
                counts['unique-provider-identity-bridges']+=sum(v['transfermarkt_person'] is not None for v in values)
            counts['identity-gaps']+=len(row['identity_gaps'])
    return dict(counts)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prior',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('continued source review is immutable')
    doc=json.loads(args.prior.read_text())
    if doc['policy']!=replay.POLICY:raise ValueError('unsupported original provider bridge policy')
    pin=doc['snapshot_binding'];people,_,_,actualpin=transfer.load_snapshot(ROOT/pin['path'],ROOT/pin['pinned_receipt_path'])
    if pin!=actualpin:raise ValueError('source review snapshot binding changed')
    people,_,_=public.merge_bound(people,{}, {'published_person_supplement':doc['published_person_binding']})
    result=revise(doc,people)
    result['continued_from']={'path':registry.relative_workspace_path(args.prior),'sha256':registry.sha256_file(args.prior)}
    pipeline.write_canonical_json(args.output,result)


if __name__=='__main__':main()
