import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.editor_actions import _indexed_variable_name_runtime_segments
from app.fdi_indexed import IndexedFDIFile
from scripts import season_numeric_name_format_only_v1 as names
from scripts.test_season_package_compiler_v2 import (
    _indexed_fdi, _dd6360_player_payload, _dd6361_player_payload,
)


def labelled(family, carrier=2):
    raw = (_dd6360_player_payload if family == 'dd6360' else _dd6361_player_payload)(carrier)
    segments = _indexed_variable_name_runtime_segments(raw)
    end = segments['full_name_end']
    surname = raw[segments['surname_start']:segments['surname_end']].decode('cp1252')
    display = '#. ' + surname if family == 'dd6360' else '#19 John ' + surname
    length = bytes(value ^ 0x61 for value in len(display).to_bytes(2, 'little'))
    return raw[:segments['full_len_offset']] + length + display.encode('cp1252') + raw[end:]


@pytest.mark.parametrize('family', ['dd6360', 'dd6361'])
def test_formatting_keeps_directory_surname_cursors_complete_suffix_and_other_person(tmp_path, family):
    raw = labelled(family)
    native = names.audit.native_player(raw, 2)
    untouched = _dd6361_player_payload(1)
    jug = _indexed_fdi([(1, '', untouched), (2, '', raw)])
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    (game / 'DBDAT/JUG98030.FDI').write_bytes(jug)
    # No DOB, nationality, profile body or source biography is needed to
    # remove a syntactic label while retaining every actual biography byte.
    person = dict(id='p2', carrier_id=2, name=native['name'], source_name='#19 John B',
                  facts={'unknown_secondary_fact': None}, ratings={'keep': 47})
    package = dict(players=[person], artifacts=[])
    package_path = tmp_path / 'package.json'
    package_path.write_text(json.dumps(package))
    release = SimpleNamespace(season='2024-25', release_id='fixture',
                              package_path=package_path, game_path=game)
    plan = names.prepare(release)
    assert len(plan['updates']) == 1 and not plan['unresolved']
    names.verify(release, plan)
    patched = names.apply(jug, plan)
    assert names.apply(patched, plan) == patched
    old_index, new_index = IndexedFDIFile.from_bytes(jug), IndexedFDIFile.from_bytes(patched)
    old_entries = {e.record_id: e for e in old_index.entries}
    new_entries = {e.record_id: e for e in new_index.entries}
    changed = new_entries[2].decode_payload(patched)
    segments = _indexed_variable_name_runtime_segments(raw)
    start, end = segments['full_name_start'], segments['full_name_end']
    assert len(patched) == len(jug)
    assert new_entries[1].decode_payload(patched) == untouched
    assert [(e.payload_offset, e.payload_length) for e in new_index.entries] == [
        (e.payload_offset, e.payload_length) for e in old_index.entries]
    assert changed[:start] == raw[:start]
    assert changed[end:] == raw[end:]
    assert names.audit.native_player(changed, 2)['name_end'] == end
    assert names.literal(names.audit.native_player(changed, 2)['name']) == names.literal(names.clean(native['name']))
    bound = names.bind(package, plan)
    assert package['players'][0] == person
    assert bound['players'][0]['facts'] == person['facts']
    assert bound['players'][0]['ratings'] == person['ratings']
    assert plan['updates'][0]['before_player']['source_name'] == '#19 John B'
    assert bound['players'][0]['source_name'] == 'John B'


def test_name_only_formatter_refuses_other_text_or_a_changed_baseline(tmp_path):
    raw = labelled('dd6361')
    before = names.audit.native_player(raw, 2)['name']
    row = dict(carrier_id=2, before_native_name=before, display_name='Different Person')
    with pytest.raises(ValueError, match='remaining name text'):
        names.renamed_payload(raw, row)
    with pytest.raises(ValueError, match='whole baseline'):
        names.apply(b'changed', dict(schema=names.SCHEMA, jug_sha256='0' * 64, updates=[row]))


def test_formatting_never_renames_an_undecorated_person():
    raw = _dd6361_player_payload(2)
    before = names.audit.native_player(raw, 2)['name']
    with pytest.raises(ValueError, match='no exact leading label'):
        names.renamed_payload(raw, dict(carrier_id=2, before_native_name=before, display_name=before))


def test_factory_compiler_rejects_a_bound_numeric_formatting_layer():
    package = {'artifacts': [{'id': names.PREFIX + '2024-25'}]}
    with pytest.raises(ValueError, match='source-bound known-good replay'):
        names.reject_factory_recipe(package)
    # Unrelated existing layers remain eligible for the normal factory gate.
    names.reject_factory_recipe({'artifacts': [{'id': 'other-season-input'}]})


def test_source_field_keeps_spelling_aliases_and_unlabelled_whitespace():
    assert names.source_label(None) is None
    assert names.source_label(' Joseph Alan Garner ') == ' Joseph Alan Garner '
    assert names.source_label('#19 Joseph Alan Garner') == 'Joseph Alan Garner'
    assert names.source_label('#19 ') == '#19 '
