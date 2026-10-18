"""Fixture tests for the generic fail-closed compact-kit archive stage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import materialise_season_kit_archives_v1 as materialiser
from app.minifoto_bitmap_archive import encode_obfuscated_bitmap_name, iter_obfuscated_bmp_records


def _bitmap(*, pixel: int) -> bytes:
    width = height = 4
    result = bytearray(26 + width * height)
    result[:2] = b"BM"
    result[2:6] = len(result).to_bytes(4, "little")
    result[10:14] = (26).to_bytes(4, "little")
    result[14:18] = (12).to_bytes(4, "little")
    result[18:20] = width.to_bytes(2, "little")
    result[20:22] = height.to_bytes(2, "little")
    result[22:24] = (1).to_bytes(2, "little")
    result[24:26] = (8).to_bytes(2, "little")
    result[26:] = bytes([pixel]) * (width * height)
    return bytes(result)


def _archive(*, carrier: int, pixel: int) -> bytes:
    bitmap = _bitmap(pixel=pixel)
    offset = 64
    result = bytearray(offset + len(bitmap))
    result[0] = 0x02
    result[1:21] = encode_obfuscated_bitmap_name(f"EQ96{carrier:04d}.BMP")
    result[26:30] = offset.to_bytes(4, "little")
    result[30:34] = len(bitmap).to_bytes(4, "little")
    result[offset:] = bitmap
    return bytes(result)


def _write_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    clean = tmp_path / "clean" / "DBDAT"
    clean.mkdir(parents=True)
    carrier = 600
    for archive, pixel in zip(materialiser.ARCHIVES, (3, 4, 5)):
        (clean / archive).write_bytes(_archive(carrier=carrier, pixel=pixel))
    renders = tmp_path / "renders"
    artifact_dir = renders / "artifacts" / "aa"
    artifact_dir.mkdir(parents=True)
    artifacts = []
    for archive, pixel in zip(materialiser.ARCHIVES, (13, 14, 15)):
        base = iter_obfuscated_bmp_records(clean / archive)[0].raw_bitmap
        candidate = bytearray(base)
        candidate[26:] = bytes([pixel]) * 16
        digest = materialiser.sha256_bytes(bytes(candidate))
        path = artifact_dir / f"{digest}.bmp"
        path.write_bytes(candidate)
        artifacts.append({
            "id": f"kit-render-2000-01-{carrier}-{archive.removesuffix('.PKF').lower()}",
            "kind": "kit-render",
            "sha256": digest,
            "relative_path": str(path.relative_to(renders)),
        })
    catalogue_sha = "a" * 64
    binding = {
        "schema_version": materialiser.BINDING_SCHEMA,
        "kit_catalogue_sha256": catalogue_sha,
        "clubs": [{"carrier_id": carrier, "artifacts": artifacts}],
    }
    receipt = {
        "schema_version": materialiser.RENDER_RECEIPT_SCHEMA,
        "season": {"label": "2000/01"},
        "kit_catalogue_sha256": catalogue_sha,
        "source": {"archive_sha256": {archive: materialiser.sha256_file(clean / archive) for archive in materialiser.ARCHIVES}},
        "coverage": {"bound_club_count": 1, "artifact_count": 3},
        "rows": [{"carrier_id": carrier, "club_name": "Example Town", "status": "rendered-source-ready", "artifacts": artifacts}],
    }
    binding_path = renders / "kit-render-bindings-v1.json"
    receipt_path = renders / "kit-render-receipt-v1.json"
    binding_path.write_bytes(materialiser.canonical_json_bytes(binding))
    receipt_path.write_bytes(materialiser.canonical_json_bytes(receipt))
    return clean, binding_path, receipt_path


def test_materialises_three_new_archives_from_matching_render_receipt(tmp_path: Path) -> None:
    clean, binding, receipt = _write_fixture(tmp_path)
    before = {archive: (clean / archive).read_bytes() for archive in materialiser.ARCHIVES}
    output = tmp_path / "stage"

    result = materialiser.materialise(
        render_bindings=binding, render_receipt=receipt, clean_dbdat=clean, output_dir=output
    )

    assert result["release_eligible"] is False
    assert result["coverage"] == {"bound_carrier_count": 1, "patched_record_count": 3, "archive_count": 3}
    assert (output / "kit-archive-materialisation-receipt-v1.json").is_file()
    assert all((output / "archives" / archive).is_file() for archive in materialiser.ARCHIVES)
    assert {archive: (clean / archive).read_bytes() for archive in materialiser.ARCHIVES} == before
    assert all(result["archives"][archive]["sha256_before"] != result["archives"][archive]["sha256_after"] for archive in materialiser.ARCHIVES)
    with pytest.raises(materialiser.KitArchiveMaterialisationError, match="refusing to replace"):
        materialiser.materialise(render_bindings=binding, render_receipt=receipt, clean_dbdat=clean, output_dir=output)


def test_rejects_stale_clean_base_before_creating_output(tmp_path: Path) -> None:
    clean, binding, receipt = _write_fixture(tmp_path)
    archive = clean / materialiser.ARCHIVES[0]
    archive.write_bytes(archive.read_bytes() + b"stale")
    output = tmp_path / "stage"

    with pytest.raises(materialiser.KitArchiveMaterialisationError, match="does not match"):
        materialiser.materialise(render_bindings=binding, render_receipt=receipt, clean_dbdat=clean, output_dir=output)
    assert not output.exists()


def test_rejects_unknown_or_mismatched_candidate_bitmap_before_creating_output(tmp_path: Path) -> None:
    clean, binding_path, receipt = _write_fixture(tmp_path)
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    artifact = binding["clubs"][0]["artifacts"][0]
    candidate = binding_path.parent / artifact["relative_path"]
    candidate.write_bytes(b"not-a-bitmap")
    artifact["sha256"] = materialiser.sha256_file(candidate)
    binding_path.write_bytes(materialiser.canonical_json_bytes(binding))
    receipt_data = json.loads(receipt.read_text(encoding="utf-8"))
    receipt_data["rows"][0]["artifacts"][0]["sha256"] = artifact["sha256"]
    receipt.write_bytes(materialiser.canonical_json_bytes(receipt_data))

    with pytest.raises(materialiser.KitArchiveMaterialisationError, match="unsupported bitmap"):
        materialiser.materialise(
            render_bindings=binding_path, render_receipt=receipt, clean_dbdat=clean, output_dir=tmp_path / "stage"
        )


def test_rejects_binding_receipt_artifact_collision(tmp_path: Path) -> None:
    clean, binding_path, receipt = _write_fixture(tmp_path)
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    binding["clubs"][0]["artifacts"][1]["id"] = binding["clubs"][0]["artifacts"][0]["id"]
    binding_path.write_bytes(materialiser.canonical_json_bytes(binding))

    with pytest.raises(materialiser.KitArchiveMaterialisationError, match="collide on artifact id"):
        materialiser.materialise(
            render_bindings=binding_path, render_receipt=receipt, clean_dbdat=clean, output_dir=tmp_path / "stage"
        )
