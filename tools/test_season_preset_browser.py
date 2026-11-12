from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from tools.season_preset_browser import (
    PresetCatalog,
    _structured_summary,
    discover_presets,
    discover_runtime_recipe_presets,
)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _empty_indexes(tmp_path: Path) -> dict[str, Path]:
    return {
        "baseline_index": tmp_path / "missing-baseline.json",
        "manager_overlay_index": tmp_path / "missing-manager-index.json",
        "overlays_root": tmp_path / "missing-overlays",
    }


def test_discovers_season_presets_without_raw_sources(tmp_path: Path) -> None:
    _write(tmp_path / "2000-01" / "fixed-carrier-ledger.json", {"schema_version": "ledger-v1", "ledger_id": "test-ledger"})
    (tmp_path / "2000-01" / "README.md").write_text("# Season\n", encoding="utf-8")
    _write(tmp_path / "2000-01" / "sources" / "squad.json", {"source": "raw"})
    _write(tmp_path / "editorial" / "ignored.json", {"not": "a season"})

    discovered = discover_presets(tmp_path)

    assert list(discovered) == ["2000-01"]
    assert [item.relative_path for item in discovered["2000-01"]] == ["README.md", "fixed-carrier-ledger.json"]
    assert discovered["2000-01"][1].title == "test-ledger"


def test_optional_source_capture_and_catalog_allowlist(tmp_path: Path, monkeypatch) -> None:
    # A developer's proprietary local backup must not leak into this fixture.
    monkeypatch.setattr("tools.season_preset_browser.discover_legacy_2015_presets", lambda: [])
    _write(tmp_path / "2015-16" / "workspace.json", {"schema_version": "workspace-v1", "workspace_id": "world-2015"})
    _write(tmp_path / "2015-16" / "sources" / "squad.json", {"source": "dated"})
    catalog = PresetCatalog(tmp_path, include_source_captures=True, **_empty_indexes(tmp_path))

    index = catalog.index()
    assert index["read_only"] is True
    assert index["season_count"] == 1
    assert [row["relative_path"] for row in index["seasons"][0]["presets"]] == [
        "overview/season-assembly-map.json", "sources/squad.json", "workspace.json"
    ]
    document = catalog.read("2015-16", "workspace.json")
    assert document["content_type"] == "json"
    assert '"workspace_id": "world-2015"' in document["content"]
    with pytest.raises(KeyError):
        catalog.read("2015-16", "../../outside.json")


def test_catalog_includes_local_playtest_manifest_for_its_target_season(tmp_path: Path) -> None:
    seasons_root = tmp_path / "seasons"
    playtests_root = tmp_path / "playtests"
    _write(seasons_root / "2000-01" / "source-intake.json", {"schema_version": "intake-v1"})
    _write(
        playtests_root / "pm99-2000-01-calendar-playtest-r1" / "provisional-playtest-manifest.json",
        {
            "schema_version": "pm99-provisional-playtest-calendar-variant-v1",
            "target_season": "2000-01",
            "variant_id": "pm99-2000-01-calendar-playtest-r1",
        },
    )

    catalog = PresetCatalog(
        seasons_root,
        include_source_captures=False,
        playtests_root=playtests_root,
        **_empty_indexes(tmp_path),
    )

    rows = catalog.index()["seasons"][0]["presets"]
    playtest = next(row for row in rows if row["kind"] == "playtest")
    assert playtest["title"] == "pm99-2000-01-calendar-playtest-r1"
    assert playtest["relative_path"].startswith("local-playtest/")
    document = catalog.read("2000-01", playtest["id"])
    assert document["content_type"] == "json"
    assert '"target_season": "2000-01"' in document["content"]


