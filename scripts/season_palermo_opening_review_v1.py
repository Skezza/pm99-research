"""Original Palermo 2005/06 XI identity/link review, never a game writer.

The original first-round report admits exactly one positively named Past Player.
Guardalben's contradictory birth month is logged, not guessed or changed.
Shared-link removals do not authorize changing those persons in other clubs.
"""
import csv
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from scripts import season_atalanta_opening_review_v1 as biographies
from scripts import season_football_data_opening_dates_v1 as dates
from scripts import season_historical_roster_audit_v1 as annual
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_within_club_reserve_repair_v1 as roster

URL = 'https://trivela.com.br/sem-categoria/fichas-completas-da-primeira-rodada-da-serie-a-3/'
XI = [4267, 4571, 4444, 4473, 4584, 8396, 4641, 4652, 4715, 14687, 14677]
LABELS = ['Guardalben', 'Zaccardo', 'Barzagli', 'Terlizzi', 'Grosso', 'Santana',
          'Corini', 'Barone', 'Bonanni', 'Makinwa', 'Caracciolo']


def report(raw):
    page = BeautifulSoup(raw, 'lxml')
    headings, articles = page.select('h1'), page.select('article')
    published = page.select('meta[property="article:published_time"]')
    if (len(headings) != 1 or headings[0].get_text(' ', strip=True) !=
            'Fichas completas da primeira rodada da Série A' or len(articles) != 1
            or len(published) != 1 or published[0].get('content') != '2005-08-30T16:46:00+00:00'):
        raise ValueError('original first-round report identity/publication differs')
    text = ' '.join(articles[0].get_text(' ', strip=True).split())
    matches = re.findall(r'Parma 1×1 Palermo Parma .+? – Técnico: Mario Beretta Palermo '
                         r'(.+?) – Técnico: Luigi del Neri Data: 28/agosto/2005 Estádio: Ennio Tardini', text)
    if len(matches) != 1:
        raise ValueError('one literal Parma/Palermo played fixture is required')
    line = matches[0]
    used = re.findall(r'\(([^(),]+), \d+min\)', line)
    clean = re.sub(r'\([^(),]+, \d+min\)', '', line)
    names = [s.strip() for s in re.split(r';|,| e ', clean)]
    if names != LABELS or len(set(names)) != 11 or used != ['Santoni', 'Brienza', 'Mutarelli']:
        raise ValueError('original eleven starters/used substitutes differ')
    return {'fixture_date': '2005-08-28', 'home': 'Parma', 'away': 'Palermo',
            'starting_xi_names': names, 'used_substitute_names': used,
            'complete_bench_published': False, 'manager': 'Luigi del Neri',
            'name_policy': 'literal published surnames; exact annual identities reviewed separately'}


def guardalben_past_row(raw):
    text = raw.decode('utf-8')
    if text.splitlines()[0].strip() != '=  Palermo - Italian Serie A 2005/06':
        raise ValueError('original Palermo annual title differs')
    sections = text.split('== Past Players')
    if len(sections) != 2:
        raise ValueError('one explicit Past Players section is required')
    rows = list(csv.DictReader([s for s in sections[1].splitlines() if s.strip()], skipinitialspace=True))
    found = [r for r in rows if r.get('Name') == 'Matteo Guardalben']
    if len(found) != 1 or found[0]['Pos'] != 'G' or found[0]['Date of Birth'] != '05-06-74':
        raise ValueError('positively named Guardalben past row differs')
    return {'name': 'Matteo Guardalben', 'birth_date': '1974-06-05', 'position': 'G',
            'shirt_number': 99, 'annual_section': 'Past Players',
            'admission_basis': 'literal keeper in actual first played league XI; no other Past Players admitted'}


