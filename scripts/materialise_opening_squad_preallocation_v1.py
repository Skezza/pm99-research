#!/usr/bin/env python3
"""Join dated squad rows and sourced opening XIs before carrier allocation.

The output is a deterministic projection, not a replacement source capture.
For each club with a captured first fixture it orders the eleven sourced
starters first, using the original FootballSquads row where reconciliation
found one and a hash-bound Transfermarkt profile row where the starter was
absent.  An unprofiled addition remains a blocker and is never invented.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "pm99-opening-squad-preallocation-v1"
INTAKE_SCHEMA = "pm99-season-source-intake-v1"
LINEUP_SCHEMA = "pm99-transfermarkt-opening-lineup-source-v1"
LINEUP_SCHEMAS = {LINEUP_SCHEMA, "pm99-composed-opening-lineup-source-v1"}
RECONCILIATION_SCHEMA = "pm99-transfermarkt-opening-lineup-reconciliation-v1"
ADDITIONS_SCHEMA = "pm99-transfermarkt-opening-fixture-player-additions-v1"


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_source_club_selection_v1 as source_club_selection_v1  # noqa: E402
from scripts import season_player_identity_v1 as identity_lib  # noqa: E402


class PreallocationError(ValueError):
    """The supplied evidence chain is stale, incomplete, or ambiguous."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreallocationError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise PreallocationError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _selector(value: Mapping[str, Any]) -> tuple[str, str, str]:
    result = tuple(str(value.get(key) or "").strip() for key in ("country_catalog", "competition_catalog", "club_name"))
    if not all(result):
        raise PreallocationError("source selector is incomplete")
    return result  # type: ignore[return-value]


def _full_selector(value: Mapping[str, Any], *, label: str) -> tuple[str, str, str, str, str]:
    """Return one fully content-addressed source-club selector.

    Lineup evidence is indexed on the historical three-part club identity, but
    the selection stage needs the complete source selector.  Keeping those
    notions separate prevents a selected August capture from becoming a second
    allocatable club merely because its display name differs from the
    all-season capture.
    """

    fields = (
        "country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256",
    )
    result = tuple(str(value.get(key) or "").strip() for key in fields)
    if not all(result):
        raise PreallocationError(f"{label} has an incomplete content-addressed selector")
    return result  # type: ignore[return-value]


_SOURCE_PLAYER_ANNOTATIONS = {
    "opening_xi_order",
    "opening_xi_origin",
    "opening_source_player_id",
}


