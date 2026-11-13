#!/usr/bin/env python3
"""Probe a PM99 install directory for binaries, save-path clues, and key strings.

This is a lightweight binary reconnaissance step intended for pre-Ghidra reverse engineering.
It extracts:
- binary inventory (size + SHA256)
- relevant ASCII strings (FDI/DBDAT, save paths, tactics files, UI labels)
- presence of known record separator markers in binaries (dd6360/dd6361/61dd63)
- save directory/file inventory (if present)

Use this to ground follow-on reverse engineering (Ghidra, structure mapping, save diffing)
with a reproducible artifact instead of ad-hoc terminal grep.
"""

from __future__ import annotations

try:
    from scripts import json_storage_io_v1 as storage_io
except ModuleNotFoundError:
    import sys as _storage_sys
    from pathlib import Path as _StoragePath
    _storage_sys.path.insert(0, str(next(p for p in _StoragePath(__file__).resolve().parents if (p / 'scripts/json_storage_io_v1.py').is_file())))
    from scripts import json_storage_io_v1 as storage_io

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = storage_io.resolve(Path(__file__)).parents[1]
DEFAULT_INSTALL_DIR = REPO_ROOT / ".local" / "premier-manager-ninety-nine"

BINARY_NAMES = [
    "PM99.EXE",
    "MANAGPRE.EXE",
    "DBASEPRE.EXE",
    "MIDAS11.DLL",
    "RegSetUp.exe",
]

ASCII_MIN_LEN = 4
ASCII_RE = re.compile(rb"[\x20-\x7e]{%d,}" % ASCII_MIN_LEN)

STRING_PATTERNS = {
    "db_paths": re.compile(r"(?:^|\\)(?:dbdat|DBDAT)\\", re.IGNORECASE),
    "fdi_refs": re.compile(r"(?:jug|eq|ent)98\d{3}\.fdi", re.IGNORECASE),
    "save_paths": re.compile(r"(?:^|\\)(?:save|SAVES)(?:\\|$)|main\.dat$|aviso\d{3}\.\d{3}$", re.IGNORECASE),
    "tactics_paths": re.compile(r"(?:^|\\)tactics\\|TACTIC\.[0-9A-F]{3}$|partido\.dat$", re.IGNORECASE),
    "ui_attr_labels": re.compile(r"^(?:FITNESS|MORAL|STAMINA|AGGRESSION|QUALITY|ROL\.|LINE-UP|TACTICS|TRAINING|SQUAD|TRANSFERS?)$", re.IGNORECASE),
    "ui_misc_editor": re.compile(r"(?:SAVE GAME|LOAD GAME|SQUAD NUMBERS|TEAM TACTICS|PREDEFINED TACTICS|TRANSFER MARKET)", re.IGNORECASE),
}

