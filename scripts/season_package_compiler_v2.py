#!/usr/bin/env python3
"""Compile a native PM99 Season Package V2 into a clean materialisation.

This is the binary-writing boundary for Season Pipeline V2.  It consumes the
canonical ``pm99-season-package-v2`` document itself; it never reads the old
2015 source ledgers, an earlier release tree, a browser-session export, or an
unhashed ratings file.

The compiler is deliberately narrow.  It writes the runtime-proven JUG, EQ
and ENT lanes only, and requires a clean copy of the verified base as its
target.  Portraits, kits and calendar patches are separate V2 stages.  In
particular, a missing portrait is *not* a compiler failure: the portrait stage
must materialise it as PM99's native no-photo state and record that decision.

Editorial feedback is represented by the canonical source-only review overlay
implemented in ``season_review_v2``.  The compiler derives an in-memory V2
package from that overlay before it writes any binary; an overlay is never an
in-place edit of a released game folder.  Its hash and derivation receipt
appear in this compiler's receipt and therefore in the build-plan's
external-artifact lock.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import struct
import sys
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.editor_actions import (  # noqa: E402
    _apply_player_mutations,
    _native_dd6360_role_start,
    _patch_indexed_player_variable_name_payload,
    _read_native_dd6360_fields,
)
from app.eq_jug_linked import parse_eq_external_team_roster_payload  # noqa: E402
from app.eq_team_indexed_metadata import (  # noqa: E402
    extract_indexed_team_payload_metadata,
    patch_indexed_team_mode0_starting_finance,
    patch_indexed_team_seated_capacity,
)
from app.eq_team_manager_links import patch_indexed_eq_active_manager_id  # noqa: E402
from app.eq_initial_tactics import patch_initial_tactics  # noqa: E402
from app.fdi_indexed import IndexedFDIFile  # noqa: E402
from app.indexed_jug_identity import read_indexed_player_id, rebind_indexed_player_id  # noqa: E402
from app.models import PlayerRecord  # noqa: E402
from app.xor import xor_decode, xor_encode  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402
from scripts import season_pipeline_v2 as pipeline_v2  # noqa: E402
from scripts import season_review_v2 as review_v2  # noqa: E402
from scripts.build_2015_english92_release import (  # noqa: E402
    EQ_TACTICS_TOTAL_BYTES,
    NATIONALITY,
    POSITION,
    SKILLS,
    VISIBLE_SKILLS,
    _country_code,
    _find_dd6361_name_end,
    _mode1_initial_tactics_offset as _mode1_opaque_prelink_offset_from_shared_prefix,
    _patch_dd6361_visible_handling,
    _patch_ent_name,
    _read_inner_string,
    _rebuild_indexed,
    _rewrite_eq_strings,
    _rewrite_roster_tail,
    _set_dd6360_native_player_fields,
    _set_dd6361_roles_and_startup,
    _write_initial_tactics,
)


# The generic indexed writer has nine contiguous attribute slots.  Compact
# dd6360 records have one additional, immediately following live byte for
# Handling.  Keep the two collections separate: treating the latter as a
# generic tenth slot is what previously made it too easy to edit the wrong
# tail byte on other player families.
DD6360_VISIBLE_SKILLS = (*SKILLS, "handling")


def _preserved_eq_stadium_name(decoded: bytes) -> str:
    """Read the existing stadium string so the shared string writer preserves it."""
    marker = decoded.find(b"\xdd\x63\x61", 2, 64)
    if marker < 2:
        raise SeasonCompilerError("EQ string marker missing for ground preservation")
    _short, _start, short_end = _read_inner_string(decoded, marker + 4)
    stadium, _start, _end = _read_inner_string(decoded, short_end)
    return stadium


def _mode1_opaque_prelink_offset(raw_payload: bytes) -> int:
    """Locate the mode-1 opaque pre-link block without granting it semantics.

    The shared EQ prefix parser establishes the byte boundary.  Ghidra proves
    that the `0x6e7` region is skipped by the DBASEPRE sparse-state reader for
    mode 1, so this helper exists only to make byte-preservation assertions
    precise.  It is not an opening-tactics writer.
    """

    return _mode1_opaque_prelink_offset_from_shared_prefix(raw_payload)


# Kept as a private compatibility alias for the existing regression fixture.
# New code must use `_mode1_opaque_prelink_offset`, which states the real
# preserve-only contract.
def _mode1_initial_tactics_offset(raw_payload: bytes) -> int:
    return _mode1_opaque_prelink_offset(raw_payload)

COMPILER_RECEIPT_SCHEMA = "pm99-season-package-compiler-receipt-v1"
# The public review-overlay contract is owned by season_review_v2.  Keep the
# old experimental compiler-only parser visibly versioned so it cannot accept
# a document which claims to be the real V1 contract.
OVERRIDES_SCHEMA = review_v2.OVERRIDES_SCHEMA
LEGACY_COMPILER_OVERRIDES_SCHEMA = "pm99-season-review-overrides-legacy-compiler-v0"
DATABASE_RELATIVE_PATHS = (
    "DBDAT/ENT98030.FDI",
    "DBDAT/EQ98030.FDI",
    "DBDAT/JUG98030.FDI",
)
COUNTRY_TABLE_RELATIVE_PATH = "DBDAT/TEXTOS.PKF"
_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,79}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_OVERRIDE_KEYS = {
    "schema_version",
    "base_package_sha256",
    "source_review_request_sha256",
    "revision_id",
    "review_note",
    "players",
    "clubs",
    "managers",
    "portraits",
}
_PLAYER_OVERRIDE_KEYS = {"id", "expected", "name", "facts", "ratings"}
_CLUB_OVERRIDE_KEYS = {
    "id",
    "expected",
    "name",
    "full_name",
    "ground_name",
    "seated_capacity",
    "starting_finance",
    "manager_id",
    "roster_player_ids",
    "opening",
}
_MANAGER_OVERRIDE_KEYS = {"id", "expected", "name"}
_PORTRAIT_OVERRIDE_KEYS = {"player_id", "expected", "status", "note"}
_PLAYER_FACT_KEYS = {
    "birth_date",
    "nationality",
    "height_cm",
    "weight_kg",
    "primary_position",
    "fine_roles",
    "shirt_number",
}
_RATING_VALUE_KEYS = {
    "quality",
    "speed",
    "stamina",
    "aggression",
    "passing",
    "tackling",
    "heading",
    "shooting",
    "dribbling",
    "handling",
}
_POSITION_BY_CODE = {value: key for key, value in POSITION.items()}


class SeasonCompilerError(ValueError):
    """The package cannot be represented by the proven PM99 write lanes."""


def _sha256_file(path: Path) -> str:
    return pipeline_v2.sha256_file(path)


def _canonical_json_bytes(value: Any) -> bytes:
    return package_v2.canonical_json_bytes(value)


def _read_canonical_json(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SeasonCompilerError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict) or raw != _canonical_json_bytes(value):
        raise SeasonCompilerError(f"{label} must use canonical JSON bytes: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def _require_id(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value):
        raise SeasonCompilerError(f"{label} must be a stable lower-case id")
    return value


def _require_string(value: Any, *, label: str, maximum: int = 255) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SeasonCompilerError(f"{label} must be a non-blank string")
    normalised = unicodedata.normalize("NFC", value)
    try:
        encoded = normalised.encode("cp1252")
    except UnicodeEncodeError as exc:
        raise SeasonCompilerError(f"{label} cannot be represented by PM99 CP1252") from exc
    if len(encoded) > maximum:
        raise SeasonCompilerError(f"{label} exceeds PM99's {maximum}-byte CP1252 limit")
    return normalised


def _pm99_text(value: Any, *, label: str) -> str:
    """Use the legacy compiler's conservative CP1252 transliteration boundary."""

    substitutions = str.maketrans(
        {
            "Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ø": "O", "ø": "o",
            "Þ": "Th", "þ": "th", "Æ": "AE", "æ": "ae", "Ð": "D", "ð": "d",
            "İ": "I", "ı": "i",
        }
    )
    if not isinstance(value, str) or not value.strip():
        raise SeasonCompilerError(f"{label} must be a non-blank string")
    # Preserve names PM99 can represent exactly.  Only enter the documented
    # ASCII fallback when the source contains a character outside CP1252;
    # unconditional NFKD conversion needlessly changed native names such as
    # Marín and defeated exact no-write preservation rows.
    source = " ".join(unicodedata.normalize("NFC", value).split())
    try:
        source.encode("cp1252")
    except UnicodeEncodeError:
        pass
    else:
        return _require_string(source, label=label)
    text = unicodedata.normalize("NFKD", source.translate(substitutions))
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = " ".join(text.split())
    return _require_string(text, label=label)


def _deep_patch(target: dict[str, Any], patch: Mapping[str, Any]) -> None:
    """Apply a shallow field patch with one explicit nested level.

    This avoids generic JSON merge-patch semantics, where an accidental ``null``
    can delete a cross-record relation.  Package validation runs immediately
    after all patches, but the narrow merge itself is the first guardrail.
    """

    for key, value in patch.items():
        if key in {"id", "expected"}:
            continue
        if isinstance(value, dict):
            current = target.get(key)
            if not isinstance(current, dict):
                raise SeasonCompilerError(f"cannot merge object into non-object field {key!r}")
            _deep_patch(current, value)
        else:
            target[key] = copy.deepcopy(value)


def _index(items: list[dict[str, Any]], *, label: str, id_key: str = "id") -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in items:
        identity = row.get(id_key)
        if not isinstance(identity, str) or identity in indexed:
            raise SeasonCompilerError(f"{label} must contain unique string {id_key}s")
        indexed[identity] = row
    return indexed


