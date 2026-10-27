import copy
from datetime import date
from types import SimpleNamespace

import pytest

from app.fdi_indexed import IndexedFDIFile
from scripts import season_authored_player_roles_v1 as subject
from scripts.test_season_package_compiler_v2 import (
    _dd6360_player_payload, _dd6361_player_payload, _indexed_fdi,
)


def actor():
    return dict(id='p', carrier_id=1, name='Player One', source_name='Player One',
                person_id='same-person', club_id='c', ratings={'quality': 55},
                facts=dict(primary_position='D', fine_roles=[4],
                           birth_date='1990-01-01', nationality='ENG'))


def pair(monkeypatch):
    def closed(before, after, request):
        assert request['selection_kind'] == 'players-only'
        assert request['club_carrier_ids'] == []
        return set(), {'p'}, set()
    monkeypatch.setattr(subject.common, 'verify_recipe_mask', closed)
    before = dict(players=[actor()], assets={'portraits': []})
    after = copy.deepcopy(before)
    after['players'][0]['facts'].update(primary_position='M', fine_roles=[9, 14])
    request = dict(selection_kind='same-identity-player-roles', club_carrier_ids=[])
    return before, after, request


def test_same_identity_role_mask_does_not_require_an_opening_rewrite(monkeypatch):
    before, after, request = pair(monkeypatch)
    assert subject.verify_recipe_mask(before, after, request) == {'p'}


@pytest.mark.parametrize('field,value', [
    ('name', 'Another Name'), ('source_name', 'Another Person'),
    ('person_id', 'different-person'), ('club_id', 'other-club'),
    ('carrier_id', 2), ('ratings', {'quality': 99}),
])
def test_role_mask_rejects_identity_owner_and_ability_changes(monkeypatch, field, value):
    before, after, request = pair(monkeypatch)
    after['players'][0][field] = value
    with pytest.raises(ValueError, match='identity or another player field'):
        subject.verify_recipe_mask(before, after, request)


@pytest.mark.parametrize('field,value', [('birth_date', '1980-01-01'),
                                        ('nationality', 'FRA'), ('height_cm', 200)])
def test_role_mask_rejects_other_fact_changes(monkeypatch, field, value):
    before, after, request = pair(monkeypatch)
    after['players'][0]['facts'][field] = value
    with pytest.raises(ValueError, match='non-role fact'):
        subject.verify_recipe_mask(before, after, request)


@pytest.mark.parametrize('broad,fine', [('M', [4]), ('M', [0]), ('G', [0]),
                                     ('M', [9, 9]), ('M', [True]), ('M', [[]])])
def test_role_mask_refuses_incompatible_or_goalkeeper_conversions(monkeypatch, broad, fine):
    before, after, request = pair(monkeypatch)
    after['players'][0]['facts'].update(primary_position=broad, fine_roles=fine)
    with pytest.raises(ValueError):
        subject.verify_recipe_mask(before, after, request)


def test_roles_cannot_clear_portraits_or_change_unrelated_fallbacks(monkeypatch):
    before, after, request = pair(monkeypatch)
    after['assets']['portraits'] = ['removed-face']
    with pytest.raises(ValueError, match='assets'):
        subject.verify_recipe_mask(before, after, request)
    after['assets'] = copy.deepcopy(before['assets'])
    after['players'][0]['fact_fallbacks'] = [{'field': 'height_cm', 'value': 200}]
    with pytest.raises(ValueError, match='provenance'):
        subject.verify_recipe_mask(before, after, request)


