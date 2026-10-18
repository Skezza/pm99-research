import copy
import json
import pytest
from scripts import prepare_paired_whole_club_native_v1 as native
from scripts.test_prepare_paired_whole_club_dispositions_v1 import proposals


@pytest.mark.parametrize('problem', ['singleton-schema', 'authorised', 'missing-club', 'different-baseline',
    'outside-collision', 'missing-manager', 'tampered-summary', 'wrapper-season'])
def test_coupled_candidate_refuses_before_native_writes(tmp_path, monkeypatch, problem):
    ps = proposals()
    pair = {'schema_version': native.paired.SCHEMA, 'publication_authorised': False,
        'season': '2021-22', 'release_id': 'baseline', 'proposals': [
            {'path': str(i)} for i in range(2)], 'source_guard': native.paired.validate_group(ps)}
    if problem == 'singleton-schema': pair['schema_version'] = 'singleton'
    if problem == 'authorised': pair['publication_authorised'] = True
    if problem == 'missing-club': ps.pop(); pair['proposals'].pop()
    if problem == 'different-baseline': ps[1]['jug_sha256'] = 'another'
    if problem == 'outside-collision': ps[0]['outside_collisions'][0]['other_club_id'] = 'outside'
    if problem == 'tampered-summary': pair['source_guard']['corrected_slots'] = 99
    if problem == 'wrapper-season': pair['season'] = '2020-21'
    original_paths = []
    for i, p in enumerate(ps):
        path = tmp_path / f'original-{i}.json'; path.write_text(json.dumps(p)); original_paths.append(path)
    monkeypatch.setattr(native.native, 'original', lambda b: original_paths[int(b['path'])])
    managers = {100: tmp_path / 'a.html', 200: tmp_path / 'b.html'}
    if problem == 'missing-manager': managers.pop(200)
    path = tmp_path / 'pair.json'; path.write_text(json.dumps(pair))
    with pytest.raises(ValueError): native.prepare(path, managers, tmp_path / 'candidate')
    assert not (tmp_path / 'candidate').exists()


def test_completed_private_candidate_is_never_overwritten(tmp_path):
    output = tmp_path / 'candidate'; output.mkdir()
    with pytest.raises(ValueError, match='immutable'):
        native.prepare(tmp_path / 'missing.json', {}, output)


def manager_html(id, name='Phil Parkinson',start='01 Jul, 2021',end='Present'):
    return (f'<table><tr><td><a href="/managers/manager.sd?manager_id={id}">{name}</a></td>'
        f'<td>{start}</td><td>{end}</td></tr></table>').encode()


def test_same_manager_name_is_not_a_person_identity():
    assert native.dated_manager_identity(manager_html(1852),'2021-08-21')==('Phil Parkinson',1852)
    assert native.dated_manager_identity(manager_html(6000),'2021-08-21')==('Phil Parkinson',6000)
    older=manager_html(100,start='01 Jul, 2010')
    assert native.dated_manager_identity(older+manager_html(1852),'2021-08-21')==('Phil Parkinson',1852)


def test_identical_tenure_names_cannot_hide_two_publisher_people():
    with pytest.raises(ValueError,match='identity is ambiguous'):
        native.dated_manager_identity(manager_html(1852)+manager_html(6000),'2021-08-21')


@pytest.mark.parametrize('id',['-1','0','1852&fake=1'])
def test_manager_identity_must_be_one_original_positive_numeric_link(id):
    with pytest.raises(ValueError):native.dated_manager_identity(manager_html(id),'2021-08-21')


def test_legacy_input_semantic_hash_and_exact_override(tmp_path):
    import hashlib
    original=tmp_path/'retained.json';original.write_text('{"updates": []}\n')
    digest=hashlib.sha256(native.pipeline.canonical_json_bytes({'updates':[]})).hexdigest()
    (tmp_path/'role-plan.json').write_text('{"updates": [1]}\n')
    package={'artifacts':[{'id':'historical-role-plan-2021-22','relative_path':'role-plan.json','sha256':digest}]}
    with pytest.raises(ValueError,match='hash changed'):native.recipe_inputs(package,tmp_path)
    result=native.recipe_inputs(package,tmp_path,{'role-plan.json':original})
    assert result[native.Path('role-plan.json')][1]['hash_contract']=='canonical-semantic-json'
    with pytest.raises(ValueError,match='unused'):native.recipe_inputs(package,tmp_path,{'role-plan.json':original,'unused.json':original})


@pytest.mark.parametrize('relative',['../other.json','/other.json'])
def test_inherited_input_cannot_escape_recipe(tmp_path,relative):
    with pytest.raises(ValueError,match='unsafe'):
        native.recipe_inputs({'artifacts':[{'id':'original','relative_path':relative}]},tmp_path)
