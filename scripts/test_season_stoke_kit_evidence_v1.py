from scripts.season_stoke_kit_evidence_v1 import HFK_PAGE, HFK_ATTRIBUTION, build_matrix, capture_url, parse_hfk_entries


HFK = b'''<title>Stoke City - Historical Football Kits</title><div class="float"><div class="manufacturer"><!-- x -->Asics<!-- y --></div><img src="/Stoke_City/images/stoke_city_1999-2023.gif"><span class="date"><!-- x -->1999-2023<!-- y --></span><!-- InstanceEndRepeat -->'''


def test_content_addressed_cache_skips_second_fetch(tmp_path) -> None:
    calls = []
    first = capture_url("https://example.test/evidence", tmp_path, allow_network=True, fetcher=lambda url: calls.append(url) or b"source")
    second = capture_url("https://example.test/evidence", tmp_path, allow_network=False)
    assert first == second
    assert calls == ["https://example.test/evidence"]


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