def prepare(release=None):
    release = release or registry.load_preferred_release('2005-06')
    if release.season != '2005-06':
        raise ValueError('Palermo review only supports 2005-06')
    root = registry.ROOT / '.local/opening-xi-repairs-20261008'
    source_dir = root / 'palermo-source-review'
    package = json.loads(release.package_path.read_text())
    players = {p['carrier_id']: p for p in package['players']}
    club = next(c for c in package['clubs'] if c['carrier_id'] == 223)
    capture, annual_proof = roster.annual_capture(release.season, club)
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    bindings = {}

    def bind(label, path, url):
        bindings[label] = {'path': registry.relative_workspace_path(path),
                           'sha256': registry.sha256_file(path), 'url': url}
        return path.read_bytes()

    sheet = report(bind('lineup_report', root / 'italian-preflight/sources/palermo-first-round-trivela.html', URL))
    first = dates.first_fixture(bind('league_results', source_dir / '2005-06-I1.csv',
                               'https://www.football-data.co.uk/mmz4281/0506/I1.csv'), release.season, 'I1', 'Palermo')
    if first['fixture'] != {'date': '2005-08-28', 'home': 'Parma', 'away': 'Palermo', 'competition_code': 'I1'}:
        raise ValueError('original complete results first fixture differs')
    past = guardalben_past_row((registry.ROOT / annual_proof['local_path']).read_bytes())
    keeper_bio = biographies.biography(bind('guardalben_biography', source_dir / 'matteo-guardalben-wikipedia.html',
                                           'https://en.wikipedia.org/wiki/Matteo_Guardalben'), 'Matteo Guardalben')
    keeper_sky = BeautifulSoup(bind('guardalben_profile', source_dir / 'matteo-guardalben-sky.html',
                                    'https://www.skysports.com/football/player/54808/matteo-guardalben'), 'lxml').get_text(' ', strip=True)
    if (keeper_bio['birth_date'] != past['birth_date'] or
            'Name: Matteo Guardalben Date of birth: 05/06/1974' not in keeper_sky or
            'Position: Goal Keeper' not in keeper_sky):
        raise ValueError('Guardalben profile corroboration differs')
    approved, conflicts = [], []
    for carrier, label in zip(XI, LABELS):
        player, native = players[carrier], roster.native_facts(jug, carrier)
        name = player.get('source_name') or player['name']
        matches = [p for p in capture['players'] if p['name'] == name]
        if carrier == 4267:
            matches = [past] if name == past['name'] else []
        if (len(matches) != 1 or name.split()[-1] != label or
                annual.normalise(native['name'].split()[-1]) != annual.normalise(label) or
                native['position'] != matches[0]['position'] or
                player['facts'].get('birth_date') != native['birth_date']):
            raise ValueError('source XI identity/broad role/recipe-native birthday differs')
        source = matches[0]
        if native['birth_date'] != source['birth_date']:
            if carrier != 4267 or native['birth_date'] != '1974-05-05':
                raise ValueError('unreviewed starter birthday conflict')
            conflicts.append({'carrier_id': carrier, 'name': name, 'native_birth_date': native['birth_date'],
                              'annual_and_sky_and_wikipedia_birth_date': source['birth_date'],
                              'policy': 'retain native date unchanged; source-backed actual keeper identity does not infer birth-month correction',
                              'resolved': False})
        approved.append({'carrier_id': carrier, 'player_id': player['id'], 'sheet_name': label,
                         'source': source, 'native': native})
    removals = []
    fresi = biographies.biography(bind('fresi_biography', root / 'italian-preflight/sources/salvatore-fresi-wikipedia.html',
                                     'https://en.wikipedia.org/wiki/Salvatore_Fresi'), 'Salvatore Fresi')
    native_fresi = roster.native_facts(jug, 3150)
    if (fresi['birth_date'] != native_fresi['birth_date'] or
            annual.normalise(native_fresi['name']) != annual.normalise('Salvatore Fresi') or
            any(r['club'] == 'Palermo' for r in fresi['senior_career']) or
            any(p['name'] == 'Salvatore Fresi' for p in capture['players'])):
        raise ValueError('Fresi stale-link source review contradicts identity/career/annual')
    removals.append({'carrier_id': 3150, 'person': fresi,
                     'basis': 'reviewed complete senior career plus annual/fixture absence; not exact transfer-date proof'})
    bernardini = biographies.biography(bind('bernardini_biography', source_dir / 'antonino-bernardini-wikipedia.html',
                                           'https://en.wikipedia.org/wiki/Antonino_Bernardini'), 'Antonino Bernardini')
    presentation = BeautifulSoup(bind('bernardini_contemporary_club', source_dir / 'atalanta-2005-presentation.html',
                            'https://www.ecodibergamo.it/stories/sport/al-lazzaretto-lrsquoabbraccio-dei-tifosi-e-lrsquoatalanta-parte-a-caccia-del_48900_11/'), 'lxml')
    published = presentation.select('meta[property="article:published_time"]')
    person = roster.native_facts(jug, 4165)
    if (person['birth_date'] != bernardini['birth_date'] or person['position'] != 'M' or
            annual.normalise(person['name']) != annual.normalise('Antonio Bernardini') or
            len(published) != 1 or published[0].get('content') != '2005-07-15T21:03:00+02:00' or
            'Antonio Bernardini (1974)' not in presentation.get_text(' ', strip=True) or
            any(r['club'] == 'Palermo' for r in bernardini['senior_career']) or
            any(p['name'] in ('Antonio Bernardini', 'Antonino Bernardini') for p in capture['players'])):
        raise ValueError('Bernardini reviewed native/contemporary/career identity differs')
    removals.append({'carrier_id': 4165, 'person': bernardini, 'native_identity': person,
                     'basis': 'reviewed Antonio/Antonino name variant: contemporary Atalanta presentation, exact native DOB, complete career and Palermo annual/fixture absence; no exact transfer-date claim'})
    left, right = roster.native_facts(jug, 4372), roster.native_facts(jug, 15003)
    ted = [p for p in capture['players'] if p['name'] == 'Giovanni Tedesco']
    if (len(ted) != 1 or left['birth_date'] != right['birth_date'] or left['birth_date'] != ted[0]['birth_date'] or
            left['position'] != right['position'] or left['position'] != ted[0]['position'] or
            any((players[c].get('source_name') or players[c]['name']).casefold() != 'giovanni tedesco' for c in (4372, 15003))):
        raise ValueError('shared/exclusive Tedesco duplicate identity differs')
    removals.append({'carrier_id': 4372, 'retained_carrier_id': 15003, 'annual_identity': ted[0],
                     'basis': 'same full source name/native birthday/broad role; remove duplicate Palermo link, retain shared record elsewhere'})
    return {'schema_version': 'pm99-Palermo-original-opening-XI-source-review-v1',
            'season': release.season, 'source_release_id': release.release_id,
            'source_package_sha256': registry.sha256_file(release.package_path),
            'native_input_sha256': {'JUG98030.FDI': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
                                    'EQ98030.FDI': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI')},
            'source_bindings': bindings, 'annual_proof': annual_proof, 'first_fixture': first,
            'original_XI_bench': sheet, 'approved_XI_identities': approved,
            'reviewed_link_removals': removals, 'birthday_conflicts': conflicts,
            'source_XI_identity_review_passed': True,
            'candidate_startup_slot_order_policy': 'literal original XI ordering; source annual Grosso broad M preserved, defensive usage separately visible in source',
            'missing_used_substitutes': ['Nicola Santoni'], 'reserve_opening_membership_approved': False,
            'historical_formation_approved': False, 'compiler_replay_integrated': False,
            'publishable': False, 'registered': False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    pipeline.write_canonical_json(args.output, prepare())
    print(json.dumps({'source_XI_identity_review_passed': True, 'publishable': False, 'output': str(args.output)}))
