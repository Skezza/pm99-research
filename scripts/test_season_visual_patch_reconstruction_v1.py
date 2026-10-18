from types import SimpleNamespace

import pytest

from scripts import season_visual_patch_reconstruction_v1 as replay


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(replay.registry, 'ROOT', tmp_path)
    plan = tmp_path / 'plan.json'
    replay.pipeline.write_canonical_json(plan, dict(inputs=dict(release_id='base', package_sha256='original')))
    material = tmp_path / 'materialisation.json'
    replay.pipeline.write_canonical_json(material, {})
    application = tmp_path / 'application.json'
    replay.pipeline.write_canonical_json(application, dict(plan_sha256=replay.registry.sha256_file(plan),
        materialisation_path=str(material), materialisation_sha256=replay.registry.sha256_file(material)))
    chain = tmp_path / 'chain.json'
    replay.pipeline.write_canonical_json(chain, dict(stages=[dict(id='portrait-art',
        receipt_sha256=replay.registry.sha256_file(application))]))
    package = tmp_path / 'recipe.json'
    package.write_bytes(b'original')
    return SimpleNamespace(season='2005-06', release_id='art', build_chain_path=chain,
        package_path=package, locator=dict(visual_patch_plan_path='plan.json',
            portrait_patch_application_path='application.json')), plan, material, application


def test_unannotated_historical_release_is_not_misclassified():
    assert replay.reconstruction(SimpleNamespace(locator={}), 'new') is None


def test_subsequent_database_layer_has_priority(tmp_path, monkeypatch):
    previous, *_ = fixture(tmp_path, monkeypatch)
    alternate = tmp_path / 'later-chain.json'
    replay.pipeline.write_canonical_json(alternate, dict(stages=[dict(id='newer-database-layer')]))
    previous.build_chain_path = alternate
    assert replay.reconstruction(previous, 'new') is None


@pytest.mark.parametrize('fault', ['plan', 'materialisation', 'application'])
def test_changed_artwork_evidence_stops_before_copy(tmp_path, monkeypatch, fault):
    previous, plan, material, application = fixture(tmp_path, monkeypatch)
    path = dict(plan=plan, materialisation=material, application=application)[fault]
    path.write_bytes(b'changed')
    with pytest.raises((ValueError, replay.pipeline.PipelineError)):
        replay.reconstruction(previous, 'new')


def test_edited_recipe_is_not_discarded(tmp_path, monkeypatch):
    previous, _, material, _ = fixture(tmp_path, monkeypatch)
    base = tmp_path / 'base-recipe.json'
    base.write_bytes(b'original')
    plan = tmp_path / 'correctly-bound-plan.json'
    replay.pipeline.write_canonical_json(plan, dict(inputs=dict(release_id='base',
        package_sha256=replay.registry.sha256_file(base))))
    application = tmp_path / 'correctly-bound-application.json'
    replay.pipeline.write_canonical_json(application, dict(plan_sha256=replay.registry.sha256_file(plan),
        materialisation_path=str(material), materialisation_sha256=replay.registry.sha256_file(material)))
    chain = tmp_path / 'correctly-bound-chain.json'
    replay.pipeline.write_canonical_json(chain, dict(stages=[dict(id='portrait-art',
        receipt_sha256=replay.registry.sha256_file(application))]))
    previous.build_chain_path = chain
    previous.locator.update(visual_patch_plan_path=plan.name,
        portrait_patch_application_path=application.name)
    previous.package_path.write_bytes(b'user-edited-recipe')
    monkeypatch.setattr(replay.registry, 'load_registered_release',
        lambda *a: SimpleNamespace(package_path=base))
    # All source/evidence bindings are valid: only the user's recipe differs.
    # Refuse before any copy, runtime invocation or product output mutation.
    with pytest.raises(ValueError, match='no edits discarded'):
        replay.reconstruction(previous, 'new')
    assert previous.package_path.read_bytes() == b'user-edited-recipe'
