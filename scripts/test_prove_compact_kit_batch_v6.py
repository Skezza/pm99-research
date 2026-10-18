from types import SimpleNamespace
import pytest
from scripts import prove_compact_kit_batch_v6 as batch


def test_old_runtime_proof_cannot_be_reused_as_v6_kit_evidence(tmp_path, monkeypatch):
    receipt = tmp_path / 'old.json'
    batch.visual.save(receipt, {'renderer': 'pm99-factory-template-kit-v5-native-tone-transfer'})
    monkeypatch.setattr(batch.registry, 'load_preferred_release', lambda s: SimpleNamespace())
    monkeypatch.setattr(batch.builder, '_kit_receipt', lambda s: receipt)
    with pytest.raises(ValueError, match='not installed'):
        batch.require_installed_v6('2004-05')


def test_complete_hash_bound_audit_is_required(tmp_path, monkeypatch):
    audit = tmp_path / 'audit.json'
    batch.visual.save(audit, {'blockers': 0, 'all_records': 544})
    receipt = tmp_path / 'receipt.json'
    batch.visual.save(receipt, {'renderer': batch.factory.RENDERER_ID, 'audit_path': str(audit),
                               'audit_sha256': batch.visual.sha(audit)})
    release = SimpleNamespace(release_id='new')
    monkeypatch.setattr(batch.registry, 'load_preferred_release', lambda s: release)
    monkeypatch.setattr(batch.builder, '_kit_receipt', lambda s: receipt)
    assert batch.require_installed_v6('2004-05') is release
    audit.write_text('{"blockers":1,"all_records":544}')
    with pytest.raises(ValueError, match='audit changed'):
        batch.require_installed_v6('2004-05')
