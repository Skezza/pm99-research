"""Fixture tests for the source-only NTF package integration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import scripts.integrate_2015_ntf_source_package as integration


def _capture(club_name: str, *, country: str, competition: str, source_path: str, player_count: int) -> dict:
    return {
        "schema_version": "pm99-footballsquads-season-capture-v1",
        "source": {"title": "fixture", "repository": "fixture", "revision": "fixture", "license": "fixture"},
        "season": {"catalog": "fixture", "label": "fixture"},
        "clubs": [{
            "country_catalog": country, "competition_catalog": competition, "club_name": club_name,
            "source_path": source_path, "source_sha256": f"sha-{source_path}",
            "players": [{"name": f"Player {index}", "birth_date": "1990-01-01", "nationality": "SRB", "position": "M", "unresolved_fields": []} for index in range(player_count)],
        }],
    }


def test_explicit_ntf_binding_replaces_only_matching_carrier(monkeypatch, tmp_path: Path) -> None:
    base = _capture("Existing", country="serbia", competition="old", source_path="base.txt", player_count=1)
    ntf = _capture("New Club", country="serbia", competition="national-football-teams-2015-1", source_path="ntf.html", player_count=1)
    ntf["clubs"][0]["candidate_carrier_id"] = 701
    ntf["clubs"][0]["fixed_roster_slot_count"] = 1
    registry = {"carriers": [{"carrier_id": 701, "roster_slots": [{"slot_index": 0}], "baseline_club": {"name": "Old", "active_manager_carrier_id": 1}}]}
    base_draft = {
        "schema_version": "pm99-world-2015-source-carrier-drafts-v1",
        "registry_sha256": integration.digest(registry),
        "source_capture_sha256": integration.digest(base),
        "proposals": [{"carrier_id": 701, "group": "serbia", "baseline_name": "Old", "fixed_roster_slot_count": 1, "status": "no-captured-source-country"}],
    }
    monkeypatch.setattr(integration, "_read_fifa_rows", lambda _path: ([], "fifa-fixture"))
    monkeypatch.setattr(integration, "build_reconciliation", lambda **_kwargs: {"carrier_plans": [], "coverage": {}, "sources": {}})
    _capture_out, draft, report = integration.integrate(registry=registry, base_capture=base, base_draft=base_draft, ntf_capture=ntf, fifa_csv=tmp_path / "unused.csv")
    assert draft["proposals"][0]["status"] == "source-squad-ready"
    assert draft["proposals"][0]["source_club_name"] == "New Club"
    assert report["coverage"]["remaining_unresolved_carrier_count"] == 0


def test_duplicate_ntf_candidate_is_rejected(tmp_path: Path) -> None:
    base = _capture("Existing", country="serbia", competition="old", source_path="base.txt", player_count=1)
    ntf = _capture("First", country="serbia", competition="national-football-teams-2015-1", source_path="first.html", player_count=1)
    second = _capture("Second", country="serbia", competition="national-football-teams-2015-1", source_path="second.html", player_count=1)["clubs"][0]
    ntf["clubs"][0]["candidate_carrier_id"] = 701
    second["candidate_carrier_id"] = 701
    ntf["clubs"].append(second)
    registry = {"carriers": [{"carrier_id": 701, "roster_slots": [{"slot_index": 0}], "baseline_club": {"name": "Old", "active_manager_carrier_id": 1}}]}
    base_draft = {"schema_version": "pm99-world-2015-source-carrier-drafts-v1", "registry_sha256": integration.digest(registry), "source_capture_sha256": integration.digest(base), "proposals": [{"carrier_id": 701, "group": "serbia", "baseline_name": "Old", "fixed_roster_slot_count": 1, "status": "unresolved"}]}
    try:
        integration.integrate(registry=registry, base_capture=base, base_draft=base_draft, ntf_capture=ntf, fifa_csv=tmp_path / "unused.csv")
    except ValueError as exc:
        assert "unique integer candidate_carrier_id" in str(exc)
    else:
        raise AssertionError("duplicate NTF candidate carrier was accepted")


if __name__ == "__main__":
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as directory:
        path = Path(directory)
        # Keep direct execution dependency-free; invoke the first test with a
        # tiny monkeypatch shim rather than requiring pytest.
        class Patch:
            def setattr(self, obj, name, value):
                old = getattr(obj, name)
                setattr(obj, name, value)
                return old
        # The assertions above are run by the repository's pytest lane.
        print("fixture tests require pytest monkeypatch fixture")