def validate_selection_bound_preallocation(
    *, preallocation: Mapping[str, Any], source_intake: Mapping[str, Any],
    source_club_selection: Mapping[str, Any],
) -> None:
    """Require a preallocation to be an exact projection of one selection.

    This is intentionally narrower than a general preallocation validator.
    Existing non-selection packages retain their legacy contract.  A selected
    package, however, must carry the selection hash and every effective raw
    squad row exactly once.  Profiled opening-XI additions remain permissible,
    but cannot replace or mutate a selected raw row.
    """

    try:
        source_club_selection_v1.validate_selection(
            selection=source_club_selection, source_intake=source_intake
        )
    except source_club_selection_v1.SourceClubSelectionError as exc:
        raise PreallocationError(f"source-club selection is invalid: {exc}") from exc

    if preallocation.get("schema_version") != SCHEMA:
        raise PreallocationError("selection-bound preallocation schema is unsupported")
    if preallocation.get("season") != source_intake.get("season"):
        raise PreallocationError("selection-bound preallocation targets a different season")
    sources = preallocation.get("sources")
    if not isinstance(sources, Mapping):
        raise PreallocationError("selection-bound preallocation sources are malformed")
    if sources.get("source_intake_sha256") != _sha(source_intake):
        raise PreallocationError("selection-bound preallocation targets a different source intake")
    if sources.get("source_capture_sha256") != source_intake.get("source_capture_sha256"):
        raise PreallocationError("selection-bound preallocation targets a different source capture")
    if sources.get("source_club_selection_sha256") != _sha(source_club_selection):
        raise PreallocationError("selection-bound preallocation targets a different source-club selection")

    projected_rows = preallocation.get("source_clubs")
    if not isinstance(projected_rows, list):
        raise PreallocationError("selection-bound preallocation has no source clubs")
    effective_rows = source_club_selection_v1.effective_source_clubs(
        selection=source_club_selection, source_intake=source_intake
    )
    effective_by_selector = {
        _full_selector(row["selector"], label="effective source selector"): row
        for row in effective_rows
    }
    projected_by_selector: dict[tuple[str, str, str, str, str], Mapping[str, Any]] = {}
    for index, row in enumerate(projected_rows):
        if not isinstance(row, Mapping) or not isinstance(row.get("selector"), Mapping):
            raise PreallocationError(f"selection-bound preallocation source club {index} is malformed")
        selector = _full_selector(row["selector"], label="selection-bound preallocation selector")
        if selector in projected_by_selector:
            raise PreallocationError("selection-bound preallocation duplicates a source selector")
        projected_by_selector[selector] = row
    if set(projected_by_selector) != set(effective_by_selector):
        raise PreallocationError(
            "selection-bound preallocation does not exactly cover effective selected source clubs"
        )

    for selector, effective_row in effective_by_selector.items():
        projected_players = projected_by_selector[selector].get("players")
        if not isinstance(projected_players, list):
            raise PreallocationError("selection-bound preallocation source club has no player rows")
        effective_players = effective_row.get("players")
        if not isinstance(effective_players, list):
            raise PreallocationError("effective selected source club has no player rows")
        effective_by_digest: dict[str, Mapping[str, Any]] = {}
        for player in effective_players:
            if not isinstance(player, Mapping):
                raise PreallocationError("effective selected source player is malformed")
            digest = str(player.get("source_row_sha256") or "")
            if not digest or digest in effective_by_digest:
                raise PreallocationError("effective selected source club has invalid player row hashes")
            effective_by_digest[digest] = player

        matched_digests: set[str] = set()
        seen_digests: set[str] = set()
        for player in projected_players:
            if not isinstance(player, Mapping):
                raise PreallocationError("selection-bound preallocation player row is malformed")
            digest = str(player.get("source_row_sha256") or "")
            if not digest or digest in seen_digests:
                raise PreallocationError("selection-bound preallocation duplicates a player row hash")
            seen_digests.add(digest)
            effective_player = effective_by_digest.get(digest)
            if effective_player is None:
                if player.get("opening_xi_origin") != "profiled-first-fixture-addition":
                    raise PreallocationError(
                        "selection-bound preallocation includes a player absent from effective selected source rows"
                    )
                continue
            raw_player = {
                key: copy.deepcopy(value)
                for key, value in player.items()
                if key not in _SOURCE_PLAYER_ANNOTATIONS
            }
            if raw_player != dict(effective_player):
                raise PreallocationError(
                    "selection-bound preallocation player does not exactly match its effective selected source row"
                )
            matched_digests.add(digest)
        if matched_digests != set(effective_by_digest):
            raise PreallocationError(
                "selection-bound preallocation omits an effective selected source player row"
            )


def _position(value: object) -> str | None:
    text = str(value or "").casefold()
    if "goal" in text:
        return "G"
    if "defen" in text or "back" in text:
        return "D"
    if "mid" in text:
        return "M"
    if any(word in text for word in ("attack", "forward", "striker")):
        return "F"
    return None


