#!/usr/bin/env python3
"""Render hash-bound PM99 kit artifacts from a V1 season kit catalogue.

The clean base archives supply only record dimensions, transparency mask and
palette. Wikipedia rows require the exact referenced Commons pattern layers;
reviewed FKA rows use their explicit PM99 style contract. Unresolved catalogue
rows and unavailable render prerequisites remain gaps and produce no binding.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / "upstream" / "pm99-skezmod-db-editor"
for candidate in (ROOT, EDITOR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.minifoto_bitmap_archive import discover_riff_palette_resource, iter_obfuscated_bmp_records, load_riff_palette  # noqa: E402
from scripts import materialise_2015_world_kits as legacy_renderer  # noqa: E402
from scripts import patch_english80_reference_kits_v2 as reviewed_renderer  # noqa: E402
from scripts import pm99_factory_kit_renderer_v6 as factory_tone_renderer  # noqa: E402
from scripts import pm99_kit_raster_v1 as kit_raster  # noqa: E402
from scripts import season_kit_catalogue_v1 as catalogue_v1  # noqa: E402
from scripts.pm99_kit_palette_v1 import runtime_kit_palette  # noqa: E402


SCHEMA = "pm99-season-kit-render-bindings-v1"
RECEIPT_SCHEMA = "pm99-season-kit-render-receipt-v1"
ARCHIVES = ("MINIESC.PKF", "NANOESC.PKF", "RIDIESC.PKF")


class KitRenderError(ValueError):
    """Catalogue or clean-base input violates the deterministic renderer contract."""


def catalogue_from_english_compiler_input(document: Mapping[str, Any]) -> dict[str, Any]:
    """Project assigned English kit layers onto their final mode-0 carriers."""
    if document.get("schema_version") != "pm99-english-mode0-compiler-input-v1":
        raise KitRenderError("English compiler input schema is unsupported")
    label = str(document.get("season") or "")
    match = re.fullmatch(r"((?:19|20)\d{2})/(\d{2})", label)
    if not match:
        raise KitRenderError("English compiler input season must be YYYY/YY")
    start = int(match.group(1))
    rows = []
    for club in document.get("clubs") or []:
        kit = club.get("kit") if isinstance(club, Mapping) else None
        carrier = club.get("carrier_id") if isinstance(club, Mapping) else None
        name = str(club.get("club") or "") if isinstance(club, Mapping) else ""
        if not isinstance(carrier, int) or not name or not isinstance(kit, Mapping):
            raise KitRenderError("English compiler club lacks carrier, identity, or kit layer")
        status = str(kit.get("status") or "")
        row = {"carrier_id": carrier, "club_name": name, "status": status, "reason": kit.get("reason")}
        if status == "source-ready":
            accepted_policies = {
                "historical-target-season",
                "target-season-url-with-nearest-source-backed-style-provisional",
                "exited-club-prior-season-source-backed-style-fallback",
            }
            if kit.get("policy") not in accepted_policies or not isinstance(kit.get("home"), Mapping):
                raise KitRenderError(f"source-ready English kit lacks exact historical contract: {name}")
            row["render_contract"] = dict(kit["home"])
            row["source"] = {key: value for key, value in kit.items() if key.startswith("source_") or key in {"attribution", "facts", "policy", "style_source_season", "style_source_url"}}
        rows.append(row)
    carriers = [row["carrier_id"] for row in rows]
    if len(carriers) != len(set(carriers)):
        raise KitRenderError("English compiler input contains duplicate carriers")
    return {"schema_version": catalogue_v1.SCHEMA, "season": {"start_year": start, "end_year": start + 1, "label": label}, "policy": {"projection": "hash-bound-English-compiler-input-final-mode0-carriers"}, "rows": sorted(rows, key=lambda row: row["carrier_id"])}


def canonical_json_bytes(value: Any) -> bytes:
    return catalogue_v1.canonical_json_bytes(value)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_index(path: Path) -> dict[int, Any]:
    rows = {}
    for record in iter_obfuscated_bmp_records(path, file_name_pattern=r"^EQ96\d{4}\.BMP$"):
        match = re.fullmatch(r"EQ96(\d{4})\.BMP", str(record.file_name), flags=re.IGNORECASE)
        if match:
            rows[int(match.group(1))] = record
    return rows


def _palette(dbdat: Path) -> tuple[list[tuple[int, int, int]], dict[str, Any]]:
    try:
        palette, source = runtime_kit_palette(dbdat)
    except ValueError as exc:
        raise KitRenderError(str(exc)) from exc
    return palette, {**source, "sha256": sha256_file(Path(str(source["path"]))) }


def _cached_layers(tokens: Mapping[str, str], cache_dir: Path) -> dict[str, Any] | None:
    layers = {}
    defaulted = []
    for part in ("body", "left_arm", "right_arm"):
        stem = str(tokens.get(part) or "").strip().lstrip("_")
        if not stem:
            defaulted.append(part)
            continue
        url = f"https://commons.wikimedia.org/wiki/Special:Redirect/file/Kit_{part}_{stem}.png"
        index = cache_dir / "pattern-index" / f"{sha256_bytes(url.encode('utf-8'))}.json"
        if not index.is_file():
            return None
        try:
            row = json.loads(index.read_text(encoding="utf-8"))
            path = Path(str(row.get("path") or ""))
            if not path.is_file() or sha256_file(path) != row.get("sha256"):
                return None
            layers[part] = row
        except (OSError, ValueError, json.JSONDecodeError):
            return None
    return {"status": "ready", "tokens": dict(tokens), "layers": layers, "defaulted_empty_parts": defaulted}


def _fetch_exact_layer(part: str, stem: str, cache_dir: Path) -> dict[str, Any]:
    url = f"https://commons.wikimedia.org/wiki/Special:Redirect/file/Kit_{part}_{stem}.png"
    index_path = cache_dir / "pattern-index" / f"{sha256_bytes(url.encode('utf-8'))}.json"
    if index_path.is_file():
        try:
            row = json.loads(index_path.read_text(encoding="utf-8"))
            path = Path(str(row.get("path") or ""))
            if path.is_file() and sha256_file(path) == row.get("sha256"):
                return {"status": "ready", "layer": row}
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    for attempt in range(4):
        try:
            response = legacy_renderer.requests.get(
                url, headers={"User-Agent": legacy_renderer.USER_AGENT}, timeout=10
            )
            if response.status_code == 429:
                time.sleep(float(2 ** attempt))
                continue
            if response.status_code != 200:
                return {"status": "missing", "reason": f"{part}-http-{response.status_code}", "failed_url": url}
            image = legacy_renderer.Image.open(io.BytesIO(response.content))
            image.verify()
            digest = sha256_bytes(response.content)
            path = cache_dir / "patterns" / digest[:2] / f"{digest}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and sha256_file(path) != digest:
                raise KitRenderError(f"content-addressed collision: {path}")
            if not path.exists():
                path.write_bytes(response.content)
            result = {
                "url": url,
                "path": str(path.resolve()),
                "sha256": digest,
                "dimensions": {"width": image.width, "height": image.height},
            }
            index_path.parent.mkdir(parents=True, exist_ok=True)
            index_path.write_bytes(canonical_json_bytes(result))
            return {"status": "ready", "layer": result}
        except Exception as exc:
            if attempt == 3:
                return {"status": "missing", "reason": f"{part}-{type(exc).__name__}: {exc}", "failed_url": url}
            time.sleep(float(2 ** attempt))
    return {"status": "missing", "reason": f"{part}-no-valid-response", "failed_url": url}


def resolve_wikipedia_layers(tokens: Mapping[str, str], cache_dir: Path, *, allow_network: bool) -> dict[str, Any]:
    cached = _cached_layers(tokens, cache_dir)
    if cached is not None:
        return cached
    if not allow_network:
        return {"status": "missing", "reason": "exact-pattern-layer-cache-miss-network-disabled"}
    # Resolve each layer independently so successful content-addressed fetches
    # survive a later panel failure and a retry never redownloads them.
    layers: dict[str, Any] = {}
    defaulted: list[str] = []
    for part in ("body", "left_arm", "right_arm"):
        stem = str(tokens.get(part) or "").strip().lstrip("_")
        if not stem:
            defaulted.append(part)
            continue
        url = f"https://commons.wikimedia.org/wiki/Special:Redirect/file/Kit_{part}_{stem}.png"
        index_path = cache_dir / "pattern-index" / f"{sha256_bytes(url.encode('utf-8'))}.json"
        if index_path.is_file():
            try:
                row = json.loads(index_path.read_text(encoding="utf-8"))
                path = Path(str(row.get("path") or ""))
                if path.is_file() and sha256_file(path) == row.get("sha256"):
                    layers[part] = row
                    continue
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        fetched = _fetch_exact_layer(part, stem, cache_dir)
        if fetched.get("status") != "ready":
            return fetched
        layers[part] = fetched["layer"]
    return {"status": "ready", "tokens": dict(tokens), "layers": layers, "defaulted_empty_parts": defaulted}


def _write_artifact(payload: bytes, output_dir: Path) -> tuple[Path, str]:
    digest = sha256_bytes(payload)
    path = output_dir / "artifacts" / digest[:2] / f"{digest}.bmp"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise KitRenderError(f"content-addressed collision: {path}")
    if not path.exists():
        path.write_bytes(payload)
    return path, digest


def _reviewed_style_payload(
    record: Any,
    template: Any,
    palette: list[tuple[int, int, int]],
    style: Mapping[str, Any],
) -> bytes:
    """Render a season recipe through reviewed PM99 factory artwork.

    The dated layer remains the authority for colours and pattern.  The clean
    factory record supplies only its silhouette, folds, highlights and
    garment cuts; V5 copies the result into the target record's pixel lane.
    """
    return factory_tone_renderer.render_template_on_record(
        record, template, palette, dict(style)
    )


def _pattern_texture(path, fabric_rgb, size, part=None):
    """Unwrap the source garment, not Commons' white diagram backdrop."""
    from collections import deque
    with legacy_renderer.Image.open(path) as opened:
        source = opened.convert('RGBA')
    base = legacy_renderer.Image.new('RGBA', source.size, fabric_rgb + (255,))
    source = legacy_renderer.Image.alpha_composite(base, source).convert('RGB')
    width, height = source.size
    if part == 'body':
        # Commons' torso diagrams are rectangular and open at the hem. White
        # fabric is therefore connected to the backdrop: flood-fill cannot
        # distinguish it from background. Keep the fixed torso interior,
        # including white side panels, instead of stretching only its logos.
        return source.crop((1, min(8, height // 5), width - 1, height - 1)).resize(
            size, legacy_renderer.Image.Resampling.NEAREST)
    outside = set()
    queue = deque()
    for x in range(width):
        queue.extend(((x, 0), (x, height - 1)))
    for y in range(height):
        queue.extend(((0, y), (width - 1, y)))
    while queue:
        x, y = queue.popleft()
        if (x, y) in outside or not (0 <= x < width and 0 <= y < height):
            continue
        if min(source.getpixel((x, y))) < 245:
            continue
        outside.add((x, y))
        queue.extend(((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))
    mask = {(x, y) for y in range(height) for x in range(width) if (x, y) not in outside}
    # A one-pixel inset removes the diagram's black outline. PM99 supplies its
    # own linework; the source contributes only fabric colours and patterns.
    inner = {(x, y) for x, y in mask if all(p in mask for p in
             ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)))}
    if inner:
        mask = inner
    if part in {'left_arm', 'right_arm'}:
        # Some sleeve outlines are open by a pixel. Preserve white fabric
        # between both contour edges even if flood-fill can reach it. The
        # inset excludes diagram outlines, not coloured sleeve decoration.
        valid = {}
        for y in range(height):
            contour = [x for x in range(width) if min(source.getpixel((x, y))) < 245]
            if contour:
                # Commons sleeves are cropped at their INNER edge. White or
                # transparent fabric there need not have a second outline.
                # Include it instead of inflating a thin coloured cuff.
                lo, hi = (contour[0] + 1, width - 1) if part == 'left_arm' else (0, contour[-1])
                if hi - lo >= 3:
                    valid[y] = list(range(lo, hi))
    else:
        valid = {y: sorted(x for x in range(width) if (x, y) in mask) for y in range(height)}
    valid = {y: xs for y, xs in valid.items() if xs}
    if not valid:
        return source.resize(size, legacy_renderer.Image.Resampling.LANCZOS)
    first, last = min(valid), max(valid)
    texture = legacy_renderer.Image.new('RGB', size)
    for y in range(size[1]):
        sy = round(first + (last - first) * y / max(1, size[1] - 1))
        if sy not in valid:
            sy = min(valid, key=lambda row: (abs(row - sy), row))
        xs = valid[sy]
        for x in range(size[0]):
            sx = xs[round((len(xs) - 1) * x / max(1, size[0] - 1))]
            texture.putpixel((x, y), source.getpixel((sx, sy)))
    return texture


def _wikipedia_canvas(layer_info, fields):
    """Composite transparent patterns onto their declared fabric colour.

    Commons layers often contain invisible black RGB and are 59 pixels tall,
    not 100. Discarding alpha or pasting without resizing invents black panels
    and a white lower shirt. Neither is present in the historical source.
    """
    canvas = legacy_renderer.Image.new("RGB", (100, 100))
    specs = (("left_arm", (0, 0), (31, 100), "leftarm1"),
             ("body", (31, 0), (38, 100), "body1"),
             ("right_arm", (69, 0), (31, 100), "rightarm1"))
    for part, xy, size, colour_field in specs:
        base = legacy_renderer.Image.new("RGBA", size, tuple(bytes.fromhex(str(fields[colour_field]))) + (255,))
        layer = (layer_info.get("layers") or {}).get(part)
        if layer:
            base = _pattern_texture(layer['path'], tuple(bytes.fromhex(str(fields[colour_field]))), size, part).convert('RGBA')
        canvas.paste(base.convert("RGB"), xy)
    return canvas


def _wikipedia_payload(
    record: Any,
    layer_info: Mapping[str, Any],
    fields: Mapping[str, str],
    palette: list[tuple[int, int, int]],
    nearest_cache: dict[tuple[int, int, int], int] | None = None,
    template: Any = None,
    canvas_override: Any = None,
) -> bytes:
    canvas = canvas_override if canvas_override is not None else _wikipedia_canvas(layer_info, fields)
    if template is not None:
        native = factory_tone_renderer.hem_renderer.boundary_renderer
        if (record.width, record.height) != (template.width, template.height):
            raise KitRenderError("factory template dimensions do not fit Wikipedia kit")
        rows = native.recipe_renderer.record_to_top_down_indices(template)
        mask = [[index != 0 for index in row] for row in rows]
        top, waist = native._shirt_top_and_waist(mask)
        hems = factory_tone_renderer.hem_renderer._hem_by_column(mask, waist)
        regions = native._smoothed_native_regions(rows, palette, mask, top, waist)
        profiles = factory_tone_renderer._tone_profiles(rows, palette, mask, regions, hems, "solid")
        reference_y = top + round(.75 * (waist - top))
        body_left, body_right = native._row_bounds(mask, reference_y)
        body_width = max(1, body_right - body_left)
        body_center = (body_left + body_right) / 2
        shorts = tuple(bytes.fromhex(str(fields['shorts1'])))
        output = [list(row) for row in rows]
        for y, row in enumerate(rows):
            for x, index in enumerate(row):
                if not index or native._is_neutral_dark_structure(palette[index]):
                    continue
                hem = hems[x]
                # A single sheared fabric plane, not a different scale for
                # every silhouette row/column. The old map bent straight
                # stripes into waves and displaced hoops at the curved hem.
                center = body_center - .28 * (y - reference_y)
                fraction = (x - center) / body_width + .5
                if fraction < 0 and y < top + .48 * (waist - top):
                    sx = round(30 * max(0, 1 + fraction))
                elif fraction > 1 and y < top + .48 * (waist - top):
                    sx = 69 + round(30 * min(1, fraction - 1))
                else:
                    sx = 31 + round(37 * max(0, min(1, fraction)))
                colour = shorts if y > hem else canvas.getpixel((max(0, min(99, sx)),
                    max(0, min(99, round(99 * (y - top) / max(1, waist - top))))))
                key = ("shorts", None) if y > hem else ("shirt", None)
                shaded = factory_tone_renderer._transfer_tone(colour, native._luminance(palette[index]),
                                                              profiles.get(key, (64., 160., 240.)))
                if native.recipe_renderer.edge_pixel(mask, x, y):
                    shaded = factory_tone_renderer._darken(shaded, .9)
                if y == hem:
                    shaded = factory_tone_renderer._darken(shaded, .58)
                elif y == hem + 1:
                    shaded = factory_tone_renderer._darken(shaded, .82)
                output[y][x] = kit_raster.nearest_nontransparent_palette_index(shaded, palette, nearest_cache)
        canvas.close()
        return native.recipe_renderer.top_down_indices_to_raw(record, output)
    try:
        height = int(record.height)
        shirt_top = int(height * 0.22)
        shirt_bottom = int(height * 0.60)
        source = canvas.resize((int(record.width), shirt_bottom - shirt_top), legacy_renderer.Image.Resampling.LANCZOS)
        return kit_raster.rasterize_preserving_native_shading(
            record,
            palette,
            lambda x, y: tuple(int(value) for value in source.getpixel((x, y - shirt_top))) if shirt_top <= y < shirt_bottom else None,
            nearest_cache=nearest_cache,
        )
    finally:
        canvas.close()


def render_catalogue(
    catalogue: Mapping[str, Any], *, dbdat: Path, output_dir: Path, pattern_cache_dir: Path,
    allow_network: bool = False,
    record_loader: Callable[[Path], dict[int, Any]] | None = None,
    palette_loader: Callable[[Path], tuple[list[tuple[int, int, int]], dict[str, Any]]] | None = None,
    layer_resolver: Callable[[Mapping[str, str], Path, bool], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if catalogue.get("schema_version") != catalogue_v1.SCHEMA:
        raise KitRenderError(f"catalogue must use {catalogue_v1.SCHEMA}")
    rows = catalogue.get("rows")
    if not isinstance(rows, list):
        raise KitRenderError("catalogue rows must be a list")
    load_records = record_loader or _record_index
    archives: dict[str, dict[int, Any]] = {}
    archive_hashes = {}
    for archive in ARCHIVES:
        path = dbdat / archive
        if record_loader is None and not path.is_file():
            raise KitRenderError(f"missing clean base archive: {path}")
        archives[archive] = load_records(path)
        archive_hashes[archive] = sha256_file(path) if path.is_file() else "fixture-injected"
    palette, palette_source = (palette_loader or _palette)(dbdat)
    nearest_cache: dict[tuple[int, int, int], int] = {}
    bindings, receipts = [], []
    season = catalogue.get("season") or {}
    season_slug = str(season.get("label") or "season").replace("/", "-")
    resolve_layers = layer_resolver or (lambda tokens, cache, network: resolve_wikipedia_layers(tokens, cache, allow_network=network))
    for row in sorted(rows, key=lambda value: int(value.get("carrier_id") or 0)):
        carrier = int(row.get("carrier_id") or 0)
        base = {"carrier_id": carrier, "club_name": row.get("club_name"), "catalogue_status": row.get("status")}
        if row.get("status") != "source-ready":
            receipts.append({**base, "status": "not-rendered-catalogue-gap", "reason": row.get("reason")})
            continue
        contract = row.get("render_contract") or {}
        kind = contract.get("kind")
        layers = None
        if kind == "wikipedia-template-fields":
            fields = contract.get("fields") or {}
            if fields.get('pattern_sh1'):
                receipts.append({**base, 'status': 'not-rendered-unsupported-shorts-overlay',
                                 'reason': 'shorts pattern must be rendered, never replaced with its background colour',
                                 'pattern_sh1': fields['pattern_sh1']})
                continue
            tokens = {"body": fields.get("pattern_b1"), "left_arm": fields.get("pattern_la1"), "right_arm": fields.get("pattern_ra1")}
            layers = resolve_layers(tokens, pattern_cache_dir, allow_network)
            if layers.get("status") != "ready":
                receipts.append({**base, "status": "not-rendered-exact-pattern-unavailable", "reason": layers.get("reason"), "pattern_tokens": tokens})
                continue
        elif kind != "reviewed-pm99-style":
            receipts.append({**base, "status": "not-rendered-unsupported-contract", "reason": str(kind)})
            continue
        missing = [archive for archive in ARCHIVES if carrier not in archives[archive]]
        if missing:
            receipts.append({**base, "status": "not-rendered-clean-base-record-missing", "archives": missing})
            continue
        artifacts = []
        for archive in ARCHIVES:
            record = archives[archive][carrier]
            if kind == "wikipedia-template-fields":
                template = archives[archive].get(factory_tone_renderer.factory_template_carrier(archive, {"pattern": "solid"}))
                if template is None:
                    raise KitRenderError(f"{archive} lacks factory template for Wikipedia kit")
                payload = _wikipedia_payload(record, layers, fields, palette, nearest_cache, template=template)
            else:
                style = contract.get("style") or {}
                template_carrier = factory_tone_renderer.factory_template_carrier(archive, style)
                template = archives[archive].get(template_carrier)
                if template is None:
                    raise KitRenderError(
                        f"{archive} lacks V5 factory template carrier {template_carrier}"
                    )
                payload = _reviewed_style_payload(record, template, palette, style)
            path, digest = _write_artifact(payload, output_dir)
            archive_slug = archive.lower().replace(".pkf", "")
            artifacts.append({"id": f"kit-render-{season_slug}-{carrier}-{archive_slug}", "kind": "kit-render", "sha256": digest, "relative_path": str(path.relative_to(output_dir))})
        bindings.append({"carrier_id": carrier, "artifacts": artifacts})
        receipt = {**base, "status": "rendered-source-ready", "contract_kind": kind, "artifacts": artifacts}
        if kind == "reviewed-pm99-style":
            receipt["renderer"] = factory_tone_renderer.RENDERER_ID
        if layers is not None:
            receipt["pattern_layers"] = {part: {"url": value.get("url"), "sha256": value.get("sha256")} for part, value in sorted(layers["layers"].items())}
        receipts.append(receipt)
    catalogue_sha = sha256_bytes(canonical_json_bytes(dict(catalogue)))
    binding = {"schema_version": SCHEMA, "kit_catalogue_sha256": catalogue_sha, "clubs": bindings}
    counts: dict[str, int] = {}
    for row in receipts:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    receipt = {"schema_version": RECEIPT_SCHEMA, "season": dict(season), "kit_catalogue_sha256": catalogue_sha, "policy": {"base": "clean-record-wrapper-and-runtime-palette", "reviewed_style_renderer": factory_tone_renderer.RENDERER_ID, "wikipedia": "exact-captured-template-fields-and-hash-bound-commons-pattern-layers", "football_kit_archive": "manually-reviewed-pm99-style-contract-rendered-through-original-factory-tonal-art", "gaps": "no-artifact-no-binding-no-native-fallback"}, "source": {"dbdat": str(dbdat.resolve()), "archive_sha256": archive_hashes, "palette": palette_source}, "coverage": {"catalogue_club_count": len(rows), "bound_club_count": len(bindings), "artifact_count": sum(len(row["artifacts"]) for row in bindings), "status_counts": dict(sorted(counts.items()))}, "rows": receipts}
    return binding, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--kit-catalogue", type=Path)
    source.add_argument("--catalogue-root", type=Path, help="render every */kit-catalogue-v1.json in sorted order")
    source.add_argument("--english-compiler-input", type=Path, help="project embedded kits onto final assigned mode-0 carriers")
    parser.add_argument("--clean-dbdat", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--pattern-cache-dir", type=Path, required=True)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    compiler_catalogue = catalogue_from_english_compiler_input(json.loads(args.english_compiler_input.read_text(encoding="utf-8"))) if args.english_compiler_input else None
    paths = [args.kit_catalogue] if args.kit_catalogue else (sorted(args.catalogue_root.glob("*/kit-catalogue-v1.json")) if args.catalogue_root else [])
    if not paths and compiler_catalogue is None:
        parser.error("no kit catalogues found")
    summary = {}
    for path in paths or [None]:
        catalogue = compiler_catalogue if path is None else json.loads(path.read_text(encoding="utf-8"))
        season_slug = str((catalogue.get("season") or {}).get("label") or (path.parent.name if path else "season")).replace("/", "-")
        output_dir = args.output_dir if (args.kit_catalogue or compiler_catalogue is not None) else args.output_dir / season_slug
        binding, receipt = render_catalogue(catalogue, dbdat=args.clean_dbdat, output_dir=output_dir, pattern_cache_dir=args.pattern_cache_dir, allow_network=args.allow_network)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "kit-render-bindings-v1.json").write_bytes(canonical_json_bytes(binding))
        (output_dir / "kit-render-receipt-v1.json").write_bytes(canonical_json_bytes(receipt))
        summary[season_slug] = receipt["coverage"]
    print(json.dumps(summary if len(summary) > 1 else next(iter(summary.values())), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
