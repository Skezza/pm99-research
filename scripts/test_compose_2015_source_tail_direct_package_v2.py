"""Focused checks for zero-gap direct V2 source promotion."""

from scripts.compose_2015_source_tail_direct_package_v2 import DirectPackageError, compose


PLAN_SHA = "a" * 64


def _plan() -> dict:
    return {"schema_version": "pm99-world-2015-source-tail-replacement-plan-v1", "assignments": [{
        "carrier_id": 1, "fixed_roster_slot_count": 11, "family": "example",
        "status": "proposed-target-membership-club-awaiting-capacity-source",
        "proposed_target": {"name": "One", "article_title": "One F.C.", "article_path": "/wiki/One"},
    }]}


def _capture(gaps: list[dict] | None = None) -> dict:
    return {"schema_version": "pm99-world-2015-source-tail-squad-capture-v1", "sources": {
        "source_tail_plan_sha256": PLAN_SHA, "title": "test", "repository": "example",
    }, "gaps": gaps or [], "clubs": [{
        "candidate_carrier_id": 1, "fixed_roster_slot_count": 11, "country_catalog": "example",
        "club_name": "One", "target_article_title": "One F.C.", "target_article_path": "/wiki/One",
        "players": [{"name": f"One {index}", "nationality": "ENG", "position": "M", "unresolved_fields": []} for index in range(11)],
    }]}


def test_direct_package_promotes_complete_capture_only() -> None:
    result = compose(plan=_plan(), plan_sha256=PLAN_SHA, squad_capture=_capture(), squad_sha256="b" * 64)
    assert result["summary"]["covered_carrier_count"] == 1
    assert result["clubs"][0]["source_package"]["route"] == "pinned-historic-season-squad"


def test_direct_package_rejects_even_a_logged_source_gap() -> None:
    try:
        compose(plan=_plan(), plan_sha256=PLAN_SHA, squad_capture=_capture([{"reason": "short"}]), squad_sha256="b" * 64)
    except DirectPackageError as error:
        assert "zero-gap" in str(error)
    else:
        raise AssertionError("a gap cannot be promoted")
