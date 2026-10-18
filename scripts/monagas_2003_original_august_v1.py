"""Read the original August cup XI and adjoining July opening-squad witness.

This is source-only. It neither substitutes a league opener nor certifies a
person's birthday, citizenship, role, portrait or ownership in a native slot.
"""
import re

from bs4 import BeautifulSoup

URL = 'https://rsssf.org/sacups/sudamcup-venez.html'
JULY = ('Monagas: José Fasciana, Pedro Duval, Enermis Rodríguez, Carlos Carreño, '
        'Orlando Mejías, Anyelo Rodríguez, Marcos Dotta (Ronald Ojeda, 59), Hugo '
        'Lusardi, Carlos Gorosso, Jhony Alejo (Rolando Suárez, 46), Alexis Acuña. '
        'Coach: Daniel Lanatta;')
AUGUST = ('Monagas SC: José Fasciana – Carlos Goroso, Pedro Duval, Héctor Blanco, '
          'Enermis Rodríguez (Ronald Ojeda, 75) – Anyelo Rodríguez, Orlando Mejías '
          '(Jhony Alejo, 75), Hugo Luzardi – Alexis Acuña, Luciano Roque '
          '(Rolando Suárez, 31), William Lacle. Coach: Daniel Lanata;')
XI = ['José Fasciana', 'Carlos Goroso', 'Pedro Duval', 'Héctor Blanco',
      'Enermis Rodríguez', 'Anyelo Rodríguez', 'Orlando Mejías', 'Hugo Luzardi',
      'Alexis Acuña', 'Luciano Roque', 'William Lacle']
USED = [('Ronald Ojeda', 75), ('Jhony Alejo', 75), ('Rolando Suárez', 31)]
JULY_ADDITIONS = ['Carlos Carreño', 'Marcos Dotta']


def parse(raw, *, url=URL):
    if url != URL or not isinstance(raw, bytes) or not 500 <= len(raw) <= 2 * 1024**2:
        raise ValueError('unexpected original Sudamericana URL or payload')
    # RSSSF's saved original is Western Windows-1252 with no charset header.
    # Automatic encoding detection incorrectly turns accents into Polish letters.
    page = BeautifulSoup(raw.decode('cp1252'), 'html.parser')
    if page.title is None or page.title.get_text() != 'Venezolan clubs in Copa Sudamericana':
        raise ValueError('original source identifies another competition')
    pre = page.find('pre')
    if pre is None:
        raise ValueError('original competition report missing')
    text = re.sub(r'\s+', ' ', pre.get_text(' ', strip=True))
    if text.count('Edition 2003') != 1 or text.count('Edition 2002') != 1:
        raise ValueError('original edition labels absent or ambiguous')
    section = text.split('Edition 2003', 1)[1].split('Edition 2002', 1)[0]
    july = section.split('[July 31]', 1)
    if len(july) != 2 or '[August 5]' not in july[1]:
        raise ValueError('original adjoining opening dates missing')
    july, august = july[1].split('[August 5]', 1)
    august = august.split('First Round:', 1)[0]
    if (july.count(JULY) != 1 or august.count(AUGUST) != 1
            or 'Monagas SC 1-2 Deportivo Italchacao' not in july
            or 'Deportivo Italchacao 1-0 Monagas SC' not in august
            or 'At Estadio Alexander “comanche” Bottini in Maturín.' not in july
            or 'At Estadio Brígido Iriarte in Caracas' not in august):
        raise ValueError('original target fixture, ground, XI or changes differ')
    names = XI + [name for name, _ in USED] + JULY_ADDITIONS
    if len(names) != 16 or len(set(names)) != 16:
        raise ValueError('original opening union does not contain sixteen distinct labels')
    return dict(season='2003-04', club='Monagas SC', fixture_date='2003-08-05',
        competition='cup', first_league_xi=False, opponent='Deportivo Italchacao',
        result='0-1', manager_published='Daniel Lanata',
        starting_xi=[dict(published_match_name=name) for name in XI],
        used_substitutes=[dict(published_match_name=name, minute=minute) for name, minute in USED],
        additional_opening_people=[dict(published_match_name=name,
            witnessed_date='2003-07-31') for name in JULY_ADDITIONS],
        opening_home_ground=dict(name='Estadio Alexander Comanche Bottini',
            witnessed_date='2003-07-31'), formation=None, unused_substitutes=None,
        source_disagreements=[dict(field='published labels',
            july=['Carlos Gorosso', 'Hugo Lusardi', 'Daniel Lanatta'],
            august=['Carlos Goroso', 'Hugo Luzardi', 'Daniel Lanata'],
            disposition='Retain original spellings; independent person joins required.')],
        source_gaps=['August cup XI, not a proven first league XI.',
            'Two additional players positively witnessed on July31, not invented August bench.',
            'Birthdays, nationality, physical facts and exact formation require separate evidence.',
            'Published label variants are not automatic same-person identity approval.'],
        credits='Eliézer Sebastián Pérez Pérez / RSSSF; original compilation credits El Nacional, El Universal and Meridiano.',
        native_writes=0, publication_authorised=False)
