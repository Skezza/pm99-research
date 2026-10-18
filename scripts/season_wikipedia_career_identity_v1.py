"""Original Wikipedia identity and conservative interior-year club witness.

Only a year strictly inside one senior playing spell is usable. Boundary years,
overlapping loans and managerial/international/current-team rows confer no
permission. No exact transfer day or matchday appearance is manufactured.
"""
from datetime import date
import calendar
import hashlib
import re
from urllib.parse import unquote, urlparse
from bs4 import BeautifulSoup
from scripts import season_historical_roster_audit_v1 as roster

POLICY = 'original-Wikipedia-full-name-DOB-unique-senior-interior-year-v1'
MONTH_POLICY = 'original-Wikipedia-full-name-DOB-explicit-entry-month-v1'
CLUB_ALIASES = {'italy': {'milan': {'milan', 'acmilan'}}}


def read(raw, slug, url, anchor, club, country, *, allow_entry_month=False, expected_name=None,
         allow_nonperson_infoboxes=False):
    source = urlparse(url)
    if (source.scheme != 'https' or source.netloc != 'en.wikipedia.org' or
            source.path != '/wiki/' + slug or source.query or source.fragment or '/' in slug):
        raise ValueError('original Wikipedia person URL/namespace differs')
    page = BeautifulSoup(raw, 'lxml')
    headings, boxes = page.select('h1'), page.select('table.infobox')
    if allow_nonperson_infoboxes:
        # An unrelated "external videos" box is not a second biography.
        # Only this explicit route filters it; two DOB-bearing biographies
        # still refuse, even if just one also contains a career table.
        boxes = [box for box in boxes if box.select('.bday')]
    if len(headings) != 1 or len(boxes) != 1:
        raise ValueError('Wikipedia identity needs one original heading and infobox')
    name = headings[0].get_text(' ', strip=True)
    if roster.normalise(name) != roster.normalise(unquote(slug).replace('_', ' ')):
        raise ValueError('Wikipedia article title does not identify the requested full person')
    box = boxes[0]
    if expected_name and roster.normalise(expected_name) != roster.normalise(name):
        full_names = []
        for tr in box.select('tr'):
            cells = tr.find_all(['th', 'td'], recursive=False)
            if len(cells) == 2 and cells[0].get_text(' ', strip=True) == 'Full name':
                field = BeautifulSoup(str(cells[1]), 'lxml')
                for citation in field.select('sup'):
                    citation.decompose()
                full_names.append(field.get_text(' ', strip=True))
        if len(full_names) != 1 or roster.normalise(full_names[0]) != roster.normalise(expected_name):
            raise ValueError('expected full identity lacks one literal biography Full name field')
        name = full_names[0]
    birthdays = box.select('.bday')
    if len(birthdays) != 1:
        raise ValueError('Wikipedia identity needs one literal birth date')
    birthday = date.fromisoformat(birthdays[0].get_text(strip=True)).isoformat()
    anchor_year = date.fromisoformat(anchor).year
    rows, section, senior_headers = [], None, 0
    for tr in box.select('tr'):
        headers = tr.select('th.infobox-header')
        if headers:
            text = headers[0].get_text(' ', strip=True)
            section = 'senior' if text.rstrip('*').strip() == 'Senior career' else None
            senior_headers += section == 'senior'
            continue
        if section != 'senior':
            continue
        cells = tr.find_all(['th', 'td'], recursive=False)
        if len(cells) < 2:
            continue
        years = cells[0].get_text(' ', strip=True)
        if years in ('Years', 'Total'):
            continue
        match = re.fullmatch(r'(\d{4})(?:[–-](\d{4}))?', years)
        future_ongoing = re.fullmatch(r'(\d{4})[–-]', years)
        if match is None and future_ongoing and int(future_ongoing[1]) > anchor_year:
            # A later ongoing spell cannot overlap the historical anchor.
            # Exclude it explicitly; never invent its exit year or accept an
            # ongoing target-period/current-team row as ownership evidence.
            if not cells[1].get_text(' ', strip=True):
                raise ValueError('future senior spell lacks a club')
            rows.append({'club': cells[1].get_text(' ', strip=True),
                'entry_year': int(future_ongoing[1]), 'departure_year': None,
                'loan': '→' in cells[1].get_text() or '(loan)' in cells[1].get_text().casefold(),
                'future_open_ended_spell_excluded': True})
            continue
        if match is None:
            raise ValueError('unbounded or unsupported Wikipedia senior career years')
        start, end = int(match[1]), int(match[2] or match[1])
        if start > end:
            raise ValueError('Wikipedia senior career years are reversed')
        # The single team cell excludes appearance counts and other sections.
        team = cells[1].get_text(' ', strip=True)
        if not team:
            raise ValueError('Wikipedia senior spell lacks a club')
        loan = '→' in team or '(loan)' in team.casefold()
        team = team.replace('→', '').replace('(loan)', '').strip()
        row = {'club': team, 'entry_year': start, 'departure_year': end, 'loan': loan}
        if allow_entry_month:
            row['club_links'] = [a['href'] for a in cells[1].select('a[href]')]
        rows.append(row)
    year = date.fromisoformat(anchor).year
    possible = [r for r in rows if r['departure_year'] is not None and r['entry_year'] <= year <= r['departure_year']]
    accepted = roster.club_names(country, club)
    accepted |= CLUB_ALIASES.get(country, {}).get(roster.normalise(club), set())
    if (senior_headers != 1 or len(possible) != 1 or possible[0]['loan'] or
            roster.normalise(possible[0]['club']) not in accepted):
        raise ValueError('Wikipedia lacks one unambiguous interior-year senior club owner')
    witness = None
    if not possible[0]['entry_year'] < year < possible[0]['departure_year']:
        if not allow_entry_month or possible[0]['entry_year'] != year or year >= possible[0]['departure_year']:
            raise ValueError('Wikipedia lacks one unambiguous interior-year senior club owner')
        witness = entry_month_witness(page, name, possible[0], anchor)
    policy = MONTH_POLICY if witness else POLICY
    owner = {'policy': policy, 'anchor': anchor, 'owner': possible[0], 'career_rows': rows,
             'exact_transfer_dates_claimed': False, 'exact_matchday_appearance_claimed': False}
    if witness:
        owner['entry_month_witness'] = witness
    return ({'source_provider': 'wikipedia', 'source_player_id': 'wikipedia:' + slug,
        'name': name, 'birth_date': birthday, 'source_profile_url': url,
        'identity_policy': policy,
        'ownership_established_by_biography': False},
        owner)


