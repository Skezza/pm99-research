"""Focused private contract tests for the source-bound Shevlin adapter."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
ROOT = next(parent for parent in HERE.parents if (parent / "scripts" / "season_release_registry_v1.py").is_file())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MODULE_PATH = HERE / "season_ballymena_shevlin_reserve_v1.py"
REQUEST_PATH = ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/calendar-2017-slice-v3-capture-guard/ballymena-shevlin-reserve-v2/ballymena-shevlin-reserve-request-v2.json"
SPEC = importlib.util.spec_from_file_location("private_shevlin_adapter_v1", MODULE_PATH)
adapter = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
sys.modules[SPEC.name] = adapter
SPEC.loader.exec_module(adapter)


@pytest.fixture(scope="module")
def context():
    if not REQUEST_PATH.is_file() or not adapter.registry.locator_path("2017-18", adapter.PARENT).is_file():
        pytest.skip("retained local Ballymena source request/corpus is unavailable")
    base = adapter.registry.load_registered_release("2017-18", adapter.PARENT)
    plan = adapter.prepare(base, REQUEST_PATH)
    parent = adapter.pipeline.read_json_file(base.package_path)
    post = adapter.bind(parent, plan)
    jug = (base.game_path / "DBDAT/JUG98030.FDI").read_bytes()
    eq = (base.game_path / "DBDAT/EQ98030.FDI").read_bytes()
    minifoto = (base.game_path / "DBDAT/MINIFOTO.PKF").read_bytes()
    return base, plan, parent, post, jug, eq, minifoto


def test_prepare_binds_provider_identity_and_source_artifact(context, tmp_path):
    base, plan, _, _, _, _, _ = context
    assert plan["target"]["after"]["person_id"] == "person-bufchistory-player-35"
    assert adapter.packages.ID_RE.fullmatch(plan["target"]["after"]["person_id"])
    assert plan["person_id_material"]["source_provider"] == "bufchistory"
    assert plan["person_id_material"]["provider_player_id"] == "35"
    assert plan["target"]["after"]["full_name"] == "Matthew Shevlin"
    assert plan["target"]["after"]["native_display_name"] == "Shevlin"
    assert adapter.verify(base, plan) is None
    artifact = adapter.source_artifact(plan)
    assert artifact["document"] == plan
    assert artifact["filename"] == adapter.filename(plan)
    actual_path = tmp_path / artifact["filename"]
    adapter.pipeline.write_canonical_json(actual_path, artifact["document"])
    assert actual_path.read_bytes() == artifact["bytes"]
    assert artifact["bytes"] == adapter.packages.canonical_json_bytes(plan)
    assert artifact["bytes"].endswith(b"\n") and not artifact["bytes"].endswith(b"\n\n")
    assert adapter.digest(artifact["bytes"]) == artifact["sha256"]


def test_wrong_request_source_or_parent_binding_fails_closed(context, tmp_path):
    base, _, _, _, _, _, _ = context
    original = json.loads(REQUEST_PATH.read_text(encoding="utf-8"))
    wrong_source = copy.deepcopy(original)
    wrong_source["sources"]["shevlin_profile"]["url"] = "https://transfermarkt.example/player/35"
    source_path = tmp_path / "wrong-source.json"
    source_path.write_text(json.dumps(wrong_source), encoding="utf-8")
    with pytest.raises(ValueError, match="source hash/URL pin differs"):
        adapter.prepare(base, source_path)

    wrong_parent = copy.deepcopy(original)
    wrong_parent["parent_package_sha256"] = "0" * 64
    parent_path = tmp_path / "wrong-parent.json"
    parent_path.write_text(json.dumps(wrong_parent), encoding="utf-8")
    with pytest.raises(ValueError, match="request package binding differs"):
        adapter.prepare(base, parent_path)


def test_native_apply_changes_only_shevlin_record_and_preserves_eq(context):
    base, plan, parent, post, jug, eq, _ = context
    output_jug, output_eq = adapter.apply(jug, eq, plan)
    assert output_eq == eq

    from app.fdi_indexed import IndexedFDIFile

    def payloads(data: bytes) -> dict[int, bytes]:
        index = IndexedFDIFile.from_bytes(data)
        return {
            entry.record_id: data[entry.payload_offset:entry.payload_offset + entry.payload_length]
            for entry in index.entries
        }

    before, after = payloads(jug), payloads(output_jug)
    assert [record_id for record_id in before if before[record_id] != after[record_id]] == [19829]
    index = IndexedFDIFile.from_bytes(output_jug)
    entry = next(item for item in index.entries if item.record_id == 19829)
    native = adapter.roster.native_player(entry.decode_payload(output_jug), 19829)
    facts = adapter.exchange.facts.native_facts(output_jug, 19829)
    assert (native["name"], native["position"], native["roles"][0]) == ("Shevlin", "F", 12)
    assert (facts["birth_date"], facts["startup_order"]) == ("1998-12-07", 12)
    assert post["players"] != parent["players"]


def test_selected_portrait_is_explicit_no_photo_and_exact_archive_noop(context):
    base, plan, _, _, _, _, minifoto = context
    assert adapter.selected_carriers(plan) == {19829}
    assert not (base.game_path / "DBDAT/MINIFOTO/J9619829.BMP").exists()
    assert adapter.photo_offsets(plan) == {19829: []}
    assert adapter.apply_minifoto(minifoto, plan) == minifoto
    with pytest.raises(ValueError, match="MINIFOTO accepts only exact preimage"):
        adapter.apply_minifoto(minifoto + b"tamper", plan)


def test_apply_rejects_mixed_native_pair_before_compilation(context):
    _, plan, _, _, jug, eq, _ = context
    mixed_eq = bytearray(eq)
    mixed_eq[-1] ^= 1
    with pytest.raises(ValueError, match="exact unchanged parent EQ"):
        adapter.apply(jug, bytes(mixed_eq), plan)


def test_source_reconstruction_checks_mode_before_locator_and_requires_matching_locator(tmp_path):
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"compilation_mode": "another-mode"}), encoding="utf-8")

    class ModeMismatch:
        compiler_receipt_path = receipt

        @property
        def locator(self):
            raise AssertionError("inherited locator must not be read for another mode")

    assert adapter.reconstruction(ModeMismatch(), "unused-release") is None

    receipt.write_text(json.dumps({"compilation_mode": adapter.MODE}), encoding="utf-8")
    matching = SimpleNamespace(compiler_receipt_path=receipt, locator={})
    with pytest.raises(ValueError, match="lacks the standard profile-assignment plan locator"):
        adapter.reconstruction(matching, "unused-release")


def test_matching_source_reconstruction_routes_parent_and_child_inventories(tmp_path, monkeypatch, context):
    base, plan, parent, post, _, _, _ = context
    from scripts import publish_historical_role_delta_v1 as publisher

    # A matching receipt must execute the positive SOURCE route. Keep the
    # planned source/recipe real, but stub publication and tree verification so
    # this test cannot build, register, or write any game release.
    import tempfile

    with tempfile.TemporaryDirectory(prefix="shevlin-source-route-", dir=adapter.registry.ROOT / ".local") as temp:
        package_dir = Path(temp)
        plan_path = package_dir / adapter.filename(plan)
        adapter.pipeline.write_canonical_json(plan_path, plan)
        artifact = adapter.source_artifact(plan)
        assert plan_path.read_bytes() == artifact["bytes"]

        expected_package = adapter.bind(parent, plan)
        expected_bytes = adapter.packages.canonical_json_bytes(expected_package)
        previous_package = package_dir / "season-package.json"
        previous_package.write_bytes(expected_bytes)
        descriptor_path = package_dir / "role-delta-input.json"
        descriptor = {
            "season": base.season,
            "release_id": base.release_id,
            "package_sha256": plan["parent"]["package_sha256"],
            "jug_sha256": plan["parent"]["jug_sha256"],
            "updates": [],
            "unresolved": [],
        }
        adapter.pipeline.write_canonical_json(descriptor_path, descriptor)
        candidate_inventory_path = package_dir / "candidate-inventory.json"
        candidate_inventory = {"files": [{"path": "sentinel", "sha256": "0" * 64}]}
        adapter.pipeline.write_canonical_json(candidate_inventory_path, candidate_inventory)
        receipt_path = package_dir / "compiler-receipt.json"
        adapter.pipeline.write_canonical_json(receipt_path, {
            "compilation_mode": adapter.MODE,
            "original_profile_assignment_plan_sha256": adapter.registry.sha256_file(plan_path),
        })

        candidate_tree = package_dir / "candidate-game-tree"
        rebuilt_tree = package_dir / "rebuilt-game-tree"
        child_id = "test-shevlin-source-child"
        previous = SimpleNamespace(
            season=base.season,
            release_id="test-shevlin-source-parent-candidate",
            package_path=previous_package,
            inventory_path=candidate_inventory_path,
            game_path=candidate_tree,
            compiler_receipt_path=receipt_path,
            locator={"sourced_profile_assignment_plan_path": adapter.registry.relative_workspace_path(plan_path)},
        )
        rebuilt_package = package_dir / "rebuilt-season-package.json"
        rebuilt_package.write_bytes(expected_bytes)
        rebuilt = SimpleNamespace(
            season=base.season,
            release_id=child_id,
            package_path=rebuilt_package,
            inventory_path=candidate_inventory_path,
            game_path=rebuilt_tree,
        )

        loads = []

        def load_release(season, release_id):
            loads.append((season, release_id))
            if release_id == base.release_id:
                return base
            if release_id == child_id:
                return rebuilt
            raise AssertionError(f"unexpected release lookup: {season}/{release_id}")

        monkeypatch.setattr(adapter.registry, "load_registered_release", load_release)
        publish_calls = []

        def publish(season, descriptor_path_arg, **kwargs):
            publish_calls.append((season, Path(descriptor_path_arg), kwargs))

        monkeypatch.setattr(publisher, "publish", publish)
        inventory_checks = []

        def assert_tree_matches_inventory(tree, inventory):
            inventory_checks.append((Path(tree), inventory))

        monkeypatch.setattr(adapter.pipeline, "assert_tree_matches_inventory", assert_tree_matches_inventory)
        result = adapter.reconstruction(previous, child_id)

        assert result == {
            "season": base.season,
            "release_id": child_id,
            "complete_game_inventory_identical": True,
            "complete_recipe_identical": True,
            "compilation_mode": adapter.MODE,
        }
        assert loads == [
            (base.season, base.release_id),  # source_artifact exact parent
            (base.season, base.release_id),  # reconstruction exact parent
            (base.season, base.release_id),  # bind exact parent
            (base.season, child_id),          # rebuilt child after publisher dispatch
        ]
        assert publish_calls == [(
            base.season,
            descriptor_path,
            {"release_id": child_id, "source_release_id": base.release_id,
             "profile_assignment_plan_path": plan_path},
        )]
        assert inventory_checks == [
            (base.game_path, adapter.pipeline.read_json_file(base.inventory_path)),
            (candidate_tree, candidate_inventory),
            (rebuilt_tree, candidate_inventory),
        ]
        assert previous_package.read_bytes() == rebuilt_package.read_bytes() == expected_bytes


def test_canonical_factory_compiler_rejects_source_bound_recipe(monkeypatch, context, tmp_path):
    _, _, _, post, _, _, _ = context
    from scripts import season_package_compiler_v2 as compiler

    isolated = copy.deepcopy(post)
    isolated["artifacts"] = [row for row in isolated["artifacts"] if row["id"].startswith(adapter.PREFIX)]
    assert len(isolated["artifacts"]) == 1
    monkeypatch.setattr(compiler, "_load_native_package", lambda _path: (isolated, "0" * 64))
    with pytest.raises(compiler.SeasonCompilerError, match="requires exact source reconstruction"):
        compiler.compile_package_to_tree(
            package_path=tmp_path / "bound.json",
            base_tree=tmp_path / "missing-base",
            materialisation_tree=tmp_path / "missing-output",
        )
