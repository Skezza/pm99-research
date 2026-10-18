#!/usr/bin/env python3
"""Repair recipe DOB plausibility faults without concealing their provenance.

There are three bounded outcomes for a dated player row that is impossible at
the season snapshot:

* replace a stale 2015 fallback with an unused player from the pinned
  target-season capture for the *same exact club*;
* restore the parser-read base record where no target-season squad capture
  exists for that fixed carrier; or
* apply one explicit, cited correction for an ambiguous historic source date.

Raw captures are never rewritten.  Every affected row is recorded in the
receipt, and the live game receives only the corresponding JUG player-record
payloads from a clean compiler materialisation.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import sys
import tempfile
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import apply_opening_lineup_position_repairs_v1 as jug_refresh  # noqa: E402
from scripts import reconcile_mode1_roster_base_v1 as base_rows  # noqa: E402
from scripts import prepare_provisional_compile_package_v1 as preparation  # noqa: E402
from scripts import season_package_display_alias_repair_v1 as aliases  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_source_package_builder_v1 as source_builder  # noqa: E402


SCHEMA = "pm99-season-direct-birth-date-plausibility-repair-v1"
CORRECTIONS_SCHEMA = "pm99-season-birth-date-corrections-v1"
CORRECTIONS = ROOT / "scripts/data/season_birth_date_corrections_v1.json"
PRESERVATION_ARTIFACT_ID = "world-mode1-runtime-contract"
PRESERVATION_SOURCE_ID = "baseline-runtime-contract"


class BirthDateRepairError(ValueError):
    """A source-backed date repair cannot safely remain within its declared scope."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalise(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(char.casefold() for char in text if char.isalnum())


def _snapshot(season: Mapping[str, Any]) -> tuple[str, dt.date]:
    start, end = season.get("start_year"), season.get("end_year")
    if not isinstance(start, int) or not isinstance(end, int) or end != start + 1:
        raise BirthDateRepairError("package season must contain consecutive numeric years")
    return f"{start:04d}-{end % 100:02d}", dt.date(start, 8, 1)


def _plausible(value: object, snapshot: dt.date) -> bool:
    if not isinstance(value, str):
        return False
    try:
        born = dt.date.fromisoformat(value)
    except ValueError:
        return False
    age = snapshot.year - born.year - ((snapshot.month, snapshot.day) < (born.month, born.day))
    # A 55-year ceiling includes genuine late-career outliers (notably Kevin
    # Poole at Burton in 2013/14) while still catching the stale future-player
    # leakage this repair targets.
    return born <= snapshot and 14 <= age <= 55


def _bad_date(player: Mapping[str, Any], snapshot: dt.date) -> bool:
    facts = player.get("facts")
    return isinstance(facts, Mapping) and isinstance(facts.get("birth_date"), str) and not _plausible(facts["birth_date"], snapshot)


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BirthDateRepairError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise BirthDateRepairError(f"{label} must be a JSON object")
    return value


def _correction_index() -> tuple[dict[tuple[str, str], dict[str, Any]], str]:
    payload = _read_object(CORRECTIONS, "birth-date correction ledger")
    if payload.get("schema_version") != CORRECTIONS_SCHEMA or not isinstance(payload.get("corrections"), list):
        raise BirthDateRepairError("birth-date correction ledger has an unsupported schema")
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload["corrections"]:
        if not isinstance(row, Mapping) or not isinstance(row.get("birth_date"), str) or not isinstance(row.get("source_name"), str):
            raise BirthDateRepairError("birth-date correction row is malformed")
        if not _plausible(row["birth_date"], dt.date(2026, 8, 1)):
            raise BirthDateRepairError("birth-date correction itself is not a usable ISO date")
        player_ids = row.get("player_ids")
        if not isinstance(player_ids, Mapping):
            raise BirthDateRepairError("birth-date correction lacks player IDs")
        for season, player_id in player_ids.items():
            key = (str(season), str(player_id))
            if key in index:
                raise BirthDateRepairError(f"duplicate correction target: {key}")
            index[key] = dict(row)
    return index, _sha256(CORRECTIONS)