def test_catalog_discovers_generated_authoring_manifests_without_uploads(tmp_path: Path) -> None:
    seasons_root = tmp_path / "seasons"
    authoring_root = tmp_path / "authoring"
    _write(seasons_root / "2000-01" / "workspace.json", {"schema_version": "workspace-v1"})
    source_path = authoring_root / "2000-01" / "revisions" / "rev-example" / "draft-season-package.json"
    _write(source_path, {"schema_version": "pm99-season-package-v2", "package_id": "pm99-2000-01-draft"})
    _write(
        authoring_root / "2000-01" / "current.json",
        {
            "schema_version": "pm99-historical-squad-backfill-current-v1",
            "revision_id": "rev-example",
            "artifacts": {
                "source": {
                    "path": "revisions/rev-example/draft-season-package.json",
                    "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
                }
            },
        },
    )

    catalog = PresetCatalog(
        seasons_root,
        include_source_captures=False,
        authoring_root=authoring_root,
        **_empty_indexes(tmp_path),
    )

    rows = catalog.index()["seasons"][0]["presets"]
    generated = next(row for row in rows if row["kind"] == "authoring-input")
    assert generated["relative_path"] == "authoring/revisions/rev-example/draft-season-package.json"
    document = catalog.read("2000-01", generated["id"])
    assert '"package_id": "pm99-2000-01-draft"' in document["content"]
    assert document["summary"]["title"] == "Club, manager and opening-lineup overview"


def test_structured_summary_exposes_current_revision_and_cross_season_coverage() -> None:
    current = _structured_summary({
        "schema_version": "pm99-historical-squad-backfill-current-v1",
        "revision_id": "rev-example",
        "artifacts": {"source": {"path": "revisions/rev-example/source.json", "sha256": "a" * 64}},
    })
    assert current is not None
    assert current["counts"]["revision"] == "rev-example"
    assert current["rows"][0]["artifact"] == "source"

    matrix = _structured_summary({
        "schema_version": "pm99-historical-squad-current-coverage-matrix-v1",
        "seasons": [{"season": "2000-01", "assigned_real_carrier_count": 400,
                     "unassigned_real_carrier_count": 46}],
    })
    assert matrix is not None
    assert matrix["columns"] == [
        "season", "assigned_real_carrier_count", "unassigned_real_carrier_count"
    ]


def test_structured_summary_exposes_a_read_only_season_assembly_map() -> None:
    overview = _structured_summary({
        "schema_version": "pm99-local-season-assembly-map-v1",
        "state": {"playable": False, "release_status": "not released"},
        "components": [{
            "role": "Frozen base", "kind": "frozen-base", "relative_path": "assembly/base.json", "sha256": "a" * 64,
        }],
    })
    assert overview is not None
    assert overview["counts"]["playable"] is False
    assert overview["rows"][0]["manifest"] == "assembly/base.json"


def test_catalog_stages_and_materialises_a_hash_bound_source_copy(tmp_path: Path) -> None:
    seasons_root = tmp_path / "seasons"
    source_path = seasons_root / "2000-01" / "source.json"
    source = {"clubs": [{"name": "Wrong name"}]}
    _write(source_path, source)
    catalog = PresetCatalog(
        seasons_root,
        include_source_captures=False,
        amendment_output_root=tmp_path / "materialised",
        **_empty_indexes(tmp_path),
    )
    catalog.index()
    staged = catalog.stage_amendment(
        season="2000-01",
        manifest_id="source.json",
        json_pointer="/clubs/0/name",
        replacement="Correct name",
        reason="Opening-season source confirms the club name.",
        evidence="https://example.test/source",
    )
    assert staged["changes"][0]["expected"] == "Wrong name"
    assert json.loads(source_path.read_text(encoding="utf-8")) == source

    receipt = catalog.materialise_amendments(season="2000-01")
    output = Path(receipt["outputs"][0]["output_path"])
    assert json.loads(output.read_text(encoding="utf-8"))["clubs"][0]["name"] == "Correct name"
    assert receipt["state"] == "materialised-source-copies-not-promoted"


def _package() -> dict[str, object]:
    return {
        "schema_version": "pm99-season-package-v2",
        "package_id": "world-2000-01-test",
        "players": [{
            "id": "player-1", "name": "Ada Player", "club_id": "club-1", "carrier_family": "dd6361",
            "facts": {
                "fine_roles": [9], "birth_date": "1980-01-02", "nationality": "ENG", "primary_position": "M",
                "shirt_number": 8, "height_cm": 170, "weight_kg": 60,
            },
            "ratings": {"values": {"handling": 5, "speed": 70}},
        }],
        "managers": [{"id": "manager-1", "name": "Ada Manager", "carrier_id": 10, "policy": "write",
                      "native_names": {"display_name": "Manager", "surname": "Manager"}}],
        "clubs": [{
            "id": "club-1", "name": "Ada Town", "full_name": "Ada Town FC", "division": "Division One",
            "ground_name": "Ada Ground", "manager_id": "manager-1", "carrier_id": 10,
        }],
    }