def native_case(tmp_path, monkeypatch, family):
    pair(monkeypatch)
    monkeypatch.setattr(subject.r, 'ROOT', tmp_path)
    payload = bytearray(_dd6360_player_payload(1, role_code=4) if family == 'compact'
                        else _dd6361_player_payload(1, role=4))
    native = subject.audit.native_player(bytes(payload), 1)
    payload[native['name_end'] + 11] = 1 ^ 0x61
    data = _indexed_fdi([(1, '', bytes(payload)),
                         (2, '', _dd6360_player_payload(2, role_code=4))])
    db = tmp_path / 'game/DBDAT'
    db.mkdir(parents=True)
    for name, raw in [('JUG98030.FDI', data), ('EQ98030.FDI', b'unchanged-roster'),
                      ('ENT98030.FDI', b'unchanged-manager'), ('MINIFOTO.PKF', b'face'),
                      ('TEXTOS.PKF', b'texts')]:
        (db / name).write_bytes(raw)
    native = subject.audit.native_player(bytes(payload), 1)
    end = native['name_end']
    born = date(int.from_bytes(bytes(v ^ 0x61 for v in payload[end+14:end+16]), 'little'),
                payload[end+13] ^ 0x61, payload[end+12] ^ 0x61).isoformat()
    old = actor()
    old.update(name=native['name'], source_name=native['name'])
    old['facts']['birth_date'] = born
    before = dict(players=[old], clubs=[dict(id='c', carrier_id=10)], assets={})
    after = copy.deepcopy(before)
    after['players'][0]['facts'].update(primary_position='M', fine_roles=[9, 14])
    parent = tmp_path / 'parent.json'
    child = tmp_path / 'child.json'
    subject.p.write_canonical_json(parent, before)
    subject.p.write_canonical_json(child, after)
    base = SimpleNamespace(season='2018-19', release_id='parent', manifest_sha256='a'*64,
                           package_path=parent, game_path=db.parent)
    def bound(path):
        return dict(path=str(path.relative_to(tmp_path)), sha256=subject.r.sha256_file(path))
    receipt = tmp_path / 'receipt.json'
    subject.p.write_canonical_json(receipt, dict(country='fixture', source_bindings=[],
        child_recipe_sha256=subject.r.sha256_file(child)))
    request = dict(schema=subject.SCHEMA+'-input', parent=subject._parent(base),
                   selection_kind='same-identity-player-roles', country='fixture',
                   club_carrier_ids=[], player_ids=['p'], child_recipe=bound(child),
                   authoring_receipt=bound(receipt))
    monkeypatch.setattr(subject.owners, 'native_owners', lambda eq: {1: {10}})
    return base, request, data


@pytest.mark.parametrize('family', ['compact', 'extended'])
def test_native_starter_role_edit_preserves_every_other_byte(tmp_path, monkeypatch, family):
    base, request, before = native_case(tmp_path, monkeypatch, family)
    result = subject._reconstruct(base, request)
    entry = IndexedFDIFile.from_bytes(before).entries[0]
    old = entry.decode_payload(before)
    end = subject.audit.native_player(old, 1)['name_end']
    allowed = {entry.payload_offset + end + i for i in (*range(2, 8), 11)}
    changed = {i for i, (a, b) in enumerate(zip(before, result['jug'])) if a != b}
    assert changed and changed <= allowed
    assert len(before) == len(result['jug'])
    assert result['jug'][entry.payload_offset+end+10] == before[entry.payload_offset+end+10]
    assert result['eq'] == b'unchanged-roster'
    assert result['ent'] == b'unchanged-manager'
    assert result['selected_clubs'] == result['selected_managers'] == []


@pytest.mark.parametrize('problem', ['DOB', 'name', 'owner', 'source'])
def test_native_role_write_refuses_wrong_person_owner_or_changed_inputs(tmp_path, monkeypatch, problem):
    base, request, before = native_case(tmp_path, monkeypatch, 'compact')
    if problem == 'owner':
        monkeypatch.setattr(subject.owners, 'native_owners', lambda eq: {1: {10, 20}})
    elif problem == 'source':
        (tmp_path / 'child.json').write_bytes(b'changed source')
    else:
        # Alter both recipe snapshots coherently: the actual native person must
        # still independently agree, rather than trusting the two JSON copies.
        for name in ['parent.json', 'child.json']:
            path = tmp_path / name
            doc = subject.p.read_json_file(path)
            if problem == 'DOB':
                doc['players'][0]['facts']['birth_date'] = '1980-01-01'
            else:
                doc['players'][0]['name'] = 'Another Person'
            path.write_bytes(subject.packages.canonical_json_bytes(doc))
        request['parent'] = subject._parent(base)
        receipt = tmp_path / 'receipt.json'
        doc = subject.p.read_json_file(receipt)
        doc['child_recipe_sha256'] = subject.r.sha256_file(tmp_path/'child.json')
        receipt.write_bytes(subject.packages.canonical_json_bytes(doc))
        for key, path in [('child_recipe', tmp_path/'child.json'),
                          ('authoring_receipt', receipt)]:
            request[key]['sha256'] = subject.r.sha256_file(path)
    with pytest.raises(ValueError):
        subject._reconstruct(base, request)
    assert (base.game_path/'DBDAT/JUG98030.FDI').read_bytes() == before
