from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/root-dif-canonical-integration-v1'
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_roles
from scripts import season_adjudicated_player_facts_v1 as adjudicated
from scripts import season_official_career_context_v1 as career
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as common
from scripts import season_dated_parent_facts_editorial_role_v1 as role_api
from scripts.season_historical_roster_audit_v1 import native_player
from scripts import season_package_compiler_v2 as compiler
from scripts.season_within_club_reserve_repair_v1 import native_facts

SEASON = '2002-03'
PARENT_ID = 'sourced-nacional-portugal-kit-2002-20261025-r316a'
TARGET = 14265
NAME = 'Andreas Isaksson'
ROW_SHA = 'c64ce58c3677275716afbdff8d76d6e61962e87b35e5c0d851d78e20e7c66ab2'
PREALLOCATION = ROOT / '.local/transfermarkt-opening-plans-current-v1/2002-03/opening-squad-preallocation.json'
INTAKE = ROOT / '.local/season-historical-squad-backfill-v1/2002-03/source-intake.json'
SOURCE_ROOT = ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa'
DIF_PROFILE = SOURCE_ROOT / 'isaksson-dob-fine0-r315-private-proposal-v1/source/dif-current-profile.html'
DIF_RECEIPT = SOURCE_ROOT / 'isaksson-dob-fine0-r315-private-proposal-v1/source/capture-receipt.json'
PROGRAM_ROOT = SOURCE_ROOT / 'isaksson-programme-2002-source-v1'
PROGRAM_PDF = PROGRAM_ROOT / 'dif-shamrock-2002-08-15.pdf'
PROGRAM_TEXT = PROGRAM_ROOT / 'source-text.txt'
PROGRAM_RECEIPT = PROGRAM_ROOT / 'capture-receipt.json'
PROGRAM_URL = 'https://difhistoria.se/wp-content/uploads/Matchprogram-Fotboll-Herr-2002-08-15-Shamrock-Rovers-Djurgardens-IF.pdf'
DIF_PROFILE_URL = 'https://www.dif.se/spelare/herrar/2010-2019/andreas-isaksson'
pytestmark = pytest.mark.skipif(not all(path.is_file() for path in [PREALLOCATION,INTAKE,DIF_PROFILE,DIF_RECEIPT,PROGRAM_PDF,PROGRAM_RECEIPT]), reason='Local official DIF source corpus is not installed')


