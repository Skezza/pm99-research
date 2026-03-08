#!/usr/bin/env python3
"""Patch MANAGPRE.EXE with Valderrama-safe guard and source-club fallbacks.

Patch contract (MANAGPRE only):
- Keep the proven null-pointer defense at FUN_0066f1f0 (0x0066F208 crash guard).
- Add one shared wrapper around source-club lookup calls in both signing branches:
  - 0x004B8C3D, 0x004B8C73, 0x004B8F09, 0x004B8F3F
- Add conservative lookup-result fallback for unresolved/invalid club names at
  FUN_004B5C20 tail hook (0x004B5C76):
  - team_id 0    -> "Unknown club"
  - team_id 4705 -> "Stars"
  - team_id 4706 -> "Free players"
- Revert older experimental upstream trampolines so the script is idempotent over
  previous patch variants.

This script intentionally avoids variable-length/data-file edits.
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

TEAM_ID_STARS = 4705
TEAM_ID_FREE_PLAYERS = 4706

# Slack region at tail of .text (file-backed): 0x006E5092..0x006E51BF (302 bytes)
CAVE_BUNDLE_BASE_VA = 0x006E5092
CAVE_BUNDLE_SIZE = 302

# Keep these string addresses stable so legacy patched bytes remain compatible.
CAVE_EMPTY_STRING_VA = 0x006E5199
CAVE_STARS_STRING_VA = 0x006E519A
CAVE_FREE_STRING_VA = 0x006E51A0
CAVE_UNKNOWN_STRING_VA = 0x006E51AD

# Null guard cave remains at proven location.
CAVE_NULL_GUARD_VA = 0x006E51C0


@dataclass(frozen=True)
class DirectPatch:
    name: str
    site_va: int
    expected: bytes
    replacement: bytes
    alternates: tuple[bytes, ...] = ()


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
    raise ValueError(f"VA 0x{va:08X} does not map to a file-backed section")


def _rel32(from_va: int, instr_len: int, to_va: int) -> bytes:
    rel = to_va - (from_va + instr_len)
    return struct.pack("<i", rel)


def _build_trampoline(src_va: int, dst_va: int, total_len: int) -> bytes:
    if total_len < 5:
        raise ValueError("Trampoline region must be at least 5 bytes")
    rel = dst_va - (src_va + 5)
    return b"\xE9" + struct.pack("<i", rel) + (b"\x90" * (total_len - 5))


def _build_call(src_va: int, dst_va: int) -> bytes:
    return b"\xE8" + _rel32(src_va, 5, dst_va)


def _build_null_text_guard_stub(*, cave_va: int, resume_va: int, empty_text_va: int) -> bytes:
    """Replays overwritten setup and normalizes NULL text ptr to empty string."""
    out = bytearray()

    # Original bytes from 0x0066F1FB up to (but excluding) MOV AL,[ECX].
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
    jmp_resume_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"

    out[jnz_pos + 2: jnz_pos + 6] = _rel32(cave_va + jnz_pos, 6, continue_va)
    out[jmp_resume_pos + 1: jmp_resume_pos + 5] = _rel32(cave_va + jmp_resume_pos, 5, resume_va)
    return bytes(out)


def _build_old_null_guard_stub(*, cave_va: int, resume_va: int, null_target_va: int) -> bytes:
    """Legacy v1 guard accepted for idempotent upgrades."""
    out = bytearray()
    out += bytes.fromhex("8b4c242033f68a472033d28be8")
    out += b"\x85\xC9"
    jz_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"
    out += b"\x8A\x01"
    jmp_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"
    out[jz_pos + 2: jz_pos + 6] = _rel32(cave_va + jz_pos, 6, null_target_va)
    out[jmp_pos + 1: jmp_pos + 5] = _rel32(cave_va + jmp_pos, 5, resume_va)
    return bytes(out)


def _build_signing_source_lookup_fallback_helper(
    *,
    cave_va: int,
    lookup_call_target_va: int,
    stars_va: int,
    free_va: int,
    unknown_va: int,
) -> bytes:
    """Wrapper for source-club lookup calls in signing-message flows.

    Call contract is identical to original CALL 0x004A4720 at the four callsites:
    - 0x004B8C3D, 0x004B8C73, 0x004B8F09, 0x004B8F3F

    Behavior:
    - Calls the original lookup function.
    - If returned text pointer is NULL/empty/placeholder, falls back by team_id:
      4705 -> "Stars", 4706 -> "Free players", 0/other -> "Unknown club"
    - Returns chosen text pointer in EAX.
    """
    out = bytearray()

    # call original lookup target
    call_lookup_pos = len(out)
    out += b"\xE8" + b"\x00\x00\x00\x00"

    # validate returned text pointer
    out += b"\x85\xC0"  # test eax,eax
    jz_fallback_1_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    out += b"\x8A\x10"  # mov dl,[eax]
    # Accept only printable team-name leading bytes in [0x30..0x7A].
    out += b"\x80\xFA\x30"  # cmp dl,'0'
    jb_fallback_pos = len(out)
    out += b"\x0F\x82" + b"\x00\x00\x00\x00"

    out += b"\x80\xFA\x7A"  # cmp dl,'z'
    jbe_done_pos = len(out)
    out += b"\x0F\x86" + b"\x00\x00\x00\x00"

    fallback_va = cave_va + len(out)

    out += b"\x8B\x8E\x10\x00\x00\x00"  # mov ecx,[esi+0x10]
    out += b"\x81\xF9" + struct.pack("<I", TEAM_ID_STARS)
    je_stars_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    out += b"\x81\xF9" + struct.pack("<I", TEAM_ID_FREE_PLAYERS)
    je_free_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    out += b"\xB8" + struct.pack("<I", unknown_va)  # mov eax,unknown
    out += b"\xC3"  # ret

    set_stars_va = cave_va + len(out)
    out += b"\xB8" + struct.pack("<I", stars_va)  # mov eax,stars
    out += b"\xC3"  # ret

    set_free_va = cave_va + len(out)
    out += b"\xB8" + struct.pack("<I", free_va)  # mov eax,free
    out += b"\xC3"  # ret

    done_va = cave_va + len(out)
    out += b"\xC3"  # ret

    out[call_lookup_pos + 1: call_lookup_pos + 5] = _rel32(cave_va + call_lookup_pos, 5, lookup_call_target_va)
    out[jz_fallback_1_pos + 2: jz_fallback_1_pos + 6] = _rel32(cave_va + jz_fallback_1_pos, 6, fallback_va)
    out[jb_fallback_pos + 2: jb_fallback_pos + 6] = _rel32(cave_va + jb_fallback_pos, 6, fallback_va)
    out[jbe_done_pos + 2: jbe_done_pos + 6] = _rel32(cave_va + jbe_done_pos, 6, done_va)
    out[je_stars_pos + 2: je_stars_pos + 6] = _rel32(cave_va + je_stars_pos, 6, set_stars_va)
    out[je_free_pos + 2: je_free_pos + 6] = _rel32(cave_va + je_free_pos, 6, set_free_va)

    return bytes(out)


def _build_lookup_result_fallback_helper(
    *,
    cave_va: int,
    epilogue_va: int,
    unknown_rec_va: int,
    stars_rec_va: int,
    free_rec_va: int,
) -> bytes:
    """Helper for 0x004B5C20 tail result handling.

    Input registers at hook point:
    - EAX: candidate team-record pointer
    - EBX: requested team ID

    Behavior:
    - if candidate is NULL -> fallback mapping
    - if candidate ID matches AND candidate name pointer/text is valid -> keep EAX
    - else fallback records for unresolved IDs (0, 4705, 4706)
    - all unresolved IDs degrade to unknown-club record (never NULL)
    - always jump to original epilogue at 0x004B5C7D
    """
    out = bytearray()

    out += b"\x85\xC0"  # test eax,eax
    jz_fallback_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    out += b"\x39\x58\x10"  # cmp dword ptr [eax+0x10],ebx
    jne_fallback_pos = len(out)
    out += b"\x0F\x85" + b"\x00\x00\x00\x00"

    out += b"\x8B\x50\x04"  # mov edx,[eax+0x04]
    out += b"\x85\xD2"  # test edx,edx
    jz_fallback_2_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    out += b"\x8A\x0A"  # mov cl,[edx]
    out += b"\x84\xC9"  # test cl,cl
    jz_fallback_3_pos = len(out)
    # JLE after TEST treats zero or high-bit bytes (>=0x80) as invalid text.
    out += b"\x0F\x8E" + b"\x00\x00\x00\x00"

    out += b"\x80\xF9\x2E"  # cmp cl,'.'
    jbe_fallback_4_pos = len(out)
    out += b"\x0F\x86" + b"\x00\x00\x00\x00"

    # matched and valid -> keep EAX
    jmp_epilogue_match_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"

    fallback_va = cave_va + len(out)

    out += b"\x85\xDB"  # test ebx,ebx
    je_unknown_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    out += b"\x81\xFB" + struct.pack("<I", TEAM_ID_STARS)  # cmp ebx,4705
    je_stars_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    out += b"\x81\xFB" + struct.pack("<I", TEAM_ID_FREE_PLAYERS)  # cmp ebx,4706
    je_free_pos = len(out)
    out += b"\x0F\x84" + b"\x00\x00\x00\x00"

    jmp_set_unknown_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"

    set_unknown_va = cave_va + len(out)
    out += b"\xB8" + struct.pack("<I", unknown_rec_va)
    jmp_epilogue_unknown_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"

    set_stars_va = cave_va + len(out)
    out += b"\xB8" + struct.pack("<I", stars_rec_va)
    jmp_epilogue_stars_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"

    set_free_va = cave_va + len(out)
    out += b"\xB8" + struct.pack("<I", free_rec_va)
    jmp_epilogue_free_pos = len(out)
    out += b"\xE9" + b"\x00\x00\x00\x00"

    out[jz_fallback_pos + 2: jz_fallback_pos + 6] = _rel32(cave_va + jz_fallback_pos, 6, fallback_va)
    out[jne_fallback_pos + 2: jne_fallback_pos + 6] = _rel32(cave_va + jne_fallback_pos, 6, fallback_va)
    out[jz_fallback_2_pos + 2: jz_fallback_2_pos + 6] = _rel32(cave_va + jz_fallback_2_pos, 6, fallback_va)
    out[jz_fallback_3_pos + 2: jz_fallback_3_pos + 6] = _rel32(cave_va + jz_fallback_3_pos, 6, fallback_va)
    out[jbe_fallback_4_pos + 2: jbe_fallback_4_pos + 6] = _rel32(cave_va + jbe_fallback_4_pos, 6, fallback_va)

    out[jmp_epilogue_match_pos + 1: jmp_epilogue_match_pos + 5] = _rel32(
        cave_va + jmp_epilogue_match_pos, 5, epilogue_va
    )

    out[je_unknown_pos + 2: je_unknown_pos + 6] = _rel32(cave_va + je_unknown_pos, 6, set_unknown_va)
    out[je_stars_pos + 2: je_stars_pos + 6] = _rel32(cave_va + je_stars_pos, 6, set_stars_va)
    out[je_free_pos + 2: je_free_pos + 6] = _rel32(cave_va + je_free_pos, 6, set_free_va)

    out[jmp_set_unknown_pos + 1: jmp_set_unknown_pos + 5] = _rel32(
        cave_va + jmp_set_unknown_pos, 5, set_unknown_va
    )
    out[jmp_epilogue_unknown_pos + 1: jmp_epilogue_unknown_pos + 5] = _rel32(
        cave_va + jmp_epilogue_unknown_pos, 5, epilogue_va
    )
    out[jmp_epilogue_stars_pos + 1: jmp_epilogue_stars_pos + 5] = _rel32(
        cave_va + jmp_epilogue_stars_pos, 5, epilogue_va
    )
    out[jmp_epilogue_free_pos + 1: jmp_epilogue_free_pos + 5] = _rel32(
        cave_va + jmp_epilogue_free_pos, 5, epilogue_va
    )

    return bytes(out)


def _build_fake_team_record(*, name_ptr_va: int, team_id: int) -> bytes:
    """Minimal fake team record used for text-only fallback paths.

    Layout used by observed callers:
    - +0x04 : char* team-name pointer
    - +0x10 : uint32 team_id
    """
    rec = bytearray(0x14)
    struct.pack_into("<I", rec, 0x04, int(name_ptr_va))
    struct.pack_into("<I", rec, 0x10, int(team_id))
    return bytes(rec)


def _build_bundle() -> tuple[bytes, dict[str, int], bytes]:
    strings_blob = b"\x00Stars\x00Free players\x00Unknown club\x00"

    # String addresses are fixed contract points.
    string_addrs = {
        "empty": CAVE_EMPTY_STRING_VA,
        "stars": CAVE_STARS_STRING_VA,
        "free": CAVE_FREE_STRING_VA,
        "unknown": CAVE_UNKNOWN_STRING_VA,
    }

    # Build helpers once to lock lengths.
    sign_tmp = _build_signing_source_lookup_fallback_helper(
        cave_va=CAVE_BUNDLE_BASE_VA,
        lookup_call_target_va=0x004A4720,
        stars_va=0,
        free_va=0,
        unknown_va=0,
    )

    lookup_tmp = _build_lookup_result_fallback_helper(
        cave_va=CAVE_BUNDLE_BASE_VA + len(sign_tmp),
        epilogue_va=0x004B5C7D,
        unknown_rec_va=0,
        stars_rec_va=0,
        free_rec_va=0,
    )

    rec_base_va = CAVE_BUNDLE_BASE_VA + len(sign_tmp) + len(lookup_tmp)
    unknown_rec_va = rec_base_va
    stars_rec_va = rec_base_va + 0x14
    free_rec_va = rec_base_va + 0x28

    sign_real = _build_signing_source_lookup_fallback_helper(
        cave_va=CAVE_BUNDLE_BASE_VA,
        lookup_call_target_va=0x004A4720,
        stars_va=string_addrs["stars"],
        free_va=string_addrs["free"],
        unknown_va=string_addrs["unknown"],
    )

    lookup_real = _build_lookup_result_fallback_helper(
        cave_va=CAVE_BUNDLE_BASE_VA + len(sign_real),
        epilogue_va=0x004B5C7D,
        unknown_rec_va=unknown_rec_va,
        stars_rec_va=stars_rec_va,
        free_rec_va=free_rec_va,
    )

    if len(sign_tmp) != len(sign_real) or len(lookup_tmp) != len(lookup_real):
        raise RuntimeError("Internal helper sizing mismatch")

    rec_unknown = _build_fake_team_record(name_ptr_va=string_addrs["unknown"], team_id=0)
    rec_stars = _build_fake_team_record(name_ptr_va=string_addrs["stars"], team_id=TEAM_ID_STARS)
    rec_free = _build_fake_team_record(name_ptr_va=string_addrs["free"], team_id=TEAM_ID_FREE_PLAYERS)

    prefix = sign_real + lookup_real + rec_unknown + rec_stars + rec_free
    prefix_end_va = CAVE_BUNDLE_BASE_VA + len(prefix)
    pad_len = CAVE_EMPTY_STRING_VA - prefix_end_va
    if pad_len < 0:
        raise RuntimeError(
            f"Bundle overflow before fixed strings: end=0x{prefix_end_va:08X} > strings=0x{CAVE_EMPTY_STRING_VA:08X}"
        )

    bundle = prefix + (b"\x00" * pad_len) + strings_blob
    if len(bundle) > CAVE_BUNDLE_SIZE:
        raise RuntimeError(f"Bundle too large ({len(bundle)} > {CAVE_BUNDLE_SIZE})")
    if len(bundle) < CAVE_BUNDLE_SIZE:
        bundle += b"\x00" * (CAVE_BUNDLE_SIZE - len(bundle))

    legacy_bundle_prefixes = (
        bytes.fromhex("e8890bddff85c00f84140000008b4004"),
        bytes.fromhex("e889f6dbff85c00f84130000008a1084d20f840900000080fa2e0f8730000000"),
        bytes.fromhex("e889f6dbff85c00f84130000008a1084d20f8e0900000080fa2e0f8730000000"),
        bytes.fromhex("e889f6dbff85c00f84140000008a1080fa300f820900000080fa7a0f8630000000"),
        bytes.fromhex("0fb7c08b54241485d20f8412000000803a000f8409000000803a2e0f8740000000"),
        bytes.fromhex("0fb7c08b54241485d20f841a0000008a0284c00f84100000003c800f83080000003c2e0f874c000000"),
    )
    return bundle, string_addrs, legacy_bundle_prefixes


def _build_patch_plan(sign_helper_va: int, lookup_helper_va: int) -> list[DirectPatch]:
    orig_search = bytes.fromhex("e8d51204008b4004")
    orig_transfer_a = bytes.fromhex("e8d8b3fbff8b4004")
    orig_transfer_b = bytes.fromhex("e887a6fbff8b4004")

    old_tramp_search = _build_trampoline(0x00474946, 0x006E5092, len(orig_search))
    old_tramp_transfer_a = _build_trampoline(0x004FA843, 0x006E50EB, len(orig_transfer_a))
    old_tramp_transfer_b = _build_trampoline(0x004FB594, 0x006E5142, len(orig_transfer_b))

    old_sign_call_a = _build_call(0x004B8C2E, 0x006E51E1)
    old_sign_call_b = _build_call(0x004B8EFA, 0x006E51E1)
    old_sign_call_a_v2 = _build_call(0x004B8C2E, 0x006E5092)
    old_sign_call_b_v2 = _build_call(0x004B8EFA, 0x006E5092)

    old_lookup_bytes = bytes.fromhex("395810740933c0")
    unpatched_lookup_bytes = bytes.fromhex("395810740233c0")
    old_lookup_trampoline = _build_trampoline(0x004B5C76, 0x006E50F4, len(unpatched_lookup_bytes))
    old_lookup_trampoline_v2 = _build_trampoline(0x004B5C76, 0x006E5108, len(unpatched_lookup_bytes))
    old_lookup_trampoline_v3 = _build_trampoline(0x004B5C76, 0x006E50E3, len(unpatched_lookup_bytes))
    old_lookup_trampoline_v4 = _build_trampoline(0x004B5C76, 0x006E50E4, len(unpatched_lookup_bytes))

    old_null_guard_trampoline = _build_trampoline(0x0066F1FB, 0x006E51C0, 15)

    old_hook_block = bytes.fromhex("e878ee2200e9efffffff9090")

    patches = [
        # Revert old experimental upstream list/profile trampolines.
        DirectPatch(
            name="restore_lookup_search_FUN_00474870",
            site_va=0x00474946,
            expected=orig_search,
            replacement=orig_search,
            alternates=(old_tramp_search,),
        ),
        DirectPatch(
            name="restore_lookup_transfer_FUN_004FA000",
            site_va=0x004FA843,
            expected=orig_transfer_a,
            replacement=orig_transfer_a,
            alternates=(old_tramp_transfer_a,),
        ),
        DirectPatch(
            name="restore_lookup_transfer_FUN_004FAC80",
            site_va=0x004FB594,
            expected=orig_transfer_b,
            replacement=orig_transfer_b,
            alternates=(old_tramp_transfer_b,),
        ),
        # Restore old helper-hooked AND instructions (idempotent upgrade path).
        DirectPatch(
            name="restore_signing_multiyear_hook_FUN_004b8b40",
            site_va=0x004B8C2E,
            expected=bytes.fromhex("25ffff0000"),
            replacement=bytes.fromhex("25ffff0000"),
            alternates=(old_sign_call_a, old_sign_call_a_v2),
        ),
        DirectPatch(
            name="restore_signing_multiyear_hook_FUN_004b8e20",
            site_va=0x004B8EFA,
            expected=bytes.fromhex("25ffff0000"),
            replacement=bytes.fromhex("25ffff0000"),
            alternates=(old_sign_call_b, old_sign_call_b_v2),
        ),
        # Shared source-lookup wrapper hook in both branches.
        DirectPatch(
            name="signing_source_lookup_wrapper_FUN_004b8b40_multiyear",
            site_va=0x004B8C3D,
            expected=_build_call(0x004B8C3D, 0x004A4720),
            replacement=_build_call(0x004B8C3D, sign_helper_va),
        ),
        DirectPatch(
            name="signing_source_lookup_wrapper_FUN_004b8b40_oneyear",
            site_va=0x004B8C73,
            expected=_build_call(0x004B8C73, 0x004A4720),
            replacement=_build_call(0x004B8C73, sign_helper_va),
        ),
        DirectPatch(
            name="signing_source_lookup_wrapper_FUN_004b8e20_multiyear",
            site_va=0x004B8F09,
            expected=_build_call(0x004B8F09, 0x004A4720),
            replacement=_build_call(0x004B8F09, sign_helper_va),
        ),
        DirectPatch(
            name="signing_source_lookup_wrapper_FUN_004b8e20_oneyear",
            site_va=0x004B8F3F,
            expected=_build_call(0x004B8F3F, 0x004A4720),
            replacement=_build_call(0x004B8F3F, sign_helper_va),
        ),
        # Lookup-result fallback hook at FUN_004b5c20 tail.
        DirectPatch(
            name="lookup_result_fallback_FUN_004b5c20",
            site_va=0x004B5C76,
            expected=unpatched_lookup_bytes,
            replacement=_build_trampoline(0x004B5C76, lookup_helper_va, len(unpatched_lookup_bytes)),
            alternates=(
                old_lookup_bytes,
                old_lookup_trampoline,
                old_lookup_trampoline_v2,
                old_lookup_trampoline_v3,
                old_lookup_trampoline_v4,
            ),
        ),
        # Clean obsolete hook block bytes (idempotent).
        DirectPatch(
            name="clear_obsolete_lookup_hook_block",
            site_va=0x004B5C84,
            expected=bytes.fromhex("909090909090909090909090"),
            replacement=bytes.fromhex("909090909090909090909090"),
            alternates=(old_hook_block,),
        ),
        # Proven null-guard trampoline site.
        DirectPatch(
            name="defense_in_depth_textptr_normalize_FUN_0066f1f0",
            site_va=0x0066F1FB,
            expected=bytes.fromhex("8b4c242033f68a472033d28be88a01"),
            replacement=_build_trampoline(0x0066F1FB, CAVE_NULL_GUARD_VA, 15),
            alternates=(old_null_guard_trampoline,),
        ),
    ]

    return patches


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

    bundle, string_addrs, legacy_bundle_prefixes = _build_bundle()

    sign_helper_va = CAVE_BUNDLE_BASE_VA
    sign_helper_len = len(
        _build_signing_source_lookup_fallback_helper(
            cave_va=CAVE_BUNDLE_BASE_VA,
            lookup_call_target_va=0x004A4720,
            stars_va=string_addrs["stars"],
            free_va=string_addrs["free"],
            unknown_va=string_addrs["unknown"],
        )
    )
    lookup_helper_va = CAVE_BUNDLE_BASE_VA + sign_helper_len

    patches = _build_patch_plan(sign_helper_va=sign_helper_va, lookup_helper_va=lookup_helper_va)

    rows: list[dict[str, Any]] = []

    # Write bundle cave region.
    bundle_off = _va_to_file_offset(input_bytes, CAVE_BUNDLE_BASE_VA)
    current_bundle = input_bytes[bundle_off: bundle_off + CAVE_BUNDLE_SIZE]

    all_zero = current_bundle == (b"\x00" * CAVE_BUNDLE_SIZE)
    all_cc = current_bundle == (b"\xCC" * CAVE_BUNDLE_SIZE)
    old_bundle_like = any(current_bundle.startswith(prefix) for prefix in legacy_bundle_prefixes)
    new_bundle = current_bundle == bundle

    if not force and not (all_zero or all_cc or old_bundle_like or new_bundle):
        raise RuntimeError(
            "Bundle cave bytes are not recognized (neither pristine nor known previous patch). "
            "Use --force only after manual verification."
        )

    patched[bundle_off: bundle_off + CAVE_BUNDLE_SIZE] = bundle
    rows.append(
        {
            "name": "write_shared_fallback_bundle_cave",
            "site_va": f"0x{CAVE_BUNDLE_BASE_VA:08X}",
            "site_file_offset": f"0x{bundle_off:08X}",
            "site_before": current_bundle[:64].hex(),
            "site_after": bundle[:64].hex(),
            "bytes_written": CAVE_BUNDLE_SIZE,
        }
    )

    # Apply direct patch sites.
    for spec in patches:
        site_off = _va_to_file_offset(input_bytes, spec.site_va)
        current_site = input_bytes[site_off: site_off + len(spec.expected)]
        allowed = {spec.expected, spec.replacement, *spec.alternates}
        if current_site not in allowed and not force:
            raise RuntimeError(
                f"Patch-site bytes do not match expected signature for {spec.name}. "
                "Use --force only after manual verification."
            )

        patched[site_off: site_off + len(spec.expected)] = spec.replacement
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
    old_null_stub = _build_old_null_guard_stub(
        cave_va=CAVE_NULL_GUARD_VA,
        resume_va=0x0066F20A,
        null_target_va=0x0066F243,
    )

    null_off = _va_to_file_offset(input_bytes, CAVE_NULL_GUARD_VA)
    current_null = input_bytes[null_off: null_off + len(null_stub)]
    old_prefix_ok = current_null.startswith(old_null_stub) and all(
        b == 0 for b in current_null[len(old_null_stub):]
    )

    allowed_null = {b"\x00" * len(null_stub), null_stub}
    if (current_null not in allowed_null) and (not old_prefix_ok) and (not force):
        raise RuntimeError(
            "Null-guard cave bytes are not empty/known. "
            "Use --force only after manual verification."
        )

    patched[null_off: null_off + len(null_stub)] = null_stub
    rows.append(
        {
            "name": "write_null_guard_cave",
            "site_va": f"0x{CAVE_NULL_GUARD_VA:08X}",
            "site_file_offset": f"0x{null_off:08X}",
            "site_before": current_null.hex(),
            "site_after": null_stub.hex(),
            "bytes_written": len(null_stub),
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
        "addresses": {
            "bundle_base": f"0x{CAVE_BUNDLE_BASE_VA:08X}",
            "bundle_size": CAVE_BUNDLE_SIZE,
            "sign_helper": f"0x{sign_helper_va:08X}",
            "lookup_helper": f"0x{lookup_helper_va:08X}",
            "null_guard": f"0x{CAVE_NULL_GUARD_VA:08X}",
            "empty": f"0x{string_addrs['empty']:08X}",
            "stars": f"0x{string_addrs['stars']:08X}",
            "free": f"0x{string_addrs['free']:08X}",
            "unknown": f"0x{string_addrs['unknown']:08X}",
        },
        "sha256": {
            "input": _sha256(input_bytes),
            "output": _sha256(output_bytes),
        },
        "notes": [
            "MANAGPRE-only patch. No database edits.",
            "FUN_0066f1f0 keeps the proven null text-pointer guard (NULL -> empty string).",
            "Signing-message source lookup now uses one shared wrapper across all 4 callsites.",
            "When source lookup returns NULL/empty/placeholder, fallback is Stars/Free players/Unknown club.",
            "FUN_004b5c20 tail now rejects invalid candidate name pointers before fallback mapping.",
            "Legacy experimental upstream list trampolines are reverted to original bytes.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch MANAGPRE.EXE with Valderrama-safe null guard + source-club fallbacks"
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
