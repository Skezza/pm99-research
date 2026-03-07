#!/usr/bin/env python3
"""Patch MANAGPRE.EXE with guarded Valderrama hover/source-club fallbacks.

Patch contract:
- MANAGPRE only (no DBASEPRE / database edits)
- Primary upstream fix: normalize empty club lookups in transfer/search callsites
  before formatting/rendering text:
  - 0x00474946 (search player by name list row assembly)
  - 0x004FA843 (transfer briefcase branch A)
  - 0x004FB594 (transfer briefcase branch B)
- Club fallback policy:
  - team_id 4705 -> "Stars"
  - team_id 4706 -> "Free players"
  - otherwise -> "Unknown club"
- Defense-in-depth: keep the FUN_0066f1f0 null text-pointer guard, but normalize
  NULL to "" and continue normal flow rather than hard early-exit.
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
DEFAULT_OUTPUT_EXE = Path("/tmp") / "MANAGPRE.valderrama_guard.EXE"
IMAGE_BASE = 0x400000
LOOKUP_FUN_VA = 0x004B5C20

CAVE_LOOKUP_BASE_VA = 0x006E5092
CAVE_LOOKUP_MAX_LEN = 302
CAVE_NULL_GUARD_VA = 0x006E51C0
CAVE_SIGNING_CLUB_VA = 0x006E51E1

TEAM_ID_STARS = 4705
TEAM_ID_FREE_PLAYERS = 4706


@dataclass(frozen=True)
class TrampolinePatch:
    name: str
    site_va: int
    site_original: bytes
    cave_va: int
    cave_bytes: bytes


@dataclass(frozen=True)
class DirectPatch:
    name: str
    site_va: int
    site_original: bytes
    replacement: bytes


def _sha256(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _read_sections(pe_bytes: bytes) -> list[dict[str, int]]:
    if pe_bytes[:2] != b"MZ":
        raise ValueError("Input is not an MZ executable")
    pe_off = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    if pe_bytes[pe_off:pe_off + 4] != b"PE\x00\x00":
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


def _build_lookup_fallback_stub_edi(
    *,
    cave_va: int,
    resume_va: int,
    stars_va: int,
    free_va: int,
    unknown_va: int,
) -> bytes:
    """Build stub for callsites that pass team_id in EDI before LOOKUP_FUN_VA."""
    out = bytearray()

    # call LOOKUP_FUN_VA
    call_va = cave_va + len(out)
    out += b"\xE8" + _rel32(call_va, 5, LOOKUP_FUN_VA)

    # test eax,eax
    out += b"\x85\xC0"

    # jz fallback
    jz_lookup_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    # mov eax,[eax+4]
    out += b"\x8B\x40\x04"

    # test eax,eax
    out += b"\x85\xC0"

    # jz fallback
    jz_ptr_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    # cmp byte ptr [eax],0
    out += b"\x80\x38\x00"

    # jnz done
    jnz_done_pos = len(out)
    out += b"\x0F\x85" + b"\x00\x00\x00\x00"

    fallback_va = cave_va + len(out)

    # cmp edi, TEAM_ID_STARS
    out += b"\x81\xFF" + struct.pack("<I", TEAM_ID_STARS)
    # je set_stars
    je_stars_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    # cmp edi, TEAM_ID_FREE_PLAYERS
    out += b"\x81\xFF" + struct.pack("<I", TEAM_ID_FREE_PLAYERS)
    # je set_free
    je_free_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    # mov eax, unknown
    out += b"\xB8" + struct.pack("<I", unknown_va)
    # jmp done
    jmp_done_unknown_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"

    set_stars_va = cave_va + len(out)
    out += b"\xB8" + struct.pack("<I", stars_va)
    jmp_done_stars_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"

    set_free_va = cave_va + len(out)
    out += b"\xB8" + struct.pack("<I", free_va)

    done_va = cave_va + len(out)

    # jmp resume
    jmp_resume_va = cave_va + len(out)
    out += b"\xE9" + _rel32(jmp_resume_va, 5, resume_va)

    # patch rel32 branches
    out[jz_lookup_pos + 2 : jz_lookup_pos + 6] = _rel32(cave_va + jz_lookup_pos, 6, fallback_va)
    out[jz_ptr_pos + 2 : jz_ptr_pos + 6] = _rel32(cave_va + jz_ptr_pos, 6, fallback_va)
    out[jnz_done_pos + 2 : jnz_done_pos + 6] = _rel32(cave_va + jnz_done_pos, 6, done_va)
    out[je_stars_pos + 2 : je_stars_pos + 6] = _rel32(cave_va + je_stars_pos, 6, set_stars_va)
    out[je_free_pos + 2 : je_free_pos + 6] = _rel32(cave_va + je_free_pos, 6, set_free_va)
    out[jmp_done_unknown_pos + 1 : jmp_done_unknown_pos + 5] = _rel32(cave_va + jmp_done_unknown_pos, 5, done_va)
    out[jmp_done_stars_pos + 1 : jmp_done_stars_pos + 5] = _rel32(cave_va + jmp_done_stars_pos, 5, done_va)

    return bytes(out)


def _build_lookup_fallback_stub_esi_word18(
    *,
    cave_va: int,
    resume_va: int,
    stars_va: int,
    free_va: int,
    unknown_va: int,
) -> bytes:
    """Build stub for callsites where team_id is available at [ESI+0x18]."""
    out = bytearray()

    # call LOOKUP_FUN_VA
    call_va = cave_va + len(out)
    out += b"\xE8" + _rel32(call_va, 5, LOOKUP_FUN_VA)

    # test eax,eax
    out += b"\x85\xC0"

    # jz fallback
    jz_lookup_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    # mov eax,[eax+4]
    out += b"\x8B\x40\x04"

    # test eax,eax
    out += b"\x85\xC0"

    # jz fallback
    jz_ptr_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    # cmp byte ptr [eax],0
    out += b"\x80\x38\x00"

    # jnz done
    jnz_done_pos = len(out)
    out += b"\x0F\x85" + b"\x00\x00\x00\x00"

    fallback_va = cave_va + len(out)

    # movzx edx,word ptr [esi+0x18]
    out += b"\x0F\xB7\x56\x18"

    # cmp dx,TEAM_ID_STARS
    out += b"\x66\x81\xFA" + struct.pack("<H", TEAM_ID_STARS)
    je_stars_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    # cmp dx,TEAM_ID_FREE_PLAYERS
    out += b"\x66\x81\xFA" + struct.pack("<H", TEAM_ID_FREE_PLAYERS)
    je_free_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    # mov eax, unknown
    out += b"\xB8" + struct.pack("<I", unknown_va)
    jmp_done_unknown_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"

    set_stars_va = cave_va + len(out)
    out += b"\xB8" + struct.pack("<I", stars_va)
    jmp_done_stars_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"

    set_free_va = cave_va + len(out)
    out += b"\xB8" + struct.pack("<I", free_va)

    done_va = cave_va + len(out)

    # jmp resume
    jmp_resume_va = cave_va + len(out)
    out += b"\xE9" + _rel32(jmp_resume_va, 5, resume_va)

    # patch rel32 branches
    out[jz_lookup_pos + 2 : jz_lookup_pos + 6] = _rel32(cave_va + jz_lookup_pos, 6, fallback_va)
    out[jz_ptr_pos + 2 : jz_ptr_pos + 6] = _rel32(cave_va + jz_ptr_pos, 6, fallback_va)
    out[jnz_done_pos + 2 : jnz_done_pos + 6] = _rel32(cave_va + jnz_done_pos, 6, done_va)
    out[je_stars_pos + 2 : je_stars_pos + 6] = _rel32(cave_va + je_stars_pos, 6, set_stars_va)
    out[je_free_pos + 2 : je_free_pos + 6] = _rel32(cave_va + je_free_pos, 6, set_free_va)
    out[jmp_done_unknown_pos + 1 : jmp_done_unknown_pos + 5] = _rel32(cave_va + jmp_done_unknown_pos, 5, done_va)
    out[jmp_done_stars_pos + 1 : jmp_done_stars_pos + 5] = _rel32(cave_va + jmp_done_stars_pos, 5, done_va)

    return bytes(out)


def _build_null_text_guard_stub(
    *,
    cave_va: int,
    resume_va: int,
    empty_text_va: int,
) -> bytes:
    """Replays overwritten FUN_0066f1f0 setup and normalizes NULL text ptr to ""."""
    out = bytearray()

    # Original bytes from 0x0066F1FB up to (but excluding) faulting MOV AL,[ECX].
    out += bytes.fromhex("8b4c242033f68a472033d28be8")

    # test ecx,ecx
    out += b"\x85\xC9"

    # jnz continue
    jnz_pos = len(out)
    out += b"\x0F\x85" + b"\x00\x00\x00\x00"

    # mov ecx, empty_text
    out += b"\xB9" + struct.pack("<I", empty_text_va)

    continue_va = cave_va + len(out)

    # original faulting read
    out += b"\x8A\x01"

    # jmp resume
    jmp_resume_va = cave_va + len(out)
    out += b"\xE9" + _rel32(jmp_resume_va, 5, resume_va)

    out[jnz_pos + 2 : jnz_pos + 6] = _rel32(cave_va + jnz_pos, 6, continue_va)
    return bytes(out)




def _build_signing_source_club_fallback_stub(
    *,
    cave_va: int,
    resume_va: int,
    unknown_va: int,
) -> bytes:
    """Normalize empty source-club pointer in transfer sentence path."""
    out = bytearray()

    # Replaced instruction at 0x004B8C2E: and eax,0xffff
    out += b"\x0f\xb7\xc0"  # movzx eax,ax

    # local_10c is stored at [esp+0x10] in FUN_004b8b40.
    out += b"\x8b\x54\x24\x10"  # mov edx,[esp+0x10]
    out += b"\x85\xd2"  # test edx,edx
    jz_pos = len(out)
    out += b"\x74\x00"  # jz set_unknown (patched)
    out += b"\x80\x3a\x00"  # cmp byte ptr [edx],0
    jnz_pos = len(out)
    out += b"\x75\x00"  # jnz done (patched)

    set_unknown_va = cave_va + len(out)
    out += b"\xba" + struct.pack("<I", unknown_va)  # mov edx,unknown_va
    out += b"\x89\x54\x24\x10"  # mov [esp+0x10],edx

    done_va = cave_va + len(out)
    jmp_resume_va = cave_va + len(out)
    out += b"\xe9" + _rel32(jmp_resume_va, 5, resume_va)

    rel_jz = set_unknown_va - (cave_va + jz_pos + 2)
    rel_jnz = done_va - (cave_va + jnz_pos + 2)
    if not (-128 <= rel_jz <= 127 and -128 <= rel_jnz <= 127):
        raise RuntimeError("Short-branch range overflow in source-club fallback stub")
    out[jz_pos + 1] = rel_jz & 0xFF
    out[jnz_pos + 1] = rel_jnz & 0xFF
    return bytes(out)


def _old_null_guard_stub(cave_va: int, resume_va: int, null_target_va: int) -> bytes:
    """Legacy v1 guard accepted for idempotent upgrades."""
    out = bytearray()
    out += bytes.fromhex("8b4c242033f68a472033d28be8")
    out += b"\x85\xC9"
    jz_va = cave_va + len(out)
    out += b"\x0F\x84" + _rel32(jz_va, 6, null_target_va)
    out += b"\x8A\x01"
    jmp_va = cave_va + len(out)
    out += b"\xE9" + _rel32(jmp_va, 5, resume_va)
    return bytes(out)


def _build_patch_plan() -> tuple[list[TrampolinePatch], list[DirectPatch], dict[str, int], bytes]:
    # Build once with placeholder string addresses to lock lengths.
    s1_tmp = _build_lookup_fallback_stub_esi_word18(
        cave_va=CAVE_LOOKUP_BASE_VA,
        resume_va=0x0047494E,
        stars_va=0,
        free_va=0,
        unknown_va=0,
    )
    s2_tmp = _build_lookup_fallback_stub_edi(
        cave_va=CAVE_LOOKUP_BASE_VA + len(s1_tmp),
        resume_va=0x004FA84B,
        stars_va=0,
        free_va=0,
        unknown_va=0,
    )
    s3_tmp = _build_lookup_fallback_stub_edi(
        cave_va=CAVE_LOOKUP_BASE_VA + len(s1_tmp) + len(s2_tmp),
        resume_va=0x004FB59C,
        stars_va=0,
        free_va=0,
        unknown_va=0,
    )

    strings_va = CAVE_LOOKUP_BASE_VA + len(s1_tmp) + len(s2_tmp) + len(s3_tmp)
    strings_blob = b"\x00" + b"Stars\x00" + b"Free players\x00" + b"Unknown club\x00"

    string_addrs = {
        "empty": strings_va,
        "stars": strings_va + 1,
        "free": strings_va + 1 + len(b"Stars\x00"),
        "unknown": strings_va + 1 + len(b"Stars\x00") + len(b"Free players\x00"),
    }

    s1 = _build_lookup_fallback_stub_esi_word18(
        cave_va=CAVE_LOOKUP_BASE_VA,
        resume_va=0x0047494E,
        stars_va=string_addrs["stars"],
        free_va=string_addrs["free"],
        unknown_va=string_addrs["unknown"],
    )
    s2 = _build_lookup_fallback_stub_edi(
        cave_va=CAVE_LOOKUP_BASE_VA + len(s1),
        resume_va=0x004FA84B,
        stars_va=string_addrs["stars"],
        free_va=string_addrs["free"],
        unknown_va=string_addrs["unknown"],
    )
    s3 = _build_lookup_fallback_stub_edi(
        cave_va=CAVE_LOOKUP_BASE_VA + len(s1) + len(s2),
        resume_va=0x004FB59C,
        stars_va=string_addrs["stars"],
        free_va=string_addrs["free"],
        unknown_va=string_addrs["unknown"],
    )

    if len(s1) != len(s1_tmp) or len(s2) != len(s2_tmp) or len(s3) != len(s3_tmp):
        raise RuntimeError("Internal stub sizing mismatch")

    upstream_blob = s1 + s2 + s3 + strings_blob
    if len(upstream_blob) > CAVE_LOOKUP_MAX_LEN:
        raise RuntimeError(
            f"Upstream cave payload too large ({len(upstream_blob)} > {CAVE_LOOKUP_MAX_LEN})"
        )

    trampoline_patches = [
        TrampolinePatch(
            name="upstream_club_fallback_search_FUN_00474870",
            site_va=0x00474946,
            site_original=bytes.fromhex("e8d51204008b4004"),
            cave_va=CAVE_LOOKUP_BASE_VA,
            cave_bytes=s1,
        ),
        TrampolinePatch(
            name="upstream_club_fallback_transfer_FUN_004FA000",
            site_va=0x004FA843,
            site_original=bytes.fromhex("e8d8b3fbff8b4004"),
            cave_va=CAVE_LOOKUP_BASE_VA + len(s1),
            cave_bytes=s2,
        ),
        TrampolinePatch(
            name="upstream_club_fallback_transfer_FUN_004FAC80",
            site_va=0x004FB594,
            site_original=bytes.fromhex("e887a6fbff8b4004"),
            cave_va=CAVE_LOOKUP_BASE_VA + len(s1) + len(s2),
            cave_bytes=s3,
        ),
    ]

    null_stub = _build_null_text_guard_stub(
        cave_va=CAVE_NULL_GUARD_VA,
        resume_va=0x0066F20A,
        empty_text_va=string_addrs["empty"],
    )

    direct_patches = [
        DirectPatch(
            name="defense_in_depth_textptr_normalize_FUN_0066f1f0",
            site_va=0x0066F1FB,
            site_original=bytes.fromhex("8b4c242033f68a472033d28be88a01"),
            replacement=_build_trampoline(0x0066F1FB, CAVE_NULL_GUARD_VA, 15),
        ),
        DirectPatch(
            name="upstream_source_club_fallback_FUN_004b8b40",
            site_va=0x004B8C2E,
            site_original=bytes.fromhex("25ffff0000"),
            replacement=_build_trampoline(0x004B8C2E, CAVE_SIGNING_CLUB_VA, 5),
        ),
    ]

    return trampoline_patches, direct_patches, string_addrs, upstream_blob + null_stub


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

    trampoline_patches, direct_patches, string_addrs, full_blob = _build_patch_plan()

    # Split blob back into regions for write/validation.
    # Region A: lookup upstream cave [0x6E5092, +302)
    upstream_off = _va_to_file_offset(input_bytes, CAVE_LOOKUP_BASE_VA)
    # Region B: null-guard cave at 0x6E51C0
    null_guard_off = _va_to_file_offset(input_bytes, CAVE_NULL_GUARD_VA)

    rows: list[dict[str, Any]] = []

    # Build upstream region bytes only (first CAVE_LOOKUP_MAX_LEN bytes from plan content).
    upstream_region = full_blob[:CAVE_LOOKUP_MAX_LEN]

    # Validate/write upstream cave block.
    current_upstream = input_bytes[upstream_off : upstream_off + CAVE_LOOKUP_MAX_LEN]
    if not force:
        nonzero = [b for b in current_upstream if b != 0]
        # Allow pristine (all zero) or already matching prefix we are about to write.
        if nonzero and current_upstream != upstream_region:
            raise RuntimeError(
                "Upstream code cave is not pristine and does not match target bytes. "
                "Use --force only after manual verification."
            )
    patched[upstream_off : upstream_off + CAVE_LOOKUP_MAX_LEN] = upstream_region

    rows.append(
        {
            "name": "write_upstream_cave_bundle",
            "site_va": f"0x{CAVE_LOOKUP_BASE_VA:08X}",
            "site_file_offset": f"0x{upstream_off:08X}",
            "site_before": current_upstream[: min(64, len(current_upstream))].hex(),
            "site_after": upstream_region[: min(64, len(upstream_region))].hex(),
            "bytes_written": CAVE_LOOKUP_MAX_LEN,
        }
    )

    # Apply trampoline patches.
    for spec in trampoline_patches:
        site_off = _va_to_file_offset(input_bytes, spec.site_va)
        current_site = input_bytes[site_off : site_off + len(spec.site_original)]
        trampoline = _build_trampoline(spec.site_va, spec.cave_va, len(spec.site_original))
        allowed_sites = {spec.site_original, trampoline}
        if current_site not in allowed_sites and not force:
            raise RuntimeError(
                f"Patch-site bytes do not match expected signature for {spec.name}. "
                "Use --force only after manual verification."
            )
        patched[site_off : site_off + len(spec.site_original)] = trampoline
        rows.append(
            {
                "name": spec.name,
                "site_va": f"0x{spec.site_va:08X}",
                "site_file_offset": f"0x{site_off:08X}",
                "site_before": current_site.hex(),
                "site_after": trampoline.hex(),
                "cave_va": f"0x{spec.cave_va:08X}",
                "cave_bytes_len": len(spec.cave_bytes),
            }
        )

    # Apply direct trampoline patches.
    null_guard_site_va = 0x0066F1FB
    null_guard_site_len = len(bytes.fromhex("8b4c242033f68a472033d28be88a01"))
    old_null_trampoline = _build_trampoline(null_guard_site_va, CAVE_NULL_GUARD_VA, null_guard_site_len)
    for spec in direct_patches:
        site_off = _va_to_file_offset(input_bytes, spec.site_va)
        current_site = input_bytes[site_off : site_off + len(spec.site_original)]
        allowed_sites = {spec.site_original, spec.replacement}
        if spec.site_va == null_guard_site_va:
            allowed_sites.add(old_null_trampoline)
        if current_site not in allowed_sites and not force:
            raise RuntimeError(
                f"Patch-site bytes do not match expected signature for {spec.name}. "
                "Use --force only after manual verification."
            )
        patched[site_off : site_off + len(spec.site_original)] = spec.replacement
        rows.append(
            {
                "name": spec.name,
                "site_va": f"0x{spec.site_va:08X}",
                "site_file_offset": f"0x{site_off:08X}",
                "site_before": current_site.hex(),
                "site_after": spec.replacement.hex(),
            }
        )

    # Write null-guard cave stub.
    null_stub = _build_null_text_guard_stub(
        cave_va=CAVE_NULL_GUARD_VA,
        resume_va=0x0066F20A,
        empty_text_va=string_addrs["empty"],
    )
    old_stub = _old_null_guard_stub(
        cave_va=CAVE_NULL_GUARD_VA,
        resume_va=0x0066F20A,
        null_target_va=0x0066F243,
    )
    current_null_cave = input_bytes[null_guard_off : null_guard_off + len(null_stub)]
    old_prefix_ok = current_null_cave.startswith(old_stub) and all(
        b == 0 for b in current_null_cave[len(old_stub) :]
    )
    allowed_null_caves = {b"\x00" * len(null_stub), null_stub}
    if (current_null_cave not in allowed_null_caves) and (not old_prefix_ok) and (not force):
        raise RuntimeError(
            "Null-guard cave bytes are not empty/known. "
            "Use --force only after manual verification."
        )
    patched[null_guard_off : null_guard_off + len(null_stub)] = null_stub

    rows.append(
        {
            "name": "write_null_guard_cave",
            "site_va": f"0x{CAVE_NULL_GUARD_VA:08X}",
            "site_file_offset": f"0x{null_guard_off:08X}",
            "site_before": current_null_cave.hex(),
            "site_after": null_stub.hex(),
            "bytes_written": len(null_stub),
        }
    )


    # Write source-club fallback cave stub.
    signing_stub = _build_signing_source_club_fallback_stub(
        cave_va=CAVE_SIGNING_CLUB_VA,
        resume_va=0x004B8C33,
        unknown_va=string_addrs["unknown"],
    )
    signing_cave_off = _va_to_file_offset(input_bytes, CAVE_SIGNING_CLUB_VA)
    current_signing_cave = input_bytes[signing_cave_off : signing_cave_off + len(signing_stub)]
    allowed_signing_caves = {b"\x00" * len(signing_stub), signing_stub}
    if current_signing_cave not in allowed_signing_caves and not force:
        raise RuntimeError(
            "Source-club fallback cave bytes are not empty/known. "
            "Use --force only after manual verification."
        )
    patched[signing_cave_off : signing_cave_off + len(signing_stub)] = signing_stub
    rows.append(
        {
            "name": "write_signing_source_club_fallback_cave",
            "site_va": f"0x{CAVE_SIGNING_CLUB_VA:08X}",
            "site_file_offset": f"0x{signing_cave_off:08X}",
            "site_before": current_signing_cave.hex(),
            "site_after": signing_stub.hex(),
            "bytes_written": len(signing_stub),
        }
    )

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
            backup_path = target_out.with_name(f"{target_out.name}.bak_valderrama_upstream_{stamp}")
            shutil.copy2(target_out, backup_path)
        target_out.write_bytes(output_bytes)

    return {
        "input_exe": str(input_exe),
        "output_exe": str(target_out),
        "backup_exe": str(backup_path) if backup_path else None,
        "dry_run": bool(dry_run),
        "patch_count": len(rows),
        "patches": rows,
        "string_addresses": {k: f"0x{v:08X}" for k, v in string_addrs.items()},
        "sha256": {
            "input": _sha256(input_bytes),
            "output": _sha256(output_bytes),
        },
        "notes": [
            "MANAGPRE-only patch. No database edits.",
            "Upstream callsites now normalize missing/empty club lookup text to Stars/Free players/Unknown club.",
            "FUN_0066f1f0 keeps a defense-in-depth guard and normalizes NULL text_ptr to empty string.",
            "FUN_004b8b40 transfer sentence path now normalizes empty source-club text to Unknown club.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch MANAGPRE.EXE with upstream club fallback + text guard for Valderrama paths"
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
