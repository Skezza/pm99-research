"""Resolve a static birthday conflict; preserve the contrary period source."""
from datetime import date
import re
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as identities
from scripts.capture_tachira_2014_original_people_v1 import source_rows

KEYS = ['italchacao-2001-bidoglio-original-2020-interview',
    'italchacao-2001-bidoglio-original-wikipedia',
    'italchacao-2001-original-official-bidoglio-profile']


def parse(interview_raw, wikipedia_raw, period_raw):
    for raw in (interview_raw, wikipedia_raw, period_raw):
        if not isinstance(raw, bytes) or len(raw) > 2 * 1024 ** 2:
            raise ValueError('unexpected original birthday payload')
    interview = BeautifulSoup(interview_raw, 'html.parser')
    wikipedia = BeautifulSoup(wikipedia_raw, 'html.parser')
    period = BeautifulSoup(period_raw.decode('cp1252', errors='replace').replace('ï¿½', '�'), 'html.parser')
    if ([h.get_text(' ', strip=True) for h in interview.select('h1')]
            != ['Héctor Pablo Bidoglio, un rosarino con corazón Vinotinto']
            or {t.get('datetime') for t in interview.select('time')} != {'2020-04-15T07:00:38-04:00'}):
        raise ValueError('independent original interview identity/date changed')
    paragraphs = [p.get_text(' ', strip=True) for p in interview.select('p')
        if p.get_text(' ', strip=True).startswith('El texto del que')]
    if len(paragraphs) != 1:
        raise ValueError('original interview birthday paragraph missing or ambiguous')
    dates = re.findall(r'Héctor Pablo Bidoglio, mediocampista que nace un (\d+) de febrero de (\d{4})', paragraphs[0])
    if len(dates) != 1:
        raise ValueError('interview birthday identity missing or ambiguous')
    born = date(int(dates[0][1]), 2, int(dates[0][0])).isoformat()
    if [h.get_text(' ', strip=True) for h in wikipedia.select('h1')] != ['Héctor Bidoglio']:
        raise ValueError('independent original biography names another person')
    rows = [r.get_text(' ', strip=True) for r in wikipedia.select('table.infobox tr')
        if r.get_text(' ', strip=True).startswith('Nacimiento ')]
    if len(rows) != 1 or len(re.findall(r'(\d+) de febrero de (\d{4})', rows[0])) != 1:
        raise ValueError('independent biography birthday missing or ambiguous')
    day, year = re.findall(r'(\d+) de febrero de (\d{4})', rows[0])[0]
    if date(int(year), 2, int(day)).isoformat() != born:
        raise ValueError('independent original birthdays disagree')
    if ([c.get_text(' ', strip=True) for c in period.select('td') if 'Bidoglio' in c.get_text()]
            != ['H�ctor Pablo Bidoglio']
            or [c.get_text(' ', strip=True) for c in period.select('td')
                if re.fullmatch(r'\d{2}/\d{2}/\d{4}', c.get_text(' ', strip=True))] != ['15/02/1968']):
        raise ValueError('contrary original period identity/date changed')
    if born != '1968-02-05':
        raise ValueError('reviewed static birthday changed')
    return dict(source_player_id=347836, published_full_name='Héctor Pablo Bidoglio',
        birth_date=born, contrary_period_birth_date='1968-02-15',
        birthday_approved=True,
        basis='Original independent interview and biography agree with original published person API; contrary period value retained, not silently overwritten.',
        approves_opening_membership=False, approves_current_roles=False, native_writes=0)


if __name__ == '__main__':
    root = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1'
    originals = [source_rows(key) for key in KEYS]
    result = parse(*(row[1] for row in originals))
    person_path = root / 'italchacao-2001-original-person-candidates-v1.json'
    document = pipeline.read_json_file(person_path)
    identities.merge({}, document)
    people = [p for batch in document['batches'] for p in batch['people'] if p['source_player_id'] == 347836]
    if len(people) != 1 or people[0]['birth_date'] != result['birth_date'] or people[0]['name'] != 'Héctor Bidoglio':
        raise ValueError('original published person identity/birthday disagrees')
    result.update(original_bindings=[row[2] for row in originals] + [dict(
        path=registry.relative_workspace_path(person_path), sha256=registry.sha256_file(person_path))],
        closed_duplicate_cases=0, publication_authorised=False)
    output = root / 'bidoglio-original-birthday-resolution-v1.json'
    if output.exists():
        if pipeline.read_json_file(output) != result:
            raise ValueError('immutable birthday resolution differs')
    else:
        pipeline.write_canonical_json(output, result)
    print(dict(source_player_id=347836, birthday_approved=True, native_writes=0, duplicates_closed=0), flush=True)
