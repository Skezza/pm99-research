from __future__ import annotations
import copy, json, sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts import season_source_hash_continuity_v1 as proof
from scripts import season_source_package_builder_v1 as builder

V2 = ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/calendar-2017-slice-v1/generated-v2"
TEMPLATE = OLD = INTAKE = SOURCE_CAPTURE = SOURCE_ASSIGNMENT = REGISTRY = TARGET = CONTEXT = None
ORIGINAL_TEMPLATE_SHA = None


def _load_corpus():
    global TEMPLATE, OLD, INTAKE, SOURCE_CAPTURE, SOURCE_ASSIGNMENT, REGISTRY
    global TARGET, ORIGINAL_TEMPLATE_SHA, CONTEXT
    if TEMPLATE is not None:
        return
    paths = [
        ROOT / ".local/historical-role-deltas-v1/2017-18/sourced-coady-defence-cascade-20261024-r218a/season-package.json",
        ROOT / ".local/transfermarkt-opening-plans-current-v1/2017-18/opening-squad-preallocation.json",
        V2 / "calendar-2017-four-country-source-intake.json",
        V2 / "calendar-2017-four-country-source-capture.json",
        V2 / "calendar-2017-four-country-assignment-candidate.json",
        ROOT / "seasons/2017-18/fixed-carrier-registry.json",
        V2 / "calendar-2017-four-country-mapping-proposal.json",
    ]
    if any(not path.is_file() for path in paths):
        pytest.skip("retained 2017-18 source continuity corpus is unavailable")
    TEMPLATE = json.loads(paths[0].read_text())
    OLD = json.loads(paths[1].read_text())
    INTAKE = json.loads(paths[2].read_text())
    SOURCE_CAPTURE = json.loads(paths[3].read_text())
    SOURCE_ASSIGNMENT = json.loads(paths[4].read_text())
    REGISTRY = json.loads(paths[5].read_text())
    TARGET = next(x for x in INTAKE["source_clubs"] if x["selector"]["source_path"].endswith("/1189.html"))
    ORIGINAL_TEMPLATE_SHA = proof.document_sha256(TEMPLATE)
    CONTEXT = proof.SourceHashContinuityContext(template=TEMPLATE,
        original_template_sha256=ORIGINAL_TEMPLATE_SHA, old_preallocation=OLD,
        source_intake=INTAKE, registry=REGISTRY,
        source_capture=SOURCE_CAPTURE, source_assignment=SOURCE_ASSIGNMENT)


def test_source_hash_continuity_is_reported_as_a_continuing_assignment():
    assert builder._is_continuing_allocation_method(proof.METHOD)


def test_invalid_method_fails_without_local_corpus():
    with pytest.raises(proof.SourceHashContinuityError, match="only accepts its dedicated"):
        proof.validate_source_hash_continuity_allocation_row(
            method="different-method", row={}, template={}, original_template_sha256="",
            old_preallocation=None, source_intake={}, registry={}, target_source_club={})


def test_missing_pinned_preallocation_fails_without_local_corpus():
    with pytest.raises(proof.SourceHashContinuityError, match="requires the template-pinned old preallocation"):
        proof.validate_source_hash_continuity_allocation_row(
            method=proof.METHOD, row={}, template={}, original_template_sha256="",
            old_preallocation=None, source_intake={}, registry={}, target_source_club={})


def test_malformed_selector_fails_without_local_corpus():
    with pytest.raises(proof.SourceHashContinuityError, match="selector fields are incomplete"):
        proof._selector({}, "test")


def proposal_row(*, target=None, carrier_id=1854, template=None, old=None):
    _load_corpus()
    target = target or TARGET
    template = template or TEMPLATE
    old = old or OLD
    evidence=proof.derive_source_hash_continuity_evidence(
        template=template, original_template_sha256=proof.document_sha256(template),
        old_preallocation=old, source_intake=INTAKE, registry=REGISTRY,
        source_capture=SOURCE_CAPTURE, source_assignment=SOURCE_ASSIGNMENT,
        carrier_id=carrier_id, target_source_club=target, context=CONTEXT)
    row={
        'carrier_id':carrier_id,
        'club_name':target['selector']['club_name'],
        'source_selector':{k:target['selector'][k] for k in ('country_catalog','competition_catalog','source_path','source_sha256')},
        'method':proof.METHOD,
        'source_identity_evidence':evidence,
        'source_identity_evidence_sha256':proof.document_sha256(evidence),
    }
    return row


def validate(row, *, target=None, template=None, old=None):
    _load_corpus()
    target = target or TARGET
    template = template or TEMPLATE
    old = old or OLD
    return proof.validate_source_hash_continuity_allocation_row(
        method=row.get('method'),row=row,template=template,
        original_template_sha256=proof.document_sha256(template),
        old_preallocation=old,source_intake=INTAKE,registry=REGISTRY,
            source_capture=SOURCE_CAPTURE,source_assignment=SOURCE_ASSIGNMENT,
        target_source_club=target,context=CONTEXT)


