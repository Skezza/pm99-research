"""Read only the four explicit biographies linked by the original match.

These are Foro IDs, not native or Transfermarkt IDs. Passive security scripts
do not replace the required complete biography DOM. Current club, displayed
age, role and portrait are deliberately excluded from historical facts.
"""
import datetime as dt
import re

from bs4 import BeautifulSoup

PEOPLE = {
    177: ('Alan Liebenskind', '1985-01-07'),
    194: ('José Miguel Reyes', '1992-09-19'),
    146: ('José Marrufo', '1996-05-12'),
    288: ('Marcos Sánchez', '1989-12-23'),
}


def parse(payload, url):
    match = re.fullmatch(r'https://www\.forovinotinto\.com/equipos/jugador\.php\?id=(\d+)', url)
    if match is None or int(match[1]) not in PEOPLE or not 1000 <= len(payload) <= 2*1024**2:
        raise ValueError('unexpected original linked person URL/size')
    id = int(match[1])
    expected_name, expected_dob = PEOPLE[id]
    page = BeautifulSoup(payload, 'html.parser')
    cards = page.select('.player-card-data')
    headings = page.select('h1')
    if (len(cards) != 1 or len(headings) != 1 or headings[0] not in cards[0].select('h1')
            or headings[0].get_text(' ', strip=True) != expected_name
            or page.title is None or page.title.get_text(' ', strip=True) != 'ForoVinotinto | '+expected_name):
        raise ValueError('original linked biography missing, ambiguous or another person')
    dates = []
    for line in cards[0].select('.player-card-meta-line'):
        labels = line.select('strong')
        if len(labels) == 1 and labels[0].get_text(strip=True) == 'Nacimiento:':
            text = line.get_text(' ', strip=True)
            date = re.fullmatch(r'Nacimiento: (\d{2})/(\d{2})/(\d{4}) \(\d+ años\)', text)
            if date is None:
                raise ValueError('original linked birthday missing or malformed')
            day, month, year = map(int, date.groups())
            dates.append(dt.date(year, month, day).isoformat())
    if dates != [expected_dob]:
        raise ValueError('original linked birthday ambiguous or conflicting')
    return dict(source_person_namespace='forovinotinto', source_person_id=id,
        published_name=expected_name, birth_date=dates[0], source_url=url,
        discarded_fields=['current club', 'displayed current age', 'current role', 'current portrait'],
        native_writes=0, publication_authorised=False)


def validate(payload, url):
    parse(payload, url)
