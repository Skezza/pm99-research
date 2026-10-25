import hashlib
import json

import pytest

from scripts import season_uefa_roster_profile_admission_v1 as source


TEXT = '''FC Example | Group B
PLAYERS
No. Name Position Date of Birth Nationality Height (cm) Joined Previous Club
2  Alex SAMPLE  Defender  04.03.1982  FRA  180  2001  FC Other
GROUP FIXTURES
'''


def test_generic_official_table_reads_another_person_and_country():
    row = source.parse_roster_table_text(TEXT, full_name='Alex Sample',
        birth_date='1982-03-04', expected_club_label='Example')
    assert (row['nationality'], row['broad_position']) == ('FRA', 'D')


@pytest.mark.parametrize('name,dob,club', [('Other Sample', '1982-03-04', 'Example'),
    ('Alex Sample', '1982-03-05', 'Example'), ('Alex Sample', '1982-03-04', 'Different')])
def test_table_refuses_other_identity_or_club(name, dob, club):
    with pytest.raises(ValueError):
        source.parse_roster_table_text(TEXT, full_name=name, birth_date=dob, expected_club_label=club)


def test_duplicate_player_row_is_ambiguous():
    row = TEXT.splitlines()[3]
    with pytest.raises(ValueError, match='one row'):
        source.parse_roster_table_text(TEXT.replace(row, row+'\n'+row), full_name='Alex Sample',
            birth_date='1982-03-04', expected_club_label='Example')


@pytest.mark.parametrize('short,full,expected', [
    ('Bruno Patacas', 'Bruno Alexandre Santos Patacas', True),
    ('Bruno Patacas', 'Rui Santos Patacas', False),
    ('Bruno Ricardo Patacas', 'Bruno Santos Patacas', False),
    ('Alex Sample', 'Alex Sample', True),
])
def test_published_fullname_crosswalk_requires_given_and_complete_family_components(short, full, expected):
    assert source._name_crosswalk(short, full) is expected


def capture(tmp_path, monkeypatch, *, full='Alex Sample', position='Right-Back', pid='99001'):
    monkeypatch.setattr(source.registry, 'ROOT', tmp_path)
    url = 'https://www.transfermarkt.com/alex-sample/profil/spieler/' + pid
    text = (url + '\nFull name: ' + full + '\nDate of birth: 04/03/1982\n'
            'Citizenship: France\nPosition: Defender - ' + position + '.')
    data = {'schema': 'pm99-indexed-profile-result-capture-v1',
        'capture_method': 'web-search-indexed-result-transcription',
        'provider': 'transfermarkt-indexed-profile-result-v1', 'profile_url': url,
        'provider_player_id': pid, 'indexed_text': text,
        'sha256_of_indexed_text': hashlib.sha256(text.encode()).hexdigest(),
        'claims': {'published_full_name': full, 'published_birth_date': '1982-03-04',
            'published_country': 'France', 'published_position': position},
        'identity_crosswalk': {'annual_source_name': 'Alex Sample',
            'annual_birth_date': '1982-03-04', 'annual_provider_player_id': pid}}
    path = tmp_path / 'indexed.json'
    path.write_bytes(json.dumps(data).encode())
    return {'path': 'indexed.json', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.mark.parametrize('position,code', [('Right-Back', 1), ('Left-Back', 2)])
def test_literal_profile_role_uses_existing_taxonomy(tmp_path, monkeypatch, position, code):
    binding = capture(tmp_path, monkeypatch, position=position)
    parsed = source.parse_indexed_role(binding, annual_name='Alex Sample',
        annual_birth_date='1982-03-04', annual_provider_id='99001')
    assert parsed['fine_role_code'] == code


@pytest.mark.parametrize('problem', ['other_given_name', 'other_dob', 'other_provider_id', 'changed_capture'])
def test_literal_profile_refuses_identity_or_capture_conflicts(tmp_path, monkeypatch, problem):
    binding = capture(tmp_path, monkeypatch, full='Rui Sample' if problem == 'other_given_name' else 'Alex Sample')
    if problem == 'changed_capture':
        binding['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        source.parse_indexed_role(binding, annual_name='Alex Sample',
            annual_birth_date='1982-03-05' if problem == 'other_dob' else '1982-03-04',
            annual_provider_id='99002' if problem == 'other_provider_id' else '99001')
