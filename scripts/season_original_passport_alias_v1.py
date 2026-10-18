"""Read only an exact person's published full passport NAME from retained JSON.

Current nationalities, teams and all other mutable data are deliberately unused.
A passport-name alias can bridge two full published names only with exact
original numerical ID and DOB, URL/receipt/body hashes and reparsed identities.
"""
from pathlib import Path

from scripts import season_published_person_identity_v1 as persons
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_exact_fifa_role_delta_v1 as fifa

DOCUMENT = registry.ROOT / '.local/duplicate-ownership-v3/published-person-identities-r2.json'


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def parse_person(raw, person):
    if (int(raw['id']) != person['source_player_id'] or raw.get('name') != person['name']
            or raw.get('lifeDates', {}).get('dateOfBirth') != person['birth_date']
            or raw['lifeDates'].get('isDateOfBirthUnknown') is not False):
        raise ValueError('passport alias original numerical ID/full name/DOB differs')
    alias = raw.get('nationalityDetails', {}).get('passportName')
    # Initial-only strings must not become a full-name identity bridge.
    if not isinstance(alias, str) or not fifa.names(dict(name=alias)):
        return None
    return alias.strip()


def original_alias(person, *, document_path=DOCUMENT):
    path = Path(document_path)
    document = pipeline.read_json_file(path)
    if document.get('schema_version') != persons.SCHEMA or document.get('policy') != persons.POLICY:
        raise ValueError('unsupported original person document for passport-name alias')
    hits = []
    for batch in document['batches']:
        if batch['status'] != 'original-entities-parsed' or person['source_player_id'] not in batch['requested_ids']:
            continue
        raw_path = registry.ROOT / batch['raw_path']
        receipt_path = registry.ROOT / batch['source_receipt_path']
        if (registry.sha256_file(raw_path) != batch['raw_sha256']
                or batch['source_url'] != persons.url(batch['requested_ids'])
                or pipeline.read_json_file(receipt_path) != dict(url=batch['source_url'], sha256=batch['raw_sha256'])):
            raise ValueError('original passport-name response URL/body/receipt changed')
        raw = pipeline.read_json_file(raw_path)
        parsed, gaps = persons.parse(raw, batch['requested_ids'])
        if parsed != batch['people'] or gaps != batch['gaps']:
            raise ValueError('original passport-name identity batch does not reparse')
        identities = [p for p in parsed if p['source_player_id'] == person['source_player_id']]
        if identities != [person]:
            raise ValueError('passport-name original identity differs from historical actor')
        records = [r for r in raw['data'] if int(r['id']) == person['source_player_id']]
        if len(records) != 1:
            raise ValueError('passport-name numerical person is not unique')
        alias = parse_person(records[0], person)
        if alias is not None:
            hits.append(dict(name=alias, original_person=person, original_source=binding(raw_path),
                original_receipt=binding(receipt_path), document=binding(path),
                current_country_club_position_and_photos_used=False))
    if len(hits) > 1:
        raise ValueError('passport alias has multiple source batches; resolve explicitly')
    return hits[0] if hits else None