def _addition_player(row: Mapping[str, Any], source_row_index: int) -> dict[str, Any]:
    if row.get("profile_status") != "opening-fixture-person-profiled":
        raise PreallocationError("an unprofiled opening-XI addition cannot become an allocatable player")
    # A detailed profile label can be outside PM99's four coarse groups (for
    # example "Right Winger").  In that case retain the match report's
    # published position group instead of turning a sourced role into a gap.
    position = _position(row.get("published_profile_position")) or _position(row.get("source_position_group"))
    facts = {
        "shirt_number": None,
        "name": str(row.get("published_full_name") or row.get("display_name") or "").strip(),
        "nationality": None,
        "position": position,
        "height_cm": row.get("published_height_cm"),
        "weight_kg": None,
        "birth_date": row.get("published_birth_date"),
        "unresolved_fields": [],
    }
    if not facts["name"]:
        raise PreallocationError("profiled opening-XI addition has no published name")
    # A provider-specific URL is evidence of its namespace; an unqualified
    # numeric ID or a same-name join alone is not. Existing source rows already
    # retain their facts unchanged through the reconciled-row path.
    profile_url = str(row.get("profile_url") or row.get("source_url") or "")
    profile_id = identity_lib.profile_id_from_href(profile_url)
    if profile_id is not None:
        if str(row.get("source_player_id") or "") != profile_id:
            raise PreallocationError("profile URL and opening source player ID disagree")
        facts[identity_lib.IDENTITY_FIELD] = {"provider": "transfermarkt", "player_id": profile_id}
    gap_names = {
        "shirt_number": "shirt_number", "nationality": "nationality", "position": "primary_position",
        "height_cm": "height_cm", "weight_kg": "weight_kg", "birth_date": "birth_date",
    }
    facts["unresolved_fields"] = [gap for field, gap in gap_names.items() if facts[field] is None]
    identity = {
        "source_player_id": str(row.get("source_player_id") or ""),
        "profile_url": profile_url,
        "facts": facts,
    }
    return {
        "source_row_index": source_row_index,
        "source_row_sha256": _sha(identity),
        "facts": facts,
        "opening_xi_origin": "profiled-first-fixture-addition",
        "opening_source_player_id": identity["source_player_id"],
    }


