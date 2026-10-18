from scripts import promote_post1999_worldwide_v1 as promotion


def test_kit_archive_stage_uses_documented_durable_pattern_cache():
    assert promotion.PATTERN_CACHE == promotion.LOCAL / "source-cache" / "wikimedia-kit-patterns-v1"


def test_kit_archive_stage_requires_and_passes_durable_pattern_cache(monkeypatch, tmp_path):
    local = tmp_path / ".local"
    pattern_cache = local / "source-cache" / "wikimedia-kit-patterns-v1"
    monkeypatch.setattr(promotion, "LOCAL", local)
    monkeypatch.setattr(promotion, "PATTERN_CACHE", pattern_cache)

    required = []
    commands = []

    def fake_require(paths):
        required.extend(paths)

    def fake_run(command, *, terminal):
        commands.append(command)
        return {"status": "built", "terminal": str(terminal)}

    monkeypatch.setattr(promotion, "_require", fake_require)
    monkeypatch.setattr(promotion, "_run", fake_run)

    promotion.promote(
        "2000-01", revision="unit", kit_revision=None,
        through="kit-archives", allow_network=False,
    )

    assert pattern_cache / "pattern-index" in required
    assert pattern_cache / "patterns" in required
    render_command = next(
        command for command in commands
        if command[1] == "scripts/season_kit_render_bindings_v1.py"
    )
    cache_index = render_command.index("--pattern-cache-dir")
    assert render_command[cache_index + 1] == str(pattern_cache)