MARKER_BYTES = {
    "dd6360": bytes([0xDD, 0x63, 0x60]),
    "dd6361": bytes([0xDD, 0x63, 0x61]),
    "61dd63": bytes([0x61, 0xDD, 0x63]),
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with storage_io.open_file(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_ascii_strings(data: bytes) -> list[str]:
    out: list[str] = []
    for m in ASCII_RE.finditer(data):
        try:
            out.append(m.group(0).decode("ascii", errors="ignore"))
        except Exception:
            continue
    return out


def _classify_strings(strings: list[str]) -> dict[str, list[str]]:
    categorized: dict[str, list[str]] = {k: [] for k in STRING_PATTERNS}
    for s in strings:
        for key, rx in STRING_PATTERNS.items():
            if rx.search(s):
                categorized[key].append(s)
    # Dedup while preserving order.
    for key in categorized:
        seen: set[str] = set()
        deduped: list[str] = []
        for s in categorized[key]:
            if s in seen:
                continue
            seen.add(s)
            deduped.append(s)
        categorized[key] = deduped
    return categorized


def _scan_marker_offsets(data: bytes) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for label, needle in MARKER_BYTES.items():
        positions: list[int] = []
        pos = data.find(needle)
        while pos != -1:
            positions.append(pos)
            if len(positions) >= 32:  # cap to keep artifact manageable
                break
            pos = data.find(needle, pos + 1)
        out[label] = positions
    return out


def _scan_binary(path: Path) -> dict[str, Any]:
    data = storage_io.read_bytes(path)
    strings = _extract_ascii_strings(data)
    classified = _classify_strings(strings)
    marker_offsets = _scan_marker_offsets(data)
    return {
        "path": str(path),
        "size_bytes": storage_io.size(path),
        "sha256": _sha256(path),
        "ascii_string_count": len(strings),
        "marker_offsets": {k: [int(x) for x in v] for k, v in marker_offsets.items()},
        "marker_present": {k: bool(v) for k, v in marker_offsets.items()},
        "strings": classified,
    }


def _inventory_save_like_files(install_dir: Path) -> dict[str, Any]:
    save_roots = [
        install_dir / "save",
        install_dir / "SAVES",
    ]
    existing = [p for p in save_roots if storage_io.exists(p)]
    files: list[dict[str, Any]] = []

    # Also include known oddball root files that may be save-/session-related.
    extra_patterns = ["*.R0X", "*.0??", "*.DAT", "*.dbc", "*.DBC"]
    candidates: set[Path] = set()
    for root in existing:
        for p in storage_io.glob(root, '*', recursive=True):
            if storage_io.is_file(p):
                candidates.add(p)
    for pat in extra_patterns:
        for p in storage_io.glob(install_dir, pat):
            if storage_io.is_file(p):
                candidates.add(p)

    for p in sorted(candidates):
        files.append(
            {
                "path": str(p),
                "size_bytes": storage_io.size(p),
            }
        )
    return {
        "save_dirs_present": [str(p) for p in existing],
        "candidate_file_count": len(files),
        "candidate_files": files,
    }


def _inventory_tactics_files(install_dir: Path) -> dict[str, Any]:
    tactics_dir = install_dir / "TACTICS"
    if not storage_io.exists(tactics_dir):
        return {"tactics_dir": str(tactics_dir), "exists": False}
    files = sorted([p for p in tactics_dir.iterdir() if storage_io.is_file(p)])
    tactic_files = [p for p in files if p.name.upper().startswith("TACTIC.")]
    predef_files = [p for p in files if p.name.lower().startswith("predef.")]
    return {
        "tactics_dir": str(tactics_dir),
        "exists": True,
        "file_count": len(files),
        "tactic_file_count": len(tactic_files),
        "predef_file_count": len(predef_files),
        "partido_dat_exists": storage_io.exists(tactics_dir / 'partido.dat'),
        "sample_files": [p.name for p in files[:40]],
        "sizes": {
            p.name: storage_io.size(p)
            for p in files
            if p.name in {"partido.dat", "TACTIC.000", "TACTIC.001", "TACTIC.002", "predef.001"}
        },
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Probe PM99 install binaries and save/tactics file clues")
    p.add_argument(
        "--install-dir",
        default=str(DEFAULT_INSTALL_DIR),
        help="Path to the PM99 install directory",
    )
    p.add_argument("--json-output", help="Write JSON artifact to this path")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    install_dir = Path(args.install_dir)
    if not storage_io.exists(install_dir):
        payload = {"error": f"Install dir not found: {install_dir}"}
        print(json.dumps(payload, indent=2))
        return 2

    binaries: list[dict[str, Any]] = []
    for name in BINARY_NAMES:
        p = install_dir / name
        if storage_io.exists(p) and storage_io.is_file(p):
            binaries.append(_scan_binary(p))

    payload = {
        "install_dir": str(install_dir),
        "binaries": binaries,
        "save_inventory": _inventory_save_like_files(install_dir),
        "tactics_inventory": _inventory_tactics_files(install_dir),
        "notes": [
            "ASCII string extraction is a pre-Ghidra reconnaissance step and is not exhaustive (no resource parsing, no xrefs).",
            "marker_offsets reports raw byte-sequence presence in binaries only; absence does not mean the code lacks parser support.",
            "save_inventory includes likely save/session files by path and extension heuristics (may include non-save files).",
        ],
    }

    text = json.dumps(payload, indent=2)
    if args.json_output:
        out = Path(args.json_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        storage_io.write_text(out, text + '\n', encoding='utf-8')
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
