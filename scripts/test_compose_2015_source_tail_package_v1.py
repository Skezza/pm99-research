"""Focused checks for strict 2015 source-tail package composition."""

from scripts.compose_2015_source_tail_package_v1 import (
    CaptureInput,
    SourceTailPackageError,
    compose,
)


PLAN_SHA = "a" * 64


def _plan() -> dict:
    return {
        "schema_version": "pm99-world-2015-source-tail-replacement-plan-v1",
        "assignments": [
            {
                "carrier_id": number, "fixed_roster_slot_count": 11, "family": "example",
                "status": "proposed-target-membership-club-awaiting-capacity-source",
                "proposed_target": {"name": name, "article_title": title, "article_path": f"/wiki/{name}"},
            }
            for number, name, title in ((1, "One", "One F.C."), (2, "Two", "Two F.C."), (3, "Three", "Three F.C."))
        ],
    }


def _club(number: int, name: str, title: str) -> dict:
    return {
        "candidate_carrier_id": number, "fixed_roster_slot_count": 11, "country_catalog": "example",
        "club_name": name, "target_article_title": title, "target_article_path": f"/wiki/{name}",
        "players": [
            {"name": f"{name} {index}", "nationality": "ENG", "position": "M", "unresolved_fields": []}
            for index in range(11)
        ],
    }


def _input(name: str, route: str, schema: str, club: dict, *, pinned_sha: str | None = None) -> CaptureInput:
    source = {"title": name, "repository": "example", "tail_plan_sha256": PLAN_SHA}
    if schema == "pm99-world-2015-source-tail-squad-capture-v1":
        value = {"schema_version": schema, "sources": {"source_tail_plan_sha256": PLAN_SHA}, "clubs": [club]}
    elif schema == "pm99-world-2015-lff-opening-squad-capture-v1":
        value = {"schema_version": schema, "source": source, "club": club}
    else:
        source["tail_squad_receipt_sha256"] = pinned_sha
        value = {"schema_version": schema, "source": source, "clubs": [club]}
    return CaptureInput(name=name, route=route, value=value, sha256=("b" if name == "pinned" else "c") * 64)


def _inputs() -> list[CaptureInput]:
    pinned = _input("pinned", "pinned-historic-season-squad", "pm99-world-2015-source-tail-squad-capture-v1", _club(1, "One", "One F.C."))
    opening = _input("opening", "opening-window", "pm99-world-2015-source-tail-opening-squad-capture-v1", _club(2, "Two", "Two F.C."), pinned_sha=pinned.sha256)
    granitas = _input("granitas", "official-opening-window-exception", "pm99-world-2015-lff-opening-squad-capture-v1", _club(3, "Three", "Three F.C."))
    return [pinned, opening, granitas]


def test_composition_requires_all_planned_carriers_and_binds_inputs() -> None:
    result = compose(plan=_plan(), plan_sha256=PLAN_SHA, captures=_inputs())
    assert result["summary"]["covered_carrier_count"] == 3
    assert result["summary"]["source_route_counts"] == {
        "opening-window": 1, "official-opening-window-exception": 1, "pinned-historic-season-squad": 1,
    }


def test_composition_rejects_unknown_nationality_before_any_database_write() -> None:
    inputs = _inputs()
    inputs[0].value["clubs"][0]["players"][0]["nationality"] = "UNK"  # type: ignore[index]
    try:
        compose(plan=_plan(), plan_sha256=PLAN_SHA, captures=inputs)
    except SourceTailPackageError as error:
        assert "unresolved nationality" in str(error)
    else:
        raise AssertionError("unknown nationality must not reach a package")
