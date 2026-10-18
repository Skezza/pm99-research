#!/usr/bin/env python3
"""Fail-closed structural audit for a compiled 2015/16 English-92 release.

This verifies the data and asset contracts which are cheap to prove from the
generated artefacts.  It deliberately does not claim that a player skill is a
historically perfect rating or that the generic 4-4-2 is a date-certified XI;
those remain source-evidence questions recorded in the build ledgers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (EDITOR, ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.editor_actions import _decoded_byte, _native_dd6360_role_start  # noqa: E402
from app.editor_actions import xor_encode  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.eq_initial_tactics import read_initial_tactics  # noqa: E402
from scripts.build_2015_english92_release import (  # noqa: E402
    EQ_TACTICS_GRID_BYTES,
    EQ_TACTICS_PLAYER_COUNT,
    EQ_TACTICS_PREFIX_BYTES,
    _initial_tactics_offset,
)


SKILLS = (
    "speed", "stamina", "aggression", "quality", "heading", "dribbling",
    "passing", "shooting", "tackling",
)
VISIBLE_SKILLS = (*SKILLS, "handling")


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise RuntimeError(f"required artefact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dd6360_audit(game_root: Path, ledger: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    player_path = game_root / "DBDAT" / "JUG98030.FDI"
    data = player_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(data)
    entries = {entry.record_id: entry for entry in indexed.entries}
    nationalities = {int(row["record_id"]): int(row["nationality_code"]) for row in manifest["players"]}
    failures: list[dict[str, Any]] = []
    rows = [row for row in ledger if row.get("family") == "dd6360"]
    for row in rows:
        record_id = int(row["record_id"])
        entry = entries.get(record_id)
        if entry is None:
            failures.append({"record_id": record_id, "reason": "missing-jug-entry"})
            continue
        payload = entry.decode_payload(data)
        if payload[2:5] != b"\xdd\x63\x60":
            failures.append({"record_id": record_id, "reason": "signature", "actual": payload[2:5].hex()})
            continue
        start = _native_dd6360_role_start(payload)
        year, month, day = (int(value) for value in str(row["birth_date"]).split("-"))
        metadata = [
            _decoded_byte(payload, start + 8),
            _decoded_byte(payload, start + 10),
            _decoded_byte(payload, start + 11),
            _decoded_byte(payload, start + 12),
            _decoded_byte(payload, start + 13),
            _decoded_byte(payload, start + 14) | (_decoded_byte(payload, start + 15) << 8),
            _decoded_byte(payload, start + 16),
            _decoded_byte(payload, start + 17),
        ]
        expected = [
            nationalities[record_id],
            {"G": 0, "D": 1, "M": 2, "F": 3}[str(row["position"])],
            {"G": 0, "D": 1, "M": 2, "F": 3}[str(row["position"])],
            day, month, year, int(row["height_cm"]), int(row["weight_kg"]),
        ]
        observed_skills = [_decoded_byte(payload, start + 18 + index) for index in range(9)]
        expected_skills = [int(row["skills"][skill]) for skill in SKILLS]
        if metadata != expected or observed_skills != expected_skills:
            failures.append({"record_id": record_id, "reason": "native-field-mismatch"})
    return {"rows": len(rows), "ok": not failures, "failures": failures}


def _dd6361_visible_skill_audit(game_root: Path, ledger: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify all ten displayed skills, including the dedicated Handling byte."""
    player_path = game_root / "DBDAT" / "JUG98030.FDI"
    data = player_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(data)
    entries = {entry.record_id: entry for entry in indexed.entries}
    rows = [row for row in ledger if row.get("family") == "dd6361"]
    failures: list[dict[str, Any]] = []
    goalkeeper_count = 0
    for row in rows:
        record_id = int(row["record_id"])
        entry = entries.get(record_id)
        if entry is None:
            failures.append({"record_id": record_id, "reason": "missing-jug-entry"})
            continue
        payload = entry.decode_payload(data)
        if payload[2:5] != b"\xdd\x63\x61" or len(payload) < 19:
            failures.append({"record_id": record_id, "reason": "dd6361-tail-layout"})
            continue
        visible = dict(row.get("visible_skills") or {})
        if set(visible) != set(VISIBLE_SKILLS):
            failures.append({"record_id": record_id, "reason": "incomplete-visible-skill-ledger"})
            continue
        observed = [payload[-16 + offset] ^ 0x61 for offset in range(9)]
        observed.append(payload[-7] ^ 0x61)
        expected = [int(visible[field]) for field in VISIBLE_SKILLS]
        if observed != expected:
            failures.append({"record_id": record_id, "reason": "visible-skill-mismatch", "observed": observed, "expected": expected})
        if row.get("position") == "G":
            goalkeeper_count += 1
            minimum_plausible = max(35, int(visible["quality"]) - 20)
            if int(visible["handling"]) < minimum_plausible:
                failures.append({
                    "record_id": record_id,
                    "reason": "goalkeeper-handling-not-relative-to-quality",
                    "handling": int(visible["handling"]),
                    "quality": int(visible["quality"]),
                    "minimum_plausible": minimum_plausible,
                    "basis": row.get("handling_basis"),
                })
    non_dd6361_goalkeepers = [
        {"record_id": int(row["record_id"]), "name": row["name"], "club": row["club"]}
        for row in ledger if row.get("position") == "G" and row.get("family") != "dd6361"
    ]
    if non_dd6361_goalkeepers:
        failures.append({"reason": "goalkeeper-without-proven-visible-skill-tail", "players": non_dd6361_goalkeepers})
    return {
        "rows": len(rows),
        "goalkeeper_count": goalkeeper_count,
        "all_goalkeepers_dd6361": not non_dd6361_goalkeepers,
        "ok": not failures,
        "failures": failures,
    }


