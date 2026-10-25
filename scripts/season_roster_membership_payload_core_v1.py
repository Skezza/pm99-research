"""Source-bound in-memory primitive for checked mode-0 EQ roster membership moves.

This deliberately does not decide player identity, date ownership, lineup
membership, or roster disposition. A source-admission plan must provide those
claims; this helper only applies an exact carrier membership move in memory.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
from typing import Any, Mapping, Sequence

from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.xor import xor_decode
from scripts import season_package_compiler_v2 as compiler


class MembershipPayloadError(ValueError):
    """A requested owner move is stale, ambiguous, or outside the writer lane."""


def _read_rosters(eq_data: bytes) -> tuple[IndexedFDIFile, dict[int, bytes], dict[int, Any], dict[int, set[int]]]:
    index = IndexedFDIFile.from_bytes(eq_data)
    raw_by_club: dict[int, bytes] = {}
    rows_by_club: dict[int, Any] = {}
    owners: dict[int, set[int]] = defaultdict(set)
    for entry in index.entries:
        raw = eq_data[entry.payload_offset:entry.payload_offset + entry.payload_length]
        parsed = parse_eq_external_team_roster_payload(raw, {})
        if parsed is None:
            continue
        raw_by_club[int(entry.record_id)] = raw
        rows_by_club[int(entry.record_id)] = parsed
        for row in parsed.rows:
            owners[int(row.player_record_id)].add(int(entry.record_id))
    return index, raw_by_club, rows_by_club, dict(owners)


def _rewrite_roster_rows(raw: bytes, rows: Sequence[tuple[int, int]]) -> bytes:
    """Delegate the bounded native encoding to the upstream pure payload API."""
    parsed = parse_eq_external_team_roster_payload(raw, {})
    if parsed is None or not parsed.rows or parsed.mode_byte != 0:
        raise MembershipPayloadError("selected roster must be a parser-backed mode-0 external roster")
    from app.eq_roster_membership import rewrite_mode0_roster_membership_payload
    before = [(int(row.flag), int(row.player_record_id)) for row in parsed.rows]
    try:
        return rewrite_mode0_roster_membership_payload(
            raw, expected_rows=before, desired_rows=rows)
    except ValueError as exc:
        raise MembershipPayloadError(str(exc)) from exc


def reassign_memberships(eq_data: bytes, moves: Sequence[Mapping[str, int]]) -> tuple[bytes, dict[str, Any]]:
    """Move existing unique-owned carriers between mode-0 roster tails in memory."""
    if not moves:
        raise MembershipPayloadError("at least one ownership move is required")
    index, raw_by_club, parsed_by_club, owners = _read_rosters(eq_data)
    roster_before = {
        cid: [(int(row.flag), int(row.player_record_id)) for row in parsed.rows]
        for cid, parsed in parsed_by_club.items()
    }
    changed = {int(cid): list(rows) for cid, rows in roster_before.items()}
    seen_players: set[int] = set()
    changed_clubs: set[int] = set()
    move_rows = []
    for move in moves:
        pid = move.get("player_record_id")
        source = move.get("from_club_carrier_id")
        target = move.get("to_club_carrier_id")
        if any(type(v) is not int for v in (pid, source, target)) or pid <= 0 or source == target:
            raise MembershipPayloadError("moves require distinct integer source/target clubs and a positive player ID")
        if pid in seen_players:
            raise MembershipPayloadError("a carrier may appear in only one move")
        seen_players.add(pid)
        if source not in parsed_by_club or target not in parsed_by_club:
            raise MembershipPayloadError("both source and target must have supported linked rosters")
        if parsed_by_club[source].mode_byte != 0 or parsed_by_club[target].mode_byte != 0:
            raise MembershipPayloadError("membership writes are limited to explicitly selected mode-0 clubs")
        if owners.get(pid) != {source}:
            raise MembershipPayloadError("moved carrier must have exactly the pinned source owner")
        source_rows = changed[source]
        target_rows = changed[target]
        hits = [row for row in source_rows if row[1] == pid]
        if len(hits) != 1 or any(row[1] == pid for row in target_rows):
            raise MembershipPayloadError("source/target roster preimage is ambiguous or stale")
        flag, _ = hits[0]
        if flag != 0 or any(row[0] != 0 for row in source_rows + target_rows):
            raise MembershipPayloadError("writer supports only exact all-zero roster flags")
        changed[source] = [row for row in source_rows if row[1] != pid]
        changed[target] = [*target_rows, (flag, pid)]
        changed_clubs.update((source, target))
        move_rows.append({"player_record_id": pid, "from_club_carrier_id": source,
                          "to_club_carrier_id": target, "preserved_row_flag": flag})

    replacements: dict[int, bytes] = {}
    for cid in sorted(changed_clubs):
        if changed[cid] == roster_before[cid]:
            raise MembershipPayloadError("selected club has no membership delta")
        replacements[cid] = xor_decode(_rewrite_roster_rows(raw_by_club[cid], changed[cid]))
    result = compiler._rebuild_indexed(eq_data, index, replacements)
    after_index, after_raw, after_parsed, after_owners = _read_rosters(result)
    if {e.record_id for e in after_index.entries} != {e.record_id for e in index.entries}:
        raise MembershipPayloadError("indexed rebuild changed EQ record IDs")
    for entry in index.entries:
        cid = int(entry.record_id)
        if cid not in changed_clubs:
            after_entry = next(e for e in after_index.entries if e.record_id == cid)
            before_raw = eq_data[entry.payload_offset:entry.payload_offset + entry.payload_length]
            after_payload = result[after_entry.payload_offset:after_entry.payload_offset + after_entry.payload_length]
            if before_raw != after_payload:
                raise MembershipPayloadError(f"unselected EQ payload {cid} changed")
    for pid in seen_players:
        expected = {target for target, rows in changed.items() if any(row[1] == pid for row in rows)}
        if after_owners.get(pid) != expected:
            raise MembershipPayloadError("owner readback differs from requested unique postimage")
    for cid in changed_clubs:
        observed = [(int(row.flag), int(row.player_record_id)) for row in after_parsed[cid].rows]
        if observed != changed[cid]:
            raise MembershipPayloadError("selected complete roster row postimage differs")
        after_entry = next(e for e in after_index.entries if e.record_id == cid)
        after_payload = result[after_entry.payload_offset:after_entry.payload_offset + after_entry.payload_length]
        before_payload = raw_by_club[cid]
        parsed_before = parsed_by_club[cid]
        count_offset = parsed_before.rows[0].raw_row_offset - 1
        if after_payload[:count_offset] != before_payload[:count_offset]:
            raise MembershipPayloadError("selected roster prefix before its row count changed")
    receipt = {
        "schema_version": "pm99-opening-roster-membership-payload-prototype-v1",
        "operation": "source-plan-bound-existing-carrier-ownership-move",
        "moves": move_rows,
        "selected_clubs": [
            {"carrier_id": cid,
             "mode": int(parsed_by_club[cid].mode_byte),
             "before_rows": [{"flag": flag, "player_record_id": pid} for flag, pid in roster_before[cid]],
             "after_rows": [{"flag": flag, "player_record_id": pid} for flag, pid in changed[cid]],
             "before_count": len(roster_before[cid]), "after_count": len(changed[cid]),
             "payload_prefix_before_row_count_sha256": hashlib.sha256(
                 raw_by_club[cid][:parsed_by_club[cid].rows[0].raw_row_offset - 1]).hexdigest(),
             "payload_prefix_after_row_count_sha256": hashlib.sha256(
                 after_raw[cid][:after_parsed[cid].rows[0].raw_row_offset - 1]).hexdigest()}
            for cid in sorted(changed_clubs)],
        "unselected_eq_payloads_byte_identical": True,
        "jug_or_recipe_written": False,
    }
    return result, receipt
