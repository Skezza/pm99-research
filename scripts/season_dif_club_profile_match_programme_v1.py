"""Typed parsers for retained official DIF player profiles and match programmes.

This adapter supports the publisher's explicit labelled profile card
and the original layout-preserving match-programme player block. Callers bind
the full source body, transport receipt, period selector and exact subject.
"""
from __future__ import annotations

import hashlib
import calendar
import re
import unicodedata
from datetime import date
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

SWEDISH_MONTHS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'maj': 5, 'jun': 6,
                  'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dec': 12}


def _text(body: bytes):
    page = BeautifulSoup(body, 'lxml')
    for node in page(['script', 'style', 'noscript', 'template']):
        node.decompose()
    return page


def _fold(value: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFKD', value).casefold()
                   if not unicodedata.combining(ch))


def _name_slug(fullname: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', _fold(fullname)).strip('-')


def parse_dif_player_profile(body: bytes, *, url: str, fullname: str) -> dict:
    """Return DOB/nationality/position claims from one explicit DIF profile card."""
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname != 'www.dif.se'
            or not re.fullmatch(r'/spelare/herrar/[0-9]{4}-[0-9]{4}/[a-z0-9-]+', parsed.path)
            or parsed.path.rsplit('/', 1)[-1] != _name_slug(fullname)):
        raise ValueError('official DIF profile host, typed route or name slug differs')
    page = _text(body)
    headings = [node.get_text(' ', strip=True) for node in page.select('h1,h2,h3')
                if node.get_text(' ', strip=True) == fullname]
    if headings != [fullname]:
        raise ValueError('official DIF profile requires one exact full-name heading')
    labels = ('Född', 'Nationalitet', 'Position', 'Säsonger i DIF')
    candidates = [node for node in page.select('article,section,table,dl,div')
                  if fullname in node.get_text(' ', strip=True)
                  and all(label in ' '.join(node.get_text(' ', strip=True).split()) for label in labels)]
    minimal = [node for node in candidates
               if not any(child is not node and node in child.parents for child in candidates)]
    if len(minimal) != 1:
        raise ValueError('DIF profile needs one unique single-subject labeled fact card')
    card = ' '.join(minimal[0].get_text(' ', strip=True).split())
    match = re.search(r'\bFödd\s+(\d{1,2})\s+([a-zåäö]{3,})\.?\s+(\d{4})\b', card, re.I)
    if not match:
        raise ValueError('DIF profile lacks a literal full day/month/year DOB')
    month_key = _fold(match.group(2))[:3]
    if month_key not in SWEDISH_MONTHS:
        raise ValueError('DIF profile DOB month literal is unsupported')
    try:
        birthday = date(int(match.group(3)), SWEDISH_MONTHS[month_key], int(match.group(1))).isoformat()
    except ValueError as exc:
        raise ValueError('DIF profile DOB is not a valid calendar date') from exc

    def value(label):
        return re.search(re.escape(label) + r'\s+(.+?)(?=\s+(?:'
            + '|'.join(map(re.escape, labels)) + r')\s|$)', card, re.I)
    nationality, position, seasons = (value(label) for label in labels[1:])
    if not nationality or not position or not seasons:
        raise ValueError('DIF profile lacks one or more exact labeled fields')
    return {'full_name': fullname, 'birth_date': birthday,
            'nationality_literal': nationality.group(1).strip(' .'),
            'position_literal': position.group(1).strip(' .'),
            'club_seasons_literal': seasons.group(1).strip(' .'),
            'profile_card': card, 'body_sha256': hashlib.sha256(body).hexdigest()}


def parse_match_programme_player_block(text: str, fullname: str) -> dict:
    """Read one named player block in the same layout column as its claims."""
    lines = text.splitlines()
    header_re = re.compile(re.escape(fullname)
        + r'\s+-\s+Position:\s*([^.]*)\.\s*Date of birth:\s*$', re.I)
    headers = [(i, line, header_re.search(line)) for i, line in enumerate(lines)
               if header_re.search(line)]
    if len(headers) != 1:
        raise ValueError('match programme needs one unique exact-name position/DOB block')
    index, header, match = headers[0]
    start = match.start()
    later_starts = []
    for line in lines[index:index + 5]:
        later_starts.extend(m.start(1) for m in re.finditer(r'\s{3,}(\S)', line)
                            if m.start(1) > start + 20)
    boundary = min(later_starts) if later_starts else None
    column = []
    for line in lines[index:index + 5]:
        piece = line[start:boundary] if boundary is not None and len(line) > start else line[start:]
        column.append(piece.strip())
    block = ' '.join(' '.join(column).split())
    date_match = re.search(r'\bDate of birth:\s*([A-Z][a-z]+)\s+(\d{1,2})(st|nd|rd|th),\s*(\d{4})\b', block)
    if not date_match:
        raise ValueError('match programme named block lacks a complete ordinal DOB')
    month, day, _, year = date_match.groups()
    try:
        birthday = date(int(year), list(calendar.month_name).index(month), int(day)).isoformat()
    except (ValueError, IndexError) as exc:
        raise ValueError('match programme DOB is not a valid calendar date') from exc
    position = match.group(1).strip()
    if position.casefold() not in {'goalkeeper', 'defender', 'midfielder', 'forward'}:
        raise ValueError('match programme role literal is unsupported')
    return {'full_name': fullname, 'birth_date': birthday, 'position_literal': position,
            'person_block': block}
