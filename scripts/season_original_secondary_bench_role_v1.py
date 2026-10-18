"""A missing bench role may use an exact-person official club biography.

This is a biographical broad-role witness, not a claim about match deployment.
Never override a published match position or infer a starting XI role.
"""
from datetime import datetime
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from scripts import season_external_soccerbase_birthday_v2 as birthdays

POLICY = 'original-numeric-bench-actor-and-exact-DOB-official-club-biographical-role-v1'


def parse(raw, url, name, birthday):
    source = urlparse(url)
    if (source.scheme != 'https' or source.netloc != 'www.stalybridgeceltic.co.uk'
            or source.path != '/play.php' or re.fullmatch(r'code=[A-Z]{5}', source.query) is None):
        raise ValueError('unsupported original official club biography URL')
    page = BeautifulSoup(raw, 'lxml')
    if page.title is None or page.title.get_text(' ', strip=True) != (
            'Stalybridge Celtic - Official Site - Player Profile ' + name):
        raise ValueError('official biography full player name differs')
    text = page.get_text(' ', strip=True)
    dates = re.findall(r'\bBorn (\d{1,2})(?:st|nd|rd|th) ([A-Z][a-z]{2}) (\d{4})\b', text)
    roles = re.findall(r'\bCareer Position (Goalkeeper|Defender|Midfielder|Forward) Born\b', text)
    if (len(dates) != 1 or len(roles) != 1
            or datetime.strptime(' '.join(dates[0]), '%d %b %Y').date().isoformat() != birthday):
        raise ValueError('official biography exact birthday/role is absent or conflicting')
    return {'Goalkeeper':'G', 'Defender':'D', 'Midfielder':'M', 'Forward':'F'}[roles[0]]


def resolve(review, bio, actual):
    if (review.get('policy') != POLICY or review.get('source_provider_person_id') != bio['source_player_id']
            or review.get('name') != bio['name'] or review.get('birth_date') != bio.get('birth_date')
            or bio.get('birth_date') is None):
        raise ValueError('secondary bench role lacks exact original numerical name/DOB')
    bench = [row for row in actual['original_match']['published_bench']
             if row['source_player_id'] == bio['source_player_id']]
    starters = [row for row in actual['original_match']['starting_xi']
                if row['source_player_id'] == bio['source_player_id']]
    if len(bench) != 1 or starters or bench[0]['position'] is not None:
        raise ValueError('secondary role only fills one unpublished bench position, never starters or known roles')
    original = review['original_profile']
    if original['url'] != bio['source_profile_url']:
        raise ValueError('secondary role changes original numerical person URL')
    raw = birthdays.prior.raw_source(original)
    if birthdays.prior.biographies.profile(raw, bench[0], original['url'], allow_missing_birth_date=True) != bio:
        raise ValueError('original bench full biography does not reparse')
    team = actual['original_match']['provider_club_id']
    if not re.fullmatch(r'soccerbase:[1-9][0-9]*', team):
        raise ValueError('original numerical club missing')
    birthdays.prior.careers.career_interval(raw, int(team.split(':')[1]), actual['fixture']['date'])
    external = review['external_biography']
    role = parse(birthdays.publisher_original(external), external['url'], bio['name'], bio['birth_date'])
    if role != review.get('primary_position'):
        raise ValueError('secondary bench role differs from literal official biography')
    return dict(policy=POLICY, primary_position=role, original_match_role=None,
        exact_match_deployment_claimed=False, official_biography=external,
        source_provider_person_id=bio['source_player_id'], birth_date=bio['birth_date'])
