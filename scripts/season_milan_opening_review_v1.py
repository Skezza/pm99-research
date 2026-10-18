"""Source-bound review of Milan's actual 2000/01 opening XI, not publication."""
import json
import re
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

from scripts import season_atalanta_opening_review_v1 as reviewed
from scripts import season_italian_opening_dates_v2 as dates
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_within_club_reserve_repair_v1 as roster

XI = [2510, 2683, 2685, 2687, 3153, 2691, 2813, 2686, 4051, 4053, 4055]
SHEET_NAMES = ['Abbiati', 'Chamot', 'Costacurta', 'P. Maldini', 'Gattuso',
               'Albertini', 'Ambrosini', 'Coco', 'Leonardo', 'Bierhoff', 'Shevchenko']
PDF_SHA = 'b78ec6ce2d0ab07527fd42c7833e4b7c7a79f4ee611c9853e2ac2596d1331859'


def archive_sheet(raw):
    text = BeautifulSoup(raw, 'lxml').get_text(' ', strip=True)
    marker = 'MILAN vs VICENZA'
    if text.count(marker) != 1:
        raise ValueError('opening match is ambiguous')
    block = text[text.index(marker):]
    if not re.search(r'^MILAN vs VICENZA\s+2-0', block):
        raise ValueError('opening match score differs')
    sheet = re.search(r'MILAN\s*:\s*(.*?)\s*- All\.: Zaccheroni', block)
    if not sheet:
        raise ValueError('actual opening lineup missing')
    names = [re.sub(r'\s*\([^)]*\)', '', n).strip() for n in sheet[1].split(',')]
    if names != SHEET_NAMES:
        raise ValueError('published opening starters differ')
    return names


def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(c))


