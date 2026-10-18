#!/usr/bin/env python3
"""Prepare a season-neutral English mode-0 compiler input.

This module is an authoring gate, not a database release compiler.  It joins a
dated FootballSquads capture (or its lossless source-intake projection), the
runner-proven native English selector map, and four independently replaceable
editorial layers: opening XI, opening manager, historical kit, and ratings.

The result deliberately contains no borrowed JUG or ENT carrier IDs.  It tells
the binary compiler to allocate players only from exclusively owned selected
mode-0 ``dd6361`` records, appending from an eligible mode-0 template when the
exclusive pool is exhausted.  Borrowing a player referenced by a foreign or
unselected club is forbidden.  The existing 2015 compiler already proved that
mechanism; this file makes its season inputs deterministic and reviewable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "pm99-english-fixed-carrier-authoring-v1"
COMPILER_SCHEMA = "pm99-english-mode0-compiler-input-v1"
LAYER_SCHEMAS = {
    "openings": "pm99-season-opening-layer-v1",
    "managers": "pm99-season-manager-layer-v1",
    "kits": "pm99-season-kit-layer-v1",
    "ratings": "pm99-season-rating-layer-v1",
}
SOURCE_SCHEMAS = {
    "pm99-footballsquads-season-capture-v1",
    "pm99-season-source-intake-v1",
    "pm99-opening-squad-preallocation-v1",
}
DIVISIONS = ("Premier League", "Championship", "League One", "League Two")
COMPETITION_DIVISION = {
    "faprem": "Premier League",
    "engprem": "Premier League",
    "prem": "Premier League",
    "premier": "Premier League",
    "champ": "Championship",
    "championship": "Championship",
    "flcham": "Championship",
    "d1": "Championship",
    "lge1": "League One",
    "league1": "League One",
    "flone": "League One",
    "d2": "League One",
    "lge2": "League Two",
    "league2": "League Two",
    "fltwo": "League Two",
    "d3": "League Two",
}
PANEL_DIVISION = dict(zip(("division_01", "division_02", "division_03", "division_04"), DIVISIONS, strict=True))
NATIVE_DIVISION_CARRIERS = {
    "Premier League": (301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312, 313, 314, 315, 316, 317, 319, 320, 333),
    "Championship": (318, 321, 322, 325, 326, 327, 328, 329, 330, 331, 332, 334, 336, 337, 339, 340, 342, 343, 344, 348, 351, 353, 363, 365),
    "League One": (323, 335, 338, 341, 345, 346, 349, 350, 352, 354, 355, 356, 357, 360, 364, 366, 367, 368, 375, 379, 384, 386, 392, 3311),
    "League Two": (324, 347, 358, 359, 361, 362, 369, 370, 371, 372, 373, 374, 376, 378, 380, 382, 383, 385, 387, 388, 389, 390, 391, 3306),
}
RATING_FIELDS = (
    "speed", "stamina", "aggression", "quality", "heading", "dribbling",
    "passing", "shooting", "tackling", "handling",
)
SQUAD_SNAPSHOT_POLICIES = {
    "at-club-on-first-league-fixture-date-exclude-later-arrivals",
    "opening-window-through-august-31-exclude-september-and-later-arrivals",
    "opening-window-through-august-31-exited-club-prior-season-squad-fallback",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EnglishAuthoringError(ValueError):
    """An input is structurally unsafe, rather than merely incomplete."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def document_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char.casefold() for char in text if char.isalnum() and not unicodedata.combining(char))


def _season_label(document: Mapping[str, Any]) -> str:
    value = document.get("season")
    label = value.get("label") if isinstance(value, Mapping) else value
    if not isinstance(label, str) or not re.fullmatch(r"(?:19|20)\d{2}/\d{2}", label):
        raise EnglishAuthoringError("every input must declare a YYYY/YY season")
    return label


