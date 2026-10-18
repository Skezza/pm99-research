"""Pure imports need no installed releases; explicit play lookups remain strict."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import pm99_season_play_v1 as play


def test_import_does_not_read_local_release_locators():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([
        str(root / "upstream/pm99-skezmod-db-editor"), str(root),
    ]))
    code = """
from scripts import season_release_registry_v1 as registry
def forbidden(*args, **kwargs):
    raise AssertionError('pure import read a local release locator')
registry.load_preferred_release = forbidden
from scripts import pm99_season_play_v1, pm99_season_qa_v1
print('pure-import-pass')
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "pure-import-pass"


def test_legacy_revision_mapping_is_lazy_and_uses_one_stable_snapshot(monkeypatch):
    calls = []
    monkeypatch.setattr(play.registry, "supported_seasons", lambda: ["2000-01", "2001-02", "2015-16"])

    def load(season):
        calls.append(season)
        return SimpleNamespace(revision="r1" if season == "2000-01" else None)

    monkeypatch.setattr(play.registry, "load_preferred_release", load)
    revisions = play._PreferredRevisions()
    assert calls == []
    assert revisions["2000-01"] == "r1"
    assert revisions.get("2001-02") is None
    assert dict(revisions) == {"2000-01": "r1"}
    assert sorted(revisions) == ["2000-01"]
    assert len(revisions) == 1
    assert calls == ["2000-01", "2001-02"]


def test_explicit_revision_lookup_does_not_hide_missing_registration(monkeypatch):
    monkeypatch.setattr(play.registry, "supported_seasons", lambda: ["2000-01"])

    def missing(season):
        raise play.registry.RegistryError("missing test locator")

    monkeypatch.setattr(play.registry, "load_preferred_release", missing)
    with pytest.raises(play.registry.RegistryError, match="missing test locator"):
        play._PreferredRevisions()["2000-01"]
