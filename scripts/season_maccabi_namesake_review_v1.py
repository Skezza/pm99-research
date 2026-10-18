"""Original club paired-appearance evidence; no database or recipe writes.

This explicitly scoped policy clears duplicate suspicion, not exact birthday,
first-league-XI, display-name or whole-squad approval. Different native dates
alone never suffice. Retain both independently published historical people.
"""
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from scripts import season_release_registry_v1 as registry
from scripts import season_italian_opening_layer_v1 as native
from scripts import season_within_club_reserve_repair_v1 as facts

ROOT = registry.ROOT
SOURCE_ROOT = ROOT / '.local/consolidated-audit-20261009/official-namesake-sources'
SOURCES = (
    ('maccabi-player-archive.html', 'https://www.maccabi-tlv.co.il/en/team/page/52/',
     'ec5768d46c7776cd15297c55e98348a6d14693d85f6be0300380409b23ab0540'),
    ('plzen-maccabi-20150805.html', 'https://www.fcviktoria.cz/zapas.asp?id=2879',
     '04d6974b651ef92a57ad41518aff1773fef98c4f63b79c2970ac8fb82eb3e546'),
)
CANDIDATE = 'b10350da555981b028b52ac7a6dbd80efdf015b388c9d6f8ac45a17da200db41'


def source_witness(archive_raw, match_raw):
    archive = BeautifulSoup(archive_raw.decode('utf-8'), 'lxml')
    biographies = {}
    for link in archive.select('h1.entry-title a'):
        url = link.get('href')
        if url in ('https://www.maccabi-tlv.co.il/en/team/tal-ben-haim/',
                   'https://www.maccabi-tlv.co.il/en/team/tal-ben-chaim/'):
            article = link.find_parent('article')
            if article is None or url in biographies:
                raise ValueError('official person article missing or repeated')
            biographies[url] = article.get_text(' ', strip=True)
    if len(biographies) != 2:
        raise ValueError('two independent official person URLs required')
    # Fixed identity URLs, not source DOM order, determine the sporting identity.
    defender = biographies['https://www.maccabi-tlv.co.il/en/team/tal-ben-haim/']
    winger = biographies['https://www.maccabi-tlv.co.il/en/team/tal-ben-chaim/']
    if not all(p in defender for p in ('born in 1982', 'central defender', 'June 3, 2015')):
        raise ValueError('defender birth-year/role/dated return missing')
    if not all(p in winger for p in ('winger', 'summer of 2015', '2015/16')):
        raise ValueError('other sporting identity and target season missing')
    # Original declares cp1250, with undefined bytes elsewhere in the page.
    # Preserve raw bytes and reject replacement characters in evidentiary nodes.
    match = BeautifulSoup(match_raw.decode('cp1250', errors='replace'), 'lxml')
    canonical = match.select('meta[property="og:url"]')
    if len(canonical) != 1 or canonical[0].get('content') != SOURCES[1][1]:
        raise ValueError('wrong original match identity')
    dates = match.select('p.match-head.hidden-mobile')
    if len(dates) != 1 or '5. 8. 2015, 20:45' not in dates[0].get_text(' ', strip=True):
        raise ValueError('original August fixture date missing')
    team_nodes = [p for p in match.select('article.article-text p.team-name')
                  if p.get_text(' ', strip=True) == 'Maccabi Tel-Aviv']
    if len(team_nodes) != 1:
        raise ValueError('original match side missing or ambiguous')
    lineup = team_nodes[0].find_next_sibling('p')
    text = lineup.get_text(' ', strip=True) if lineup else ''
    if (not lineup or 'font-15' not in lineup.get('class', []) or '\ufffd' in text
            or len(re.findall(r'\bBen Haim I\b', text)) != 1
            or len(re.findall(r'\bBen Haim II\b', text)) != 1):
        raise ValueError('both distinct published people must appear once on exact side')
    return {'date': '2015-08-05', 'club': 'Maccabi Tel-Aviv',
            'two_distinct_published_match_people': True,
            'defender_born_year': 1982, 'other_role': 'winger',
            'exact_birthdays_independently_verified': False,
            'first_league_fixture_claimed': False,
            'decoding_policy': 'raw cp1250 retained; no replacement in lineup evidence'}


def prepare(release=None):
    bindings = []
    for name, url, sha in SOURCES:
        path = SOURCE_ROOT / name
        if registry.sha256_file(path) != sha:
            raise ValueError('original official source bytes changed')
        bindings.append({'url': url, 'path': registry.relative_workspace_path(path), 'sha256': sha})
    witness = source_witness(*( (SOURCE_ROOT / row[0]).read_bytes() for row in SOURCES))
    release = release or registry.load_preferred_release('2015-16')
    if release.season != '2015-16':
        raise ValueError('official paired appearance belongs only to 2015-16')
    package = json.loads(release.package_path.read_text())
    club = next(c for c in package['clubs'] if c['id'] == 'club-2101')
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    _, _, roster = native.roster_rows(eq, 2101)
    players = []
    for id, position, birth in ((2027, 'D', '1982-03-31'), (32232, 'M', '1989-08-05')):
        person = next(p for p in package['players'] if p['carrier_id'] == id)
        actual = facts.native_facts(jug, id)
        if (person['id'] not in club['roster_player_ids'] or roster.count((id, 0)) != 1
                or actual['position'] != position or actual['birth_date'] != birth
                or person.get('source_name') != 'Ben-Haim, Tal'
                or person['facts']['birth_date'] != birth):
            raise ValueError('native/recipe paired identities changed')
        players.append({'carrier_id': id, 'native': actual, 'source_name': person['source_name']})
    return {'schema': 'pm99-official-paired-appearance-namesake-disposition-v1',
            'policy': 'two-original-club-person-biographies-and-same-dated-positive-match-side-v1',
            'candidate_id': CANDIDATE, 'season': release.season, 'club_id': club['id'],
            'release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
            'jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
            'eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
            'sources': bindings, 'witness': witness, 'players': players,
            'duplicate_suspicion_cleared': True, 'native_writes': 0,
            'scope': 'Retain both legitimate people. No exact DOB, first league XI, skills, portraits or display-name approval.',
            'remaining_display_name_issue': 'Both native/recipe display names are Tal; retain separately for sourced name correction.'}
