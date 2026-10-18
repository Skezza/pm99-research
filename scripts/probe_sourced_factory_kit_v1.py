#!/usr/bin/env python3
"""Build minimal runner inputs for one historically sourced factory-style kit.

Not a full local game copy. Runner supplies its verified installation; these
inputs preserve every database byte and replace only three target kit BMPs.
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_kit_render_bindings_v1 as renderer
from scripts import season_release_registry_v1 as registry
from scripts.season_portrait_pipeline_v1 import _normalise_name
from scripts import season_visual_patch_v1 as visual
from scripts import season_pipeline_v2 as pipeline
from app.minifoto_bitmap_archive import validate_minifoto_bitmap
from app.bitmap_pixel_rows import bitmap_pixel_ranges


def run(season, club, output):
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    catalogue_path = ROOT / '.local/season-kit-sources-historical-backfill-v1' / season / 'kit-catalogue-v1.json'
    catalogue = json.loads(catalogue_path.read_text())
    sources = [r for r in catalogue['rows'] if _normalise_name(r['club_name']) == _normalise_name(club) and r['status'] == 'source-ready']
    if len(sources) != 1:
        raise ValueError('no unique dated source-ready club')
    source = sources[0]
    carrier = int(source['carrier_id'])
    clubs = [c for c in package['clubs'] if int(c['carrier_id']) == carrier]
    if len(clubs) != 1 or _normalise_name(clubs[0]['name']) != _normalise_name(club):
        raise ValueError('kit source and recipe carrier identity disagree')
    fields = source['render_contract']['fields']
    cache = ROOT / '.local/season-kit-evidence-cache-v1/factory-patterns'
    layers = renderer.resolve_wikipedia_layers({'body': fields['pattern_b1'],
                'left_arm': fields['pattern_la1'], 'right_arm': fields['pattern_ra1']}, cache, allow_network=True)
    if layers['status'] != 'ready':
        raise ValueError('exact historical pattern is unavailable: ' + str(layers))
    if output.exists():
        raise ValueError('probe output already exists')
    dbdat = output / 'game/DBDAT'
    dbdat.mkdir(parents=True)
    names = ['MANAGPRE.EXE', 'DAT.PKF', *['DBDAT/' + n for n in (
        'JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF',
        'MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF', 'BIGESC.PKF', 'BIGCAMP.PKF')]]
    for name in names:
        shutil.copyfile(release.game_path / name, output / 'game' / name)
    palette, palette_source = renderer._palette(release.game_path / 'DBDAT')
    sheet = Image.new('RGB', (720, 600), '#18212a')
    draw = ImageDraw.Draw(sheet)
    changes = []
    for index, name in enumerate(renderer.ARCHIVES):
        path = dbdat / name
        original = path.read_bytes()
        record = renderer._record_index(path)[carrier]
        templates = renderer._record_index(ROOT / '.local/season-pipeline-v2/pm99-base-clean/DBDAT' / name)
        template = templates[renderer.factory_tone_renderer.factory_template_carrier(name, {'pattern': 'solid'})]
        payload = renderer._wikipedia_payload(record, layers, fields, palette, template=template)
        after = bytearray(original)
        start = record.bitmap_offset
        after[start:start + record.bitmap_length] = payload
        changed = [i for i, (a, b) in enumerate(zip(original, after)) if a != b]
        permitted = {start + i for lo, hi in bitmap_pixel_ranges(record) for i in range(lo, hi)}
        if len(after) != len(original) or any(i not in permitted for i in changed):
            raise ValueError('kit correction changed bytes outside target pixels')
        path.write_bytes(after)
        readback = renderer._record_index(path)[carrier]
        if readback.raw_bitmap != payload:
            raise ValueError('rendered kit readback failed')
        for col, item in enumerate((record, readback, template)):
            rows = renderer.reviewed_renderer.record_to_top_down_indices(item)
            image = Image.new('RGB', (item.width, item.height))
            image.putdata([palette[p] for row in rows for p in row])
            image.thumbnail((170, 150), Image.Resampling.NEAREST)
            factor = max(1, min(170 // item.width, 150 // item.height))
            image = image.resize((item.width * factor, item.height * factor), Image.Resampling.NEAREST)
            sheet.paste(image, (col * 240 + 20, index * 200 + 30))
            draw.text((col * 240 + 10, index * 200 + 10), ['Inherited artwork', 'Sourced correction', 'Factory template'][col], fill='white')
            draw.text((col * 240 + 10, index * 200 + 180), name, fill='white')
        changes.append({'archive': name, 'carrier_id': carrier, 'archive_before_sha256': renderer.sha256_bytes(original),
                        'archive_after_sha256': renderer.sha256_file(path), 'changed_pixel_bytes': len(changed),
                        'original_bitmap_sha256': renderer.sha256_bytes(record.raw_bitmap),
                        'corrected_bitmap_sha256': renderer.sha256_bytes(payload), 'template_carrier': 4,
                        'template_bitmap_sha256': renderer.sha256_bytes(template.raw_bitmap)})
    sheet.save(output / 'factory-comparison.png')
    receipt = {'schema_version': 'pm99-sourced-factory-kit-probe-v1', 'season': season, 'club': club,
               'source': source, 'catalogue_sha256': registry.sha256_file(catalogue_path),
               'pattern_layers': layers, 'runtime_palette': palette_source, 'changes': changes,
               'input_hashes': {name: registry.sha256_file(output / 'game' / name) for name in names},
               'scope': 'Minimal runner overlay, not a standalone playable local game or all-season kit certification.'}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


def checked_pixel_replacement(record, payload):
    """Refuse incompatible headers, transparency, or non-pixel alterations."""
    shape = validate_minifoto_bitmap(payload)
    if (shape.width, shape.height, shape.bits_per_pixel, len(payload)) != (
            record.width, record.height, 8, len(record.raw_bitmap)):
        raise ValueError('candidate bitmap does not fit current archive record')
    allowed = {i for start, end in bitmap_pixel_ranges(record) for i in range(start, end)}
    if any(a != b for i, (a, b) in enumerate(zip(payload, record.raw_bitmap)) if i not in allowed):
        raise ValueError('candidate changes the native bitmap wrapper')
    return payload


def kit_image(record, palette, scale=2):
    rows = renderer.reviewed_renderer.record_to_top_down_indices(record)
    image = Image.new('RGB', (record.width, record.height), '#25313a')
    image.putdata([palette[index] if index else (37, 49, 58) for row in rows for index in row])
    return image.resize((record.width * scale, record.height * scale), Image.Resampling.NEAREST)


def prepare_batch(season, catalogue_path, render_root, output, exclusions=(), *, source_release=None):
    """Prepare three compact archives and source comparison sheets, no game copy.

    Every changed carrier must be identity-bound to the current recipe and all
    candidate/source hashes checked. Missing sources remain explicit gaps.
    Human/vision review is still required before applying this patch.
    """
    release = source_release if source_release is not None else registry.load_preferred_release(season)
    if release.season != season:
        raise ValueError('kit source release belongs to another season')
    package = json.loads(release.package_path.read_text())
    catalogue = json.loads(catalogue_path.read_text())
    if catalogue['season']['label'].replace('/', '-') != season:
        raise ValueError('catalogue belongs to another season')
    binding_path = render_root / 'kit-render-bindings-v1.json'
    binding = json.loads(binding_path.read_text())
    render_receipt_path = render_root / 'kit-render-receipt-v1.json'
    render_receipt = json.loads(render_receipt_path.read_text())
    digest = renderer.sha256_bytes(renderer.canonical_json_bytes(catalogue))
    if binding['kit_catalogue_sha256'] != digest or render_receipt['kit_catalogue_sha256'] != digest:
        raise ValueError('rendered candidates do not match the captured catalogue')
    if output.exists():
        raise ValueError('batch output already exists')
    clubs = {int(c['carrier_id']): c for c in package['clubs']}
    source_rows = {int(r['carrier_id']): r for r in catalogue['rows']}
    palette, palette_source = renderer._palette(release.game_path / 'DBDAT')
    originals = {name: (release.game_path / 'DBDAT' / name).read_bytes() for name in renderer.ARCHIVES}
    changed = {name: bytearray(value) for name, value in originals.items()}
    records = {name: renderer._record_index(release.game_path / 'DBDAT' / name) for name in renderer.ARCHIVES}
    render_rows = {int(r['carrier_id']): r for r in render_receipt['rows']}
    events, pictures, report_rows, skipped = [], [], [], []
    used_carriers = set()
    for row in binding['clubs']:
        source_carrier = int(row['carrier_id'])
        source = source_rows[source_carrier]
        if _normalise_name(source['club_name']) in {_normalise_name(n) for n in exclusions}:
            skipped.append({'source_carrier_id': source_carrier, 'club': source['club_name'],
                            'reason': 'explicit-visual-review-exclusion'})
            continue
        matches = [c for c in clubs.values() if _normalise_name(c['name']) == _normalise_name(source['club_name'])]
        original_club = clubs.get(source_carrier)
        if original_club and _normalise_name(original_club['name']) == _normalise_name(source['club_name']):
            club, carrier = original_club, source_carrier
        elif len(matches) == 1:
            club, carrier = matches[0], int(matches[0]['carrier_id'])
        else:
            skipped.append({'source_carrier_id': source_carrier, 'club': source['club_name'],
                            'reason': 'no-unique-current-club-source-binding',
                            'current_source_carrier_club': original_club.get('name') if original_club else None,
                            'matching_current_carriers': [c['carrier_id'] for c in matches]})
            continue
        if carrier in used_carriers:
            raise ValueError('duplicate source assignment to current carrier')
        used_carriers.add(carrier)
        if source['status'] != 'source-ready' or len(row['artifacts']) != 3:
            raise ValueError('incomplete or unapproved candidate kit')
        panel = []
        for artifact, name in zip(row['artifacts'], renderer.ARCHIVES):
            if artifact['id'] != f"kit-render-{season}-{source_carrier}-{name.lower().replace('.pkf', '')}":
                raise ValueError('candidate archive order or identity is invalid')
            path = render_root / artifact['relative_path']
            path.resolve().relative_to(render_root.resolve())
            if registry.sha256_file(path) != artifact['sha256']:
                raise ValueError('candidate bitmap changed')
            record = records[name][carrier]
            candidate = path.read_bytes()
            shape = validate_minifoto_bitmap(candidate)
            if (shape.width, shape.height, shape.bits_per_pixel) != (record.width, record.height, 8):
                raise ValueError('source kit cannot be rebound to current record shape')
            # Catalogues can predate later carrier allocation. Bind by unique
            # club identity, then transfer ONLY pixels into the live wrapper.
            payload = bytearray(record.raw_bitmap)
            if len(candidate) != len(record.raw_bitmap) or shape.pixel_offset != record.pixel_offset:
                raise ValueError('source kit cannot be rebound to current record row layout')
            for lo, hi in bitmap_pixel_ranges(record):
                payload[lo:hi] = candidate[lo:hi]
            payload = checked_pixel_replacement(record, bytes(payload))
            if name == 'MINIESC.PKF':
                from dataclasses import replace
                panel = [kit_image(record, palette), kit_image(replace(record, raw_bitmap=payload), palette)]
            start = record.bitmap_offset
            changed[name][start:start + record.bitmap_length] = payload
            events.append({'archive': name, 'carrier_id': carrier, 'club': club['name'],
                'source_carrier_id': source_carrier, 'before_bitmap_sha256': renderer.sha256_bytes(record.raw_bitmap),
                'after_bitmap_sha256': renderer.sha256_bytes(payload),
                'pixel_lanes': [[start + lo, start + hi] for lo, hi in bitmap_pixel_ranges(record)]})
        report_rows.append({'carrier_id': carrier, 'source_carrier_id': source_carrier,
                            'club': club['name'], 'source': source['source'],
                            'render_contract': source['render_contract'], 'pattern_layers': render_rows[source_carrier].get('pattern_layers'),
                            'result': 'source-bound-candidate-not-yet-visually-approved'})
        pictures.append((club['name'], carrier, panel))
    output.mkdir(parents=True)
    outputs = {}
    for name in renderer.ARCHIVES:
        allowed = [lane for e in events if e['archive'] == name for lane in e['pixel_lanes']]
        changed_offsets = [i for i, (a, b) in enumerate(zip(originals[name], changed[name])) if a != b]
        if len(changed[name]) != len(originals[name]) or any(not any(a <= i < b for a, b in allowed) for i in changed_offsets):
            raise ValueError('batch changed bytes outside approved carrier pixel lanes')
        path = output / 'patch/DBDAT' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(changed[name])
        readback = renderer._record_index(path)
        if any(renderer.sha256_bytes(readback[e['carrier_id']].raw_bitmap) != e['after_bitmap_sha256'] for e in events if e['archive'] == name):
            raise ValueError('batch archive readback failed')
        outputs['DBDAT/' + name] = registry.sha256_file(path)
    sheets = []
    for offset in range(0, len(pictures), 12):
        entries = pictures[offset:offset + 12]
        sheet = Image.new('RGB', (900, 4 * 190), '#18212a')
        draw = ImageDraw.Draw(sheet)
        for index, (club, carrier, panel) in enumerate(entries):
            x, y = (index % 3) * 300, (index // 3) * 190
            draw.text((x + 5, y + 4), f'{carrier} {club}'[:42], fill='white')
            draw.text((x + 8, y + 24), 'Installed       Candidate', fill='#b9d5f0')
            sheet.paste(panel[0], (x + 10, y + 44))
            sheet.paste(panel[1], (x + 135, y + 44))
        path = output / f'kit-comparison-{offset // 12 + 1:02d}.png'
        sheet.save(path)
        sheets.append({'path': str(path), 'sha256': registry.sha256_file(path)})
    plan = {'schema_version': visual.SCHEMA, 'season': season,
            'inputs': {'release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
                       'catalogue_sha256': registry.sha256_file(catalogue_path),
                       'render_binding_sha256': registry.sha256_file(binding_path)},
            'no_photo': [], 'replacements': []}
    pipeline.write_canonical_json(output / 'plan.json', plan)
    receipt = {'schema_version': 'pm99-season-visual-patch-materialisation-v1', 'season': season,
               'plan_sha256': registry.sha256_file(output / 'plan.json'),
               'archive_before_sha256': registry.sha256_file(release.game_path / 'DBDAT/MINIFOTO.PKF'),
               'kit_before_sha256s': {'DBDAT/' + name: renderer.sha256_bytes(value) for name, value in originals.items()},
               'outputs': outputs, 'replacements': [], 'no_photo_count': 0,
               'catalogue_sha256': registry.sha256_file(catalogue_path), 'events': events,
               'clubs': report_rows, 'skipped': skipped, 'sheets': sheets, 'visual_review': 'pending',
               'scope': 'Source-bound compact kit candidates; no database changes or full game copies.'}
    pipeline.write_canonical_json(output / 'patch/receipt.json', receipt)
    return {'clubs': len(pictures), 'skipped': skipped, 'archives': 3, 'sheets': sheets}


def audit_legacy_2015(output):
    """Inspect ALL installed source-backed foreign kits without copying a game."""
    if output.exists():
        raise ValueError('audit output already exists')
    release = registry.load_preferred_release('2015-16')
    source = ROOT / '.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v5-native-tone-transfer.json'
    materialisation = json.loads(source.read_text())
    package = json.loads(release.package_path.read_text())
    clubs = {int(c['carrier_id']): c for c in package['clubs']}
    palette, palette_source = renderer._palette(release.game_path / 'DBDAT')
    records = {name: renderer._record_index(release.game_path / 'DBDAT' / name) for name in renderer.ARCHIVES}
    report, pictures = [], []
    for row in materialisation['rows']:
        if not row['status'].startswith('release-eligible-'):
            continue
        carrier = int(row['carrier_id'])
        club = clubs[carrier]
        failures = []
        if _normalise_name(club['name']) != _normalise_name(row['source_club_name']):
            failures.append('source-and-current-recipe-club-name-disagree')
        for name in renderer.ARCHIVES:
            record = records[name][carrier]
            validate_minifoto_bitmap(record.raw_bitmap)
            if renderer.sha256_bytes(record.raw_bitmap) != row['assets'][name]['sha256']:
                failures.append('installed-bitmap-differs-from-bound-source-render:' + name)
        source_image = row.get('source_image') or {}
        path = Path(source_image.get('cache_path') or '')
        if path.is_file() and registry.sha256_file(path) == source_image.get('sha256'):
            with Image.open(path) as opened:
                image = opened.convert('RGBA')
                image.thumbnail((80, 110), Image.Resampling.LANCZOS)
                source_panel = Image.new('RGBA', image.size, 'white')
                source_panel.alpha_composite(image)
                source_panel = source_panel.convert('RGB')
        else:
            source_panel = Image.new('RGB', (80, 100), '#25313a')
            ImageDraw.Draw(source_panel).text((2, 20), 'Reviewed\nstyle only' if 'reviewed' in row['status'] else 'Source\nunavailable', fill='white')
            if 'reviewed' not in row['status']:
                failures.append('source-image-unavailable-or-hash-mismatch')
        report.append({'carrier_id': carrier, 'club': club['name'], 'source_status': row['status'],
                       'source': source_image, 'render_recipe': row.get('render_recipe'), 'failures': failures})
        pictures.append((club['name'], carrier, source_panel, kit_image(records['MINIESC.PKF'][carrier], palette)))
    output.mkdir(parents=True)
    sheets = []
    for offset in range(0, len(pictures), 48):
        sheet = Image.new('RGB', (1600, 1200), '#18212a')
        draw = ImageDraw.Draw(sheet)
        for index, (club, carrier, source_panel, current) in enumerate(pictures[offset:offset + 48]):
            x, y = (index % 8) * 200, (index // 8) * 200
            draw.text((x + 2, y + 4), f'{carrier} {club}'[:29], fill='white')
            draw.text((x + 2, y + 24), 'Source      Installed', fill='#b9d5f0')
            sheet.paste(source_panel, (x + 2, y + 45))
            sheet.paste(current, (x + 92, y + 45))
        path = output / f'source-comparison-{offset // 48 + 1:02d}.png'
        sheet.save(path)
        sheets.append({'path': str(path), 'sha256': registry.sha256_file(path)})
    result = {'schema_version': 'pm99-legacy-source-kit-audit-v1', 'season': '2015-16',
              'release_id': release.release_id, 'source_materialisation_sha256': registry.sha256_file(source),
              'package_sha256': registry.sha256_file(release.package_path), 'runtime_palette': palette_source,
              'archive_sha256s': {n: registry.sha256_file(release.game_path / 'DBDAT' / n) for n in renderer.ARCHIVES},
              'clubs_checked': len(report), 'clubs_with_failures': sum(bool(r['failures']) for r in report),
              'native_fallback_clubs_not_certified': len(package['clubs']) - len(report),
              'scope': 'Hash/identity/readback checks plus source comparison sheets, NOT blanket historical certification.',
              'clubs': report, 'sheets': sheets}
    pipeline.write_canonical_json(output / 'report.json', result)
    return {k: v for k, v in result.items() if k not in {'clubs', 'sheets'}}


def record_legacy_visual_findings(output):
    """Retain concrete source-vs-installed observations, not a fabricated pass."""
    defects = {
        8: 'diagonal red sash missing', 204: 'contrasting chest band missing',
        220: 'black vertical panels lost', 404: 'chest band misclassified as hoops',
        412: 'white base/red chest band misclassified as red/white hoops',
        502: 'diagonal red/white split missing', 503: 'white chevron missing',
        509: 'orange diagonal panel missing', 602: 'checkerboard lost', 617: 'checkerboard lost',
        801: 'single red centre panel turned into multiple stripes', 802: 'red/white halves turned into stripes',
        804: 'diagonal red/white split lost', 812: 'three-colour stripes simplified to two colours',
        817: 'red/green halves turned into stripes', 851: 'single white chest band turned into hoops',
        866: 'white chest band missing', 867: 'blue/white chest band missing',
        956: 'single blue centre panel turned into stripes', 1002: 'claret/blue halves turned into sleeves',
        1003: 'orange/claret halves turned into stripes', 1005: 'checker/gradient simplified into stripes',
        1008: 'contrasting navy upper panel/sleeves missing', 1058: 'blue/claret halves turned into stripes',
        1059: 'black upper panel missing', 1101: 'blue/white halves lost',
        1104: 'blue/red halves lost', 1107: 'single red centre panel turned into stripes',
        1161: 'blue/white quarter/panel structure turned into stripes',
    }
    report_path = output / 'report.json'
    report = json.loads(report_path.read_text())
    clubs = {r['carrier_id']: r for r in report['clubs']}
    findings = [{'carrier_id': carrier, 'club': clubs[carrier]['club'], 'observation': defect,
                 'source_image_sha256': clubs[carrier]['source'].get('sha256'),
                 'source_url': clubs[carrier]['source'].get('origin_url'),
                 'current_recipe': clubs[carrier]['render_recipe'], 'status': 'open-geometry-correction'}
                for carrier, defect in sorted(defects.items())]
    result = {'schema_version': 'pm99-source-kit-visual-findings-v1', 'season': '2015-16',
              'audit_sha256': registry.sha256_file(report_path), 'release_id': report['release_id'],
              'reviewed_comparison_sheets': report['sheets'], 'confirmed_pattern_findings': len(findings),
              'policy': 'Unlisted kits are not automatically certified. Sources show shirts, not independently verified shorts.',
              'findings': findings}
    pipeline.write_canonical_json(output / 'visual-findings.json', result)
    return {'confirmed_pattern_findings': len(findings), 'status': 'open-not-fixed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--club')
    parser.add_argument('--audit-legacy-2015', action='store_true')
    parser.add_argument('--record-legacy-findings', action='store_true')
    parser.add_argument('--batch-catalogue', type=Path)
    parser.add_argument('--render-root', type=Path)
    parser.add_argument('--exclude-club', action='append', default=[], help='exclude an explicitly reviewed questionable candidate')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.record_legacy_findings:
        if args.season != '2015-16' or args.club or args.batch_catalogue or args.audit_legacy_2015:
            parser.error('record findings requires an existing 2015-16 source audit')
        print(json.dumps(record_legacy_visual_findings(args.output)))
    elif args.audit_legacy_2015:
        if args.season != '2015-16' or args.club or args.batch_catalogue:
            parser.error('legacy audit is only for 2015-16 without rendering options')
        print(json.dumps(audit_legacy_2015(args.output)))
    elif args.batch_catalogue:
        if args.club or not args.render_root:
            parser.error('batch catalogue requires --render-root and no --club')
        print(json.dumps(prepare_batch(args.season, args.batch_catalogue, args.render_root, args.output, args.exclude_club)))
    else:
        if not args.club:
            parser.error('provide --club or --batch-catalogue')
        result = run(args.season, args.club, args.output)
        print(json.dumps({'club': result['club'], 'archives_corrected': len(result['changes'])}))
