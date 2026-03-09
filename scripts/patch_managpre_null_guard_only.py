#!/usr/bin/env python3
"""Patch MANAGPRE.EXE with only the minimal Valderrama null-pointer guard.

Crash signature:
- Access violation at 0x0066F208 (MOV AL,[ECX]) in FUN_0066f1f0
- On some transfer hover paths, ECX can be NULL.

Patch contract:
- MANAGPRE only
- no upstream/source-club behavior patches
- one trampoline at 0x0066F1FB into local cave
- if ECX is NULL, jump to existing empty-string path at 0x0066F243
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_EXE = REPO_ROOT / ".local" / "premier-manager-ninety-nine" / "MANAGPRE.EXE"
DEFAULT_OUTPUT_EXE = Path("/tmp") / "MANAGPRE.null_guard_only.EXE"
IMAGE_BASE = 0x400000


@dataclass(frozen=True)
class PatchSpec:
    name: str
    site_va: int
    site_original: bytes
    cave_va: int
    resume_va: int
    null_target_va: int


PATCH = PatchSpec(
    name="guard_null_textptr_FUN_0066f1f0_only",
    site_va=0x0066F1FB,
    # 8B4C2420 33F6 8A4720 33D2 8BE8 8A01
    site_original=bytes.fromhex("8b4c242033f68a472033d28be88a01"),
    cave_va=0x006E51C0,
    resume_va=0x0066F20A,
    null_target_va=0x0066F243,
)


def _sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _read_sections(pe_bytes: bytes) -> list[dict[str, int]]:
    if pe_bytes[:2] != b"MZ":
        raise ValueError("Input is not an MZ executable")
    pe_off = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    if pe_bytes[pe_off : pe_off + 4] != b"PE\x00\x00":
        raise ValueError("Input does not contain a valid PE header")

    section_count = struct.unpack_from("<H", pe_bytes, pe_off + 6)[0]
    opt_size = struct.unpack_from("<H", pe_bytes, pe_off + 20)[0]
    section_off = pe_off + 24 + opt_size
    sections: list[dict[str, int]] = []
    for i in range(section_count):
        off = section_off + i * 40
        virtual_size, virtual_address, raw_size, raw_ptr = struct.unpack_from("<IIII", pe_bytes, off + 8)
        sections.append(
            {
                "virtual_address": virtual_address,
                "virtual_size": virtual_size,
                "raw_ptr": raw_ptr,
                "raw_size": raw_size,
            }
        )
    return sections


def _va_to_file_offset(pe_bytes: bytes, va: int) -> int:
    rva = va - IMAGE_BASE
    for sec in _read_sections(pe_bytes):
        start = sec["virtual_address"]
        size = max(sec["virtual_size"], sec["raw_size"])
        end = start + size
        if start <= rva < end:
            return sec["raw_ptr"] + (rva - start)
    raise ValueError(f"VA 0x{va:08X} does not map to a file section")


def _rel32(from_va: int, instr_len: int, to_va: int) -> bytes:
    rel = to_va - (from_va + instr_len)
    return struct.pack("<i", rel)


def _build_trampoline(src_va: int, dst_va: int, total_len: int) -> bytes:
    if total_len < 5:
        raise ValueError("Trampoline region must be at least 5 bytes")
    rel = dst_va - (src_va + 5)
    return b"\xE9" + struct.pack("<i", rel) + (b"\x90" * (total_len - 5))


def _build_stub(spec: PatchSpec) -> bytes:
    # Replay overwritten setup, then guard before MOV AL,[ECX].
    out = bytearray()

    # 8B4C2420 33F6 8A4720 33D2 8BE8
    out += bytes.fromhex("8b4c242033f68a472033d28be8")

    # test ecx, ecx
    out += b"\x85\xc9"

    # jz null_target
    jz_va = spec.cave_va + len(out)
    out += b"\x0f\x84" + _rel32(jz_va, 6, spec.null_target_va)

    # original faulting read
    out += b"\x8a\x01"

    # jump back to continuation
    jmp_va = spec.cave_va + len(out)
    out += b"\xe9" + _rel32(jmp_va, 5, spec.resume_va)
    return bytes(out)


def apply_patch(
    *,
    input_exe: Path,
    output_exe: Path | None,
    in_place: bool,
    dry_run: bool,
    force: bool,
    make_backup: bool,
) -> dict[str, Any]:
    input_bytes = input_exe.read_bytes()
    patched = bytearray(input_bytes)
    spec = PATCH

    site_off = _va_to_file_offset(input_bytes, spec.site_va)
    cave_off = _va_to_file_offset(input_bytes, spec.cave_va)
    stub = _build_stub(spec)
    trampoline = _build_trampoline(spec.site_va, spec.cave_va, len(spec.site_original))

    current_site = input_bytes[site_off : site_off + len(spec.site_original)]
    current_cave = input_bytes[cave_off : cave_off + len(stub)]

    allowed_sites = {spec.site_original, trampoline}
    allowed_caves = {b"\x00" * len(stub), stub}
    if current_site not in allowed_sites and not force:
        raise RuntimeError(
            "Patch-site bytes do not match expected signature. "
            "Use --force only after manual verification."
        )
    if current_cave not in allowed_caves and not force:
        raise RuntimeError(
            "Code-cave bytes are not empty/already-patched. "
            "Use --force only after manual verification."
        )

    patched[cave_off : cave_off + len(stub)] = stub
    patched[site_off : site_off + len(spec.site_original)] = trampoline
    output_bytes = bytes(patched)

    target_out: Path
    if in_place:
        target_out = input_exe
    else:
        target_out = output_exe or DEFAULT_OUTPUT_EXE

    backup_path: Path | None = None
    if not dry_run:
        target_out.parent.mkdir(parents=True, exist_ok=True)
        if in_place and make_backup:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = target_out.with_name(f"{target_out.name}.bak_nullguard_only_{stamp}")
            shutil.copy2(target_out, backup_path)
        target_out.write_bytes(output_bytes)

    return {
        "input_exe": str(input_exe),
        "output_exe": str(target_out),
        "backup_exe": str(backup_path) if backup_path else None,
        "dry_run": bool(dry_run),
        "patches": [
            {
                "name": spec.name,
                "site_va": f"0x{spec.site_va:08X}",
                "site_file_offset": f"0x{site_off:08X}",
                "site_before": current_site.hex(),
                "site_after": trampoline.hex(),
                "cave_va": f"0x{spec.cave_va:08X}",
                "cave_file_offset": f"0x{cave_off:08X}",
                "cave_before": current_cave.hex(),
                "cave_after": stub.hex(),
                "resume_va": f"0x{spec.resume_va:08X}",
                "null_target_va": f"0x{spec.null_target_va:08X}",
            }
        ],
        "sha256": {
            "input": _sha256(input_bytes),
            "output": _sha256(output_bytes),
        },
        "notes": [
            "MANAGPRE-only patch. No database edits.",
            "Single defense patch only: NULL ECX guard before 0x0066F208 dereference.",
            "On NULL, control flows to existing empty-text path at 0x0066F243.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch MANAGPRE.EXE with only the minimal null-pointer guard for Valderrama hover crash"
    )
    parser.add_argument("--input-exe", default=str(DEFAULT_INPUT_EXE), help="Path to source MANAGPRE.EXE")
    parser.add_argument(
        "--output-exe",
        default=str(DEFAULT_OUTPUT_EXE),
        help="Output path (ignored with --in-place)",
    )
    parser.add_argument("--in-place", action="store_true", help="Patch input file in place")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report only")
    parser.add_argument("--force", action="store_true", help="Ignore signature checks")
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Disable auto-backup when using --in-place",
    )
    parser.add_argument("--json-output", help="Optional report output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_exe = Path(args.input_exe)
    output_exe = None if args.in_place else Path(args.output_exe)
    report = apply_patch(
        input_exe=input_exe,
        output_exe=output_exe,
        in_place=bool(args.in_place),
        dry_run=bool(args.dry_run),
        force=bool(args.force),
        make_backup=not bool(args.no_backup),
    )
    text = json.dumps(report, indent=2)
    if args.json_output:
        out = Path(args.json_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