def test_spreadsheet_model_is_year_first_and_stages_a_cell_more_than_once(tmp_path: Path) -> None:
    seasons_root = tmp_path / "seasons"
    _write(seasons_root / "2000-01" / "season-package.json", _package())
    catalog = PresetCatalog(
        seasons_root,
        include_source_captures=False,
        amendment_output_root=tmp_path / "materialised",
        **_empty_indexes(tmp_path),
    )

    assert catalog.index()["seasons"][0]["spreadsheet_ready"] is True
    metadata = catalog.spreadsheet_metadata("2000-01")
    assert [tab["id"] for tab in metadata["workbook"]["tabs"]] == ["players", "managers", "clubs", "kits"]
    assert metadata["workbook"]["choices"]["nationality"][0]["value"]
    players = catalog.spreadsheet_tab(
        season="2000-01", tab="players", query="Ada", offset=0, limit=20,
    )["table"]
    assert players["rows"][0]["cells"]["name"]["pointer"] == "/players/0/name"
    assert players["rows"][0]["cells"]["portrait"]["display"] == "No verified portrait"
    assert players["rows"][0]["cells"]["rating:handling"]["maximum"] == 100
    clubs = catalog.spreadsheet_tab(
        season="2000-01", tab="clubs", query="", offset=0, limit=20,
    )["table"]
    assert clubs["rows"][0]["cells"]["manager"]["kind"] == "select"

    catalog.stage_amendment(
        season="2000-01", manifest_id="season-package.json", json_pointer="/players/0/name",
        replacement="Ada Correct", reason="Correct source spelling", evidence=None,
    )
    amended = catalog.stage_amendment(
        season="2000-01", manifest_id="season-package.json", json_pointer="/players/0/name",
        replacement="Ada Final", reason="Correct source spelling", evidence=None,
    )
    assert len(amended["changes"]) == 1
    assert amended["changes"][0]["expected"] == "Ada Player"
    assert amended["changes"][0]["set"] == "Ada Final"
    # The workbook previews a copy with staged, hash-bound changes applied;
    # the selected source remains immutable until explicit materialisation.
    preview = catalog.spreadsheet_tab(
        season="2000-01", tab="players", query="", offset=0, limit=20,
    )["table"]
    assert preview["rows"][0]["cells"]["name"]["value"] == "Ada Final"
    assert json.loads((seasons_root / "2000-01" / "season-package.json").read_text(encoding="utf-8"))[
        "players"
    ][0]["name"] == "Ada Player"


def test_runtime_recipe_discovery_requires_the_matching_local_game_tree(tmp_path: Path) -> None:
    ingress = tmp_path / "ingress"
    runtime = tmp_path / "runtime"
    _write(
        ingress / "2000-01-worldwide-source-backed-r1" / "season-package.source-writable.json",
        _package(),
    )
    (runtime / "2000-01" / "worldwide-source-backed-r1" / "game").mkdir(parents=True)

    discovered, states = discover_runtime_recipe_presets(ingress, runtime)

    assert discovered["2000-01"][0].kind == "runtime-recipe"
    assert states["2000-01"]["playable"] is True


def test_registered_recipe_wins_over_stale_ingress_and_rejects_ambiguity(tmp_path):
    from tools.season_preset_browser import Preset
    current = tmp_path / "current.json"
    stale = tmp_path / "stale.json"
    _write(current, {"schema_version": "pm99-season-package-v2", "players": [{"name": "New Player"}]})
    _write(stale, {"schema_version": "pm99-season-package-v2", "players": [{"name": "Old Player"}]})
    def row(path, kind):
        return Preset("2000-01", kind + "/recipe.json", kind, kind, kind,
                      "pm99-season-package-v2", path.stat().st_size,
                      hashlib.sha256(path.read_bytes()).hexdigest(), path)
    catalog = object.__new__(PresetCatalog)
    catalog.entries = {"2000-01": [row(stale, "runtime-recipe"), row(current, "preferred-release-recipe")]}
    selected = catalog._spreadsheet_preset("2000-01")
    assert json.loads(selected.path.read_text())["players"][0]["name"] == "New Player"
    catalog.entries["2000-01"].append(row(stale, "preferred-release-recipe"))
    with pytest.raises(ValueError, match="ambiguous"):
        catalog._spreadsheet_preset("2000-01")