def entry_month_witness(page, name, owner, anchor):
    """A literal joined-month + exact linked club resolves only an entry year.

    Use the LAST possible day of the published month, never invent a transfer
    day. Exit years, loans, current-team widgets and vague summer prose refuse.
    """
    if len(name.split()) != 2 or len(owner['club_links']) != 1:
        raise ValueError('entry month needs exact person and linked career club')
    club_url = owner['club_links'][0]
    parsed = urlparse(club_url)
    if parsed.netloc not in ('', 'en.wikipedia.org') or not parsed.path.startswith('/wiki/'):
        raise ValueError('entry month club link is not an original Wikipedia club')
    matches = []
    for paragraph in page.select('p'):
        sentence = paragraph.get_text(' ', strip=True).split('.', 1)[0]
        pattern = r'^In (' + '|'.join(calendar.month_name[1:]) + r') (\d{4}), ' + re.escape(name.split()[1]) + r' joined '
        found = re.match(pattern, sentence)
        if not found:
            continue
        links = [a for a in paragraph.select('a[href]')
                 if urlparse(a['href']).path == parsed.path
                 and urlparse(a['href']).netloc in ('', 'en.wikipedia.org')]
        if len(links) != 1 or links[0].get_text(' ', strip=True) not in sentence or 'loan' in sentence.casefold():
            continue
        joined_clause = sentence[found.end():].split(',', 1)[0].strip()
        target = links[0].get_text(' ', strip=True)
        if not re.fullmatch(r"(?:[A-Za-z][A-Za-z -]*\s*['’]s\s+)?" + re.escape(target), joined_clause):
            continue  # a later reference to this club does not establish joining it
        month = list(calendar.month_name).index(found[1]); year = int(found[2])
        latest = date(year, month, calendar.monthrange(year, month)[1])
        if year != owner['entry_year'] or latest >= date.fromisoformat(anchor):
            continue
        matches.append({'published_sentence': sentence, 'paragraph_sha256': hashlib.sha256(str(paragraph).encode()).hexdigest(),
                        'club_path': parsed.path, 'published_month': f'{year:04d}-{month:02d}',
                        'latest_possible_entry': latest.isoformat(), 'exact_transfer_day_claimed': False})
    if len(matches) != 1:
        raise ValueError('entry boundary requires one explicit pre-anchor joined-month witness')
    return matches[0]
