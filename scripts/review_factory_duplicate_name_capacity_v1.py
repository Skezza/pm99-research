#!/usr/bin/env python3
"""Read-only same-carrier factory capacity review; not source eligibility QA."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts import season_published_family_component_v1 as family
from scripts import season_pipeline_v2 as pipeline
from app.fdi_indexed import IndexedFDIFile
from app.editor_actions import _patch_indexed_dd6360_variable_name
from experiments.factory_name_window_recovery_probe_v1 import recover_candidate,_stored_case_display

FACTORY=ROOT/'.local/season-pipeline-v2/pm99-base-clean/DBDAT/JUG98030.FDI'


def fitting_native_names(recovered, claim, person):
    """Keep the native surname field whole, including any surname particles."""
    names=[]
    for alias in family.native_candidates(claim,person):
        name=compiler._pm99_text(alias['name'],label='original whole family component')
        try:_patch_indexed_dd6360_variable_name(recovered,_stored_case_display(recovered),name)
        except (ValueError,RuntimeError):continue
        names.append({'source_person_id':person['source_player_id'],'display_name':name,
                      'original_family_claim':claim})
    return names


def review(plan_root,people_path,output):
    if output.exists():raise ValueError('capacity evidence is immutable')
    plans=[(p,json.loads(p.read_text())) for p in sorted(plan_root.glob('*/ownership-plan.json'))]
    requested={id for _,plan in plans for row in plan['unresolved']
        if row['reason']=='owner-proven-but-all-eligible-replacement-surnames-exceed-native-window'
        for id in row.get('eligible_source_person_ids',[]) if isinstance(id,int)}
    claims=family.claims(people_path,requested)
    factory=FACTORY.read_bytes();entries={e.record_id:e.decode_payload(factory) for e in IndexedFDIFile.from_bytes(factory).entries}
    rows=[]
    for path,plan in plans:
        release=registry.load_preferred_release(plan['season'])
        base=registry.load_registered_release(plan['season'],plan['release_id'])
        current=(release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        old=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        indexed={e.record_id:e.decode_payload(current) for e in IndexedFDIFile.from_bytes(current).entries}
        old_indexed={e.record_id:e.decode_payload(old) for e in IndexedFDIFile.from_bytes(old).entries}
        for row in plan['unresolved']:
            if row['reason']!='owner-proven-but-all-eligible-replacement-surnames-exceed-native-window':continue
            loser=next(p for p in row['candidates'] if p['player_id']==row['player_id']);id=loser['carrier_id']
            result={'season':plan['season'],'release_id':release.release_id,'carrier_id':id,
                'source_plan_path':registry.relative_workspace_path(path),'source_plan_sha256':registry.sha256_file(path),
                'current_jug_sha256':registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
                'source_ownership_and_replacement_eligibility_rechecked':False,'possible_names':[]}
            if indexed[id]!=old_indexed[id]:raise ValueError('unresolved carrier changed since source proposal')
            try:recovered,proof=recover_candidate(entries[id],indexed[id])
            except (ValueError,RuntimeError) as error:
                result.update(status='recovery-refused',reason=str(error));rows.append(result);continue
            result.update(status='reversible-same-carrier-capacity-candidate',recovery=proof)
            for person_id in row.get('eligible_source_person_ids',[]):
                claim=claims.get(person_id)
                if not claim:continue
                person={'source_player_id':person_id,'birth_date':claim['birth_date']}
                result['possible_names'].extend(fitting_native_names(recovered,claim,person))
            rows.append(result)
    result={'schema_version':'pm99-readonly-factory-name-capacity-candidates-v1',
        'native_writes':0,'publication_authorised':False,'factory_path':registry.relative_workspace_path(FACTORY),
        'factory_sha256':registry.sha256_file(FACTORY),'person_input_path':registry.relative_workspace_path(people_path),
        'person_input_sha256':registry.sha256_file(people_path),'reviewed_slots':len(rows),
        'structurally_reversible_slots':sum(r['status']=='reversible-same-carrier-capacity-candidate' for r in rows),
        'whole_family_name_fit_slots':sum(bool(r['possible_names']) for r in rows),'rows':rows}
    output.parent.mkdir(parents=True,exist_ok=True);pipeline.write_canonical_json(output,result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plans',type=Path,required=True)
    p.add_argument('--people',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();review(a.plans,a.people,a.output)