def test_valid_exact_hash_continuity_survives_package_label_disagreement():
    row=proposal_row()
    result=validate(row)
    assert result['old_provider_club_id']=='1189'
    assert result['target_provider_club_id']=='1189'
    assert result['old_preallocation_artifact_id']=='opening-squad-preallocation-2017-18'
    assert result['overlap_count']>=10
    package_club=next(x for x in TEMPLATE['clubs'] if x['carrier_id']==1854)
    assert package_club['name']=='Cork City'
    assert TARGET['selector']['club_name']=="St. Patrick's Athletic"


def test_new_method_without_proof_fails_closed():
    row=proposal_row(); row.pop('source_identity_evidence'); row.pop('source_identity_evidence_sha256')
    with pytest.raises(proof.SourceHashContinuityError,match='missing source_identity_evidence'):
        validate(row)


def test_altered_evidence_digest_or_source_hash_fails():
    row=proposal_row(); row['source_identity_evidence']['target_source_selector']['source_sha256']='0'*64
    with pytest.raises(proof.SourceHashContinuityError,match='digest is missing or altered'):
        validate(row)
    row=proposal_row(); row['source_identity_evidence']['overlap_source_row_sha256s'][0]='0'*64
    row['source_identity_evidence_sha256']=proof.document_sha256(row['source_identity_evidence'])
    with pytest.raises(proof.SourceHashContinuityError,match='does not reproduce'):
        validate(row)


def test_wrong_source_selector_or_cross_country_fails():
    row=proposal_row(); row['source_selector']['source_sha256']='0'*64
    with pytest.raises(proof.SourceHashContinuityError,match='differs from exact source-intake selector'):
        validate(row)
    wrong=copy.deepcopy(TARGET); wrong['selector']['country_catalog']='norway'
    row=proposal_row()
    row['source_selector']['country_catalog']='norway'
    with pytest.raises(proof.SourceHashContinuityError,match='country differs'):
        validate(row,target=wrong)


def test_unpinned_preallocation_and_changed_template_fail():
    _load_corpus()
    altered=copy.deepcopy(OLD); altered['source_clubs'][0]['players'][0]['source_row_sha256']='0'*64
    with pytest.raises(proof.SourceHashContinuityError,match='not uniquely pinned'):
        proof.derive_source_hash_continuity_evidence(
            template=TEMPLATE,original_template_sha256=ORIGINAL_TEMPLATE_SHA,
            old_preallocation=altered,source_intake=INTAKE,registry=REGISTRY,
            source_capture=SOURCE_CAPTURE,source_assignment=SOURCE_ASSIGNMENT,
            carrier_id=1854,target_source_club=TARGET)
    changed=copy.deepcopy(TEMPLATE); changed['package_id']+='-tampered'
    with pytest.raises(proof.SourceHashContinuityError,match='template package changed'):
        proof.derive_source_hash_continuity_evidence(
            template=changed,original_template_sha256=ORIGINAL_TEMPLATE_SHA,
            old_preallocation=OLD,source_intake=INTAKE,registry=REGISTRY,
            source_capture=SOURCE_CAPTURE,source_assignment=SOURCE_ASSIGNMENT,
            carrier_id=1854,target_source_club=TARGET)


def test_ambiguous_preallocation_overlap_fails_even_if_artifact_is_rebound():
    _load_corpus()
    old=copy.deepcopy(OLD)
    original=next(x for x in old['source_clubs'] if x['selector']['source_path'].endswith('/1189.html'))
    duplicate=copy.deepcopy(original)
    duplicate['selector']['club_name']='Synthetic competing selector'
    duplicate['selector']['source_path']='squad/2017/IR1/999999.html'
    duplicate['selector']['source_sha256']='1'*64
    old['source_clubs'].append(duplicate)
    template=copy.deepcopy(TEMPLATE)
    digest=proof.document_sha256(old)
    artifact=next(x for x in template['artifacts'] if x['id']=='opening-squad-preallocation-2017-18')
    artifact['sha256']=digest
    with pytest.raises(proof.SourceHashContinuityError,match='matches multiple old preallocation rows equally'):
        proof.derive_source_hash_continuity_evidence(
            template=template,original_template_sha256=proof.document_sha256(template),
            old_preallocation=old,source_intake=INTAKE,registry=REGISTRY,
            source_capture=SOURCE_CAPTURE,source_assignment=SOURCE_ASSIGNMENT,
            carrier_id=1854,target_source_club=TARGET)


