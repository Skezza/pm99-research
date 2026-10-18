import json
from pathlib import Path
import shutil

import pytest
from scripts import compact_crash04_database_copies_v1 as cleanup


def setup(tmp_path, monkeypatch):
    controls = tmp_path / '.local/crash04-diagnostics-v1'
    base = tmp_path / '.local/base/DBDAT'
    output = tmp_path / '.local/deltas'
    for name, value in [('ROOT', tmp_path), ('CONTROLS', controls), ('BASE', base), ('OUTPUT', output)]:
        monkeypatch.setattr(cleanup, name, value)
    # recover's default is bound at definition time; patch through a wrapper.
    original = cleanup.recover
    monkeypatch.setattr(cleanup, 'recover', lambda row: original(row, output=output))
    monkeypatch.setattr(cleanup.registry, 'supported_seasons', lambda: [])
    base.mkdir(parents=True)
    (base / 'JUG98030.FDI').write_bytes(b'original-base-player-data')
    directory = controls / 'failed-control/DBDAT'
    directory.mkdir(parents=True)
    (directory / 'diagnostic.json').write_text('{"diagnostic_only":true}')
    source = directory / 'JUG98030.FDI'
    source.write_bytes(b'changed-control-player-data-with-extra-tail')
    protected = controls / 'identity-repair/DBDAT'
    protected.mkdir(parents=True)
    (protected / 'JUG98030.FDI').write_bytes(b'keep-successful-control')
    return source, output, base, protected


def test_exact_recovery_before_removing_only_the_obsolete_copy(tmp_path, monkeypatch):
    source, output, base, protected = setup(tmp_path, monkeypatch)
    target = source.read_bytes()
    result = cleanup.compact(execute=True)
    assert result['files_verified'] == 1
    assert not source.exists()
    assert (source.parent / 'diagnostic.json').exists()
    assert (protected / 'JUG98030.FDI').read_bytes() == b'keep-successful-control'
    receipt = json.loads((output / 'receipt.json').read_text())
    assert cleanup.recover(receipt['rows'][0]) == target
    (base / 'JUG98030.FDI').write_bytes(b'base changed')
    with pytest.raises(ValueError, match='input changed'):
        cleanup.compact(False)


def test_verified_pi_copy_can_supply_reconstruction_after_local_delta_removal(tmp_path, monkeypatch):
    source, output, _, _ = setup(tmp_path, monkeypatch)
    original = source.read_bytes()
    cleanup.compact(True)
    remote = tmp_path / 'mounted-pi'
    shutil.copytree(output, remote)
    cleanup.archive_deltas(remote, 'smb://test/HDD/verified-deltas')
    assert list((output / 'files').iterdir()) == []
    receipt = json.loads((output / 'receipt.json').read_text())
    assert cleanup.recover(receipt['rows'][0]) == original


def test_corrupt_pi_backup_prevents_local_delta_deletion(tmp_path, monkeypatch):
    _, output, _, _ = setup(tmp_path, monkeypatch)
    cleanup.compact(True)
    remote = tmp_path / 'mounted-pi'
    shutil.copytree(output, remote)
    next((remote / 'files').iterdir()).write_bytes(b'corrupt backup')
    with pytest.raises(ValueError, match='readback hash mismatch'):
        cleanup.archive_deltas(remote, 'smb://test/HDD')
    assert len(list((output / 'files').iterdir())) == 1
