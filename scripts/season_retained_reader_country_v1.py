"""Exact biography countries from separately identified original/reader sources.

The reader response is extracted text, not original HTML. Never infer from birthplace,
club, a name or a national-team appearance. Native masks and SOURCE replay use
the existing source-backed nationality writer.
"""
from datetime import datetime
import re
from urllib.parse import urlsplit

PROVIDER = '11v11-retained-reader-biography-v1'
ORIGINAL_PROVIDER = '11v11-original-profile-country-v1'


def parse_original_country(raw, source, *, actor_name, birth_date):
    """Read explicit biography cells from the original, URL-bound HTML."""
    from bs4 import BeautifulSoup
    origin = source.get('url', '')
    url = urlsplit(origin)
    pid = source.get('provider_player_id')
    if (source.get('provider') != ORIGINAL_PROVIDER or type(pid) is not int or pid < 1
            or url.scheme != 'https' or url.netloc != 'www.11v11.com'
            or url.query or url.fragment
            or not re.fullmatch(rf'/players/[a-z0-9-]+-{pid}/', url.path)):
        raise ValueError('exact original canonical profile URL and ID required')
    page = BeautifulSoup(raw, 'lxml')
    if ([x.get('content') for x in page.select('meta[property="og:url"]')] != [origin]
            or [x.get_text(' ', strip=True) for x in page.select('h1')] != [actor_name]
            or page.title is None
            or page.title.get_text(strip=True) != actor_name + ' Football Player Statistics | 11v11.com'):
        raise ValueError('original HTML identifies another profile')
    blocks = page.select('.basicData')
    if len(blocks) != 1:
        raise ValueError('one original biography block required')
    values = {}
    for row in blocks[0].select('tr'):
        cells = row.find_all(['td', 'th'], recursive=False)
        if len(cells) != 2:
            continue
        key, value = [c.get_text(' ', strip=True) for c in cells]
        if key in {'Date of birth', 'Nationality'}:
            if key in values or not value:
                raise ValueError('duplicate or empty original biography fact')
            values[key] = value
    if (set(values) != {'Date of birth', 'Nationality'}
            or datetime.strptime(values['Date of birth'], '%d %B %Y').date().isoformat() != birth_date):
        raise ValueError('original exact birthday or explicit nationality missing')
    from scripts.season_historical_player_facts_audit_v1 import country, COUNTRIES
    literal = values['Nationality']
    code = {'Dutch': 'NED', 'Norwegian': 'NOR', 'German': 'GER',
            'Swiss': 'SUI', 'English': 'ENG'}.get(literal) or country(literal)
    if code is None or code == 'XXX' or code not in set(COUNTRIES.values()):
        raise ValueError('original nationality has no explicit supported mapping')
    return dict(name=actor_name, birth_date=birth_date, nationality=code,
                published_country=literal, provider=ORIGINAL_PROVIDER,
                provider_player_id=pid, url=origin, original_url=origin,
                source_format='original-profile-HTML',
                target_season_ownership_claimed=False,
                exclusive_citizenship_at_target_date_claimed=False)


def parse_country(raw, source, *, actor_name, birth_date):
    origin = source.get('original_url', '')
    url = urlsplit(origin)
    pid = source.get('provider_player_id')
    if (source.get('provider') != PROVIDER or type(pid) is not int or pid < 1
            or url.scheme != 'https' or url.netloc != 'www.11v11.com'
            or url.query or url.fragment
            or not re.fullmatch(rf'/players/[a-z0-9-]+-{pid}/', url.path)
            or source.get('url') != 'https://r.jina.ai/' + origin):
        raise ValueError('exact reader/original canonical profile URL and ID required')
    text = raw.decode('utf-8')

    def one(pattern, label):
        matches = re.findall(pattern, text, re.MULTILINE)
        if len(matches) != 1:
            raise ValueError('one explicit reader ' + label + ' required')
        return matches[0].strip()

    title = one(r'^Title: (.+)$', 'title')
    if (title not in {actor_name, actor_name + ' Football Player Statistics | 11v11.com'}
            or one(r'^URL Source: (.+)$', 'origin URL') != origin
            or text.count('Markdown Content:') != 1):
        raise ValueError('reader source identifies another profile')
    birthday = one(r'^\*\*Date of birth\*\*[ \t]*(.+)$', 'birthday')
    if datetime.strptime(birthday, '%d %B %Y').date().isoformat() != birth_date:
        raise ValueError('reader exact birthday differs from selected identity')
    literal = one(r'^\*\*Nationality\*\*[ \t]*(.+)$', 'nationality')
    from scripts.season_historical_player_facts_audit_v1 import country
    code = {'Dutch': 'NED', 'Norwegian': 'NOR', 'German': 'GER', 'Swiss': 'SUI'}.get(literal) or country(literal)
    if code is None or code == 'XXX':
        raise ValueError('reader nationality has no explicit supported mapping')
    return dict(name=actor_name, birth_date=birth_date, nationality=code,
                published_country=literal, provider=PROVIDER, provider_player_id=pid,
                url=source['url'], original_url=origin,
                source_format='retained-reader-extracted-text-not-original-HTML',
                target_season_ownership_claimed=False,
                exclusive_citizenship_at_target_date_claimed=False)
