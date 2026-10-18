from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts import cascade_compact_kit_v6 as cascade
from scripts import build_registered_quality_release_v1 as build
from scripts import capture_registered_season_runtime_v1 as capture


def test_binding_requires_current_bytes_and_correct_club():
    contract = {'expected': 'old', 'club': 'Stoke City', 'contract': {'kind': 'style'}}
    newer = {**contract, 'expected': 'new'}
    assert cascade.select_contract([contract, newer], 'new', 'Stoke City') == newer
    with pytest.raises(ValueError, match='no existing source'):
        cascade.select_contract([contract], 'new', 'Stoke City')
    with pytest.raises(ValueError, match='does not match'):
        cascade.select_contract([newer], 'new', 'Bayern')
    with pytest.raises(ValueError, match='conflicting'):
        cascade.select_contract([newer, {**newer, 'contract': {'kind': 'different'}}], 'new', 'Stoke City')


def test_all_record_audit_preserves_native_fallbacks_and_does_not_write(tmp_path):
    result = cascade.prepare('2004-05', cascade.OUTPUT / '2004-05', audit_only=True)
    assert result['all_records'] == 544
    assert result['blockers'] == 0
    assert result['status_counts']['native-byte-preserved'] == 452
    assert result['status_counts']['source-bound-rerendered'] == 92
    assert result['runtime_verified'] is False


def test_pixel_contract_rejects_wrapper_and_silhouette_damage():
    template = cascade.renderer._record_index(cascade.BASE / cascade.ARCHIVE)[2]
    palette, _ = cascade.renderer._palette(cascade.BASE)
    payload = cascade.factory.render_record(template, palette,
        {'pattern': 'vertical_stripes', 'colors': ['white', 'red'], 'shorts': 'white'})
    cascade.validate_pixel_patch(template, template, payload)
    corrupt = bytearray(payload)
    corrupt[0] ^= 1
    with pytest.raises(ValueError):
        cascade.validate_pixel_patch(template, template, bytes(corrupt))
    bitmap = cascade.factory.hem_renderer.boundary_renderer.recipe_renderer
    rows = bitmap.record_to_top_down_indices(replace(template, raw_bitmap=payload))
    rows[0][0] = 1 if rows[0][0] == 0 else 0
    with pytest.raises(ValueError, match='silhouette'):
        cascade.validate_pixel_patch(template, template, bitmap.top_down_indices_to_raw(template, rows))


def test_later_database_build_uses_updated_artwork_receipt(tmp_path, monkeypatch):
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    archives = {}
    for name in cascade.renderer.ARCHIVES:
        path = game / 'DBDAT' / name
        path.write_bytes(name.encode())
        archives[name] = {'sha256_after': cascade.visual.sha(path)}
    complete = tmp_path / 'complete.json'
    cascade.visual.save(complete, {'archives': archives})
    materialisation = tmp_path / 'materialisation.json'
    cascade.visual.save(materialisation, {'complete_kit_receipt_path': str(complete),
        'complete_kit_receipt_sha256': cascade.visual.sha(complete)})
    application = tmp_path / 'application.json'
    cascade.visual.save(application, {'materialisation_path': str(materialisation),
        'materialisation_sha256': cascade.visual.sha(materialisation)})
    monkeypatch.setattr(build.registry, 'load_preferred_release', lambda s: SimpleNamespace(
        game_path=game, locator={'kit_patch_application_path': str(application)}))
    assert build._kit_receipt('2004-05') == complete
    explicit = SimpleNamespace(season='2004-05', game_path=game,
        locator={'kit_patch_application_path': str(application)})
    monkeypatch.setattr(build.registry, 'load_preferred_release', lambda s:
        pytest.fail('exact replay must read its explicit ancestor kit receipt, not the current preferred game'))
    assert build._kit_receipt('2004-05', source_release=explicit) == complete
    with pytest.raises(build.QualityBuildError, match='another season'):
        build._kit_receipt('2005-06', source_release=explicit)
    (game / 'DBDAT/NANOESC.PKF').write_bytes(b'stale')
    with pytest.raises(build.QualityBuildError, match='stale'):
        build._kit_receipt('2004-05', source_release=explicit)


