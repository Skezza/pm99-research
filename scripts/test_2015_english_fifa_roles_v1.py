import copy
from pathlib import Path
import pytest
from scripts import season_2015_english_fifa_roles_v1 as roles


def test_forward_wide_midfielder_overlap_not_arbitrary_position_rewrite():
    assert roles.compatible('F',10)
    assert roles.compatible('F',6)
    assert not roles.compatible('F',4)
    assert not roles.compatible('G',10)
    assert not roles.compatible({'policy':'preserve-existing-mode1'},10)


def fixture(monkeypatch):
    person=dict(carrier_id=9277,name='Marko Arnautovic',facts=dict(fine_roles=[11,15,7],primary_position='F'),
        ratings=dict(values=dict(handling=15,quality=78)))
    english=dict(players=[person],artifacts=[])
    main=dict(players=[dict(carrier_id=1790,name='Messi')],artifacts=[dict(id=roles.ARTIFACT,sha256='old')])
    monkeypatch.setattr(roles.registry,'load_registered_release',lambda *args:object())
    monkeypatch.setattr(roles,'overlay',lambda base:(english,Path('test.json')))
    monkeypatch.setattr(roles.registry,'sha256_file',lambda p:'English-preimage')
    monkeypatch.setattr(roles.packages,'validate_package',lambda p:None)
    plan=dict(schema=roles.SCHEMA,season='2015-16',release_id='base',transaction_id='test',
        english_package_sha256='English-preimage',updates=[dict(carrier_id=9277,
            before_player_sha256=roles.prior.digest(person),fine_roles=[10,12])])
    return main,english,plan


def test_edited_english_recipe_and_hash_published_without_foreign_or_skill_edits(monkeypatch):
    main,english,plan=fixture(monkeypatch);before=copy.deepcopy(english)
    result=roles.bind(main,plan);updated=roles.updated_english(plan)
    assert result['players']==main['players']
    assert updated['players'][0]['facts']['fine_roles']==[10,12]
    assert updated['players'][0]['facts']['primary_position']=='F'
    assert updated['players'][0]['ratings']==english['players'][0]['ratings']
    assert result['artifacts'][0]['sha256']==roles.prior.digest(updated)
    assert english==before


def test_changed_english_preimage_refuses(monkeypatch):
    _,_,plan=fixture(monkeypatch);plan['english_package_sha256']='changed'
    with pytest.raises(ValueError):roles.updated_english(plan)


def test_changed_player_preimage_refuses(monkeypatch):
    _,_,plan=fixture(monkeypatch);plan['updates'][0]['before_player_sha256']='changed'
    with pytest.raises(ValueError):roles.updated_english(plan)


def test_original_native_ui_role_abbreviation_is_explicit_and_code_specific():
    from scripts.checkpoint_2015_english_fifa_roles_20261015 import role_label_matches
    assert role_label_matches(10,'LEFT MID.')
    assert role_label_matches(10,'Left Midfielder')
    assert not role_label_matches(9,'LEFT MID.')
    assert not role_label_matches(10,'LEFT')
    assert not role_label_matches(10,'RIGHT MID.')
