#!/usr/bin/env python3
"""Enforce PM99RE boundary: research-only parent, product code in submodules."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BLOCKED_PREFIXES = ("app/", "tests/")
BLOCKED_EXACT = ("pm99_database_editor.py", "pytest.ini")


def _tracked_files(repo_root: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "ls-files"],
        cwd=repo_root,
        text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def _violations(files: list[str]) -> list[str]:
    found: list[str] = []
    for rel in files:
        if rel in BLOCKED_EXACT:
            found.append(rel)
            continue
        for prefix in BLOCKED_PREFIXES:
            if rel.startswith(prefix):
                found.append(rel)
                break
    return sorted(found)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    files = _tracked_files(repo_root)
    found = _violations(files)
    if not found:
        print("Boundary check OK: no product-code paths tracked in PM99RE.")
        return 0

    print("Boundary check FAILED. Remove product-code paths from PM99RE:")
    for rel in found:
        print(f"- {rel}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
