import copy
from types import SimpleNamespace

import pytest

from scripts import prepare_reviewed_kit_delta_v1 as kits


def source_fixture(tmp_path, monkeypatch, receipt_metadata=None):
    monkeypatch.setattr(kits.registry, 'ROOT', tmp_path)
    image = tmp_path / 'period.jpg'
    image.write_bytes(b'original-period-image')
    receipt = dict(url='https://example.test/period.jpg', sha256=kits.registry.sha256_file(image))
    receipt.update(receipt_metadata or {})
    kits.pipeline.write_canonical_json(image.with_name('period.jpg.source.json'), receipt)
    catalogue = dict(rows=[dict(status='source-ready', source=dict(reviewed=True,
        evidence=[dict(path='period.jpg', **receipt)]))])
    return catalogue, image


def test_source_replay_accepts_exact_original_receipt(tmp_path, monkeypatch):
    catalogue, _ = source_fixture(tmp_path, monkeypatch)
    kits.verify_sources(catalogue)


def test_source_replay_preserves_richer_capture_metadata(tmp_path, monkeypatch):
    catalogue, image = source_fixture(tmp_path, monkeypatch, dict(
        utc='2026-10-17T12:23:18Z', transport='curl', in_image_year_label='2000-01'))
    path = image.with_name('period.jpg.source.json')
    before = path.read_bytes()
    kits.verify_sources(catalogue)
    assert path.read_bytes() == before


@pytest.mark.parametrize('field,value', [('url', 'https://example.test/other.jpg'),
                                       ('sha256', '0' * 64)])
def test_source_replay_rejects_changed_binding(tmp_path, monkeypatch, field, value):
    catalogue, _ = source_fixture(tmp_path, monkeypatch)
    catalogue['rows'][0]['source']['evidence'][0][field] = value
    with pytest.raises(ValueError, match='receipt differs'):
        kits.verify_sources(catalogue)


def test_source_replay_rejects_changed_original_image(tmp_path, monkeypatch):
    catalogue, image = source_fixture(tmp_path, monkeypatch)
    image.write_bytes(b'substituted-image')
    with pytest.raises(ValueError, match='bytes changed'):
        kits.verify_sources(catalogue)


@pytest.mark.parametrize('mutation', ['unreviewed', 'missing', 'gap'])
def test_no_implicit_design_approval(tmp_path, monkeypatch, mutation):
    catalogue, _ = source_fixture(tmp_path, monkeypatch)
    row = catalogue['rows'][0]
    if mutation == 'unreviewed':
        row['source']['reviewed'] = False
    elif mutation == 'missing':
        row['source']['evidence'] = []
    else:
        row['status'] = 'blocked'
    with pytest.raises(ValueError):
        kits.verify_sources(catalogue)


def test_output_is_never_overwritten(tmp_path):
    output = tmp_path / 'existing'
    output.mkdir()
    with pytest.raises(ValueError, match='immutable'):
        kits.prepare('2005-06', tmp_path / 'absent.json', output)


def test_explicit_parent_refuses_other_season_before_rendering(tmp_path, monkeypatch):
    catalogue, _ = source_fixture(tmp_path, monkeypatch)
    path = tmp_path / 'catalogue.json'
    kits.pipeline.write_canonical_json(path, catalogue)
    monkeypatch.setattr(kits.registry, 'load_preferred_release',
                        lambda *a: pytest.fail('explicit parent must not load preferred'))
    with pytest.raises(ValueError, match='another season'):
        kits.prepare('2017-18', path, tmp_path / 'output',
                     source_release=SimpleNamespace(season='2018-19'))


def test_probe_explicit_parent_refuses_other_season_before_reading(tmp_path, monkeypatch):
    monkeypatch.setattr(kits.registry, 'load_preferred_release',
                        lambda *a: pytest.fail('explicit parent must not load preferred'))
    with pytest.raises(ValueError, match='another season'):
        kits.probe.prepare_batch('2017-18', tmp_path / 'absent.json', tmp_path,
            tmp_path / 'out', source_release=SimpleNamespace(season='2018-19'))


def complete_fixture(tmp_path, monkeypatch):
    game = tmp_path / 'game/DBDAT'
    patch = tmp_path / 'patch/DBDAT'
    for root in [game, patch]:
        root.mkdir(parents=True)
        for name in kits.render.ARCHIVES:
            (root / name).write_bytes(b'archive')
    before = {i: SimpleNamespace(raw_bitmap=f'kit-{i}'.encode()) for i in range(544)}
    after = copy.deepcopy(before)
    after[223].raw_bitmap = b'reviewed-new-kit'
    def records(path):
        return after if path.parent == patch else before
    monkeypatch.setattr(kits.render, '_record_index', records)
    audit = tmp_path / 'original-audit.json'
    kits.pipeline.write_canonical_json(audit, dict(blockers=0, all_records=544,
        records=[dict(carrier_id=i, club='Atalanta' if i == 223 else f'club-{i}',
            after_sha256=kits.render.sha256_bytes(before[i].raw_bitmap),
            status='native-byte-preserved') for i in range(544)]))
    complete = tmp_path / 'original-complete.json'
    kits.pipeline.write_canonical_json(complete, dict(audit_path=str(audit),
        audit_sha256=kits.registry.sha256_file(audit)))
    monkeypatch.setattr(kits.build, '_kit_receipt', lambda *a, **k: complete)
    catalogue = tmp_path / 'catalogue.json'
    kits.pipeline.write_canonical_json(catalogue, dict(rows=[dict(carrier_id=223,
        club_name='Atalanta', render_contract=dict(kind='reviewed-pm99-style', style={}))]))
    original = tmp_path / 'patch/receipt.json'
    kits.pipeline.write_canonical_json(original, dict(outputs={}))
    release = SimpleNamespace(season='2006-07', release_id='old', game_path=game.parent)
    return release, catalogue, tmp_path / 'patch', before, after, audit, original


