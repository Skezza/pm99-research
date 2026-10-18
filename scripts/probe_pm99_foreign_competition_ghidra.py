#!/usr/bin/env python3
"""Read-only PM99 competition-call-chain probe through the approved GhidraMCP.

The probe deliberately limits itself to the two already observed lookup
functions.  It does not alter the Ghidra project, executable, database, or
runtime process.  Its JSON output is intended to be captured with the runner
evidence when deciding whether a live-memory watch can be made specific enough
to distinguish candidate-pool selection from a generic carrier lookup.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from tiny_m73_pm9x_ghidramcp_probe import McpHttpClient, ProbeError, normalize_project_path


# The base image is preferred.  The second entry is retained solely as a
# read-only diagnostic fallback because the approved project currently indexes
# it separately; output always states which image actually opened.
PM99_PROGRAMS = (
    "/PM99/MANAGPRE.EXE",
    "/PM99_SKEZMOD/MANAGPRE.EXE",
)
TARGETS = {
    "pre_name_copy_caller_FUN_004b1340": "0x004b1340",
    "carrier_lookup_FUN_004b5c20": "0x004b5c20",
}


def call_read_only_probe(url: str, timeout: float, decompile_timeout: int) -> dict[str, Any]:
    """Return raw static evidence without project mutation."""
    client = McpHttpClient(url, timeout=timeout)
    client.initialize()
    available_tools = client.list_tools()
    required_tools = {"manage_project", "read_functions", "decompile_code"}
    missing = sorted(required_tools - available_tools)
    if missing:
        raise ProbeError(f"PM99 probe requires unavailable tools: {', '.join(missing)}")

    inventory = client.call_tool("list_programs", {"page_size": 100})
    program_rows = list(inventory.get("data") or [])
    program_paths = sorted(normalize_project_path(str(row.get("path") or "")) for row in program_rows)
    listed_candidates = [program for program in PM99_PROGRAMS if program in program_paths]
    if not listed_candidates:
        return {
            "read_only": True,
            "program_candidates": list(PM99_PROGRAMS),
            "pm99_program_available": False,
            "available_tools": sorted(available_tools),
            "project_program_paths": program_paths,
            "conclusion": (
                "The approved Ghidra project does not contain MANAGPRE.EXE; "
                "no static competition-call-chain inference was attempted."
            ),
        }

    program_info: dict[str, Any] | None = None
    opened_program = ""
    lookup_errors: dict[str, str] = {}
    for candidate in listed_candidates:
        try:
            candidate_info = client.call_tool(
                "manage_project", {"file_name": candidate, "action": "get_program_info"}
            )
        except ProbeError as exc:
            lookup_errors[candidate] = str(exc)
            continue
        if candidate_info.get("data"):
            program_info = candidate_info
            opened_program = candidate
            break
        lookup_errors[candidate] = "manage_project returned no data"
    if program_info is None:
        return {
            "read_only": True,
            "program_candidates": list(PM99_PROGRAMS),
            "pm99_program_available": False,
            "available_tools": sorted(available_tools),
            "project_program_paths": program_paths,
            "program_lookup_errors": lookup_errors,
            "conclusion": (
                "The approved Ghidra project inventory cannot open MANAGPRE.EXE; "
                "no static competition-call-chain inference was attempted."
            ),
        }
    if not program_info.get("data"):
        raise ProbeError(f"PM99 program is unavailable at {PM99_PROGRAM}")

    functions = client.call_tool(
        "read_functions",
        {"file_name": opened_program, "page_size": 5000},
    )
    rows = list(functions.get("data") or [])
    matched_functions = []
    target_addresses = {address.lower() for address in TARGETS.values()}
    for row in rows:
        entry = str(row.get("entry_point") or row.get("start_address") or "").lower()
        if entry in target_addresses:
            matched_functions.append(row)

    decompilations: dict[str, Any] = {}
    for label, address in TARGETS.items():
        decompilations[label] = client.call_tool(
            "decompile_code",
            {
                "file_name": opened_program,
                "target_type": "address",
                "target_value": address,
                "timeout": int(decompile_timeout),
            },
        )

    return {
        "read_only": True,
        "program": opened_program,
        "base_program_opened": opened_program == PM99_PROGRAMS[0],
        "pm99_program_available": True,
        "program_info": program_info,
        "available_tools": sorted(available_tools),
        "function_inventory_match_count": len(matched_functions),
        "function_inventory_matches": matched_functions,
        "decompilations": decompilations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080/mcp")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--decompile-timeout", type=int, default=60)
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional local JSON output path; omitted means stdout only.",
    )
    args = parser.parse_args()
    try:
        result = call_read_only_probe(args.url, args.timeout, args.decompile_timeout)
    except (ProbeError, OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