def test_current_recipe_discovery_checks_manifest_binding(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from tools import season_preset_browser as browser
    package = tmp_path / 'registered.json'
    _write(package, {'schema_version': 'pm99-season-package-v2', 'players': []})
    release = SimpleNamespace(release_id='test-release', package_path=package, manifest_sha256='a' * 64)
    monkeypatch.setattr(browser, 'ROOT', tmp_path)
    monkeypatch.setattr(browser.release_registry, 'load_catalog', lambda _: {
        '2000-01': {'release_id': 'test-release', 'release_manifest_sha256': 'a' * 64}})
    monkeypatch.setattr(browser.release_registry, 'load_registered_release', lambda *args: release)
    rows = browser.discover_preferred_release_recipe_presets(tmp_path / 'catalog.json')
    assert rows['2000-01'][0].path == package
    assert rows['2000-01'][0].sha256 == hashlib.sha256(package.read_bytes()).hexdigest()
    release.manifest_sha256 = 'b' * 64
    with pytest.raises(ValueError, match='manifest'):
        browser.discover_preferred_release_recipe_presets(tmp_path / 'catalog.json')


# --- edit -> build -> play bridge -------------------------------------------------

def _build_bound_catalog(tmp_path, monkeypatch, *, builder=None, candidate_packages=None):
    """A workbook over a fake registered release (the real registry is never touched)."""
    from types import SimpleNamespace
    from tools import season_preset_browser as browser
    monkeypatch.setattr(browser, "ROOT", tmp_path)
    packages = {"base-release": tmp_path / "base.json"}
    _write(packages["base-release"], _package())
    for name, package in (candidate_packages or {}).items():
        packages[name] = tmp_path / f"{name}.json"
        _write(packages[name], package)
    monkeypatch.setattr(browser.release_registry, "load_catalog", lambda _=None: {
        "2000-01": {"release_id": "base-release", "release_manifest_sha256": "a" * 64}})
    monkeypatch.setattr(browser.release_registry, "load_registered_release", lambda season, release_id=None, *a: SimpleNamespace(
        release_id=release_id or "base-release", package_path=packages[release_id or "base-release"], manifest_sha256="a" * 64))
    seasons_root = tmp_path / "seasons"
    (seasons_root / "2000-01").mkdir(parents=True)
    catalog = PresetCatalog(
        seasons_root, include_source_captures=False, amendment_output_root=tmp_path / "materialised",
        preferred_catalog_path=tmp_path / "catalog.json", amendment_builder=builder,
        candidates_root=tmp_path / "builds", **_empty_indexes(tmp_path))
    return catalog, browser


def test_build_bound_recipe_refuses_cells_the_game_cannot_take(tmp_path, monkeypatch):
    from tools.season_manifest_amendments import AmendmentError
    catalog, _ = _build_bound_catalog(tmp_path, monkeypatch)
    manifest = "preferred-release/base-release/season-package.json"
    # Supported: rating, broad position, manager name.
    for pointer, value in (("/players/0/ratings/values/speed", 71), ("/players/0/facts/primary_position", "F"),
                           ("/managers/0/name", "Ada Newname")):
        catalog.stage_amendment(season="2000-01", manifest_id=manifest, json_pointer=pointer, replacement=value, reason="edit", evidence=None)
    # Unsupported edits are rejected up front with a reason, not saved as if they reached the game.
    for pointer, fragment in (("/players/0/name", "name"), ("/clubs/0/manager_id", "relational"), ("/clubs/0/name", "club label")):
        with pytest.raises(AmendmentError, match=fragment):
            catalog.stage_amendment(season="2000-01", manifest_id=manifest, json_pointer=pointer, replacement="x", reason="edit", evidence=None)
    assert len(catalog.amendments("2000-01")["changes"]) == 3
    players = catalog.spreadsheet_tab(season="2000-01", tab="players", query="", offset=0, limit=10)["table"]["rows"][0]["cells"]
    assert players["name"]["editable"] is False and "name" in players["name"]["build_note"]
    assert players["rating:speed"]["editable"] is True and "build_note" not in players["rating:speed"]
    clubs = catalog.spreadsheet_tab(season="2000-01", tab="clubs", query="", offset=0, limit=10)["table"]["rows"][0]["cells"]
    assert clubs["manager"]["editable"] is False and clubs["name"]["editable"] is False
    managers = catalog.spreadsheet_tab(season="2000-01", tab="managers", query="", offset=0, limit=10)["table"]["rows"][0]["cells"]
    assert managers["name"]["editable"] is True


def test_non_release_presets_keep_free_form_staging(tmp_path):
    # Source manifests that do not feed the build route are unchanged: any existing field may be staged.
    seasons_root = tmp_path / "seasons"
    _write(seasons_root / "2000-01" / "season-package.json", _package())
    catalog = PresetCatalog(seasons_root, include_source_captures=False, amendment_output_root=tmp_path / "m", **_empty_indexes(tmp_path))
    catalog.index()
    catalog.stage_amendment(season="2000-01", manifest_id="season-package.json", json_pointer="/clubs/0/name", replacement="Ada City", reason="r", evidence=None)
    tab = catalog.spreadsheet_tab(season="2000-01", tab="players", query="", offset=0, limit=5)["table"]
    assert tab["rows"][0]["cells"]["name"]["editable"] is True


def _http(server_catalog, method, path, body=None):
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer
    from tools.season_preset_browser import make_handler
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(server_catalog))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())
    finally:
        server.shutdown()
        server.server_close()


