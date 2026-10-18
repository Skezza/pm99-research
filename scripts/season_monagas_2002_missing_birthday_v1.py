"""Known original person IDs with explicitly unpublished secondary birthdays.

Do not modify the established biography parser or pretend a native carrier's
date belongs to the new person. This narrow adapter reparses dated membership,
the original annual ID links and the raw publisher's missing-date flags.
"""
import json
import tempfile
from pathlib import Path

from scripts import prepare_monagas_2002_original_people_v1 as source
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry

POLICY = 'original-Monagas2002-person-ID-and-explicit-unpublished-DOB-v1'


def from_row(row, bindings):
    if row.get('source_gap') != 'original-DOB-unpublished-or-unconfirmed' or row.get('confirmed_birth_date') is not None:
        raise ValueError('missing-birthday policy cannot replace a known source date')
    return dict(source_player_id=row['source_player_id'], name=row['independent_published_name'],
        given_name=None, family_name=None, birth_date=None, source_provider='transfermarkt',
        identity_policy=POLICY, identity_evidence=dict(original_bindings=bindings, opening_actor=row))


def verify(person):
    if person.get('identity_policy') != POLICY:
        raise ValueError('unknown birthday lacks explicit original missing-date policy')
    with tempfile.TemporaryDirectory(prefix='pm99-monagas-missing-date-') as temporary:
        original = source.prepare(Path(temporary) / 'original-links.json')
    rows = [row for row in original['people'] if row['source_player_id'] == person.get('source_player_id')]
    if len(rows) != 1 or person != from_row(rows[0], original['original_bindings']):
        raise ValueError('unknown-birthday person changes original membership, name, ID, source or missing date')
    return 'person-transfermarkt-' + str(person['source_player_id'])


def display_candidates(person):
    """Use exact publisher short names despite an unpublished secondary DOB."""
    verify(person)
    document = pipeline.read_json_file(source.ROOT / 'monagas-2002-original-person-candidates-v1.json')
    candidates = []
    for batch in document['batches']:
        path = registry.ROOT / batch['raw_path']
        if registry.sha256_file(path) != batch['raw_sha256']:
            raise ValueError('original unknown-DOB display source changed')
        rows = [row for row in json.loads(path.read_bytes())['data']
                if str(row.get('id')) == str(person['source_player_id'])]
        if not rows:
            continue
        if len(rows) != 1 or rows[0].get('name') != person['name']:
            raise ValueError('original unknown-DOB alias identifies another person')
        for field in ['shortName', 'artistName', 'displayName']:
            name = rows[0].get(field)
            if isinstance(name, str) and name.strip():
                candidates.append(dict(name=name.strip(), method='original-explicit-unknown-DOB-' + field))
    return candidates
