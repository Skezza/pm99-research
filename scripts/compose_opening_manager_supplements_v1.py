#!/usr/bin/env python3
"""Compose independently hash-bound dated manager supplements without guessing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "pm99-opening-manager-supplement-v1"


class ManagerSupplementCompositionError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _selector(row: Mapping[str, Any]) -> tuple[str, str, str]:
    source = row.get("source_selector") or {}
    key = tuple(str(source.get(field) or "") for field in ("country_catalog", "competition_catalog", "club_name"))
    if not all(key):
        raise ManagerSupplementCompositionError("manager supplement row has an incomplete selector")
    return key  # type: ignore[return-value]


def compose(inputs: Sequence[tuple[Mapping[str, Any], str]]) -> dict[str, Any]:
    managers: dict[tuple[str, str, str], dict[str, Any]] = {}
    years: set[int] = set()
    sources = []
    for document, digest in inputs:
        if document.get("schema_version") != SCHEMA:
            raise ManagerSupplementCompositionError(f"manager supplement must have schema {SCHEMA}")
        years.add(int(document["season_start_year"]))
        sources.append({"sha256": digest, "source": document.get("sources")})
        for row in document.get("managers") or []:
            key = _selector(row)
            previous = managers.get(key)
            if previous is not None and (
                previous.get("manager_name") != row.get("manager_name")
                or previous.get("opening_fixture_date") != row.get("opening_fixture_date")
            ):
                raise ManagerSupplementCompositionError(f"conflicting dated manager evidence for {key}")
            managers[key] = dict(row)
    if len(years) != 1:
        raise ManagerSupplementCompositionError("manager supplements target different seasons")
    rows = [managers[key] for key in sorted(managers)]
    return {
        "schema_version": SCHEMA,
        "season_start_year": next(iter(years)),
        "sources": {"composition_policy": "exact-selector-date-manager-agreement-v1", "inputs": sources},
        "summary": {"supplemented_manager_count": len(rows), "unresolved_manager_count": 0},
        "managers": rows,
        "gaps": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    loaded = []
    for path in args.input:
        payload = path.read_bytes()
        loaded.append((json.loads(payload), hashlib.sha256(payload).hexdigest()))
    try:
        result = compose(loaded)
    except (KeyError, TypeError, ValueError, ManagerSupplementCompositionError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical_json_bytes(result))
    print(json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
