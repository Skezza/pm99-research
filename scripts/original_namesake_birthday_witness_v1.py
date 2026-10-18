"""Read two explicit independent biographies; never choose the youngest name."""
from datetime import date
import re
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_tachira_2014_original_people_v1 import source_rows

SCHEMA = 'pm99-original-independent-namesake-birthday-witness-v1'
KEYS = {
    'savio-nationality-original-man-city-2024-squad':'https://www.transfermarkt.es/manchester-city/kader/verein/281/saison_id/2024/plus/1',
    'six-dates-original-crewe-U18-2024-squad':'https://www.transfermarkt.es/crewe-alexandra-u18/kader/verein/12804/saison_id/2024/plus/1',
    'six-dates-original-crawley-2024-squad':'https://www.transfermarkt.es/crawley-town/kader/verein/3537/saison_id/2024/plus/1',
    'six-dates-original-morecambe-3697-2023-squad':'https://www.transfermarkt.es/fc-morecambe/kader/verein/3697/saison_id/2023/plus/1',
    'six-dates-original-shrewsbury-2024-squad':'https://www.transfermarkt.es/shrewsbury-town/kader/verein/3054/saison_id/2024/plus/1',
    'six-dates-original-man-city-2024-squad':'https://www.transfermarkt.es/manchester-city/kader/verein/281/saison_id/2024/plus/1',
    'namesake-birthday-primary-dylan-cardiff': 'https://www.cardiffcityfc.co.uk/player/412',
    'namesake-birthday-original-john-wikipedia': 'https://en.wikipedia.org/wiki/John_Clarke_(footballer,_born_2004)',
    'namesake-birthday-original-gillingham-2025-squad': 'https://www.transfermarkt.co.uk/gillingham-fc/kader/verein/2814/saison_id/2025/plus/1',
    'namesake-birthday-original-grimsby-2025-squad': 'https://www.transfermarkt.co.uk/grimsby-town/kader/verein/1034/saison_id/2025/plus/1',
}
PERIOD_SQUADS = {
    'savio-nationality-original-man-city-2024-squad':('Manchester City','Manchester City','Sávio',743591),
    'six-dates-original-crewe-U18-2024-squad':('Crewe Alexandra U18','Crewe Alexandra','Owen Taylor',1353755),
    'six-dates-original-crawley-2024-squad':('Crawley Town','Crawley Town','Jay Williams',612093),
    'six-dates-original-morecambe-3697-2023-squad':('FC Morecambe','Morecambe','Tom Bloxham',816515),
    'six-dates-original-shrewsbury-2024-squad':('Shrewsbury Town','Shrewsbury Town','Tom Bloxham',816515),
    'six-dates-original-man-city-2024-squad':('Manchester City','Manchester City','Sávio',743591),
    'namesake-birthday-original-gillingham-2025-squad': ('Gillingham FC', 'Gillingham', 'Harry Webster', 1313578),
    'namesake-birthday-original-grimsby-2025-squad': ('Grimsby Town', 'Grimsby Town', 'Alex Graham', 1350651),
}


