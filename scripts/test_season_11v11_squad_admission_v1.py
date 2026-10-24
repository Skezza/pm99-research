import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import season_11v11_squad_admission_v1 as source
from scripts import season_soccerbase_duplicate_source_policy_v1 as identities


@pytest.fixture
def admission(tmp_path, monkeypatch):
    monkeypatch.setattr(source.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(source, '_verify_football_squads_source_file',
                        lambda *args: {'capture_status': 'raw-source-reparsed'})
    url = 'https://www.11v11.com/players/example-person-8/'
    raw = f'''<meta property="og:url" content="{url}">
        <meta property="og:title" content="Example Person"><h1>Example Person</h1>
        <table><tr><td>Date of birth</td><td>16 February 1982</td></tr>
        <tr><td>Nationality</td><td>English</td></tr><tr><td>Position</td><td>Midfielder</td></tr></table>
        <table><tr><th>Team</th><th>Joined</th><th>Left</th><th>Loan / Trialist</th></tr>
        <tr><td>Example Club</td><td>17 Jul 2000</td><td>21 Nov 2000</td><td></td></tr></table>'''.encode()
    profile = tmp_path / 'profile.html'
    profile.write_bytes(raw)
    bound = {'path': 'profile.html', 'sha256': hashlib.sha256(raw).hexdigest(),
             'url': url, 'final_url': url, 'http_status': 200}
    receipt = tmp_path / 'receipt.json'
    receipt.write_text(json.dumps({'schema': 'pm99-original-http-source-capture-v1', 'sources': [bound]}))
    roster = tmp_path / '.local/external-sources/cache.footballsquads/eng/2000-2001/d3/example.txt'
    roster.parent.mkdir(parents=True)
    roster.write_text('=  Example Club - 2000/01\n== Past Players\n18, Example Person, M, 1.88, 12 01, 16-02-82, Town, Old Club\n')
    evidence = {'profile': bound,
        'receipt': {'path': 'receipt.json', 'sha256': hashlib.sha256(receipt.read_bytes()).hexdigest()},
        'roster': {'path': str(roster.relative_to(tmp_path)), 'sha256': hashlib.sha256(roster.read_bytes()).hexdigest(),
                   'url': 'https://www.footballsquads.co.uk/eng/2000-2001/d3/example.htm',
                   'source_kind': 'retained-normalized-footballsquads-text'}}
    selection = {'provider': source.POLICY, 'admission_policy': source.POLICY,
        'identity_source': 'profile', 'capture_receipt_source': 'receipt', 'roster_source': 'roster',
        'provider_player_id': '8', 'full_name': 'Example Person', 'name': 'Example Person',
        'native_display_name': 'Example Person', 'birth_date': '1982-02-16',
        'nationality_label': 'English', 'nationality': 'ENG', 'profile_position': 'Midfielder',
        'position': 'M', 'footballsquads_position': 'M', 'fine_roles': [9],
        'editorial_fine_role': {'classification': 'editorial-compatible-not-source-specific', 'code': 9},
        'season': '2000/01', 'club': 'Example Club',
        'membership_window': {'start': '2000-08-01', 'end': '2000-08-31'}}
    return selection, evidence


def test_dated_annual_member_is_not_claimed_as_a_match_appearance(admission):
    selection, evidence = admission
    result = source.new_person(selection, evidence, '2000-01', {'name': 'Example Club'})
    assert result['opening_date'] == '2000-08-01'
    assert 'not-matchday' in result['membership']
    assert result['source_person']['source_player_id'] == '11v11:8'
    assert identities.person_id(result['source_person']) == 'person-11v11-8'
    assert result['source_player']['height_cm'] == 188
    assert result['source_player']['weight_kg'] == 77
    assert result['published_shirt_number_not_admitted_by_this_writer'] == 18
    assert result['football_squads_row']['nationality_column_present'] is False
    assert result['football_squads_row']['candidate_row_in_legacy_canonical_roster'] is False


@pytest.mark.parametrize('field,value', [('source_player_id', '11v11:9'), ('name', 'Another Person'),
                                        ('birth_date', '1982-02-17')])
def test_provider_namespace_cannot_bypass_original_identity_replay(admission, field, value):
    selection, evidence = admission
    person = source.new_person(selection, evidence, '2000-01', {'name': 'Example Club'})['source_person']
    person[field] = value
    with pytest.raises(ValueError, match='differs'):
        identities.person_id(person)


@pytest.mark.parametrize('field,value', [('nationality', 'GER'), ('provider_player_id', '9'),
                                        ('birth_date', '1982-02-17')])
def test_published_profile_facts_are_not_free_inputs(admission, field, value):
    selected, evidence = admission
    selected[field] = value
    with pytest.raises(ValueError):
        source.admit(selected, evidence)


def test_another_years_august_cannot_pass_as_target_membership(admission):
    selected, evidence = admission
    selected['membership_window'] = {'start': '2001-08-01', 'end': '2001-08-31'}
    with pytest.raises(ValueError, match='exactly August'):
        source.admit(selected, evidence)


def test_partial_two_digit_annual_date_does_not_invent_a_century():
    assert source._matches_short_dob('16-02-68', '1968-02-16')
    assert source._matches_short_dob('16-02-68', '2068-02-16')
    assert not source._matches_short_dob('16-02-69', '1968-02-16')


def test_destination_club_and_editorial_role_require_explicit_agreement(admission):
    selected, evidence = admission
    with pytest.raises(ValueError, match='destination'):
        source.new_person(selected, evidence, '2000-01', {'name': 'Another Club'})
    selected['editorial_fine_role']['code'] = 12
    selected['fine_roles'] = [12]
    with pytest.raises(ValueError, match='fine role'):
        source.new_person(selected, evidence, '2000-01', {'name': 'Example Club'})