def prepare(release=None):
    release = release or registry.load_preferred_release('2000-01')
    root = registry.ROOT / '.local/opening-xi-repairs-20261008'
    source_dir = root / 'milan-source-review'
    preflight_path = root / 'italian-preflight/current-native-preflight.json'
    preflight = json.loads(preflight_path.read_text())
    old = next(c for c in preflight['clubs'] if c['season'] == '2000-01')
    if release.season != '2000-01' or release.release_id != old['release_id']:
        raise ValueError('review requires explicit original registered baseline')
    for name, sha in old['game_files_before'].items():
        if registry.sha256_file(release.game_path / name) != sha:
            raise ValueError('reviewed native preimage changed')
    package = json.loads(release.package_path.read_text())
    if registry.sha256_file(release.package_path) != old['package_sha256']:
        raise ValueError('reviewed package changed')
    pdf = source_dir / 'la-stampa-original.pdf'
    if registry.sha256_file(pdf) != PDF_SHA:
        raise ValueError('visually reviewed contemporary scan changed')
    archive = root / 'italian-preflight/sources/milan-2000-01-match-archive.html'
    names = archive_sheet(archive.read_bytes())
    results = root / 'italian-preflight/sources/2000-01-I1.csv'
    fixture = dates.first_fixture(results.read_bytes(), '2000-01', 'Milan',
                                  url='https://www.football-data.co.uk/mmz4281/0001/I1.csv')
    if fixture['fixture'] != {'home': 'Milan', 'away': 'Vicenza',
                              'date': '2000-10-01', 'competition_code': 'I1'}:
        raise ValueError('first fixture differs')
    club = next(c for c in package['clubs'] if c['carrier_id'] == 201)
    capture, annual_proof = roster.annual_capture('2000-01', club)
    players = {p['carrier_id']: p for p in package['players']}
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    identities = []
    for carrier, sheet_name in zip(XI, names):
        p = players[carrier]
        source_name = p.get('source_name') or p['name']
        matches = [r for r in capture['players'] if r['name'] == source_name]
        native = roster.native_facts(jug, carrier)
        if (len(matches) != 1 or native['birth_date'] != matches[0]['birth_date']
                or native['position'] != matches[0]['position']):
            raise ValueError('starter source/native birthday or broad role differs')
        identities.append({'carrier_id': carrier, 'player_id': p['id'],
                           'sheet_name': sheet_name, 'source': matches[0], 'native': native})
    removals, bindings = [], [pdf, archive, results, preflight_path]
    for carrier, file, title in [(4075, 'andre-cruz', 'André Cruz'),
                                 (4293, 'maini', 'Giampiero Maini'),
                                 (4316, 'morfeo', 'Domenico Morfeo'),
                                 (8408, 'lehmann', 'Jens Lehmann'),
                                 (14652, 'iannuzzi', 'Alessandro Iannuzzi')]:
        path = source_dir / (file + '-wikipedia.html')
        biography = reviewed.biography(path.read_bytes(), title)
        native = roster.native_facts(jug, carrier)
        if biography['birth_date'] != native['birth_date']:
            raise ValueError('stale link identity birthday differs')
        milan = [s for s in biography['senior_career'] if s['club'] in ('Milan', 'AC Milan')
                 and s['start_year'] <= 2000 <= s['end_year']]
        if carrier == 14652:
            if not milan or not any(s['club'] == 'Monza' and s['loan']
                                   and s['start_year'] == 2000 and s['end_year'] == 2001
                                   for s in biography['senior_career']):
                raise ValueError('Iannuzzi parent-club/Monza loan review differs')
            basis = 'reviewed Monza 2000/01 loan plus Milan annual/actual fixture absence; not exact loan-date proof'
        else:
            if milan:
                raise ValueError('career still includes Milan in opening year')
            basis = 'reviewed ended Milan career plus annual/actual first-fixture absence; not exact transfer-date proof'
        removals.append({'carrier_id': carrier, 'basis': basis, 'biography': biography,
                         'native': native, 'exact_transfer_date_claimed': False})
        bindings.append(path)
    a, b = roster.native_facts(jug, 4493), roster.native_facts(jug, 14958)
    source_giunti = next(r for r in capture['players'] if r['name'] == 'Federico Giunti')
    if a['name'] != b['name'] or a['birth_date'] != b['birth_date'] or a['birth_date'] != source_giunti['birth_date']:
        raise ValueError('Giunti duplicate identity differs')
    removals.append({'carrier_id': 4493, 'retained_carrier_id': 14958,
                     'basis': 'same full native name/DOB, one annual Federico Giunti; preserve shared record at other club'})
    leonardo_path = source_dir / 'leonardo-wikipedia.html'
    biography = reviewed.biography(leonardo_path.read_bytes(), 'Leonardo Araújo')
    a, b = roster.native_facts(jug, 7278), roster.native_facts(jug, 4051)
    if (biography['birth_date'] != a['birth_date'] or a['birth_date'] != b['birth_date']
            or plain(a['name']) != 'leonardo nascimento de araujo'
            or not any(plain(n) == 'leonardo nascimento de araujo' for n in biography['full_names'])):
        raise ValueError('Leonardo full/sporting-name identity bridge differs')
    bindings.append(leonardo_path)
    removals.append({'carrier_id': 7278, 'retained_carrier_id': 4051,
                     'basis': 'reviewed Leonardo sporting/full-name alias and exact DOB; duplicate Milan link',
                     'biography': biography, 'native': a})
    return {'season': '2000-01', 'club_carrier_id': 201,
            'source_release_id': release.release_id, 'source_package_sha256': old['package_sha256'],
            'first_fixture': fixture['fixture'], 'annual_proof': annual_proof,
            'approved_XI_identities': identities, 'reviewed_link_removals': removals,
            'source_bindings': [{'local_path': str(p.relative_to(registry.ROOT)),
                                 'sha256': registry.sha256_file(p)} for p in bindings],
            'contemporary_visual_review': {'source': 'La Stampa, 2 October 2000, page 30',
              'sha256': PDF_SHA, 'actual_XI': names, 'published_formation': '3-4-3',
              'method': 'visual reading of retained scan; not OCR'},
            'unresolved': ['Opening reserve membership not certified',
              '25527 Guglielminpietro vs24060 DOB/role discrepancy remains outside this XI repair',
              'Kaladze appears in annual list but is a midseason arrival; reserve queue remains'],
            'reserve_opening_membership_approved': False, 'publishable': False, 'registered': False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    pipeline.write_canonical_json(args.output, prepare())