def _validate_override_rows(
    rows: Any,
    *,
    label: str,
    allowed_keys: set[str],
    identity_key: str = "id",
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise SeasonCompilerError(f"review overrides {label} must be a list")
    result: list[dict[str, Any]] = []
    previous = ""
    for number, row in enumerate(rows):
        if not isinstance(row, dict) or not set(row) <= allowed_keys:
            raise SeasonCompilerError(f"review overrides {label}[{number}] have unsupported fields")
        identity = _require_id(row.get(identity_key), label=f"review overrides {label}[{number}].{identity_key}")
        if identity <= previous:
            raise SeasonCompilerError(f"review overrides {label} must be id-sorted and unique")
        previous = identity
        result.append(copy.deepcopy(row))
    return result


def _validate_expected_identity(
    value: Any,
    *,
    label: str,
    required_keys: set[str],
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != required_keys:
        raise SeasonCompilerError(f"{label} must contain exactly {sorted(required_keys)}")
    if "carrier_id" in required_keys:
        carrier = value["carrier_id"]
        if not isinstance(carrier, int) or isinstance(carrier, bool) or carrier < 1:
            raise SeasonCompilerError(f"{label}.carrier_id must be a positive integer")
    if "club_id" in required_keys:
        _require_id(value["club_id"], label=f"{label}.club_id")
    if "name" in required_keys:
        _require_string(value["name"], label=f"{label}.name")
    return copy.deepcopy(value)


def _assert_expected_identity(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    label: str,
) -> None:
    """Reject a valid package when an overlay describes a different entity.

    The package hash protects against a stale package file.  These redundant
    per-row assertions protect against the other common review mistake: a
    human selecting the wrong stable ID while looking at a long squad list.
    """

    for key, expected_value in expected.items():
        if actual.get(key) != expected_value:
            raise SeasonCompilerError(
                f"review override identity mismatch for {label}: expected {key}={expected_value!r}, "
                f"package has {actual.get(key)!r}"
            )


def validate_review_overrides(overlay: Any, *, package_sha256: str) -> dict[str, Any]:
    """Validate one in-memory targeted, hash-locked feedback overlay.

    It is intentionally not a second season package.  It identifies a single
    immutable source package and allows only reviewable fields that the native
    compiler can actually consume.  Competition/division rewrites are absent:
    those remain behind the foreign-membership research gate.
    """

    if (
        not isinstance(overlay, dict)
        or set(overlay) != _OVERRIDE_KEYS
        or overlay.get("schema_version") != LEGACY_COMPILER_OVERRIDES_SCHEMA
    ):
        raise SeasonCompilerError(
            "legacy compiler review overlays are retired; use "
            "pm99-season-review-overrides-v1 via scripts/season_review_v2.py"
        )
    if overlay.get("base_package_sha256") != package_sha256:
        raise SeasonCompilerError("review overrides are locked to a different season package")
    request_hash = overlay.get("source_review_request_sha256")
    if request_hash is not None and (not isinstance(request_hash, str) or not _SHA256_RE.fullmatch(request_hash)):
        raise SeasonCompilerError("review overrides source_review_request_sha256 must be a SHA-256 or null")
    _require_id(overlay.get("revision_id"), label="review overrides revision_id")
    _require_string(overlay.get("review_note"), label="review overrides review_note", maximum=500)

    players = _validate_override_rows(
        overlay.get("players"), label="players", allowed_keys=_PLAYER_OVERRIDE_KEYS
    )
    for row in players:
        _validate_expected_identity(
            row.get("expected"), label=f"review player {row['id']} expected",
            required_keys={"carrier_id", "club_id", "name"},
        )
        facts = row.get("facts")
        if facts is not None and (not isinstance(facts, dict) or not facts or not set(facts) <= _PLAYER_FACT_KEYS):
            raise SeasonCompilerError("review player facts must be a non-empty supported field object")
        ratings = row.get("ratings")
        if ratings is not None:
            if not isinstance(ratings, dict) or set(ratings) != {"values"}:
                raise SeasonCompilerError("review player ratings may patch only ratings.values")
            values = ratings.get("values")
            if not isinstance(values, dict) or not values or not set(values) <= _RATING_VALUE_KEYS:
                raise SeasonCompilerError("review player ratings.values have unsupported fields")
            if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 99 for value in values.values()):
                raise SeasonCompilerError("review player rating values must be integers in 0..99")

    clubs = _validate_override_rows(
        overlay.get("clubs"), label="clubs", allowed_keys=_CLUB_OVERRIDE_KEYS
    )
    for row in clubs:
        _validate_expected_identity(
            row.get("expected"), label=f"review club {row['id']} expected",
            required_keys={"carrier_id", "name"},
        )
    managers = _validate_override_rows(
        overlay.get("managers"), label="managers", allowed_keys=_MANAGER_OVERRIDE_KEYS
    )
    for row in managers:
        _validate_expected_identity(
            row.get("expected"), label=f"review manager {row['id']} expected",
            required_keys={"carrier_id", "name"},
        )
    portraits = _validate_override_rows(
        overlay.get("portraits"), label="portraits", allowed_keys=_PORTRAIT_OVERRIDE_KEYS,
        identity_key="player_id",
    )
    for row in portraits:
        _validate_expected_identity(
            row.get("expected"), label=f"review portrait {row['player_id']} expected",
            required_keys={"carrier_id", "club_id", "name"},
        )
        if row.get("status") not in {"native-no-photo", "unresolved", "applied"}:
            raise SeasonCompilerError("review portrait status is unsupported")
        _require_string(row.get("note"), label="review portrait note", maximum=500)
    return {
        "schema_version": LEGACY_COMPILER_OVERRIDES_SCHEMA,
        "base_package_sha256": package_sha256,
        "source_review_request_sha256": request_hash,
        "revision_id": overlay["revision_id"],
        "review_note": overlay["review_note"],
        "players": players,
        "clubs": clubs,
        "managers": managers,
        "portraits": portraits,
    }


def load_review_overrides(path: Path, *, package_sha256: str) -> tuple[dict[str, Any], str]:
    """Read a canonical review overlay and return it with its content hash."""

    overlay, digest = _read_canonical_json(path, label="review overrides")
    return validate_review_overrides(overlay, package_sha256=package_sha256), digest


def apply_review_overrides(package: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    """Return a validated resolved package without modifying its source bytes."""

    resolved = copy.deepcopy(package)
    players = _index(resolved["players"], label="package players")
    clubs = _index(resolved["clubs"], label="package clubs")
    managers = _index(resolved["managers"], label="package managers")
    portraits = _index(resolved["assets"]["portraits"], label="package portraits", id_key="player_id")
    player_identities = {
        identity: {
            "carrier_id": target["carrier_id"],
            "club_id": target["club_id"],
            "name": target["name"],
        }
        for identity, target in players.items()
    }
    club_identities = {
        identity: {"carrier_id": target["carrier_id"], "name": target["name"]}
        for identity, target in clubs.items()
    }
    manager_identities = {
        identity: {"carrier_id": target["carrier_id"], "name": target["name"]}
        for identity, target in managers.items()
    }

    for row in overlay["players"]:
        target = players.get(row["id"])
        if target is None:
            raise SeasonCompilerError(f"review override targets unknown player {row['id']!r}")
        _assert_expected_identity(
            row["expected"],
            player_identities[row["id"]],
            label=f"player {row['id']}",
        )
        _deep_patch(target, row)
    for row in overlay["clubs"]:
        target = clubs.get(row["id"])
        if target is None:
            raise SeasonCompilerError(f"review override targets unknown club {row['id']!r}")
        _assert_expected_identity(
            row["expected"],
            club_identities[row["id"]],
            label=f"club {row['id']}",
        )
        _deep_patch(target, row)
    for row in overlay["managers"]:
        target = managers.get(row["id"])
        if target is None:
            raise SeasonCompilerError(f"review override targets unknown manager {row['id']!r}")
        _assert_expected_identity(
            row["expected"],
            manager_identities[row["id"]],
            label=f"manager {row['id']}",
        )
        _deep_patch(target, row)
    for row in overlay["portraits"]:
        target = portraits.get(row["player_id"])
        if target is None:
            raise SeasonCompilerError(f"review override targets unknown portrait {row['player_id']!r}")
        _assert_expected_identity(
            row["expected"],
            player_identities[row["player_id"]],
            label=f"portrait {row['player_id']}",
        )
        target["status"] = row["status"]
        # The note belongs to the overlay receipt, not the portable package.

    # Cross-links, ranges, tactics ordering and asset completeness still apply.
    try:
        package_v2.validate_package(resolved, strict=True)
    except package_v2.PackageValidationError as exc:
        raise SeasonCompilerError(f"review overrides violate Season Package V2: {exc}") from exc
    return resolved


def _load_native_package(path: Path) -> tuple[dict[str, Any], str]:
    package = package_v2.read_canonical_package(path)
    try:
        package_v2.validate_package(package, strict=True)
    except package_v2.PackageValidationError as exc:
        raise SeasonCompilerError(f"native compiler requires a strict V2 package: {exc}") from exc
    return package, _sha256_file(path)


def _derive_reviewed_package(
    *,
    source_package: dict[str, Any],
    overrides_path: Path,
    derived_package_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Apply the one supported V1 review contract before binary planning.

    ``season_review_v2`` owns both the schema and the source derivation.  This
    adapter deliberately does not duplicate that logic: it gives the compiler
    a strict derived package only after hash, expected-value, duplicate-field,
    proof and identity checks have all passed.  The caller invokes this before
    obtaining writable paths, which makes an invalid review a no-write error.
    """

    if derived_package_id is None:
        raise SeasonCompilerError(
            "--derived-package-id is required with --overrides; derive a named "
            "source revision rather than editing a release tree"
        )
    try:
        overrides = review_v2.read_overrides(overrides_path)
        derived, application_receipt = review_v2.apply_overrides(
            source_package,
            overrides,
            derived_package_id=derived_package_id,
        )
    except (OSError, package_v2.PackageValidationError, review_v2.SeasonReviewError) as exc:
        raise SeasonCompilerError(f"review overlay cannot derive a source package: {exc}") from exc
    return (
        derived,
        application_receipt,
        review_v2.sha256_bytes(review_v2.canonical_json_bytes(overrides)),
    )


def _ensure_clean_database_inputs(*, base_tree: Path, materialisation_tree: Path) -> dict[str, Path]:
    base_tree = base_tree.expanduser().resolve()
    materialisation_tree = materialisation_tree.expanduser().resolve()
    if base_tree == materialisation_tree:
        raise SeasonCompilerError("base tree and materialisation tree must be distinct")
    if not base_tree.is_dir() or not materialisation_tree.is_dir():
        raise SeasonCompilerError("base tree and materialisation tree must both exist")
    paths: dict[str, Path] = {}
    for relative in (*DATABASE_RELATIVE_PATHS, COUNTRY_TABLE_RELATIVE_PATH):
        source = base_tree / relative
        target = materialisation_tree / relative
        if not source.is_file() or source.is_symlink() or not target.is_file() or target.is_symlink():
            raise SeasonCompilerError(f"required PM99 database file is missing or unsafe: {relative}")
        if _sha256_file(source) != _sha256_file(target):
            raise SeasonCompilerError(
                f"materialisation is not a clean copy of the verified base for {relative}; rebuild from base"
            )
        paths[relative] = target
    return paths


def _iso_date(value: Any, *, label: str) -> tuple[int, int, int]:
    if not isinstance(value, str):
        raise SeasonCompilerError(f"{label} must be ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise SeasonCompilerError(f"{label} is not a valid ISO date") from exc
    return parsed.day, parsed.month, parsed.year


def _extract_country_codes_from_textos(textos_pkf: Path) -> dict[str, int]:
    """Read the existing PM99 country table without importing a web client.

    The historic helper lived in a capture script which imports ``requests`` at
    module level.  A deterministic offline compiler must not acquire that
    dependency merely to read a local TEXTOS.PKF file, so the small
    parser-backed extraction lives here as part of the compiler boundary.
    """

    decoded = bytes(byte ^ 0x61 for byte in textos_pkf.read_bytes())
    germany = decoded.find(b"GERMANY")
    if germany < 0:
        raise SeasonCompilerError("TEXTOS.PKF does not contain the English country-table anchor")
    probe = decoded[max(0, germany - 200) : germany + 12_000]
    printable = "".join(chr(byte) if 32 <= byte < 127 else " " for byte in probe)
    printable = re.sub(r"\s+", " ", printable)
    tokens: list[str] = []
    for token in re.findall(r"[A-Z][A-Z .'\-/]{1,}", printable):
        cleaned = token.strip(" .-")
        if len(cleaned) >= 2 and (not tokens or tokens[-1] != cleaned):
            tokens.append(cleaned)
    try:
        start = next(index for index, token in enumerate(tokens) if token in {"XXX", "XXXX"} and index + 1 < len(tokens) and tokens[index + 1] == "ALBANIA")
        end = tokens.index("VANUATU", start)
    except StopIteration as exc:
        raise SeasonCompilerError("TEXTOS.PKF country-table start is not parser-backed") from exc
    except ValueError as exc:
        raise SeasonCompilerError("TEXTOS.PKF country-table end is not parser-backed") from exc
    return {country: index for index, country in enumerate(tokens[start : end + 1])}


def _player_name(payload: bytes, *, record_id: int) -> str:
    try:
        name = str(PlayerRecord.from_bytes(payload, 0).name or "").strip()
    except Exception as exc:
        raise SeasonCompilerError(f"player carrier {record_id} cannot be parsed for variable-name rewrite") from exc
    if not name or name in {"Unknown Player", "Parse Error"}:
        raise SeasonCompilerError(f"player carrier {record_id} has no safe variable-name anchor")
    return name


def _club_player_orders(package: Mapping[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    shared_seen: set[str] = set()
    for club in package["clubs"]:
        shared = set(club.get("shared_preserve_player_ids") or [])
        roster = club["roster_player_ids"]
        opening = club.get("opening", {})
        selected = [*opening.get("starting_xi_player_ids", []), *opening.get("substitute_player_ids", [])]
        if len(selected) != len(set(selected)) or not set(selected) <= set(roster):
            raise SeasonCompilerError(f"club {club['id']} has an invalid opening selection")
        ordered = selected + [pid for pid in roster if pid not in set(selected)]
        for order, player_id in enumerate(ordered, start=1):
            if player_id in result:
                if player_id not in shared and player_id not in shared_seen:
                    raise SeasonCompilerError(f"player {player_id!r} occurs in more than one club roster without a shared-preserve declaration")
                continue
            result[player_id] = order
            if player_id in shared:
                shared_seen.add(player_id)
    player_ids = {row["id"] for row in package["players"]}
    if set(result) != player_ids:
        absent = sorted(player_ids - set(result))
        raise SeasonCompilerError(f"every package player must occur in one club roster; absent: {absent[:5]}")
    return result


def _club_modes(package: Mapping[str, Any], eq_data: bytes) -> dict[str, int]:
    """Resolve the immutable EQ layout mode for every requested carrier.

    ``record_mode`` is a layout selector, not a country or competition field.
    It is read here solely to select the already-proven writer surface.  In
    particular, a mode-1 carrier is *not* given the English opening-tactics or
    finance writer just because it has the same headline record size.
    """

    entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(eq_data).entries}
    result: dict[str, int] = {}
    for club in package["clubs"]:
        carrier = int(club["carrier_id"])
        entry = entries.get(carrier)
        if entry is None:
            raise SeasonCompilerError(f"club carrier {carrier} is absent from EQ98030.FDI")
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        try:
            metadata = extract_indexed_team_payload_metadata(raw)
            mode = int(metadata["record_mode"])
        except Exception as exc:
            raise SeasonCompilerError(
                f"club {club['id']} carrier {carrier} has no parser-backed modern EQ mode"
            ) from exc
        if mode not in {0, 1}:
            raise SeasonCompilerError(
                f"club {club['id']} uses unsupported EQ mode {mode}; preserve its carrier"
            )
        result[str(club["id"])] = mode
    return result


def _patch_dd6360_mode1_safe_fields(
    payload: bytes,
    *,
    position: int | None,
    nationality: int | None,
    birth_day: int | None,
    birth_month: int | None,
    birth_year: int | None,
    height: int | None,
    weight: int | None,
    skills: Mapping[str, int],
    native_role_start: int,
    fine_roles: Sequence[int] | None,
) -> bytes:
    """Write the bounded foreign ``dd6360`` player core and candidate roles.

    The compact native stream has two pre-role bytes, six independent
    tactical candidate bytes, then the profile metadata block.
    The caller passes active candidate codes in preference order; unused slots
    are written as PM99's native zero/unassigned representation.  Neither
    control byte is interpreted or changed here.
    """

    if payload[2:5] != b"\xdd\x63\x60":
        raise SeasonCompilerError("mode-1 core player writer requires a dd6360 payload")
    if position is not None and not 0 <= position <= 3:
        raise SeasonCompilerError("mode-1 core player received an invalid broad position")
    if None not in {birth_day, birth_month, birth_year} and not (1 <= int(birth_day) <= 31 and 1 <= int(birth_month) <= 12 and 1900 <= int(birth_year) <= 2100):
        raise SeasonCompilerError("mode-1 core player writer received an invalid date of birth")
    if height is not None and weight is not None and not (50 <= height <= 250 and 40 <= weight <= 140):
        raise SeasonCompilerError("mode-1 core player writer received invalid height or weight")
    if native_role_start < 8 or native_role_start + 28 > len(payload):
        raise SeasonCompilerError("mode-1 core player block overruns its payload")
    if fine_roles is not None and (
        not 1 <= len(fine_roles) <= 6
        or any(not isinstance(value, int) or not 0 <= int(value) <= 17 for value in fine_roles)
    ):
        raise SeasonCompilerError("mode-1 core player received invalid fine-role candidates")

    result = bytearray(payload)

    def write_xor(offset: int, value: int) -> None:
        if not 0 <= int(value) <= 255:
            raise SeasonCompilerError(f"mode-1 core player byte outside range at {offset}: {value}")
        result[offset] = int(value) ^ 0x61

    for slot in range(6) if fine_roles is not None else ():
        # Fine roles are stored one-based; a decoded zero is PM99's native
        # unassigned slot. Both bytes preceding the role window stay untouched.
        value = int(fine_roles[slot]) + 1 if slot < len(fine_roles) else 0
        write_xor(native_role_start + 2 + slot, value)
    if nationality is not None: write_xor(native_role_start + 8, nationality)
    # +9 is an unknown control byte and remains preserve-only.  +10 and +11
    # are the parser/display broad-position pair consumed by the profile UI.
    if position is not None:
        write_xor(native_role_start + 10, position); write_xor(native_role_start + 11, position)
    if birth_day is not None: write_xor(native_role_start + 12, birth_day)
    if birth_month is not None: write_xor(native_role_start + 13, birth_month)
    if birth_year is not None:
        write_xor(native_role_start + 14, birth_year & 0xFF); write_xor(native_role_start + 15, birth_year >> 8)
    if height is not None: write_xor(native_role_start + 16, height)
    if weight is not None: write_xor(native_role_start + 17, weight)
    for index, field in enumerate(SKILLS):
        value = int(skills[field])
        if not 0 <= value <= 100:
            raise SeasonCompilerError(f"mode-1 core player has invalid {field}: {value}")
        write_xor(native_role_start + 18 + index, value)
    if "handling" in skills:
        handling = int(skills["handling"])
        if not 0 <= handling <= 100:
            raise SeasonCompilerError(f"mode-1 core player has invalid handling: {handling}")
        # FUN_004afd80 copies this tenth byte into player+0xd3; the profile
        # renderer labels that member HANDLING.  It is adjacent to, but outside,
        # the generic nine-slot trailing window, so it must be written explicitly.
        write_xor(native_role_start + 27, handling)
    return bytes(result)


def _dd6361_active_fine_roles_in_order(payload: bytes, *, carrier: int) -> list[int]:
    """Read a full-player role candidate sequence without assigning priority."""

    if payload[2:5] != b"\xdd\x63\x61":
        raise SeasonCompilerError(f"mode-1 dd6361 carrier {carrier} has the wrong player family")
    try:
        name_end = _find_dd6361_name_end(payload)
    except Exception as exc:
        raise SeasonCompilerError(
            f"mode-1 dd6361 carrier {carrier} has no parser-backed role-vector anchor"
        ) from exc
    if name_end + 8 > len(payload):
        raise SeasonCompilerError(f"mode-1 dd6361 carrier {carrier} role vector overruns payload")
    roles: list[int] = []
    for slot in range(6):
        encoded = int(payload[name_end + 2 + slot] ^ 0x61)
        if encoded:
            role = encoded - 1
            if not 0 <= role <= 17:
                raise SeasonCompilerError(
                    f"mode-1 dd6361 carrier {carrier} has unsupported fine-role code {role}"
                )
            roles.append(role)
    if not roles:
        raise SeasonCompilerError(f"mode-1 dd6361 carrier {carrier} has no active fine role")
    return roles


def _patch_dd6361_mode1_safe_fields(
    payload: bytes,
    *,
    position: int | None,
    nationality: int | None,
    birth_day: int | None,
    birth_month: int | None,
    birth_year: int | None,
    height: int | None,
    weight: int | None,
    skills: Mapping[str, int],
) -> bytes:
    """Write the isolated full-player foreign core lane byte-accountably.

    The one existing mode-1 ``dd6361`` record has a full generic player
    layout. The product codec round-trips that layout except for its opaque
    indexed two-byte preamble; preserve those two original bytes explicitly
    and reject the lane if an otherwise untouched round-trip is not exact.
    """

    if payload[2:5] != b"\xdd\x63\x61":
        raise SeasonCompilerError("mode-1 dd6361 core writer received a non-dd6361 payload")
    if position is not None and not 0 <= position <= 3:
        raise SeasonCompilerError("mode-1 dd6361 core player received an invalid broad position")
    if (birth_day is not None and not 1 <= birth_day <= 31) or (birth_month is not None and not 1 <= birth_month <= 12) or (birth_year is not None and not 1900 <= birth_year <= 2100):
        raise SeasonCompilerError("mode-1 dd6361 core player received an invalid date of birth")
    if (height is not None and not 50 <= height <= 250) or (weight is not None and not 40 <= weight <= 140):
        raise SeasonCompilerError("mode-1 dd6361 core player received invalid height or weight")

    name_end = _find_dd6361_name_end(payload)
    native_year = int.from_bytes(bytes(byte ^ 0x61 for byte in payload[name_end + 14:name_end + 16]), 'little')
    record = PlayerRecord.from_bytes(payload, 0)
    pristine = bytearray(record.to_bytes())
    if len(pristine) != len(payload):
        raise SeasonCompilerError("mode-1 dd6361 codec changed payload length on a no-op round trip")
    pristine[:2] = payload[:2]
    # The generic legacy serializer clamps post-1999 DOBs even on a no-op.
    # Account for this known field only; every other byte must still round-trip
    # exactly. The separately patched modern game accepts these native years.
    if 2000 <= native_year <= 2100:
        pristine[name_end + 14:name_end + 16] = payload[name_end + 14:name_end + 16]
    if bytes(pristine) != payload:
        raise SeasonCompilerError("mode-1 dd6361 codec does not preserve this record's unknown bytes")

    role_before = _dd6361_active_fine_roles_in_order(payload, carrier=-1)
    role_window = range(name_end + 2, name_end + 8)
    role_bytes_before = bytes(payload[offset] for offset in role_window)
    _apply_player_mutations(
        record,
        position=position,
        nationality=nationality,
        birth_day=birth_day,
        birth_month=birth_month,
        birth_year=birth_year,
        height=height,
        weight=weight,
        attribute_updates={slot: int(skills[field]) for slot, field in zip(range(3, 12), SKILLS, strict=True)},
        offset=0,
    )
    result = bytearray(record.to_bytes())
    if len(result) != len(payload):
        raise SeasonCompilerError("mode-1 dd6361 core mutation changed payload length")
    # The legacy generic model intentionally clamps DOB authoring to 1999.
    # Modern season executables have a separately verified year-bound patch;
    # write the proven native u16 year at this already validated suffix anchor
    # explicitly instead of silently retaining the previous person's year.
    if birth_year is not None:
        result[name_end + 14:name_end + 16] = bytes(
            byte ^ 0x61 for byte in int(birth_year).to_bytes(2, 'little'))
    else:
        result[name_end + 14:name_end + 16] = payload[name_end + 14:name_end + 16]
    result[:2] = payload[:2]
    if _dd6361_active_fine_roles_in_order(bytes(result), carrier=-1) != role_before:
        raise SeasonCompilerError("mode-1 dd6361 core mutation changed the fine-role candidate set")
    if bytes(result[offset] for offset in role_window) != role_bytes_before:
        raise SeasonCompilerError("mode-1 dd6361 core mutation changed the fine-role byte window")
    return bytes(result)


def _guard_mode1_dd6361_preserve_only_player_fields(
    *,
    decoded: bytes,
    facts: Mapping[str, Any],
    player_id: str,
    carrier: int,
) -> None:
    """Reject mode-1 dd6361 writes outside the proven isolated core lane."""

    requested_roles = facts.get("fine_roles")
    preserve_roles = (
        isinstance(requested_roles, Mapping)
        and requested_roles.get("policy") == "preserve-existing-mode1"
    )
    if not preserve_roles:
        if not isinstance(requested_roles, list) or not requested_roles:
            raise SeasonCompilerError(f"mode-1 dd6361 player {player_id} has invalid fine-role values")
        if [int(value) for value in requested_roles] != _dd6361_active_fine_roles_in_order(decoded, carrier=carrier):
            raise SeasonCompilerError(
                f"mode-1 dd6361 player {player_id} requests an unproven fine-role rewrite"
            )
    shirt = facts.get("shirt_number")
    preserve_shirt = (
        isinstance(shirt, Mapping)
        and shirt.get("policy") == "preserve-existing-mode1"
    )
    if not preserve_shirt and int(shirt if shirt is not None else -1) != 0:
        raise SeasonCompilerError(
            f"mode-1 dd6361 player {player_id} requests a shirt number; foreign storage is unproven"
        )


def _plan_mode1_dd6360_player_fields(
    *,
    decoded: bytes,
    facts: Mapping[str, Any],
    player_id: str,
    allow_recycle_normalisation: bool = False,
) -> tuple[int, int | None, list[int] | None]:
    """Resolve the bounded runtime-proven foreign player-write surface.

    Compact role bytes form one six-slot tactical candidate set.  All six are
    encoded together, while the two adjacent controls remain opaque.  A
    legacy outlier cannot be normalised by a release: it must be left alone
    or moved through an explicitly compatible carrier transaction.
    """

    try:
        role_start = int(_native_dd6360_role_start(decoded))
        current = _read_native_dd6360_fields(decoded, role_start)
    except Exception as exc:
        raise SeasonCompilerError(
            f"mode-1 player {player_id} has no safe native dd6360 role cursor"
        ) from exc

    baseline_roles = [int(value) for value in current["fine_role_codes"]]
    unsupported_baseline_roles = [
        value for value in baseline_roles if value not in {*range(18), 98}
    ]
    requested_roles = facts.get("fine_roles")
    preserve_roles = isinstance(requested_roles, Mapping) and requested_roles.get("policy") == "preserve-existing-mode1"
    if unsupported_baseline_roles and not preserve_roles and not allow_recycle_normalisation:
        raise SeasonCompilerError(
            f"mode-1 player {player_id} has preserve-only legacy fine-role codes "
            f"{unsupported_baseline_roles}; allocate a compatible, parser-backed carrier "
            "instead of normalising an unproven record"
        )
    if not preserve_roles and (not isinstance(requested_roles, list) or not requested_roles or len(requested_roles) > 6 or any(not isinstance(value, int) or not 0 <= int(value) <= 17 for value in requested_roles)):
        raise SeasonCompilerError(
            f"mode-1 player {player_id} has invalid fine-role values"
        )
    preserve_position = isinstance(facts.get("primary_position"), Mapping) and facts["primary_position"].get("policy") == "preserve-existing-mode1"
    position = None if preserve_position else POSITION.get(facts.get("primary_position"))
    if position is None and not preserve_position:
        raise SeasonCompilerError(
            f"mode-1 player {player_id} has unsupported broad position {facts.get('primary_position')!r}"
        )
    shirt = facts.get("shirt_number")
    if not (isinstance(shirt, Mapping) and shirt.get("policy") == "preserve-existing-mode1") and int(shirt if shirt is not None else -1) != 0:
        raise SeasonCompilerError(
            f"mode-1 player {player_id} requests shirt number; foreign shirt-number storage is unproven"
        )
    return role_start, int(position) if position is not None else None, None if preserve_roles else [int(value) for value in requested_roles]


def _mode1_preserved_fields(facts: Mapping[str, Any], *, player_id: str, club_mode: int) -> set[str]:
    fields = {key for key, value in facts.items() if isinstance(value, Mapping) and value.get("policy") == "preserve-existing-mode1"}
    if fields and club_mode != 1:
        raise SeasonCompilerError(f"player {player_id} declares mode-1 preservation on a mode-{club_mode} carrier")
    for key, value in facts.items():
        if isinstance(value, Mapping) and key not in fields:
            raise SeasonCompilerError(f"player {player_id} has unsupported field policy {key}")
    return fields


def _player_replacements(
    *,
    package: Mapping[str, Any],
    jug_data: bytes,
    country_codes: Mapping[str, int],
    club_modes: Mapping[str, int],
) -> tuple[dict[int, bytes], list[dict[str, Any]], list[int], list[int], list[int], list[dict[str, Any]]]:
    """Build decoded JUG replacements and defer dd6361 handling to its tail pass."""

    indexed = IndexedFDIFile.from_bytes(jug_data)
    entries = {entry.record_id: entry for entry in indexed.entries}
    club_carriers = {club["id"]: int(club["carrier_id"]) for club in package["clubs"]}
    orders = _club_player_orders(package)
    replacements: dict[int, bytes] = {}
    handling_rows: list[dict[str, Any]] = []
    dd6360_handling_written: list[int] = []
    mode1_dd6360_core_written: list[int] = []
    mode1_dd6361_core_written: list[int] = []
    mode1_preserved_rows: list[dict[str, Any]] = []

    for player in package["players"]:
        carrier = int(player["carrier_id"])
        entry = entries.get(carrier)
        if entry is None:
            raise SeasonCompilerError(f"player carrier {carrier} is absent from JUG98030.FDI")
        decoded = entry.decode_payload(jug_data)
        family = str(player["carrier_family"])
        club_mode = club_modes.get(str(player["club_id"]))
        if club_mode not in {0, 1}:
            raise SeasonCompilerError(f"player {player['id']} belongs to an unresolved club layout")
        if player.get("policy") == "preserve-existing-mode1":
            if club_mode != 1:
                raise SeasonCompilerError(
                    f"player {player['id']} uses preserve-existing-mode1 outside mode 1"
                )
            mode1_preserved_rows.append(
                {
                    "carrier_id": carrier,
                    "fields": {"whole_record": {"before_sha256": hashlib.sha256(decoded).hexdigest(), "after_sha256": hashlib.sha256(decoded).hexdigest()}},
                    "result": "whole-record-byte-identical-no-write",
                }
            )
            continue
        expected_signature = b"\xdd\x63\x61" if family == "dd6361" else b"\xdd\x63\x60" if family == "dd6360" else None
        if expected_signature is None:
            raise SeasonCompilerError(f"player {player['id']} has unsupported carrier family {family!r}")
        if decoded[2:5] != expected_signature:
            raise SeasonCompilerError(
                f"player {player['id']} carrier {carrier} is not the declared {family} family"
            )
        facts = player["facts"]
        preserved_fields = _mode1_preserved_fields(facts, player_id=str(player["id"]), club_mode=club_mode)
        target_name = _pm99_text(player["name"], label=f"player {player['id']} name")
        mode1_role_start: int | None = None
        mode1_position: int | None = None
        mode1_fine_roles: list[int] | None = None
        if club_mode == 1:
            if family == "dd6360":
                mode1_role_start, mode1_position, mode1_fine_roles = _plan_mode1_dd6360_player_fields(
                    decoded=decoded, facts=facts, player_id=str(player["id"]),
                    allow_recycle_normalisation=player.get("recycle_from_mode1_carrier_id") is not None,
                )
            elif family == "dd6361":
                _guard_mode1_dd6361_preserve_only_player_fields(
                    decoded=decoded,
                    facts=facts,
                    player_id=str(player["id"]),
                    carrier=carrier,
                )
            else:
                raise SeasonCompilerError(
                    f"mode-1 player {player['id']} uses unsupported family {family}"
                )
        current_name = _player_name(decoded, record_id=carrier)
        try:
            if current_name == target_name:
                named = decoded
                name_proof = (
                    {"new_name_end": _find_dd6361_name_end(decoded)}
                    if family == "dd6361"
                    else {"new_role_start": int(_native_dd6360_role_start(decoded))}
                )
            else:
                named, name_proof = _patch_indexed_player_variable_name_payload(
                    decoded,
                    current_name,
                    target_name,
                )
        except Exception as exc:
            raise SeasonCompilerError(
                f"player {player['id']} carrier {carrier} cannot apply variable name {target_name!r}: {exc}"
            ) from exc
        ratings = player["ratings"]["values"]
        day, month, year = (None, None, None) if "birth_date" in preserved_fields else _iso_date(facts["birth_date"], label=f"player {player['id']} birth_date")
        position = None if "primary_position" in preserved_fields else POSITION.get(facts["primary_position"])
        if position is None and "primary_position" not in preserved_fields:
            raise SeasonCompilerError(f"player {player['id']} has unsupported broad position")
        nationality = None if "nationality" in preserved_fields else _country_code(str(facts["nationality"]), dict(country_codes))
        native_skills = {
            field: int(ratings[field])
            for field in (*SKILLS, "handling")
            if field in ratings
        }
        missing_core_skills = [field for field in SKILLS if field not in native_skills]
        if missing_core_skills:
            raise SeasonCompilerError(
                f"player {player['id']} is missing required core skills: {', '.join(missing_core_skills)}"
            )
        roles = None if "fine_roles" in preserved_fields else [int(value) for value in facts["fine_roles"]]
        if roles is not None and (not roles or len(roles) > 6 or any(not 0 <= role <= 17 for role in roles)):
            raise SeasonCompilerError(
                f"player {player['id']} fine_roles are outside the compiler's proven PM99 0..17 / six-slot contract"
            )
        height = None if "height_cm" in preserved_fields else int(facts["height_cm"])
        weight = None if "weight_kg" in preserved_fields else int(facts["weight_kg"])
        if family == "dd6361":
            record = PlayerRecord.from_bytes(named, entry.payload_offset)
            if club_mode == 1:
                replacement = _patch_dd6361_mode1_safe_fields(
                    named,
                    position=position,
                    nationality=nationality,
                    birth_day=day,
                    birth_month=month,
                    birth_year=year,
                    height=height,
                    weight=weight,
                    skills=native_skills,
                )
                mode1_dd6361_core_written.append(carrier)
            else:
                _apply_player_mutations(
                    record,
                    team_id=club_carriers[player["club_id"]],
                    position=position,
                    nationality=nationality,
                    birth_day=day,
                    birth_month=month,
                    birth_year=year,
                    height=height,
                    weight=weight,
                    attribute_updates={slot: native_skills[field] for slot, field in zip(range(3, 12), SKILLS, strict=True)},
                    offset=entry.payload_offset,
                )
                serialized = bytearray(record.to_bytes())
                # The legacy generic serializer only authors years through
                # 1999, silently retaining the carrier's year for newer DOBs.
                # The mode-1 lane already repairs this at the validated native
                # suffix; mode 0 requires exactly the same explicit u16 write.
                native_end = int(name_proof["new_name_end"])
                if year is not None:
                    serialized[native_end + 14:native_end + 16] = bytes(
                        value ^ 0x61 for value in int(year).to_bytes(2, 'little'))
                replacement = _set_dd6361_roles_and_startup(
                    bytes(serialized),
                    roles=roles,
                    shirt_number=int(facts["shirt_number"]),
                    initial_order=orders[player["id"]],
                    name_end=int(name_proof["new_name_end"]),
                )
            # Handling is the tenth visible dd6361 value and is written by a
            # separate tail-anchored, readback-verified pass.  That proven
            # contract applies to both club modes; limiting it to mode 0 left
            # otherwise writable mode-1 players with their carrier's old
            # Handling value.
            handling_rows.append(
                {
                    "record_id": carrier,
                    "family": family,
                    "visible_skills": {field: int(ratings[field]) for field in VISIBLE_SKILLS},
                    "name": target_name,
                    "club": player["club_id"],
                    "position": facts["primary_position"],
                    "handling_basis": "pm99-season-package-v2",
                }
            )
        else:
            role_start = name_proof.get("new_role_start")
            if not isinstance(role_start, int) or role_start < 0:
                raise SeasonCompilerError(f"player {player['id']} did not retain a safe dd6360 role cursor")
            if club_mode == 1:
                if mode1_role_start is None:
                    raise SeasonCompilerError(f"mode-1 player {player['id']} lost its safe write plan")
                replacement = _patch_dd6360_mode1_safe_fields(
                    named,
                    position=mode1_position,
                    nationality=nationality,
                    birth_day=day,
                    birth_month=month,
                    birth_year=year,
                    height=height,
                    weight=weight,
                    skills=native_skills,
                    native_role_start=role_start,
                    fine_roles=mode1_fine_roles,
                )
                mode1_dd6360_core_written.append(carrier)
            else:
                replacement = _set_dd6360_native_player_fields(
                    named,
                    role=roles[0],
                    position=position,
                    nationality=nationality,
                    birth_day=day,
                    birth_month=month,
                    birth_year=year,
                    height=int(facts["height_cm"]),
                    weight=int(facts["weight_kg"]),
                    skills=native_skills,
                    native_role_start=role_start,
                )
                # Mode-0 compact reserves participate in the same native
                # startup ordering as extended players. Mode 1 stays untouched.
                from app.player_initial_order import replace_initial_order
                replacement = replace_initial_order(replacement, orders[player['id']], allow_compact=True)
            if "handling" in native_skills:
                dd6360_handling_written.append(carrier)
        replacements[carrier] = replacement
        if preserved_fields and family == "dd6360":
            old_role_start = _native_dd6360_role_start(decoded)
            old_ranges = {"fine_roles": range(old_role_start + 2, old_role_start + 8), "nationality": range(old_role_start + 8, old_role_start + 9), "primary_position": range(old_role_start + 10, old_role_start + 12), "birth_date": range(old_role_start + 12, old_role_start + 16), "height_cm": range(old_role_start + 16, old_role_start + 17), "weight_kg": range(old_role_start + 17, old_role_start + 18)}
            new_role_start = int(_native_dd6360_role_start(replacement))
            new_ranges = {"fine_roles": range(new_role_start + 2, new_role_start + 8), "nationality": range(new_role_start + 8, new_role_start + 9), "primary_position": range(new_role_start + 10, new_role_start + 12), "birth_date": range(new_role_start + 12, new_role_start + 16), "height_cm": range(new_role_start + 16, new_role_start + 17), "weight_kg": range(new_role_start + 17, new_role_start + 18)}
            preserved_ranges = {field: {"before_offsets": list(old_ranges[field]), "after_offsets": list(new_ranges[field]), "before_hex": bytes(decoded[offset] for offset in old_ranges[field]).hex(), "after_hex": bytes(replacement[offset] for offset in new_ranges[field]).hex()} for field in sorted(preserved_fields) if field in old_ranges}
            if any(row["before_hex"] != row["after_hex"] for row in preserved_ranges.values()):
                raise SeasonCompilerError(f"mode-1 player {player['id']} changed a declared preserved field")
            mode1_preserved_rows.append({"carrier_id": carrier, "fields": preserved_ranges, "result": "field-ranges-byte-identical"})
        elif preserved_fields and family == "dd6361":
            before_name_end = _find_dd6361_name_end(decoded)
            after_name_end = _find_dd6361_name_end(replacement)
            before_ranges = {
                "fine_roles": range(before_name_end + 2, before_name_end + 8),
                "nationality": range(before_name_end + 8, before_name_end + 9),
                "primary_position": range(before_name_end + 10, before_name_end + 12),
                "birth_date": range(before_name_end + 12, before_name_end + 16),
                "height_cm": range(before_name_end + 16, before_name_end + 17),
                "weight_kg": range(before_name_end + 17, before_name_end + 18),
            }
            after_ranges = {
                field: range(
                    after_name_end + source.start - before_name_end,
                    after_name_end + source.stop - before_name_end,
                )
                for field, source in before_ranges.items()
            }
            preserved_ranges = {
                field: {
                    "before_offsets": list(before_ranges[field]),
                    "after_offsets": list(after_ranges[field]),
                    "before_hex": bytes(decoded[offset] for offset in before_ranges[field]).hex(),
                    "after_hex": bytes(replacement[offset] for offset in after_ranges[field]).hex(),
                }
                for field in sorted(preserved_fields)
                if field in before_ranges
            }
            if any(row["before_hex"] != row["after_hex"] for row in preserved_ranges.values()):
                raise SeasonCompilerError(f"mode-1 player {player['id']} changed a declared preserved field")
            mode1_preserved_rows.append(
                {
                    "carrier_id": carrier,
                    "fields": preserved_ranges,
                    "result": "field-ranges-byte-identical",
                }
            )
    return (
        replacements,
        handling_rows,
        dd6360_handling_written,
        mode1_dd6360_core_written,
        mode1_dd6361_core_written,
        mode1_preserved_rows,
    )


def _source_roster_owners(eq_data: bytes) -> tuple[dict[int, list[int]], dict[int, list[int]], dict[int, int]]:
    """Read parser-backed roster ownership and immutable EQ layout modes.

    Foreign mode-1 roster rows are a fixed topology contract.  A player may
    appear in more than one historical roster carrier, but the compiler must
    never "clean up" an unselected mode-1 owner while applying a selected
    team.  Returning the layout mode with the ownership map makes that rule
    explicit at the one place that might otherwise rewrite donor rows.
    """

    indexed = IndexedFDIFile.from_bytes(eq_data)
    owners: dict[int, list[int]] = defaultdict(list)
    rosters: dict[int, list[int]] = {}
    modes: dict[int, int] = {}
    for entry in indexed.entries:
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        try:
            metadata = extract_indexed_team_payload_metadata(raw)
            modes[int(entry.record_id)] = int(metadata["record_mode"])
        except Exception:
            # A roster parser result is still useful for legacy mode-0 donor
            # handling.  Unknown-layout records cannot qualify as a safe
            # mode-1 preservation exception below.
            pass
        parsed = parse_eq_external_team_roster_payload(raw, {})
        if parsed is None:
            continue
        ids = [row.player_record_id for row in parsed.rows]
        rosters[entry.record_id] = ids
        for player_id in ids:
            owners[player_id].append(entry.record_id)
    return owners, rosters, modes


def _append_indexed_fdi_records(
    *,
    original: bytes,
    records: Sequence[tuple[int, str, bytes]],
) -> bytes:
    """Append decoded records without changing any existing decoded payload.

    DMFI keeps its directory immediately before a contiguous payload area.  A
    new directory entry shifts that whole payload area by a known number of
    bytes, so every existing offset changes by the same amount while the
    payload bytes themselves remain exact.  This is deliberately *append*
    only: no existing JUG record is reused, replaced or removed.
    """

    if not records:
        return original
    indexed = IndexedFDIFile.from_bytes(original)
    known_ids = {int(entry.record_id) for entry in indexed.entries}
    requested_ids = [int(record_id) for record_id, _key, _payload in records]
    if len(requested_ids) != len(set(requested_ids)):
        raise SeasonCompilerError("indexed FDI append requests duplicate record IDs")
    duplicate = sorted(known_ids.intersection(requested_ids))
    if duplicate:
        raise SeasonCompilerError(f"indexed FDI append reuses existing record ID(s): {duplicate[:8]}")
    if any(record_id < 1 or record_id > 0xFFFFFFFF for record_id in requested_ids):
        raise SeasonCompilerError("indexed FDI append record ID is outside uint32 range")

    encoded_records: list[tuple[int, bytes, bytes]] = []
    for record_id, key, decoded_payload in records:
        try:
            key_bytes = str(key).encode("cp1252")
        except UnicodeEncodeError as exc:
            raise SeasonCompilerError(f"indexed FDI append key for {record_id} is not CP1252") from exc
        if len(key_bytes) > 255:
            raise SeasonCompilerError(f"indexed FDI append key for {record_id} exceeds 255 bytes")
        encoded_payload = xor_encode(bytes(decoded_payload))
        if len(encoded_payload) > 0xFFFFFFFF:
            raise SeasonCompilerError(f"indexed FDI append payload for {record_id} exceeds uint32 length")
        encoded_records.append((int(record_id), key_bytes, encoded_payload))

    directory_growth = sum(4 + 1 + len(key) + 8 for _record_id, key, _payload in encoded_records)
    new_payload_base = len(original) + directory_growth
    if new_payload_base > 0xFFFFFFFF:
        raise SeasonCompilerError("indexed FDI append would overflow uint32 offsets")

    result = bytearray(original[: indexed.index_end_offset])
    struct.pack_into("<I", result, 0x10, indexed.record_count + len(encoded_records))
    # All old payloads are shifted by the appended directory entries.  Their
    # original encoded bytes and any bytes beyond the directory are copied as
    # one opaque suffix below.
    for entry in indexed.entries:
        key_length = result[entry.index_offset + 4]
        offset_at = entry.index_offset + 5 + key_length
        struct.pack_into("<I", result, offset_at, entry.payload_offset + directory_growth)

    payload_offset = new_payload_base
    for record_id, key_bytes, encoded_payload in encoded_records:
        result.extend(struct.pack("<I", record_id))
        result.append(len(key_bytes))
        result.extend(key_bytes)
        result.extend(struct.pack("<I", payload_offset))
        result.extend(struct.pack("<I", len(encoded_payload)))
        payload_offset += len(encoded_payload)
    result.extend(original[indexed.index_end_offset :])
    for _record_id, _key_bytes, encoded_payload in encoded_records:
        result.extend(encoded_payload)

    rebuilt = bytes(result)
    checked = IndexedFDIFile.from_bytes(rebuilt)
    if checked.record_count != indexed.record_count + len(encoded_records):
        raise SeasonCompilerError("indexed FDI append did not retain the expected record count")
    checked_by_id = {int(entry.record_id): entry for entry in checked.entries}
    for entry in indexed.entries:
        if checked_by_id[entry.record_id].decode_payload(rebuilt) != entry.decode_payload(original):
            raise SeasonCompilerError(f"indexed FDI append changed existing record {entry.record_id}")
    for record_id, _key_bytes, decoded_payload in encoded_records:
        if checked_by_id[record_id].decode_payload(rebuilt) != xor_decode(decoded_payload):
            # ``encoded_records`` intentionally carries the XORed payload;
            # decode it here to compare against the requested decoded bytes.
            raise SeasonCompilerError(f"indexed FDI append read-back failed for new record {record_id}")
    return rebuilt


def _append_package_player_carriers(
    *,
    package: Mapping[str, Any],
    jug_data: bytes,
    eq_data: bytes,
) -> tuple[bytes, list[int], list[int]]:
    """Materialise explicit cloned JUG allocations in two bounded lanes.

    Mode 0 may append a ``dd6361`` clone from a mode-0-only source, which is
    the existing English 25-player route.  Mode 1 compact append is rejected:
    a live-game control proved that a high fresh ID reaches Search but fails
    opening its profile, while ID 1 is not discoverable.  The full roster
    transaction guard therefore operates only on already-addressable JUG
    records until the foreign player-ID namespace is reverse engineered.
    """

    indexed = IndexedFDIFile.from_bytes(jug_data)
    entries = {int(entry.record_id): entry for entry in indexed.entries}
    owners, _rosters, modes = _source_roster_owners(eq_data)
    requested: list[tuple[int, str, bytes]] = []
    appended_mode0_dd6361_ids: list[int] = []
    appended_mode1_dd6360_ids: list[int] = []
    for player in package["players"]:
        carrier = int(player["carrier_id"])
        if carrier in entries:
            if player.get("append_from_carrier_id") is not None:
                raise SeasonCompilerError(
                    f"player {player['id']} declares append_from_carrier_id but carrier {carrier} already exists"
                )
            continue
        if carrier in owners:
            raise SeasonCompilerError(
                f"player {player['id']} appended carrier {carrier} is already referenced by an EQ roster"
            )
        source_id = player.get("append_from_carrier_id")
        if not isinstance(source_id, int) or source_id < 1:
            raise SeasonCompilerError(
                f"player {player['id']} carrier {carrier} is absent from the clean JUG file; "
                "declare an append_from_carrier_id"
            )
        source = entries.get(source_id)
        if source is None:
            raise SeasonCompilerError(
                f"player {player['id']} append source carrier {source_id} is absent from the clean JUG file"
            )
        source_owners = owners.get(source_id, [])
        decoded = source.decode_payload(jug_data)
        family = decoded[2:5]
        declared_family = str(player["carrier_family"])
        if family == b"\xdd\x63\x61" and declared_family == "dd6361":
            if not source_owners or any(modes.get(owner) != 0 for owner in source_owners):
                raise SeasonCompilerError(
                    f"player {player['id']} append source carrier {source_id} is not mode-0-only"
                )
            appended_mode0_dd6361_ids.append(carrier)
        elif family == b"\xdd\x63\x60" and declared_family == "dd6360":
            raise SeasonCompilerError(
                f"player {player['id']} requests a mode-1 compact append; this is runtime-blocked "
                "because PM99 cannot safely open a profile for a fresh compact JUG ID"
            )
        else:
            raise SeasonCompilerError(
                f"player {player['id']} append allocation family does not match its declared carrier family"
            )
        decoded = rebind_indexed_player_id(decoded, carrier, expected_id=source_id)
        requested.append((carrier, source.key, decoded))
    return (
        _append_indexed_fdi_records(original=jug_data, records=requested),
        sorted(appended_mode0_dd6361_ids),
        sorted(appended_mode1_dd6360_ids),
    )


def _dd6361_fine_roles(payload: bytes, *, carrier: int) -> set[int]:
    """Read the established six-slot role vector from one mode-0 JUG row."""

    if payload[2:5] != b"\xdd\x63\x61":
        raise SeasonCompilerError(f"mode-0 recycle source {carrier} is not a dd6361 player")
    try:
        name_end = _find_dd6361_name_end(payload)
    except Exception as exc:
        raise SeasonCompilerError(f"mode-0 recycle source {carrier} has no role-vector anchor") from exc
    if name_end + 8 > len(payload):
        raise SeasonCompilerError(f"mode-0 recycle source {carrier} role vector overruns payload")
    result = {
        int(payload[name_end + 2 + slot] ^ 0x61) - 1
        for slot in range(6)
        if int(payload[name_end + 2 + slot] ^ 0x61) != 0
    }
    if not result or any(role < 0 or role > 17 for role in result):
        raise SeasonCompilerError(f"mode-0 recycle source {carrier} has an unsupported role vector")
    return result


def _materialise_mode1_carrier_recycles(
    *,
    package: Mapping[str, Any],
    jug_data: bytes,
    eq_data: bytes,
    club_modes: Mapping[str, int],
) -> tuple[bytes, list[dict[str, int]], list[dict[str, int]]]:
    """Turn explicitly declared mode-0 carriers into bounded compact carriers.

    A fresh compact directory entry can appear in player search but cannot
    open a native PM99 profile.  This narrow transaction instead pairs an
    existing, exclusive mode-0 ``dd6361`` row with its separately appended
    clone and reuses the old ID for a mode-1 ``dd6360`` source shape.  Every
    check is intentionally structural: a package cannot use this to borrow an
    arbitrary English player, skip the clone, or pick a broad-position match.

    The function only changes JUG bytes.  The corresponding mode-0 and mode-1
    EQ roster rows are still reconstructed from the package and subsequently
    checked by their normal exact-tail contracts.
    """

    recycle_players = [
        player for player in package["players"]
        if player.get("recycle_from_mode1_carrier_id") is not None
    ]
    if not recycle_players:
        return jug_data, [], []

    indexed = IndexedFDIFile.from_bytes(jug_data)
    entries = {int(entry.record_id): entry for entry in indexed.entries}
    owners, _rosters, modes = _source_roster_owners(eq_data)
    club_carriers = {str(club["id"]): int(club["carrier_id"]) for club in package["clubs"]}
    appended_by_source: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for player in package["players"]:
        source = player.get("append_from_carrier_id")
        if isinstance(source, int):
            appended_by_source[source].append(player)

    replacements: dict[int, bytes] = {}
    receipts: list[dict[str, int]] = []
    implicit_clone_records: list[tuple[int, str, bytes]] = []
    implicit_clone_roster_rows: list[dict[str, int]] = []
    target_ids = {int(player["carrier_id"]) for player in recycle_players}
    if len(target_ids) != len(recycle_players):
        raise SeasonCompilerError("mode-1 recycle targets must be distinct player carriers")

    for player in recycle_players:
        target = int(player["carrier_id"])
        donor = int(player["recycle_from_mode1_carrier_id"])
        if str(player.get("carrier_family")) != "dd6360":
            raise SeasonCompilerError(
                f"mode-1 recycle player {player['id']} must declare the dd6360 carrier family"
            )
        if club_modes.get(str(player["club_id"])) != 1:
            raise SeasonCompilerError(
                f"mode-1 recycle player {player['id']} must belong to a mode-1 club"
            )
        if donor in target_ids:
            raise SeasonCompilerError("mode-1 recycle donor cannot also be a recycle target")
        source_entry = entries.get(target)
        donor_entry = entries.get(donor)
        if source_entry is None or donor_entry is None:
            raise SeasonCompilerError(f"mode-1 recycle player {player['id']} names an absent JUG carrier")
        source_payload = source_entry.decode_payload(jug_data)
        donor_payload = donor_entry.decode_payload(jug_data)
        if donor_payload[2:5] != b"\xdd\x63\x60":
            raise SeasonCompilerError(
                f"mode-1 recycle player {player['id']} donor {donor} is not a compact dd6360 payload"
            )
        donor_owners = owners.get(donor, [])
        if not donor_owners or any(modes.get(owner) != 1 for owner in donor_owners):
            raise SeasonCompilerError(
                f"mode-1 recycle player {player['id']} donor {donor} is not mode-1-only"
            )
        source_owners = owners.get(target, [])
        if len(source_owners) != 1 or modes.get(source_owners[0]) != 0:
            raise SeasonCompilerError(
                f"mode-1 recycle target {target} must be owned by exactly one mode-0 roster"
            )
        clone_players = appended_by_source.get(target, [])
        implicit_clone_carrier = player.get("mode0_clone_carrier_id")
        if clone_players and implicit_clone_carrier is not None:
            raise SeasonCompilerError(
                f"mode-1 recycle target {target} cannot declare both a clone player and mode0_clone_carrier_id"
            )
        if len(clone_players) > 1:
            raise SeasonCompilerError(f"mode-1 recycle target {target} has multiple clone players")
        if clone_players:
            clone = clone_players[0]
            clone_carrier = int(clone["carrier_id"])
            if str(clone.get("carrier_family")) != "dd6361" or club_modes.get(str(clone["club_id"])) != 0:
                raise SeasonCompilerError(
                    f"mode-1 recycle target {target} clone must be a dd6361 player in a mode-0 club"
                )
            if club_carriers[str(clone["club_id"])] != source_owners[0]:
                raise SeasonCompilerError(
                    f"mode-1 recycle target {target} clone must remain in its original mode-0 roster carrier"
                )
            if clone_carrier not in entries or clone_carrier in owners:
                raise SeasonCompilerError(
                    f"mode-1 recycle target {target} clone {clone_carrier} was not safely appended"
                )
        elif isinstance(implicit_clone_carrier, int) and implicit_clone_carrier > 0:
            clone_carrier = int(implicit_clone_carrier)
            if clone_carrier >= 0x8000:
                raise SeasonCompilerError(
                    f"mode-1 recycle target {target} implicit clone {clone_carrier} is outside the gameplay-safe positive 15-bit carrier range"
                )
            if clone_carrier in entries or clone_carrier in owners:
                raise SeasonCompilerError(
                    f"mode-1 recycle target {target} implicit clone {clone_carrier} is not a fresh JUG carrier"
                )
            clone_payload = rebind_indexed_player_id(source_payload, clone_carrier, expected_id=target)
            implicit_clone_records.append((clone_carrier, source_entry.key, clone_payload))
            implicit_clone_roster_rows.append(
                {
                    "mode0_team_carrier_id": int(source_owners[0]),
                    "old_player_carrier_id": target,
                    "new_player_carrier_id": clone_carrier,
                }
            )
            clone = None
        else:
            raise SeasonCompilerError(
                f"mode-1 recycle target {target} requires exactly one explicit clone player or mode0_clone_carrier_id"
            )

        requested_roles = player.get("facts", {}).get("fine_roles")
        if (
            not isinstance(requested_roles, list)
            or not 1 <= len(requested_roles) <= 6
            or any(not isinstance(value, int) or not 0 <= int(value) <= 17 for value in requested_roles)
        ):
            raise SeasonCompilerError(
                f"mode-1 recycle player {player['id']} requires one to six proven 0..17 fine-role candidates"
            )
        # The executable does not merely accept any existing English carrier
        # as a compact foreign player.  The role vector which matters at
        # runtime is the paired, appended mode-0 clone: it is the surviving
        # dd6361 representation after the target ID has been replaced by the
        # compact foreign donor.  A role-3 runner control deliberately
        # changed that clone from an original [4, 5] vector to [3] and opened
        # the foreign profile cleanly.  Therefore retain the original vector
        # only as a receipt/audit fact; require the *declared clone output*
        # to contain the requested compact role.  Broad position remains no
        # substitute: a different fine-role control raised the native error.
        # Fail before changing either JUG or EQ graph so a package cannot turn
        # an unqualified experimental allocation into a release by accident.
        baseline_source_roles = _dd6361_fine_roles(source_payload, carrier=target)
        clone_roles = clone.get("facts", {}).get("fine_roles") if clone is not None else sorted(baseline_source_roles)
        if not isinstance(clone_roles, list) or not 1 <= len(clone_roles) <= 6 or any(not isinstance(value, int) or not 0 <= int(value) <= 17 for value in clone_roles):
            raise SeasonCompilerError(f"mode-1 recycle target {target} clone {clone_carrier} requires one to six proven 0..17 fine-role candidates")
        primary_role = int(requested_roles[0])
        if primary_role not in clone_roles:
            raise SeasonCompilerError(
                f"mode-1 recycle player {player['id']} primary fine role {primary_role} "
                f"is incompatible with mode-0 recycle clone {clone_carrier} roles {sorted(clone_roles)}"
            )
        replacements[target] = rebind_indexed_player_id(donor_payload, target, expected_id=donor)
        receipts.append({
            "recycled_carrier_id": target,
            "mode1_donor_carrier_id": donor,
            "mode0_clone_carrier_id": clone_carrier,
            "mode0_target_baseline_role_candidates": sorted(baseline_source_roles),
            "mode0_clone_requested_role_candidates": [int(value) for value in clone_roles],
            "requested_fine_roles": [int(value) for value in requested_roles],
        })

    rebuilt = _rebuild_indexed(jug_data, indexed, replacements)
    if implicit_clone_records:
        rebuilt = _append_indexed_fdi_records(original=rebuilt, records=implicit_clone_records)
    rebuilt_entries = {int(entry.record_id): entry for entry in IndexedFDIFile.from_bytes(rebuilt).entries}
    for receipt in receipts:
        payload = rebuilt_entries[receipt["recycled_carrier_id"]].decode_payload(rebuilt)
        if payload[2:5] != b"\xdd\x63\x60":
            raise SeasonCompilerError("mode-1 recycle read-back did not retain a compact player payload")
    return (
        rebuilt,
        sorted(receipts, key=lambda row: row["recycled_carrier_id"]),
        sorted(implicit_clone_roster_rows, key=lambda row: row["new_player_carrier_id"]),
    )


def _mode1_roster_tails(eq_data: bytes) -> dict[int, bytes]:
    """Return exact count-and-row bytes for every parser-backed mode-1 roster.

    The tail is a live cross-family link table, including its count and flag
    bytes.  Keeping a decoded player-id list is not sufficient evidence that
    a compiler has left every foreign roster untouched.
    """

    result: dict[int, bytes] = {}
    indexed = IndexedFDIFile.from_bytes(eq_data)
    for entry in indexed.entries:
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        try:
            mode = int(extract_indexed_team_payload_metadata(raw)["record_mode"])
        except Exception as exc:
            raise SeasonCompilerError(
                f"EQ carrier {entry.record_id} has no parser-backed modern mode for roster preservation"
            ) from exc
        if mode != 1:
            continue
        parsed = parse_eq_external_team_roster_payload(raw, {})
        if parsed is None or not parsed.rows:
            raise SeasonCompilerError(
                f"mode-1 EQ carrier {entry.record_id} has no parser-backed terminal roster tail"
            )
        tail_start = parsed.rows[0].raw_row_offset - 1
        if tail_start < 0 or parsed.rows[-1].raw_row_offset + 5 != len(raw):
            raise SeasonCompilerError(
                f"mode-1 EQ carrier {entry.record_id} roster is not a bounded terminal tail"
            )
        result[int(entry.record_id)] = raw[tail_start:]
    return result


def _implicit_mode0_clone_roster_replacements(
    *,
    eq_data: bytes,
    clone_rows: Sequence[Mapping[str, int]],
) -> tuple[dict[int, bytes], list[dict[str, Any]]]:
    """Retain an allocation's mode-0 source player as an exact appended clone.

    An allocation can declare the clone directly on its selected mode-1 player
    instead of inventing an unsourced mode-0 club/player package row.  This
    narrow helper changes only the identified terminal roster ID, preserving
    the existing mode-0 row count and flags through the proven roster writer.
    """

    if not clone_rows:
        return {}, []
    indexed = IndexedFDIFile.from_bytes(eq_data)
    entries = {int(entry.record_id): entry for entry in indexed.entries}
    by_team: dict[int, list[Mapping[str, int]]] = defaultdict(list)
    for row in clone_rows:
        team = int(row["mode0_team_carrier_id"])
        by_team[team].append(row)
    replacements: dict[int, bytes] = {}
    statuses: list[dict[str, Any]] = []
    for team, rows in sorted(by_team.items()):
        entry = entries.get(team)
        if entry is None:
            raise SeasonCompilerError(f"implicit recycle clone source team {team} is absent from EQ98030.FDI")
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        try:
            metadata = extract_indexed_team_payload_metadata(raw)
        except Exception as exc:
            raise SeasonCompilerError(f"implicit recycle clone source team {team} has no parser-backed mode") from exc
        if int(metadata["record_mode"]) != 0:
            raise SeasonCompilerError(f"implicit recycle clone source team {team} is not mode-0")
        parsed = parse_eq_external_team_roster_payload(raw, {})
        if parsed is None or not parsed.rows:
            raise SeasonCompilerError(f"implicit recycle clone source team {team} has no parser-backed roster")
        old_to_new = {int(row["old_player_carrier_id"]): int(row["new_player_carrier_id"]) for row in rows}
        if len(old_to_new) != len(rows) or len(set(old_to_new.values())) != len(rows):
            raise SeasonCompilerError(f"implicit recycle clone source team {team} has duplicate allocation rows")
        roster = [int(row.player_record_id) for row in parsed.rows]
        for old_id in old_to_new:
            if roster.count(old_id) != 1:
                raise SeasonCompilerError(
                    f"implicit recycle clone source team {team} does not own exactly one source player {old_id}"
                )
        rewritten = [old_to_new.get(player_id, player_id) for player_id in roster]
        replacements[team] = xor_decode(_rewrite_roster_tail(raw, rewritten))
        statuses.append(
            {
                "club_id": None,
                "carrier_id": team,
                "record_mode": 0,
                "roster_contract": "written-qualified-recycle-clone-id-substitution",
                "roster_count": len(rewritten),
            }
        )
    return replacements, statuses


def _decode_mode1_roster_tail(tail: bytes, *, carrier: int) -> list[tuple[int, int]]:
    """Decode the fixed terminal ``count, flag, JUG-id`` representation.

    ``parse_eq_external_team_roster_payload`` intentionally accepts a full EQ
    record, not a sliced tail.  The compiler stores tails for exact
    preservation checks, so decode this tiny bounded representation directly
    instead of pretending a tail is a standalone EQ payload.
    """

    if not tail:
        raise SeasonCompilerError(f"mode-1 roster tail {carrier} is empty")
    count = tail[0]
    expected_length = 1 + count * 5
    if len(tail) != expected_length:
        raise SeasonCompilerError(
            f"mode-1 roster tail {carrier} has {len(tail)} bytes; expected {expected_length}"
        )
    return [
        (tail[offset], int.from_bytes(tail[offset + 1 : offset + 5], "little"))
        for offset in range(1, len(tail), 5)
    ]


def _assert_mode1_roster_tails_match_plan(
    *,
    before: Mapping[int, bytes],
    after_eq_data: bytes,
    planned_player_ids: Mapping[int, list[int]],
) -> None:
    """Verify every foreign roster transaction against its exact plan.

    Foreign row replacements are runtime-proven only as a coherent graph
    transaction.  Existing row counts and flag bytes stay immutable; an
    unplanned foreign tail must remain byte-for-byte unchanged.
    """

    after = _mode1_roster_tails(after_eq_data)
    if set(before) != set(after):
        raise SeasonCompilerError("mode-1 roster carrier set changed during compilation")
    for carrier in sorted(before):
        expected_ids = planned_player_ids.get(carrier)
        if expected_ids is None:
            if before[carrier] != after[carrier]:
                raise SeasonCompilerError(f"unplanned mode-1 roster tail {carrier} changed during compilation")
            continue
        before_rows = _decode_mode1_roster_tail(before[carrier], carrier=carrier)
        after_rows = _decode_mode1_roster_tail(after[carrier], carrier=carrier)
        if len(before_rows) != len(expected_ids) or len(after_rows) != len(expected_ids):
            raise SeasonCompilerError(f"mode-1 roster transaction {carrier} changed the fixed row count")
        if [flag for flag, _player_id in before_rows] != [flag for flag, _player_id in after_rows]:
            raise SeasonCompilerError(f"mode-1 roster transaction {carrier} changed an immutable row flag")
        if [player_id for _flag, player_id in after_rows] != list(expected_ids):
            raise SeasonCompilerError(f"mode-1 roster transaction {carrier} failed its player-id read-back")


def _team_replacements(
    *,
    package: Mapping[str, Any],
    eq_data: bytes,
    ent_carriers: set[int],
    implicit_mode0_clone_rows: Sequence[Mapping[str, Any]] = (),
) -> tuple[dict[int, bytes], list[dict[str, Any]], dict[int, list[int]]]:
    """Write only proven EQ team metadata, links, roster and mode-0 tactics.

    Mode 1 is deliberately an in-place carrier transaction: strings, seated
    capacity and an existing final manager link may change, while roster rows
    must remain byte-for-byte in the same slot order.  Finance and opening
    tactics are not attempted.  This is the largest safe world surface we can
    currently compile without pretending to know foreign competition state.
    """

    indexed = IndexedFDIFile.from_bytes(eq_data)
    entries = {entry.record_id: entry for entry in indexed.entries}
    selected = {int(club["carrier_id"]) for club in package["clubs"]}
    owners, source_rosters, source_modes = _source_roster_owners(eq_data)
    mode1_tails = _mode1_roster_tails(eq_data)
    player_carriers = {str(player["id"]): int(player["carrier_id"]) for player in package["players"]}
    requested_rosters: dict[int, list[int]] = {}
    for club in package["clubs"]:
        carrier = int(club["carrier_id"])
        try:
            requested_rosters[carrier] = [player_carriers[str(player_id)] for player_id in club["roster_player_ids"]]
        except KeyError as exc:
            raise SeasonCompilerError(
                f"club {club['id']} names an unresolved roster player {exc.args[0]!r}"
            ) from exc
    player_rows_by_carrier = {int(player["carrier_id"]): player for player in package["players"]}
    requested_mode1_owners: dict[int, set[int]] = defaultdict(set)
    for team_carrier, roster in requested_rosters.items():
        if source_modes.get(team_carrier) == 1:
            for player_carrier in roster:
                requested_mode1_owners[player_carrier].add(team_carrier)
    shared_declarations = {
        int(club["carrier_id"]): {
            player_carriers[str(player_id)] for player_id in club.get("shared_preserve_player_ids") or []
        }
        for club in package["clubs"]
    }
    for player_carrier, requested_owner_set in requested_mode1_owners.items():
        if len(requested_owner_set) < 2:
            continue
        baseline_owner_set = {
            owner for owner in owners.get(player_carrier, []) if source_modes.get(owner) == 1
        }
        player_row = player_rows_by_carrier.get(player_carrier)
        declared_owners = {
            owner for owner in requested_owner_set
            if player_carrier in shared_declarations.get(owner, set())
        }
        if (
            requested_owner_set != baseline_owner_set
            or player_row is None
            or player_row.get("policy") != "preserve-existing-mode1"
            or not declared_owners
        ):
            raise SeasonCompilerError(
                f"mode-1 shared carrier {player_carrier} is not an exact baseline whole-record preserve graph"
            )
    mode1_roster_plans = {
        carrier: roster
        for carrier, roster in requested_rosters.items()
        if source_modes.get(carrier) == 1 and roster != source_rosters.get(carrier)
    }
    if mode1_roster_plans:
        selected_mode1 = {carrier for carrier in selected if source_modes.get(carrier) == 1}
        missing = sorted(set(mode1_tails) - selected_mode1)
        if missing:
            raise SeasonCompilerError(
                "mode-1 roster changes require one complete foreign graph transaction; "
                "unselected carrier(s): " + ", ".join(str(carrier) for carrier in missing[:12])
            )
        for carrier, roster in mode1_roster_plans.items():
            baseline = source_rosters.get(carrier)
            if baseline is None or len(roster) != len(baseline):
                raise SeasonCompilerError(
                    f"mode-1 club carrier {carrier} changes its fixed roster row count"
                )
    package_player_ids = {int(player["carrier_id"]) for player in package["players"]}
    clone_substitutions = {
        (int(row["mode0_team_carrier_id"]), int(row["old_player_carrier_id"]))
        for row in implicit_mode0_clone_rows
    }
    donor_removals: dict[int, set[int]] = defaultdict(set)
    for player_id in package_player_ids:
        for owner in owners.get(player_id, []):
            if owner not in selected:
                if (owner, player_id) in clone_substitutions:
                    continue
                if source_modes.get(owner) == 1:
                    raise SeasonCompilerError(
                        "selected player carrier "
                        f"{player_id} has unselected mode-1 roster owner {owner}; "
                        "foreign fixed-carrier rows must remain byte-for-byte preserved"
                    )
                donor_removals[owner].add(player_id)

    replacements: dict[int, bytes] = {}
    statuses: list[dict[str, Any]] = []
    for club in package["clubs"]:
        carrier = int(club["carrier_id"])
        entry = entries.get(carrier)
        if entry is None:
            raise SeasonCompilerError(f"club carrier {carrier} is absent from EQ98030.FDI")
        manager = next(manager for manager in package["managers"] if manager["id"] == club["manager_id"])
        preserve_manager = manager.get("policy") == "preserve-existing-mode1"
        manager_id = int(manager["carrier_id"])
        if not preserve_manager and manager_id not in ent_carriers:
            raise SeasonCompilerError(f"club {club['id']} manager carrier {manager_id} is absent from ENT98030.FDI")
        decoded = entry.decode_payload(eq_data)
        try:
            rewrite_kwargs: dict[str, str] = {
                "short_name": _pm99_text(club["name"], label=f"club {club['id']} name"),
                "full_name": _pm99_text(club.get("full_name") or club["name"], label=f"club {club['id']} full_name"),
            }
            if club.get("ground_policy") != "preserve-existing-mode1":
                rewrite_kwargs["stadium_name"] = _pm99_text(club.get("ground_name"), label=f"club {club['id']} ground_name")
            else:
                # The indexed string rewriter always touches its supplied
                # stadium lane, so omit it entirely for a declared preserve.
                rewrite_kwargs["stadium_name"] = _preserved_eq_stadium_name(decoded)
            decoded = _rewrite_eq_strings(decoded, **rewrite_kwargs)
            raw = xor_encode(decoded)
            if club.get("capacity_policy") != "preserve-existing-mode1":
                raw = patch_indexed_team_seated_capacity(raw, int(club.get("seated_capacity", 0)))
            metadata = extract_indexed_team_payload_metadata(raw)
            mode = int(metadata["record_mode"])
            if mode not in {0, 1}:
                raise SeasonCompilerError(
                    f"club {club['id']} uses unsupported EQ mode {mode}; preserve its carrier"
                )
            roster = requested_rosters[carrier]
            minimum_roster_rows = 1 if mode == 1 else 16
            if not minimum_roster_rows <= len(roster) <= 255:
                raise SeasonCompilerError(
                    f"club {club['id']} roster has {len(roster)} players; "
                    f"PM99's proven mode-{mode} linked-roster writer requires "
                    f"{minimum_roster_rows}..255"
                )
            if mode == 0:
                raw = patch_indexed_team_mode0_starting_finance(raw, int(club.get("starting_finance", 0)))
                context = club["opening"].get("tactics_context")
                if context is not None:
                    raw = patch_initial_tactics(raw, [slot['states'] for slot in context['slots']])
                else:
                    positions = club["opening"]["tactics_positions"]
                    raw = _write_initial_tactics(raw, [list(row) for row in positions])
                if not preserve_manager: raw = patch_indexed_eq_active_manager_id(raw, manager_id)
                raw = _rewrite_roster_tail(raw, roster)
                opening_tactics = "written-contextual-mode0-grid" if context is not None else "written-legacy-static-mode0-grid"
                starting_finance = "written-proven-mode0"
                roster_contract = "written-proven-mode0-linked-roster"
            else:
                baseline_roster = source_rosters.get(carrier)
                if baseline_roster is None:
                    raise SeasonCompilerError(f"mode-1 club {club['id']} has no parser-backed baseline roster")
                if "starting_finance" in club:
                    raise SeasonCompilerError(
                        f"mode-1 club {club['id']} supplies starting_finance; foreign finance is preserve-only"
                    )
                if not preserve_manager: raw = patch_indexed_eq_active_manager_id(raw, manager_id)
                opening_tactics = "preserved-mode1-unproven"
                starting_finance = "preserved-mode1-unproven"
                if carrier in mode1_roster_plans:
                    raw = _rewrite_roster_tail(raw, roster)
                    roster_contract = "written-proven-mode1-complete-graph-fixed-row-count-and-flags"
                else:
                    roster_contract = "verified-fixed-existing-slot-order"
        except SeasonCompilerError:
            raise
        except Exception as exc:
            raise SeasonCompilerError(f"club {club['id']} cannot be written through the proven EQ lanes: {exc}") from exc
        replacements[carrier] = xor_decode(raw)
        statuses.append({
            "club_id": club["id"],
            "carrier_id": carrier,
            "record_mode": mode,
            "opening_tactics": opening_tactics,
            "starting_finance": starting_finance,
            "manager_link": "preserved-existing-mode1" if preserve_manager else "written-proven-link",
            "ground": "preserved-existing-mode1" if club.get("ground_policy") == "preserve-existing-mode1" else "written",
            "capacity": "preserved-existing-mode1" if club.get("capacity_policy") == "preserve-existing-mode1" else "written",
            "roster_contract": roster_contract,
            "roster_count": len(roster),
        })

    # Some valid native carrier allocations draw reserve rows from another
    # existing team.  Retain the historical safety rule: remove the moved row
    # from that source team only when it has a parser-backed terminal roster
    # tail and remains at least twenty players deep.  Do not guess ownership.
    for donor, removed in sorted(donor_removals.items()):
        if source_modes.get(donor) == 1 or donor in mode1_tails:
            raise SeasonCompilerError(f"refusing to rewrite mode-1 donor EQ carrier {donor}")
        if donor in replacements:
            raise SeasonCompilerError(f"donor EQ carrier {donor} overlaps a selected club")
        entry = entries.get(donor)
        current = source_rosters.get(donor)
        if entry is None or current is None:
            raise SeasonCompilerError(f"player donor EQ carrier {donor} has no parser-backed roster")
        retained = [player_id for player_id in current if player_id not in removed]
        if len(retained) < 20:
            raise SeasonCompilerError(
                f"removing selected players from donor carrier {donor} would leave fewer than 20 players"
            )
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        try:
            replacements[donor] = xor_decode(_rewrite_roster_tail(raw, retained))
        except Exception as exc:
            raise SeasonCompilerError(f"cannot safely remove moved players from donor {donor}: {exc}") from exc
        statuses.append({
            "club_id": None,
            "carrier_id": donor,
            "record_mode": None,
            "opening_tactics": "preserved-donor",
            "starting_finance": "preserved-donor",
            "roster_count": len(retained),
        })
    return replacements, statuses, mode1_roster_plans


def _manager_replacements(package: Mapping[str, Any], ent_data: bytes) -> dict[int, bytes]:
    indexed = IndexedFDIFile.from_bytes(ent_data)
    entries = {entry.record_id: entry for entry in indexed.entries}
    replacements: dict[int, bytes] = {}
    for manager in package["managers"]:
        if manager.get("policy") == "preserve-existing-mode1":
            continue
        carrier = int(manager["carrier_id"])
        entry = entries.get(carrier)
        if entry is None:
            raise SeasonCompilerError(f"manager carrier {carrier} is absent from ENT98030.FDI")
        try:
            replacements[carrier] = _patch_ent_name(
                entry.decode_payload(ent_data), carrier,
                _pm99_text(manager["name"], label=f"manager {manager['id']} name"),
                native_names=manager.get("native_names"),
            )
        except Exception as exc:
            raise SeasonCompilerError(f"manager {manager['id']} cannot be renamed safely: {exc}") from exc
    return replacements


def _verify_output(
    *,
    package: Mapping[str, Any],
    jug_path: Path,
    eq_path: Path,
) -> None:
    jug_data = jug_path.read_bytes()
    jug_index = IndexedFDIFile.from_bytes(jug_data)
    jug_entries = {entry.record_id: entry for entry in jug_index.entries}
    for carrier, entry in jug_entries.items():
        payload = entry.decode_payload(jug_data)
        if payload[2:5] in (b"\xdd\x63\x60", b"\xdd\x63\x61"):
            actual = read_indexed_player_id(payload)
            if actual != carrier:
                raise SeasonCompilerError(
                    f"post-build native player identity mismatch: directory {carrier}, native {actual}"
                )
    for player in package["players"]:
        carrier = int(player["carrier_id"])
        entry = jug_entries.get(carrier)
        if entry is None:
            raise SeasonCompilerError(f"post-build player carrier missing: {carrier}")
        payload = entry.decode_payload(jug_data)
        if payload[2:5] != (b"\xdd\x63\x61" if player["carrier_family"] == "dd6361" else b"\xdd\x63\x60"):
            raise SeasonCompilerError(f"post-build player family changed for {player['id']}")
        observed = _player_name(payload, record_id=carrier)
        if observed.casefold() != _pm99_text(player["name"], label=f"player {player['id']} name").casefold():
            raise SeasonCompilerError(f"post-build player name read-back failed for {player['id']}: {observed!r}")

    eq_data = eq_path.read_bytes()
    eq_index = IndexedFDIFile.from_bytes(eq_data)
    entries = {entry.record_id: entry for entry in eq_index.entries}
    player_carriers = {row["id"]: int(row["carrier_id"]) for row in package["players"]}
    for club in package["clubs"]:
        carrier = int(club["carrier_id"])
        entry = entries.get(carrier)
        if entry is None:
            raise SeasonCompilerError(f"post-build club carrier missing: {carrier}")
        raw = eq_data[entry.payload_offset : entry.payload_offset + entry.payload_length]
        parsed = parse_eq_external_team_roster_payload(raw, {})
        expected = [player_carriers[player_id] for player_id in club["roster_player_ids"]]
        if parsed is None or [row.player_record_id for row in parsed.rows] != expected:
            raise SeasonCompilerError(f"post-build linked roster read-back failed for {club['id']}")


def compile_package_to_tree(
    *,
    package_path: Path,
    base_tree: Path,
    materialisation_tree: Path,
    overrides_path: Path | None = None,
    derived_package_id: str | None = None,
) -> dict[str, Any]:
    """Compile a strict V2 package into an existing clean materialisation tree.

    The function writes only JUG98030.FDI, EQ98030.FDI and ENT98030.FDI.  It
    has no output-directory creation, no implicit cache, no backup and no
    fallback input.  Those constraints let the V2 build-plan runner detect any
    accidental expansion of this adapter's write surface.
    """

    package, source_package_sha256 = _load_native_package(package_path)
    review_application: dict[str, Any] | None = None
    overlay_sha256: str | None = None
    if overrides_path is not None:
        package, review_application, overlay_sha256 = _derive_reviewed_package(
            source_package=package,
            overrides_path=overrides_path,
            derived_package_id=derived_package_id,
        )
    elif derived_package_id is not None:
        raise SeasonCompilerError("--derived-package-id requires --overrides")
    from scripts import season_trabzon_opening_layer_v1 as trabzon_opening
    from scripts import season_maccabi_name_layer_v1 as maccabi_names
    from scripts import season_profile_assignment_pruning_layer_v1 as assignments
    try:
        trabzon_opening.reject_factory_recipe(package)
        maccabi_names.reject_factory_recipe(package)
        assignments.reject_factory_recipe(package)
        from scripts import season_source_bound_duplicate_opening_v1 as duplicate_opening
        duplicate_opening.reject_factory_recipe(package)
        from scripts import season_source_bound_namesake_dates_v1 as namesake_dates
        namesake_dates.reject_factory_recipe(package)
        from scripts import season_original_secondary_facts_v1 as secondary_facts
        secondary_facts.reject_factory_recipe(package)
        from scripts import season_stevenage_opening_repair_v1 as stevenage
        stevenage.reject_factory_recipe(package)
        from scripts import season_boreham_opening_repair_v1 as boreham
        boreham.reject_factory_recipe(package)
        from scripts import season_barrow_opening_repair_v1 as barrow
        barrow.reject_factory_recipe(package)
        from scripts import season_city_2024_opening_exchange_v1 as city
        city.reject_factory_recipe(package)
        from scripts import season_woking_2003_owned_opening_v1 as woking
        woking.reject_factory_recipe(package)
        from scripts import season_quality_only_delta_v1 as quality_only
        quality_only.reject_factory_recipe(package)
        from scripts import season_exact_fifa_role_delta_v1 as exact_roles
        exact_roles.reject_factory_recipe(package)
        from scripts import season_donor_keeper_role_delta_v1 as donor_roles
        donor_roles.reject_factory_recipe(package)
        from scripts import season_exact_primary_position_delta_v1 as primary_positions
        primary_positions.reject_factory_recipe(package)
        from scripts import season_exact_primary_position_delta_v2 as alias_primary_positions
        alias_primary_positions.reject_factory_recipe(package)
        from scripts import season_original_country_policy_v2 as country_policy
        country_policy.reject_factory_recipe(package)
        from scripts import season_source_verified_player_changes_v1 as source_changes
        source_changes.reject_factory_recipe(package)
        from scripts import season_annual_position_role_candidate_v1 as annual_roles
        annual_roles.reject_factory_recipe(package)
        from scripts import season_barrow_winger_fine_role_v1 as barrow_roles
        barrow_roles.reject_factory_recipe(package)
        from scripts import season_horne_26979_facts_v1 as horne_facts
        horne_facts.reject_factory_recipe(package)
        from scripts import season_altrincham_macc_joint_exchange_v1 as alty_joint
        alty_joint.reject_factory_recipe(package)
        from scripts import season_vokes_crouch_opening_exchange_v2 as vokes_crouch
        vokes_crouch.reject_factory_recipe(package)
        from scripts import season_madrid_mode1_activation_v1 as madrid_activation
        madrid_activation.reject_factory_recipe(package)
        from scripts import season_verified_owned_roster_transaction_v1 as owned_roster
        owned_roster.reject_factory_recipe(package)
        from scripts import season_owned_club_composition_v1 as retained_composition
        retained_composition.reject_factory_recipe(package)
        from scripts import season_opening_identity_exchange_v1 as opening_exchange
        opening_exchange.reject_factory_recipe(package)
        from scripts import season_resolved_period_country_v3 as resolved_country
        resolved_country.reject_factory_recipe(package)
        from scripts import season_biographic_birth_years_v1 as biography
        biography.reject_factory_recipe(package)
        from scripts import season_cross_period_birth_years_v1 as cross_period
        cross_period.reject_factory_recipe(package)
        from scripts import season_original_person_birth_years_v1 as original_person
        original_person.reject_factory_recipe(package)
        from scripts import season_number_label_names_v2 as numeric_labels
        numeric_labels.reject_factory_recipe(package)
        from scripts import season_foreign_fixed_roster_delta_v1 as foreign
        foreign.reject_factory_recipe(package)
    except ValueError as exc:
        raise SeasonCompilerError(str(exc)) from exc
    effective_package_sha256 = package_v2.sha256_bytes(_canonical_json_bytes(package))
    paths = _ensure_clean_database_inputs(
        base_tree=base_tree, materialisation_tree=materialisation_tree
    )
    country_codes = _extract_country_codes_from_textos(paths[COUNTRY_TABLE_RELATIVE_PATH])
    jug_path = paths["DBDAT/JUG98030.FDI"]
    eq_path = paths["DBDAT/EQ98030.FDI"]
    ent_path = paths["DBDAT/ENT98030.FDI"]
    jug_data = jug_path.read_bytes()
    eq_data = eq_path.read_bytes()
    ent_data = ent_path.read_bytes()
    from scripts import season_italian_opening_layer_v1 as italian_opening
    italian_opening_plans = italian_opening.layers(package, package_path)
    for italian_plan in italian_opening_plans:
        eq_data = italian_opening.prune(eq_data, italian_plan)
    baseline_mode1_roster_tails = _mode1_roster_tails(eq_data)
    ent_carriers = {entry.record_id for entry in IndexedFDIFile.from_bytes(ent_data).entries}
    club_modes = _club_modes(package, eq_data)
    jug_data, appended_mode0_dd6361_ids, appended_mode1_dd6360_ids = _append_package_player_carriers(
        package=package,
        jug_data=jug_data,
        eq_data=eq_data,
    )
    (
        jug_data,
        mode1_recycled_carriers,
        implicit_mode0_clone_rows,
    ) = _materialise_mode1_carrier_recycles(
        package=package,
        jug_data=jug_data,
        eq_data=eq_data,
        club_modes=club_modes,
    )

    (
        player_replacements,
        handling_rows,
        dd6360_handling_written,
        mode1_dd6360_core_written,
        mode1_dd6361_core_written,
        mode1_preserved_rows,
    ) = _player_replacements(
        package=package,
        jug_data=jug_data,
        country_codes=country_codes,
        club_modes=club_modes,
    )
    # An implicit recycle clone is deliberately not a synthetic player in the
    # package: it is an exact clone of the displaced mode-0 carrier.  Its EQ
    # row must therefore be substituted before normal club rewriting, and it
    # must never silently overlap a selected team's independently declared
    # roster plan.
    implicit_clone_team_replacements, implicit_clone_team_statuses = (
        _implicit_mode0_clone_roster_replacements(
            eq_data=eq_data,
            clone_rows=implicit_mode0_clone_rows,
        )
    )
    team_replacements, team_statuses, mode1_roster_plans = _team_replacements(
        package=package, eq_data=eq_data, ent_carriers=ent_carriers,
        implicit_mode0_clone_rows=implicit_mode0_clone_rows,
    )
    overlapping_clone_teams = sorted(
        set(implicit_clone_team_replacements) & set(team_replacements)
    )
    if overlapping_clone_teams:
        raise SeasonCompilerError(
            "implicit recycle clone source team overlaps a package club roster plan: "
            + ", ".join(str(carrier) for carrier in overlapping_clone_teams)
        )
    team_replacements = {
        **implicit_clone_team_replacements,
        **team_replacements,
    }
    team_statuses = [*implicit_clone_team_statuses, *team_statuses]
    manager_replacements = _manager_replacements(package, ent_data)

    from scripts.season_contextual_tactics_v1 import apply_layer, package_layers
    contextual_layers = package_layers(package, package_path)
    compiled_jug = _rebuild_indexed(jug_data, IndexedFDIFile.from_bytes(jug_data), player_replacements)
    compiled_eq = _rebuild_indexed(eq_data, IndexedFDIFile.from_bytes(eq_data), team_replacements)
    from scripts import season_roster_visibility_v1 as visibility
    compiled_eq, visibility_changes = visibility.replay(compiled_eq, package, package_path)
    from scripts.season_opening_order_repair_v1 import apply_layer as apply_order_layer, package_layers as order_layers
    for order_layer in order_layers(package, package_path):
        compiled_jug = apply_order_layer(compiled_eq, compiled_jug, order_layer, allow_compact=True)
    from scripts import season_whole_club_keeper_exchange_v1 as whole_keeper
    compiled_jug, whole_keeper_changes = whole_keeper.replay(compiled_jug, compiled_eq, package, package_path)
    from scripts import season_mode1_sourced_keeper_slot_v1 as sourced_keeper
    compiled_jug, sourced_keeper_changes = sourced_keeper.replay(compiled_jug, compiled_eq, package, package_path)
    from scripts import season_tff_sourced_opening_xi_v1 as sourced_full_xi
    compiled_jug, sourced_full_xi_changes = sourced_full_xi.replay(compiled_jug, compiled_eq, package, package_path, country_codes)
    for italian_plan in italian_opening_plans:
        compiled_jug = italian_opening.order(compiled_jug, compiled_eq, italian_plan)
    # Also bind inline contextual slots to the actual compiled JUG order.
    inline_contexts = [{'carrier_id': c['carrier_id'], 'context': c['opening']['tactics_context']}
                       for c in package['clubs'] if 'tactics_context' in c['opening']]
    if {c['carrier_id'] for c in inline_contexts} & {c['carrier_id'] for layer in contextual_layers for c in layer['clubs']}:
        raise SeasonCompilerError('inline contextual tactics conflict with a recipe-local tactics layer')
    if inline_contexts:
        from scripts.season_contextual_tactics_v1 import SCHEMA
        compiled_eq = apply_layer(compiled_eq, compiled_jug, {'schema_version': SCHEMA, 'clubs': inline_contexts})
    for layer in contextual_layers:
        compiled_eq = apply_layer(compiled_eq, compiled_jug, layer)
    # Build all replacement plans before mutating the clean materialisation.
    # A rejected mode-1 topology/finance request therefore leaves the tree
    # untouched; the outer build-plan can safely discard it and report the
    # precise package error.
    jug_path.write_bytes(compiled_jug)
    if handling_rows:
        handling_receipt = _patch_dd6361_visible_handling(jug_path, handling_rows)
    else:
        handling_receipt = {
            "schema_version": "pm99-dd6361-visible-handling-v1",
            "requested_player_count": 0,
            "goalkeeper_count": 0,
            "changes": [],
        }
    eq_path.write_bytes(compiled_eq)
    ent_path.write_bytes(_rebuild_indexed(ent_data, IndexedFDIFile.from_bytes(ent_data), manager_replacements))
    _assert_mode1_roster_tails_match_plan(
        before=baseline_mode1_roster_tails,
        after_eq_data=eq_path.read_bytes(),
        planned_player_ids=mode1_roster_plans,
    )
    _verify_output(package=package, jug_path=jug_path, eq_path=eq_path)

    outputs = [
        {"path": relative, "sha256": _sha256_file(paths[relative]), "size": paths[relative].stat().st_size}
        for relative in DATABASE_RELATIVE_PATHS
    ]
    return {
        "schema": COMPILER_RECEIPT_SCHEMA,
        "season_package_sha256": effective_package_sha256,
        "source_season_package_sha256": source_package_sha256,
        "review_overrides_sha256": overlay_sha256,
        "review_application": review_application,
        "clubs_written": len(package["clubs"]),
        "authored_roster_visibility_changes": visibility_changes,
        "owned_whole_club_keeper_exchange_changes": whole_keeper_changes,
        "sourced_mode1_complete_xi_changes": sourced_full_xi_changes,
        "original_first_fixture_reserve_keeper_slot_changes": sourced_keeper_changes,
        "original_italian_opening_pruning_and_XI_layers": italian_opening_plans,
        "players_written": len(package["players"]),
        "managers_written": len(package["managers"]),
        "team_statuses": sorted(team_statuses, key=lambda row: (int(row["carrier_id"]), str(row["club_id"] or ""))),
        "contextual_tactics_carriers": sorted([c['carrier_id'] for c in inline_contexts] +
                                             [c['carrier_id'] for layer in contextual_layers for c in layer['clubs']]),
        "dd6361_visible_handling": handling_receipt,
        "dd6360_visible_handling_written_carrier_ids": sorted(dd6360_handling_written),
        "mode1_dd6360_core_written_carrier_ids": sorted(mode1_dd6360_core_written),
        "mode1_dd6361_core_written_carrier_ids": sorted(mode1_dd6361_core_written),
        "mode1_preserved_player_fields": sorted(mode1_preserved_rows, key=lambda row: int(row["carrier_id"])),
        "appended_mode0_dd6361_carrier_ids": appended_mode0_dd6361_ids,
        "appended_mode1_dd6360_carrier_ids": appended_mode1_dd6360_ids,
        "mode1_recycled_mode0_carriers": mode1_recycled_carriers,
        "portraits": {
            "compiler_action": "preserved-for-separate-portrait-stage",
            "native_no_photo_player_ids": sorted(
                row["player_id"]
                for row in package["assets"]["portraits"]
                if row["status"] in {"native-no-photo", "unresolved"}
            ),
        },
        "outputs": outputs,
    }


def write_canonical_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_json_bytes(dict(receipt)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-tree", required=True, type=Path)
    parser.add_argument("--tree", required=True, type=Path, help="existing clean materialisation tree")
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument(
        "--overrides",
        type=Path,
        help="canonical pm99-season-review-overrides-v1 source overlay",
    )
    parser.add_argument(
        "--derived-package-id",
        help="required named source revision when --overrides is supplied",
    )
    parser.add_argument("--receipt", type=Path, help="optional canonical receipt outside the game tree")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        receipt = compile_package_to_tree(
            package_path=args.package,
            base_tree=args.base_tree,
            materialisation_tree=args.tree,
            overrides_path=args.overrides,
            derived_package_id=args.derived_package_id,
        )
        if args.receipt is not None:
            tree = args.tree.expanduser().resolve()
            receipt_path = args.receipt.expanduser().resolve()
            if receipt_path.is_relative_to(tree):
                raise SeasonCompilerError("compiler receipt must be outside the game materialisation tree")
            write_canonical_receipt(receipt_path, receipt)
    except (SeasonCompilerError, pipeline_v2.PipelineError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