def test_build_endpoints_run_the_builder_over_the_staged_document(tmp_path, monkeypatch):
    calls = []

    def builder(season, **kwargs):
        calls.append((season, kwargs))
        return {"status": "planned" if kwargs["dry_run"] else "built", "candidate_release_id": "edited-2000-01-abc",
                "summary": [], "ignored_changes": [], "parent_release_id": "base-release"}

    catalog, _ = _build_bound_catalog(tmp_path, monkeypatch, builder=builder)
    manifest = "preferred-release/base-release/season-package.json"
    # Nothing staged yet: refused before any build is attempted.
    status, body = _http(catalog, "POST", "/api/amendments/build", {"season": "2000-01"})
    assert status == 409 and "stage at least one" in body["error"] and calls == []
    catalog.stage_amendment(season="2000-01", manifest_id=manifest, json_pointer="/players/0/ratings/values/speed",
                            replacement=71, reason="edit", evidence=None)
    status, body = _http(catalog, "POST", "/api/amendments/check", {"season": "2000-01"})
    assert status == 200 and body["report"]["status"] == "planned"
    status, body = _http(catalog, "POST", "/api/amendments/build", {"season": "2000-01"})
    assert status == 200 and body["report"]["status"] == "built" and body["base"]["release_id"] == "base-release"
    assert [(c[1]["dry_run"], c[1]["parent_id"], c[1]["origin"]) for c in calls] == [
        (True, None, "workbook-staged-working-json"), (False, None, "workbook-staged-working-json")]
    assert calls[1][1]["document"]["changes"][0]["json_pointer"] == "/players/0/ratings/values/speed"


def test_build_errors_reach_the_page_with_status_and_details(tmp_path, monkeypatch):
    from scripts.pm99_season_amend_v1 import AmendmentBuildError

    def builder(season, **kwargs):
        raise AmendmentBuildError("stale edit change-0001", status="stale", details={"ignored": []})

    catalog, _ = _build_bound_catalog(tmp_path, monkeypatch, builder=builder)
    catalog.stage_amendment(season="2000-01", manifest_id="preferred-release/base-release/season-package.json",
        json_pointer="/players/0/ratings/values/speed", replacement=71, reason="edit", evidence=None)
    status, body = _http(catalog, "POST", "/api/amendments/build", {"season": "2000-01"})
    assert status == 409 and body["status"] == "stale" and "stale edit" in body["error"]
    # The lock is released after a failure, so the user can fix the edit and retry.
    assert catalog._build_lock.acquire(blocking=False)
    catalog._build_lock.release()


def test_a_busy_workbook_refuses_a_second_concurrent_build(tmp_path, monkeypatch):
    catalog, _ = _build_bound_catalog(tmp_path, monkeypatch, builder=lambda *a, **k: {})
    catalog.stage_amendment(season="2000-01", manifest_id="preferred-release/base-release/season-package.json",
        json_pointer="/players/0/ratings/values/speed", replacement=71, reason="edit", evidence=None)
    from tools.season_manifest_amendments import AmendmentError
    assert catalog._build_lock.acquire(blocking=False)
    try:
        with pytest.raises(AmendmentError, match="already running"):
            catalog.build_amendments(season="2000-01", dry_run=False)
    finally:
        catalog._build_lock.release()


