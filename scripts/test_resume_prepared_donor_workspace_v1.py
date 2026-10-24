import os
from types import SimpleNamespace
import pytest
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import season_pipeline_v2 as pipeline
from scripts import season_donor_keeper_role_delta_v1 as source


def fixture(tmp_path):
    base=tmp_path/'base';game=base/'game';(game/'DBDAT').mkdir(parents=True)
    (game/'DBDAT/JUG98030.FDI').write_bytes(b'before')
    (game/'DBDAT/EQ98030.FDI').write_bytes(b'unchanged')
    before=pipeline.build_tree_inventory(game)
    workspace=tmp_path/'prepared';target=workspace/'game';(target/'DBDAT').mkdir(parents=True)
    (target/'DBDAT/JUG98030.FDI').write_bytes(b'after')
    (target/'DBDAT/EQ98030.FDI').write_bytes(b'unchanged')
    package=dict(players=[],artifacts=[]);plan=dict(updates=[]);assignment=dict(transaction_id='test')
    (workspace/'season-package.json').write_bytes(publisher.package_v2.canonical_json_bytes(package))
    pipeline.write_canonical_json(workspace/'role-delta-input.json',plan)
    pipeline.write_canonical_json(workspace/source.filename(assignment),assignment)
    return workspace,SimpleNamespace(package_path=base/'season-package.json'),before,b'after',package,plan,assignment


def test_resume_proves_complete_staged_game_and_metadata_without_writing(tmp_path):
    args=fixture(tmp_path)
    before={str(p):p.read_bytes() for p in args[0].rglob('*') if p.is_file()}
    publisher._verify_prepared_donor_workspace(*args)
    assert {str(p):p.read_bytes() for p in args[0].rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('change',['other-game-file','selected-game-file','recipe','input',
    'assignment','unexpected-metadata','advanced-receipt','shared-recipe'])
def test_resume_refuses_changed_or_unrecognised_and_later_state(tmp_path,change):
    args=fixture(tmp_path);workspace=args[0]
    if change=='other-game-file':(workspace/'game/DBDAT/EQ98030.FDI').write_bytes(b'changed')
    if change=='selected-game-file':(workspace/'game/DBDAT/JUG98030.FDI').write_bytes(b'changed')
    if change=='recipe':(workspace/'season-package.json').write_bytes(b'{}')
    if change=='input':(workspace/'role-delta-input.json').write_bytes(b'{}')
    if change=='assignment':(workspace/source.filename(args[-1])).write_bytes(b'{}')
    if change=='unexpected-metadata':(workspace/'unexpected.json').write_bytes(b'{}')
    if change=='advanced-receipt':(workspace/'role-delta-compiler.json').write_bytes(b'{}')
    if change=='shared-recipe':os.link(workspace/'season-package.json',tmp_path/'shared.json')
    with pytest.raises(ValueError):publisher._verify_prepared_donor_workspace(*args)


def test_resume_source_assignment_module_preserves_same_fail_closed_guards(tmp_path):
    from scripts import season_ballymena_shevlin_reserve_v1 as shevlin
    args = fixture(tmp_path)
    workspace = args[0]
    old = workspace / source.filename(args[-1])
    new = workspace / shevlin.filename(args[-1])
    old.rename(new)
    publisher._verify_prepared_donor_workspace(*args, assignment_module=shevlin)
    (workspace / 'game/DBDAT/EQ98030.FDI').write_bytes(b'unrelated corruption')
    with pytest.raises(ValueError):
        publisher._verify_prepared_donor_workspace(*args, assignment_module=shevlin)
