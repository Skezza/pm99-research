#!/usr/bin/env python3
"""Compose canonical season captures from different credited source projects.

Unlike the FootballSquads hybrid merger, this compositor intentionally permits
different repositories and licences.  Each input is retained by path, SHA-256
and complete source metadata; club selectors may not overlap.  It makes no
identity, carrier or player-fact decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.merge_footballsquads_captures import MergeError, canonical_json_bytes
from scripts import season_player_identity_v1 as identity_lib

SCHEMA = "pm99-footballsquads-season-capture-v1"


def _check_identities(clubs: list[dict[str, Any]]) -> int:
    """Reject malformed or self-contradicting optional identities; count them.

    The same provider ID in several clubs is legitimate here (transfers and
    loans are dated reconciliation, not a compositor decision), but one ID
    described as different people is a source conflict that must not be
    carried forward by arbitrarily picking one description.
    """

    count = sum(
        identity_lib.IDENTITY_FIELD in player
        for club in clubs for player in club.get("players") or [] if isinstance(player, Mapping)
    )
    if not count:
        return 0
    audit = identity_lib.audit_entries(identity_lib.entries_from_capture({"clubs": clubs}))
    if audit["malformed_identities"]:
        raise MergeError(f"captures contain malformed source identities: {audit['malformed_identities'][:5]}")
    if audit["metadata_conflicts"]:
        raise MergeError(f"captures describe one provider player ID inconsistently: {audit['metadata_conflicts'][:5]}")
    return count


def read_capture(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise MergeError(f"capture {path} must be canonical JSON")
    if value.get("schema_version") != SCHEMA or not isinstance(value.get("clubs"), list) or not value["clubs"]:
        raise MergeError(f"capture {path} must be a non-empty {SCHEMA}")
    source = value.get("source")
    if not isinstance(source, dict) or any(not source.get(key) for key in ("title", "repository", "revision", "license")):
        raise MergeError(f"capture {path} lacks credited source metadata")
    return value, hashlib.sha256(raw).hexdigest()


def compose(*, inputs: list[tuple[str, Mapping[str, Any], str]], catalog: str, label: str) -> dict[str, Any]:
    if len(inputs) < 2 or not catalog.strip() or not label.strip():
        raise MergeError("composition needs two captures and a non-blank season")
    clubs: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    source_inputs: list[dict[str, Any]] = []
    for name, capture, digest in sorted(inputs, key=lambda value: value[0]):
        source_inputs.append({"capture_name": name, "sha256": digest, "source": dict(capture["source"])})
        for raw in capture["clubs"]:
            if not isinstance(raw, Mapping):
                raise MergeError(f"capture {name} contains a malformed club")
            required = ("country_catalog", "competition_catalog", "club_name", "source_path", "source_sha256")
            selector = tuple(str(raw.get(key) or "") for key in required)
            if not all(selector):
                raise MergeError(f"capture {name} contains an incomplete selector")
            if selector in seen:
                raise MergeError(f"captures duplicate source selector {selector!r}")
            seen.add(selector)
            clubs.append(dict(raw))
    clubs.sort(key=lambda row: (row["country_catalog"], row["competition_catalog"], row["club_name"], row["source_path"]))
    identified = _check_identities(clubs)
    countries = Counter(str(row["country_catalog"]) for row in clubs)
    result = {
        "clubs": clubs,
        "schema_version": SCHEMA,
        "season": {"catalog": catalog.strip(), "label": label.strip()},
        "source": {
            "inputs": source_inputs,
            "license": "mixed; retain and comply with each hash-bound input licence",
            "repository": "multiple-content-addressed-source-captures",
            "revision": "season-source-composition-v1",
            "title": "Composed attributed historical squad captures",
        },
        "summary": {
            "club_count": len(clubs), "club_count_by_country": dict(sorted(countries.items())),
            "competition_catalogs": sorted({f'{r["country_catalog"]}/{r["competition_catalog"]}' for r in clubs}),
            "country_catalogs": sorted(countries),
            "player_count": sum(len(row.get("players") or []) for row in clubs),
            "player_rows_with_unresolved_facts": sum(
                bool(player.get("unresolved_fields")) for row in clubs for player in row.get("players") or []
            ),
        },
    }
    if identified:
        result["summary"]["player_rows_with_provider_identity"] = identified
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="append", required=True, type=Path)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        inputs = [(path.name, *read_capture(path)) for path in args.capture]
        result = compose(inputs=inputs, catalog=args.catalog, label=args.label)
    except (OSError, json.JSONDecodeError, MergeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