def _opening_tactics_audit(
    game_root: Path,
    manifest: dict[str, Any],
    ledger: list[dict[str, Any]],
) -> dict[str, Any]:
    """Verify every opening XI grid and its minimum meaningful geometry."""
    team_path = game_root / "DBDAT" / "EQ98030.FDI"
    data = team_path.read_bytes()
    indexed = IndexedFDIFile.from_bytes(data)
    entries = {entry.record_id: entry for entry in indexed.entries}
    player_positions = {int(row["record_id"]): str(row["position"]) for row in ledger}
    failures: list[dict[str, Any]] = []
    modes: Counter[str] = Counter()
    all_vertical_lanes: list[int] = []
    for team in manifest["teams"]:
        record_id = int(team["record_id"])
        entry = entries.get(record_id)
        if entry is None:
            failures.append({"record_id": record_id, "club": team["club"], "reason": "missing-eq-entry"})
            continue
        raw = xor_encode(entry.decode_payload(data))
        mode = int(raw[0x29]) if len(raw) > 0x29 else -1
        modes[str(mode)] += 1
        try:
            offset = _initial_tactics_offset(raw)
        except ValueError as exc:
            failures.append({"record_id": record_id, "club": team["club"], "reason": "tactics-layout", "detail": str(exc)})
            continue
        grid_start = offset + EQ_TACTICS_PREFIX_BYTES
        grid_end = grid_start + EQ_TACTICS_GRID_BYTES
        actual_states = read_initial_tactics(raw).states
        expected_positions = list(team.get("opening_tactics_positions") or [])
        if len(expected_positions) != EQ_TACTICS_PLAYER_COUNT:
            failures.append({"record_id": record_id, "club": team["club"], "reason": "missing-opening-tactics-plan"})
            continue
        if not str(team.get("opening_tactics_status") or "").startswith(("written-proven-mode", "written-contextual-mode", "written-legacy-static-mode")):
            failures.append({"record_id": record_id, "club": team["club"], "reason": "tactics-not-written", "status": team.get("opening_tactics_status")})
            continue
        opening_ids = [int(value) for value in team.get("opening_lineup_player_record_ids") or []]
        if len(opening_ids) != EQ_TACTICS_PLAYER_COUNT:
            failures.append({"record_id": record_id, "club": team["club"], "reason": "missing-opening-lineup-order"})
            continue
        goalkeeper_slots = [index for index, player_id in enumerate(opening_ids) if player_positions.get(player_id) == "G"]
        if len(goalkeeper_slots) != 1:
            failures.append({
                "record_id": record_id,
                "club": team["club"],
                "reason": "opening-lineup-needs-one-goalkeeper",
                "goalkeeper_slots": [slot + 1 for slot in goalkeeper_slots],
            })
            continue
        for player_index, position in enumerate(expected_positions):
            if not isinstance(position, list) or len(position) != 4:
                failures.append({"record_id": record_id, "club": team["club"], "reason": "invalid-opening-tactics-plan", "player_slot": player_index + 1})
                break
            for ball_zone in range(20):
                actual = list(actual_states[player_index][ball_zone])
                context = team.get('opening_tactics_context')
                expected = context['slots'][player_index]['states'][ball_zone] if context else [
                    min(int(value), maximum) for value, maximum in zip(position, (228, 398, 228, 398))]
                if not context and player_index == 0 and ball_zone == 0:
                    expected[3] = 0
                if actual != expected:
                    failures.append({
                        "record_id": record_id, "club": team["club"], "reason": "opening-tactics-grid-mismatch",
                        "player_slot": player_index + 1, "ball_zone": ball_zone, "actual": actual,
                        "expected": expected,
                    })
                    break
            if failures and failures[-1].get("record_id") == record_id:
                break
        if failures and failures[-1].get("record_id") == record_id:
            continue
        # The PM99 pitch has its own goal at the low-depth edge.  A prior
        # compiler revision wrote the coordinates structurally correctly but
        # inverted that axis, placing every goalkeeper at the attacking end.
        # This inexpensive semantic guard catches that regression without
        # pretending that an automated audit can judge a manager's tactics.
        goalkeeper_slot = goalkeeper_slots[0]
        goalkeeper_depth = int(expected_positions[goalkeeper_slot][1])
        outfield_depths = [int(position[1]) for index, position in enumerate(expected_positions) if index != goalkeeper_slot]
        if goalkeeper_depth >= min(outfield_depths):
            failures.append({
                "record_id": record_id,
                "club": team["club"],
                "reason": "goalkeeper-not-at-own-goal-end",
                "goalkeeper_depth": goalkeeper_depth,
                "nearest-outfield_depth": min(outfield_depths),
            })
            continue
        if not team.get('opening_tactics_context') and any(int(position[0]) != int(position[2]) or int(position[1]) != int(position[3]) for position in expected_positions):
            failures.append({"record_id": record_id, "club": team["club"], "reason": "non-static-opening-tactics-grid"})
            continue
        # The semantic lane is PM99's short, vertical pitch axis. It clips at
        # the lower edge when a wide-axis value is accidentally written here;
        # that produces a technically valid grid with the whole XI crushed
        # against one touchline.  The historical compiler intentionally keeps
        # every generated lane inside the safe in-pitch range.
        vertical_lanes = [int(position[0]) for position in expected_positions]
        all_vertical_lanes.extend(vertical_lanes)
        if any(lane < 0 or lane > 228 for lane in vertical_lanes):
            failures.append({
                "record_id": record_id,
                "club": team["club"],
                "reason": "opening-tactics-vertical-lane-out-of-range",
                "minimum_lane": min(vertical_lanes),
                "maximum_lane": max(vertical_lanes),
            })
            continue
        if grid_end > len(raw):
            failures.append({"record_id": record_id, "club": team["club"], "reason": "tactics-grid-overruns-eq"})
    return {
        "clubs": len(manifest["teams"]),
        "record_modes": dict(sorted(modes.items())),
        "vertical_lane_count": len(all_vertical_lanes),
        "vertical_lane_min": min(all_vertical_lanes) if all_vertical_lanes else None,
        "vertical_lane_max": max(all_vertical_lanes) if all_vertical_lanes else None,
        "ok": not failures,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument(
        "--game-root", type=Path,
        help="Optional clean materialisation to audit against the build's immutable ledgers.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    build_dir = args.build_dir.expanduser().resolve()
    game_root = (args.game_root or build_dir / "game").expanduser().resolve()
    if not game_root.is_dir() or game_root.is_symlink():
        raise RuntimeError(f"game root must be an existing non-symlink directory: {game_root}")
    output = (args.output or build_dir / "release-audit.json").expanduser().resolve()

    manifest = _load_json(build_dir / "2015-16-english92-manifest.json")
    ledger = list(_load_json(build_dir / "player-ledger.json"))
    roster_audit = list(_load_json(build_dir / "roster-audit.json"))
    visible_skills_receipt = _load_json(build_dir / "visible-skill-receipt.json")
    face_receipt = _load_json(build_dir / "face-stage-receipt.json")
    kit_receipts = sorted((build_dir / "kit-stage").glob("*kit-receipt.json"))
    if len(kit_receipts) != 1:
        raise RuntimeError(
            "expected exactly one generated kit receipt in kit-stage, found "
            f"{[str(path) for path in kit_receipts]}"
        )
    kit_receipt = _load_json(kit_receipts[0])
    calendar_receipt = _load_json(build_dir / "calendar-patch-receipt.json")

    team_counts = Counter(str(row["division"]) for row in manifest["teams"])
    expected_counts = {"Premier League": 20, "Championship": 24, "League One": 24, "League Two": 24}
    roster_ok = all(
        bool(row.get("roster_ok"))
        and int(row.get("actual_count", 0)) == int(row.get("expected_count", 0))
        and int(row.get("actual_count", 0)) in {24, 25}
        and int(row.get("player_parse_count", 0)) == int(row.get("actual_count", 0))
        for row in roster_audit
    )
    dd6360 = _dd6360_audit(game_root, ledger, manifest)
    dd6361_visible_skills = _dd6361_visible_skill_audit(game_root, ledger)
    opening_tactics = _opening_tactics_audit(game_root, manifest, ledger)
    face_rows = list(face_receipt.get("rows") or [])
    applied_faces = [row for row in face_rows if row.get("status") == "applied"]
    intentionally_no_photo_faces = [row for row in face_rows if row.get("status") == "intentionally-no-photo"]
    audit = {
        "schema_version": "pm99-2015-16-english92-release-audit-v1",
        "build_dir": str(build_dir),
        "club_count": len(manifest["teams"]),
        "division_counts": dict(team_counts),
        "division_distribution_ok": dict(team_counts) == expected_counts,
        "player_count": len(ledger),
        "manager_count": len(manifest["managers"]),
        "roster_audit": {"clubs": len(roster_audit), "ok": roster_ok},
        "dd6360_native_fields": dd6360,
        "dd6361_visible_skills": {
            **dd6361_visible_skills,
            "receipt_requested_player_count": int(visible_skills_receipt.get("requested_player_count", 0)),
        },
        "opening_tactics": opening_tactics,
        "faces": {
            "complete": bool(face_receipt.get("complete")),
            "verified_portraits": len(applied_faces),
            "intentionally_no_photo": len(intentionally_no_photo_faces),
            "covered": len(applied_faces),
            "dispositioned": len(applied_faces) + len(intentionally_no_photo_faces),
        # Face receipts use a scalar unresolved count.  Accept a legacy list
        # too, so the release audit remains usable while comparing older
        # compiler artifacts.
        "unresolved": (
            int(face_receipt.get("unresolved") or 0)
            if not isinstance(face_receipt.get("unresolved"), list)
            else len(face_receipt.get("unresolved") or [])
        ),
            "loose_bitmap_count": len(list((game_root / "DBDAT" / "MINIFOTO").glob("J96*.BMP"))),
            "minifoto_pkf_sha256": _sha256(game_root / "DBDAT" / "MINIFOTO.PKF"),
        },
        "kits": {
            "team_count": int(kit_receipt.get("team_count", 0)),
            "patched_record_count": int(kit_receipt.get("patched_record_count", 0)),
            "per_archive": dict(kit_receipt.get("patched_counts_by_archive") or {}),
        },
        "calendar": {
            "target_year": int(calendar_receipt.get("target_year", 0)),
            "target_rollover_year": int(calendar_receipt.get("target_rollover_year", 0)),
            "patch_count": int(calendar_receipt.get("patch_count", 0)),
            "exe_sha256": _sha256(game_root / "MANAGPRE.EXE"),
        },
    }
    failures = []
    if audit["club_count"] != 92 or not audit["division_distribution_ok"]:
        failures.append("club/division distribution")
    expected_player_count = sum(int(row.get("expected_count", 0)) for row in roster_audit)
    if audit["player_count"] != expected_player_count or audit["manager_count"] != 92:
        failures.append("player/manager count")
    if not roster_ok or not dd6360["ok"] or not dd6361_visible_skills["ok"]:
        failures.append("roster/native player fields")
    if not opening_tactics["ok"]:
        failures.append("opening tactics")
    if not audit["faces"]["complete"] or audit["faces"]["dispositioned"] != expected_player_count or audit["faces"]["unresolved"]:
        failures.append("face completion")
    if audit["kits"]["team_count"] != 92 or audit["kits"]["patched_record_count"] < 400:
        failures.append("kit render")
    if audit["calendar"]["target_year"] != 2015 or audit["calendar"]["target_rollover_year"] != 2016:
        failures.append("calendar patch")
    audit["ok"] = not failures
    audit["failures"] = failures
    output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
