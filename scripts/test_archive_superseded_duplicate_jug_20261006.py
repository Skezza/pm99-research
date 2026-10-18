from pathlib import Path
import pytest
from scripts import archive_superseded_duplicate_jug_20261006 as mod


@pytest.fixture
def tree(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, 'SOURCE', tmp_path)
    monkeypatch.setattr(mod.registry, 'supported_seasons', lambda: ['2001-02'])
    monkeypatch.setattr(mod.archive, '_active_game', lambda p: False)
    def create(release='opening-test-20261006-r31a', filename='JUG98030.FDI'):
        path = tmp_path / '2001-02' / release / 'game/DBDAT' / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'test')
        return path
    return create


def test_old_unshared_allowed(tree):
    mod.eligible(tree(), set())


@pytest.mark.parametrize('release', ['opening-test-20261006-r32a',
    'historical-manager-display-20261005-r22a', 'opening-test-20261006-r36a'])
def test_preserve_other_releases(tree, release):
    with pytest.raises(ValueError):
        mod.eligible(tree(release), set())


def test_protected_base(tree):
    path = tree()
    with pytest.raises(ValueError):
        mod.eligible(path, {path.resolve()})


def test_other_file(tree):
    with pytest.raises(ValueError):
        mod.eligible(tree(filename='EQ98030.FDI'), set())


def test_hardlink(tree, tmp_path):
    path = tree()
    (tmp_path / 'shared').hardlink_to(path)
    with pytest.raises(ValueError):
        mod.eligible(path, set())


def test_running_game(tree, monkeypatch):
    path = tree()
    monkeypatch.setattr(mod.archive, '_active_game', lambda p: True)
    with pytest.raises(ValueError):
        mod.eligible(path, set())


def test_later_cohort_needs_explicit_bounded_allowlist_and_still_protects_current(tree):
    import re
    pattern=re.compile(r'opening-[a-z0-9.-]+-20261006-r3[2-5]a')
    path=tree('opening-test-20261006-r32a')
    mod.eligible(path,set(),pattern)
    with pytest.raises(ValueError):mod.eligible(path,{path.resolve()},pattern)
    with pytest.raises(ValueError):mod.eligible(tree('opening-test-20261006-r36a'),set(),pattern)


def test_unknown_retirement_cohort_is_refused_before_any_backup_or_removal():
    with pytest.raises(ValueError,match='unknown exact'):
        mod.run(True,'all-old-builds')


def test_later_baselines_cannot_be_retired_before_full_closeouts(tmp_path,monkeypatch):
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='complete R36/R37/R38'):
        mod.run(True,'r32-r38-after-r38')


def test_complete_closeouts_still_require_next_batch_baselines(tmp_path,monkeypatch):
    import json
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    for label in ('r36','r37','r38'):
        path=tmp_path/'.local/duplicate-ownership-v3'/f'closeout-{label}-final/summary.json'
        path.parent.mkdir(parents=True);path.write_text(json.dumps({'full_release_validation_passed':26}))
    with pytest.raises(ValueError,match='all 26 next-batch'):
        mod.run(True,'r32-r38-after-r38')


def test_recipe_exact_location_and_game_root(tree):
    import re
    jug=tree('opening-test-20261006-r38a')
    recipe=jug.parents[2]/'season-package.json'
    recipe.write_bytes(b'{}')
    pattern=re.compile(r'opening-[a-z0-9.-]+-20261006-r(?:2[3-9]|3[0-8])a')
    mod.eligible(recipe,set(),pattern,'season-package.json')
    assert mod.game_root(recipe,'season-package.json')==jug.parents[1]
    with pytest.raises(ValueError):mod.eligible(recipe,{recipe.resolve()},pattern,'season-package.json')
    with pytest.raises(ValueError):mod.eligible(jug,set(),pattern,'season-package.json')


def test_recipe_shared_and_future_release_are_preserved(tree,tmp_path):
    import re
    pattern=re.compile(r'opening-[a-z0-9.-]+-20261006-r(?:2[3-9]|3[0-8])a')
    jug=tree('opening-test-20261006-r38a')
    recipe=jug.parents[2]/'season-package.json';recipe.write_bytes(b'{}')
    (tmp_path/'shared-recipe').hardlink_to(recipe)
    with pytest.raises(ValueError):mod.eligible(recipe,set(),pattern,'season-package.json')
    future=tree('opening-test-20261006-r39a').parents[2]/'season-package.json'
    future.write_bytes(b'{}')
    with pytest.raises(ValueError):mod.eligible(future,set(),pattern,'season-package.json')


def test_recipe_cohort_also_requires_full_closeout(tmp_path,monkeypatch):
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    with pytest.raises(ValueError,match='complete R36/R37/R38'):
        mod.run(True,'recipes-r23-r38-after-r38')
