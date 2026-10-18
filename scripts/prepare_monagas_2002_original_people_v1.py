"""Bind sixteen dated cup actors to saved publisher person responses.

Annual rows provide independent identity links only. Missing secondary dates
remain explicit gaps. This review does not allocate slots or change a recipe.
"""
import json
import re
import tempfile
from pathlib import Path

from bs4 import BeautifulSoup

from scripts import monagas_2002_original_august_v1 as opening
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as people
from scripts.capture_tachira_2014_original_people_v1 import source_rows

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1'
URL = 'https://www.transfermarkt.es/monagas-sc/kader/verein/14596/saison_id/2001/plus/1/sort/trikotNumber.desc'


def prepare(output):
    if output.exists():
        raise ValueError('original sixteen-person review is immutable')
    with tempfile.TemporaryDirectory(prefix='pm99-monagas2002-original-') as tmp:
        actual = opening.prepare(Path(tmp) / 'opening.json')
    annual_path, raw, annual_binding = source_rows('monagas-2002-original-linked-identity-catalogue')
    receipt = pipeline.read_json_file(annual_path.with_suffix('.source.json'))
    page = BeautifulSoup(raw, 'html.parser')
    if (receipt['url'] != URL or page.title is None or page.title.get_text(' ', strip=True)
            != 'Monagas SC - Plantilla detallada 2002 (Vista en detalle) | Transfermarkt'):
        raise ValueError('original annual identity catalogue club or period differs')
    annual = {}
    for row in page.select('table.items > tbody > tr'):
        links = {a['href']: a.get_text(' ', strip=True)
            for a in row.select('a[href*="/profil/spieler/"]')}
        if not links:
            continue
        if len(links) != 1:
            raise ValueError('original annual identity row ambiguous')
        href, name = next(iter(links.items()))
        id = int(re.search(r'/profil/spieler/(\d+)', href)[1])
        if id in annual:
            raise ValueError('original annual repeats a publisher person ID')
        annual[id] = name
    path = ROOT / 'monagas-2002-original-person-candidates-v1.json'
    document = pipeline.read_json_file(path)
    people.merge({}, document)
    biographies = {row['source_player_id']: row for batch in document['batches'] for row in batch['people']}
    unpublished = {}
    for batch in document['batches']:
        raw_path = registry.ROOT / batch['raw_path']
        if registry.sha256_file(raw_path) != batch['raw_sha256']:
            raise ValueError('original person response changed')
        response = json.loads(raw_path.read_bytes())
        for gap in batch['gaps']:
            if gap['reason'] != 'original-DOB-unpublished-or-unconfirmed':
                continue
            rows = [row for row in response['data'] if str(row.get('id')) == str(gap['player_id'])]
            if (len(rows) != 1 or not re.search(
                    rf'/profil/spieler/{gap["player_id"]}(?:/|$)', rows[0].get('relativeUrl', ''))
                    or not isinstance(rows[0].get('name'), str) or not rows[0]['name'].strip()):
                raise ValueError('unknown birthday has no unique original person ID/name/URL')
            unpublished[gap['player_id']] = dict(name=rows[0]['name'].strip(),
                birth_date=None, source_gap=gap['reason'])
    selected = []
    for group in ('starting_xi', 'used_substitutes', 'unused_substitutes'):
        for actor in actual[group]:
            id = actor['source_player_id']
            person = biographies.get(id, unpublished.get(id))
            if person is None or person['name'] != annual.get(id):
                raise ValueError('dated cup person ID lacks matching original annual and biography names')
            selected.append(dict(source_player_id=id, published_match_name=actor['published_match_name'],
                independent_published_name=person['name'], confirmed_birth_date=person['birth_date'],
                membership=group, source_gap=person.get('source_gap')))
    if len(selected) != 16 or len({row['source_player_id'] for row in selected}) != 16:
        raise ValueError('dated cup source lacks sixteen distinct independently linked people')
    report = dict(schema_version='pm99-original-monagas2002-fixed16-person-links-v1',
        original_opening=actual, people=selected,
        original_bindings=actual['original_bindings'] + [annual_binding,
            dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))],
        missing_secondary_facts=[dict(source_player_id=row['source_player_id'],
            name=row['independent_published_name'], field='birth_date', reason=row['source_gap'])
            for row in selected if row['source_gap']],
        identity_catalogue_scope='Calendar2002 provides IDs only; original August28 fixture alone proves membership.',
        discarded_current_attributes=['roles', 'nationality', 'height', 'weight', 'photos', 'skills', 'club'],
        native_writes=0, closed_duplicate_cases=0, publication_authorised=False,
        remaining=['fixed16 allocation', 'explicit native missing-DOB treatment',
            'dated ground and period kit', 'source/native/identity checks',
            'exact reconstruction', 'actual corrected profile and final startup', 'frozen checkpoint'])
    pipeline.write_canonical_json(output, report)
    return report