def test_compact_capture_is_opt_in(monkeypatch):
    release = SimpleNamespace(release_manifest_path=Path('manifest'), manifest_sha256='abc',
        game_path=Path('/game'), locator={'game_inventory_fingerprint': 'xyz'})
    monkeypatch.setattr(capture.registry, 'load_preferred_release', lambda s: release)
    monkeypatch.setattr(capture.registry, 'validate_preferred_release', lambda *a, **kw: {'valid': True})
    common = dict(season='2004-05', worker='linux-runner', run_tag='test')
    normal, _ = capture.capture_command(**common)
    compact, _ = capture.capture_command(**common, compact_evidence=True)
    assert '--artifact-screen-scope' not in normal
    assert compact[-2:] == ['--artifact-screen-scope', 'lineup']


def test_installed_contracts_require_registered_unchanged_audit_and_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(cascade, 'ROOT', tmp_path)
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    archives = {}
    for name in cascade.renderer.ARCHIVES:
        path = game / 'DBDAT' / name
        path.write_bytes(name.encode())
        archives[name] = {'sha256_after': cascade.visual.sha(path)}
    source = tmp_path / 'source.json'
    cascade.visual.save(source, {'original': 'source contract'})
    records = [{'carrier_id': i, 'status': 'native-byte-preserved'} for i in range(1, 545)]
    records[0] = {'carrier_id': 1, 'status': 'source-bound-rerendered', 'after_sha256': 'installed-bitmap',
        'source': {'receipt': str(source), 'receipt_sha256': cascade.visual.sha(source),
                   'contract': {'kind': 'reviewed-pm99-style'}, 'club': 'Example', 'expected': 'original-bitmap'}}
    audit = tmp_path / 'audit.json'
    cascade.visual.save(audit, {'season': '2004-05', 'all_records': 544, 'blockers': 0, 'records': records})
    complete = tmp_path / 'complete.json'
    cascade.visual.save(complete, {'renderer': cascade.factory.RENDERER_ID, 'archives': archives,
        'audit_path': str(audit), 'audit_sha256': cascade.visual.sha(audit)})
    material = tmp_path / 'material.json'
    cascade.visual.save(material, {'complete_kit_receipt_path': str(complete),
        'complete_kit_receipt_sha256': cascade.visual.sha(complete)})
    application = tmp_path / 'application.json'
    cascade.visual.save(application, {'materialisation_path': str(material),
        'materialisation_sha256': cascade.visual.sha(material)})
    manifest = tmp_path / 'manifest.json'
    cascade.visual.save(manifest, {'external_artifacts': [{'sha256': cascade.visual.sha(application),
        'size': application.stat().st_size}]})
    release = SimpleNamespace(game_path=game, locator={'kit_patch_application_path': 'application.json'},
        release_manifest_path=manifest, manifest_sha256=cascade.visual.sha(manifest))
    monkeypatch.setattr(cascade.registry, 'load_preferred_release', lambda s: release)
    assert cascade.installed_contracts('2004-05')[1][0]['expected'] == 'installed-bitmap'
    legacy = cascade.read(complete)
    legacy['renderer'] = 'pm99-factory-template-kit-v6-scale-aware-patterns'
    complete.write_bytes(cascade.renderer.canonical_json_bytes(legacy))
    material_doc = cascade.read(material)
    material_doc['complete_kit_receipt_sha256'] = cascade.visual.sha(complete)
    material.write_bytes(cascade.renderer.canonical_json_bytes(material_doc))
    application_doc = cascade.read(application)
    application_doc['materialisation_sha256'] = cascade.visual.sha(material)
    application.write_bytes(cascade.renderer.canonical_json_bytes(application_doc))
    manifest.write_bytes(cascade.renderer.canonical_json_bytes({'external_artifacts': [{'sha256':cascade.visual.sha(application), 'size':application.stat().st_size}]}))
    release.manifest_sha256 = cascade.visual.sha(manifest)
    assert cascade.installed_contracts('2004-05')[1][0]['expected'] == 'installed-bitmap'
    original = audit.read_bytes()
    audit.write_bytes(original + b' ')
    with pytest.raises(ValueError, match='audit changed'):
        cascade.installed_contracts('2004-05')
    audit.write_bytes(original)
    source.write_bytes(source.read_bytes() + b' ')
    with pytest.raises(ValueError, match='source receipt changed'):
        cascade.installed_contracts('2004-05')
