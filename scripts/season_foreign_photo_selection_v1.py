#!/usr/bin/env python3
"""Dated, source-labelled real-photo selections across the registered seasons.

This is a bounded photographic expansion, NOT a claim of complete worldwide
photo coverage. Uncertain identity/date/framing is logged, never illustrated
with a modern retired-player photograph. All requests and crops are cached.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

import cv2
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_portrait_pipeline_v1 as portrait
from scripts import season_release_registry_v1 as registry
from scripts import season_visual_patch_v1 as art
from scripts import season_historical_photo_qa_v1 as qa
from scripts.season_historical_photo_pilot_v1 import norm
from scripts.pm99_kit_palette_v1 import runtime_kit_palette

API = 'https://commons.wikimedia.org/w/api.php'
UA = {'User-Agent': 'PlayPM99/1.0 (historical football research; https://playpm99.com)'}
STARS = [('Zinedine Zidane', '1972-06-23'), ('Ronaldo Nazario', '1976-09-22'),
         ('Cristiano Ronaldo', '1985-02-05'), ('Lionel Messi', '1987-06-24'),
         ('Marko Arnautovic', '1989-04-19'), ('Lamine Yamal', '2007-07-13'),
         ('Andres Iniesta', '1984-05-11'), ('Xavi Hernandez', '1980-01-25'),
         ('Thierry Henry', '1977-08-17'), ('David Beckham', '1975-05-02'),
         ('Ronaldinho', '1980-03-21'), ('Gianluigi Buffon', '1978-01-28'),
         ('Paolo Maldini', '1968-06-26'), ('Raul Gonzalez', '1977-06-27'),
         ('Luis Figo', '1972-11-04'), ('Robert Lewandowski', '1988-08-21'),
         ('Kylian Mbappe', '1998-12-20'), ('Erling Haaland', '2000-07-21')]
STARS += [('Dennis Bergkamp', '1969-05-10'), ('Roberto Carlos', '1973-04-10')]
POLICY_VERSION = 'football-face-v4'
FORMAL_CONTEXT = re.compile(r'\b(amiri|suit|tuxedo|red carpet|gala|fashion|blazer|award ceremony|ballon d.or)\b', re.I)
FOOTBALL_CONTEXT = re.compile(r'\b(vs?|training|match|warm.?up|premier league|uefa|champions league|world cup|maillot|trikot|football kit|soccer jersey)\b', re.I)
REJECTED_TITLES = {'File:Lamine Yamal (2025) (cropped).png': 'reviewed-formalwear',
                  'File:Roberto Carlos Sosa.jpg': 'different-full-name',
                  'File:Mbappe Messi Neymar (cropped).jpg': 'ambiguous-group-caption'}


def taken_year(meta, title):
    """Never mistake the upload/revision date for the photograph's date."""
    original = meta.get('DateTimeOriginal', {})
    if original.get('value'):
        value = re.sub('<[^>]+>', '', original['value'])
        years = re.findall(r'\b(?:19|20)\d{2}\b', value)
        if len(set(years)) == 1 and not re.search(r'upload|revision', value, re.I):
            return int(years[0]), 'DateTimeOriginal', value
    description = re.sub('<[^>]+>', '', meta.get('ImageDescription', {}).get('value', ''))
    years = re.findall(r'\b(?:19|20)\d{2}\b', description)
    if len(set(years)) == 1:
        return int(years[0]), 'source-caption-declared-year', description
    # Titles with an explicit shooting year are a weaker, clearly labelled
    # date source; never use the MediaWiki file timestamp as a replacement.
    years = re.findall(r'\b(?:19|20)\d{2}\b', title.replace('_', ' '))
    if len(set(years)) == 1:
        return int(years[0]), 'source-file-title-declared-year', title
    return None, None, None


def identity_title(name, title):
    tokens = set(norm(title).split())
    expected = set(norm(name).split())
    if name == 'Xavi Hernandez':
        return 'xavi' in tokens and ('hernandez' in tokens or len(tokens) <= 5)
    if name == 'Ronaldo Nazario':
        return 'ronaldo' in tokens and 'cristiano' not in tokens and (
            'nazario' in tokens or title in ('File:Salvaronaldo.jpg', 'File:Ronaldo 2002 cropped.jpg'))
    return norm(name) in norm(title)


