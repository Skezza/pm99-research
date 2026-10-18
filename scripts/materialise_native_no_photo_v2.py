#!/usr/bin/env python3
"""Materialise PM99 native no-photo state for unresolved V2 package portraits.

An unresolved portrait must not leave a recycled carrier's image visible.  This
small, separate V2 asset stage disables the matching active MINIFOTO directory
entry in place (without repacking the archive) and removes any matching loose
``DBDAT/MINIFOTO/J96xxxxx.BMP`` override.  It never invents or substitutes an
image.  Its receipt records every player that falls back to PM99's ordinary
no-photo state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import decode_obfuscated_bitmap_name  # noqa: E402
from scripts import season_package_v2 as package_v2  # noqa: E402


RECEIPT_SCHEMA = "pm99-native-no-photo-materialisation-v1"
DIRECTORY_RECORD_SIZE = 38
ACTIVE_DIRECTORY_TYPE = 0x02


class NativeNoPhotoError(ValueError):
    """The clean materialisation does not satisfy the no-photo contract."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _active_offsets_for_player(archive: bytes | bytearray, player_id: int) -> list[int]:
    """Find all active directory rows for an exact PM99 player bitmap name.

    This deliberately examines the archive directory byte/name signature, not
    image decode success.  A malformed inherited BMP must also be disabled;
    otherwise a game lookup could still resolve a stale carrier image.
    """

    expected_name = f"J96{player_id:05d}.BMP"
    offsets: list[int] = []
    maximum = max(0, len(archive) - DIRECTORY_RECORD_SIZE)
    for offset in range(maximum + 1):
        if archive[offset] != ACTIVE_DIRECTORY_TYPE:
            continue
        try:
            decoded = decode_obfuscated_bitmap_name(bytes(archive[offset + 1 : offset + 21]))
        except ValueError:
            continue
        name = decoded.split(b"\x00", 1)[0].decode("ascii", errors="ignore")
        if name == expected_name:
            offsets.append(offset)
    return offsets


def _active_offsets_for_players(archive: bytes | bytearray, player_ids: Iterable[int]) -> dict[int, list[int]]:
    """Scan the archive once for a batch of exact player names."""

    wanted = {int(player_id): f"J96{int(player_id):05d}.BMP" for player_id in player_ids}
    by_name = {name: player_id for player_id, name in wanted.items()}
    offsets = {player_id: [] for player_id in wanted}
    maximum = max(0, len(archive) - DIRECTORY_RECORD_SIZE)
    for offset in range(maximum + 1):
        if archive[offset] != ACTIVE_DIRECTORY_TYPE:
            continue
        try:
            decoded = decode_obfuscated_bitmap_name(bytes(archive[offset + 1 : offset + 21]))
        except ValueError:
            continue
        name = decoded.split(b"\x00", 1)[0].decode("ascii", errors="ignore")
        player_id = by_name.get(name)
        if player_id is not None:
            offsets[player_id].append(offset)
    return offsets


def _targets(package: Mapping[str, Any]) -> list[tuple[str, int, str]]:
    players_by_id = {str(row["id"]): row for row in package["players"]}
    targets: list[tuple[str, int, str]] = []
    for portrait in package["assets"]["portraits"]:
        status = str(portrait["status"])
        if status not in {"native-no-photo", "unresolved"}:
            continue
        player_id = str(portrait["player_id"])
        player = players_by_id.get(player_id)
        if player is None:
            raise NativeNoPhotoError(f"portrait references absent player {player_id}")
        targets.append((player_id, int(player["carrier_id"]), status))
    return sorted(targets, key=lambda row: (row[1], row[0]))


def materialise_native_no_photo(*, package: Mapping[str, Any], game_tree: Path) -> dict[str, Any]:
    """Disable every unresolved/native-no-photo carrier asset in ``game_tree``."""

    game_tree = game_tree.resolve()
    archive_path = game_tree / "DBDAT" / "MINIFOTO.PKF"
    if not archive_path.is_file() or archive_path.is_symlink():
        raise NativeNoPhotoError(f"missing regular MINIFOTO.PKF in {game_tree}")
    package_v2.validate_package(package, strict=True)
    target_rows = _targets(package)
    original = archive_path.read_bytes()
    archive = bytearray(original)
    loose_root = game_tree / "DBDAT" / "MINIFOTO"
    initial_offsets = _active_offsets_for_players(archive, (carrier_id for _id, carrier_id, _status in target_rows))
    outcomes: list[dict[str, Any]] = []
    for player_id, carrier_id, declared_status in target_rows:
        offsets = initial_offsets[carrier_id]
        for offset in offsets:
            archive[offset] = 0
        loose_path = loose_root / f"J96{carrier_id:05d}.BMP"
        removed_loose = loose_path.is_file()
        loose_path.unlink(missing_ok=True)
        if loose_path.exists():
            raise NativeNoPhotoError(f"failed to remove loose MINIFOTO override for player carrier {carrier_id}")
        outcomes.append({
            "player_id": player_id,
            "player_carrier_id": carrier_id,
            "declared_status": declared_status,
            "disabled_archive_directory_offsets": offsets,
            "removed_loose_bitmap": removed_loose,
            "resulting_state": "native-no-photo",
        })
    residual_offsets = _active_offsets_for_players(archive, (carrier_id for _id, carrier_id, _status in target_rows))
    residual = [carrier_id for carrier_id, offsets in residual_offsets.items() if offsets]
    if residual:
        raise NativeNoPhotoError(
            "failed to disable all active MINIFOTO rows for player carriers: "
            + ", ".join(str(carrier_id) for carrier_id in residual)
        )
    patched = bytes(archive)
    if patched != original:
        archive_path.write_bytes(patched)
    return {
        "schema_version": RECEIPT_SCHEMA,
        "package_sha256": package_v2.sha256_bytes(package_v2.canonical_json_bytes(dict(package))),
        "archive_sha256_before": hashlib.sha256(original).hexdigest(),
        "archive_sha256_after": _sha256(archive_path),
        "target_player_count": len(target_rows),
        "native_no_photo_player_count": len(outcomes),
        "disabled_archive_record_count": sum(len(row["disabled_archive_directory_offsets"]) for row in outcomes),
        "removed_loose_bitmap_count": sum(1 for row in outcomes if row["removed_loose_bitmap"]),
        "outcomes": outcomes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--game-tree", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args(argv)
    package = package_v2.read_canonical_package(args.package)
    receipt = materialise_native_no_photo(package=package, game_tree=args.game_tree)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_bytes(package_v2.canonical_json_bytes(receipt))
    print(json.dumps({
        "target_player_count": receipt["target_player_count"],
        "native_no_photo_player_count": receipt["native_no_photo_player_count"],
        "disabled_archive_record_count": receipt["disabled_archive_record_count"],
        "receipt": str(args.receipt),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
