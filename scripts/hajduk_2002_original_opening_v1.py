"""Read original opening labels without inventing full names or a reserve bench.

The archived report supplies eleven starters and one used substitute. Its
independently dated corroborator has a malformed list and different changes;
retain that disagreement, rather than repairing the source to suit a build.
"""
import re

from bs4 import BeautifulSoup

MATCH_URL = 'https://web.archive.org/web/20160305072650id_/http://dekisa.tripod.com/2003/12003.htm'
DATED_URL = 'https://www.partizanopedia.rs/0203.html'
MANAGER_URL = 'https://www.uefa.com/news-media/news/025e-0f90758aca0c-effa75959e30-1000--kula-coach-ends-two-month-reign/'
XI = ['Ciric', 'Antic', 'Malbasa', 'Mandic', 'Trajkovic', 'Cirka',
      'Marinkovic', 'Bosnjakovic', 'Pavicevic', 'Mester', 'Stojisavljevic']
LINE = ('HAJDUK: Ciric 5,5, Antic 5, Malbasa 6, Mandic 5, Trajkovic 5, '
        'Cirka 5, Marinkovic 5 (46. Vojnic 5), Bosnjakovic 5, Pavicevic 5, '
        'Mester 6, Stojisavljevic 5.')
DATED_LINE = ("Hajduk: Ćirić, Antić, Malbaša, Mandić, Trajković, Ćirka, "
              "Marinković (46' Vuksanović), Bošnjaković, Pavićević, "
              "Mešter (77' Buzić), Stojisavljević (46' Vojnić), Zelić")


def page(raw):
    if not isinstance(raw, bytes) or not 500 <= len(raw) <= 2 * 1024 ** 2:
        raise ValueError('unexpected original payload type or size')
    return BeautifulSoup(raw, 'html.parser')


def flat(raw):
    return re.sub(r'\s+', ' ', page(raw).get_text(' ', strip=True))


def parse(match_raw, dated_raw, manager_raw, *, urls=(MATCH_URL, DATED_URL, MANAGER_URL)):
    if urls != (MATCH_URL, DATED_URL, MANAGER_URL):
        raise ValueError('unexpected original source URLs')
    original = flat(match_raw)
    markers = ['PARTIZAN: Radakovic -', LINE,
               'IGRAC UTAKMICE: Goran Trobok (Partizan).',
               'RADNICKI: Soldatovic 7']
    if any(original.count(marker) != 1 for marker in markers):
        raise ValueError('original opening section missing or ambiguous')
    if [original.index(marker) for marker in markers] != sorted(original.index(marker) for marker in markers):
        raise ValueError('original XI belongs to another fixture')
    dated = page(dated_raw)
    headings = [h for h in dated.select('h3')
                if h.get_text(' ', strip=True) == 'Partizan - Hajduk Kula 5:1 (3:1)']
    if len(headings) != 1:
        raise ValueError('independently dated fixture missing or repeated')
    section = list(headings[0].find_all_next(['h3', 'p']))
    if (len(section) < 5 or section[0].name != 'p'
            or re.sub(r'\s+', ' ', section[0].get_text(' ', strip=True)) != '10. avgust 2002. Gledalaca: 800'
            or section[2].name != 'p' or section[2].get_text(' ', strip=True) != DATED_LINE
            or section[4].name != 'h3'
            or section[4].get_text(' ', strip=True) != 'Radnički Obrenovac - Partizan 1:2 (1:2)'):
        raise ValueError('independent first date or lineup disagreement changed')
    manager = flat(manager_raw)
    required = ['Sunday, September 1, 2002',
                'Miloljub Ostojic has resigned as coach of Yugoslavian first division side FK Hajduk Kula.',
                'Kula are 13th after four matches under Ostojic, who was appointed in June']
    if any(fragment not in manager for fragment in required):
        raise ValueError('dated opening-manager chronology missing or changed')
    return dict(season='2002-03', fixture_date='2002-08-10', club='Hajduk Kula',
        opponent='Partizan', result='1-5', manager='Miloljub Ostojić',
        starting_xi=[dict(published_match_name=name, full_identity=None) for name in XI],
        used_substitutes=[dict(published_match_name='Vojnic', minute=46, full_identity=None)],
        unused_substitutes=None, formation=None,
        source_disagreements=[dict(source='Partizanopedia', original_line=DATED_LINE,
            issue='Apparent twelve starters and different substitute names/assignments.',
            disposition='Date/result corroboration only; not used to manufacture a bench or full identity.')],
        limitations=['Full identities and birthdays must be joined independently.',
            'Six additional positively dated opening reserves are needed for fixed18.',
            'Later annual catalogue and current roles do not prove opening membership.'],
        native_writes=0, publication_authorised=False)
