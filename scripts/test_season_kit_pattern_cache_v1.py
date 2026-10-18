from scripts.season_kit_pattern_cache_v1 import requested_layers


def test_requested_layers_are_exact_nonempty_source_ready_tokens() -> None:
    document = {
        "rows": [
            {"status": "source-ready", "render_contract": {"kind": "wikipedia-template-fields", "fields": {"pattern_b1": "_body", "pattern_la1": "", "pattern_ra1": "_arm"}}},
            {"status": "blocked-missing-home-kit-fields", "render_contract": {"kind": "wikipedia-template-fields", "fields": {"pattern_b1": "_blocked"}}},
        ]
    }
    assert requested_layers(document) == {("body", "body"), ("right_arm", "arm")}
