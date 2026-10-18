#!/usr/bin/env python3
"""Read-only static negative-control probe for the PM99 carrier-ID watch.

This is deliberately not a topology editor or a binary patcher.  It preserves
the relevant disassembly from an explicitly supplied local MANAGPRE.EXE so a
runtime watch hit can be checked against the actual lookup instructions before
being described as competition selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


WINDOWS = {
    "watched_caller": (0x004B1340, 0x004B13E8),
    "watched_lookup": (0x004B5C20, 0x004B5C84),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def disassemble(executable: Path, start: int, stop: int) -> str:
    result = subprocess.run(
        [
            "objdump",
            "-D",
            "-Mintel",
            f"--start-address=0x{start:x}",
            f"--stop-address=0x{stop:x}",
            str(executable),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "objdump failed")
    return result.stdout


def collect(executable: Path) -> dict[str, Any]:
    if not executable.is_file():
        raise FileNotFoundError(f"MANAGPRE.EXE not found: {executable}")
    if shutil.which("objdump") is None:
        raise RuntimeError("objdump is required for this read-only probe")

    disassembly = {
        label: disassemble(executable, start, stop)
        for label, (start, stop) in WINDOWS.items()
    }
    caller = disassembly["watched_caller"]
    lookup = disassembly["watched_lookup"]
    return {
        "read_only": True,
        "executable": str(executable.resolve()),
        "executable_sha256": sha256(executable),
        "windows": {label: {"start": f"0x{start:08x}", "stop": f"0x{stop:08x}"} for label, (start, stop) in WINDOWS.items()},
        "instruction_checks": {
            "caller_reads_word_at_input_plus_0x18": "mov    cx,WORD PTR [esi+0x18]" in caller,
            "caller_passes_word_to_004b5c20": "call   0x4b5c20" in caller,
            "lookup_compares_candidate_dword_at_plus_0x10": "cmp    edx,ebx" in lookup,
            "lookup_uses_binary_search_bounds": all(
                token in lookup
                for token in ("lea    edi,[eax+0x1]", "lea    esi,[eax-0x1]", "cmp    edi,esi")
            ),
            "caller_clamps_result_to_40_through_99": all(
                token in caller
                for token in ("cmp    edi,0x28", "cmp    edi,0x63")
            ),
        },
        "conclusion": (
            "This establishes only the mechanics of the observed carrier-ID watch: "
            "a caller supplies input +0x18 to a generic sorted lookup. It does not "
            "identify a pre-name-copy fixture slot or a foreign candidate-pool source."
        ),
        "disassembly": disassembly,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="Optional JSON path; stdout is always emitted.")
    args = parser.parse_args()
    try:
        result = collect(args.exe)
    except (FileNotFoundError, RuntimeError, OSError) as exc:
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
