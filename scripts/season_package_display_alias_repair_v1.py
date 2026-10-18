#!/usr/bin/env python3
"""Derive a parser-safe display-name candidate from a strict V2 package.

This is a post-ingress repair for a known limitation of fixed PM99 player
carriers: a dated source name can be longer than the native DD6360 string
window, or contain characters outside the executable's CP1252 storage.  The
source name and stable person identity remain untouched.  Only ``player.name``
(the in-game display field) may become a source-derived alias, and every
selection is parser-exercised against the verified clean base before it is
written.

The result is explicitly a static-candidate input.  It is not a canonical
release package, compiler receipt, runtime result, screenshot, or playable
claim.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from scripts import season_package_compiler_v2 as compiler_v2  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402


SCHEMA = "pm99-season-package-display-alias-repair-v1"
STATE = "alias-bound-static-candidate-only"

# NFKD handles most accented Latin characters.  These are the remaining
# letter forms seen in cached historical source names that do not decompose
# into CP1252-compatible characters.  The mapping is a display transliteration
# only; ``source_name`` retains the exact captured spelling.
TRANSLITERATION = str.maketrans({
    "ß": "ss", "ẞ": "SS", "Æ": "AE", "æ": "ae", "Œ": "OE", "œ": "oe",
    "Ø": "O", "ø": "o", "Ð": "D", "ð": "d", "Þ": "Th", "þ": "th",
    "Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ħ": "H", "ħ": "h",
    "ı": "i", "İ": "I", "Ŋ": "NG", "ŋ": "ng", "Ə": "E", "ə": "e",
    "ĸ": "k", "ŧ": "t",
})


class DisplayAliasRepairError(ValueError):
    """The package cannot be safely derived against the named clean base."""


def _canonical_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(dict(value))).hexdigest()


def _portable_source_text(value: str) -> str:
    """Return a conservative CP1252 display transliteration of a source name."""

    normalized = unicodedata.normalize("NFKD", value.translate(TRANSLITERATION))
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
        and unicodedata.category(character) != "Cf"
    ).strip()


def _is_cp1252(value: str) -> bool:
    try:
        value.encode("cp1252", errors="strict")
    except UnicodeEncodeError:
        return False
    return bool(value.strip())


def _name_parts(portable_source_name: str) -> tuple[str, str]:
    """Return the best conservative given/surname pair for aliasing."""

    if "," in portable_source_name:
        surname, remainder = (part.strip() for part in portable_source_name.split(",", 1))
        given = remainder.split()[0] if remainder else ""
        return given, surname
    tokens = portable_source_name.split()
    if not tokens:
        return "", ""
    return tokens[0], tokens[-1]


def _candidate_names(*, source_name: str, requested_name: str, native_name: str) -> list[tuple[str, str]]:
    """Return display candidates in loss-minimising, source-derived order."""

    portable_source = _portable_source_text(source_name)
    without_trailing_nickname = re.sub(r"\s+'[^']+'$", "", portable_source).strip()
    given, surname = _name_parts(portable_source)
    candidates: list[tuple[str, str]] = [
        (requested_name, "requested-display-name"),
        (source_name, "source-name"),
        (portable_source, "transliterated-source-name"),
    ]
    if without_trailing_nickname and without_trailing_nickname != portable_source:
        candidates.append((without_trailing_nickname, "source-derived-without-trailing-nickname"))
    if given and surname:
        candidates.extend([
            (f"{given[0]}. {surname}", "source-derived-initial-surname"),
            (surname, "source-derived-surname"),
            (f"{given} {surname[0]}.", "source-derived-given-initial"),
            (given, "source-derived-given-name"),
            (f"{given[0]}.", "source-derived-initial"),
        ])
    elif surname:
        candidates.extend([
            (surname, "source-derived-surname"),
            (f"{surname[0]}.", "source-derived-initial"),
        ])
    # This terminal fallback is deliberately explicit in the receipt.  It is
    # never a guessed replacement identity and preserves the dated source name
    # separately for later editorial review.
    candidates.append((native_name, "retain-native-display-name"))

    unique: list[tuple[str, str]] = []
    seen: set[str] = set()
    for candidate, method in candidates:
        candidate = " ".join(candidate.split())
        # Multiple apostrophe pairs exercise a false-positive path in the
        # isolated variable-name probe but can corrupt a later appended row.
        # Preserve the exact source_name and select a shorter source-derived
        # display alias instead.
        if candidate.count("'") > 1 or not _is_cp1252(candidate) or candidate in seen:
            continue
        seen.add(candidate)
        unique.append((candidate, method))
    return unique


def _can_apply_name(*, payload: bytes, carrier_id: int, target_name: str) -> bool:
    """Exercise exactly the parser-backed name mutation used by compilation."""

    native_name = compiler_v2._player_name(payload, record_id=carrier_id)
    # The compiler's no-write branch is byte/case exact.  Treating a
    # case-only difference as already applied here let an overlong requested
    # spelling through this preflight and then fail during materialisation.
    # Require exact equality so the candidate loop either proves the requested
    # spelling writable or reaches the exact native fallback.
    if native_name == target_name:
        return True
    try:
        patched, _proof = compiler_v2._patch_indexed_player_variable_name_payload(
            payload, native_name, target_name
        )
    except Exception:
        return False
    observed = compiler_v2._player_name(patched, record_id=carrier_id)
    return observed.casefold() == target_name.casefold()


def _derive_display_name(*, payload: bytes, carrier_id: int, source_name: str, requested_name: str) -> tuple[str, str]:
    native_name = compiler_v2._player_name(payload, record_id=carrier_id)
    # Some native rows contain a duplicated single-token name.  The isolated
    # variable-string mutation can falsely report that shortening it is safe,
    # while the complete appended-record stream retains the duplicate.  Keep
    # the exact source identity separately and bind the already parser-safe
    # native display spelling.
    source_tokens = source_name.split()
    if len(source_tokens) == 1 and native_name.casefold() == f"{source_name} {source_name}".casefold():
        return native_name, "retain-native-duplicated-single-token-display-name"
    if len(source_tokens) == 1 and source_name:
        expanded = f"{source_name[0]}. {source_name}"
        if _can_apply_name(payload=payload, carrier_id=carrier_id, target_name=expanded):
            return expanded, "source-derived-initial-single-token-name"
    for candidate, method in _candidate_names(
        source_name=source_name,
        requested_name=requested_name,
        native_name=native_name,
    ):
        if _can_apply_name(payload=payload, carrier_id=carrier_id, target_name=candidate):
            return candidate, method
    raise DisplayAliasRepairError(
        f"player carrier {carrier_id} has no parser-safe display alias or native fallback"
    )


def derive_alias_bound_package(
    *, package_path: Path, base_tree: Path, verified_base_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return an alias-bound strict package and a complete derivation receipt."""

    package = package_v2.read_canonical_package(package_path)
    package_v2.validate_package(package, strict=True)
    verified_base = pipeline_v2.validate_verified_base_descriptor(
        json.loads(verified_base_path.read_text(encoding="utf-8"))
    )
    pipeline_v2.verify_base_tree(tree=base_tree, verified_base=verified_base)

    jug_path = base_tree / "DBDAT" / "JUG98030.FDI"
    if not jug_path.is_file():
        raise DisplayAliasRepairError(f"clean base has no JUG98030.FDI: {jug_path}")
    jug_data = jug_path.read_bytes()
    entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(jug_data).entries}

    output = copy.deepcopy(package)
    changed: list[dict[str, Any]] = []
    method_counts: Counter[str] = Counter()
    preserved_count = 0
    for player in output["players"]:
        if player.get("policy") == "preserve-existing-mode1":
            preserved_count += 1
            continue
        carrier_id = int(player["carrier_id"])
        entry = entries.get(carrier_id)
        if entry is None:
            append_from = player.get("append_from_carrier_id")
            if not isinstance(append_from, int) or append_from not in entries:
                raise DisplayAliasRepairError(f"player {player['id']} carrier {carrier_id} is absent from clean base")
            # Appended mode-0 rows are created later by the compiler from this
            # exact template.  Alias sizing can therefore be checked against
            # the template payload while retaining the new target carrier ID.
            entry = entries[append_from]
        payload = entry.decode_payload(jug_data)
        source_name = str(player.get("source_name") or player["name"])
        requested_name = str(player["name"])
        display_name, method = _derive_display_name(
            payload=payload,
            carrier_id=carrier_id,
            source_name=source_name,
            requested_name=requested_name,
        )
        method_counts[method] += 1
        if display_name == requested_name:
            continue
        player["name"] = display_name
        changed.append({
            "player_id": player["id"],
            "person_id": player["person_id"],
            "carrier_id": carrier_id,
            "source_name": source_name,
            "previous_display_name": requested_name,
            "display_name": display_name,
            "method": method,
        })

    package_v2.validate_package(output, strict=True)
    audit = {
        "schema_version": SCHEMA,
        "state": STATE,
        "season": output["season"],
        "release_eligible": False,
        "input": {
            "package_sha256": package_v2.sha256_file(package_path),
            "verified_base_sha256": package_v2.sha256_file(verified_base_path),
            "base_inventory_fingerprint": verified_base["inventory"]["files_fingerprint"],
            "base_jug98030_sha256": hashlib.sha256(jug_data).hexdigest(),
            "calendar_contract_sha256": _digest(package["calendar"]),
        },
        "coverage": {
            "player_count": len(output["players"]),
            "writable_player_count": len(output["players"]) - preserved_count,
            "preserve_existing_mode1_player_count": preserved_count,
            "changed_display_name_count": len(changed),
            "parser_safe_display_name_count": len(output["players"]) - preserved_count,
            "method_counts": dict(sorted(method_counts.items())),
        },
        "calendar_contract_preserved": package["calendar"] == output["calendar"],
        "changed_players": changed,
        "not_performed": [
            "binary compiler materialisation",
            "clean static audit",
            "release manifest generation",
            "PM99 runtime validation",
            "target-season runtime screenshot",
        ],
    }
    return output, audit


