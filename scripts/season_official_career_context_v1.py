"""Reviewed official career and named-fact context for a null annual DOB.

This source-admission policy reuses existing native field writers. It does not
write games, infer missing facts, or replace legacy identity policies.
"""
import hashlib
import inspect
import locale
import os
import re
import shutil
import subprocess
import unicodedata
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from scripts.capture_2015_source_tail_squads_v1 import NATIONALITY_CODES

POLICY = 'annual-source-row-person-identity-null-dob-v1'
COUNTRY_LITERALS = {'schweiz': 'SUI', 'swiss': 'SUI', 'switzerland': 'SUI'}

# Process-local successful-replay memoization. Keys contain the content bindings,
# executable bytes, helper source, extraction mode, and process locale; values
# are immutable bytes from a successful exact extraction only.
_PDF_TEXT_CACHE: OrderedDict[tuple, bytes] = OrderedDict()
_PDF_TEXT_CACHE_MAX = 16


def _pdf_executable_binding():
    found = shutil.which('pdftotext')
    if not found:
        raise FileNotFoundError('pdftotext executable was not found')
    path = Path(found).resolve(strict=True)
    if not path.is_file():
        raise ValueError('pdftotext resolved path is not a regular file')
    raw = path.read_bytes()
    return str(path), hashlib.sha256(raw).hexdigest()


def _helper_code_fingerprint():
    """Bind cache entries to the helper implementation, not a version label."""
    raw = Path(__file__).read_bytes()
    functions = '\n'.join(inspect.getsource(fn) for fn in (_read_binding, _pdf_executable_binding, source_text))
    return hashlib.sha256(raw + functions.encode('utf-8')).hexdigest()


def _locale_fingerprint():
    env = tuple(sorted((key, value) for key, value in os.environ.items()
                       if key == 'LANG' or key.startswith('LC_')))
    return locale.setlocale(locale.LC_ALL, None), env


def _clear_pdf_text_cache():
    _PDF_TEXT_CACHE.clear()


def check_annual_dob(policy, annual_row_dob, biography_dob):
    if policy == POLICY:
        if annual_row_dob is not None:
            raise ValueError('null-DOB identity policy accepts only a null annual DOB')
        if not isinstance(biography_dob, str) or not re.fullmatch(r'\d{4}-\d\d-\d\d', biography_dob):
            raise ValueError('independently sourced exact DOB required')
        from datetime import date
        date.fromisoformat(biography_dob)
        return biography_dob
    if annual_row_dob != biography_dob:
        raise ValueError('legacy annual row DOB must exactly match')
    return biography_dob


def country_code(literal):
    published = str(literal).strip()
    code = NATIONALITY_CODES.get(published)
    if code is None:
        code = COUNTRY_LITERALS.get(published.casefold())
    if code is None:
        raise ValueError('unrecognized explicit nationality literal')
    return code