def _source_clubs(source: Mapping[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    schema = source.get("schema_version")
    if schema not in SOURCE_SCHEMAS:
        raise EnglishAuthoringError(f"source schema must be one of {sorted(SOURCE_SCHEMAS)}")
    season = _season_label(source)
    output: list[dict[str, Any]] = []
    if schema == "pm99-footballsquads-season-capture-v1":
        rows = source.get("clubs")
        if not isinstance(rows, list):
            raise EnglishAuthoringError("source clubs must be a list")
        for row in rows:
            if not isinstance(row, Mapping) or str(row.get("country_catalog")) != "eng":
                continue
            division = COMPETITION_DIVISION.get(str(row.get("competition_catalog")))
            if division is None:
                continue
            players = row.get("players")
            if not isinstance(players, list):
                raise EnglishAuthoringError("source club players must be a list")
            output.append({
                "club": str(row.get("club_name") or ""), "division": division,
                "source_path": str(row.get("source_path") or ""),
                "source_sha256": str(row.get("source_sha256") or ""),
                "players": [dict(player) for player in players if isinstance(player, Mapping)],
            })
    else:
        rows = source.get("source_clubs")
        if not isinstance(rows, list):
            raise EnglishAuthoringError("source intake source_clubs must be a list")
        for row in rows:
            if not isinstance(row, Mapping):
                raise EnglishAuthoringError("source intake club rows must be objects")
            selector = row.get("selector")
            if not isinstance(selector, Mapping) or str(selector.get("country_catalog")) != "eng":
                continue
            division = COMPETITION_DIVISION.get(str(selector.get("competition_catalog")))
            if division is None:
                continue
            players = row.get("players")
            if not isinstance(players, list):
                raise EnglishAuthoringError("source intake club players must be a list")
            facts = []
            preallocated_xi: list[tuple[int, str]] = []
            for player in players:
                if not isinstance(player, Mapping) or not isinstance(player.get("facts"), Mapping):
                    raise EnglishAuthoringError("source intake player has no facts row")
                player_facts = dict(player["facts"])
                facts.append(player_facts)
                opening_order = player.get("opening_xi_order")
                if isinstance(opening_order, int) and not isinstance(opening_order, bool):
                    preallocated_xi.append((opening_order, str(player_facts.get("name") or "")))
            preallocated_xi.sort()
            canonical_xi = [name for _order, name in preallocated_xi]
            if schema == "pm99-opening-squad-preallocation-v1":
                if row.get("opening_xi_complete") is True and (
                    [order for order, _name in preallocated_xi] != list(range(1, 12))
                    or len({_normalise(name) for name in canonical_xi}) != 11
                ):
                    raise EnglishAuthoringError(
                        "complete opening-squad preallocation must expose eleven ordered unique XI identities"
                    )
                if row.get("opening_xi_complete") is not True:
                    canonical_xi = []
            output.append({
                "club": str(selector.get("club_name") or ""), "division": division,
                "source_path": str(selector.get("source_path") or ""),
                "source_sha256": str(selector.get("source_sha256") or ""), "players": facts,
                "preallocated_first_xi": canonical_xi,
            })
    keys = [(_normalise(row["club"]), row["division"]) for row in output]
    if any(not key[0] for key in keys) or len(keys) != len(set(keys)):
        raise EnglishAuthoringError("English source clubs must have unique non-empty identities per division")
    return season, output


def _slots(selector_map: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if selector_map.get("schema_version") != "pm99-native-english-selector-eq-map-v1":
        raise EnglishAuthoringError("selector map schema is unsupported")
    visible_by_division: dict[str, dict[int, dict[str, Any]]] = {}
    seen: set[int] = set()
    for panel in selector_map.get("divisions") or []:
        if not isinstance(panel, Mapping):
            raise EnglishAuthoringError("selector panels must be objects")
        division = PANEL_DIVISION.get(str(panel.get("division_key")))
        if division is None:
            continue
        teams = panel.get("teams")
        if not isinstance(teams, list) or len(teams) != 20:
            raise EnglishAuthoringError(f"{division} must expose exactly 20 runner-proven selector slots")
        slots: dict[int, dict[str, Any]] = {}
        for team in teams:
            if not isinstance(team, Mapping) or not isinstance(team.get("eq_record_id"), int):
                raise EnglishAuthoringError("selector team row is malformed")
            carrier = int(team["eq_record_id"])
            if carrier in seen or int(team.get("mode_byte", -1)) != 0:
                raise EnglishAuthoringError("English selector carriers must be unique mode-0 records")
            seen.add(carrier)
            slots[carrier] = {
                "carrier_id": carrier,
                "native_name": str(team.get("canonical_team_name") or team.get("eq_short_name") or ""),
                "native_panel": str(panel["division_key"]),
                "native_row_index": int(team.get("row_index") or 0),
                "team_select_x": int(team.get("team_select_x") or 0),
                "team_select_y": int(team.get("team_select_y") or 0),
            }
        visible_by_division[division] = slots
    if set(visible_by_division) != set(DIVISIONS):
        raise EnglishAuthoringError("selector map does not cover the four English panels")
    # The picker exposes only 80 cells, but runtime league-table controls prove
    # the complete native membership to be the sets above.  The membership is
    # deliberately not inferred from numeric ranges: carrier 333 is Premier
    # League, for example, and 3306/3311 are genuine native English carriers.
    # Every one of the 92 records must be rewritten; the twelve non-picker
    # carriers are not spare or safe to preserve.
    result: dict[str, list[dict[str, Any]]] = {}
    for division in DIVISIONS:
        rows = []
        for carrier in NATIVE_DIVISION_CARRIERS[division]:
            visible = visible_by_division[division].get(carrier)
            rows.append(visible or {
                "carrier_id": carrier, "native_name": "", "native_panel": None,
                "native_row_index": None, "team_select_x": None, "team_select_y": None,
            })
        result[division] = rows
    proven = {carrier for carriers in NATIVE_DIVISION_CARRIERS.values() for carrier in carriers}
    if not seen <= proven:
        raise EnglishAuthoringError("selector map contains a carrier outside the proven native English membership")
    return result


def _layer_index(layer: Mapping[str, Any], kind: str, season: str) -> dict[str, dict[str, Any]]:
    if layer.get("schema_version") != LAYER_SCHEMAS[kind] or _season_label(layer) != season:
        raise EnglishAuthoringError(f"{kind} layer schema or season mismatch")
    key = "rows" if kind in {"managers", "ratings"} else "clubs"
    rows = layer.get(key)
    if not isinstance(rows, list):
        raise EnglishAuthoringError(f"{kind} layer {key} must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("club"), str):
            raise EnglishAuthoringError(f"{kind} layer row is malformed")
        identity = _normalise(row["club"])
        if not identity or identity in result:
            raise EnglishAuthoringError(f"{kind} layer contains a duplicate club")
        result[identity] = dict(row)
    return result


def _assign(clubs: list[dict[str, Any]], slots: dict[str, list[dict[str, Any]]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    assignments: list[dict[str, Any]] = []
    omissions: list[dict[str, Any]] = []
    for division in DIVISIONS:
        candidates = sorted((row for row in clubs if row["division"] == division), key=lambda row: (_normalise(row["club"]), row["source_path"]))
        by_name = {_normalise(row["club"]): row for row in candidates}
        used: set[str] = set()
        free = []
        for slot in slots[division]:
            match = by_name.get(_normalise(slot["native_name"]))
            if match is None or _normalise(match["club"]) in used:
                free.append(slot)
                continue
            used.add(_normalise(match["club"]))
            assignments.append({**slot, **match, "assignment_method": "continuing-club-normalized-identity"})
        remaining = [row for row in candidates if _normalise(row["club"]) not in used]
        for slot, club in zip(free, remaining, strict=False):
            used.add(_normalise(club["club"]))
            assignments.append({**slot, **club, "assignment_method": "same-division-canonical-source-order"})
        for club in remaining[len(free):]:
            omissions.append({"club": club["club"], "division": division, "reason": "source-club-exceeds-native-panel-capacity"})
        for slot in free[len(remaining):]:
            omissions.append({"carrier_id": slot["carrier_id"], "division": division, "reason": "native-panel-slot-has-no-target-season-club"})
    assignments.sort(key=lambda row: int(row["carrier_id"]))
    omissions.sort(key=lambda row: (row["division"], str(row.get("club", "")), int(row.get("carrier_id", 0))))
    return assignments, omissions


def _rating_index(row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    players = row.get("players")
    if not isinstance(players, list):
        return {}
    result = {}
    for player in players:
        if isinstance(player, Mapping) and isinstance(player.get("player"), str):
            result[_normalise(player["player"])] = dict(player)
    return result


def build_authoring(
    *, source: Mapping[str, Any], selector_map: Mapping[str, Any], openings: Mapping[str, Any],
    managers: Mapping[str, Any], kits: Mapping[str, Any], ratings: Mapping[str, Any], squad_limit: int = 25,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not 11 <= squad_limit <= 25:
        raise EnglishAuthoringError("squad_limit must be between 11 and 25")
    season, clubs = _source_clubs(source)
    selector_slots = _slots(selector_map)
    layers = {
        "openings": _layer_index(openings, "openings", season),
        "managers": _layer_index(managers, "managers", season),
        "kits": _layer_index(kits, "kits", season),
        "ratings": _layer_index(ratings, "ratings", season),
    }
    assignments, omissions = _assign(clubs, selector_slots)
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    authored: list[dict[str, Any]] = []
    for club in assignments:
        name = club["club"]
        club_key = _normalise(name)
        for kind in ("openings", "managers", "kits", "ratings"):
            if club_key not in layers[kind]:
                blockers.append({"code": f"missing-{kind[:-1]}-layer-row", "club": name, "division": club["division"]})
        opening = dict(layers["openings"].get(club_key, {}))
        xi = opening.get("first_xi")
        preallocated_xi = club.get("preallocated_first_xi")
        opening_squad_value = opening.get("opening_squad")
        if (
            isinstance(preallocated_xi, list)
            and len(preallocated_xi) == 11
            and isinstance(xi, list)
            and len(xi) == 11
            and isinstance(opening_squad_value, list)
            and len(opening_squad_value) >= 11
            and [_normalise(value) for value in opening_squad_value[:11]]
            == [_normalise(value) for value in xi]
        ):
            # The preallocation has already joined each lineup source player
            # ID to one dated squad/profile row.  Preserve that stronger
            # identity edge instead of re-matching report display spellings.
            xi = list(preallocated_xi)
            opening["first_xi"] = list(preallocated_xi)
            opening["opening_squad"] = list(preallocated_xi) + list(opening_squad_value[11:])
        if not isinstance(xi, list) or len(xi) != 11 or len({_normalise(value) for value in xi}) != 11:
            blockers.append({"code": "opening-xi-not-eleven-unique-players", "club": name})
            xi = []
        opening_squad = opening.get("opening_squad")
        if (
            not isinstance(opening_squad, list)
            or len(opening_squad) < 11
            or len({_normalise(value) for value in opening_squad}) != len(opening_squad)
            or any(not isinstance(value, str) or not _normalise(value) for value in opening_squad)
        ):
            blockers.append({"code": "opening-date-squad-not-at-least-eleven-unique-players", "club": name})
            opening_squad = []
        if opening.get("squad_snapshot_policy") not in SQUAD_SNAPSHOT_POLICIES:
            blockers.append({"code": "opening-date-squad-policy-not-declared", "club": name})
        formation = str(opening.get("formation") or "")
        if not re.fullmatch(r"[1-9](?:-[1-9])+", formation) or sum(int(value) for value in formation.split("-") if value) != 10:
            blockers.append({"code": "opening-formation-missing-or-invalid", "club": name})
        if opening.get("formation_method") not in {"source", "deterministic-inference-from-sourced-xi"}:
            blockers.append({"code": "opening-formation-method-not-source-or-deterministic-inference", "club": name})
        source_players = list(club["players"])
        by_player: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for player in source_players:
            by_player[_normalise(player.get("name"))].append(player)
        missing_xi = [value for value in xi if len(by_player.get(_normalise(value), [])) != 1]
        if missing_xi:
            blockers.append({"code": "opening-xi-not-uniquely-reconciled-to-opening-squad", "club": name, "players": missing_xi})
        missing_opening_squad = [value for value in opening_squad if len(by_player.get(_normalise(value), [])) != 1]
        if missing_opening_squad:
            blockers.append({"code": "opening-squad-not-uniquely-reconciled-to-source", "club": name, "players": missing_opening_squad})
        xi_keys = {_normalise(value) for value in xi}
        if opening_squad and not xi_keys <= {_normalise(value) for value in opening_squad}:
            blockers.append({"code": "opening-xi-not-contained-in-opening-date-squad", "club": name})
        ordered: list[dict[str, Any]] = []
        used_players: set[int] = set()
        for value in xi:
            matches = by_player.get(_normalise(value), [])
            if len(matches) == 1:
                ordered.append(matches[0]); used_players.add(id(matches[0]))
        for value in opening_squad:
            matches = by_player.get(_normalise(value), [])
            if len(matches) == 1 and id(matches[0]) not in used_players:
                ordered.append(matches[0]); used_players.add(id(matches[0]))
        selected = ordered[:squad_limit]
        if len(selected) < 11:
            blockers.append({"code": "opening-squad-below-eleven-player-compiler-minimum", "club": name, "available": len(selected)})
        rating_index = _rating_index(layers["ratings"].get(club_key, {}))
        player_rows = []
        for order, player in enumerate(selected, start=1):
            player_name = str(player.get("name") or "")
            rating = rating_index.get(_normalise(player_name))
            values = rating.get("ratings") if rating else None
            if not isinstance(values, Mapping) or set(values) != set(RATING_FIELDS) or any(not isinstance(values[field], int) or isinstance(values[field], bool) or not 0 <= values[field] <= 100 for field in RATING_FIELDS):
                blockers.append({"code": "missing-or-invalid-player-ratings", "club": name, "player": player_name})
                values = None
            player_rows.append({
                "source_order": order, "opening_xi": order <= 11 and bool(xi),
                "facts": player, "ratings": dict(values) if values is not None else None,
                "unresolved_secondary_facts": sorted(
                    field for field in ("birth_date", "nationality", "height_cm", "weight_kg", "shirt_number")
                    if player.get(field) is None
                ),
                "portrait": {"status": "no-image", "reason": "no approved era-specific portrait supplied"},
            })
        manager = layers["managers"].get(club_key)
        if manager is not None and (not str(manager.get("manager_name") or "").strip() or not str(manager.get("source_url") or "").strip()):
            blockers.append({"code": "opening-manager-name-or-source-missing", "club": name})
        kit = layers["kits"].get(club_key)
        accepted_kit_policies = {
            "historical-target-season",
            "target-season-url-with-nearest-source-backed-style-provisional",
            "exited-club-prior-season-source-backed-style-fallback",
        }
        if kit is not None and (kit.get("policy") not in accepted_kit_policies or not str(kit.get("source_url") or "").strip()):
            blockers.append({"code": "historical-target-season-kit-source-missing", "club": name})
        elif kit is not None and kit.get("policy") != "historical-target-season":
            warnings.append({
                "code": "target-season-kit-url-with-provisional-style-carry-forward",
                "club": name,
                "source_url": kit.get("source_url"),
                "style_source_season": kit.get("style_source_season"),
            })
        if opening and (not str(opening.get("fixture_date") or "").strip() or not str(opening.get("source_url") or "").strip()):
            blockers.append({"code": "opening-fixture-date-or-source-missing", "club": name})
        authored.append({
            **{key: club[key] for key in ("carrier_id", "native_panel", "native_row_index", "team_select_x", "team_select_y", "club", "division", "assignment_method", "source_path", "source_sha256")},
            "opening": dict(opening) if opening else None, "manager": dict(manager) if manager else None,
            "kit": dict(kit) if kit else None, "players": player_rows,
        })
    blocker_keys = {json.dumps(row, ensure_ascii=False, sort_keys=True) for row in blockers}
    blockers = [json.loads(value) for value in sorted(blocker_keys)]
    audit = {
        "schema_version": SCHEMA, "season": season,
        "input_sha256": {"source": document_sha256(source), "selector_map": document_sha256(selector_map), **{kind: document_sha256(document) for kind, document in (("openings", openings), ("managers", managers), ("kits", kits), ("ratings", ratings))}},
        "policies": {
            "squad_snapshot": "first-league-fixture-or-opening-window-through-august-31; exclude later arrivals",
            "squad_selection": "sourced-first-xi-then-source-order-capacity-fitting-opening-squad",
            "preallocation_identity": "prefer-exact-ordered-source-player-id-join-for-complete-preallocated-xi",
            "formation": "sourced-or-deterministically-inferred-from-sourced-first-xi",
            "manager": "historical-opening-date-source-required-no-native-fallback",
            "kit": "historical-target-season-required-for-every-selected-club",
            "portrait": "approved-era-image-or-no-image",
            "secondary_facts": "source-value-or-logged-deterministic-default-or-nearby-season-evidence",
            "player_carriers": "exclusive-selected-mode0-dd6361-or-append-from-exclusive-mode0-template-never-borrow-shared",
        },
        "coverage": {"source_english_clubs": len(clubs), "selected_clubs": len(assignments), "omitted_rows": len(omissions), "blockers": len(blockers)},
        "omissions": omissions, "blockers": blockers,
        "warnings": sorted(warnings, key=lambda row: (str(row.get("club")), str(row.get("code")))),
        "status": "compiler-input-ready" if not blockers and len(assignments) == 92 else "blocked",
    }
    compiler_input = None
    if audit["status"] == "compiler-input-ready":
        compiler_input = {
            "schema_version": COMPILER_SCHEMA, "season": season,
            "authoring_audit_sha256": document_sha256(audit),
            "binary_preflight": {
                "required": True,
                "source_files": ["JUG98030.FDI", "EQ98030.FDI", "ENT98030.FDI", "TEXTOS.PKF"],
                "rules": [
                    "all-selected-team-carriers-are-mode0",
                    "every-reused-player-carrier-owned-only-by-selected-mode0-clubs",
                    "append-only-from-parser-valid-exclusive-dd6361-template",
                    "one-writable-ent-manager-record-per-selected-club",
                    "reopen-and-byte-scope-audit-all-written-fdi-files",
                ],
            },
            "clubs": authored,
        }
    return audit, compiler_input


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EnglishAuthoringError(f"input must be a JSON object: {path}")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--selector-map", required=True, type=Path)
    parser.add_argument("--openings", required=True, type=Path)
    parser.add_argument("--managers", required=True, type=Path)
    parser.add_argument("--kits", required=True, type=Path)
    parser.add_argument("--ratings", required=True, type=Path)
    parser.add_argument("--squad-limit", type=int, default=25)
    parser.add_argument("--output-audit", required=True, type=Path)
    parser.add_argument("--output-compiler-input", type=Path)
    args = parser.parse_args(argv)
    audit, compiler_input = build_authoring(
        source=_read(args.source), selector_map=_read(args.selector_map), openings=_read(args.openings),
        managers=_read(args.managers), kits=_read(args.kits), ratings=_read(args.ratings), squad_limit=args.squad_limit,
    )
    args.output_audit.parent.mkdir(parents=True, exist_ok=True)
    args.output_audit.write_bytes(canonical_json_bytes(audit))
    if args.output_compiler_input is not None:
        if compiler_input is None:
            raise SystemExit("authoring is blocked; compiler input was not written")
        args.output_compiler_input.parent.mkdir(parents=True, exist_ok=True)
        args.output_compiler_input.write_bytes(canonical_json_bytes(compiler_input))
    print(json.dumps(audit["coverage"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
