"""Missing-only secondary birthdays from explicitly bound publisher originals.

Preserve known dates. Keep original numerical Soccerbase identity and dated
career/match witnesses; never invent a Transfermarkt person or claim consensus.
Retained web excerpts are explicitly not represented as original network HTML.
"""
import copy
from datetime import date, datetime
import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from scripts import season_external_soccerbase_birthday_v1 as prior

pipeline, registry = prior.pipeline, prior.registry
POLICY = 'original-numeric-Soccerbase-missing-DOB-bound-secondary-publishers-v2'


def publisher_original(binding):
    path = registry.ROOT / binding['path']
    if registry.sha256_file(path) != binding['sha256']:
        raise ValueError('secondary publisher body changed')
    if binding.get('content_form') == 'retained-minimal-publisher-excerpt':
        document = pipeline.read_json_file(path)
        if (document.get('schema') != 'pm99-retained-publisher-extracted-facts-witness-v1'
                or document.get('url') != binding['url']
                or document.get('retrieval_method') != 'web.open original publisher page, extracted text'
                or document.get('content_form') != 'minimal literal factual excerpt, NOT original network HTML or local browser DOM'):
            raise ValueError('excerpt provenance is missing or falsely labelled as raw HTML')
        numeric = re.fullmatch(r'/players/[a-z-]+-([1-9][0-9]*)/', urlparse(binding['url']).path)
        if numeric is None or document.get('source_person_numeric_id') != '11v11:' + numeric[1]:
            raise ValueError('excerpt numerical publisher person differs from its URL')
        return document
    receipt = registry.ROOT / binding['source_receipt_path']
    metadata = pipeline.read_json_file(receipt)
    if (registry.sha256_file(receipt) != binding['source_receipt_sha256']
            or metadata.get('url') != binding['url'] or metadata.get('status') != 'original-captured'
            or metadata.get('sha256') != binding['sha256']):
        raise ValueError('secondary publisher original receipt/body/URL differs')
    return path.read_bytes()


def birthday(body, url, name, role, club, fixture_date):
    source = urlparse(url)
    if source.scheme != 'https' or source.fragment:
        raise ValueError('secondary publisher URL is not an allowed original')
    if isinstance(body, dict):
        if (source.netloc != 'www.11v11.com'
                or re.fullmatch(r'/players/[a-z-]+-[1-9][0-9]*/', source.path) is None):
            raise ValueError('unsupported original excerpt publisher URL')
        literal = body['literal_excerpt'].splitlines()
        if len(literal) != 3 or literal[0] != name:
            raise ValueError('original excerpt full person name differs')
        born = re.fullmatch(r'Date of birth \| (\d{1,2} [A-Z][a-z]+ \d{4})', literal[1])
        spell = re.fullmatch(re.escape(club) + r' \| (\d{2} [A-Z][a-z]{2} \d{4}) \| (\d{2} [A-Z][a-z]{2} \d{4})', literal[2])
        if born is None or spell is None:
            raise ValueError('original excerpt date/club interval is absent')
        value = datetime.strptime(born[1], '%d %B %Y').date().isoformat()
        start = datetime.strptime(spell[1], '%d %b %Y').date().isoformat()
        end = datetime.strptime(spell[2], '%d %b %Y').date().isoformat()
        if not start <= fixture_date <= end:
            raise ValueError('excerpt club spell does not cover the original fixture')
        if body.get('structured_facts') != dict(name=name, birth_date=value, club=club, from_date=start, to_date=end):
            raise ValueError('excerpt parsed facts disagree with retained literal text')
        return value
    page = BeautifulSoup(body, 'lxml')
    if source.netloc == 'en.wikipedia.org' and source.path.startswith('/wiki/'):
        headings = [h.get_text(' ', strip=True) for h in page.select('h1#firstHeading')]
        if len(headings) != 1 or not (headings[0] == name or headings[0].startswith(name + ' (')):
            raise ValueError('original Wikipedia person heading differs')
        dates = [node.get_text(' ', strip=True) for node in page.select('table.infobox .bday')]
        if len(dates) != 1:
            raise ValueError('one original Wikipedia birthday required')
        positions = [tr.get_text(' ', strip=True) for tr in page.select('table.infobox tr')
            if tr.find('th') and tr.find('th').get_text(' ', strip=True) in ('Position', 'Position(s)')]
        expected = {'G':'Goalkeeper', 'D':'Defender', 'M':'Midfielder', 'F':'Forward'}[role]
        if len(positions) != 1 or expected not in positions[0]:
            raise ValueError('Wikipedia biography role does not identify the original actor')
        year = int(fixture_date[:4]); spells = []
        for tr in page.select('table.infobox tr'):
            cells = tr.find_all(['th', 'td'], recursive=False)
            if len(cells) < 2 or not any(a.get_text(' ', strip=True) == club for a in cells[1].select('a')):
                continue
            match = re.fullmatch(r'(\d{4})(?:[–−-](\d{4}))?', cells[0].get_text(' ', strip=True))
            if match and int(match[1]) <= year <= int(match[2] or match[1]): spells.append(tr)
        if len(spells) != 1:
            raise ValueError('Wikipedia original biography lacks the target club-year')
        return date.fromisoformat(dates[0]).isoformat()
    if (source.netloc == 'www.southportcentral.co.uk'
            and source.path == '/players/player-details/' and re.fullmatch(r'id=[1-9][0-9]*', source.query)):
        if [h.get_text(' ', strip=True) for h in page.select('h1')] != [name]:
            raise ValueError('original official Southport person heading differs')
        people = [json.loads(s.get_text()) for s in page.select('script[type="application/ld+json"]')]
        people = [p for p in people if isinstance(p, dict) and p.get('@type') == 'Person']
        if (len(people) != 1 or people[0].get('@id') != url or people[0].get('url') != url
                or people[0].get('name') != name or people[0].get('jobTitle') != 'Footballer'
                or not any(n.get_text(' ', strip=True) == club+' First Team'
                           for n in page.select('.mcr-transfer-club'))):
            raise ValueError('original Southport numerical person/club biography differs')
        value = date.fromisoformat(people[0]['birthDate'])
        facts = {dt.get_text(' ', strip=True): dt.find_next_sibling('dd').get_text(' ', strip=True)
            for dt in page.select('dl.mcr-player-facts dt') if dt.find_next_sibling('dd') is not None}
        if not facts.get('Born', '').startswith(value.strftime('%d/%m/%Y') + ' '):
            raise ValueError('Southport displayed/structured birthdays disagree')
        return value.isoformat()
    if (source.netloc == 'www.afcsudbury.co.uk'
            and source.path == '/a/a-to-z-the-men-of-afc-sudbury-39173.html'):
        headings = [n for n in page.select('strong') if n.get_text(' ', strip=True) == name]
        if len(headings) != 1:
            raise ValueError('one exact official Sudbury biography heading required')
        text = headings[0].find_parent('p').find_next_sibling('p').get_text(' ', strip=True)
        born = re.match(r'A defender/midfielder \(b (\d{2}/\d{2}/\d{2})\)', text)
        years = re.search(re.escape(club) + r' in (\d{4}) an[d]? stayed with them until (\d{4})', text)
        if (born is None or years is None or role not in ('D', 'M')
                or not int(years[1]) <= int(fixture_date[:4]) <= int(years[2])):
            raise ValueError('official Sudbury biography lacks literal date/role/club-year')
        return datetime.strptime(born[1], '%d/%m/%y').date().isoformat()
    raise ValueError('unsupported secondary original publisher layout')