def _source_clubs(path: Path) -> dict[str, dict[str, Any]]:
    intake = _read_object(path, "pinned source intake")
    rows = intake.get("source_clubs")
    if not isinstance(rows, list):
        raise BirthDateRepairError("source intake lacks source_clubs")
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("selector"), Mapping):
            raise BirthDateRepairError("source intake contains a malformed source club")
        key = _normalise(row["selector"].get("club_name"))
        if not key:
            raise BirthDateRepairError("source intake has a missing normalised club name")
        candidates[key].append(dict(row))
    # A name collision in an old multi-country capture is not enough evidence
    # to select either squad.  It is deliberately treated as source-unavailable
    # for this bounded repair, which restores the parser-read native record
    # and records that fact rather than making a cross-club substitution.
    return {key: rows[0] for key, rows in candidates.items() if len(rows) == 1}


def _represented_source_rows(
    *, source_club: Mapping[str, Any], club_players: Sequence[Mapping[str, Any]], snapshot: dt.date,
) -> set[str]:
    raw_players = source_club.get("players")
    if not isinstance(raw_players, list):
        raise BirthDateRepairError("source club has no player list")
    names: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in raw_players:
        if not isinstance(row, Mapping) or not isinstance(row.get("facts"), Mapping):
            raise BirthDateRepairError("source player row is malformed")
        names[_normalise(row["facts"].get("name"))].append(row)
    represented: set[str] = set()
    for player in club_players:
        if _bad_date(player, snapshot):
            continue
        person_id = str(player.get("person_id") or "")
        facts = player.get("facts")
        if not isinstance(facts, Mapping):
            continue
        display_name = _normalise(player.get("source_name") or player.get("name"))
        birth = facts.get("birth_date")
        matches = [
            row for row in names.get(display_name, [])
            if row.get("source_row_sha256") in person_id
            or (isinstance(birth, str) and row["facts"].get("birth_date") == birth)
        ]
        if len(matches) == 1 and isinstance(matches[0].get("source_row_sha256"), str):
            represented.add(str(matches[0]["source_row_sha256"]))
    return represented


def _person_identity(player: Mapping[str, Any]) -> tuple[str, str, str] | None:
    """Return the conservative identity used by strict package validation.

    A dated capture can contain the same player in a second club's opening
    roster (typically a stale transfer or a duplicated capture row).  A
    source-backed replacement must never introduce that ambiguity merely to
    resolve a bad date.  Leave the carrier native in that case instead.
    """
    name = _normalise(player.get("source_name") or player.get("name"))
    facts = player.get("facts")
    if not isinstance(facts, Mapping):
        return None
    birth_date = facts.get("birth_date")
    nationality = _normalise(facts.get("nationality"))
    if not name or not isinstance(birth_date, str) or not nationality:
        return None
    return name, birth_date, nationality


def _restore_base_player(
    *, player: Mapping[str, Any], club_id: str, base_entries: Mapping[int, Any], base_bytes: bytes,
) -> dict[str, Any]:
    carrier = player.get("carrier_id")
    if not isinstance(carrier, int):
        raise BirthDateRepairError("fallback target has no numeric player carrier")
    entry = base_entries.get(carrier)
    if entry is None:
        raise BirthDateRepairError(f"clean base JUG has no player carrier {carrier}")
    payload = entry.decode_payload(base_bytes)
    try:
        restored = base_rows._preserved_player(
            payload=payload, player_carrier=carrier, club_id=club_id,
            artifact_id=PRESERVATION_ARTIFACT_ID, source_id=PRESERVATION_SOURCE_ID,
        )
    except base_rows.ReconciliationError as exc:
        raise BirthDateRepairError(str(exc)) from exc
    if restored["id"] != player.get("id"):
        raise BirthDateRepairError(f"base fallback changes stable player ID for carrier {carrier}")
    return restored


