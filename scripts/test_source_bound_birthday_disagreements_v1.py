from types import SimpleNamespace
import pytest

from scripts import season_kit_render_bindings_v1
from scripts import season_source_bound_birthday_disagreements_v1 as dates


def native_fixture(tmp_path, monkeypatch):
    db = tmp_path / 'DBDAT'; db.mkdir()
    (db / 'JUG98030.FDI').write_bytes(b'old-native')
    monkeypatch.setattr(dates.registry, 'load_registered_release', lambda *a: SimpleNamespace(game_path=tmp_path))
    plan = dict(schema=dates.SCHEMA, season='2007-08', release_id='original',
        jug_sha256=dates.digest(b'old-native'), eq_sha256=dates.digest(b'exact-EQ'),
        updates=[dict(carrier_id=123, native_name='original person',
                      before_birth_date='1987-07-04', birth_date='1984-07-04')])
    def rewrite(raw, updates):
        if raw == b'old-native':
            return b'new-native', [dict(carrier_id=123)]
        if raw == b'new-native':
            return raw, []
        raise ValueError('unknown data')
    monkeypatch.setattr(dates, 'rewrite_indexed_native_birth_dates', rewrite)
    return plan


@pytest.mark.parametrize('raw', [b'old-native', b'new-native'])
def test_exact_preimage_or_complete_postimage_only(tmp_path, monkeypatch, raw):
    plan = native_fixture(tmp_path, monkeypatch)
    assert dates.apply(raw, b'exact-EQ', plan) == (b'new-native', b'exact-EQ')


@pytest.mark.parametrize('fault', ['schema', 'EQ', 'JUG', 'empty', 'duplicate', 'unrelated-jug'])
def test_no_unrelated_or_partial_preimages(tmp_path, monkeypatch, fault):
    plan = native_fixture(tmp_path, monkeypatch)
    raw = b'old-native'; eq = b'exact-EQ'
    if fault == 'schema': plan['schema'] = 'unreviewed'
    if fault == 'EQ': eq = b'other-EQ'
    if fault == 'JUG': plan['jug_sha256'] = '0' * 64
    if fault == 'empty': plan['updates'] = []
    if fault == 'duplicate': plan['updates'] *= 2
    if fault == 'unrelated-jug': raw = b'other-data'
    with pytest.raises(ValueError):
        dates.apply(raw, eq, plan)


def test_unrelated_compiler_receipt_does_not_claim_latest_layer(tmp_path):
    receipt = tmp_path / 'compiler.json'
    dates.pipeline.write_canonical_json(receipt, dict(compilation_mode='later-manager-layer'))
    assert dates.reconstruction(SimpleNamespace(compiler_receipt_path=receipt), 'proof') is None


def test_source_verification_requires_exact_reproduction(monkeypatch):
    monkeypatch.setattr(dates, 'prepare', lambda base: {'schema': dates.SCHEMA, 'literal': 'original'})
    with pytest.raises(ValueError, match='did not reproduce'):
        dates.verify(object(), dict(schema=dates.SCHEMA, literal='changed source'))