def discover(name, year, root):
    key = hashlib.sha256(f'{name}:{year}:v1'.encode()).hexdigest()
    path = root / 'discovery' / (key + '.json')
    if path.exists(): return json.loads(path.read_text())
    query_name = 'Ronaldo -Cristiano -pdf' if name == 'Ronaldo Nazario' else name
    queries = [f'{query_name} {year}', f'{query_name} {year-1}', f'{query_name} {year+1}']
    pages = {}
    for query in queries:
        response = requests.get(API, params={'action': 'query', 'generator': 'search',
            'gsrsearch': query, 'gsrnamespace': 6, 'gsrlimit': 20, 'prop': 'imageinfo',
            'iiprop': 'url|extmetadata', 'iiurlwidth': 640, 'format': 'json', 'formatversion': 2},
            headers=UA, timeout=25)
        response.raise_for_status()
        for page in response.json().get('query', {}).get('pages', []): pages[page['pageid']] = page
        time.sleep(.35)
    path.parent.mkdir(parents=True, exist_ok=True)
    art.save(path, {'name': name, 'year': year, 'queries': queries, 'pages': list(pages.values())})
    return json.loads(path.read_text())


def candidates(discovery, name, year, maximum=10):
    found = []
    for page in discovery['pages']:
        title = page['title']
        if title in REJECTED_TITLES or not re.search(r'\.(jpg|jpeg|png|webp)$', title, re.I): continue
        if re.search(r'\b(and|with|alongside|junto|et)\b', title, re.I): continue
        info = (page.get('imageinfo') or [{}])[0]
        meta = info.get('extmetadata', {})
        description = re.sub('<[^>]+>', '', meta.get('ImageDescription', {}).get('value', ''))
        context = title + ' ' + description + ' ' + meta.get('Categories', {}).get('value', '')
        if FORMAL_CONTEXT.search(context): continue
        labelled_surname = (norm(name) in norm(description) and norm(name).split()[-1] in norm(title).split()
                            and not re.search(r'\b(and|with|alongside|junto|et)\b', title, re.I))
        if not identity_title(name, title) and not labelled_surname: continue
        if re.search(r'\b(statue|sculpture|bust|wax|caricature|drawing|painting|bronze|estatua|escultura|candidato|prefeito|vereador)\b',
                     title + ' ' + description, re.I): continue
        if title == 'File:Raúl Rojas González.jpg': continue
        taken, basis, declaration = taken_year(meta, title)
        title_years = {int(y) for y in re.findall(r'\b(?:19|20)\d{2}\b', title.replace('_', ' '))}
        if taken is not None and title_years and min(abs(taken-y) for y in title_years) > 1: continue
        licence = meta.get('LicenseShortName', {}).get('value')
        licence_url = meta.get('LicenseUrl', {}).get('value')
        if taken is None or not year - 2 <= taken <= year + 1 or not licence or not licence_url: continue
        found.append({'title': title, 'photo_year': taken, 'date_basis': basis, 'date_declaration': declaration,
                      'image_url': info.get('thumburl') or info.get('url'), 'source_page': info.get('descriptionurl'),
                      'licence': licence, 'licence_url': licence_url,
                      'football_context': 'source-declared' if FOOTBALL_CONTEXT.search(context) else 'requires-visual-review',
                      'artist': re.sub('<[^>]+>', '', meta.get('Artist', {}).get('value', ''))})
    return sorted(found, key=lambda r: (r['football_context'] != 'source-declared', abs(r['photo_year'] - year), r['title']))[:maximum]


def face_view(face):
    """Framing heuristic from YuNet landmarks, not identity/biometric recognition."""
    width = float(face[2])
    ex1, ey1, ex2, ey2, nx, ny = map(float, face[4:10])
    separation = abs(ex2 - ex1)
    eye_ratio = separation / max(width, 1)
    nose_offset = abs(nx - (ex1 + ex2) / 2) / max(separation, 1)
    passed = eye_ratio >= .24 and nose_offset <= .65
    return {'passed': passed, 'eye_separation_ratio': round(eye_ratio, 3),
            'nose_offset_ratio': round(nose_offset, 3),
            'reason': 'front-or-mild-angle' if passed else 'strong-profile-or-uncertain-landmarks'}


def prominent_faces(detected):
    """Ignore tiny crowd faces, never choose between two foreground people."""
    return [face for face in detected if min(face[2:4]) >= 40]


def bounded_tight_crop(photo, face):
    """Keep a complete face in a narrow source portrait without inventing pixels."""
    x, y, width, height = map(float, face[:4])
    if x < 0 or y < 0 or x + width > photo.shape[1] or y + height > photo.shape[0]:
        return None
    side = min(max(width, height) * 1.65, photo.shape[0], photo.shape[1])
    if side < max(width, height) * 1.08: return None
    left = max(0, min(photo.shape[1] - side, x + width / 2 - side / 2))
    top = max(0, min(photo.shape[0] - side, y + height * .56 - side * .43))
    if left > x or top > y or left + side < x + width or top + side < y + height: return None
    return Image.fromarray(cv2.cvtColor(photo, cv2.COLOR_BGR2RGB)).crop(
        (round(left), round(top), round(left + side), round(top + side)))


