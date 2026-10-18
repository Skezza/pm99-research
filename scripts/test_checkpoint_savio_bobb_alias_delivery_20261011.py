import copy
import pytest
from scripts import checkpoint_savio_bobb_alias_delivery_20261011 as checkpoint

VALUES=dict(speed=62,stamina=63,aggression=60,quality=58,handling=7,passing=65,
    dribbling=61,heading=52,tackling=57,shooting=56)


@pytest.fixture
def review(tmp_path,monkeypatch):
    frame=tmp_path/'frame.png';frame.write_bytes(b'original inspected frame fixture')
    monkeypatch.setattr(checkpoint.registry,'ROOT',tmp_path)
    return dict(method='assistant-original-image-visual-review',original_frame_visually_inspected=True,
        screenshot='frame.png',screenshot_sha256=checkpoint.registry.sha256_file(frame),
        observed_native_name='Oscar Bobb',observed_club='Manchester City',observed_age=21,expected_age=21,
        observed_nationality='NORWAY',visible_skills_match_compiled_replacement=True,observed_skills=VALUES.copy())


def test_requires_new_authored_replacement_skills_not_unchanged_displaced_skills(review):
    checkpoint.check_bobb_visual(review,VALUES)
    assert 'visible_skills_match_native_baseline' not in review


@pytest.mark.parametrize('field,value',[('method','OCR-only'),('original_frame_visually_inspected',False),
    ('screenshot_sha256','wrong'),('observed_native_name','Savinho'),('observed_club','Fulham'),
    ('observed_age',20),('expected_age',20),('observed_nationality','BRAZIL'),
    ('visible_skills_match_compiled_replacement',False)])
def test_wrong_person_fact_or_uninspected_frame_refuses(review,field,value):
    review[field]=value
    with pytest.raises(ValueError):checkpoint.check_bobb_visual(review,VALUES)


def test_wrong_or_incomplete_authored_skills_refuse(review):
    changed=copy.deepcopy(review);changed['observed_skills']['handling']=99
    with pytest.raises(ValueError):checkpoint.check_bobb_visual(changed,VALUES)
    del review['observed_skills']['shooting']
    with pytest.raises(ValueError):checkpoint.check_bobb_visual(review,VALUES)
