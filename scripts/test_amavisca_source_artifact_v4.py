"""Exercise the actual publisher artifact writer without historical binaries."""
import copy
import hashlib

import pytest

from scripts import publish_historical_role_delta_v1 as publisher
from scripts import season_amavisca_retirement_xi_r194_v4 as source
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline


def plan():
    document = {'schema': 'fixture', 'names': ['José', 'Frédson']}
    return {'schema': source.SCHEMA, 'source_plan_artifact': {
        'filename': source.SOURCE_PLAN_FILENAME,
        'artifact_id': source.SOURCE_PLAN_ARTIFACT_ID,
        'document': document,
        'sha256': hashlib.sha256(packages.canonical_json_bytes(document)).hexdigest()}}


def test_publisher_writes_exact_recipe_artifact_encoding(tmp_path):
    value = plan()
    target = publisher._write_amavisca_source_artifact(tmp_path, value)
    assert target.read_bytes() == packages.canonical_json_bytes(value['source_plan_artifact']['document'])
    assert hashlib.sha256(target.read_bytes()).hexdigest() == value['source_plan_artifact']['sha256']
    with pytest.raises(ValueError, match='must not be overwritten'):
        publisher._write_amavisca_source_artifact(tmp_path, value)


@pytest.mark.parametrize('field,value', [
    ('filename', '../outside.json'), ('artifact_id', 'wrong-source'),
    ('sha256', '0' * 64)])
def test_publisher_refuses_unbound_artifact_before_writing(tmp_path, field, value):
    damaged = copy.deepcopy(plan())
    damaged['source_plan_artifact'][field] = value
    with pytest.raises(ValueError, match='binding differs'):
        publisher._write_amavisca_source_artifact(tmp_path, damaged)
    assert list(tmp_path.iterdir()) == []


def test_publisher_refuses_hash_without_written_newline(tmp_path):
    value = plan()
    value['source_plan_artifact']['sha256'] = hashlib.sha256(
        pipeline.canonical_json_bytes(value['source_plan_artifact']['document'])).hexdigest()
    with pytest.raises(ValueError, match='binding differs'):
        publisher._write_amavisca_source_artifact(tmp_path, value)
    assert list(tmp_path.iterdir()) == []
