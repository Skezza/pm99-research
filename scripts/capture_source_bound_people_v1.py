"""Acquire explicit IDs from bound originals using the unchanged person reader.

Read-only acquisition, not ownership approval. Keep this orchestration apart
from the established parser: changing its implementation hash would needlessly
disturb older source-bound release reconstructions.
"""
import hashlib
import json
from urllib.request import Request, urlopen

from scripts import season_published_person_identity_v1 as people
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.season_art_transaction_v1 import atomic_bytes


def capture_ids(ids, cache, output, inputs):
    if output.exists():
        raise ValueError('person evidence is immutable')
    if not ids or any(type(id) is not int or id < 1 for id in ids):
        raise ValueError('acquisition requires explicit positive original publisher IDs')
    requested = sorted(set(ids))
    if len(requested) > 100 or not inputs:
        raise ValueError('one bounded original-source query required')
    for source in inputs:
        if registry.sha256_file(registry.ROOT / source['path']) != source['sha256']:
            raise ValueError('original person query source changed')
    url = people.url(requested)
    key = hashlib.sha256(url.encode()).hexdigest()
    path = cache / 'people' / (key + '.json')
    receipt = path.with_suffix('.source.json')
    if path.exists():
        raw = path.read_bytes()
        if pipeline.read_json_file(receipt) != dict(url=url, sha256=hashlib.sha256(raw).hexdigest()):
            raise ValueError('retained original people URL/hash differs')
    else:
        with urlopen(Request(url, headers={'Accept': 'application/json',
                'Accept-Language': 'en-GB', 'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
            if response.geturl() != url:
                raise ValueError('original biography query redirected to another endpoint')
            raw = response.read(3 * 1024 * 1024 + 1)
        if len(raw) > 3 * 1024 * 1024:
            raise ValueError('original biography response exceeds bounded size')
        json.loads(raw)
        atomic_bytes(path, raw)
        pipeline.write_canonical_json(receipt, dict(url=url, sha256=hashlib.sha256(raw).hexdigest()))
    parsed, gaps = people.parse(json.loads(raw), requested)
    for source in inputs:
        if registry.sha256_file(registry.ROOT / source['path']) != source['sha256']:
            raise ValueError('original biography query source changed during acquisition')
    result = dict(schema_version=people.SCHEMA, policy=people.POLICY,
        historical_opening_inputs=inputs, batches=[dict(status='original-entities-parsed',
            requested_ids=requested, source_url=url, raw_path=registry.relative_workspace_path(path),
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            source_receipt_path=registry.relative_workspace_path(receipt), people=parsed, gaps=gaps)],
        discarded_fields=['current club', 'nationality', 'positions', 'shirt number',
            'market value', 'ratings', 'contemporary portrait'])
    # Independently reparse the saved original before exposing a source ledger.
    people.merge({}, result)
    pipeline.write_canonical_json(output, result)
    return result
