#!/usr/bin/env python3
"""Capture early-season 2015/16 managers from pinned Transfermarkt squads.

This is a deliberately narrow source pass for the 2015 world package.  The
older squad close-out already cached a set of exact Transfermarkt club pages
with ``saison_id/2015``.  For an explicitly unresolved club, that page is a
stronger identity link than a fresh name search.  We use it to read the
club's published manager history at the fixed early-season snapshot of
2015-09-01.

The result is source evidence only.  It neither picks a PM99 ENT record nor
writes a database.  A missing, ambiguous or non-representable manager stays
an explicit gap; this command has no current-manager or native fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import capture_opening_manager_history_supplements_v1 as history  # noqa: E402
from scripts import capture_transfermarkt_opening_lineups_v1 as opening  # noqa: E402


SCHEMA = "pm99-world-2015-transfermarkt-squad-snapshot-manager-history-v5"
CANDIDATE_SCHEMA = "pm99-world-2015-editorial-fallback-ratings-v1"
WIKIPEDIA_SCHEMA = "pm99-world-2015-multilingual-wikipedia-manager-history-v3"
AS_OF = date(2015, 9, 1)
DETAIL_URL_RE = re.compile(
    r"https?://(?:www\.)?transfermarkt\.(?:com|co\.uk)/([^/]+)/kader/verein/([1-9]\d*)/saison_id/2015(?:[/?#\"']|$)",
    re.I,
)


class SnapshotManagerError(ValueError):
    """A pinned historical squad cannot safely support a manager fact."""


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _load(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotManagerError(f"cannot read {label}: {path}") from exc
    if not isinstance(value, dict):
        raise SnapshotManagerError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _safe_manager_name(value: str) -> bool:
    """Return whether the published display name is safely writable by PM99.

    The compiler's historical name lane is Windows-1252, not arbitrary
    Unicode.  Do not silently strip a Cyrillic, Greek or Hebrew manager name:
    a separate Latin display source is required in that situation.
    """

    if not value or any(character in value for character in "\r\n\t"):
        return False
    try:
        value.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return len(value) <= 63


def _pinned_identity(payload: bytes) -> tuple[str, int, str]:
    """Read one exact 2015 Transfermarkt club identity from a cached squad."""

    matches = {
        (match.group(1), int(match.group(2)))
        for match in DETAIL_URL_RE.finditer(payload.decode("utf-8", errors="replace"))
    }
    if len(matches) != 1:
        raise SnapshotManagerError(
            f"pinned squad cache has {len(matches)} unique 2015 Transfermarkt club identities"
        )
    slug, club_id = next(iter(matches))
    source_url = f"https://www.transfermarkt.com/{slug}/kader/verein/{club_id}/saison_id/2015"
    return slug, club_id, source_url


def _candidate_index(candidate: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    if candidate.get("schema_version") != CANDIDATE_SCHEMA:
        raise SnapshotManagerError("2015 source candidate has an unsupported schema")
    rows = candidate.get("carrier_drafts")
    if not isinstance(rows, list):
        raise SnapshotManagerError("2015 source candidate has no carrier drafts")
    result: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("carrier_id"), int):
            raise SnapshotManagerError("2015 source candidate has a malformed carrier draft")
        carrier_id = int(row["carrier_id"])
        if carrier_id in result:
            raise SnapshotManagerError("2015 source candidate has duplicate carrier drafts")
        club = row.get("club")
        manager = row.get("manager")
        if not isinstance(club, Mapping) or not isinstance(manager, Mapping):
            raise SnapshotManagerError("2015 source candidate draft has no club or manager section")
        selector = club.get("source_selector")
        if not isinstance(selector, Mapping) or not all(
            isinstance(selector.get(key), str) and selector[key].strip()
            for key in ("country_catalog", "competition_catalog", "club_name")
        ):
            raise SnapshotManagerError("2015 source candidate draft has an incomplete source selector")
        result[carrier_id] = row
    return result


def _unresolved_scope(
    wikipedia: Mapping[str, Any], *, candidate_sha256: str,
) -> dict[int, Mapping[str, Any]]:
    if wikipedia.get("schema_version") != WIKIPEDIA_SCHEMA:
        raise SnapshotManagerError("multilingual Wikipedia receipt has an unsupported schema")
    sources = wikipedia.get("sources")
    rows = wikipedia.get("rows")
    if not isinstance(sources, Mapping) or sources.get("source_candidate_sha256") != candidate_sha256:
        raise SnapshotManagerError("multilingual Wikipedia receipt is not bound to this source candidate")
    if not isinstance(rows, list):
        raise SnapshotManagerError("multilingual Wikipedia receipt has no rows")
    result: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise SnapshotManagerError("multilingual Wikipedia receipt has a malformed row")
        carrier_id = row.get("carrier_id")
        status = str(row.get("status") or "")
        if not isinstance(carrier_id, int) or not status:
            raise SnapshotManagerError("multilingual Wikipedia receipt row has no carrier or status")
        if status.startswith("requires-review-"):
            if carrier_id in result:
                raise SnapshotManagerError("multilingual Wikipedia receipt has duplicate unresolved carriers")
            result[carrier_id] = row
    return result


def _pinned_squad_file(cache_root: Path, country: str, carrier_id: int) -> Path | None:
    matches = sorted((cache_root / country).glob(f"{carrier_id}-*.html"))
    if len(matches) > 1:
        raise SnapshotManagerError(
            f"pinned squad cache has multiple files for {country}/{carrier_id}"
        )
    return matches[0] if matches else None


def capture(
    *,
    candidate: Mapping[str, Any],
    candidate_sha256: str,
    wikipedia: Mapping[str, Any],
    wikipedia_sha256: str,
    pinned_squad_cache: Path,
    manager_history_cache: opening.SnapshotCache,
) -> dict[str, Any]:
    candidates = _candidate_index(candidate)
    unresolved = _unresolved_scope(wikipedia, candidate_sha256=candidate_sha256)
    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    pinned_used: list[dict[str, str]] = []
    missing_candidate_count = 0
    missing_pinned_squad_count = 0
    pinned_candidate_count = 0

    for carrier_id in sorted(unresolved):
        draft = candidates.get(carrier_id)
        source_row = unresolved[carrier_id]
        if draft is None:
            # The original all-source candidate intentionally covered 395 of
            # the 451 package carriers.  This pass must not misrepresent an
            # unrepresented carrier as a failed pinned-squad lookup.
            missing_candidate_count += 1
            continue
        club = draft["club"]
        selector = club["source_selector"]
        country = str(selector["country_catalog"])
        name = str(club.get("source_club_name") or selector["club_name"])
        path = _pinned_squad_file(pinned_squad_cache, country, carrier_id)
        if path is None:
            missing_pinned_squad_count += 1
            continue
        pinned_candidate_count += 1
        try:
            squad_payload = path.read_bytes()
            slug, club_id, squad_url = _pinned_identity(squad_payload)
            squad_sha = hashlib.sha256(squad_payload).hexdigest()
            pinned_used.append({
                "cache_relative_path": path.relative_to(pinned_squad_cache).as_posix(),
                "sha256": squad_sha,
                "source_url": squad_url,
            })
            history_url = f"{opening.BASE_URL}/{slug}/mitarbeiterhistorie/verein/{club_id}"
            history_key = f"manager-history/2015-snapshot/{club_id}.html"
            manager_payload = manager_history_cache.get(history_url, history_key)
            manager_name, manager_id = history.manager_at_date(manager_payload, AS_OF)
            if not _safe_manager_name(manager_name):
                raise SnapshotManagerError("published manager display name requires a reviewed PM99 Latin spelling")
            manager_snapshot = manager_history_cache.used[history_key]
            rows.append({
                "carrier_id": carrier_id,
                "source_club_name": name,
                "source_selector": {
                    key: str(selector[key]) for key in ("country_catalog", "competition_catalog", "club_name")
                },
                "snapshot_as_of": AS_OF.isoformat(),
                "manager_name": manager_name,
                "source_name": "Transfermarkt published club manager history",
                "source_url": history_url,
                "source_snapshot_sha256": manager_snapshot["sha256"],
                "pinned_2015_squad": {
                    "source_url": squad_url,
                    "source_snapshot_sha256": squad_sha,
                    "cache_relative_path": path.relative_to(pinned_squad_cache).as_posix(),
                    "transfermarkt_club_id": club_id,
                },
                "reason": (
                    f"manager id {manager_id} uniquely covers the fixed 2015-09-01 "
                    f"early-season snapshot for the exact club on the cached 2015 squad page"
                ),
            })
        except (OSError, history.ManagerHistoryError, opening.CaptureError, SnapshotManagerError) as exc:
            gaps.append({
                "carrier_id": carrier_id,
                "source_club_name": name,
                "reason": str(exc),
            })

    status_counts = Counter(str(row.get("status") or "") for row in unresolved.values())
    return {
        "schema_version": SCHEMA,
        "policy": (
            "source-only; only explicitly unresolved multilingual-Wikipedia carriers; "
            "exact historical Transfermarkt club identity from a cached 2015 squad page; "
            "manager tenure uniquely covering 2015-09-01; no current/native fallback; no PM99 write"
        ),
        "sources": {
            "source_candidate_sha256": candidate_sha256,
            "multilingual_wikipedia_history_sha256": wikipedia_sha256,
            "pinned_squad_cache_root": str(pinned_squad_cache),
            "pinned_2015_squad_files": sorted(pinned_used, key=lambda row: row["cache_relative_path"]),
            "manager_history_cache_files": [
                manager_history_cache.used[key] for key in sorted(manager_history_cache.used)
            ],
        },
        "coverage": {
            "early_season_snapshot": AS_OF.isoformat(),
            "wikipedia_unresolved_carrier_count": len(unresolved),
            "wikipedia_unresolved_status_counts": dict(sorted(status_counts.items())),
            "unresolved_carrier_absent_from_original_source_candidate_count": missing_candidate_count,
            "source_candidate_carrier_without_pinned_historical_squad_count": missing_pinned_squad_count,
            "pinned_historical_squad_candidate_count": pinned_candidate_count,
            "dated_transfermarkt_manager_match_count": len(rows),
            "unresolved_pinned_historical_squad_count": len(gaps),
        },
        "rows": rows,
        "gaps": gaps,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-candidate", required=True, type=Path)
    parser.add_argument("--multilingual-wikipedia-history", required=True, type=Path)
    parser.add_argument("--pinned-squad-cache", required=True, type=Path)
    parser.add_argument("--manager-history-cache", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise SnapshotManagerError(f"refusing to overwrite source receipt: {args.output}")
        candidate, candidate_sha = _load(args.source_candidate, "source candidate")
        wikipedia, wikipedia_sha = _load(args.multilingual_wikipedia_history, "multilingual Wikipedia history")
        result = capture(
            candidate=candidate,
            candidate_sha256=candidate_sha,
            wikipedia=wikipedia,
            wikipedia_sha256=wikipedia_sha,
            pinned_squad_cache=args.pinned_squad_cache,
            manager_history_cache=opening.SnapshotCache(
                args.manager_history_cache, offline=args.offline, delay=args.delay,
            ),
        )
    except (OSError, SnapshotManagerError, opening.CaptureError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["coverage"], sort_keys=True))
    return 1 if args.strict and result["gaps"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