def test_all_26_same_carrier_continuity_candidates_have_exact_proof():
    _load_corpus()
    mapping=json.loads((V2/'calendar-2017-four-country-mapping-proposal.json').read_text())
    checked=0
    for candidate in mapping['candidate_assignments']:
        if candidate['status']!='candidate-preserve':
            continue
        country=mapping['country_source_year_mapping']['country_groups'][candidate['country_group']]['country_catalog']
        target=next(x for x in INTAKE['source_clubs']
                    if x['selector']['country_catalog']==country
                    and x['selector']['source_path'].endswith('/'+candidate['provider_club_id']+'.html'))
        evidence=proof.derive_source_hash_continuity_evidence(
            template=TEMPLATE,original_template_sha256=ORIGINAL_TEMPLATE_SHA,
            old_preallocation=OLD,source_intake=INTAKE,registry=REGISTRY,
            source_capture=SOURCE_CAPTURE,source_assignment=SOURCE_ASSIGNMENT,
            carrier_id=candidate['carrier_id'],target_source_club=target,context=CONTEXT)
        row={
            'carrier_id':candidate['carrier_id'],
            'club_name':target['selector']['club_name'],
            'source_selector':{k:target['selector'][k] for k in ('country_catalog','competition_catalog','source_path','source_sha256')},
            'method':proof.METHOD,
            'source_identity_evidence':evidence,
            'source_identity_evidence_sha256':proof.document_sha256(evidence),
        }
        checked_proof=validate_source_row(row,target)
        assert checked_proof['old_provider_club_id']==candidate['provider_club_id']
        assert checked_proof['target_provider_club_id']==candidate['provider_club_id']
        checked+=1
    assert checked==26


def validate_source_row(row,target):
    return proof.validate_source_hash_continuity_allocation_row(
        method=row['method'],row=row,template=TEMPLATE,
        original_template_sha256=ORIGINAL_TEMPLATE_SHA,
        old_preallocation=OLD,source_intake=INTAKE,registry=REGISTRY,
            source_capture=SOURCE_CAPTURE,source_assignment=SOURCE_ASSIGNMENT,
        target_source_club=target)


def test_provider_id_and_native_capacity_guards():
    _load_corpus()
    wrong_id=copy.deepcopy(TARGET)
    wrong_id['selector']['source_path']=wrong_id['selector']['source_path'].replace('/1189.html','/999999.html')
    with pytest.raises(proof.SourceHashContinuityError,match='provider club ID differs'):
        proof.derive_source_hash_continuity_evidence(
            template=TEMPLATE,original_template_sha256=ORIGINAL_TEMPLATE_SHA,
            old_preallocation=OLD,source_intake=INTAKE,registry=REGISTRY,
            source_capture=SOURCE_CAPTURE,source_assignment=SOURCE_ASSIGNMENT,
            carrier_id=1854,target_source_club=wrong_id,context=CONTEXT)
    too_small=copy.deepcopy(TARGET)
    too_small['players']=too_small['players'][:17]
    with pytest.raises(proof.SourceHashContinuityError,match='smaller than native fixed-carrier capacity'):
        proof.derive_source_hash_continuity_evidence(
            template=TEMPLATE,original_template_sha256=ORIGINAL_TEMPLATE_SHA,
            old_preallocation=OLD,source_intake=INTAKE,registry=REGISTRY,
            source_capture=SOURCE_CAPTURE,source_assignment=SOURCE_ASSIGNMENT,
            carrier_id=1854,target_source_club=too_small,context=CONTEXT)


def test_forged_capture_hash_and_altered_target_selector_fail_source_binding():
    _load_corpus()
    forged=copy.deepcopy(INTAKE)
    forged['source_capture_sha256']='a'*64
    with pytest.raises(proof.SourceHashContinuityError,match='does not exactly match its hash-locked inputs'):
        proof.derive_source_hash_continuity_evidence(
            template=TEMPLATE,original_template_sha256=ORIGINAL_TEMPLATE_SHA,
            old_preallocation=OLD,source_intake=forged,registry=REGISTRY,
            source_capture=SOURCE_CAPTURE,source_assignment=SOURCE_ASSIGNMENT,
            carrier_id=1854,target_source_club=TARGET)

    altered=copy.deepcopy(INTAKE)
    altered_target=next(x for x in altered['source_clubs']
                        if x['selector']['source_path'].endswith('/1189.html'))
    altered_target['selector']['source_sha256']='b'*64
    with pytest.raises(proof.SourceHashContinuityError,match='does not exactly match its hash-locked inputs'):
        proof.derive_source_hash_continuity_evidence(
            template=TEMPLATE,original_template_sha256=ORIGINAL_TEMPLATE_SHA,
            old_preallocation=OLD,source_intake=altered,registry=REGISTRY,
            source_capture=SOURCE_CAPTURE,source_assignment=SOURCE_ASSIGNMENT,
            carrier_id=1854,target_source_club=TARGET)


def test_continuity_method_requires_capture_and_assignment_inputs():
    _load_corpus()
    with pytest.raises(proof.SourceHashContinuityError,match='requires source capture and assignment'):
        proof.SourceHashContinuityContext(
            template=TEMPLATE,original_template_sha256=ORIGINAL_TEMPLATE_SHA,
            old_preallocation=OLD,source_intake=INTAKE,registry=REGISTRY,
            source_capture=None,source_assignment=None)