def resolve(review, bio, actual):
    if (review.get('secondary_birthday_policy') != POLICY or bio.get('birth_date') is not None
            or review.get('published_birth_date') is not None or review['name'] != bio['name']
            or review['source_provider_person_id'] != bio['source_player_id']
            or review['canonical_source_player_id'] != bio['source_player_id']):
        raise ValueError('secondary birthday cannot override a known date or another original numerical person')
    rows = [p for group in ('starting_xi', 'published_bench') for p in actual['original_match'][group]
            if p['source_player_id'] == bio['source_player_id']]
    if len(rows) != 1 or rows[0]['position'] not in ('G', 'D', 'M', 'F'):
        raise ValueError('secondary date lacks one original numerical fixture actor/role')
    original = review['original_profile']
    if original['url'] != bio['source_profile_url']:
        raise ValueError('secondary identity changes the original numerical profile URL')
    raw = prior.raw_source(original)
    if prior.biographies.profile(raw, rows[0], original['url'], allow_missing_birth_date=True) != bio:
        raise ValueError('original missing biography no longer independently reparses')
    team = actual['original_match']['provider_club_id']
    if not re.fullmatch(r'soccerbase:[1-9][0-9]*', team):
        raise ValueError('original numerical club missing')
    prior.careers.career_interval(raw, int(team.split(':')[1]), actual['fixture']['date'])
    external = review['external_biography']
    value = birthday(publisher_original(external), external['url'], bio['name'],
                     rows[0]['position'], actual['club'], actual['fixture']['date'])
    if value != review['canonical_birth_date']:
        raise ValueError('secondary date differs from its literal original publication')
    if not 12 <= (date.fromisoformat(actual['fixture']['date']) - date.fromisoformat(value)).days / 365.2425 <= 50:
        raise ValueError('secondary birthday outside plausible playing age')
    result = copy.deepcopy(bio)
    result.update(birth_date=value, source_provider='soccerbase', identity_policy=POLICY,
        secondary_birth_date_original=external,
        birthday_confidence='single-original-secondary-publication-not-consensus')
    return result