def _club_key(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().casefold()
    words = re.findall(r'[a-z0-9]+', value)
    while words and words[0] in {'fc', 'football', 'club', 'association'}:
        words.pop(0)
    return ' '.join(words)


def _club_identity_key(value):
    """Normalize spelling only; preserve meaningful name tokens such as FC."""
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().casefold()
    return ' '.join(re.findall(r'[a-z0-9]+', value))


def _visible_text(body):
    page = BeautifulSoup(body, 'lxml')
    for node in page(['script', 'style', 'noscript', 'template']):
        node.decompose()
    return page


def _parse_year_ranges(text):
    found = []
    for m in re.finditer(r'(?<!\d)(19\d{2}|20\d{2})\s*[-–]\s*(\d{2}|(?:19|20)\d{2})(?!\d)', text):
        start = int(m.group(1)); end_text = m.group(2)
        if len(end_text) == 2:
            end = (start // 100) * 100 + int(end_text)
            if end < start:
                end += 100
        else:
            end = int(end_text)
        if end >= start:
            found.append((start, end))
    return found


def _subject_lead_ok(prefix, fullname, source_club):
    """A pronoun such as `them` needs a direct unambiguous club subject lead."""
    club = _club_key(source_club)
    name = ' '.join(re.findall(r'[a-z0-9]+', unicodedata.normalize('NFKD', fullname)
        .encode('ascii', 'ignore').decode().casefold()))
    club_pattern = r'\s+'.join(re.escape(part) for part in club.split())
    name_pattern = r'\s+'.join(re.escape(part) for part in name.split())
    # The selected club must directly govern the subject; a second club in
    # between makes the antecedent ambiguous and therefore refuses the join.
    lead = re.compile(r'(?<!\w)(?:fc\s+)?' + club_pattern
        + r'\s+(?:fc\s+)?(?:boss|coach|manager|captain|defender|player)\s+'
        + name_pattern + r'(?!\w)')
    return bool(lead.search(prefix))


def _career_role_clause(paragraph, fullname, source_club):
    folded = unicodedata.normalize('NFKD', paragraph).encode('ascii', 'ignore').decode().casefold()
    # Treat a sentence as a single supported grammatical subject. A name that
    # appears elsewhere in the paragraph cannot lend its identity to another
    # person's playing clause. The conservative person-name check rejects
    # multi-subject sentence forms that need a richer source-specific parser.
    raw_sentences = re.split(r'(?<=[.!?])\s+', paragraph)
    name = unicodedata.normalize('NFKD', fullname).encode('ascii', 'ignore').decode().casefold()
    named_sentences = [sentence for sentence in raw_sentences
                       if name in unicodedata.normalize('NFKD', sentence).encode('ascii', 'ignore').decode().casefold()]
    if len(named_sentences) != 1:
        return None
    sentence_raw = unicodedata.normalize('NFKD', named_sentences[0]).encode('ascii', 'ignore').decode()
    sentence = sentence_raw.casefold()
    role_match = re.search(r'\bplayed\b.{0,100}\bdefender\b', sentence)
    if not role_match:
        return None
    start = role_match.start()
    role_clause = sentence[start:]
    # Do not let a later coaching/appointment range be borrowed as a playing
    # tenure date, even when it occurs in the same sentence.
    role_clause = re.split(r'\band\s+(?:took charge|became|was appointed|coached|managed|returned as coach)\b',
                           role_clause, maxsplit=1)[0]
    playing_for = re.search(r'\bplayed\s+(?:for|at|with)\s+(.+?)\s+as\s+(?:a\s+)?defender\b', role_clause)
    if not playing_for:
        return None
    prefix = sentence[:start]
    name_end = prefix.find(name) + len(name)
    if name_end < len(name):
        return None
    # A different complete person name in the sentence subject region means the
    # playing predicate cannot safely inherit the target. This also rejects a
    # target mentioned as the object of another person's verb.
    person_spans = re.findall(
        r"\b([A-Z][a-z.'’-]{2,}\s+[A-Z][a-z.'’-]{2,})\s+"
        r"(?:said|told|played|joined|signed|returned|spent|represented|"
        r"was|were|became|coached|managed|captained|served|took)\b",
        sentence_raw[:start + len('played')])
    target_person = ' '.join(name.split())
    other_people = [person for person in person_spans
                    if ' '.join(unicodedata.normalize('NFKD', person).encode('ascii', 'ignore')
                                .decode().casefold().split()) != target_person]
    if other_people:
        return None
    after_name = sentence[name_end:start + len('played')]
    if re.search(r'(?:,\s*(?:then\s+)?|\b(?:and|but|while|whereas|then)\b\s*)'
                 r'(?:he|she|they|the player|the coach|a former player)\s+\w+\b', after_name):
        return None
    # Support only a direct named playing subject or a tightly recognized
    # coordinated career sentence (e.g. “Urs Fischer joined ..., played ...”).
    # Appositive, possessive, and embedded-subject forms need a source-specific
    # parser and are refused rather than inheriting the name by proximity.
    subject_tail = sentence[name_end:]
    direct_subject = re.match(r'\s+played\b', subject_tail)
    coordinated_subject = re.match(
        r'\s+joined\s+the\s+club\s+as\s+(?:a\s+)?youth\s+player\s+in\s+'
        r'(?:the\s+)?(?:early|mid|late)\s+(?:19|20)\d{2}s,\s+played\b',
        subject_tail)
    if not direct_subject and not coordinated_subject:
        return None
    named_club = ' '.join(playing_for.group(1).split()).strip(' ,.;:')
    target_key = _club_key(source_club)
    if named_club.casefold() in {'them', 'the club', 'the side'}:
        if not _subject_lead_ok(prefix, fullname, source_club):
            return None
    elif _club_key(named_club) != target_key:
        return None
    defender_end = re.search(r'\bdefender\b', role_clause)
    if not defender_end:
        return None
    years_clause = role_clause[defender_end.end():]
    return role_clause, years_clause


def _html_subject_text(raw, fullname, source):
    page = _visible_text(raw)
    label = source.get('subject_name_label')
    birth = source['birth_date']
    country = source.get('nationality')
    if not isinstance(label, str) or not label.strip():
        raise ValueError('HTML fact source must specify its exact labeled full-name field')
    # Bind each labeled field to one record row. Flattened ancestor text (even
    # a unique table/div) can contain several people and is not a subject card.
    def row_claim(rows, claim):
        matches = [row for row in rows if claim['label'] + ' ' + claim['literal']
                   in ' '.join(row.get_text(' ', strip=True).replace('|', ' ').split())]
        all_labeled = [row for row in rows if claim['label'] in
                       ' '.join(row.get_text(' ', strip=True).replace('|', ' ').split())]
        if len(matches) != 1 or len(all_labeled) != 1:
            return None
        return matches[0]
    cards=[]
    for table in page.select('table'):
        rows = table.select('tr')
        name_rows = [row for row in rows if label + ' ' + fullname in
                     ' '.join(row.get_text(' ', strip=True).replace('|', ' ').split())]
        all_name_rows = [row for row in rows if label in
                         ' '.join(row.get_text(' ', strip=True).replace('|', ' ').split())]
        birth_row = row_claim(rows, birth)
        country_row = row_claim(rows, country) if country else None
        if (len(name_rows) == 1 and len(all_name_rows) == 1 and birth_row is not None
                and (not country or country_row is not None)):
            cards.append(' '.join(table.get_text(' ', strip=True).split()))
    if len(cards) != 1:
        raise ValueError('HTML full name, DOB and nationality must share one unique single-subject table/card')
    return cards[0]


def approved_official_fact_publisher(source):
    """Allow only the reviewed DFB player-profile and UEFA report routes."""
    parsed = urlsplit(source.get('url', ''))
    if parsed.scheme != 'https' or not parsed.hostname:
        raise ValueError('official fact source must use HTTPS')
    path = parsed.path
    if (parsed.hostname == 'datencenter.dfb.de'
            and re.fullmatch(r'/personen/[a-z0-9-]+/spieler', path)
            and source.get('document_type') != 'application/pdf'):
        return 'dfb-player-profile'
    if (parsed.hostname in {'www.uefa.com', 'uefa.com'}
            and re.fullmatch(r'/MultimediaFiles/Download/uefaorg/General/(?:[0-9]{2}/){3}[0-9]{2}/[0-9]+_DOWNLOAD\.pdf', path, re.I)
            and source.get('document_type') == 'application/pdf'):
        return 'uefa-technical-report-pdf'
    raise ValueError('official fact source publisher/route is not in the reviewed DFB/UEFA families')


def _pdf_subject_text(extracted_text, fullname, claims):
    """Bind facts to one named report card, not a neighboring profile."""
    pages=extracted_text.split('\f')
    matches=[]
    for page in pages:
        lines=page.splitlines()
        name_lines=[i for i,line in enumerate(lines) if line.strip()==fullname]
        for line_index in name_lines:
            # UEFA technical reports lay out each coach as a short sequential
            # card. Stop at the next standalone person name; never borrow a
            # neighboring column/card's DOB or nationality.
            end=min(len(lines),line_index+9)
            for j in range(line_index+1,end):
                candidate=lines[j].strip()
                if re.fullmatch(r"[A-Z][A-Za-zÀ-ÿ.' -]{2,50}",candidate) and not any(
                        candidate.startswith(c['label']) for c in claims):
                    end=j;break
            card=' '.join(' '.join(x.split()) for x in lines[line_index:end] if x.strip())
            if all(c['label'] in card and c['literal'] in card.split(c['label'],1)[1][:120]
                   for c in claims):
                matches.append(card)
    if len(matches)!=1:
        raise ValueError('PDF DOB/nationality labels must align with one exact named subject column')
    return matches[0]


def verify_official_career_context(body: bytes, *, source_url: str, source_sha256: str,
                                   receipt: dict, fullname: str, source_club: str,
                                   target_season: str):
    """Require a named, same-context club-playing career range and role."""
    if hashlib.sha256(body).hexdigest() != source_sha256:
        raise ValueError('career source original-body digest differs')
    parsed = urlsplit(source_url)
    if parsed.scheme != 'https' or parsed.hostname not in {'www.uefa.com', 'uefa.com'}:
        raise ValueError('career context must be from official UEFA publication')
    if (receipt.get('url') != source_url or receipt.get('raw_sha256') != source_sha256
            or receipt.get('http_status') != 200 or receipt.get('method') != 'original-network-body'):
        raise ValueError('career source URL/body receipt differs')
    page = _visible_text(body)
    full = ' '.join(page.get_text(' ', strip=True).split())
    club_key = _club_key(source_club)
    # Match the club phrase with an optional governing prefix such as FC. The
    # actor's exact source name and club spelling are passed from bound inputs.
    paragraphs = [' '.join(p.get_text(' ', strip=True).split()) for p in page.select('p,li')]
    relevant = []
    for paragraph in paragraphs:
        folded = unicodedata.normalize('NFKD', paragraph).encode('ascii', 'ignore').decode().casefold()
        if fullname.casefold() not in paragraph.casefold():
            continue
        parsed_clause=_career_role_clause(paragraph,fullname,source_club)
        if parsed_clause is None:
            continue
        role_clause,years_clause=parsed_clause
        if not _parse_year_ranges(years_clause):
            continue
        relevant.append((paragraph, role_clause, years_clause))
    if len(relevant) != 1:
        raise ValueError('one named player/target-club/defender career paragraph required')
    year = int(target_season[:4])
    paragraph, role_clause, years_clause = relevant[0]
    ranges = _parse_year_ranges(years_clause)
    # With year-only bounds, require coverage through the following calendar
    # year so a tenure that ended early in the target year cannot be mistaken
    # for August-start-season membership.
    if not any(start < year < end for start, end in ranges):
        raise ValueError('year-only career bounds must bracket the target season year')
    return {'full_name': fullname, 'source_club': source_club,
            'target_season': target_season, 'role_literal': 'defender',
            'career_ranges': [list(x) for x in ranges], 'source_url': source_url,
            'source_sha256': source_sha256, 'matched_paragraph': paragraph,
            'matched_role_clause': role_clause, 'matched_career_years_clause': years_clause}


def _read_binding(binding):
    if not isinstance(binding, dict) or not isinstance(binding.get('path'), str):
        raise ValueError('retained source binding malformed')
    from scripts import season_release_registry_v1 as registry
    path = registry.ROOT / binding['path']
    if (Path(binding['path']).is_absolute() or not path.resolve().is_relative_to(registry.ROOT.resolve())
            or path.is_symlink() or not path.is_file()):
        raise ValueError('retained source path must be a regular workspace file')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding.get('sha256'):
        raise ValueError('retained source digest differs')
    return path, raw


def source_text(source):
    # Re-read both pinned inputs before every cache lookup. In particular, a
    # warm result never masks a changed body/text file or a new symlink path.
    path, raw = _read_binding(source)
    if source.get('document_type') != 'application/pdf':
        return ' '.join(_visible_text(raw).get_text(' ', strip=True).replace('|', ' ').split())
    extraction = source.get('text_extraction')
    text_path, text_raw = _read_binding(extraction)
    mode = extraction.get('extractor_mode')
    if mode not in {'-raw', '-layout'}:
        raise ValueError('PDF text extraction mode must be explicitly allowed')
    executable_path, executable_sha256 = _pdf_executable_binding()
    helper_sha256 = _helper_code_fingerprint()
    key = (source['sha256'], extraction['sha256'], mode, executable_path,
           executable_sha256, helper_sha256, _locale_fingerprint())
    cached = _PDF_TEXT_CACHE.get(key)
    if cached is not None:
        _PDF_TEXT_CACHE.move_to_end(key)
        return cached.decode('utf-8')
    result = subprocess.run([executable_path, mode, str(path), '-'], capture_output=True, check=True).stdout
    if result != text_raw:
        raise ValueError('pinned PDF text extraction is not reproducible from bound original PDF')
    # Decode before insertion so malformed output cannot become a successful
    # cache entry. Both stored bytes and returned strings are immutable.
    decoded = result.decode('utf-8')
    _PDF_TEXT_CACHE[key] = bytes(result)
    _PDF_TEXT_CACHE.move_to_end(key)
    while len(_PDF_TEXT_CACHE) > _PDF_TEXT_CACHE_MAX:
        _PDF_TEXT_CACHE.popitem(last=False)
    return decoded


def verify_official_career_contexts(witness, annual, *, source_club=None):
    contexts = witness.get('official_career_contexts')
    if not isinstance(contexts, list) or len(contexts) != 1:
        raise ValueError('one explicit official career-context source required')
    context = contexts[0]
    _, body = _read_binding(context['body'])
    receipt_path, receipt_raw = _read_binding(context['receipt'])
    from scripts import season_pipeline_v2 as pipeline
    receipt = pipeline.read_json_file(receipt_path)
    target_club = source_club if source_club is not None else annual['selector']['club_name']
    return [verify_official_career_context(body, source_url=context['url'],
        source_sha256=context['sha256'], receipt=receipt, fullname=witness['full_name'],
        source_club=target_club, target_season=annual['season'])]


def verify_official_source_claims(witness):
    """Annual identity must already pass; parse only named official fact sources."""
    from datetime import datetime, date
    from scripts import season_pipeline_v2 as pipeline
    from scripts.season_adjudicated_player_facts_v1 import _literal_day_birthday
    sources = witness.get('official_sources')
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValueError('two independent official fact sources required')
    hosts = {urlsplit(s.get('url', '')).hostname for s in sources}
    if len(hosts) != len(sources) or None in hosts:
        raise ValueError('official DOB/nationality fact sources require distinct hosts')
    families = {approved_official_fact_publisher(source) for source in sources}
    if families != {'dfb-player-profile', 'uefa-technical-report-pdf'}:
        raise ValueError('official fact evidence requires one approved DFB profile and one UEFA report')
    birthdays, countries = [], []
    for source in sources:
        body_path, _ = _read_binding({'path': source['path'], 'sha256': source['sha256']})
        receipt_path, _ = _read_binding(source['receipt'])
        receipt = pipeline.read_json_file(receipt_path)
        if receipt.get('url') != source['url'] or receipt.get('raw_sha256') != source['sha256']:
            raise ValueError('official fact source raw URL/hash receipt differs')
        if (receipt.get('final_url') != source['url'] or receipt.get('http_status') != 200
                or receipt.get('method') not in {'original-network-body', 'original-network-body-pdf'}):
            raise ValueError('official fact source receipt is not a successful original network body')
        parsed = urlsplit(source['url'])
        if parsed.scheme != 'https' or not parsed.hostname:
            raise ValueError('official fact source must be HTTPS')
        text = source_text(source)
        claim = source['birth_date']
        claims=[claim] + ([source['nationality']] if source.get('nationality') else [])
        if source.get('document_type') == 'application/pdf':
            text = _pdf_subject_text(text,witness['full_name'],claims)
        else:
            text = _html_subject_text(body_path.read_bytes(),witness['full_name'],source)
        if witness['full_name'] not in text:
            raise ValueError('official fact source subject context does not name the exact person')
        if claim['label'] + ' ' + claim['literal'] not in ' '.join(text.replace('|',' ').split()):
            raise ValueError('published birthday label/literal absent from named official subject context')
        birthdays.append(_literal_day_birthday(claim))
        country = source.get('nationality')
        if country:
            if country['label'] + ' ' + country['literal'] not in ' '.join(text.replace('|',' ').split()):
                raise ValueError('published nationality label/literal absent; birthplace is not nationality')
            if country_code(country['literal']) != country['code']:
                raise ValueError('explicit nationality literal does not map to declared code')
            countries.append(country['code'])
    values = witness['values']
    date.fromisoformat(values['birth_date'])
    if (set(values) != {'birth_date', 'nationality'} or set(birthdays) != {values['birth_date']}
            or set(countries) != {values['nationality']}):
        raise ValueError('independent official DOB/nationality facts disagree')
    return dict(values)
