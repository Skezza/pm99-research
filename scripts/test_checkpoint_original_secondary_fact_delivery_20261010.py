"""Adversarial checks on final original-frame acceptance."""
import pytest
from scripts import checkpoint_original_secondary_fact_delivery_20261010 as checkpoint


@pytest.fixture
def review(tmp_path, monkeypatch):
    image = tmp_path / 'frame.png'
    image.write_bytes(b'original frame fixture')
    monkeypatch.setattr(checkpoint.registry, 'ROOT', tmp_path)
    return dict(method='assistant-original-image-visual-review', original_frame_visually_inspected=True,
        screenshot='frame.png', screenshot_sha256=checkpoint.registry.sha256_file(image),
        observed_native_name='#9 Ferran Torres', observed_club='Manchester City',
        observed_age=21, expected_age=21, visible_skills_match_native_baseline=True,
        observed_nationality='SPAIN')


def check(review):
    checkpoint.check_visual(review, name='#9 Ferran Torres', club='Manchester City',
        age=21, nationality='SPAIN')


def test_accepts_original_bound_profile(review):
    check(review)


@pytest.mark.parametrize('field,value', [
    ('method', 'OCR-only'), ('original_frame_visually_inspected', False),
    ('screenshot_sha256', 'wrong'), ('observed_native_name', 'Ferran Torres'),
    ('observed_club', 'Barcelona'), ('observed_age', 22), ('expected_age', 22),
    ('visible_skills_match_native_baseline', False), ('observed_nationality', 'ENGLAND'),
])
def test_refuses_false_runtime_approval(review, field, value):
    review[field] = value
    with pytest.raises(ValueError):
        check(review)


def test_changed_frame_refused(review, tmp_path):
    (tmp_path / 'frame.png').write_bytes(b'new frame replacing inspected original')
    with pytest.raises(ValueError):
        check(review)
