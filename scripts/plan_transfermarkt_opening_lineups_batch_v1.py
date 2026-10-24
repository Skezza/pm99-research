#!/usr/bin/env python3
"""Plan deterministic Transfermarkt opening-lineup captures for many seasons.

The planner is deliberately offline.  It reads the checked season source-intake
manifests, translates FootballSquads catalogue aliases through a reviewed static
table, and writes one competition map and one capture plan per season.  It does
not contact Transfermarkt or execute the capture commands.

Every catalogue alias is classified.  Unknown or deliberately unsupported
aliases remain visible in the plan instead of being silently dropped or mapped
by a name guess.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping



ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import transfermarkt_calendar_year_policy_v1 as calendar_year_policy  # noqa: E402
PLAN_SCHEMA = "pm99-transfermarkt-opening-lineup-batch-plan-v1"
SELECTOR_SCHEMA = "pm99-transfermarkt-opening-lineup-selector-capture-v1"
MAP_SCHEMA = "pm99-transfermarkt-opening-lineup-competition-map-v1"
ENGLISH_MODE0_CATALOGS = {"faprem", "engprem", "d1", "d2", "d3", "flcham", "flone", "fltwo"}


# These are Transfermarkt competition identifiers, not inferred abbreviations.
# Multiple FootballSquads aliases intentionally resolve to one stable source
# competition.  Additions require review against a Transfermarkt competition
# page and a fixture page before this table is changed.
_ALIASES_BY_CODE: dict[str, tuple[tuple[str, str], ...]] = {
    "A1": (("austria", "bundes"), ("austria", "ausbun")),
    "AR1N": (("arg", "apertura"), ("arg", "clausura"), ("arg", "final"),
              ("arg", "inicial"), ("arg", "transic"), ("arg", "primera"),
              ("arg", "superl"), ("arg", "argprim"), ("arg", "argaper"),
              ("arg", "argclaus")),
    "AUS1": (("australia", "aleague"), ("australia", "ausalge")),
    "BE1": (("belgium", "eerste"), ("belgium", "prolge"), ("belgium", "belpro")),
    "BRA1": (("brazil", "campeon"), ("brazil", "seriea"), ("brazil", "bracamp")),
    "C1": (("switz", "superl"), ("switz", "switzsup")),
    "CLPD": (("chile", "apertura"), ("chile", "clausura"), ("chile", "chileprm")),
    "CNAT": (("eng", "conf"), ("eng", "confnat"), ("eng", "confprem"), ("eng", "national")),
    "CSL": (("china", "superlge"),),
    "DK1": (("denmark", "supliga"), ("denmark", "densuper")),
    "EFD2": (("eng", "d1"),),
    "ENSD": (("eng", "d2"),),
    "ENTD": (("eng", "d3"),),
    "ES1": (("spain", "laliga"), ("spain", "spalali")),
    "ES2": (("spain", "segunda"), ("spain", "laliga2"), ("spain", "spalali2")),
    "FR1": (("france", "div1"), ("france", "ligue1"), ("france", "fralig1")),
    "FR2": (("france", "ligue2"), ("france", "fralig2")),
    "GB1": (("eng", "faprem"), ("eng", "engprem")),
    "GB1F": (("eng", "wsl"),),
    "GB2": (("eng", "flcham"),),
    "GB3": (("eng", "flone"),),
    "GB4": (("eng", "fltwo"),),
    "GR1": (("greece", "ethniki"), ("greece", "superl"), ("greece", "gresuper")),
    "IR1": (("ireland", "prem"), ("ireland", "ireprm")),
    "IT1": (("italy", "seriea"),),
    "IT2": (("italy", "serieb"),),
    "JAP1": (("japan", "jleague"), ("japan", "japjlge")),
    "KR1": (("croatia", "1hnl"), ("croatia", "cro1hnl")),
    "L1": (("ger", "bundes"), ("ger", "gerbun")),
    "L2": (("ger", "bundes2"), ("ger", "gerbun2")),
    "MEXA": (("mexico", "apertura"), ("mexico", "mexaper")),
    "MEXC": (("mexico", "clausura"), ("mexico", "bicent"), ("mexico", "mexclaus")),
    "MLS1": (("usa", "mls"), ("usa", "usamls")),
    "NL1": (("holland", "ere"), ("netherl", "ere"), ("netherl", "nethere")),
    "NO1": (("norway", "tippe"), ("norway", "norelite")),
    "PL1": (("poland", "ekstrak"), ("poland", "polekstr")),
    "PO1": (("portugal", "superl"), ("portugal", "primeira"), ("portugal", "porprim")),
    "RU1": (("russia", "rfpl"), ("russia", "rpl"), ("russia", "russiapl")),
    "SA1": (("saudi", "saudipro"),),
    "SC1": (("scots", "scotprm"), ("scots", "scotsp")),
    "SC2": (("scots", "scotcham"), ("scots", "scotsch")),
    "SE1": (("sweden", "allsven"), ("sweden", "swedalls")),
    "TS1": (("czech", "gambrin"), ("czech", "1liga"), ("czech", "cze1liga")),
    "TR1": (("turkey", "superl"), ("turkey", "tursuper")),
    "UKR1": (("ukraine", "upl"), ("ukraine", "ukrainepl")),
    "UN1": (("hungary", "borsodi"), ("hungary", "soproni"), ("hungary", "monicomp"),
              ("hungary", "otpliga"), ("hungary", "hungnb1")),
    "URU1": (("uruguay", "uruprim"),),
}


# FootballSquads' early ``prem`` catalogue is Australia's defunct National
# Soccer League, not the later A-League.  It must not inherit AUS1 merely from
# its country or display name.
REVIEWED_UNSUPPORTED: dict[tuple[str, str], str] = {
    ("australia", "prem"): "historical-national-soccer-league-code-not-reviewed",
}


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def reviewed_competition_codes() -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}
    for code, aliases in _ALIASES_BY_CODE.items():
        for alias in aliases:
            if alias in result:
                raise ValueError(f"duplicate reviewed competition alias: {alias[0]}/{alias[1]}")
            result[alias] = code
    overlap = set(result) & set(REVIEWED_UNSUPPORTED)
    if overlap:
        raise ValueError(f"competition aliases are both supported and unsupported: {sorted(overlap)}")
    return result


def _load_source_intake(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("source_clubs"), list):
        raise ValueError(f"{path}: source intake needs a source_clubs list")
    return document, _sha256(raw)


def _selectors(document: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for club in document["source_clubs"]:
        selector = club.get("selector") if isinstance(club, dict) else None
        if not isinstance(selector, dict):
            raise ValueError("source intake club has no selector")
        key = tuple(str(selector.get(field) or "").strip() for field in ("country_catalog", "competition_catalog", "club_name"))
        if not all(key):
            raise ValueError("source intake club selector is incomplete")
        if key in seen:
            raise ValueError(f"source intake duplicates selector {key}")
        seen.add(key)
        rows.append({"country_catalog": key[0], "competition_catalog": key[1], "club_name": key[2]})
    return sorted(rows, key=lambda row: (row["country_catalog"], row["competition_catalog"], row["club_name"]))


def plan_season(
    *, source_intake: Path, output_directory: Path, repo_root: Path = ROOT,
    season_id: str | None = None,
    selected_selector_keys: set[tuple[str, str, str]] | None = None,
    selection_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    document, intake_sha = _load_source_intake(source_intake)
    all_selectors = _selectors(document)
    selectors = all_selectors
    if selected_selector_keys is not None:
        observed = {(row["country_catalog"], row["competition_catalog"], row["club_name"]) for row in all_selectors}
        missing = selected_selector_keys - observed
        if missing:
            raise ValueError(f"opening selection is absent from immutable intake: {sorted(missing)[:5]}")
        selectors = [row for row in all_selectors if (
            row["country_catalog"], row["competition_catalog"], row["club_name"]
        ) in selected_selector_keys]
    season_dir = season_id or source_intake.parent.name
    try:
        season_start_year = int(season_dir[:4])
    except ValueError as exc:
        raise ValueError(f"cannot derive start year from season directory {season_dir!r}") from exc

    codes = reviewed_competition_codes()
    pair_counts = Counter((row["country_catalog"], row["competition_catalog"]) for row in selectors)
    supported: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    routed_pairs: list[dict[str, Any]] = []
    audit_binding = None
    if any(codes.get(pair) in {*calendar_year_policy.CALENDAR_CODE_COUNTRY, "RU1"} for pair in pair_counts):
        audit_binding = calendar_year_policy.verify_audit(repo_root)
    for pair, club_count in sorted(pair_counts.items()):
        if pair in codes:
            code = codes[pair]
            try:
                route = calendar_year_policy.route_provider_year(season_start_year, code, pair[0])
            except calendar_year_policy.RoutingError as exc:
                quarantined.append({
                    "club_count": club_count, "competition_catalog": pair[1],
                    "country_catalog": pair[0], "source_competition_code": code,
                    "reason": str(exc),
                })
                continue
            supported.append({
                "club_count": club_count, "competition_catalog": pair[1],
                "country_catalog": pair[0], "source_competition_code": code,
            })
            if route.provider_season_id != route.target_year:
                routed_pairs.append({**route.document(), "club_count": club_count,
                    "competition_catalog": pair[1]})
        else:
            unsupported.append({
                "club_count": club_count, "competition_catalog": pair[1], "country_catalog": pair[0],
                "reason": REVIEWED_UNSUPPORTED.get(pair, "no-reviewed-static-transfermarkt-code"),
            })

    output_directory.mkdir(parents=True, exist_ok=True)
    map_path = output_directory / "competition-map.json"
    selector_path = output_directory / "source-selectors.json"
    receipt_path = output_directory / "opening-lineups.json"
    cache_path = output_directory / "cache"
    plan_path = output_directory / "plan.json"

    competition_map = {"competitions": [
        {key: row[key] for key in ("competition_catalog", "country_catalog", "source_competition_code")}
        for row in supported
    ], "schema_version": MAP_SCHEMA}
    supported_pairs = {(row["country_catalog"], row["competition_catalog"]) for row in supported}
    capture_selectors = [
        row for row in selectors
        if (row["country_catalog"], row["competition_catalog"]) in supported_pairs
    ]
    selector_capture = {
        # Keep unsupported catalogues out of the executable strict lane.  They
        # remain counted and named in plan.json and therefore cannot disappear
        # behind a successful supported-only capture.
        "clubs": capture_selectors,
        "excluded_unsupported_club_count": len(selectors) - len(capture_selectors),
        "schema_version": SELECTOR_SCHEMA,
        "source_intake_path": str(source_intake.relative_to(repo_root) if source_intake.is_relative_to(repo_root) else source_intake),
        "source_intake_sha256": intake_sha,
    }
    if selection_evidence is not None:
        selector_capture["selection_evidence"] = dict(selection_evidence)
    map_bytes = _canonical_bytes(competition_map)
    selector_bytes = _canonical_bytes(selector_capture)
    map_path.write_bytes(map_bytes)
    selector_path.write_bytes(selector_bytes)

    argv = [
        "python3", "scripts/capture_transfermarkt_opening_lineups_v1.py",
        "--source-capture", str(selector_path), "--competition-map", str(map_path),
        "--season-start-year", str(season_start_year), "--cache-dir", str(cache_path),
        "--output", str(receipt_path), "--strict",
    ]
    plan = {
        "capture": {"argv": argv, "shell_command": shlex.join(argv), "executed": False, "network_fetch_performed": False},
        "competition_map": {"path": str(map_path), "sha256": _sha256(map_bytes)},
        "competition_registry": {
            "policy": "reviewed-static-transfermarkt-codes-only; no online discovery or country-level guessing",
            "unsupported_aliases_are_reported": True,
        },
        "schema_version": PLAN_SCHEMA,
        "season": {"directory": season_dir, "start_year": season_start_year},
        "source_intake": {"path": str(source_intake), "sha256": intake_sha},
        "source_selectors": {"path": str(selector_path), "sha256": _sha256(selector_bytes)},
        "summary": {
            "source_club_count": len(selectors), "supported_club_count": sum(row["club_count"] for row in supported),
            "unselected_source_club_count": len(all_selectors) - len(selectors),
            "supported_competition_count": len(supported), "unsupported_club_count": sum(row["club_count"] for row in unsupported),
            "unsupported_competition_count": len(unsupported),
        },
        "supported_competitions": supported,
        "unsupported_competitions": unsupported,
    }
    if audit_binding is not None:
        plan["summary"].update(calendar_quarantined_club_count=sum(row["club_count"] for row in quarantined),
                               calendar_quarantined_competition_count=len(quarantined))
        plan["calendar_quarantined_competitions"] = quarantined
        plan["calendar_year_routing"] = {
            "audit": audit_binding, "policy_schema": calendar_year_policy.POLICY_SCHEMA,
            "routed_competitions": routed_pairs, "quarantined_competitions": quarantined,
        }
    plan_path.write_bytes(_canonical_bytes(plan))
    return plan


def discover_source_intakes(seasons_root: Path, seasons: Iterable[str] | None = None) -> list[Path]:
    wanted = set(seasons or ())
    paths = sorted(seasons_root.glob("*/source-intake.json"))
    if wanted:
        paths = [path for path in paths if path.parent.name in wanted]
        missing = wanted - {path.parent.name for path in paths}
        if missing:
            raise ValueError(f"seasons lack source-intake.json: {', '.join(sorted(missing))}")
    return paths


def discover_current_source_intakes(
    current_root: Path, seasons: Iterable[str] | None = None,
) -> list[tuple[str, Path]]:
    """Resolve and verify immutable intake revisions through ``current.json``."""

    wanted = set(seasons or ())
    results: list[tuple[str, Path]] = []
    for pointer_path in sorted(current_root.glob("*/current.json")):
        season_id = pointer_path.parent.name
        if wanted and season_id not in wanted:
            continue
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        if pointer.get("schema_version") != "pm99-historical-squad-backfill-current-v1":
            raise ValueError(f"{pointer_path}: unsupported historical-current schema")
        intake = (pointer.get("artifacts") or {}).get("intake") or {}
        relative = str(intake.get("path") or "")
        expected_sha = str(intake.get("sha256") or "")
        path = pointer_path.parent / relative
        if not relative or not path.is_file() or _sha256(path.read_bytes()) != expected_sha:
            raise ValueError(f"{pointer_path}: immutable intake path/hash does not verify")
        results.append((season_id, path))
    if wanted:
        missing = wanted - {season for season, _path in results}
        if missing:
            raise ValueError(f"historical current revisions missing seasons: {', '.join(sorted(missing))}")
    return results


def current_opening_selection(current_directory: Path) -> tuple[set[tuple[str, str, str]], dict[str, Any]]:
    """Select fixed foreign allocations plus every English mode-0 source club."""

    pointer_path = current_directory / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    allocation_ref = (pointer.get("artifacts") or {}).get("allocation") or {}
    allocation_path = current_directory / str(allocation_ref.get("path") or "")
    payload = allocation_path.read_bytes()
    digest = _sha256(payload)
    if digest != allocation_ref.get("sha256"):
        raise ValueError(f"{pointer_path}: immutable allocation path/hash does not verify")
    allocation = json.loads(payload.decode("utf-8"))
    selected: set[tuple[str, str, str]] = set()
    for row in allocation.get("assignments") or []:
        source = row.get("source_selector") or {}
        if source:
            selected.add((str(source.get("country_catalog") or ""), str(source.get("competition_catalog") or ""),
                          str(row.get("club_name") or "")))
    intake_ref = pointer["artifacts"]["intake"]
    intake = json.loads((current_directory / intake_ref["path"]).read_text(encoding="utf-8"))
    for club in intake.get("source_clubs") or []:
        source = club.get("selector") or {}
        if source.get("country_catalog") == "eng" and source.get("competition_catalog") in ENGLISH_MODE0_CATALOGS:
            selected.add((str(source["country_catalog"]), str(source["competition_catalog"]), str(source["club_name"])))
    return selected, {
        "policy": "immutable-fixed-foreign-allocation-plus-english-mode0-v1",
        "allocation_path": str(allocation_path),
        "allocation_sha256": digest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons-root", type=Path, default=ROOT / "seasons")
    parser.add_argument("--output-root", type=Path, default=ROOT / ".local" / "transfermarkt-opening-plans-v1")
    parser.add_argument("--historical-current-root", type=Path,
                        help="plan from hash-verified immutable current.json revisions instead of --seasons-root")
    parser.add_argument("--season", action="append", help="season directory to plan; repeatable (default: every source intake)")
    args = parser.parse_args(argv)
    try:
        if args.historical_current_root is not None:
            revisions = discover_current_source_intakes(args.historical_current_root, args.season)
            plans = []
            for season, path in revisions:
                selected, selection_evidence = current_opening_selection(args.historical_current_root / season)
                plans.append(plan_season(source_intake=path, output_directory=args.output_root / season,
                                         season_id=season, selected_selector_keys=selected,
                                         selection_evidence=selection_evidence))
        else:
            paths = discover_source_intakes(args.seasons_root, args.season)
            plans = [plan_season(source_intake=path, output_directory=args.output_root / path.parent.name) for path in paths]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    summary = {
        "planned_season_count": len(plans),
        "supported_club_count": sum(plan["summary"]["supported_club_count"] for plan in plans),
        "unsupported_club_count": sum(plan["summary"]["unsupported_club_count"] for plan in plans),
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