def test_a_built_candidate_can_become_the_base_of_the_next_edit(tmp_path, monkeypatch):
    from scripts import season_amendment_candidates_v1 as registry_of_candidates
    from tools.season_manifest_amendments import AmendmentError
    edited = _package()
    edited["players"][0]["ratings"]["values"]["speed"] = 71
    calls = []
    catalog, _ = _build_bound_catalog(tmp_path, monkeypatch, candidate_packages={"edited-2000-01-abc": edited},
                                      builder=lambda season, **k: calls.append(k) or {"status": "built"})
    with pytest.raises(AmendmentError, match="built by this workbook"):
        catalog.select_base(season="2000-01", release_id="edited-2000-01-abc")
    registry_of_candidates.record_candidate("2000-01", dict(release_id="edited-2000-01-abc", parent_release_id="base-release",
        change_count=1, play_command="x", summary=[]), tmp_path / "builds")
    base = catalog.select_base(season="2000-01", release_id="edited-2000-01-abc")
    assert base["release_id"] == "edited-2000-01-abc" and base["is_preferred_release"] is False
    assert catalog.spreadsheet_metadata("2000-01")["source"]["id"] == "preferred-release/edited-2000-01-abc/season-package.json"
    speed = catalog.spreadsheet_tab(season="2000-01", tab="players", query="", offset=0, limit=5)["table"]["rows"][0]["cells"]["rating:speed"]
    assert speed["value"] == 71   # the edited value is now the locked 'before' of the next edit
    catalog.stage_amendment(season="2000-01", manifest_id="preferred-release/edited-2000-01-abc/season-package.json",
        json_pointer="/players/0/ratings/values/speed", replacement=72, reason="again", evidence=None)
    assert catalog.amendments("2000-01")["changes"][0]["expected"] == 71
    catalog.build_amendments(season="2000-01", dry_run=False)
    assert calls[0]["parent_id"] == "edited-2000-01-abc"
    back = catalog.select_base(season="2000-01", release_id=None)
    assert back["release_id"] == "base-release" and back["is_preferred_release"] is True


def test_configured_reserve_is_passed_to_the_builder_and_defaults_to_the_builders_own(tmp_path, monkeypatch):
    seen = []
    catalog, _ = _build_bound_catalog(tmp_path, monkeypatch, builder=lambda season, **k: seen.append(k) or {})
    catalog.stage_amendment(season="2000-01", manifest_id="preferred-release/base-release/season-package.json",
        json_pointer="/players/0/ratings/values/speed", replacement=71, reason="edit", evidence=None)
    catalog.build_amendments(season="2000-01", dry_run=True)
    assert "minimum_free_bytes" not in seen[0]
    catalog._minimum_free_bytes = 6979321856
    catalog.build_amendments(season="2000-01", dry_run=True)
    assert seen[1]["minimum_free_bytes"] == 6979321856


def _mixed_package():
    package = _package()
    package["players"] += [
        {"id": "player-gk", "name": "Gil Keeper", "club_id": "club-1", "carrier_family": "dd6361",
         "facts": {"birth_date": "1980-01-02", "nationality": "ENG", "primary_position": "G", "shirt_number": 1,
                   "height_cm": 190, "weight_kg": 80, "fine_roles": [0]}, "ratings": {"values": {"handling": 70, "speed": 40}}},
        {"id": "player-compact", "name": "Cy Compact", "club_id": "club-1", "carrier_family": "dd6360",
         "facts": {"birth_date": "1981-01-02", "nationality": "ENG", "primary_position": "M", "shirt_number": 7,
                   "height_cm": 180, "weight_kg": 70, "fine_roles": [9]}, "ratings": {"values": {"handling": 5, "speed": 60}}},
        {"id": "player-unknown", "name": "Una Known", "club_id": "club-1", "carrier_family": "dd6361",
         "facts": {"birth_date": "1982-01-02", "nationality": "ENG", "primary_position": "D", "shirt_number": 4,
                   "height_cm": 185, "weight_kg": {"policy": "unknown-preserve"}, "fine_roles": [4]},
         "ratings": {"values": {"handling": 5, "speed": 60}}},
    ]
    package["managers"].append({"id": "manager-2", "name": "Foreign Boss", "carrier_id": 11, "policy": "preserve-existing-mode1"})
    return package


