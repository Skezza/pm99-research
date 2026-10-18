"""Explicit, runtime-proven recovery of that same compact carrier's window.

Ownership/person/date/actual-XI checks are unchanged. This only recovers zero
padding introduced by an exactly reversible previous name edit; the native
writer still refuses growth beyond that carrier's original factory cursor.
"""
import hashlib
import json
from pathlib import Path

from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from app.fdi_indexed import IndexedFDIFile
from app.player_name_capacity import recover_compact_name_window

POLICY='same-compact-carrier-factory-cursor-exact-shrink-inverse-runtime-proven-v1'
FACTORY_SHA='95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844'


def bound(path):
    registry.relative_workspace_path(path)
    return {'path':registry.relative_workspace_path(path),'sha256':registry.sha256_file(path)}


def original(binding):
    path=registry.ROOT/binding['path'];registry.relative_workspace_path(path)
    if registry.sha256_file(path)!=binding['sha256']:raise ValueError('same-carrier capacity evidence changed')
    return path


def runtime_bundle(pilot_path,evidence):
    summary=json.loads((evidence/'summary.json').read_text())
    shot=evidence/'screens'/Path(summary['player_profile']['screenshot']).name
    bundle={'policy':POLICY,'factory':bound(registry.ROOT/'.local/season-pipeline-v2/pm99-base-clean/DBDAT/JUG98030.FDI'),
        'runtime_pilot':bound(pilot_path),'runtime_summary':bound(evidence/'summary.json'),
        'runtime_screenshot':bound(shot),'visible_dbdat_hashes':bound(evidence/'dbdat_override.sha256')}
    verify_bundle(bundle);return bundle


def verify_bundle(bundle):
    if bundle.get('policy')!=POLICY or bundle.get('factory',{}).get('sha256')!=FACTORY_SHA:
        raise ValueError('capacity policy requires the independently pinned original factory JUG')
    paths={k:original(bundle[k]) for k in ('factory','runtime_pilot','runtime_summary','runtime_screenshot','visible_dbdat_hashes')}
    pilot=json.loads(paths['runtime_pilot'].read_text());summary=json.loads(paths['runtime_summary'].read_text())
    proof=pilot.get('native_proof',{});profile=summary.get('player_profile',{})
    fields=proof.get('native_fields_before')
    required={'birth_day','birth_month','birth_year','fine_role_codes','skills','handling',
              'height_cm','weight_kg','visible_nationality_code','visible_position_code'}
    if (pilot.get('schema_version')!='pm99-private-factory-name-capacity-runtime-pilot-v1'
            or pilot.get('historical_release') is not False or pilot.get('publication_authorised') is not False
            or pilot.get('native_records_changed')!=1 or pilot.get('unrelated_native_bytes_unchanged') is not True
            or proof.get('semantic_readback_unchanged') is not True or proof.get('opaque_suffix_preserved') is not True
            or not isinstance(fields,dict) or not required<=set(fields)
            or proof.get('native_fields_before')!=proof.get('native_fields_after')
            or proof.get('recovery',{}).get('exact_shrink_roundtrip') is not True
            or not proof.get('current_suffix_cursor',0)<proof.get('pilot_suffix_cursor',0)<=proof.get('factory_suffix_cursor',0)):
        raise ValueError('capacity pilot did not prove same-carrier fixed-record native preservation')
    if (summary.get('success') is not True or summary.get('wine_debugger_detected')
            or summary.get('process_exit_code') not in (None,0)
            or profile.get('expected_name_token_satisfied') is not True
            or profile.get('player_name_ocr_normalized')!=pilot['pilot_display_name'].casefold()
            or Path(profile.get('screenshot','')).name!=paths['runtime_screenshot'].name):
        raise ValueError('capacity pilot did not render the requested name in a genuine live profile')
    hashes={line.split()[1]:line.split()[0] for line in paths['visible_dbdat_hashes'].read_text().splitlines()
            if line and not line.startswith('#')}
    if hashes.get('DBDAT/JUG98030.FDI')!=pilot['pilot_jug_sha256']:
        raise ValueError('capacity runner did not load the exact private pilot database')
    return paths['factory']


def recover_slot(data,carrier,bundle):
    factory_path=verify_bundle(bundle);factory=factory_path.read_bytes()
    entries=[e for e in IndexedFDIFile.from_bytes(data).entries if e.record_id==carrier]
    originals=[e for e in IndexedFDIFile.from_bytes(factory).entries if e.record_id==carrier]
    if len(entries)!=len(originals) or len(entries)!=1:raise ValueError('same-carrier capacity record is ambiguous')
    current=entries[0].decode_payload(data);original_payload=originals[0].decode_payload(factory)
    restored,proof=recover_compact_name_window(original_payload,current)
    claim={'policy':POLICY,'carrier_id':carrier,'factory_record_sha256':hashlib.sha256(original_payload).hexdigest(),
        'current_record_sha256':hashlib.sha256(current).hexdigest(),
        'recovered_record_sha256':hashlib.sha256(restored).hexdigest(),'recovery':proof}
    prepared=compiler._rebuild_indexed(data,IndexedFDIFile.from_bytes(data),{carrier:restored})
    e=entries[0];start,end=e.payload_offset,e.payload_offset+e.payload_length
    if data[:start]!=prepared[:start] or data[end:]!=prepared[end:]:
        raise ValueError('capacity recovery changed another record or the directory')
    return prepared,claim


def validate_binding(plan):
    rows=[r for r in plan.get('updates',[]) if r.get('same_carrier_name_capacity') is not None]
    enabled=bool(plan.get('allow_same_carrier_name_capacity'))
    binding=plan.get('bindings',{}).get('same_carrier_name_capacity')
    if not rows and not enabled and binding is None:return
    if not enabled or not binding or not rows:raise ValueError('capacity recovery requires explicit policy and selected-slot claims')
    verify_bundle(binding)
    for row in rows:
        claim=row['same_carrier_name_capacity']
        if claim.get('policy')!=POLICY or claim.get('carrier_id')!=row['carrier_id'] or row['layer']!='main':
            raise ValueError('capacity recovery belongs to another slot/layer or unknown policy')


def prepare_source(data,plan):
    validate_binding(plan)
    if not plan.get('allow_same_carrier_name_capacity'):return data
    prepared=data
    for row in plan['updates']:
        if not row.get('same_carrier_name_capacity'):continue
        prepared,claim=recover_slot(prepared,row['carrier_id'],plan['bindings']['same_carrier_name_capacity'])
        if claim!=row['same_carrier_name_capacity']:raise ValueError('capacity claim cannot be independently reproduced from the original slot')
    return prepared