def process(season, root, detector, maximum, *, cache_root=None, overrides=None, only_overrides=False, targets=None):
    cache_root = cache_root or root
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    players = package['players']
    clubs = portrait._club_by_player(package)
    selected = []
    requested = STARS if targets is None else targets
    for name, dob in requested:
        if only_overrides and name not in (overrides or {}): continue
        matches = [p for p in players if p.get('facts', {}).get('birth_date') == dob and (
            portrait._name_score(p['name'], name, name)[0] >= 70 or
            norm(p['name']).split()[-1:] == norm(name).split()[-1:] or
            norm(p['name']).split()[-1:] == norm(name).split()[:1] or
            (name == 'Ronaldo Nazario' and 'ronaldo' in norm(p['name']).split()) or
            (name == 'Xavi Hernandez' and 'xavi' in norm(p['name']).split()) or
            (name == 'Andres Iniesta' and 'iniesta' in norm(p['name']).split()) or
            (name == 'Lionel Messi' and 'messi' in norm(p['name']).split()))]
        if len(matches) == 1: selected.append((name, matches[0]))
    target = root / season
    parameters = {'maximum_per_season': maximum, 'only_overrides': only_overrides,
                  'overrides_sha256': hashlib.sha256(json.dumps(overrides or {}, sort_keys=True,
                                                               separators=(',', ':')).encode()).hexdigest()}
    if targets is not None:
        parameters['requested_players'] = [[name, dob] for name, dob in targets]
    if (target / 'selection.json').is_file():
        cached = json.loads((target / 'selection.json').read_text())
        if (cached.get('policy_version') != POLICY_VERSION or cached['package_sha256'] != art.sha(release.package_path)
                or cached.get('selection_parameters') != parameters):
            raise ValueError('retained selection has another policy/recipe; use a new output root')
        return cached
    target.mkdir(parents=True, exist_ok=True)
    records = list(portrait.iter_minifoto_records(release.game_path / 'DBDAT/MINIFOTO.PKF'))
    template = records[0]
    palette, palette_source = runtime_kit_palette(release.game_path / 'DBDAT')
    palette_source['sha256'] = art.sha(Path(palette_source['path']))
    palette_image = portrait._build_palette_image(palette)
    outcomes = []
    for source_name, player in selected[:maximum]:
        if shutil.disk_usage(ROOT).free < 600 * 1024**2:
            raise ValueError('photo capture reached the 600 MiB disk reserve')
        row = {'name': player['name'], 'source_name': source_name, 'birth_date': player['facts']['birth_date'],
               'carrier_id': player['carrier_id'], 'club': clubs.get(player['id']), 'status': 'no-approved-photo', 'attempts': []}
        try:
            preferred = (overrides or {}).get(source_name)
            if preferred and not only_overrides:
                year = int(season[:4])
                if not year - 2 <= int(preferred['photo_date'][:4]) <= year + 1:
                    preferred = None
            search_year = int(preferred['photo_date'][:4]) if preferred else int(season[:4])
            discovery = discover(source_name, search_year, cache_root)
            choices = candidates(discovery, source_name, int(season[:4]), maximum=None if preferred else 10)
            if preferred:
                choices = [c for c in choices if c['title'] == preferred['title']]
                if not choices: raise ValueError('approved source missing or outside period/identity/licence rules')
            for candidate in choices:
                attempt = dict(candidate)
                try:
                    raw = qa.photo_bytes(candidate['image_url'], cache_root / 'source-cache')
                    photo = qa.decode(raw)
                    all_faces = qa.faces(detector, photo)
                    detected = prominent_faces(all_faces)
                    if len(detected) != 1:
                        attempt['reason'] = 'requires-one-face-at-least-40px'; row['attempts'].append(attempt); continue
                    view = face_view(detected[0])
                    if not view['passed']:
                        attempt['reason'] = view['reason']; row['attempts'].append(attempt); continue
                    crop = bounded_tight_crop(photo, detected[0])
                    if crop is None:
                        attempt['reason'] = 'face-too-close-to-edge'; row['attempts'].append(attempt); continue
                    bitmap, _, preview = portrait._build_replacement_bitmap(raw_bitmap_template=template.raw_bitmap,
                        pixel_offset=template.pixel_offset, width=template.width, height=template.height,
                        source_image=crop, palette_image=palette_image, palette_rgb=palette,
                        allowed_indices=list(range(len(palette))))
                    portrait.validate_minifoto_bitmap(bitmap)
                    base = f"J96{int(player['carrier_id']):05d}"
                    for folder in ['crops', 'previews', 'patch/DBDAT/MINIFOTO']: (target / folder).mkdir(parents=True, exist_ok=True)
                    crop_path = target / 'crops' / (base + '.png'); crop.save(crop_path)
                    preview_path = target / 'previews' / (base + '.png'); preview.save(preview_path)
                    bitmap_path = target / 'patch/DBDAT/MINIFOTO' / (base + '.BMP'); bitmap_path.write_bytes(bitmap)
                    row.update(status='source-and-framing-pass', source=candidate,
                               face_view=view, source_cache_root=str((cache_root / 'source-cache').resolve()),
                               palette_source=palette_source,
                               source_sha256=qa.sha(raw), crop_path=str(crop_path.resolve()),
                               preview_path=str(preview_path.resolve()), bitmap_path=str(bitmap_path.resolve()),
                               bitmap_sha256=qa.sha(bitmap), face_count=1,
                               background_face_count=len(all_faces) - len(detected),
                               face_pixels=round(float(min(detected[0][2:4])), 1),
                               identity_policy='unique recipe name/DOB; source-title identity; not biometric certification')
                    row['attempts'].append({**attempt, 'reason': 'source-and-framing-pass'}); break
                except Exception as exc:
                    row['attempts'].append({**attempt, 'reason': type(exc).__name__ + ':' + str(exc)[:120]})
        except Exception as exc:
            row['discovery_error'] = type(exc).__name__ + ':' + str(exc)[:150]
        outcomes.append(row)
        print(json.dumps({'season': season, 'name': source_name, 'status': row['status']}), flush=True)
    result = {'schema_version': 'pm99-cross-season-photo-selection-v1', 'season': season,
              'policy_version': POLICY_VERSION,
              'selection_parameters': parameters,
              'release_id': release.release_id, 'package_sha256': art.sha(release.package_path),
              'policy': 'dated real photographs, -2/+1 year window; missing is not approval; no database edits',
              'players': outcomes, 'accepted': sum(r['status'] == 'source-and-framing-pass' for r in outcomes)}
    art.save(target / 'selection.json', result)
    return result


