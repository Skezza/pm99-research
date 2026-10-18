#!/usr/bin/env python3
"""Materialise the prior-table English rating layer for every playable season.

This is the batch counterpart to ``materialise_english_rating_layer_v1``.  It
does not compile games or replace a prior recipe: every output is a new,
hash-bound policy layer which the next ingress revision consumes.  Re-running
with unchanged inputs reuses byte-identical artifacts; changed inputs require
a new output root, preventing accidental historical rewrites.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.materialise_english_rating_layer_v1 import materialise  # noqa: E402
from scripts.pm99_season_play_v1 import REVISIONS  # noqa: E402


SCHEMA = "pm99-english-preseason-rating-policy-cascade-v2"


class CascadeError(ValueError):
    """A season cannot be safely cascaded through the policy layer."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CascadeError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise CascadeError(f"{path} must contain a JSON object")
    return value, raw


def _write_or_reuse(path: Path, value: Mapping[str, Any]) -> tuple[str, str]:
    raw = _canonical_bytes(value)
    digest = _sha256(raw)
    if path.exists():
        if path.read_bytes() != raw:
            raise CascadeError(f"refusing to replace a different existing output: {path}")
        return "reused", digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return "built", digest


def _latest_preallocation(*, season: str) -> Path:
    """Prefer the newest composed opening package, then the shared capture."""
    chain_root = ROOT / ".local/season-english-source-chain-v1" / season
    candidates = list(chain_root.glob("r*/opening-squad-preallocation.json"))

    def key(path: Path) -> tuple[int, str]:
        name = path.parent.name
        try:
            return int(name[1:]), str(path)
        except ValueError:
            return -1, str(path)

    if candidates:
        return max(candidates, key=key)
    return ROOT / ".local/transfermarkt-opening-plans-current-v1" / season / "opening-squad-preallocation.json"


def cascade(*, output_root: Path, seasons: Sequence[str]) -> dict[str, Any]:
    output_root = output_root.resolve()
    selected = sorted(set(seasons))
    invalid = sorted(set(selected) - set(REVISIONS))
    if invalid:
        raise CascadeError("unsupported seasons: " + ", ".join(invalid))
    rows: list[dict[str, Any]] = []
    for season in selected:
        revision = REVISIONS[season]
        preallocation_path = _latest_preallocation(season=season)
        standings_path = ROOT / ".local/season-english-preseason-standings-v1" / season / "preseason-standings.json"
        preallocation, preallocation_raw = _read(preallocation_path)
        standings, standings_raw = _read(standings_path)
        layer, audit = materialise(
            preallocation=preallocation,
            preallocation_sha256=_sha256(preallocation_raw),
            preseason_standings=standings,
            preseason_standings_sha256=_sha256(standings_raw),
        )
        child = output_root / season
        _layer_status, layer_sha256 = _write_or_reuse(child / "english-rating-layer.json", layer)
        _audit_status, audit_sha256 = _write_or_reuse(child / "english-rating-audit.json", audit)
        prior_four_unmatched = [
            row["club"] for row in audit["gaps"]
            if row["reason"] == "club-missing-from-prior-english-standing"
        ]
        ambiguous = [row for row in audit["gaps"] if row["reason"] == "club-ambiguous-in-prior-english-standing"]
        if ambiguous:
            raise CascadeError(f"{season} has ambiguous prior-table club matches")
        rows.append({
            "season": season,
            "source_revision": revision,
            "preallocation": str(preallocation_path.relative_to(ROOT)),
            "state": "complete-with-explicit-non-league-newcomers" if prior_four_unmatched else "complete",
            "english_club_count": audit["coverage"]["english_club_count"],
            "rated_player_count": audit["coverage"]["rated_player_count"],
            "prior_four_division_unmatched_clubs": sorted(prior_four_unmatched),
            "outputs": {
                "english_rating_layer": str((child / "english-rating-layer.json").relative_to(ROOT)),
                "english_rating_layer_sha256": layer_sha256,
                "english_rating_audit": str((child / "english-rating-audit.json").relative_to(ROOT)),
                "english_rating_audit_sha256": audit_sha256,
            },
        })
    result = {
        "schema_version": SCHEMA,
        "policy": "completed-prior-season-table-to-current-division-strength-v2",
        "state": "complete",
        "seasons": rows,
        "summary": {
            "season_count": len(rows),
            "english_club_count": sum(int(row["english_club_count"]) for row in rows),
            "rated_player_count": sum(int(row["rated_player_count"]) for row in rows),
            "season_count_with_non_league_newcomers": sum(bool(row["prior_four_division_unmatched_clubs"]) for row in rows),
        },
    }
    _write_or_reuse(output_root / "cascade-receipt.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / ".local/season-english-preseason-rating-policy-v4")
    parser.add_argument("season", nargs="*", default=sorted(REVISIONS))
    args = parser.parse_args(argv)
    try:
        result = cascade(output_root=args.output_root, seasons=args.season)
    except CascadeError as exc:
        parser.error(str(exc))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
