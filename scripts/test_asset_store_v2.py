"""Tests for content-addressed import of retained PM99 art outputs."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from asset_store_v2 import AssetStoreError, build_2015_index, validate_index, write_index  # noqa: E402


def _hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    game = tmp_path / "game"
    dbdat = game / "DBDAT"
    loose = dbdat / "MINIFOTO"
    loose.mkdir(parents=True)
    source = tmp_path / "source.png"
    preview = tmp_path / "preview.png"
    source.write_bytes(b"exact source pixels")
    preview.write_bytes(b"converted preview pixels")

    portrait_container = bytearray(b"x" * 64)
    portrait_raw = b"FACE"
    portrait_container[11:15] = portrait_raw
    (dbdat / "MINIFOTO.PKF").write_bytes(portrait_container)
    loose_raw = b"LOOSE"
    (loose / "J9600002.BMP").write_bytes(loose_raw)
    # This is deliberately not claimed by the face receipt and must remain in
    # the cache inventory rather than being silently discarded.
    (loose / "J9600099.BMP").write_bytes(b"UNLINKED")

    kit_container = bytearray(b"k" * 64)
    kit_raw = b"KIT"
    kit_container[20:23] = kit_raw
    (dbdat / "MINIESC.PKF").write_bytes(kit_container)

    face_receipt = tmp_path / "face.json"
    _write(face_receipt, {
        "minifoto_sha256_before": _hash(b"base portrait container"),
        "minifoto_sha256_after": _hash(bytes(portrait_container)),
        "rows": [
            {
                "record_id": 1,
                "status": "applied",
                "storage": "MINIFOTO.PKF",
                "source_image_path": str(source),
                "preview_path": str(preview),
                "replace_result": {"bitmap_offset": 11, "bitmap_length": 4},
            },
            {
                "record_id": 2,
                "status": "applied",
                "storage": "loose-DBDAT/MINIFOTO",
                "source_image_path": str(source),
                "preview_path": str(preview),
            },
            {"record_id": 3, "status": "unresolved-no-identity-safe-close-era-source"},
        ],
    })
    kit_receipt = tmp_path / "kits.json"
    _write(kit_receipt, {
        "patched": [{
            "archive_name": "MINIESC.PKF",
            "archive_sha256_before": _hash(b"base kit container"),
            "archive_sha256_after": _hash(bytes(kit_container)),
            "team_id": 307,
            "slot": 3,
            "bitmap_offset": 20,
            "bitmap_length": 3,
            "bitmap_sha256_after": _hash(kit_raw),
        }],
    })
    return face_receipt, kit_receipt, game, tmp_path / "asset-store"


def test_import_caches_exact_outputs_and_marks_source_regeneration_blocked(tmp_path: Path) -> None:
    face, kits, game, store = _fixture(tmp_path)
    index = build_2015_index(face_receipt_path=face, kit_receipt_path=kits, game_root=game, store_root=store)
    write_index(store, index)
    summary = validate_index(store, verify_blobs=True)
    assert summary["portrait_rows"] == 3
    assert summary["kit_archives"] == 1
    assert index["build_modes"]["cached_output"]["status"] == "qualified-with-matching-base"
    assert index["build_modes"]["strict_source_provenance"]["status"] == "blocked"
    assert index["portraits"][0]["output"]["blob"]["sha256"] == _hash(b"FACE")
    assert index["portraits"][1]["output"]["blob"]["sha256"] == _hash(b"LOOSE")
    assert index["portraits"][2]["status"] == "unresolved"
    assert [row["filename"] for row in index["unlinked_loose_outputs"]] == ["J9600099.BMP"]


def test_missing_source_does_not_launder_a_cached_output_into_regenerable(tmp_path: Path) -> None:
    face, kits, game, store = _fixture(tmp_path)
    receipt = json.loads(face.read_text())
    Path(receipt["rows"][0]["source_image_path"]).unlink()
    _write(face, receipt)
    index = build_2015_index(face_receipt_path=face, kit_receipt_path=kits, game_root=game, store_root=store)
    assert index["portraits"][0]["status"] == "cached-output"
    assert "source" not in index["portraits"][0]
    assert index["portraits"][0]["regeneration"]["state"] == "non-regenerable-legacy"


def test_import_refuses_receipt_hash_mismatch(tmp_path: Path) -> None:
    face, kits, game, store = _fixture(tmp_path)
    receipt = json.loads(kits.read_text())
    receipt["patched"][0]["bitmap_sha256_after"] = "0" * 64
    _write(kits, receipt)
    with pytest.raises(AssetStoreError, match="raw bitmap does not match receipt"):
        build_2015_index(face_receipt_path=face, kit_receipt_path=kits, game_root=game, store_root=store)
