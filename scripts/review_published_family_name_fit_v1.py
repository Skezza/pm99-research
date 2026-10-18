#!/usr/bin/env python3
"""Read-only name-fit review using positively identified full family components.

Source eligibility is the old immutable proposal's queue, not an installation
approval. Every eventual repair must independently replay membership/ownership.
The existing native no-growth API is used unchanged on the exact old carrier.
"""
import argparse
import collections
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import season_published_family_component_v1 as family
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from app.fdi_indexed import IndexedFDIFile


def run(plan_root,output):
    if output.exists():raise ValueError('published family name-fit review is immutable')
    paths=sorted(plan_root.glob('*/ownership-plan.json'))
    documents=[(path,json.loads(path.read_text())) for path in paths]
    if not documents:raise ValueError('family name-fit review requires completed original plans')
    person_bindings=[d['bindings']['published_person_supplement'] for _,d in documents]
    if any(b!=person_bindings[0] for b in person_bindings):raise ValueError('family name-fit inputs use different original person sources')
    person_path=ROOT/person_bindings[0]['path']
    if registry.sha256_file(person_path)!=person_bindings[0]['sha256']:raise ValueError('original person input changed')
    required={id for _,d in documents for r in d['unresolved']
        if r['reason']=='owner-proven-but-all-eligible-replacement-surnames-exceed-native-window'
        for id in r['eligible_source_person_ids'] if type(id) is int}
    claims=family.claims(person_path,required);rows=[];inputs=[]
    for plan_path,doc in documents:
        inputs.append({'path':registry.relative_workspace_path(plan_path),'sha256':registry.sha256_file(plan_path)})
        pending=[r for r in doc['unresolved'] if r['reason']=='owner-proven-but-all-eligible-replacement-surnames-exceed-native-window']
        if not pending:continue
        release=registry.load_registered_release(doc['season'],doc['release_id'])
        jug=release.game_path/'DBDAT/JUG98030.FDI'
        if registry.sha256_file(jug)!=doc['jug_sha256']:raise ValueError('reviewed original native name window changed')
        original=jug.read_bytes();entries={e.record_id:e for e in IndexedFDIFile.from_bytes(original).entries}
        for problem in pending:
            player_id=problem['player_id'];candidate=next(p for p in problem['candidates'] if p['player_id']==player_id)
            raw=entries[candidate['carrier_id']].decode_payload(original);current=compiler._player_name(raw,record_id=candidate['carrier_id'])
            fitted=[]
            for id in problem['eligible_source_person_ids']:
                claim=claims.get(id)
                if claim is None:continue
                person={'source_player_id':id,'birth_date':claim['birth_date']}
                for alias in family.verify(claim,person):
                    text=compiler._pm99_text(alias['name'],label='positively published entire family component')
                    try:compiler._patch_indexed_player_variable_name_payload(raw,current,text)
                    except (ValueError,RuntimeError):continue
                    fitted.append({'source_player_id':id,'display_name':text,'original_family_component_claim':claim})
            rows.append({'season':doc['season'],'source_release_id':doc['release_id'],'player_id':player_id,
                'carrier_id':candidate['carrier_id'],'club':candidate['club'],'native_name':current,
                'fitting_published_full_family_components':fitted,'native_writes':0})
        print(json.dumps({'family_fit_reviewed':doc['season'],'name_window_rows':len(pending)}),flush=True)
    result={'schema_version':'pm99-original-published-full-family-component-native-fit-review-v1',
        'policy':family.POLICY,'scope':'completed-proposals-present-at-start; source/native-fit feasibility only',
        'plan_inputs':inputs,'person_binding':person_bindings[0],'rows':rows,'native_writes':0,
        'summary':{'seasons':len(documents),'reviewed_name_window_slots':len(rows),
            'slots_with_fitting_full_family_component':sum(bool(r['fitting_published_full_family_components']) for r in rows),
            'confirmed_source_people_with_component':len(claims)}}
    output.parent.mkdir(parents=True,exist_ok=True);pipeline.write_canonical_json(output,result)
    print(json.dumps(result['summary']),flush=True);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.plan_root,a.output)