def parse(key, raw):
    if key not in KEYS or not isinstance(raw, bytes) or len(raw) > 2 * 1024 ** 2:
        raise ValueError('unsupported original namesake biography')
    soup = BeautifulSoup(raw, 'html.parser')
    if key in PERIOD_SQUADS:
        title_club, historical_club, name, person_id = PERIOD_SQUADS[key]
        titles = {m.get('content') for m in soup.select('meta[property="og:title"]')}
        urls = {m.get('content') for m in soup.select('meta[property="og:url"]')}
        expected_title=title_club + ' - Detailed squad 25/26 (Detailed view)'
        if key.startswith('six-dates-original-') or key=='savio-nationality-original-man-city-2024-squad':
            year='23/24' if '2023-squad' in key else '24/25'
            expected_title=title_club+' - Plantilla detallada '+year+' (Vista en detalle)'
        if (titles != {expected_title}
                or urls != {KEYS[key]}):
            raise ValueError('original namesake squad club/season/URL changed')
        rows = []
        for row in soup.select('table.items > tbody > tr'):
            links = [a for a in row.select('a[href*="/profil/spieler/"]')
                if re.search(r'/profil/spieler/' + str(person_id) + r'(?:/|$)', a.get('href', ''))]
            if links:
                if len(links) != 1 or links[0].get_text(' ', strip=True) != name:
                    raise ValueError('original namesake stable person link/name ambiguous')
                cells = row.find_all('td', recursive=False)
                match = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4}) \(\d+\)',
                    cells[2].get_text(' ', strip=True)) if len(cells) == 10 else None
                if match is None:
                    raise ValueError('original namesake period-row birthday missing')
                day, month, year = map(int, match.groups())
                rows.append(date(year, month, day).isoformat())
                if key=='savio-nationality-original-man-city-2024-squad':
                    flags=cells[3].select('img.flaggenrahmen')
                    if (len(flags)!=1 or flags[0].get('alt')!='Brasil'
                            or flags[0].get('title')!='Brasil'
                            or not re.fullmatch(r'https://img\.a\.transfermarkt\.technology/flagge/verysmall/26\.png(?:\?lm=\d+)?',flags[0].get('src',''))):
                        raise ValueError('original exact Sávio period nationality not uniquely Brazil')
        if len(rows) != 1:
            raise ValueError('original namesake stable person row missing or duplicated')
        birthday = rows[0]
    elif key == 'namesake-birthday-primary-dylan-cardiff':
        def one(selector):
            values = {e.get_text(' ', strip=True) for e in soup.select(selector)}
            if len(values) != 1 or not next(iter(values)):
                raise ValueError('original club biography identity missing or ambiguous')
            return next(iter(values))
        name = one('.field--name-field-cc-first-name') + ' ' + one('.field--name-field-cc-last-name')
        dates = {e.get('datetime', '') for e in soup.select('.field--name-field-cc-date-of-birth time')}
        if len(dates) != 1 or soup.title is None or soup.title.get_text() != 'D. Lawlor | Cardiff':
            raise ValueError('original club biography DOB/title changed')
        birthday = next(iter(dates)).split('T')[0]
        if name != 'Dylan Lawlor':
            raise ValueError('club biography refers to another player')
        historical_club = 'Cardiff City'
    else:
        names = {e.get_text(' ', strip=True) for e in soup.select('.infobox .fn')}
        dates = {e.get_text(' ', strip=True) for e in soup.select('.infobox .bday')}
        titles = {e.get_text(' ', strip=True) for e in soup.select('h1')}
        if names != {'John Clarke'} or len(dates) != 1 or titles != {'John Clarke (footballer, born 2004)'}:
            raise ValueError('original explicitly disambiguated biography identity/DOB changed')
        name, birthday = 'John Clarke', next(iter(dates))
        reading_links = {'/wiki/Reading_F.C.', './Reading_F.C.',
            'https://en.wikipedia.org/wiki/Reading_F.C.'}
        careers = [row.get_text(' ', strip=True) for row in soup.select('.infobox tr')
            if any(a.get('href') in reading_links for a in row.select('a'))]
        if len(careers) != 1 or not careers[0].startswith('2022–2026 Reading '):
            raise ValueError('independent birthday biography does not identify the target-era Reading player')
        historical_club = 'Reading'
    date.fromisoformat(birthday)
    result=dict(name=name, birth_date=birthday, historical_club=historical_club,
        approves_current_club_ownership=False)
    if key.startswith('six-dates-original-') or key=='savio-nationality-original-man-city-2024-squad':
        result.update(period_person_source_id=person_id,
            source_period='2023-24' if '2023-squad' in key else '2024-25')
    if key=='six-dates-original-crewe-U18-2024-squad':
        # Previous-season youth identity evidence, not 2025 opening ownership.
        # The first-team annual catalogue links a different older namesake.
        result['identity_scope']='2024/25 youth biography only; original 2025/26 recipe source must independently identify the same club/player'
    if key in ('six-dates-original-man-city-2024-squad','savio-nationality-original-man-city-2024-squad'):
        # A one-token name needs a separately published alias, never an inferred split.
        path,raw,binding=source_rows('six-dates-original-Savio-Savinho-primary-alias')
        receipt=pipeline.read_json_file(path.with_suffix('.source.json'))
        primary=BeautifulSoup(raw,'html.parser')
        if (receipt['url']!='https://www.premierleague.com/en/news/4051917'
                or primary.h1 is None or primary.h1.get_text(' ',strip=True)!='Who is new Man City signing Savinho?'
                or 'Also known as "Savio", he was born in Sao Mateus, Brazil, on 10 April 2004.' not in primary.get_text(' ',strip=True)
                or birthday!='2004-04-10'):
            raise ValueError('original primary Sávio/Savinho alias and birthday not proved')
        result.update(single_name_alias_verified=True,primary_alias_binding=binding,
            primary_alias_url=receipt['url'])
        if key=='savio-nationality-original-man-city-2024-squad':
            result['exact_period_nationality']='BRA'
    if 'morecambe' in key or 'shrewsbury' in key:
        result['date_disagreement_note']='Target-period stable person816515 and API publish November2,2003. Other biographies publish November1. Preserve target recipe day/month while repairing year only; not a universal actual-day verdict.'
    return result


def load(document_path):
    document = pipeline.read_json_file(document_path)
    if document.get('schema') != SCHEMA or not document.get('witnesses'):
        raise ValueError('original namesake witness schema missing')
    result = {}
    for row in document['witnesses']:
        if row['source_key'] not in KEYS:
            raise ValueError('unsupported original namesake source key')
        if row['carrier_id'] in result:
            raise ValueError('duplicate original namesake witness carrier')
        path, raw, binding = source_rows(row['source_key'])
        receipt = pipeline.read_json_file(path.with_suffix('.source.json'))
        if receipt['url'] != KEYS[row['source_key']] or binding != row['source_binding']:
            raise ValueError('original namesake biography URL/SHA differs')
        observed = parse(row['source_key'], raw)
        if observed['name'] != row['name'] or observed['birth_date'] != row['birth_date']:
            raise ValueError('saved namesake witness did not reparse from original publisher')
        result[row['carrier_id']] = dict(observed, original_binding=binding, original_url=receipt['url'])
    return result
