"""Tabular view models for the local PM99 season recipe workbench.

The browser owns file access and amendment staging.  This module deliberately
only turns an already allowlisted season-package document into small, paged
table payloads.  Keeping that boundary means the web page cannot choose an
arbitrary file or JSON path to edit.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


TAB_ORDER = ("players", "managers", "clubs", "kits")

# The packages use ISO 3166-1 alpha-3 values.  Include the common PM99-era
# countries even when a particular season has no player from one of them, and
# union these values with the selected package's observed values below.
NATIONALITY_CHOICES = frozenset("""
AFG ALB ALG AND ANG ANT ARG ARM ARU AUS AUT AZE BAH BAN BAR BEL BEN BER BHU BIH BIZ
BLR BOL BOT BRA BRU BUL BFA BDI CAM CAN CPV CAY CAF CHA CHI CHN COL COM CON COD CRC
CIV CRO CUB CYP CZE DEN DJI DMA DOM ECU EGY SLV ENG EQG ERI EST ETH FRO FIJ FIN FRA
GAB GAM GEO GER GHA GIB GRE GRN GUA GUI GNB GUY HAI HON HKG HUN ISL IND INA IRN IRQ
IRL ISR ITA JAM JPN JOR KAZ KEN KOS KUW KGZ LAO LAT LBN LBR LBY LIE LTU LUX MAC MAD
MAW MAS MLI MLT MTQ MRT MRI MEX MDA MNG MNE MSR MAR MOZ MYA NAM NEP NED NCL NZL NCA
NIG NIR MKD NOR OMA PAK PAL PAN PNG PAR PER PHI POL POR PRI QAT ROU RUS RWA SKN LCA
VIN SMR KSA SCO SEN SRB SEY SLE SIN SVK SVN SOL SOM RSA KOR SSD ESP SRI SDN SUR SWE
SUI SYR TAH TJK TAN THA TLS TOG TGA TRI TUN TUR TKM UGA UKR UAE URU USA UZB VAN VEN
VIE WAL YEM ZAM ZIM
""".split())
POSITION_CHOICES = ("G", "D", "M", "F")


def pointer_part(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def pointer(*parts: object) -> str:
    return "/" + "/".join(pointer_part(part) for part in parts)


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _display(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, Mapping):
        policy = value.get("policy")
        if isinstance(policy, str):
            return f"Fallback: {policy}"
        return "Structured value"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _cell(
    value: Any, *, json_pointer: str | None = None, kind: str = "text",
    choices: str | None = None, minimum: int | None = None, maximum: int | None = None,
    editable: bool = True,
) -> dict[str, Any]:
    can_edit = editable and json_pointer is not None and _scalar(value)
    cell: dict[str, Any] = {
        "display": _display(value),
        "value": value if _scalar(value) else None,
        "editable": can_edit,
    }
    if can_edit:
        cell.update({"pointer": json_pointer, "kind": kind})
        if choices is not None:
            cell["choices"] = choices
        if minimum is not None:
            cell["minimum"] = minimum
        if maximum is not None:
            cell["maximum"] = maximum
    return cell


def _read(mapping: Mapping[str, Any], key: str) -> Any:
    return mapping.get(key) if key in mapping else None


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _rating_keys(players: Sequence[Mapping[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for player in players:
        ratings = player.get("ratings")
        if isinstance(ratings, Mapping) and isinstance(ratings.get("values"), Mapping):
            keys.update(key for key, item in ratings["values"].items() if isinstance(key, str) and _scalar(item))
    return sorted(keys)


def _choices(players: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, str]]]:
    nationalities = set(NATIONALITY_CHOICES)
    positions = set(POSITION_CHOICES)
    for player in players:
        facts = player.get("facts")
        if not isinstance(facts, Mapping):
            continue
        nationality = facts.get("nationality")
        position = facts.get("primary_position")
        if isinstance(nationality, str) and nationality.strip():
            nationalities.add(nationality.strip().upper())
        if isinstance(position, str) and position.strip():
            positions.add(position.strip().upper())
    return {
        "nationality": [{"value": item, "label": item} for item in sorted(nationalities)],
        "position": [{"value": item, "label": item} for item in sorted(positions)],
    }


def metadata(source: Mapping[str, Any], *, kit_count: int = 0) -> dict[str, Any]:
    players = _rows(source.get("players"))
    managers = _rows(source.get("managers"))
    clubs = _rows(source.get("clubs"))
    ratings = _rating_keys(players)
    return {
        "tabs": [
            {"id": "players", "label": "Players", "count": len(players)},
            {"id": "managers", "label": "Managers", "count": len(managers)},
            {"id": "clubs", "label": "Clubs", "count": len(clubs)},
            {"id": "kits", "label": "Kit BMPs", "count": kit_count},
        ],
        "choices": _choices(players),
        "rating_keys": ratings,
    }


def _player_models(
    source: Mapping[str, Any], *, rating_keys: Sequence[str],
    portrait_assets: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    players = _rows(source.get("players"))
    clubs = {str(row.get("id")): row for row in _rows(source.get("clubs"))}
    columns: list[dict[str, str]] = [
        {"id": "name", "label": "Player name"},
        {"id": "portrait", "label": "Portrait BMP"},
        {"id": "club", "label": "Club"},
        {"id": "birth_date", "label": "DOB"},
        {"id": "nationality", "label": "Nationality"},
        {"id": "position", "label": "Position"},
        {"id": "shirt_number", "label": "Shirt #"},
        {"id": "height_cm", "label": "Height cm"},
        {"id": "weight_kg", "label": "Weight kg"},
    ] + [{"id": f"rating:{key}", "label": key.replace("_", " ").title()} for key in rating_keys]
    rows: list[dict[str, Any]] = []
    portrait_assets = portrait_assets or {}
    for index, player in enumerate(players):
        facts = player.get("facts") if isinstance(player.get("facts"), Mapping) else {}
        ratings = player.get("ratings") if isinstance(player.get("ratings"), Mapping) else {}
        values = ratings.get("values") if isinstance(ratings.get("values"), Mapping) else {}
        club = clubs.get(str(player.get("club_id")))
        club_name = club.get("name") if isinstance(club, Mapping) else player.get("club_id")
        cells: dict[str, Any] = {
            "name": _cell(_read(player, "name"), json_pointer=pointer("players", index, "name")),
            # A portrait may only be linked when a separate build receipt
            # explicitly binds this source-player id to a hash-locked BMP.
            # The file name or carrier id alone is deliberately insufficient.
            "portrait": {
                "display": "View BMP",
                "editable": False,
                "links": [dict(portrait_assets[str(player.get("id"))])],
            } if str(player.get("id")) in portrait_assets else {
                "display": "No verified portrait", "editable": False,
            },
            "club": _cell(club_name, editable=False),
        }
        for key, label, kind, minimum, maximum, choices in (
            ("birth_date", "birth_date", "date", None, None, None),
            ("nationality", "nationality", "select", None, None, "nationality"),
            ("primary_position", "position", "select", None, None, "position"),
            ("shirt_number", "shirt_number", "number", 0, 99, None),
            ("height_cm", "height_cm", "number", 0, 250, None),
            ("weight_kg", "weight_kg", "number", 0, 250, None),
        ):
            cells[label] = _cell(
                _read(facts, key), json_pointer=pointer("players", index, "facts", key), kind=kind,
                choices=choices, minimum=minimum, maximum=maximum,
            ) if key in facts else _cell(None, editable=False)
        for key in rating_keys:
            cells[f"rating:{key}"] = _cell(
                _read(values, key), json_pointer=pointer("players", index, "ratings", "values", key),
                kind="number", minimum=0, maximum=100,
            ) if key in values else _cell(None, editable=False)
        rows.append({
            "id": str(player.get("id") or f"player-{index + 1}"),
            "search": " ".join(str(part) for part in (player.get("name"), player.get("source_name"), club_name) if part),
            "cells": cells,
        })
    return rows, columns


def _manager_models(source: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    managers = _rows(source.get("managers"))
    clubs = _rows(source.get("clubs"))
    club_for_manager = {
        str(club.get("manager_id")): club.get("name")
        for club in clubs if club.get("manager_id") is not None
    }
    columns = [
        {"id": "name", "label": "Manager name"},
        {"id": "club", "label": "Club"},
        {"id": "carrier", "label": "Carrier"},
        {"id": "policy", "label": "Assignment policy"},
    ]
    rows = []
    for index, manager in enumerate(managers):
        manager_id = str(manager.get("id"))
        rows.append({
            "id": manager_id or f"manager-{index + 1}",
            "search": " ".join(str(part) for part in (manager.get("name"), club_for_manager.get(manager_id)) if part),
            "cells": {
                "name": _cell(_read(manager, "name"), json_pointer=pointer("managers", index, "name")),
                "club": _cell(club_for_manager.get(manager_id), editable=False),
                "carrier": _cell(_read(manager, "carrier_id"), editable=False),
                "policy": _cell(_read(manager, "policy"), editable=False),
            },
        })
    return rows, columns


def _club_models(source: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, str]]]:
    clubs = _rows(source.get("clubs"))
    managers = _rows(source.get("managers"))
    manager_choices = [
        {"value": str(row.get("id")), "label": str(row.get("name") or row.get("id"))}
        for row in managers if row.get("id") is not None
    ]
    manager_names = {item["value"]: item["label"] for item in manager_choices}
    columns = [
        {"id": "name", "label": "Club name"},
        {"id": "full_name", "label": "Full name"},
        {"id": "division", "label": "Division"},
        {"id": "ground", "label": "Ground"},
        {"id": "manager", "label": "Manager"},
        {"id": "carrier", "label": "Carrier"},
    ]
    rows = []
    for index, club in enumerate(clubs):
        manager_id = _read(club, "manager_id")
        rows.append({
            "id": str(club.get("id") or f"club-{index + 1}"),
            "search": " ".join(str(part) for part in (club.get("name"), club.get("full_name"), club.get("ground_name"), manager_names.get(str(manager_id))) if part),
            "cells": {
                "name": _cell(_read(club, "name"), json_pointer=pointer("clubs", index, "name")),
                "full_name": _cell(_read(club, "full_name"), json_pointer=pointer("clubs", index, "full_name")) if "full_name" in club else _cell(None, editable=False),
                "division": _cell(_read(club, "division"), json_pointer=pointer("clubs", index, "division")) if _scalar(_read(club, "division")) else _cell(_read(club, "division"), editable=False),
                "ground": _cell(_read(club, "ground_name"), json_pointer=pointer("clubs", index, "ground_name")) if "ground_name" in club else _cell(None, editable=False),
                "manager": _cell(manager_id, json_pointer=pointer("clubs", index, "manager_id"), kind="select", choices="manager") if manager_id is not None else _cell(None, editable=False),
                "carrier": _cell(_read(club, "carrier_id"), editable=False),
            },
        })
        rows[-1]["cells"]["manager"]["display"] = manager_names.get(str(manager_id), _display(manager_id))
    return rows, columns, manager_choices


def _kit_models(
    source: Mapping[str, Any], kit_assets: Mapping[int, Sequence[Mapping[str, str]]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    clubs = _rows(source.get("clubs"))
    columns = [
        {"id": "club", "label": "Club"},
        {"id": "carrier", "label": "Carrier"},
        {"id": "bitmaps", "label": "Linked BMPs"},
    ]
    rows = []
    for index, club in enumerate(clubs):
        carrier = club.get("carrier_id")
        assets = list(kit_assets.get(carrier, [])) if isinstance(carrier, int) else []
        if not assets:
            continue
        rows.append({
            "id": str(club.get("id") or f"kit-{index + 1}"),
            "search": str(club.get("name") or ""),
            "cells": {
                "club": _cell(_read(club, "name"), editable=False),
                "carrier": _cell(carrier, editable=False),
                "bitmaps": {"display": f"{len(assets)} linked BMPs", "editable": False, "links": list(assets)},
            },
        })
    return rows, columns


def tab_payload(
    source: Mapping[str, Any], *, tab: str, query: str = "", offset: int = 0, limit: int = 200,
    kit_assets: Mapping[int, Sequence[Mapping[str, str]]] | None = None,
    portrait_assets: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Return one page of the requested safe tab model."""

    if tab not in TAB_ORDER:
        raise ValueError("unknown spreadsheet tab")
    players = _rows(source.get("players"))
    rating_keys = _rating_keys(players)
    if tab == "players":
        rows, columns = _player_models(
            source, rating_keys=rating_keys, portrait_assets=portrait_assets,
        )
    elif tab == "managers":
        rows, columns = _manager_models(source)
    elif tab == "clubs":
        rows, columns, _unused = _club_models(source)
    else:
        rows, columns = _kit_models(source, kit_assets or {})
    lowered = query.strip().casefold()
    if lowered:
        rows = [row for row in rows if lowered in row["search"].casefold()]
    total = len(rows)
    start = max(offset, 0)
    page = rows[start:start + max(1, min(limit, 500))]
    return {"tab": tab, "columns": columns, "rows": page, "total": total, "offset": start, "limit": limit}


def package_choices(source: Mapping[str, Any], *, kit_count: int = 0) -> dict[str, Any]:
    """Return global controlled-value choices and table counts for a package."""

    result = metadata(source, kit_count=kit_count)
    _club_rows, _columns, manager_choices = _club_models(source)
    result["choices"]["manager"] = manager_choices
    return result
