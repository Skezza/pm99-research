import copy

import pytest

from app.editor_actions import _indexed_variable_name_runtime_segments
from app.fdi_indexed import IndexedFDIFile
from scripts import season_number_label_names_v2 as names
from scripts.test_season_package_compiler_v2 import _dd6361_player_payload, _indexed_fdi


def example(modern_year=True):
    raw = _dd6361_player_payload(2, role=3)
    end = names.audit.native_player(raw, 2)['name_end']
    surname = b'de la Cruz'
    display = b'#4 John DE LA CRUZ'
    raw = (raw[:8] + bytes([len(surname) ^ 0x61, 0x61]) + surname
        + bytes([len(display) ^ 0x61, 0x61]) + display + raw[end:])
    native = names.audit.native_player(raw, 2)
    person = dict(id='p', carrier_id=2, name='#4 John de la Cruz', source_name='#4 John de la Cruz',
        facts=dict(birth_date='2004-11-16' if modern_year else '1990-11-16', quality=50))
    row = dict(carrier_id=2, player_id='p', before_player=person, before_native_name=native['name'],
        display_name='John de la Cruz', source_name='John de la Cruz', repair_birth_year=modern_year,
        birth_date=person['facts']['birth_date'], before_birth_year=1990,
        before_payload_sha256=names.digest(raw))
    changed, metadata = names.renamed_payload(raw, row)
    row.update(after_payload_sha256=names.digest(changed), name_metadata=metadata)
    jug = _indexed_fdi([(2, '', raw), (4, '', _dd6361_player_payload(4))])
    plan = dict(schema=names.SCHEMA, season='2020-21', updates=[row], jug_sha256=names.digest(jug))
    return jug, plan


@pytest.mark.parametrize('modern_year', [True, False])
def test_exact_suffix_surname_and_other_records_survive(modern_year):
    jug, plan = example(modern_year)
    result = names.apply(jug, plan)
    assert len(result) == len(jug)
    assert names.apply(result, plan) == result
    before = {e.record_id: e.decode_payload(jug) for e in IndexedFDIFile.from_bytes(jug).entries}
    after = {e.record_id: e.decode_payload(result) for e in IndexedFDIFile.from_bytes(result).entries}
    assert before[4] == after[4]
    a, b = before[2], after[2]
    old, new = _indexed_variable_name_runtime_segments(a), _indexed_variable_name_runtime_segments(b)
    assert a[:old['full_len_offset']] == b[:new['full_len_offset']]
    assert a[old['surname_start']:old['surname_end']] == b'de la Cruz'
    old_suffix = bytearray(a[old['full_name_end']:])
    new_suffix = b[new['full_name_end']:new['full_name_end'] + len(old_suffix)]
    if modern_year:
        old_suffix[14:16] = bytes(value ^ 0x61 for value in (2004).to_bytes(2, 'little'))
    assert bytes(old_suffix) == new_suffix
    assert old['full_name_end'] == new['full_name_end']
    assert a[old['full_len_offset']:old['full_name_start']] == b[new['full_len_offset']:new['full_name_start']]
    assert b[new['full_name_end'] + len(old_suffix):] == b''
    assert b[new['full_name_start']:new['full_name_end']] == b'John DE LA CRUZ   '


@pytest.mark.parametrize('fault', ['schema', 'before', 'after', 'person', 'duplicate', 'whole-file', 'metadata'])
def test_stale_forged_or_unrelated_native_changes_are_refused(fault):
    jug, plan = example()
    row = plan['updates'][0]
    if fault == 'schema': plan['schema'] = 'other'
    elif fault == 'before': row['before_payload_sha256'] = 'changed'
    elif fault == 'after': row['after_payload_sha256'] = 'changed'
    elif fault == 'person': row['display_name'] = 'Other Person'
    elif fault == 'duplicate': plan['updates'].append(copy.deepcopy(row))
    elif fault == 'whole-file': plan['jug_sha256'] = 'changed'
    else: row['name_metadata']['original_surname_component_preserved'] = False
    with pytest.raises(ValueError): names.apply(jug, plan)


def test_recipe_facts_and_prior_evidence_are_not_rewritten():
    _, plan = example()
    package = dict(players=[copy.deepcopy(plan['updates'][0]['before_player'])],
        clubs=[dict(id='unchanged')], artifacts=[dict(id='prior')])
    original = copy.deepcopy(package)
    result = names.bind(package, plan)
    assert package == original
    assert result['players'][0] == dict(original['players'][0], name='John de la Cruz', source_name='John de la Cruz')
    assert result['clubs'] == package['clubs']
    assert package['artifacts'][0] in result['artifacts']
    with pytest.raises(ValueError): names.bind(result, plan)


@pytest.mark.parametrize('name', ['#1 Joe Bloggs', '# 23 Joe Bloggs', '#123 Joe Bloggs'])
def test_only_explicit_numeric_heading_is_removed(name):
    assert names.undecorated(name) == 'Joe Bloggs'


@pytest.mark.parametrize('name', ['Joe Bloggs', '#Joe Bloggs', '#1234 Joe Bloggs', 'Joe #1 Bloggs'])
def test_real_name_text_is_not_sanitized(name):
    assert names.undecorated(name) == name
