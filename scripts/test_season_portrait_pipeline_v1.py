from __future__ import annotations

from scripts.season_portrait_pipeline_v1 import _name_score
from scripts.season_portrait_pipeline_v1 import _copy_game_cow, PortraitPipelineError
import pytest


def test_parallel_same_url_reuses_one_immutable_cache_receipt(tmp_path, monkeypatch):
    import io
    import time
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace
    from PIL import Image
    from scripts import season_portrait_pipeline_v1 as portraits
    stream = io.BytesIO()
    Image.new('RGB', (120, 120), 'red').save(stream, format='PNG')
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        time.sleep(.03)
        return SimpleNamespace(status_code=200, content=stream.getvalue())
    monkeypatch.setattr(portraits.requests, 'get', get)
    row = {'status': 'era-source-candidate', 'source_image_url': 'https://example.test/16.png'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: portraits._fetch(row, cache_root=tmp_path, timeout=1), range(4)))
    assert len(calls) == 1
    assert {r['source_sha256'] for r in results} == {portraits._sha_bytes(stream.getvalue())}
    assert sum(r['fetch_status'] == 'cache-hit' for r in results) == 3


def test_missing_payload_recovery_preserves_receipt_and_rejects_source_drift(tmp_path, monkeypatch):
    import io
    from types import SimpleNamespace
    from PIL import Image
    from scripts import season_portrait_pipeline_v1 as portraits
    stream = io.BytesIO()
    Image.new('RGB', (120, 120), 'red').save(stream, format='PNG')
    monkeypatch.setattr(portraits.requests, 'get', lambda *args, **kwargs:
                        SimpleNamespace(status_code=200, content=stream.getvalue()))
    row = {'status': 'era-source-candidate', 'source_image_url': 'https://example.test/16.png'}
    portraits._fetch(row, cache_root=tmp_path, timeout=1)
    meta, payload = portraits._cache_paths(tmp_path, row['source_image_url'])
    original_receipt = meta.read_bytes()
    payload.unlink()
    assert portraits._fetch(row, cache_root=tmp_path, timeout=1)['fetch_status'] == 'recovered-hash-matching-payload'
    assert meta.read_bytes() == original_receipt
    payload.unlink()
    stream = io.BytesIO()
    Image.new('RGB', (120, 120), 'blue').save(stream, format='PNG')
    result = portraits._fetch(row, cache_root=tmp_path, timeout=1)
    assert result['status'] == 'native-no-photo'
    assert result['reason'] == 'recovered-source-does-not-match-retained-cache-receipt'
    assert meta.read_bytes() == original_receipt
    assert not payload.exists()


def test_name_score_accepts_accented_long_name_for_era_identity() -> None:
    score, method = _name_score("Bojan Krkic", "Bojan", "Bojan Krkíc Pérez")
    assert score >= 85
    assert method == "target-name-tokens-contained-in-long-name"


def test_non_decomposing_letters_and_given_alias_are_preserved():
    assert _name_score('Lukasz Fabianski', 'Łukasz Fabiański', 'Łukasz Fabiański')[0] == 100
    assert _name_score('Robert Elliot', 'Rob Elliot', 'Rob Elliot')[0] >= 85
    assert _name_score('Robert Elliot', 'Rob Green', 'Rob Green')[0] == 0


def test_name_score_rejects_same_first_name_only() -> None:
    score, method = _name_score("Bojan Krkic", "Bojan", "Bojan Jokič")
    assert score == 0
    assert method == "name-mismatch"


def test_name_score_handles_apostrophe_and_given_name_aliases() -> None:
    assert _name_score("Steven N'Zonzi", "S. N'Zonzi", "Steven N'Kemboanza Mike Christopher Nzonzi")[0] >= 85
    assert _name_score("Phillip Bardsley", "P. Bardsley", "Phil Bardsley") == (95, "normalised-given-name-alias")


def test_game_copy_does_not_share_mutable_files(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    (source / "manager.ini").write_bytes(b"original")
    _copy_game_cow(source, target)
    assert (source / "manager.ini").stat().st_ino != (target / "manager.ini").stat().st_ino
    (target / "manager.ini").write_bytes(b"changed")
    assert (source / "manager.ini").read_bytes() == b"original"


def test_game_copy_refuses_existing_target(tmp_path):
    with pytest.raises(PortraitPipelineError, match="already exists"):
        _copy_game_cow(tmp_path, tmp_path)


def test_game_copy_checks_fallback_space_before_copy(tmp_path, monkeypatch):
    from scripts import season_portrait_pipeline_v1 as module
    from collections import namedtuple
    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(module.shutil, "disk_usage", lambda _: usage(10, 9, 1))
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(PortraitPipelineError, match="1 GiB"):
        _copy_game_cow(source, tmp_path / "target")
    assert not (tmp_path / "target").exists()
