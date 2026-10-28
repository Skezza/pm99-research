"""Wrap literal factory pixels in an existing target's native BMP header.

Only creates a detached source envelope, never edits a playable game. The stock
kit writer can then preserve archive sizes even when two valid native BMP
wrappers differ by two bytes. All geometry, indices and opaque target bytes are
checked through the established editor pixel-row API.
"""
import hashlib
from pathlib import Path

from app.bitmap_pixel_rows import (
    bitmap_pixel_ranges, read_top_down_bitmap_rows, replace_top_down_bitmap_rows,
)
from app.minifoto_bitmap_archive import iter_obfuscated_bmp_records_from_bytes
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

ARCHIVES = ('MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def wrap_factory_pixels(source, target):
    """Keep the entire target container except its visible pixel indices."""
    if ((source.width, source.height, source.bits_per_pixel)
            != (target.width, target.height, target.bits_per_pixel)
            or source.bits_per_pixel != 8):
        raise ValueError('factory envelope requires identical indexed geometry')
    rows = read_top_down_bitmap_rows(source)
    result = replace_top_down_bitmap_rows(target, rows)
    allowed = {i for start, end in bitmap_pixel_ranges(target) for i in range(start, end)}
    if (len(result) != len(target.raw_bitmap)
            or any(a != b and i not in allowed
                   for i, (a, b) in enumerate(zip(target.raw_bitmap, result)))):
        raise ValueError('factory envelope changed target header/padding/length')
    pixel_bytes = bytes(value for row in rows for value in row)
    return result, dict(source_bitmap_sha256=digest(source.raw_bitmap),
        target_header_template_sha256=digest(target.raw_bitmap),
        wrapped_bitmap_sha256=digest(result), source_pixel_sha256=digest(pixel_bytes),
        source_pixel_offset=source.pixel_offset, target_pixel_offset=target.pixel_offset,
        source_bitmap_length=len(source.raw_bitmap), target_bitmap_length=len(result),
        target_header_padding_and_length_preserved=True,
        visible_indices_are_literal_original_factory_pixels=True)


def records(name, raw):
    return list(iter_obfuscated_bmp_records_from_bytes(
        name, raw, file_name_pattern=r'EQ96\d{4}\.BMP'))


def create_source_envelope(*, release, source_dir, source_team_id, target_team_id, output):
    """Preserve original source records, replacing only one source BMP wrapper.

    The caller must separately approve club identity and palette compatibility;
    this format adapter neither establishes historical identity nor publishes.
    """
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('factory source envelope output must be new')
    source_name, target_name = f'EQ96{source_team_id:04d}.BMP', f'EQ96{target_team_id:04d}.BMP'
    prepared, proofs = {}, {}
    for name in ARCHIVES:
        original = (Path(source_dir) / name).read_bytes()
        target_bytes = (release.game_path / 'DBDAT' / name).read_bytes()
        source_records = records(name, original)
        target_records = records(name, target_bytes)
        sources = [r for r in source_records if r.file_name == source_name]
        targets = [r for r in target_records if r.file_name == target_name]
        own = [r for r in source_records if r.file_name == target_name]
        if len(sources) != 1 or len(targets) != 1 or len(own) != 1:
            raise ValueError('missing or ambiguous source/target factory record')
        source, target = sources[0], targets[0]
        if target.raw_bitmap != own[0].raw_bitmap:
            raise ValueError('refusing a target with non-factory authored artwork')
        wrapped, proof = wrap_factory_pixels(source, target)
        difference = source.bitmap_length - len(wrapped)
        if difference not in (0, 2) or source.pixel_offset - target.pixel_offset not in (0, difference):
            raise ValueError('only identical or two-byte native BMP wrapper differences is supported')
        # Source PKFs have absolute bitmap offsets. Keep the allocated span and
        # every later offset; shorten only this source directory entry. Any two
        # unused trailing bytes remain exact, and never enter a runtime game.
        transformed = bytearray(original)
        transformed[source.bitmap_offset:source.bitmap_offset + len(wrapped)] = wrapped
        length_offset = source.record_offset + 30
        transformed[length_offset:length_offset + 4] = len(wrapped).to_bytes(4, 'little')
        allowed = set(range(source.bitmap_offset, source.bitmap_offset + len(wrapped)))
        allowed.update(range(length_offset, length_offset + 4))
        if len(transformed) != len(original) or any(
                a != b and i not in allowed for i, (a, b) in enumerate(zip(original, transformed))):
            raise ValueError('source envelope changed unrelated source bytes or offsets')
        transformed = bytes(transformed)
        after = records(name, transformed)
        if [r.file_name for r in after] != [r.file_name for r in source_records]:
            raise ValueError('source envelope changed archive record names/order')
        for before_record, after_record in zip(source_records, after, strict=True):
            expected = wrapped if before_record.file_name == source_name else before_record.raw_bitmap
            if after_record.raw_bitmap != expected:
                raise ValueError('source envelope changed another source bitmap')
        normalized = next(r for r in after if r.file_name == source_name)
        if read_top_down_bitmap_rows(normalized) != read_top_down_bitmap_rows(source):
            raise ValueError('normalized envelope no longer contains literal factory pixels')
        prepared[name] = transformed
        proofs[name] = dict(**proof, original_source_archive_sha256=digest(original),
            current_target_archive_sha256=digest(target_bytes),
            source_envelope_archive_sha256=digest(transformed),
            all_other_source_bitmap_records_exact=True)
    # Complete all preflight checks before creating any source-envelope files.
    output.mkdir(parents=True)
    for name, raw in prepared.items():
        (output / name).write_bytes(raw)
    receipt = dict(schema='pm99-literal-factory-pixels-target-header-source-envelope-v1',
        season=release.season, parent_release_id=release.release_id,
        parent_manifest_sha256=release.manifest_sha256,
        source_team_id=source_team_id, target_team_id=target_team_id,
        source_dir=registry.relative_workspace_path(Path(source_dir)), archives=proofs,
        no_playable_game_or_original_source_writes=True,
        scope='Compatible source envelopes only. Exact original factory pixel indices; target native headers/padding retained. Not original raw factory BMP equivalence or historical design certification.')
    pipeline.write_canonical_json(output / 'factory-envelope-receipt.json', receipt)
    return receipt
