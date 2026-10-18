#!/usr/bin/env python3
"""Deterministic checks for reviewed manual portrait crops."""

from __future__ import annotations

import sys
import tempfile
from types import SimpleNamespace
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from prepare_2015_english92_fifa16_faces import (  # noqa: E402
    _disable_archive_minifoto_record,
    _manual_source_crop,
    _set_native_no_photo,
)


def main() -> int:
    image = Image.new("RGB", (100, 80), "black")
    image.paste("red", (20, 16, 60, 48))
    cropped = _manual_source_crop(
        {"manual_source_crop": {"left": 0.2, "top": 0.2, "width": 0.4, "height": 0.4}},
        image,
    )
    assert cropped.size == (40, 32)
    assert cropped.getpixel((0, 0)) == (255, 0, 0)
    try:
        _manual_source_crop({"manual_source_crop": {"left": 0.8, "top": 0, "width": 0.3, "height": 1}}, image)
    except ValueError:
        pass
    else:  # pragma: no cover - explicit failure diagnostic
        raise AssertionError("out-of-bounds manual crop was accepted")
    directory = bytearray(b"\x00\x02\x00")
    _disable_archive_minifoto_record(directory, record_offset=1)
    assert directory == b"\x00\x00\x00"
    try:
        _disable_archive_minifoto_record(directory, record_offset=1)
    except ValueError:
        pass
    else:  # pragma: no cover - explicit failure diagnostic
        raise AssertionError("inactive archive record was accepted")
    with tempfile.TemporaryDirectory() as raw_dir:
        loose_root = Path(raw_dir) / "MINIFOTO"
        loose_root.mkdir()
        (loose_root / "J9600042.BMP").write_bytes(b"old loose carrier face")
        archive = bytearray(b"\x00\x00\x02\x00")
        no_photo: dict[str, object] = {}
        _set_native_no_photo(
            entry=no_photo,
            record_id=42,
            archive=archive,
            records={42: SimpleNamespace(record_offset=2, bitmap_offset=3, bitmap_length=1)},
            loose_root=loose_root,
            reason="no identity-safe close-era portrait source",
        )
        assert archive[2] == 0
        assert not (loose_root / "J9600042.BMP").exists()
        assert no_photo["status"] == "intentionally-no-photo"
    print("manual source crop and no-photo checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
