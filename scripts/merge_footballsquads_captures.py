#!/usr/bin/env python3
"""Merge reviewed FootballSquads captures into one logical PM99 season source.

Some leagues use a split-year campaign directory (``2015-2016``); others use
the 2015 calendar year.  This tool preserves every source-row hash while
making that mixed but historically correct source set one canonical input for
a worldwide season ledger.  It does not resolve club identity or write PM99.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "pm99-footballsquads-season-capture-v1"
# Retain these legacy defaults for callers which reproduce the 2015 receipt.
# New callers must name the logical historical season explicitly; a generic
# merger must not label every combined source as 2015/16.
MERGED_CATALOG = "2015-world-hybrid"
MERGED_LABEL = "2015/16 plus 2015 calendar-year leagues"


class MergeError(ValueError):
    """An input is not a compatible canonical FootballSquads capture."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MergeError(f"cannot parse capture {path}") from exc
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise MergeError(f"capture {path} must be canonical JSON")
    if value.get("schema_version") != SCHEMA:
        raise MergeError(f"capture {path} does not use {SCHEMA}")
    if not isinstance(value.get("clubs"), list) or not value["clubs"]:
        raise MergeError(f"capture {path} has no clubs")
    source = value.get("source")
    if not isinstance(source, dict):
        raise MergeError(f"capture {path} has no source metadata")
    for key in ("title", "repository", "revision", "license"):
        if not isinstance(source.get(key), str) or not source[key]:
            raise MergeError(f"capture {path} source.{key} is missing")
    season = value.get("season")
    if not isinstance(season, dict) or not isinstance(season.get("catalog"), str) or not isinstance(season.get("label"), str):
        raise MergeError(f"capture {path} has malformed season metadata")
    return value, sha256_bytes(raw)


def merge_captures(
    *,
    captures: list[tuple[str, Mapping[str, Any], str]],
    merged_catalog: str = MERGED_CATALOG,
    merged_label: str = MERGED_LABEL,
) -> dict[str, Any]:
    """Merge retained captures into a named logical historical season.

    ``merged_catalog`` and ``merged_label`` describe the logical release
    season, not a claim that a calendar-year source has been recategorised.
    The individual source catalogues and labels remain hash-bound in
    ``source.inputs``.
    """

    if len(captures) < 2:
        raise MergeError("a hybrid source needs at least two captures")
    if not isinstance(merged_catalog, str) or not merged_catalog.strip():
        raise MergeError("merged_catalog must be a non-blank string")
    if not isinstance(merged_label, str) or not merged_label.strip():
        raise MergeError("merged_label must be a non-blank string")
    capture_names = [name for name, _value, _sha in captures]
    if any(not isinstance(name, str) or not name for name in capture_names) or len(capture_names) != len(set(capture_names)):
        raise MergeError("captures must have unique non-blank names")
    repositories = {str(value["source"]["repository"]) for _name, value, _sha in captures}
    revisions = {str(value["source"]["revision"]) for _name, value, _sha in captures}
    licenses = {str(value["source"]["license"]) for _name, value, _sha in captures}
    if len(repositories) != 1 or len(revisions) != 1 or len(licenses) != 1:
        raise MergeError("captures must come from one identical repository revision and license")

    clubs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    source_inputs: list[dict[str, str]] = []
    blocked_sources: list[dict[str, str]] = []
    seen_blocked_sources: set[tuple[str, str]] = set()
    for name, capture, digest in sorted(captures, key=lambda row: row[0]):
        source_inputs.append({
            "capture_name": name,
            "sha256": digest,
            "catalog": str(capture["season"]["catalog"]),
            "label": str(capture["season"]["label"]),
        })
        for club in capture["clubs"]:
            if not isinstance(club, dict):
                raise MergeError(f"capture {name} has malformed club row")
            key = tuple(str(club.get(field) or "") for field in (
                "country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256",
            ))
            if not all(key):
                raise MergeError(f"capture {name} has incomplete source selector")
            if key in seen:
                raise MergeError(f"captures overlap source selector {key!r}")
            seen.add(key)
            clubs.append(dict(club))
        capture_blockers = capture.get("blocked_sources")
        if capture_blockers is None:
            continue
        if not isinstance(capture_blockers, list):
            raise MergeError(f"capture {name} blocked_sources must be a list")
        for blocker in capture_blockers:
            if not isinstance(blocker, Mapping) or set(blocker) != {"source_path", "source_sha256", "reason"}:
                raise MergeError(f"capture {name} has malformed blocked source")
            source_path = blocker.get("source_path")
            source_sha256 = blocker.get("source_sha256")
            reason = blocker.get("reason")
            if (
                not isinstance(source_path, str)
                or not source_path
                or not isinstance(source_sha256, str)
                or len(source_sha256) != 64
                or not isinstance(reason, str)
                or not reason
            ):
                raise MergeError(f"capture {name} has malformed blocked source")
            selector = (source_path, source_sha256)
            if selector in seen_blocked_sources:
                raise MergeError(f"captures duplicate blocked source {source_path!r}")
            seen_blocked_sources.add(selector)
            blocked_sources.append(
                {"source_path": source_path, "source_sha256": source_sha256, "reason": reason}
            )
    clubs.sort(key=lambda club: (
        str(club["country_catalog"]), str(club["competition_catalog"]), str(club["club_name"]), str(club["source_path"])
    ))
    result = {
        "schema_version": SCHEMA,
        "source": {
            "title": "footballcsv/cache.footballsquads hybrid historic capture",
            "repository": next(iter(repositories)),
            "revision": next(iter(revisions)),
            "license": next(iter(licenses)),
            "inputs": source_inputs,
        },
        "season": {"catalog": merged_catalog.strip(), "label": merged_label.strip()},
        "clubs": clubs,
        "summary": {
            "club_count": len(clubs),
            "player_count": sum(len(club.get("players") or []) for club in clubs),
            "player_rows_with_unresolved_facts": sum(
                1 for club in clubs for player in club.get("players") or []
                if isinstance(player, dict) and player.get("unresolved_fields")
            ),
            "country_catalogs": sorted({str(club["country_catalog"]) for club in clubs}),
            "competition_catalogs": sorted({
                f"{club['country_catalog']}/{club['competition_catalog']}" for club in clubs
            }),
            "club_count_by_country": dict(sorted(Counter(str(club["country_catalog"]) for club in clubs).items())),
        },
    }
    if blocked_sources:
        result["blocked_sources"] = sorted(blocked_sources, key=lambda row: (row["source_path"], row["source_sha256"]))
        result["summary"]["blocked_source_count"] = len(blocked_sources)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="append", required=True, type=Path)
    parser.add_argument("--merged-catalog", default=MERGED_CATALOG)
    parser.add_argument("--merged-label", default=MERGED_LABEL)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        captures = []
        for path in args.capture:
            value, digest = _read(path)
            captures.append((path.name, value, digest))
        merged = merge_captures(
            captures=captures,
            merged_catalog=args.merged_catalog,
            merged_label=args.merged_label,
        )
    except (OSError, MergeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(merged))
    print(json.dumps(merged["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