def _bind(path):
    return {'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path)}


def _write_once(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = packages.canonical_json_bytes(payload)
    if path.exists():
        assert path.read_bytes() == encoded
    else:
        pipeline.write_canonical_json(path, payload)


def _annual_row(allocation):
    rows = [(club, row) for club in allocation['source_clubs'] for row in club['players']
            if row.get('source_row_sha256') == ROW_SHA]
    assert len(rows) == 1
    return rows[0]


def _input(base, actor):
    allocation = pipeline.read_json_file(PREALLOCATION)
    intake = pipeline.read_json_file(INTAKE)
    club, row = _annual_row(allocation)
    assert row == _annual_row(intake)[1]
    annual = {
        'season': base.season, 'release_id': base.release_id, 'carrier_id': TARGET,
        'club_id': actor['club_id'], 'source_row_sha256': ROW_SHA,
        'source_row_index': row['source_row_index'], 'selector': copy.deepcopy(club['selector']),
        'preallocation': _bind(PREALLOCATION), 'source_intake': _bind(INTAKE),
        'package': _bind(base.package_path), 'release_manifest_sha256': base.manifest_sha256,
        'native_jug': _bind(base.game_path / 'DBDAT/JUG98030.FDI'),
        'native_eq': _bind(base.game_path / 'DBDAT/EQ98030.FDI'),
        'native_textos': _bind(base.game_path / 'DBDAT/TEXTOS.PKF'),
    }
    profile = {
        'provider': 'dif-current-player-profile-v1', 'url': DIF_PROFILE_URL,
        **_bind(DIF_PROFILE), 'receipt': _bind(DIF_RECEIPT),
        'birth_date': {'label': 'Född', 'literal': '3 okt. 1981'},
        'nationality': {'label': 'Nationalitet', 'literal': 'Svensk', 'code': 'SWE'},
    }
    programme = {
        'provider': 'dif-period-match-programme-v1', 'url': PROGRAM_URL,
        **_bind(PROGRAM_PDF), 'receipt': _bind(PROGRAM_RECEIPT),
        'document_type': 'application/pdf', 'opponent': 'Shamrock Rovers',
        'birth_date': {'label': 'Date of birth:', 'literal': 'October 3rd, 1981'},
        'text_extraction': {**_bind(PROGRAM_TEXT), 'extractor_mode': '-layout'},
    }
    witness = {
        'identity_policy': 'annual-source-row-person-identity-null-dob-v1',
        'person_id': actor['person_id'], 'full_name': NAME,
        'annual_identity': annual, 'native_before_birth_date': native_facts(
            (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes(), TARGET)['birth_date'],
        'values': {'birth_date': '1981-10-03', 'nationality': 'SWE'},
        'official_sources': [profile, programme],
        'official_career_contexts': [{
            'source_family': 'dif-period-match-programme-v1', 'url': PROGRAM_URL,
            'sha256': programme['sha256'], 'body': _bind(PROGRAM_PDF),
            'receipt': _bind(PROGRAM_RECEIPT), 'opponent': 'Shamrock Rovers',
            'text_extraction': programme['text_extraction'],
        }],
    }
    jug_path = base.game_path / 'DBDAT/JUG98030.FDI'
    jug = jug_path.read_bytes()
    entry = next(e for e in IndexedFDIFile.from_bytes(jug).entries if e.record_id == TARGET)
    raw = entry.decode_payload(jug)
    end = native_player(raw, TARGET)['name_end']
    code = raw[end + 8] ^ 0x61
    codes = compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    native_country = next(label for label, value in codes.items() if value == code)
    return {
        'schema': common.INPUT_SCHEMA, 'kind': common.ADJUDICATED_KIND,
        'season': base.season, 'release_id': base.release_id,
        'changes': [{
            'carrier_id': TARGET, 'before': copy.deepcopy(actor),
            'field_mask': ['birth_date', 'nationality'], 'witness': witness,
            'native_before_birth_date': witness['native_before_birth_date'],
            'native_before_country': native_country,
        }],
    }


def test_actual_r316_dif_profile_and_period_programme_facts_roundtrip_and_G0_role_guard():
    assert Path(career.__file__).resolve() == ROOT / 'scripts/season_official_career_context_v1.py'
    assert Path(adjudicated.__file__).resolve() == ROOT / 'scripts/season_adjudicated_player_facts_v1.py'
    assert Path(role_api.__file__).resolve() == ROOT / 'scripts/season_dated_parent_facts_editorial_role_v1.py'
    base = registry.load_registered_release(SEASON, PARENT_ID)
    assert base.manifest_sha256 == 'e3e4a9698ae686ca52f1e8949ff6845f7207ab6a7b7793436710fc08277cda1f'
    package = pipeline.read_json_file(base.package_path)
    actor = next(row for row in package['players'] if row['carrier_id'] == TARGET)
    request = _input(base, actor)
    request_path = PRIVATE / 'request/isaksson-r316-facts-input.json'
    _write_once(request_path, request)
    plan = common.prepare(base, request_path)
    common.verify(base, plan)
    bound = common.bind(package, plan)
    before_jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    before_eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    after_jug, after_eq = common.apply(before_jug, before_eq, plan)
    assert after_eq == before_eq
    assert [i for i, (old, new) in enumerate(zip(before_jug, after_jug)) if old != new] == [
        mask['file_offset'] for mask in plan['updates'][0]['native_masks'] if mask['before'] != mask['after']]
    facts_changed = [i for i, (old, new) in enumerate(zip(before_jug, after_jug)) if old != new]
    assert len(facts_changed) == 3
    updated = next(row for row in bound['players'] if row['carrier_id'] == TARGET)
    assert updated['facts']['birth_date'] == '1981-10-03'
    assert updated['facts']['nationality'] == 'SWE'
    assert updated['facts']['primary_position'] == 'G'
    assert updated['facts']['height_cm'] == {'policy': 'preserve-existing-mode1'}
    assert updated['facts']['fine_roles'] == {'policy': 'preserve-existing-mode1'}
    assert all(row == updated if row['carrier_id'] == TARGET else row == next(
        before for before in package['players'] if before['carrier_id'] == row['carrier_id'])
        for row in bound['players'])
    assert career.verify_official_source_claims(request['changes'][0]['witness']) == {
        'birth_date': '1981-10-03', 'nationality': 'SWE'}
    context = career.verify_official_career_contexts(
        request['changes'][0]['witness'], request['changes'][0]['witness']['annual_identity'],
        source_club='Djurgårdens IF')[0]
    assert context['position_literal'] == 'Goalkeeper'
    assert context['fixture_date'] == '2002-08-15'
    assert role_api.EDITORIAL_ROLE_BY_BROAD['G'] == 0
    current = native_facts(after_jug, TARGET)
    assert current['birth_date'] == '1981-10-03'
    pre_entry = next(e for e in IndexedFDIFile.from_bytes(before_jug).entries if e.record_id == TARGET)
    pre_payload = pre_entry.decode_payload(before_jug)
    name_end = native_player(pre_payload, TARGET)['name_end']
    original_country_code = pre_payload[name_end + 8] ^ 0x61
    post = next(e for e in IndexedFDIFile.from_bytes(after_jug).entries if e.record_id == TARGET)
    assert (post.decode_payload(after_jug)[name_end + 8] ^ 0x61) == original_country_code


    old_actor = next(row for row in package['players'] if row['carrier_id'] == TARGET)
    fact_update = plan['updates'][0]
    fact_update_for_role = {'values': fact_update['values']}
    annual_club, annual_row = _annual_row(pipeline.read_json_file(PREALLOCATION))
    role_evidence = role_api._official_annual_role_context(
        request['changes'][0]['witness'], annual_row, annual_club, updated,
        fact_update_for_role, ROW_SHA, SEASON)
    assert role_evidence['published_broad_role'] == 'G'
    factory_raw, _, _, factory_end, factory_roles, factory_native, factory_facts = role_api._factory_roles(TARGET)
    assert factory_roles == [13, 98, 98, 98, 98, 98]
    assert factory_native['name'] != NAME and factory_facts['position'] == 'F'
    assert role_api._factory_role_seed_guard_ok(factory_native['name'], NAME,
        factory_facts['position'], 'G', factory_roles, True)
    role_after, role_masks = rewrite_indexed_native_roles(after_jug, {TARGET: [0]})
    changed_role = [i for i, (old, new) in enumerate(zip(after_jug, role_after)) if old != new]
    assert len(changed_role) == 1
    assert len([i for i, (old, new) in enumerate(zip(before_jug, role_after)) if old != new]) == 4
    entry = next(e for e in IndexedFDIFile.from_bytes(role_after).entries if e.record_id == TARGET)
    end, roles = read_indexed_native_roles(entry.decode_payload(role_after), TARGET)
    assert roles == [0, 98, 98, 98, 98, 98]
    role_pre_entry = next(e for e in IndexedFDIFile.from_bytes(after_jug).entries if e.record_id == TARGET)
    role_pre_payload = role_pre_entry.decode_payload(after_jug)
    role_start, before_roles = read_indexed_native_roles(role_pre_payload, TARGET)
    mask_rows = []
    for i in range(6):
        offset = role_start + 2 + i
        absolute = role_pre_entry.payload_offset + offset
        mask_rows.append({'file': 'DBDAT/JUG98030.FDI', 'record_offset': offset,
            'file_offset': absolute, 'before': after_jug[absolute], 'after': role_after[absolute]})
    role_plan = {'schema': role_api.SCHEMA, 'kind': role_api.KIND,
        'updates': [{'carrier_id': TARGET, 'field_mask': ['fine_roles'],
            'values': {'fine_roles': [0]}, 'native_masks': mask_rows,
            'before_native_roles': before_roles, 'after_native_roles': roles,
            'expected_owner': 957, 'evidence': {'dated_role_evidence': {
                'published_broad_role': 'G'}}}]}
    role_api.validate_mask(role_plan)
    proof = {
        'schema': 'pm99-private-r318-dif-facts-G0-integration-proof-v1',
        'status': 'PASS_PRIVATE_SOURCE_API_ROUNDTRIP_NOT_BUILT',
        'parent_release_id': PARENT_ID, 'parent_manifest_sha256': base.manifest_sha256,
        'fact_plan': plan, 'fact_plan_sha256': hashlib.sha256(packages.canonical_json_bytes(plan)).hexdigest(),
        'facts_changed_offsets': facts_changed,
        'role_changed_offset': changed_role[0], 'role_end': end,
        'final_native_roles': roles, 'eq_unchanged': after_eq == before_eq,
        'official_sources': [request['changes'][0]['witness']['official_sources'][0]['sha256'],
                             request['changes'][0]['witness']['official_sources'][1]['sha256']],
        'source_plan_semantics_unchanged': True,
        'catalog_or_game_written': False,
    }
    _write_once(PRIVATE / 'proofs/actual-r316-integration-proof-v1.json', proof)


def test_period_programme_context_rejects_dob_different_from_adjudicated_fact():
    base = registry.load_registered_release(SEASON, PARENT_ID)
    package = pipeline.read_json_file(base.package_path)
    actor = next(row for row in package['players'] if row['carrier_id'] == TARGET)
    request = _input(base, actor)
    witness = request['changes'][0]['witness']
    witness['values']['birth_date'] = '1981-10-04'
    with pytest.raises(ValueError, match='career-context birthday differs'):
        career.verify_official_career_contexts(
            witness, witness['annual_identity'], source_club='Djurgårdens IF')
