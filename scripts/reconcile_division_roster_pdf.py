#!/usr/bin/env python3
"""Reconcile a PM99 roster-listing PDF against JUG98030.FDI (script wrapper)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script from repo root without installing the package.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.roster_reconcile import (
    print_reconcile_run_summary,
    reconcile_pdf_rosters,
    write_reconcile_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile PM99 roster listing PDF against JUG98030.FDI")
    parser.add_argument("--pdf", required=True, help="Path to PM99 listing PDF (e.g. '2nd div.pdf')")
    parser.add_argument("--player-file", default="DBDAT/JUG98030.FDI", help="Player FDI file path")
    parser.add_argument("--default-window", type=int, default=800, help="Default club mention context window")
    parser.add_argument("--wide-window", type=int, default=10000, help="Wide fallback context window")
    parser.add_argument("--json-output", required=True, help="Output JSON path")
    parser.add_argument("--csv-output", required=True, help="Output CSV path (detailed rows)")
    parser.add_argument("--team-summary-csv", help="Optional output CSV path for per-team summaries")
    parser.add_argument("--team", help="Optional team label/query filter (e.g. 'Stoke City' or 'Stoke C.')")
    parser.add_argument("--name-hints", help="Optional CSV/JSON name hints for disambiguation")
    args = parser.parse_args()

    result = reconcile_pdf_rosters(
        pdf_path=args.pdf,
        player_file=args.player_file,
        default_window=args.default_window,
        wide_window=args.wide_window,
        team_filter=args.team,
        name_hints_path=args.name_hints,
    )
    write_reconcile_outputs(
        result,
        json_output=args.json_output,
        csv_output=args.csv_output,
        team_summary_csv=args.team_summary_csv,
    )
    print_reconcile_run_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