def test_cells_and_staging_use_the_records_own_capability(tmp_path, monkeypatch):
    from tools.season_manifest_amendments import AmendmentError
    catalog, browser = _build_bound_catalog(tmp_path, monkeypatch)
    _write(tmp_path / "base.json", _mixed_package())
    catalog.select_base(season="2000-01", release_id=None)               # reload the recipe the fake release now points at
    cells = {r["id"]: r["cells"] for r in catalog.spreadsheet_tab(season="2000-01", tab="players", query="", offset=0, limit=20)["table"]["rows"]}
    assert cells["player-1"]["position"]["editable"] is True and cells["player-1"]["shirt_number"]["editable"] is True
    assert cells["player-gk"]["position"]["editable"] is False and "goalkeeper" in cells["player-gk"]["position"]["build_note"]
    assert cells["player-gk"]["rating:handling"]["editable"] is True                       # ratings are still editable for a keeper
    assert cells["player-compact"]["shirt_number"]["editable"] is False and "dd6361" in cells["player-compact"]["shirt_number"]["build_note"]
    assert cells["player-compact"]["position"]["editable"] is False and cells["player-compact"]["rating:speed"]["editable"] is True
    # An unknown weight blocks only the weight cell, not the same person's other cells.
    assert cells["player-unknown"]["weight_kg"]["editable"] is False
    assert cells["player-unknown"]["position"]["editable"] is True and cells["player-unknown"]["rating:speed"]["editable"] is True
    managers = {r["id"]: r["cells"] for r in catalog.spreadsheet_tab(season="2000-01", tab="managers", query="", offset=0, limit=20)["table"]["rows"]}
    assert managers["manager-1"]["name"]["editable"] is True
    assert managers["manager-2"]["name"]["editable"] is False and "preserved/foreign" in managers["manager-2"]["name"]["build_note"]
    # The server refuses the same edits even if a client posts them.
    manifest = "preferred-release/base-release/season-package.json"
    for pointer, value, fragment in (("/players/1/facts/primary_position", "D", "goalkeeper"), ("/players/2/facts/shirt_number", 8, "dd6361"),
                                     ("/players/3/facts/weight_kg", 70, "unknown/preserved"), ("/managers/1/name", "X Y", "preserved/foreign"),
                                     ("/players/0/facts/primary_position", "G", "goalkeeper")):
        with pytest.raises(AmendmentError, match=fragment):
            catalog.stage_amendment(season="2000-01", manifest_id=manifest, json_pointer=pointer, replacement=value, reason="r", evidence=None)
    catalog.stage_amendment(season="2000-01", manifest_id=manifest, json_pointer="/players/3/ratings/values/speed", replacement=61, reason="r", evidence=None)
    assert [c["json_pointer"] for c in catalog.amendments("2000-01")["changes"]] == ["/players/3/ratings/values/speed"]


def test_browser_reserve_option_uses_the_shared_hard_floor(tmp_path, monkeypatch):
    import sys
    (tmp_path / "s").mkdir()
    from tools import season_preset_browser as browser
    monkeypatch.setattr(sys, "argv", ["x", "--minimum-free-bytes", "6710886400", "--no-browser"])
    assert browser.parse_args().minimum_free_bytes == 6710886400
    monkeypatch.setattr(sys, "argv", ["x", "--no-browser"])
    assert browser.parse_args().minimum_free_bytes is None                   # default stays the builder's 8 GiB
    with pytest.raises(ValueError, match="6 GiB"):
        PresetCatalog(tmp_path / "s", include_source_captures=False, minimum_free_bytes=6 * 1024 ** 3 - 1, **_empty_indexes(tmp_path))
    with pytest.raises(ValueError, match="6 GiB"):
        PresetCatalog(tmp_path / "s", include_source_captures=False, minimum_free_bytes=1, **_empty_indexes(tmp_path))
    PresetCatalog(tmp_path / "s", include_source_captures=False, minimum_free_bytes=6 * 1024 ** 3, **_empty_indexes(tmp_path))
    # main() turns a below-floor value into a startup error instead of a silently smaller guard.
    monkeypatch.setattr(sys, "argv", ["x", "--minimum-free-bytes", "1", "--no-browser", "--seasons-root", str(tmp_path / "s")])
    with pytest.raises(SystemExit):
        browser.main()