def materialise(
    *, source_intake: Mapping[str, Any], source_intake_sha256: str,
    lineup: Mapping[str, Any], lineup_sha256: str,
    reconciliation: Mapping[str, Any], reconciliation_sha256: str,
    additions: Mapping[str, Any], additions_sha256: str,
    source_club_selection: Mapping[str, Any] | None = None,
    source_club_selection_sha256: str | None = None,
) -> dict[str, Any]:
    if source_intake.get("schema_version") != INTAKE_SCHEMA:
        raise PreallocationError(f"source intake must have schema {INTAKE_SCHEMA}")
    if lineup.get("schema_version") not in LINEUP_SCHEMAS:
        raise PreallocationError(f"lineup receipt must have one of {sorted(LINEUP_SCHEMAS)}")
    if reconciliation.get("schema_version") != RECONCILIATION_SCHEMA:
        raise PreallocationError(f"reconciliation must have schema {RECONCILIATION_SCHEMA}")
    if additions.get("schema_version") != ADDITIONS_SCHEMA:
        raise PreallocationError(f"additions must have schema {ADDITIONS_SCHEMA}")
    if (reconciliation.get("sources") or {}).get("lineup_capture_sha256") != lineup_sha256:
        raise PreallocationError("reconciliation is not bound to this lineup receipt")
    addition_sources = additions.get("sources") or {}
    if addition_sources.get("lineup_capture_sha256") != lineup_sha256 or addition_sources.get("reconciliation_sha256") != reconciliation_sha256:
        raise PreallocationError("additions are not bound to this lineup/reconciliation pair")
    if source_intake.get("source_capture_sha256") != (reconciliation.get("sources") or {}).get("source_capture_sha256"):
        raise PreallocationError("source intake and reconciliation target different squad captures")

    effective_source_clubs = list(source_intake.get("source_clubs") or [])
    selection_sources: dict[str, str] = {}
    if source_club_selection is None:
        if source_club_selection_sha256 is not None:
            raise PreallocationError("source-club selection hash was supplied without a source-club selection")
    else:
        if not isinstance(source_club_selection_sha256, str):
            raise PreallocationError("source-club selection requires its canonical SHA-256")
        expected_selection_sha256 = _sha(source_club_selection)
        if source_club_selection_sha256 != expected_selection_sha256:
            raise PreallocationError("source-club selection SHA-256 does not bind the supplied selection")
        # The source-selection manifest itself binds the canonical intake
        # representation.  Require the caller to use the same representation
        # so this new preallocation can later be consumed by the package
        # builder's canonical source contract.
        if source_intake_sha256 != _sha(source_intake):
            raise PreallocationError(
                "source-club selection requires a canonical source intake SHA-256"
            )
        try:
            source_club_selection_v1.validate_selection(
                selection=source_club_selection, source_intake=source_intake
            )
        except source_club_selection_v1.SourceClubSelectionError as exc:
            raise PreallocationError(f"source-club selection is invalid: {exc}") from exc
        effective_source_clubs = source_club_selection_v1.effective_source_clubs(
            selection=source_club_selection, source_intake=source_intake
        )
        selection_sources = {"source_club_selection_sha256": expected_selection_sha256}

    clubs = {_selector(row["selector"]): row for row in effective_source_clubs}
    if len(clubs) != len(effective_source_clubs):
        raise PreallocationError("source intake duplicates a club selector")
    lineup_by_club = {_selector(row["source_selector"]): row for row in lineup.get("clubs") or []}
    reconciliation_by_club = {_selector(row["source_selector"]): row for row in reconciliation.get("clubs") or []}
    additions_by_key: dict[tuple[tuple[str, str, str], str], dict[str, Any]] = {}
    pending: list[dict[str, Any]] = []
    for row in additions.get("rows") or []:
        selector = _selector(row["source_selector"])
        key = (selector, str(row.get("source_player_id") or ""))
        if key in additions_by_key:
            raise PreallocationError(f"additions duplicate {key}")
        additions_by_key[key] = dict(row)
        if row.get("profile_status") != "opening-fixture-person-profiled":
            pending.append({"source_selector": dict(row["source_selector"]), "source_player_id": key[1], "reason": "opening-XI-addition-profile-facts-pending"})

    output_clubs: list[dict[str, Any]] = []
    complete = 0
    for selector, source_club in sorted(clubs.items()):
        original = list(source_club["players"])
        by_name: dict[str, list[dict[str, Any]]] = {}
        by_provider_id: dict[str, list[dict[str, Any]]] = {}
        for player in original:
            by_name.setdefault(str(player["facts"]["name"]), []).append(player)
            identity = player['facts'].get(identity_lib.IDENTITY_FIELD, {})
            if identity.get('provider') == 'transfermarkt':
                by_provider_id.setdefault(identity['player_id'], []).append(player)
        lineup_club = lineup_by_club.get(selector)
        reconciled_club = reconciliation_by_club.get(selector)
        ordered_xi: list[dict[str, Any]] = []
        used_hashes: set[str] = set()
        blockers: list[dict[str, Any]] = []
        if lineup_club is not None and reconciled_club is not None:
            resolved_by_id = {str(row["source_player_id"]): row for row in reconciled_club.get("starting_xi") or []}
            for order, starter in enumerate(lineup_club.get("starting_xi") or [], 1):
                source_player_id = str(starter.get("source_player_id") or "")
                resolved = resolved_by_id.get(source_player_id)
                player: dict[str, Any] | None = None
                profile_id = identity_lib.profile_id_from_href(starter.get('source_url') or starter.get('profile_url'))
                if profile_id is not None and profile_id != source_player_id:
                    raise PreallocationError('opening profile URL and player ID disagree')
                identified = by_provider_id.get(profile_id, []) if profile_id is not None else []
                if len(identified) == 1:
                    player = dict(identified[0])
                    player['opening_xi_origin'] = 'literal-provider-ID-dated-squad-row'
                    player['opening_source_player_id'] = source_player_id
                elif len(identified) > 1:
                    blockers.append({'source_player_id': source_player_id, 'reason': 'opening-provider-ID-is-not-unique-in-intake'})
                elif resolved is not None:
                    candidates = by_name.get(str(resolved.get("source_name") or ""), [])
                    # A known different ID cannot become this person merely
                    # because both display names and missing DOBs coincide.
                    if profile_id is not None:
                        candidates = [candidate for candidate in candidates
                            if candidate['facts'].get(identity_lib.IDENTITY_FIELD, {}).get('provider') == 'transfermarkt'
                            and candidate['facts'][identity_lib.IDENTITY_FIELD]['player_id'] == source_player_id]
                    birth_date = resolved.get("source_birth_date")
                    if len(candidates) > 1 and birth_date:
                        candidates = [
                            candidate for candidate in candidates
                            if (candidate.get("facts") or {}).get("birth_date") == birth_date
                        ]
                    if len(candidates) == 1:
                        player = dict(candidates[0])
                        player["opening_xi_origin"] = "reconciled-dated-squad-row"
                        player["opening_source_player_id"] = source_player_id
                    else:
                        blockers.append({"source_player_id": source_player_id, "reason": "reconciled-source-name-is-not-unique-in-intake"})
                else:
                    addition = additions_by_key.get((selector, source_player_id))
                    if addition is not None and addition.get("profile_status") == "opening-fixture-person-profiled":
                        player = _addition_player(addition, len(original) + order - 1)
                    else:
                        blockers.append({"source_player_id": source_player_id, "reason": "opening-XI-player-is-neither-reconciled-nor-profiled"})
                if player is not None:
                    digest = str(player["source_row_sha256"])
                    if digest in used_hashes:
                        blockers.append({"source_player_id": source_player_id, "reason": "opening-XI-player-row-is-duplicated"})
                    else:
                        player["opening_xi_order"] = order
                        ordered_xi.append(player)
                        used_hashes.add(digest)
        remaining = [dict(player) for player in original if str(player["source_row_sha256"]) not in used_hashes]
        xi_complete = lineup_club is not None and len(ordered_xi) == 11 and not blockers
        complete += int(xi_complete)
        output_clubs.append({
            "selector": dict(source_club["selector"]),
            "competition_name": source_club["competition_name"],
            "opening_fixture_date": (lineup_club or {}).get("first_league_fixture_date"),
            "opening_source_match_id": (lineup_club or {}).get("source_match_id"),
            "opening_xi_complete": xi_complete,
            "opening_xi_player_count": len(ordered_xi),
            "opening_xi_blockers": blockers,
            "players": ordered_xi + remaining,
        })
    return {
        "schema_version": SCHEMA,
        "season": dict(source_intake["season"]),
        "sources": {
            "source_intake_sha256": source_intake_sha256,
            "source_capture_sha256": source_intake["source_capture_sha256"],
            "opening_lineup_sha256": lineup_sha256,
            "opening_reconciliation_sha256": reconciliation_sha256,
            "opening_additions_sha256": additions_sha256,
            **selection_sources,
        },
        "summary": {
            "source_club_count": len(output_clubs),
            "opening-lineup-captured-club-count": len(lineup_by_club),
            "opening-xi-complete-club-count": complete,
            "opening-xi-incomplete-or-uncaptured-club-count": len(output_clubs) - complete,
            "profile-facts-pending-count": len(pending),
        },
        "source_clubs": output_clubs,
        "gaps": sorted(pending, key=lambda row: tuple(row["source_selector"].values()) + (row["source_player_id"],)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-intake", required=True, type=Path)
    parser.add_argument("--lineup-capture", required=True, type=Path)
    parser.add_argument("--reconciliation", required=True, type=Path)
    parser.add_argument("--additions", required=True, type=Path)
    parser.add_argument(
        "--source-club-selection",
        type=Path,
        help="canonical explicit source-club projection; requires a canonical source intake",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        intake, intake_sha = _load(args.source_intake, "source intake")
        lineup, lineup_sha = _load(args.lineup_capture, "lineup capture")
        reconciliation, reconciliation_sha = _load(args.reconciliation, "reconciliation")
        additions, additions_sha = _load(args.additions, "opening additions")
        source_club_selection, source_club_selection_sha = (
            _load(args.source_club_selection, "source-club selection")
            if args.source_club_selection is not None
            else (None, None)
        )
        result = materialise(
            source_intake=intake, source_intake_sha256=intake_sha,
            lineup=lineup, lineup_sha256=lineup_sha,
            reconciliation=reconciliation, reconciliation_sha256=reconciliation_sha,
            additions=additions, additions_sha256=additions_sha,
            source_club_selection=source_club_selection,
            source_club_selection_sha256=source_club_selection_sha,
        )
    except PreallocationError as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    incomplete_captured_xi = (
        result["summary"]["opening-lineup-captured-club-count"]
        != result["summary"]["opening-xi-complete-club-count"]
    )
    return 1 if args.strict and (result["gaps"] or incomplete_captured_xi) else 0


if __name__ == "__main__":
    raise SystemExit(main())
