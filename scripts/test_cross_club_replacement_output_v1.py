import copy
import pytest
from scripts import cross_club_replacement_output_v1 as output


def publication():
    return '''<title>From licence to thrill City to riches on Blues bench | Football | The Guardian</title>
<meta property="article:published_time" content="2005-07-18T11:22:43+01:00">
<p>Shaun Wright-Phillips, the very right-winger Jose Mourinho values.</p>
<p>Wright-Phillips terrorising left-backs while marauding down Manchester City's right.</p>'''


def test_first_spell_side_review_is_not_claimed_as_exact_2000_deployment_or_FIFA():
    result = output.parse_role(publication())
    assert result['fine_roles'] == [11]
    assert result['grade'] == 'reviewed-editorial'
    assert result['exact_target_match_role_claimed'] is False
    assert result['future_FIFA_used'] is False


@pytest.mark.parametrize('old,new', [('2005-07-18', '2026-07-18'),
    ('Shaun Wright-Phillips', "D'Margio Wright-Phillips"), ('right-winger', 'striker'),
    ("Manchester City's right", "Chelsea's right"), ('Guardian', 'Another publisher')])
def test_other_person_club_role_date_or_publication_cannot_be_silently_admitted(old, new):
    with pytest.raises(ValueError): output.parse_role(publication().replace(old, new))


def test_only_selected_role_and_skills_change_without_mutating_input():
    player = dict(source_name='Shaun Wright-Phillips', facts=dict(birth_date='1981-10-25',
        primary_position='F', fine_roles=[12], nationality='ENG'), ratings=dict(old=True), club_id='city')
    before = copy.deepcopy(player)
    review = dict(policy=output.POLICY, role_review=dict(fine_roles=[11]),
        ratings=dict(values=dict(handling=7)), implementation_inputs=[])
    updated = output.apply_output(player, dict(source_bound_replacement_output=review))
    assert player == before and updated['facts']['nationality'] == 'ENG'
    assert updated['facts']['fine_roles'] == [11] and updated['ratings'] == review['ratings']
    assert updated['club_id'] == 'city'
    assert output.apply_output(player, {}) is player


def test_unreviewed_player_or_changed_model_is_refused(monkeypatch):
    player = dict(source_name='Shaun Wright-Phillips', facts=dict(birth_date='1981-10-25',
        primary_position='F'))
    review = dict(policy=output.POLICY, role_review=dict(fine_roles=[11]), ratings={},
        implementation_inputs=[dict(path='model.py', sha256='expected')])
    monkeypatch.setattr(output.registry, 'sha256_file', lambda path: 'changed')
    with pytest.raises(ValueError, match='changed'):
        output.apply_output(player, dict(source_bound_replacement_output=review))
    player['source_name'] = 'Another Player'
    with pytest.raises(ValueError, match='unreviewed'):
        output.apply_output(player, dict(source_bound_replacement_output=review))