def sheet(root, results):
    tiles = []
    for result in results:
        accepted = [p for p in result['players'] if p['status'] == 'source-and-framing-pass']
        # Keep a full 26-season grid. A visible missing tile is more honest
        # than silently displaying another season's photograph.
        chosen = accepted or [{'name': 'No approved period photograph', 'status': 'missing'}]
        for p in chosen:
            tile = Image.new('RGB', (260, 210), '#202833'); d = ImageDraw.Draw(tile)
            if p['status'] != 'missing':
                tile.paste(Image.open(p['crop_path']).convert('RGB').resize((140, 140)), (4, 4))
                tile.paste(Image.open(p['preview_path']).convert('RGB').resize((96, 96), Image.Resampling.NEAREST), (155, 25))
            d.text((5, 151), result['season'] + ' ' + p['name'][:28], fill='white')
            d.text((5, 169), str(p.get('club') or '')[:36], fill='#c8d8e8')
            d.text((5, 188), 'Photo: ' + str(p.get('source', {}).get('photo_year', 'missing')), fill='#c8d8e8')
            tiles.append(tile)
    paths = []
    for start in range(0, len(tiles), 20):
        part = tiles[start:start+20]; canvas = Image.new('RGB', (1040, ((len(part)+3)//4)*210), '#121820')
        for i, tile in enumerate(part): canvas.paste(tile, ((i % 4)*260, (i//4)*210))
        path = root / f'foreign-photo-selection-{start//20+1:02d}.png'; canvas.save(path); paths.append(str(path))
    return paths


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--season', default='all')
    parser.add_argument('--maximum-per-season', type=int, default=10)
    parser.add_argument('--cache-root', type=Path)
    parser.add_argument('--source-overrides', type=Path)
    parser.add_argument('--only-overrides', action='store_true')
    args = parser.parse_args()
    cv2.setNumThreads(1)
    model = ROOT / '.local/season-historical-photo-pilots-v1/shared/face_detection_yunet_2023mar.onnx'
    detector = cv2.FaceDetectorYN_create(str(model), '', (320, 320), score_threshold=.8)
    overrides = json.loads(args.source_overrides.read_text())['players'] if args.source_overrides else None
    results = [process(s, args.output_root, detector, args.maximum_per_season,
                       cache_root=args.cache_root, overrides=overrides, only_overrides=args.only_overrides)
               for s in registry.supported_seasons() if args.season in ('all', s)]
    print(json.dumps({'seasons': len(results), 'accepted': sum(r['accepted'] for r in results),
                      'sheets': sheet(args.output_root, results)}))
