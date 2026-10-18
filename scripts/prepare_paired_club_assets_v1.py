"""Attach two dated grounds and pixel-only kits to an unregistered squad pair.

This creates a new private candidate; it never modifies installed games or the
source candidate. Source-backed colours are not exact sponsor/pattern artwork.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_kit_render_bindings_v1 as render
from scripts.probe_sourced_factory_kit_v1 import checked_pixel_replacement, kit_image
from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact
from app.editor_actions import _patch_indexed_eq_team_string_payload
from app.bitmap_pixel_rows import bitmap_pixel_ranges
from bs4 import BeautifulSoup

GROUNDS = {
    3323: ('Weymouth', 'Bob Lucas Stadium', 'weymouth-opening-preview.html',
           'https://www.borehamwoodfootballclub.co.uk/match-preview-weymouth-a-3/',
           ('20 August 2021', '21 st August 2021', 'Weymouth v Boreham Wood')),
    3329: ('Wrexham', 'Racecourse Ground', 'wrexham-2021-home-match.html',
           'https://www.wrexhamafcarchive.co.uk/matchdetails.php?id=13720',
           ('Saturday, September 11th, 2021', 'Wrexham 1 - 0 Woking')),
}


def ground_source(cache, carrier, ground_specs=None):
    spec = (GROUNDS if ground_specs is None else ground_specs)[carrier]
    club, ground, name, url, anchors = spec[:5]
    path = cache / name
    receipt = json.loads(path.with_name(name + '.source.json').read_text())
    if receipt.get('url') != url or receipt.get('sha256') != registry.sha256_file(path):
        raise ValueError('ground original URL/SHA mismatch')
    document = BeautifulSoup(path.read_bytes(), 'html.parser')
    # Do not match a navigation link or a current stadium renaming.
    text = document.get_text(' ', strip=True)
    if ground not in text or any(anchor not in text for anchor in anchors):
        raise ValueError('ground original lacks the dated target-club match anchors')
    if len(spec) > 5:
        expected = [' '.join(cell.split()) for cell in spec[5]]
        rows = [[' '.join(cell.get_text(' ', strip=True).split()) for cell in row.select('th,td')]
                for row in document.select('table tr')]
        if (not expected or expected[0] != club or ground not in expected
                or rows.count(expected) != 1):
            raise ValueError('ground season table lacks one exact target-club row')
    proof = {'club': club, 'ground': ground, 'url': url, 'sha256': receipt['sha256'],
             'dated_match_anchors': list(anchors)}
    if len(spec) > 5:
        proof['exact_season_table_row'] = expected
    return path, proof


def candidate_club_scope(candidate, receipt):
    """Use the existing asset stage for either private composition shape."""
    from scripts import season_owned_club_composition_v1 as retained
    if receipt.get('schema_version') != retained.PRIVATE_SCHEMA:
        return {m['carrier_id'] for m in receipt['managers']}
    base = registry.load_registered_release(receipt['season'], receipt['source_release_id'])
    retained.verify_materialised(base, candidate)
    path = candidate / receipt['transaction_artifact']
    if registry.sha256_file(path) != receipt['transaction_sha256']:
        raise ValueError('retained asset transaction changed')
    transaction = pipeline.read_json_file(path)
    return {transaction['whole_club_proposal']['before_club']['carrier_id']}


def pixel_payload(record, payload):
    from app.minifoto_bitmap_archive import validate_minifoto_bitmap
    shape = validate_minifoto_bitmap(payload)
    if (shape.width, shape.height, shape.bits_per_pixel) != (record.width, record.height, 8):
        raise ValueError('rendered kit dimensions differ from target')
    start = record.pixel_offset
    size = record.width * record.height
    # Renderer uses the exact factory record layout; preserve installed wrapper.
    if len(payload) != len(record.raw_bitmap) or shape.pixel_offset != record.pixel_offset:
        raise ValueError('rendered kit layout differs from target')
    result = bytearray(record.raw_bitmap)
    for lo, hi in bitmap_pixel_ranges(record):
        result[lo:hi] = payload[lo:hi]
    return checked_pixel_replacement(record, bytes(result))


def comparison_sheet_size(club_count):
    if club_count < 1:
        raise ValueError('comparison sheet needs at least one club')
    return 320 * club_count, 560


def prepare(candidate, assets, output, *, ground_specs=None):
    if output.exists():
        raise ValueError('asset candidate is immutable')
    if output.resolve().is_relative_to(candidate.resolve()) or candidate.resolve().is_relative_to(output.resolve()):
        raise ValueError('asset output overlaps protected source candidate')
    receipt = json.loads((candidate / 'candidate-receipt.json').read_text())
    if receipt['registered'] or receipt['publication_authorised']:
        raise ValueError('assets require the exact unpublished target-season pair')
    specs=GROUNDS if ground_specs is None else ground_specs
    package = json.loads((candidate / 'season-package.json').read_text())
    clubs = {c['carrier_id']: c for c in package['clubs']}
    if candidate_club_scope(candidate, receipt) != set(specs):
        raise ValueError('ground/kit scope differs from the complete source transaction')
    for carrier, (name, *_rest) in specs.items():
        if clubs[carrier]['name'] != name:
            raise ValueError('replacement kit/ground carrier identity differs')
    bindings = json.loads((assets / 'render-bindings.json').read_text())
    catalogue = json.loads((assets / 'kit-catalogue.json').read_text())
    if catalogue['season']['label'].replace('/','-') != receipt['season']:
        raise ValueError('kit catalogue describes another target season')
    catalogue_hash = render.sha256_bytes(render.canonical_json_bytes(catalogue))
    rendered = json.loads((assets / 'render-receipt.json').read_text())
    if (bindings['kit_catalogue_sha256'] != catalogue_hash or
            rendered['kit_catalogue_sha256'] != catalogue_hash or
            {r['carrier_id'] for r in bindings['clubs']} != set(specs)):
        raise ValueError('kit source/render bindings differ from the complete pair')
    for row in catalogue['rows']:
        if row['club_name'] != clubs[row['carrier_id']]['name'] or row['status'] != 'source-ready':
            raise ValueError('kit catalogue does not bind the replaced club')
    for a in package['artifacts']:
        if a.get('relative_path'):
            verify_recipe_artifact(candidate / a['relative_path'], a['sha256'])
    grounds = {carrier: ground_source(assets / 'source-cache', carrier, specs) for carrier in specs}
    files = {name: (candidate / 'game/DBDAT' / name).read_bytes() for name in render.ARCHIVES}
    new_files = {name: bytearray(raw) for name, raw in files.items()}
    indices = {name: render._record_index(candidate / 'game/DBDAT' / name) for name in render.ARCHIVES}
    changes = []; copied = {}
    result = copy.deepcopy(package)
    palette, palette_source = render._palette(candidate / 'game/DBDAT')
    for row in bindings['clubs']:
        carrier = row['carrier_id']
        if len(row['artifacts']) != 3:
            raise ValueError('every replacement needs all three compact kit sizes')
        for archive in render.ARCHIVES:
            matches = [a for a in row['artifacts'] if a['id'].endswith('-' + archive[:-4].lower())]
            if len(matches) != 1:
                raise ValueError('kit binding has duplicate/missing size')
            artifact = copy.deepcopy(matches[0]); source = assets / 'renders' / artifact['relative_path']
            if registry.sha256_file(source) != artifact['sha256']:
                raise ValueError('rendered kit original changed')
            record = indices[archive][carrier]; payload = pixel_payload(record, source.read_bytes())
            start = record.bitmap_offset
            new_files[archive][start:start + record.bitmap_length] = payload
            copied[Path(artifact['relative_path'])] = source
            result['artifacts'] = [a for a in result['artifacts'] if a['id'] != artifact['id']] + [artifact]
            changes.append({'archive': archive, 'carrier_id': carrier,
                            'bitmap_before_sha256': render.sha256_bytes(record.raw_bitmap),
                            'bitmap_after_sha256': render.sha256_bytes(payload),
                            'only_pixel_lane_changed': True})
        kit = next(k for k in result['assets']['kits'] if k['club_id'] == clubs[carrier]['id'])
        proof_id = f'paired-kit-source-{receipt["season"]}-{carrier}'
        kit.update(policy='write', artifact_ids=[a['id'] for a in row['artifacts']],
                   proof={'artifact_id': proof_id, 'grade': 'reviewed-editorial'})
        source_row = next(r for r in catalogue['rows'] if r['carrier_id'] == carrier)
        # Store the complete source/render limitation, not an exact-artwork claim.
        document = {'catalogue_row': source_row, 'render_row': next(r for r in rendered['rows'] if r['carrier_id'] == carrier)}
        relative = Path(f'kit-source-{carrier}.json')
        result['artifacts'].append({'id': proof_id, 'kind': 'season-input', 'relative_path': str(relative),
                                   'sha256': render.sha256_bytes(pipeline.canonical_json_bytes(document) + b'\n')})
        copied[relative] = document
    for archive, after in new_files.items():
        intervals = [(indices[archive][c].bitmap_offset + lo, indices[archive][c].bitmap_offset + hi)
                     for c in specs for lo, hi in bitmap_pixel_ranges(indices[archive][c])]
        if len(after) != len(files[archive]) or any(
                not any(lo <= i < hi for lo, hi in intervals)
                for i, (a, b) in enumerate(zip(files[archive], after)) if a != b):
            raise ValueError('kit stage touched another club or archive wrapper')
    eq_before = (candidate / 'game/DBDAT/EQ98030.FDI').read_bytes()
    index = native.IndexedFDIFile.from_bytes(eq_before); patches = {}; ground_changes = []
    for carrier, (path, proof) in grounds.items():
        entry = next(e for e in index.entries if e.record_id == carrier)
        after, changed = _patch_indexed_eq_team_string_payload(entry.decode_payload(eq_before), stadium_name=proof['ground'])
        if set(changed) != {'stadium'}:
            raise ValueError('ground stage must change the inherited ground only')
        patches[carrier] = after
        club = next(c for c in result['clubs'] if c['carrier_id'] == carrier)
        club.update(ground_policy='write', ground_name=proof['ground'])
        relative = Path(f'ground-original-{carrier}.html'); copied[relative] = path
        result['artifacts'].append({'id': f'paired-ground-source-{receipt["season"]}-{carrier}', 'kind': 'season-input',
                                   'relative_path': str(relative), 'sha256': proof['sha256']})
        ground_changes.append({'carrier_id': carrier, 'native_before': changed['stadium'][0], **proof})
    eq_after = native.delta.compiler._rebuild_indexed(eq_before, index, patches)
    native.preserve_other_records(eq_before, eq_after, set(specs))
    result['artifacts'].sort(key=lambda a: a['id']); native.package_v2.validate_package(result)
    needed = len(eq_after) + sum(len(raw) for raw in new_files.values()) + 64 * 1024**2
    if shutil.disk_usage(candidate).free - needed < 8 * 1024**3:
        raise ValueError('asset stage would cross the unchanged 8-GiB reserve')
    output.mkdir(parents=True)
    shutil.copytree(candidate / 'game', output / 'game', copy_function=os.link)
    for path in candidate.rglob('*'):
        relative = path.relative_to(candidate)
        if path.is_file() and relative.parts[0] != 'game' and relative not in (Path('candidate-receipt.json'), Path('season-package.json')):
            target = output / relative; target.parent.mkdir(parents=True, exist_ok=True); os.link(path, target)
    for name, raw in {'EQ98030.FDI': eq_after, **new_files}.items():
        temporary = output / (name + '.partial'); temporary.write_bytes(raw); os.replace(temporary, output / 'game/DBDAT' / name)
    for relative, source in copied.items():
        target = output / relative; target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(source, dict): pipeline.write_canonical_json(target, source)
        else: os.link(source, target)
    pipeline.write_canonical_json(output / 'season-package.json', result)
    for artifact in result['artifacts']:
        if artifact.get('relative_path'): verify_recipe_artifact(output / artifact['relative_path'], artifact['sha256'])
    from PIL import Image, ImageDraw
    sheet = Image.new('RGB', comparison_sheet_size(len(specs)), '#25313a'); draw = ImageDraw.Draw(sheet)
    for col, carrier in enumerate(sorted(specs)):
        draw.text((col * 320 + 10, 8), clubs[carrier]['name'], fill='white')
        for row, archive in enumerate(render.ARCHIVES):
            before = indices[archive][carrier]; after = render._record_index(output / 'game/DBDAT' / archive)[carrier]
            sheet.paste(kit_image(before, palette), (col * 320 + 10, row * 170 + 40))
            sheet.paste(kit_image(after, palette), (col * 320 + 170, row * 170 + 40))
            draw.text((col * 320 + 10, row * 170 + 24), archive + ' inherited / corrected', fill='white')
    sheet.save(output / 'kit-comparison.png')
    updated = copy.deepcopy(receipt)
    updated.update(source_native_candidate={'path': registry.relative_workspace_path(candidate),
                       'sha256': registry.sha256_file(candidate / 'candidate-receipt.json')},
                   native_hashes={name: registry.sha256_file(output / 'game/DBDAT' / name)
                       for name in (*receipt['native_hashes'], *render.ARCHIVES)},
                   package_sha256=registry.sha256_file(output / 'season-package.json'),
                   paired_asset_stage={'grounds': ground_changes, 'kit_pixel_changes': changes,
                       'runtime_palette': palette_source, 'exact_sponsor_pattern_artwork': False},
                   remaining=['actual runner rosters and kits', 'mode1 deployment not historically proven',
                              'no-new-duplicate audit', 'normal release publication'])
    pipeline.write_canonical_json(output / 'candidate-receipt.json', updated)
    return updated


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('candidate', 'assets', 'output'): p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--ground-specs',type=Path,help='Explicit per-carrier dated original ground bindings')
    a = p.parse_args();specs=None
    if a.ground_specs is not None:
        specs={int(k):v for k,v in json.loads(a.ground_specs.read_text()).items()}
    r = prepare(a.candidate, a.assets, a.output,ground_specs=specs)
    print(json.dumps({'private_asset_candidate': str(a.output),
        'grounds':len(r['paired_asset_stage']['grounds']),
        'kit_records':len(r['paired_asset_stage']['kit_pixel_changes']),'registered':False}),flush=True)
