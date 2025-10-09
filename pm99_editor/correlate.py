"""Utilities to correlate team IDs (from player records) with team names (from team records)."""

import argparse
import json
import logging
from collections import defaultdict
from typing import Dict, Tuple

from pm99_editor.io import FDIFile
from pm99_editor.models import TeamRecord

logger = logging.getLogger(__name__)


def correlate_teams_players(players_fdi: str = "DBDAT/JUG98030.FDI", teams_fdi: str = "DBDAT/EQ98030.FDI") -> Tuple[Dict[int, str], Dict[int, int]]:
    """
    Build a mapping of team_id -> team_name by scanning:
      - players_fdi: player records (extract team_id from each PlayerRecord)
      - teams_fdi: decoded team records (use TeamRecord parser to extract team_id and name)

    Returns:
        (team_lookup, team_counts)
        - team_lookup: dict mapping int team_id -> str team_name (where discovered)
        - team_counts: dict mapping int team_id -> int player_count (how many players reference that id)
    """
    # Load players and count team_id usage
    p_fdi = FDIFile(players_fdi)
    p_fdi.load()
    items = getattr(p_fdi, "records_with_offsets", [(None, r) for r in getattr(p_fdi, "records", [])])

    team_counts = defaultdict(int)
    for _, rec in items:
        try:
            tid = getattr(rec, "team_id", None)
            if tid is None:
                continue
            team_counts[int(tid)] += 1
        except Exception:
            # Robustness: skip malformed records
            continue

    # Load teams and try to extract (team_id -> name)
    t_fdi = FDIFile(teams_fdi)
    t_fdi.load()

    team_lookup: Dict[int, str] = {}
    for entry, decoded, _length in t_fdi.iter_decoded_directory_entries():
        try:
            team = TeamRecord(decoded, entry.offset)
            tid = getattr(team, "team_id", 0)
            if tid and tid not in team_lookup:
                team_lookup[int(tid)] = getattr(team, "name", "Unknown Team")
        except Exception:
            # Ignore parse failures for individual team entries
            continue

    # For any team_id referenced by players but not yet matched, attempt a raw-bytes search
    missing = [tid for tid in team_counts.keys() if tid not in team_lookup]
    if missing:
        for entry, decoded, _ in t_fdi.iter_decoded_directory_entries():
            for tid in list(missing):
                try:
                    b = int(tid).to_bytes(2, "little")
                    if b in decoded:
                        try:
                            team = TeamRecord(decoded, entry.offset)
                            team_lookup[tid] = getattr(team, "name", f"Team_{tid}")
                            missing.remove(tid)
                        except Exception:
                            # Even if TeamRecord fails, still record a placeholder
                            team_lookup.setdefault(tid, f"Team_{tid}")
                            try:
                                missing.remove(tid)
                            except ValueError:
                                pass
                except Exception:
                    continue

    return team_lookup, dict(team_counts)


def save_mapping(mapping: Dict[int, str], path: str):
    """Save mapping as JSON (string keys)."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({str(k): v for k, v in mapping.items()}, fh, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Correlate team IDs from players to team names using team FDI.")
    parser.add_argument("--players", default="DBDAT/JUG98030.FDI", help="Players FDI file (default: DBDAT/JUG98030.FDI)")
    parser.add_argument("--teams", default="DBDAT/EQ98030.FDI", help="Teams FDI file (default: DBDAT/EQ98030.FDI)")
    parser.add_argument("--out", help="Optional JSON output path for team mapping")
    args = parser.parse_args()

    mapping, counts = correlate_teams_players(args.players, args.teams)
    total_players = sum(counts.values())
    print(f"Found {len(counts)} team IDs referenced by {total_players} players")

    # Print top-used teams
    sorted_by_count = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    for tid, cnt in sorted_by_count[:50]:
        name = mapping.get(tid, "")
        print(f"{tid}: {name} ({cnt} players)")

    if args.out:
        save_mapping(mapping, args.out)
        print(f"Mapping saved to {args.out}")


if __name__ == "__main__":
    main()