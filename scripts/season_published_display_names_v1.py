"""Use only the publisher's explicit, ID/DOB-bound display aliases.

Full source names remain unchanged. This is not surname guessing or a licence
to truncate arbitrary strings to fit a native carrier.
"""
import copy
import json
from scripts import season_published_person_identity_v1 as people
from scripts import season_release_registry_v1 as registry

POLICY = 'original-explicit-display-short-artist-names-confirmed-person-DOB-v1'
BATCH_KEYS = ('requested_ids', 'source_url', 'raw_path', 'raw_sha256', 'source_receipt_path')


def read_batch(batch):
    if batch['source_url'] != people.url(batch['requested_ids']):
        raise ValueError('display alias original person endpoint differs')
    path = registry.ROOT / batch['raw_path']
    if registry.sha256_file(path) != batch['raw_sha256']:
        raise ValueError('display alias original response changed')
    if json.loads((registry.ROOT / batch['source_receipt_path']).read_text()) != {
            'url': batch['source_url'], 'sha256': batch['raw_sha256']}:
        raise ValueError('display alias original response URL/SHA differs')
    original = json.loads(path.read_text())
    confirmed, _ = people.parse(original, batch['requested_ids'])
    ids = {p['source_player_id']: p for p in confirmed}
    return {int(p['id']): p for p in original['data'] if int(p['id']) in ids}, ids


def explicit_names(raw):
    result = []
    for field in ('displayName', 'shortName', 'artistName'):
        value = raw.get(field)
        if isinstance(value, str) and value.strip() and value.strip() not in [r['name'] for r in result]:
            result.append({'field': field, 'name': value.strip()})
    return result


def claims(path):
    document = json.loads(path.read_text())
    people.merge({}, document)
    result = {}
    for batch in document['batches']:
        if batch['status'] != 'original-entities-parsed':
            continue
        originals, confirmed = read_batch(batch)
        for id, raw in originals.items():
            claim = {'policy': POLICY, 'source_player_id': id,
                'birth_date': confirmed[id]['birth_date'], 'names': explicit_names(raw),
                'original_batch': {k: copy.deepcopy(batch[k]) for k in BATCH_KEYS}}
            if id in result and result[id] != claim:
                raise ValueError('published display alias responses conflict for one person')
            result[id] = claim
    return result


def verify(claim, person):
    if (claim.get('policy') != POLICY or
            (claim.get('source_player_id'), claim.get('birth_date')) !=
            (person['source_player_id'], person['birth_date'])):
        raise ValueError('display alias does not identify the same confirmed person/DOB')
    originals, confirmed = read_batch(claim['original_batch'])
    id = person['source_player_id']
    if id not in originals or confirmed[id]['birth_date'] != person['birth_date']:
        raise ValueError('display alias person/DOB does not reproduce from original response')
    if claim.get('names') != explicit_names(originals[id]):
        raise ValueError('display aliases do not reproduce from explicit original fields')
    return claim['names']


def verify_plan(plan):
    rows = [r for r in plan['updates'] if r.get('published_display_names') is not None]
    if not rows:
        return
    binding = plan['bindings'].get('published_person_supplement')
    if (not plan.get('allow_published_display_aliases') or
            plan['bindings'].get('published_display_policy') != POLICY or not binding):
        raise ValueError('published display aliases require their explicit bound policy')
    path = registry.ROOT / binding['path']
    if registry.sha256_file(path) != binding['sha256']:
        raise ValueError('published display alias input changed')
    originals = claims(path)
    for row in rows:
        claim, person = row['published_display_names'], row['replacement']['source_person']
        if claim != originals.get(person['source_player_id']):
            raise ValueError('display alias claim is not from the bound public person input')
        verify(claim, person)
