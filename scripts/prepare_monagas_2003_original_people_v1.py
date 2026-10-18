"""Join fixed16 original match labels; log missing DOBs without inventing them.

Source-only evidence. An annual row supplies an identity link, never proves
opening membership or licenses importing current roles, citizenship or photos.
"""
import copy
import json
import re

from bs4 import BeautifulSoup

from scripts import monagas_2003_original_august_v1 as opening
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as people
from scripts.capture_tachira_2014_original_people_v1 import source_rows

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1'
URL = 'https://www.transfermarkt.es/monagas-sc/kader/verein/14596/saison_id/2002/plus/1/sort/trikotNumber.desc'
# Deliberate, retained source spelling disagreements, not fuzzy matching.
LABELS = {'Hugo Luzardi': 'Hugo Lusardi', 'Jhony Alejo': 'Johny Alejo'}


def prepare(output):
    if output.exists():
        raise ValueError('original fixed16 identity review is immutable')
    _, raw, match_binding = source_rows('venezuela-2002-2003-original-RSSSF-Sudamericana-lineups')
    actual = opening.parse(raw)
    path, raw, annual_binding = source_rows('monagas-2003-original-linked-identity-catalogue')
    receipt = pipeline.read_json_file(path.with_suffix('.source.json'))
    page = BeautifulSoup(raw, 'html.parser')
    if (receipt['url'] != URL or page.title is None or page.title.get_text(' ', strip=True)
            != 'Monagas SC - Plantilla detallada 2003 (Vista en detalle) | Transfermarkt'):
        raise ValueError('original identity catalogue club, URL or period differs')
    links = {}
    for row in page.select('table.items > tbody > tr'):
        names = {a['href']: a.get_text(' ', strip=True)
                 for a in row.select('a[href*="/profil/spieler/"]')}
        if not names:
            continue
        if len(names) != 1:
            raise ValueError('original identity row identifies multiple people')
        href, name = next(iter(names.items()))
        key = roster.normalise(name)
        if key in links:
            raise ValueError('original club has ambiguous same-name identity links')
        links[key] = dict(id=int(re.search(r'/profil/spieler/(\d+)', href)[1]), name=name)
    document_path = ROOT / 'monagas-2003-original-person-candidates-v1.json'
    document = pipeline.read_json_file(document_path)
    people.merge({}, document)  # Reparse saved original responses, including gaps.
    biographies = {person['source_player_id']: person
                  for batch in document['batches'] for person in batch['people']}
    unconfirmed = {}
    for batch in document['batches']:
        raw_path = registry.ROOT / batch['raw_path']
        if registry.sha256_file(raw_path) != batch['raw_sha256']:
            raise ValueError('original biography response changed')
        response = json.loads(raw_path.read_bytes())
        for gap in batch['gaps']:
            if gap['reason'] != 'original-DOB-unpublished-or-unconfirmed':
                continue
            rows = [row for row in response['data'] if str(row.get('id')) == str(gap['player_id'])]
            if len(rows) != 1:
                raise ValueError('missing DOB has no unique original person entity')
            row = rows[0]
            if (not re.search(rf'/profil/spieler/{gap["player_id"]}(?:/|$)', row.get('relativeUrl', ''))
                    or not isinstance(row.get('name'), str) or not row['name'].strip()):
                raise ValueError('missing DOB entity lacks original ID, URL or name')
            unconfirmed[gap['player_id']] = dict(name=row['name'].strip(), birth_date=None,
                source_player_id=gap['player_id'], original_person_batch=copy.deepcopy(batch),
                source_gap=gap['reason'])
    result = []
    for group in ['starting_xi', 'used_substitutes', 'additional_opening_people']:
        for actor in actual[group]:
            label = actor['published_match_name']
            key = roster.normalise(LABELS.get(label, label))
            if key not in links:
                raise ValueError('original match label lacks an independently published identity link')
            link = links[key]
            person = biographies.get(link['id'], unconfirmed.get(link['id']))
            if person is None or roster.normalise(person['name']) != key:
                raise ValueError('independent biography differs from explicit published identity link')
            result.append(dict(published_match_name=label, membership=group,
                source_player_id=link['id'], independent_published_name=person['name'],
                confirmed_birth_date=person['birth_date'],
                source_gap=person.get('source_gap'),
                spelling_disagreement=dict(match_label=label, publisher_label=link['name'],
                    disposition='Explicit original label disagreement retained; no general fuzzy-name rule.')
                    if label in LABELS else None))
    if len(result) != 16 or len({person['source_player_id'] for person in result}) != 16:
        raise ValueError('opening source union is not sixteen distinct publisher identities')
    gaps = [dict(source_player_id=row['source_player_id'], name=row['independent_published_name'],
                 field='birth_date', reason=row['source_gap']) for row in result if row['source_gap']]
    report = dict(schema_version='pm99-original-monagas2003-fixed16-person-links-v1',
        original_opening=actual, original_bindings=[match_binding, annual_binding,
            dict(path=registry.relative_workspace_path(document_path), sha256=registry.sha256_file(document_path))],
        people=result, missing_secondary_facts=gaps,
        identity_catalogue_scope='Calendar2003 identity links only; displayed ages ignored. Dated matches alone establish opening membership.',
        discarded_current_attributes=['nationality', 'positions', 'club', 'portrait', 'ratings', 'shirt number'],
        native_writes=0, closed_duplicate_cases=0, publication_authorised=False,
        remaining=['source-bound explicit unknown-DOB native policy', 'fixed native allocation and outside-owner checks',
            'period kit', 'dated manager native mapping', 'full exact replay', 'actual runner', 'final checkpoint'])
    pipeline.write_canonical_json(output, report)
    return report


if __name__ == '__main__':
    result = prepare(ROOT / 'monagas-2003-original16-identity-links-v1.json')
    print(dict(people=len(result['people']), missing_birthdays=len(result['missing_secondary_facts']), native_writes=0), flush=True)