def test_complete_extension_preserves_original_receipt_and_543_bindings(tmp_path, monkeypatch):
    release, catalogue, patch, _, _, audit, original = complete_fixture(tmp_path, monkeypatch)
    old_receipt = original.read_bytes()
    old_audit = kits.pipeline.read_json_file(audit)
    completed = kits.extend_complete_receipt(release, catalogue, patch, tmp_path / 'out')
    assert original.read_bytes() == old_receipt
    assert completed != patch
    result = kits.pipeline.read_json_file(tmp_path / 'out/complete-kit-audit.json')
    assert all(row == old_audit['records'][i] for i, row in enumerate(result['records']) if i != 223)
    assert result['records'][223]['status'] == 'source-bound-rerendered'
    assert not result['historical_accuracy_certified']


@pytest.mark.parametrize('fault', ['other-carrier', 'carrier-set', 'stale-audit', 'wrong-club'])
def test_complete_extension_rejects_unbounded_or_stale_change(tmp_path, monkeypatch, fault):
    release, catalogue, patch, before, after, audit, _ = complete_fixture(tmp_path, monkeypatch)
    if fault == 'other-carrier':
        after[42].raw_bitmap = b'unrelated-change'
    elif fault == 'carrier-set':
        del after[42]
    elif fault == 'stale-audit':
        before[42].raw_bitmap = b'changed-base'
    else:
        row = kits.pipeline.read_json_file(catalogue)
        row['rows'][0]['club_name'] = 'Palermo'
        kits.pipeline.write_canonical_json(tmp_path / 'wrong-catalogue.json', row)
        catalogue = tmp_path / 'wrong-catalogue.json'
    with pytest.raises(ValueError):
        kits.extend_complete_receipt(release, catalogue, patch, tmp_path / 'out')


def test_v5_without_full_audit_uses_sealed_actual_parent_without_historical_approval(tmp_path, monkeypatch):
    release, catalogue, patch, before, after, audit, original = complete_fixture(tmp_path, monkeypatch)
    old = tmp_path / 'legacy-v5.json'
    kits.pipeline.write_canonical_json(old, {'schema_version': 'pm99-season-kit-runtime-overlay-v1'})
    monkeypatch.setattr(kits.build, '_kit_receipt', lambda *a, **k: old)
    release.inventory_path = tmp_path / 'inventory.json'
    kits.pipeline.write_canonical_json(release.inventory_path, kits.pipeline.build_tree_inventory(release.game_path))
    release.package_path = tmp_path / 'package.json'
    kits.pipeline.write_canonical_json(release.package_path, {'clubs': [{'carrier_id': 223, 'name': 'Atalanta'}]})
    completed = kits.extend_complete_receipt(release, catalogue, patch, tmp_path / 'out')
    result = kits.pipeline.read_json_file(tmp_path / 'out/complete-kit-audit.json')
    assert result['records'][42]['status'] == 'existing-native-historically-unreviewed'
    assert result['records'][223]['status'] == 'source-bound-rerendered'
    assert result['historical_accuracy_certified'] is False
    assert result['prior_audit'] is None
    assert completed.is_dir()


def test_unknown_receipt_without_audit_is_rejected(tmp_path, monkeypatch):
    release, catalogue, patch, *_ = complete_fixture(tmp_path, monkeypatch)
    unknown = tmp_path / 'unknown.json'
    kits.pipeline.write_canonical_json(unknown, {'schema_version': 'unknown'})
    monkeypatch.setattr(kits.build, '_kit_receipt', lambda *a, **k: unknown)
    with pytest.raises(ValueError, match='unsupported kit receipt'):
        kits.extend_complete_receipt(release, catalogue, patch, tmp_path / 'out')


def test_v5_baseline_rejects_parent_changed_since_sealing(tmp_path, monkeypatch):
    release, catalogue, patch, *_ = complete_fixture(tmp_path, monkeypatch)
    legacy = tmp_path / 'legacy-v5.json'
    kits.pipeline.write_canonical_json(legacy, {'schema_version': 'pm99-season-kit-runtime-overlay-v1'})
    monkeypatch.setattr(kits.build, '_kit_receipt', lambda *a, **k: legacy)
    release.inventory_path = tmp_path / 'inventory.json'
    kits.pipeline.write_canonical_json(release.inventory_path, kits.pipeline.build_tree_inventory(release.game_path))
    (release.game_path / 'DBDAT/NANOESC.PKF').write_bytes(b'changed-after-sealing')
    with pytest.raises(kits.pipeline.PipelineError):
        kits.extend_complete_receipt(release, catalogue, patch, tmp_path / 'out')
