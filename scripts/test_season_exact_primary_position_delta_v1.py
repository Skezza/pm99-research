import hashlib
from types import SimpleNamespace

import pytest

from scripts import season_exact_primary_position_delta_v1 as subject


@pytest.mark.parametrize('label,expected', [('CDM','M'),('CM','M'),('CB','D'),('LW','F'),('ST','F')])
def test_exact_taxonomy_does_not_infer_side(label, expected):
    assert subject.primary(label) == expected


@pytest.mark.parametrize('label', ['GK', '', 'Unknown', 'midfield'])
def test_unsupported_and_goalkeeper_conversions_refused(label):
    with pytest.raises(ValueError):
        subject.primary(label)


def test_factory_compile_cannot_silently_discard_position_layer():
    with pytest.raises(ValueError, match='exact SOURCE'):
        subject.reject_factory_recipe({'artifacts':[{'id':subject.PREFIX+'proof'}]})


@pytest.mark.parametrize('targets', [[], [1, 1], [True], ['1']])
def test_targets_explicit_unique_and_integer(targets):
    with pytest.raises(ValueError, match='explicit unique integer'):
        subject.prepare(None, targets)


def test_role_writer_changes_only_dd6361_broad_byte_and_preserves_adjacent_unknown(monkeypatch, tmp_path):
    root = tmp_path/'game/DBDAT'
    root.mkdir(parents=True)
    before = bytes(range(100))
    (root/'JUG98030.FDI').write_bytes(before)
    entry = SimpleNamespace(record_id=1, payload_offset=20)
    monkeypatch.setattr(subject.registry, 'load_registered_release',
                        lambda *args: SimpleNamespace(game_path=root.parent))
    monkeypatch.setattr(subject, 'IndexedFDIFile', SimpleNamespace(
        from_bytes=lambda data: SimpleNamespace(entries=[entry])))
    monkeypatch.setattr(subject, 'rewrite_indexed_native_roles', lambda raw, rows: (raw, []))
    plan = dict(schema=subject.SCHEMA, season='2021-22', release_id='parent',
        jug_sha256=hashlib.sha256(before).hexdigest(), eq_sha256=hashlib.sha256(b'eq').hexdigest(),
        updates=[dict(carrier_id=1, fine_roles=[14, 9], primary_position='M', before_native={'name_end':30})])
    after, eq = subject.apply(before, b'eq', plan)
    assert eq == b'eq'
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b] == [61]
    assert before[60] == after[60]
    assert subject.apply(after, b'eq', plan) == (after, b'eq')
    with pytest.raises(ValueError, match='preimage nor postimage'):
        subject.apply(b'corrupted', b'eq', plan)


def test_adjacent_skill_change_is_rejected(monkeypatch, tmp_path):
    root = tmp_path/'game/DBDAT'; root.mkdir(parents=True)
    before = bytes(range(100)); (root/'JUG98030.FDI').write_bytes(before)
    monkeypatch.setattr(subject.registry, 'load_registered_release',lambda *args:SimpleNamespace(game_path=root.parent))
    monkeypatch.setattr(subject, 'IndexedFDIFile', SimpleNamespace(from_bytes=lambda data:
        SimpleNamespace(entries=[SimpleNamespace(record_id=1,payload_offset=20)])))
    monkeypatch.setattr(subject, 'rewrite_indexed_native_roles',lambda raw,rows:(b'X'+raw[1:],[]))
    plan=dict(schema=subject.SCHEMA,season='2021-22',release_id='parent',
        jug_sha256=hashlib.sha256(before).hexdigest(),eq_sha256=hashlib.sha256(b'eq').hexdigest(),
        updates=[dict(carrier_id=1,fine_roles=[14],primary_position='M',before_native={'name_end':30})])
    with pytest.raises(ValueError,match='another native field'):
        subject.apply(before,b'eq',plan)
