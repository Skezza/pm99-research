"""Local evidence regression: cached proofs must not bypass original validation."""
import copy
import pytest
from scripts import verify_city_opening_runtime_20261011 as subject


@pytest.fixture
def original_profile():
    root = subject.registry.ROOT / '.local/consolidated-audit-20261009/haladas2000-period-kit-delivery-v1'
    if not (root / 'kurucsai-native-runtime-proof.json').exists():
        pytest.skip('retained local original profile evidence unavailable')
    return root


def verify(root):
    subject.verify_profiles(root, '2000-01', 'sourced-haladas-period-kit-20261017-r148a',
                            ((8507, 'kurucsai', '', 'Kurucsai'),))


def test_cached_proof_rechecks_actual_pixels(original_profile, monkeypatch):
    monkeypatch.setattr(subject, 'compare', lambda *args: dict(passed=False))
    with pytest.raises(ValueError, match='displayed kit differs'):
        verify(original_profile)


def test_cached_proof_rechecks_transport(original_profile, monkeypatch):
    reader = subject.pipeline.read_json_file
    def read(path):
        data = reader(path)
        if path == original_profile / 'kurucsai-profile-transport.json':
            data = dict(data, exit_code=143)
        return data
    monkeypatch.setattr(subject.pipeline, 'read_json_file', read)
    with pytest.raises(ValueError, match='visual proof differs'):
        verify(original_profile)


def test_cached_proof_must_equal_fresh_result(original_profile, monkeypatch):
    reader = subject.pipeline.read_json_file
    def read(path):
        data = reader(path)
        if path == original_profile / 'kurucsai-native-runtime-proof.json':
            data = copy.deepcopy(data)
            data['kit_pixels']['passed'] = False
        return data
    monkeypatch.setattr(subject.pipeline, 'read_json_file', read)
    with pytest.raises(ValueError, match='cached runtime proof differs'):
        verify(original_profile)
