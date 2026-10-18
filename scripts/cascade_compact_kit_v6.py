#!/usr/bin/env python3
"""Re-render every generated TEAM RATING icon from its existing source contract.

Native fallbacks are byte-preserved. Unknown or stale source bindings stop
publication rather than silently replacing newer artwork. This is an asset
patch, not a database rebuild, and uses the existing recoverable transaction.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'upstream/pm99-skezmod-db-editor'))

from PIL import Image
from scripts import apply_post1999_factory_kit_v5_overlay as old_overlay
from scripts import pm99_factory_kit_renderer_v6 as factory
from scripts import season_art_transaction_v1 as transaction
from scripts import season_kit_render_bindings_v1 as renderer
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as visual
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json
from scripts.probe_sourced_factory_kit_v1 import checked_pixel_replacement
from scripts.repair_2015_sourced_kit_geometry_v1 import source_canvas

ARCHIVE = 'NANOESC.PKF'
BASE = ROOT / '.local/season-pipeline-v2/pm99-base-clean/DBDAT'
OUTPUT = ROOT / '.local/compact-kit-v6'
CACHE = ROOT / '.local/season-kit-evidence-cache-v1/factory-patterns'
WORLD = ROOT / '.local/season-pipeline-v2/world-2015-combined-kit-materialisation-factory-template-v5-native-tone-transfer.json'
LEGACY_ENGLISH_DISPLAY_ALIASES = {
    'Man City': 'Manchester City', 'West Brom': 'West Bromwich Albion',
    'Man Utd': 'Manchester United', 'MK Dons': 'Milton Keynes Dons',
    'Sheff Wed': 'Sheffield Wednesday', 'Nottm Forest': 'Nottingham Forest',
    'QPR': 'Queens Park Rangers', 'Brighton': 'Brighton & Hove Albion',
    'Wolves': 'Wolverhampton Wanderers', 'Sheff Utd': 'Sheffield United',
    'Dag & Red': 'Dagenham & Redbridge',
}
# The registered original V6 receipt predates the explicit padded-row suffix.
# Its bytes are recognised only through the same complete immutable audit chain;
# recognising its source contracts does NOT certify them as current rendering.
SUPPORTED_INSTALLED_RENDERERS = {
    'pm99-factory-template-kit-v6-scale-aware-patterns', factory.RENDERER_ID,
}


def read(path):
    return json.loads(path.read_text())


def installed_contracts(season):
    """Recognise installed V6 bytes only through their registered audit chain."""
    release = registry.load_preferred_release(season)
    relative = release.locator.get('kit_patch_application_path')
    if not relative:
        return {}
    application_path = ROOT / relative
    application_path.resolve().relative_to(ROOT.resolve())
    application = read(application_path)
    material_path = application.get('materialisation_path')
    if not material_path:
        return {}
    material_path = Path(material_path)
    material_path.resolve().relative_to(ROOT.resolve())
    if visual.sha(material_path) != application['materialisation_sha256']:
        raise ValueError('installed kit materialisation changed')
    material = read(material_path)
    if not material.get('complete_kit_receipt_path'):
        return {}
    manifest = read(release.release_manifest_path)
    descriptors = [r for r in manifest['external_artifacts'] if r['sha256'] == visual.sha(application_path)]
    if (visual.sha(release.release_manifest_path) != release.manifest_sha256
            or len(descriptors) != 1 or descriptors[0]['size'] != application_path.stat().st_size):
        raise ValueError('installed kit application is not registered')
    complete_path = Path(material['complete_kit_receipt_path'])
    complete_path.resolve().relative_to(ROOT.resolve())
    if visual.sha(complete_path) != material['complete_kit_receipt_sha256']:
        raise ValueError('installed complete kit receipt changed')
    complete = read(complete_path)
    if complete.get('renderer') not in SUPPORTED_INSTALLED_RENDERERS:
        return {}
    audit_path = Path(complete['audit_path'])
    audit_path.resolve().relative_to(ROOT.resolve())
    if visual.sha(audit_path) != complete['audit_sha256']:
        raise ValueError('installed kit audit changed')
    audit = read(audit_path)
    if (audit['season'] != season or audit['blockers'] or audit['all_records'] != 544
            or len(audit['records']) != 544
            or len({r['carrier_id'] for r in audit['records']}) != 544
            or set(complete['archives']) != set(renderer.ARCHIVES)):
        raise ValueError('installed kit audit is incomplete')
    for name, row in complete['archives'].items():
        if name not in renderer.ARCHIVES or visual.sha(release.game_path / 'DBDAT' / name) != row['sha256_after']:
            raise ValueError('installed kit archive differs from its receipt')
    contracts = {}
    for row in audit['records']:
        if row['status'] != 'source-bound-rerendered':
            continue
        source = row['source']
        if visual.sha(Path(source['receipt'])) != source['receipt_sha256']:
            raise ValueError('installed kit source receipt changed')
        if source.get('author_path') and visual.sha(Path(source['author_path'])) != source['author_sha256']:
            raise ValueError('installed kit author input changed')
        contracts[int(row['carrier_id'])] = [{**source, 'expected': row['after_sha256'],
            'installed_audit_sha256': complete['audit_sha256']}]
    return contracts


def source_contracts(season):
    """Return candidates, selected later by CURRENT bitmap hash, not age."""
    contracts = {}

    def add(carrier, expected, club, contract, path, **extra):
        contracts.setdefault(int(carrier), []).append({
            'expected': expected, 'club': club, 'contract': contract,
            'receipt': str(path), 'receipt_sha256': visual.sha(path), **extra})

    if season == '2015-16':
        path = ROOT / 'seasons/2015-16/english-layer/2015-16-english-92-native-kit-receipt.json'
        doc = read(path)
        for row in doc['patched']:
            if row['archive_name'] == ARCHIVE:
                style = doc['styles_by_carrier'][str(row['team_id'])]
                add(row['team_id'], row['bitmap_sha256_after'], style['name'],
                    {'kind': 'reviewed-pm99-style', 'style': style}, path)
        for row in read(WORLD)['rows']:
            asset = row.get('assets', {}).get(ARCHIVE)
            if asset:
                add(row['carrier_id'], asset['sha256'], row['source_club_name'],
                    {'kind': 'reviewed-pm99-style', 'style': row['render_recipe']}, WORLD,
                    source_image=row.get('source_image'))
        path = ROOT / '.local/visual-quality-v1/2015-16/kit-source-projection-r7/patch/receipt.json'
        doc = read(path)
        rows = {int(r['carrier_id']): r for r in doc['clubs']}
        world = {int(r['carrier_id']): r for r in read(WORLD)['rows']}
        for event in doc['events']:
            if event['archive'] == ARCHIVE:
                c = int(event['carrier_id'])
                add(c, event['after_bitmap_sha256'], rows[c]['club'],
                    {'kind': 'source-image-projection',
                     'shorts': world[c]['render_recipe']['shorts']}, path,
                    source_image=rows[c]['source'])
    else:
        revision = old_overlay.REVISIONS[season]
        author = old_overlay._author_input(season, revision)
        catalogue = renderer.catalogue_from_english_compiler_input(read(author))
        rows = {int(r['carrier_id']): r for r in catalogue['rows']}
        path = ROOT / f'.local/season-kit-renders-v1/{season}/source-backed-{revision}-kit-v5/kit-render-bindings-v1.json'
        for row in read(path)['clubs']:
            carrier = int(row['carrier_id'])
            for asset in row['artifacts']:
                if asset['id'].endswith('-nanoesc'):
                    add(carrier, asset['sha256'], rows[carrier]['club_name'],
                        rows[carrier]['render_contract'], path,
                        author_path=str(author), author_sha256=visual.sha(author))
        # Later source-projection patches take precedence only if their bytes
        # are still present. This protects the newer 2014/15 corrections.
        for path in sorted((ROOT / f'.local/visual-quality-v1/{season}').glob('kit-patch*/patch/receipt.json')):
            doc = read(path)
            rows = {int(r['carrier_id']): r for r in doc.get('clubs', [])}
            for event in doc.get('events', []):
                c = int(event['carrier_id'])
                if event['archive'] == ARCHIVE and c in rows:
                    row = rows[c]
                    add(c, event['after_bitmap_sha256'], row['club'], row['render_contract'], path,
                        pattern_layers=row.get('pattern_layers'))
        for path in sorted((ROOT / f'.local/season-visual-patches-v2/{season}').glob('*factory-probe*/receipt.json')):
            doc = read(path)
            for event in doc.get('changes', []):
                if event['archive'] == ARCHIVE:
                    add(event['carrier_id'], event['corrected_bitmap_sha256'], doc['club'],
                        doc['source']['render_contract'], path,
                        pattern_layers=doc.get('pattern_layers', {}).get('layers'))
    for carrier, rows in installed_contracts(season).items():
        contracts.setdefault(carrier, []).extend(rows)
    return contracts


def select_contract(candidates, digest, club):
    matches = [r for r in candidates if r['expected'] == digest]
    if not matches:
        raise ValueError('no existing source receipt matches the current bitmap')
    # Different contracts for the same accepted bytes are ambiguous.
    signatures = {renderer.sha256_bytes(renderer.canonical_json_bytes(r['contract'])) for r in matches}
    if len(signatures) != 1:
        raise ValueError('conflicting source contracts for the current bitmap')
    row = matches[-1]
    if row['club'] != club:
        raise ValueError(f"source club {row['club']!r} does not match recipe club {club!r}")
    return row


def render_bound(record, row, palette, templates):
    source = row.get('source_image')
    if source:
        path = Path(source['cache_path'])
        if visual.sha(path) != source['sha256']:
            raise ValueError('retained source image changed')
    contract = row['contract']
    if contract['kind'] == 'reviewed-pm99-style':
        style = contract['style']
        template = templates[factory.factory_template_carrier(ARCHIVE, style)]
        return factory.render_template_on_record(record, template, palette, style), template
    template = templates[factory.factory_template_carrier(ARCHIVE, {'pattern': 'solid'})]
    if contract['kind'] == 'source-image-projection':
        with Image.open(Path(source['cache_path'])) as image:
            canvas = source_canvas(image)
        fields = {'shorts1': bytes(contract['shorts']).hex()}
        return renderer._wikipedia_payload(record, {}, fields, palette, template=template,
                                           canvas_override=canvas), template
    if contract['kind'] != 'wikipedia-template-fields':
        raise ValueError('unsupported existing kit contract')
    fields = contract['fields']
    if fields.get('pattern_sh1'):
        raise ValueError('shorts source pattern cannot be silently dropped')
    tokens = {'body': fields.get('pattern_b1'), 'left_arm': fields.get('pattern_la1'),
              'right_arm': fields.get('pattern_ra1')}
    layers = renderer.resolve_wikipedia_layers(tokens, CACHE, allow_network=False)
    if layers.get('status') != 'ready':
        # Existing English bindings historically use this alternate cache.
        layers = renderer.resolve_wikipedia_layers(tokens,
            ROOT / '.local/source-cache/wikimedia-kit-patterns-v1', allow_network=False)
    if layers.get('status') != 'ready':
        raise ValueError('exact captured source pattern is unavailable; no network rescrape')
    for part, expected in (row.get('pattern_layers') or {}).items():
        if layers['layers'][part]['sha256'] != expected['sha256']:
            raise ValueError('source pattern hash changed')
    return renderer._wikipedia_payload(record, layers, fields, palette, template=template), template


def validate_pixel_patch(record, template, payload):
    checked_pixel_replacement(record, payload)
    bitmap = factory.hem_renderer.boundary_renderer.recipe_renderer
    before = bitmap.record_to_top_down_indices(template)
    after = bitmap.record_to_top_down_indices(replace(record, raw_bitmap=payload))
    if [[i == 0 for i in r] for r in before] != [[i == 0 for i in r] for r in after]:
        raise ValueError('factory silhouette/transparency changed')
    if payload[record.pixel_offset + record.width * record.height:] != record.raw_bitmap[
            record.pixel_offset + record.width * record.height:]:
        raise ValueError('bitmap suffix changed')


def probe_dbdat(season, output):
    """Small unregistered runner candidate; no copied game or DB rebuild."""
    release = registry.load_preferred_release(season)
    patch = output / 'patch'
    receipt = read(patch / 'receipt.json')
    if visual.sha(patch / 'DBDAT' / ARCHIVE) != receipt['outputs']['DBDAT/' + ARCHIVE]:
        raise ValueError('probe archive changed')
    if visual.sha(release.game_path / 'DBDAT' / ARCHIVE) != receipt['kit_before_sha256s']['DBDAT/' + ARCHIVE]:
        raise ValueError('probe base changed')
    dbdat = output / 'probe/DBDAT'
    if dbdat.exists():
        raise ValueError('probe already exists')
    dbdat.mkdir(parents=True)
    # The route only displays club icons, never external portrait profiles.
    for path in (release.game_path / 'DBDAT').iterdir():
        if path.is_file() and path.name != ARCHIVE:
            (dbdat / path.name).hardlink_to(path)
    (dbdat / ARCHIVE).hardlink_to(patch / 'DBDAT' / ARCHIVE)
    visual.save(output / 'probe/receipt.json', {'diagnostic_only': True, 'season': season,
        'source_release_id': release.release_id, 'candidate_archive_sha256': visual.sha(dbdat / ARCHIVE),
        'database_and_executable_unchanged': True, 'full_game_copied': False})
    return dbdat


def prepare(season, output, *, audit_only=False):
    if not audit_only and output.exists():
        report = output / 'audit.json'
        if (not report.is_file() or not read(report).get('blockers')
                or any(p.name != 'audit.json' and not p.name.startswith('audit.blocked-')
                       for p in output.iterdir())):
            raise ValueError('use a fresh output directory; existing receipts are never overwritten')
        # Keep unsuccessful audits as evidence while retrying only that season.
        report.rename(output / ('audit.blocked-' + visual.sha(report)[:16] + '.json'))
    output.resolve().relative_to(ROOT / '.local')
    release = registry.load_preferred_release(season)
    clubs = {int(c['carrier_id']): c['name'] for c in read(release.package_path)['clubs']}
    if season == '2015-16':
        # This legacy release deliberately composes a separate mode-0 English
        # package with the mode-1 world package; neither contains both layers.
        english = ROOT / 'seasons/2015-16/english-layer/season-package.legacy.json'
        for c in read(english)['clubs']:
            carrier = int(c['carrier_id'])
            if carrier in clubs:
                raise ValueError('English and world kit carriers overlap')
            clubs[carrier] = LEGACY_ENGLISH_DISPLAY_ALIASES.get(c['name'], c['name'])
    source = release.game_path / 'DBDAT' / ARCHIVE
    original = source.read_bytes()
    changed = bytearray(original)
    records = renderer._record_index(source)
    templates = renderer._record_index(BASE / ARCHIVE)
    palette, palette_source = renderer._palette(release.game_path / 'DBDAT')
    contracts = source_contracts(season)
    events, audit, gaps = [], [], []
    for carrier, record in sorted(records.items()):
        digest = renderer.sha256_bytes(record.raw_bitmap)
        result = {'carrier_id': carrier, 'club': clubs.get(carrier), 'before_sha256': digest}
        try:
            if (record.width, record.height) != (24, 32):
                raise ValueError('unexpected TEAM RATING icon dimensions')
            # No guessed recolouring of inherited native artwork.
            if carrier in templates and record.raw_bitmap == templates[carrier].raw_bitmap:
                result.update(status='native-byte-preserved', after_sha256=digest)
            else:
                row = select_contract(contracts.get(carrier, []), digest, clubs.get(carrier))
                payload, template = render_bound(record, row, palette, templates)
                validate_pixel_patch(record, template, payload)
                repeated, _ = render_bound(record, row, palette, templates)
                if payload != repeated:
                    raise ValueError('non-deterministic rendering')
                start = record.bitmap_offset
                changed[start:start + record.bitmap_length] = payload
                after = renderer.sha256_bytes(payload)
                result.update(status='source-bound-rerendered', after_sha256=after,
                              source=row, factory_template_carrier=int(template.file_name[4:8]))
                if after != digest:
                    events.append({'archive': ARCHIVE, 'carrier_id': carrier, 'club': clubs[carrier],
                        'before_bitmap_sha256': digest, 'after_bitmap_sha256': after,
                        'pixel_lane': [start + record.pixel_offset,
                                       start + record.pixel_offset + record.width * record.height]})
        except (ValueError, KeyError, OSError) as exc:
            result.update(status='blocked', error=str(exc))
            gaps.append(result)
        audit.append(result)
    lanes = [e['pixel_lane'] for e in events]
    if len(original) != len(changed) or any(not any(a <= i < b for a, b in lanes)
            for i, (a, b) in enumerate(zip(original, changed)) if a != b):
        raise ValueError('non-pixel archive bytes changed')
    report = {'schema_version': 'pm99-compact-kit-v6-audit-v1', 'season': season,
        'release_id': release.release_id, 'archive': ARCHIVE, 'renderer': factory.RENDERER_ID,
        'palette': palette_source, 'all_records': len(records), 'changed_records': len(events),
        'status_counts': dict(Counter(r['status'] for r in audit)), 'blockers': len(gaps),
        'runtime_verified': False, 'historical_accuracy_certified': False, 'records': audit}
    if audit_only:
        return {k: v for k, v in report.items() if k != 'records'} | {
            'status': 'blocked' if gaps else 'audit-passed', 'gaps': gaps}
    output.mkdir(parents=True, exist_ok=True)
    visual.save(output / 'audit.json', report)
    if gaps:
        return {'season': season, 'status': 'blocked', 'blockers': len(gaps),
                'gaps': gaps, 'audit': str(output / 'audit.json')}
    plan = {'schema_version': visual.SCHEMA, 'season': season,
        'inputs': {'release_id': release.release_id, 'package_sha256': visual.sha(release.package_path),
                   'audit_sha256': visual.sha(output / 'audit.json')},
        'no_photo': [], 'replacements': []}
    visual.save(output / 'plan.json', plan)
    target = output / 'patch/DBDAT' / ARCHIVE
    target.parent.mkdir(parents=True)
    target.write_bytes(changed)
    readback = renderer._record_index(target)
    if set(readback) != set(records) or any(renderer.sha256_bytes(readback[r['carrier_id']].raw_bitmap)
            != r['after_sha256'] for r in audit):
        raise ValueError('complete archive readback failed')
    complete = output / 'complete-kit-receipt.json'
    visual.save(complete, {'schema_version': 'pm99-compact-kit-complete-receipt-v1', 'season': season,
        'archives': {n: {'sha256_after': visual.sha(target if n == ARCHIVE else release.game_path / 'DBDAT' / n)}
                     for n in renderer.ARCHIVES}, 'audit_path': str(output / 'audit.json'),
        'audit_sha256': visual.sha(output / 'audit.json'), 'renderer': factory.RENDERER_ID})
    visual.save(output / 'patch/receipt.json', {
        'schema_version': 'pm99-season-visual-patch-materialisation-v1', 'season': season,
        'plan_sha256': visual.sha(output / 'plan.json'),
        'archive_before_sha256': visual.sha(release.game_path / 'DBDAT/MINIFOTO.PKF'),
        'kit_before_sha256s': {'DBDAT/' + ARCHIVE: visual.sha(source)},
        'outputs': {'DBDAT/' + ARCHIVE: visual.sha(target)}, 'events': events,
        'complete_kit_receipt_path': str(complete), 'complete_kit_receipt_sha256': visual.sha(complete),
        'no_photo_count': 0, 'replacements': []})
    return {'season': season, 'status': 'prepared', 'records': len(records),
            'changed': len(events), 'audit': str(output / 'audit.json')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season', help='YYYY-YY or all')
    parser.add_argument('--output-root', type=Path, default=OUTPUT)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--audit-only', action='store_true', help='check all records without writing patch archives')
    parser.add_argument('--probe', action='store_true', help='create a small unregistered runner candidate')
    parser.add_argument('--report', type=Path, help='persist resumable per-season outcome summaries')
    parser.add_argument('--release-id', default='compact-kit-20261004-r11')
    args = parser.parse_args()
    if args.audit_only and (args.install or args.probe):
        parser.error('--audit-only cannot install or create a probe')
    seasons = registry.supported_seasons() if args.season == 'all' else [args.season]
    failures = 0
    results = []
    for season in seasons:
        output = args.output_root / season
        try:
            if args.audit_only:
                result = prepare(season, output, audit_only=True)
            elif (output / 'patch/receipt.json').exists():
                result = {'season': season, 'status': 'prepared-reused'}
            else:
                result = prepare(season, output)
            if result['status'] == 'blocked':
                failures += 1
            elif args.install:
                current = registry.load_preferred_release(season)
                if current.release_id == args.release_id:
                    validation = registry.validate_preferred_release(season, level='playable')
                    if not validation['valid']:
                        raise ValueError('already installed release failed hash verification')
                    result['installation'] = 'verified-reused'
                else:
                    result['installation'] = transaction.install(output / 'plan.json', output / 'patch',
                        ROOT / f'.local/season-art-transactions-v1/compact-kit-r11/{season}', args.release_id)
            if args.probe and result['status'] != 'blocked':
                result['probe_dbdat'] = str(probe_dbdat(season, output))
        except (ValueError, OSError, registry.RegistryError) as exc:
            result = {'season': season, 'status': 'failed', 'error': str(exc)}
            failures += 1
        print(json.dumps(result), flush=True)
        results.append(result)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            _atomic_replace_json(args.report, {'schema_version': 'pm99-compact-kit-v6-batch-v1',
                'implementation_sha256': visual.sha(Path(__file__)), 'requested_seasons': len(seasons),
                'completed': len(results), 'failures': failures, 'results': results})
    return 2 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