def _ensure_correction_artifact(package: dict[str, Any], *, corrections_sha256: str) -> None:
    artifacts = package.get("artifacts")
    if not isinstance(artifacts, list):
        raise BirthDateRepairError("recipe has no artifacts list")
    artifact_id = "season-birth-date-corrections-v1"
    expected = {
        "id": artifact_id,
        "kind": "season-input",
        "relative_path": "scripts/data/season_birth_date_corrections_v1.json",
        "sha256": corrections_sha256,
    }
    retained = [row for row in artifacts if isinstance(row, Mapping) and row.get("id") != artifact_id]
    if len(retained) != len(artifacts) - sum(isinstance(row, Mapping) and row.get("id") == artifact_id for row in artifacts):
        raise BirthDateRepairError("recipe artifacts list is malformed")
    package["artifacts"] = sorted([*retained, expected], key=lambda row: str(row["id"]))


def _write_package(path: Path, package: Mapping[str, Any]) -> str:
    payload = package_v2.canonical_json_bytes(dict(package))
    temporary = path.with_name(f".{path.name}.birth-date-repair.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise BirthDateRepairError(f"temporary recipe path already exists: {temporary}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    return hashlib.sha256(payload).hexdigest()


def _bind_parser_safe_source_aliases(
    *, package: dict[str, Any], source_clubs: Mapping[str, Mapping[str, Any]],
    base_entries: Mapping[int, Any], base_bytes: bytes, changes: list[dict[str, Any]],
) -> None:
    """Bind every newly scoped source identity to its proven native name window.

    A source replacement is allowed to retain the full source name in
    ``source_name`` but its in-game display spelling must fit the original
    record's variable-length window.  The scoped identity is deliberately the
    repair's marker: ordinary source rows are left untouched.
    """

    clubs = {str(club["id"]): club for club in package["clubs"]}
    for player in package["players"]:
        if not isinstance(player, dict):
            continue
        club = clubs.get(str(player.get("club_id")))
        if club is None:
            raise BirthDateRepairError(f"player {player.get('id')!r} has no declared club")
        source_club = source_clubs.get(_normalise(club.get("name")))
        if source_club is None:
            continue
        raw_players = source_club.get("players")
        if not isinstance(raw_players, list):
            raise BirthDateRepairError("source club has no player rows")
        source_player = next((
            row for row in raw_players
            if isinstance(row, Mapping)
            and player.get("person_id") == source_builder._source_person_id(
                row, source_selector=source_club["selector"],
            )
        ), None)
        if source_player is None:
            continue
        carrier = player.get("carrier_id")
        if not isinstance(carrier, int) or carrier not in base_entries:
            raise BirthDateRepairError(f"source replacement {player.get('id')!r} has no base carrier")
        source_name = str(source_player["facts"]["name"])
        payload = base_entries[carrier].decode_payload(base_bytes)
        try:
            display_name, method = aliases._derive_display_name(
                payload=payload, carrier_id=carrier, source_name=source_name,
                requested_name=source_name,
            )
        except aliases.DisplayAliasRepairError as exc:
            raise BirthDateRepairError(str(exc)) from exc
        if player.get("name") == display_name:
            continue
        before_name = player.get("name")
        player["name"] = display_name
        changes.append({
            "player_id": str(player["id"]), "club_id": str(club["id"]),
            "action": "parser-safe-source-display-alias",
            "before_display_name": before_name, "after_display_name": display_name,
            "source_name": source_name, "display_alias_method": method,
        })


def _plan_package(
    *, path: Path, source_clubs: Mapping[str, Mapping[str, Any]], base_entries: Mapping[int, Any],
    base_bytes: bytes, corrections: Mapping[tuple[str, str], Mapping[str, Any]], corrections_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    before = package_v2.read_canonical_package(path)
    after = copy.deepcopy(before)
    season_key, snapshot = _snapshot(after.get("season") if isinstance(after.get("season"), Mapping) else {})
    players = after.get("players")
    clubs = after.get("clubs")
    if not isinstance(players, list) or not isinstance(clubs, list):
        raise BirthDateRepairError(f"recipe has no players/clubs lists: {path}")
    players_by_id = {str(player.get("id")): player for player in players if isinstance(player, dict)}
    clubs_by_id = {str(club.get("id")): club for club in clubs if isinstance(club, Mapping)}
    if len(players_by_id) != len(players) or len(clubs_by_id) != len(clubs):
        raise BirthDateRepairError(f"recipe IDs are malformed: {path}")
    changes: list[dict[str, Any]] = []
    corrected = False
    occupied_identities = {
        identity
        for player in players_by_id.values()
        if isinstance(player.get("facts"), Mapping)
        and _plausible(player["facts"].get("birth_date"), snapshot)
        for identity in [_person_identity(player)]
        if identity is not None
    }

    for club_id, club in sorted(clubs_by_id.items()):
        roster_ids = club.get("roster_player_ids")
        if not isinstance(roster_ids, list) or any(player_id not in players_by_id for player_id in roster_ids):
            raise BirthDateRepairError(f"club {club_id} has a malformed roster")
        roster = [players_by_id[player_id] for player_id in roster_ids]
        targets = [player for player in roster if _bad_date(player, snapshot)]
        if not targets:
            continue
        source_club = source_clubs.get(_normalise(club.get("name")))
        represented = _represented_source_rows(source_club=source_club, club_players=roster, snapshot=snapshot) if source_club else set()
        available = [
            row for row in (source_club or {}).get("players", [])
            if isinstance(row, Mapping)
            and isinstance(row.get("facts"), Mapping)
            and isinstance(row.get("source_row_sha256"), str)
            and row["source_row_sha256"] not in represented
            and _plausible(row["facts"].get("birth_date"), snapshot)
            and (
                _person_identity({"source_name": row["facts"].get("name"), "facts": row["facts"]}) is None
                or _person_identity({"source_name": row["facts"].get("name"), "facts": row["facts"]}) not in occupied_identities
            )
        ]
        available.sort(key=lambda row: int(row.get("source_row_index") or 0))
        for player in targets:
            player_id = str(player["id"])
            correction = corrections.get((season_key, player_id))
            facts = player.get("facts")
            if correction is not None:
                if _normalise(player.get("source_name") or player.get("name")) != _normalise(correction["source_name"]):
                    raise BirthDateRepairError(f"correction identity does not match {season_key}/{player_id}")
                if not isinstance(facts, dict):
                    raise BirthDateRepairError(f"correction target {player_id} has malformed facts")
                before_birth = facts.get("birth_date")
                facts["birth_date"] = correction["birth_date"]
                player["proof"] = {"grade": "source-receipt", "artifact_id": "season-birth-date-corrections-v1"}
                changes.append({
                    "player_id": player_id, "club_id": club_id, "action": "cited-source-date-correction",
                    "before_birth_date": before_birth, "after_birth_date": correction["birth_date"],
                    "source_name": correction["source_name"],
                })
                corrected = True
                continue
            if available:
                source_player = dict(available.pop(0))
                source_facts = source_player["facts"]
                before_birth = facts.get("birth_date") if isinstance(facts, Mapping) else None
                source_display_name = unicodedata.normalize("NFC", str(source_facts["name"]))
                player["name"] = source_display_name
                player["source_name"] = source_display_name
                # Scope the raw-row ID to its exact dated club capture.  This
                # avoids silently merging same-name rows from a transfer.
                player["person_id"] = source_builder._source_person_id(
                    source_player, source_selector=source_club["selector"],
                )
                player.pop("policy", None)
                player["facts"], player["fact_fallbacks"] = source_builder._updated_facts(
                    source_facts, f"source-capture-{season_key}",
                )
                identity = _person_identity({"source_name": source_facts.get("name"), "facts": source_facts})
                if identity is not None:
                    occupied_identities.add(identity)
                player["proof"] = {"grade": "source-captured", "artifact_id": f"source-capture-{season_key}"}
                changes.append({
                    "player_id": player_id, "club_id": club_id, "action": "pinned-same-club-source-replacement",
                    "before_birth_date": before_birth, "after_birth_date": source_facts["birth_date"],
                    "source_row_sha256": source_player["source_row_sha256"], "source_name": source_display_name,
                })
                continue
            before_birth = facts.get("birth_date") if isinstance(facts, Mapping) else None
            restored = _restore_base_player(
                player=player, club_id=club_id, base_entries=base_entries, base_bytes=base_bytes,
            )
            player.clear()
            player.update(restored)
            changes.append({
                "player_id": player_id, "club_id": club_id, "action": "no-target-source-native-record-restored",
                "before_birth_date": before_birth, "after_birth_date": None,
                "base_payload_sha256": hashlib.sha256(base_entries[int(player["carrier_id"])].decode_payload(base_bytes)).hexdigest(),
            })
    if corrected:
        _ensure_correction_artifact(after, corrections_sha256=corrections_sha256)
    _bind_parser_safe_source_aliases(
        package=after, source_clubs=source_clubs, base_entries=base_entries,
        base_bytes=base_bytes, changes=changes,
    )
    # A corrected source identity may change the broad position, and an
    # opening-XI repair can do the same.  Reapply the already established
    # deterministic Handling policy to the resulting package before it is
    # materialised.  This is a rating safety guard, not a new ratings model.
    handling = preparation._normalise_position_handling(players_by_id)
    for row in [*handling["outfield"], *handling["goalkeeper"]]:
        changes.append({
            "player_id": str(row["player_id"]), "action": "position-aware-handling-realigned",
            "before_handling": int(row["before"]), "after_handling": int(row["after"]),
        })
    return after, {
        "path": str(path), "before_sha256": _sha256(path),
        "after_sha256": package_v2.sha256_bytes(package_v2.canonical_json_bytes(after)), "changes": changes,
    }


def repair(
    *, package_paths: Sequence[Path], compile_package_path: Path, source_intake: Path,
    base_tree: Path, runtime_game: Path, receipt_path: Path, apply: bool,
    force_refresh_ids: Sequence[str] = (),
) -> dict[str, Any]:
    resolved = [path.resolve() for path in package_paths]
    if len(set(resolved)) != len(resolved):
        raise BirthDateRepairError("each --package must be supplied once")
    compile_package_path = compile_package_path.resolve()
    if compile_package_path not in resolved:
        raise BirthDateRepairError("--compile-package must also be supplied through --package")
    base_jug = base_tree.resolve() / "DBDAT/JUG98030.FDI"
    if not base_jug.is_file():
        raise BirthDateRepairError("clean base JUG is unavailable")
    base_bytes = base_jug.read_bytes()
    base_entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(base_bytes).entries}
    corrections, corrections_sha256 = _correction_index()
    sources = _source_clubs(source_intake.resolve())
    plans = [
        (path, *_plan_package(
            path=path, source_clubs=sources, base_entries=base_entries, base_bytes=base_bytes,
            corrections=corrections, corrections_sha256=corrections_sha256,
        ))
        for path in resolved
    ]
    # A failed preflight must never leave a half-applied recipe/game pair.  A
    # previous interrupted alpha run can have a recipe already restored to a
    # native whole-record policy while its live JUG still carries the old
    # candidate.  Detect that specific, byte-provable pending refresh here.
    live_jug = runtime_game.resolve() / "DBDAT/JUG98030.FDI"
    if not live_jug.is_file():
        raise BirthDateRepairError("runtime game has no JUG98030.FDI")
    live_bytes = live_jug.read_bytes()
    live_entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(live_bytes).entries}
    pending_native_ids: list[str] = []
    compile_package = next(package for path, package, _plan in plans if path == compile_package_path)
    for player in compile_package["players"]:
        if player.get("policy") != "preserve-existing-mode1":
            continue
        carrier = player.get("carrier_id")
        if not isinstance(carrier, int) or carrier not in base_entries or carrier not in live_entries:
            raise BirthDateRepairError("native-preserve player is absent from a JUG index")
        if (
            live_entries[carrier].decode_payload(live_bytes)
            != base_entries[carrier].decode_payload(base_bytes)
        ):
            pending_native_ids.append(str(player["id"]))
    if pending_native_ids:
        for _path, _package, plan in plans:
            plan["changes"].extend({
                "player_id": player_id, "action": "pending-native-record-runtime-refresh",
            } for player_id in pending_native_ids)
    forced_ids = sorted(set(force_refresh_ids))
    if forced_ids:
        declared_ids = {str(player["id"]) for player in compile_package["players"]}
        unknown = sorted(set(forced_ids) - declared_ids)
        if unknown:
            raise BirthDateRepairError(f"forced runtime refresh names unknown players: {unknown}")
        for _path, _package, plan in plans:
            plan["changes"].extend({
                "player_id": player_id, "action": "explicit-pending-runtime-refresh",
            } for player_id in forced_ids)
    change_maps = [
        {row["player_id"]: (row["action"], row.get("after_birth_date"), row.get("source_row_sha256")) for row in plan["changes"]}
        for _path, _package, plan in plans
    ]
    if not change_maps or any(row != change_maps[0] for row in change_maps[1:]):
        raise BirthDateRepairError("current recipe snapshots disagree about birth-date repair targets")
    target_ids = set(change_maps[0])
    if not target_ids:
        raise BirthDateRepairError("no implausible player birth dates require repair")
    # Preflight the full parser/compiler transaction from a disposable recipe
    # file before replacing even one live snapshot.  The actual write repeats
    # the same deterministic compile only after that proof succeeds.
    with tempfile.NamedTemporaryFile(
        prefix="pm99-birth-date-repair-", suffix=".json", dir=runtime_game.resolve().parent,
        delete=False,
    ) as handle:
        temporary_package = Path(handle.name)
        handle.write(package_v2.canonical_json_bytes(compile_package))
    try:
        jug_refresh._refresh_live_jug(
            package_path=temporary_package, base_tree=base_tree, runtime_game=runtime_game,
            target_ids=target_ids, apply=False,
        )
    finally:
        if temporary_package.exists() or temporary_package.is_symlink():
            temporary_package.unlink()
    if apply:
        for path, package, plan in plans:
            plan["after_sha256"] = _write_package(path, package)
    live = jug_refresh._refresh_live_jug(
        package_path=compile_package_path, base_tree=base_tree, runtime_game=runtime_game,
        target_ids=target_ids, apply=apply,
    )
    compile_plan = next(plan for path, _package, plan in plans if path == compile_package_path)
    package = package_v2.read_canonical_package(compile_package_path)
    season, _snapshot_date = _snapshot(package["season"])
    counts: dict[str, int] = defaultdict(int)
    for row in compile_plan["changes"]:
        counts[str(row["action"])] += 1
    result = {
        "schema_version": SCHEMA, "season": season,
        "state": "applied-directly-to-alpha-game" if apply else "validated-direct-repair-plan",
        "policy": {
            "snapshot": "season-start-01-august", "minimum_age": 14, "maximum_age": 55,
            "source_replacement": "same-exact-normalised-club-and-pinned-source-row-only",
            "no_source": "restore-parser-read-native-mode1-record",
            "raw_capture": "immutable; ambiguous claims are explicit cited corrections",
        },
        "correction_ledger_sha256": corrections_sha256,
        "packages": [plan for _path, _package, plan in plans],
        "target_player_count": len(target_ids), "actions": dict(sorted(counts.items())),
        "runtime_refresh": live,
    }
    if apply:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_bytes(package_v2.canonical_json_bytes(result))
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, action="append", required=True)
    parser.add_argument("--compile-package", type=Path, required=True)
    parser.add_argument("--source-intake", type=Path, required=True)
    parser.add_argument("--base-tree", type=Path, required=True)
    parser.add_argument("--runtime-game", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--refresh-player-id", action="append", default=[],
        help="Finish one explicitly identified recipe/runtime transaction interrupted after recipe preflight.",
    )
    parser.add_argument("--apply", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = repair(
            package_paths=args.package, compile_package_path=args.compile_package,
            source_intake=args.source_intake, base_tree=args.base_tree,
            runtime_game=args.runtime_game, receipt_path=args.receipt, apply=args.apply,
            force_refresh_ids=args.refresh_player_id,
        )
    except (BirthDateRepairError, jug_refresh.OpeningLineupPositionRepairError, OSError, ValueError) as exc:
        print(f"direct-birth-date-plausibility-repair: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "state": result["state"], "target_player_count": result["target_player_count"],
        "actions": result["actions"], "runtime_changed_carrier_count": result["runtime_refresh"]["changed_carrier_count"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