def _write_new(path: Path, payload: bytes) -> str:
    if path.exists():
        raise DisplayAliasRepairError(f"refusing to replace existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--verified-base", required=True, type=Path)
    parser.add_argument("--output-package", required=True, type=Path)
    parser.add_argument("--output-audit", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output_package.resolve() == args.output_audit.resolve():
        print("display-alias repair error: output package and audit must differ", file=sys.stderr)
        return 2
    if args.output_package.exists() or args.output_audit.exists():
        existing = args.output_package if args.output_package.exists() else args.output_audit
        print(f"display-alias repair error: refusing to replace existing output: {existing.resolve()}", file=sys.stderr)
        return 2
    try:
        output, audit = derive_alias_bound_package(
            package_path=args.package.resolve(),
            base_tree=args.base_tree.resolve(),
            verified_base_path=args.verified_base.resolve(),
        )
        package_payload = _canonical_bytes(output)
        package_sha256 = _write_new(args.output_package.resolve(), package_payload)
        audit["output"] = {
            "package_sha256": package_sha256,
            "package_path": str(args.output_package),
        }
        audit_payload = _canonical_bytes(audit)
        _write_new(args.output_audit.resolve(), audit_payload)
    except (DisplayAliasRepairError, package_v2.PackageValidationError, pipeline_v2.PipelineError, OSError, ValueError) as exc:
        print(f"display-alias repair error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "season": audit["season"]["label"],
        "changed_display_name_count": audit["coverage"]["changed_display_name_count"],
        "output_package_sha256": package_sha256,
        "output_audit": str(args.output_audit),
        "state": audit["state"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
