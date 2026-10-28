import copy
import hashlib
from types import SimpleNamespace

import pytest

from scripts import season_manager_owner_isolation_v1 as subject
from app.xor import xor_decode, xor_encode


def fixture():
    package = {'players': [{'id': 'untouched'}], 'managers': [
        {'id': 'manager-1190', 'carrier_id': 1190, 'name': 'Shared Coach', 'policy': 'preserve-existing-mode1'}],
        'clubs': [{'id': 'club-8', 'carrier_id': 8, 'manager_id': 'manager-1190'},
                  {'id': 'club-3002', 'carrier_id': 3002, 'manager_id': 'manager-1190'}]}
    row = dict(club_id='club-8', club_carrier_id=8, from_manager_id='manager-1190',
               from_carrier_id=1190, to_manager_id='manager-1829', to_carrier_id=1829,
               to_raw_record_sha256=hashlib.sha256(b'newspare!').hexdigest())
    update = dict(manager_id='manager-1829', carrier_id=1829, club_id='club-8',
                  club_carrier_id=8, before='Shared Coach', before_policy='preserve-existing-mode1')
    return package, dict(owner_isolations=[row], updates=[update, dict(manager_id='manager-1190', carrier_id=1190, club_id='club-3002', club_carrier_id=3002)])


def test_recipe_split_preserves_original_coach_other_owner_and_input():
    package, plan = fixture(); original = copy.deepcopy(package)
    after = subject.prepare_recipe(package, plan)
    assert package == original
    assert after['players'] == original['players']
    assert after['managers'][:-1] == original['managers']
    assert after['clubs'][1] == original['clubs'][1]
    assert after['clubs'][0] == dict(original['clubs'][0], manager_id='manager-1829')
    assert after['managers'][-1] == dict(original['managers'][0], id='manager-1829', carrier_id=1829)


def test_recipe_split_allows_sourced_correction_for_sole_remaining_owner():
    package, plan = fixture()
    after = subject.prepare_recipe(package, plan)
    assert after['clubs'][0]['manager_id'] == 'manager-1829'
    assert after['clubs'][1]['manager_id'] == 'manager-1190'
    assert after['managers'][0] == package['managers'][0]


def test_remaining_coach_update_rejects_third_owner():
    package, plan = fixture()
    package['clubs'].append(dict(id='club-3003', carrier_id=3003,
                                 manager_id='manager-1190'))
    with pytest.raises(ValueError, match='sole remaining owner'):
        subject.prepare_recipe(package, plan)


@pytest.mark.parametrize('bad', ['existing_slot', 'exclusive_owner', 'wrong_source', 'missing_update', 'rename_parent', 'boolean_id'])
def test_recipe_rejects_unbound_or_unnecessary_splits(bad):
    package, plan = fixture()
    if bad == 'existing_slot': package['managers'].append(dict(id='manager-1829', carrier_id=1829))
    elif bad == 'exclusive_owner': package['clubs'].pop()
    elif bad == 'wrong_source': package['clubs'][0]['manager_id'] = 'manager-7'
    elif bad == 'missing_update': plan['updates'].clear()
    elif bad == 'rename_parent': plan['updates'].append(dict(manager_id='manager-1190'))
    else: plan['owner_isolations'][0]['to_carrier_id'] = True
    with pytest.raises(ValueError): subject.prepare_recipe(package, plan)


def native_fixture(monkeypatch, inactive_spare=False):
    # Synthetic containers exercise orchestration; SDK tests cover real layout parsing.
    def record(active, prefix=0):
        return prefix.to_bytes(4, 'little') + active.to_bytes(4, 'little') + b'TAIL'
    eq = record(1190) + record(1190, 1829 if inactive_spare else 0) + record(99)
    ent = b'oldcoach!' + b'newspare!'
    def entry(id, offset, length):
        return SimpleNamespace(record_id=id, payload_offset=offset, payload_length=length,
                               decode_payload=lambda data: xor_decode(data[offset:offset+length]))
    def index(data):
        return SimpleNamespace(entries=[entry(1190, 0, 9), entry(1829, 9, 9)] if len(data)==18 else
                               [entry(8, 0, 12), entry(3002, 12, 12), entry(7, 24, 12)])
    monkeypatch.setattr(subject, 'IndexedFDIFile', SimpleNamespace(from_bytes=index))
    def links(raw):
        prefix=int.from_bytes(raw[:4], 'little');active=int.from_bytes(raw[4:8], 'little')
        return SimpleNamespace(manager_record_ids=((prefix,) if prefix else ())+(active,), active_manager_record_id=active)
    monkeypatch.setattr(subject, 'parse_indexed_eq_manager_links', links)
    monkeypatch.setattr(subject, 'patch_indexed_eq_active_manager_id', lambda raw, id: raw[:4]+id.to_bytes(4,'little')+raw[8:])
    def rebuild(data, idx, replacements):
        out=bytearray(data)
        for e in idx.entries:
            if e.record_id in replacements: out[e.payload_offset:e.payload_offset+e.payload_length]=xor_encode(replacements[e.record_id])
        return bytes(out)
    monkeypatch.setattr(subject, '_rebuild_indexed', rebuild)
    return eq, ent


def test_native_split_changes_only_target_active_link(monkeypatch):
    package, plan = fixture(); eq, ent = native_fixture(monkeypatch)
    after = subject.apply_native(eq, ent, package, plan)
    assert after[:4] == eq[:4] and after[4:8] == (1829).to_bytes(4, 'little')
    assert after[8:] == eq[8:]
    assert ent == b'oldcoach!newspare!'


def test_native_inactive_reference_protects_spare(monkeypatch):
    package, plan = fixture(); eq, ent = native_fixture(monkeypatch, inactive_spare=True)
    with pytest.raises(ValueError, match='active or inactive'): subject.apply_native(eq, ent, package, plan)


def test_native_spare_preimage_is_mandatory(monkeypatch):
    package, plan = fixture(); eq, ent = native_fixture(monkeypatch)
    with pytest.raises(ValueError, match='preimage'): subject.apply_native(eq, ent[:-1]+b'?', package, plan)


def test_split_requires_sourced_remaining_owner_decision():
    package, plan = fixture()
    plan['updates'] = plan['updates'][:1]
    with pytest.raises(ValueError, match='sourced decision'):
        subject.prepare_recipe(package, plan)


def test_new_manager_preserves_required_lexicographic_actor_order():
    package, plan = fixture()
    package['managers'].append(dict(id='manager-3000', carrier_id=3000))
    after = subject.prepare_recipe(package, plan)
    assert [row['id'] for row in after['managers']] == [
        'manager-1190', 'manager-1829', 'manager-3000']
    assert after['managers'][2] == package['managers'][1]
