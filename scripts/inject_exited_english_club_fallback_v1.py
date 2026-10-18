#!/usr/bin/env python3
"""Fill a fixed English slot for a club expelled before playing a league match."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def club_row(document: dict, key: str, club: str) -> dict:
    matches = [row for row in document[key] if row.get("club") == club or row.get("selector", {}).get("club_name") == club]
    if len(matches) != 1:
        raise ValueError(f"{club}: expected one {key} row, got {len(matches)}")
    return copy.deepcopy(matches[0])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-chain", type=Path, required=True)
    parser.add_argument("--prior-chain", type=Path, required=True)
    parser.add_argument("--current-kit", type=Path, required=True)
    parser.add_argument("--prior-kit", type=Path, required=True)
    parser.add_argument("--output-chain", type=Path, required=True)
    parser.add_argument("--output-kit", type=Path, required=True)
    parser.add_argument("--club", required=True)
    parser.add_argument("--manager", required=True)
    parser.add_argument("--manager-source-url", required=True)
    parser.add_argument("--effective-date", required=True)
    args = parser.parse_args()
    names = ["opening-squad-preallocation.json", "english-opening-layer.json",
             "english-manager-layer.json", "english-rating-layer.json"]
    current = {name: load(args.current_chain / name) for name in names}
    prior = {name: load(args.prior_chain / name) for name in names}
    club = args.club
    pre = club_row(prior[names[0]], "source_clubs", club)
    pre["selector"].update({"competition_catalog": "flone", "source_path": "declared-exited-club-fallback"})
    pre["competition_name"] = "English Football League One"
    pre["opening_fixture_date"] = args.effective_date
    current[names[0]]["source_clubs"].append(pre)
    opening = club_row(prior[names[1]], "clubs", club)
    opening.update({"fixture_date": args.effective_date, "source_match_id": "no-league-fixture-expelled",
                    "source_url": args.manager_source_url,
                    "squad_snapshot_policy": "opening-window-through-august-31-exited-club-prior-season-squad-fallback"})
    current[names[1]]["clubs"].append(opening)
    manager = {"club": club, "fixture_date": args.effective_date, "manager_name": args.manager,
               "resolution_method": "source-cited-exited-club-opening-manager",
               "source_snapshot_sha256": hashlib.sha256(args.manager_source_url.encode()).hexdigest(),
               "source_url": args.manager_source_url}
    current[names[2]]["rows"].append(manager)
    current[names[3]]["rows"].append(club_row(prior[names[3]], "rows", club))
    kit = load(args.current_kit)
    kit_row = club_row(load(args.prior_kit), "clubs", club)
    kit_row.update({"policy": "exited-club-prior-season-source-backed-style-fallback",
                    "facts": "Club was expelled before playing; prior-season sourced style retained as an explicit fixed-slot fallback"})
    kit["clubs"].append(kit_row)
    args.output_chain.mkdir(parents=True, exist_ok=True)
    args.output_kit.parent.mkdir(parents=True, exist_ok=True)
    outputs = []
    for name in names:
        path = args.output_chain / name
        path.write_bytes(canonical(current[name])); outputs.append(str(path))
    args.output_kit.write_bytes(canonical(kit)); outputs.append(str(args.output_kit))
    audit = {"schema_version": "pm99-exited-english-club-fallback-audit-v1",
             "season": current[names[0]].get("season"), "club": club,
             "manager": manager, "policy": "prior-season-squad-and-kit-explicit-fallback",
             "outputs": outputs}
    audit_bytes = canonical(audit)
    for name in ("english-opening-evidence-composition-audit.json", "english-opening-manager-audit.json",
                 "english-rating-audit.json"):
        (args.output_chain / name).write_bytes(audit_bytes)
    print(json.dumps({"club": club, "status": "injected"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
