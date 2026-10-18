#!/usr/bin/env python3
"""Audit the direct indexed EQ-to-ENT manager contract without writing files.

Run from the PM99RE root, for example:

  python3 scripts/audit_manager_team_contract.py \
    --eq /path/to/EQ98030.FDI --ent /path/to/ENT98030.FDI --out /tmp/manager-contract.json

The default JSON deliberately contains counts and record ids, not biography
text.  Use ``--include-profile-text`` only for a local inspection file.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITOR_ROOT = ROOT / "upstream" / "pm99-skezmod-db-editor"
if str(EDITOR_ROOT) not in sys.path:
    sys.path.insert(0, str(EDITOR_ROOT))

from app.ent_manager_profiles import parse_indexed_ent_manager_profile  # noqa: E402
from app.eq_team_manager_links import parse_indexed_eq_manager_links  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eq", required=True, type=Path)
    parser.add_argument("--ent", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--include-profile-text", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    eq_bytes = args.eq.read_bytes()
    ent_bytes = args.ent.read_bytes()
    eq = IndexedFDIFile.from_bytes(eq_bytes)
    ent = IndexedFDIFile.from_bytes(ent_bytes)

    profiles: dict[int, object] = {}
    profile_format_counts: Counter[str] = Counter()
    for entry in ent.entries:
        payload = ent_bytes[entry.payload_offset : entry.payload_offset + entry.payload_length]
        try:
            profile = parse_indexed_ent_manager_profile(payload, record_id=entry.record_id)
        except ValueError:
            continue
        profiles[entry.record_id] = profile
        profile_format_counts[profile.format] += 1

    link_count_distribution: Counter[int] = Counter()
    parsed_team_count = 0
    no_manager_count = 0
    unresolved_count = 0
    rows: list[dict[str, object]] = []
    for entry in eq.entries:
        payload = eq_bytes[entry.payload_offset : entry.payload_offset + entry.payload_length]
        try:
            links = parse_indexed_eq_manager_links(payload)
        except ValueError:
            continue
        parsed_team_count += 1
        link_count_distribution[links.link_count] += 1
        active_id = links.active_manager_record_id
        profile = profiles.get(active_id) if active_id is not None else None
        if active_id is None:
            no_manager_count += 1
        if active_id is not None and profile is None:
            unresolved_count += 1
        row: dict[str, object] = {
            "team_record_id": entry.record_id,
            "record_mode": links.record_mode,
            "manager_link_count": links.link_count,
            "manager_record_ids": list(links.manager_record_ids),
            "active_manager_record_id": active_id,
            "active_manager_resolved": profile is not None,
            "active_manager_profile_format": getattr(profile, "format", None),
            "has_profile_text": bool(getattr(profile, "profile_text", None)),
        }
        if args.include_profile_text and profile is not None:
            row["active_manager_display_name"] = profile.display_name
            row["active_manager_profile_text"] = profile.profile_text
        rows.append(row)

    result = {
        "schema": "pm99-manager-team-contract-v1",
        "source": {"eq_record_count": eq.record_count, "ent_record_count": ent.record_count},
        "summary": {
            "modern_team_count": parsed_team_count,
            "manager_link_count_distribution": dict(sorted(link_count_distribution.items())),
            "teams_without_manager_link": no_manager_count,
            "unresolved_active_manager_count": unresolved_count,
            "parsed_ent_manager_profile_count": len(profiles),
            "ent_profile_format_distribution": dict(sorted(profile_format_counts.items())),
        },
        "teams": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
