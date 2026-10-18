"""Select already admitted country rows; writer still rederives the full plan.

This saves redundant preparation on a pre-plan interrupted job. It does not
admit a source or bypass source.verify at native publication/SOURCE replay.
"""
import copy
from scripts import season_original_secondary_facts_v1 as source
from scripts import season_pipeline_v2 as pipeline


def project(admission, targets):
    if (admission.get('schema')!=source.SCHEMA
            or admission.get('independent_namesake_biography_document') is not None
            or not targets or any(fields!=['nationality'] for fields in targets.values())):
        raise ValueError('projection requires a nonempty original nationality-only admission')
    by_carrier={str(r['carrier_id']):r for r in admission['updates']}
    if len(by_carrier)!=len(admission['updates']) or not set(targets)<=set(by_carrier):
        raise ValueError('projection cannot add an unadmitted or duplicate carrier')
    if any(admission['targets'].get(key)!=['nationality'] or by_carrier[key]['fields']!=['nationality'] for key in targets):
        raise ValueError('projection cannot change admitted fact scope')
    result=copy.deepcopy(admission)
    result.update(targets=copy.deepcopy(targets),unresolved=[],
        updates=[copy.deepcopy(r) for r in admission['updates'] if str(r['carrier_id']) in targets])
    result['transaction_id']=source.digest(pipeline.canonical_json_bytes(
        dict(people=result['original_person_document']['sha256'],targets=targets)))[:12]
    return result
