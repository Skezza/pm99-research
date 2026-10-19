import json
from pathlib import Path

import pytest

from scripts.season_stoke_kit_evidence_v1 import HFK_PAGE, HFK_ATTRIBUTION, build_matrix, capture_url, parse_hfk_entries
from scripts.season_stoke_kit_evidence_v1 import StokeKitEvidenceError, canonical_json_bytes, sha256_bytes


HFK = b'''<title>Stoke City - Historical Football Kits</title><div class="float"><div class="manufacturer"><!-- x -->Asics<!-- y --></div><img src="/Stoke_City/images/stoke_city_1999-2023.gif"><span class="date"><!-- x -->1999-2023<!-- y --></span><!-- InstanceEndRepeat -->'''


def test_content_addressed_cache_skips_second_fetch(tmp_path) -> None:
    calls = []
    first = capture_url("https://example.test/evidence", tmp_path, allow_network=True, fetcher=lambda url: calls.append(url) or b"source")
    second = capture_url("https://example.test/evidence", tmp_path, allow_network=False)
    assert first == second
    assert calls == ["https://example.test/evidence"]


@pytest.mark.parametrize('payload', [b'', b' \n\t', None, 'not bytes'])
def test_empty_response_writes_no_cache_blob_or_index(tmp_path, payload) -> None:
    url = "https://example.test/empty"
    try:
        capture_url(url, tmp_path, allow_network=True, fetcher=lambda _: payload)
    except StokeKitEvidenceError as exc:
        assert "empty source response" in str(exc)
    else:
        raise AssertionError("empty HTTP response must be rejected")
    assert not (tmp_path / "blobs").exists()
    assert not (tmp_path / "url-index").exists()


def _seed_empty_cache(tmp_path: Path, url: str) -> tuple[Path, Path]:
    index_path = tmp_path / "url-index" / f"{sha256_bytes(url.encode('utf-8'))}.json"
    blob_path = tmp_path / "blobs" / "e3" / sha256_bytes(b"")
    blob_path.parent.mkdir(parents=True)
    blob_path.write_bytes(b"")
    index_path.parent.mkdir(parents=True)
    index_path.write_bytes(canonical_json_bytes({
        "url": url,
        "sha256": sha256_bytes(b""),
        "byte_count": 0,
        "relative_path": str(blob_path.relative_to(tmp_path)),
    }))
    return index_path, blob_path


def test_existing_empty_cache_is_offline_miss(tmp_path) -> None:
    url = "https://example.test/poisoned-offline"
    index_path, blob_path = _seed_empty_cache(tmp_path, url)
    try:
        capture_url(url, tmp_path, allow_network=False)
    except StokeKitEvidenceError as exc:
        assert "cache miss with network disabled" in str(exc)
    else:
        raise AssertionError("empty cached payload must not be accepted offline")
    assert index_path.is_file()
    assert blob_path.read_bytes() == b""


def test_existing_empty_cache_retries_online_without_deleting_old_blob(tmp_path) -> None:
    url = "https://example.test/poisoned-online"
    index_path, empty_blob_path = _seed_empty_cache(tmp_path, url)
    fresh = b"fresh reviewed evidence"
    calls = []
    receipt = capture_url(url, tmp_path, allow_network=True, fetcher=lambda value: calls.append(value) or fresh)
    assert calls == [url]
    assert receipt["sha256"] == sha256_bytes(fresh)
    assert receipt["byte_count"] == len(fresh)
    fresh_blob_path = tmp_path / receipt["relative_path"]
    assert fresh_blob_path.read_bytes() == fresh
    assert empty_blob_path.exists() and empty_blob_path.read_bytes() == b""
    assert index_path.is_file()
    assert json.loads(index_path.read_text(encoding="utf-8")) == receipt


def test_hfk_parser_requires_exact_stoke_identity() -> None:
    assert parse_hfk_entries(HFK)[0]["date_label"] == "1999-2023"


def test_full_matrix_has_25_exact_rows_and_credit(tmp_path) -> None:
    def fetch(url: str) -> bytes:
        if url == HFK_PAGE:
            # One unambiguous range deliberately covers the historical lane.
            return HFK
        if "images/" in url:
            return b"GIF89a reviewed factual evidence"
        match = next(value for value in ("2023–24", "2024–25", "2025–26") if value.replace("–", "%E2%80%93") in url)
        return f'''<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/"><page><title>{match} Stoke City F.C. season</title><revision><id>123</id><timestamp>2026-01-01T00:00:00Z</timestamp><text>\n| pattern_la1 = _stokeh\n| pattern_b1 = _stokeh\n| pattern_ra1 = _stokeh\n| leftarm1 = FFFFFF\n| body1 = FFFFFF\n| rightarm1 = FFFFFF\n| shorts1 = FFFFFF\n| socks1 = FFFFFF\n</text></revision></page></mediawiki>'''.encode()

    matrix = build_matrix(tmp_path, allow_network=True, fetcher=fetch)
    assert matrix["coverage"] == {"target_seasons": 25, "source_ready": 25, "gaps": 0}
    assert matrix["rows"][0]["source"]["attribution"] == HFK_ATTRIBUTION
    assert sum(row["render_contract"]["kind"] == "reviewed-pm99-style" for row in matrix["rows"]) == 22
    assert sum(row["render_contract"]["kind"] == "wikipedia-template-fields" for row in matrix["rows"]) == 3
