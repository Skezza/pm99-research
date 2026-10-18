"""Private single-slot native-reader pilot; never registers a playable release.

This changes a display name ONLY. The old person's facts deliberately remain
unchanged so the runtime test can detect any corruption of their native fields.
It is not a historical replacement and must never be distributed as a season.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts import season_published_family_component_v1 as family
from scripts import season_pipeline_v2 as pipeline
from experiments.factory_name_window_recovery_probe_v1 import recover_candidate,_stored_case_display
from app.editor_actions import _patch_indexed_dd6360_variable_name,_indexed_variable_name_runtime_segments
from app.fdi_indexed import IndexedFDIFile


def patch_name(factory,current,target):
    recovered,recovery=recover_candidate(factory,current)
    result,writer=_patch_indexed_dd6360_variable_name(recovered,_stored_case_display(recovered),target)
    original_end=compiler._native_dd6360_role_start(factory)
    old_end=compiler._native_dd6360_role_start(current)
    new_end=compiler._native_dd6360_role_start(result)
    if not old_end<new_end<=original_end:
        raise ValueError('pilot must exercise recovered capacity, not an already fitting name')
    if len(result)!=len(current) or result[:8]!=current[:8]:
        raise ValueError('pilot changed native record length or fixed prefix')
    before=compiler._read_native_dd6360_fields(current,old_end)
    after=compiler._read_native_dd6360_fields(result,new_end)
    if before!=after:raise ValueError('pilot changed profile metadata, roles or abilities')
    gain=new_end-old_end
    if current[-gain:]!=b'\x61'*gain or result[new_end:]!=current[old_end:-gain]:
        raise ValueError('pilot changed opaque suffix bytes, beyond removing established zero padding')
    return result,{'recovery':recovery,'writer':writer,'native_fields_before':before,
        'native_fields_after':after,'semantic_readback_unchanged':True,'opaque_suffix_preserved':True,
        'current_suffix_cursor':old_end,'pilot_suffix_cursor':new_end,'factory_suffix_cursor':original_end}


def prepare(report_path,season,carrier_id,person_id,output):
    if output.exists():raise ValueError('private pilot is immutable; never overwrite')
    report=json.loads(report_path.read_text())
    if report.get('native_writes')!=0 or report.get('publication_authorised') is not False:
        raise ValueError('pilot requires the explicit read-only capacity report')
    rows=[r for r in report['rows'] if r['season']==season and r['carrier_id']==carrier_id]
    if len(rows)!=1:raise ValueError('capacity report does not uniquely identify this season/slot')
    row=rows[0];candidates=[n for n in row['possible_names'] if n['source_person_id']==person_id]
    if len(candidates)!=1:raise ValueError('pilot name lacks one independently sourced whole-family claim')
    candidate=candidates[0];claim=candidate['original_family_claim']
    person={'source_player_id':person_id,'birth_date':claim['birth_date']}
    names=family.native_candidates(claim,person)
    if candidate['display_name'] not in [compiler._pm99_text(n['name'],label='whole family') for n in names]:
        raise ValueError('pilot name would lose a surname particle or original component')
    for path,sha in ((ROOT/report['factory_path'],report['factory_sha256']),
                     (ROOT/report['person_input_path'],report['person_input_sha256']),
                     (ROOT/row['source_plan_path'],row['source_plan_sha256'])):
        if registry.sha256_file(path)!=sha:raise ValueError('pilot source binding changed')
    release=registry.load_preferred_release(season)
    if release.release_id!=row['release_id']:raise ValueError('pilot starting release changed')
    source=release.game_path/'DBDAT/JUG98030.FDI'
    if registry.sha256_file(source)!=row['current_jug_sha256']:raise ValueError('pilot starting JUG changed')
    original=source.read_bytes();index=IndexedFDIFile.from_bytes(original)
    entry=next(e for e in index.entries if e.record_id==carrier_id)
    factory=(ROOT/report['factory_path']).read_bytes()
    factory_entry=next(e for e in IndexedFDIFile.from_bytes(factory).entries if e.record_id==carrier_id)
    result,proof=patch_name(factory_entry.decode_payload(factory),entry.decode_payload(original),candidate['display_name'])
    patched=compiler._rebuild_indexed(original,index,{carrier_id:result})
    start,end=entry.payload_offset,entry.payload_offset+entry.payload_length
    if original[:start]!=patched[:start] or original[end:]!=patched[end:]:
        raise ValueError('pilot changed other records or the directory')
    dbdat=output/'DBDAT';dbdat.mkdir(parents=True)
    (dbdat/'JUG98030.FDI').write_bytes(patched)
    for name in ('EQ98030.FDI','ENT98030.FDI','MINIFOTO.PKF','BIGCAMP.PKF','BIGESC.PKF',
                 'MINIESC.PKF','NANOESC.PKF','RIDIESC.PKF'):
        os.link(release.game_path/'DBDAT'/name,dbdat/name)
    os.link(release.game_path/'MANAGPRE.EXE',output/'MANAGPRE.EXE')
    receipt={'schema_version':'pm99-private-factory-name-capacity-runtime-pilot-v1',
        'historical_release':False,'publication_authorised':False,
        'scope':'display-name-only native-reader test; old identity facts retained deliberately',
        'season':season,'release_id':release.release_id,'carrier_id':carrier_id,
        'pilot_display_name':candidate['display_name'],'pilot_name_claim':claim,'native_proof':proof,
        'capacity_report_path':registry.relative_workspace_path(report_path),
        'capacity_report_sha256':registry.sha256_file(report_path),
        'baseline_jug_sha256':row['current_jug_sha256'],'pilot_jug_sha256':hashlib.sha256(patched).hexdigest(),
        'native_records_changed':1,'unrelated_native_bytes_unchanged':True}
    pipeline.write_canonical_json(output/'private-pilot.json',receipt)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capacity-report',type=Path,required=True)
    p.add_argument('--season',required=True);p.add_argument('--carrier-id',type=int,required=True)
    p.add_argument('--person-id',type=int,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=prepare(a.capacity_report,a.season,a.carrier_id,a.person_id,a.output)
    print(json.dumps({k:v for k,v in r.items() if k not in ('pilot_name_claim','native_proof')}),flush=True)
