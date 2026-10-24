"""Portable parser tests plus two optional retained-corpus fixtures."""
import copy
import json
from pathlib import Path
import pytest
from scripts.season_annual_fixture_identity_bridge_v1 import (
    verify_report_bytes, verify_opening_fixture, verify_annual_source_row_binding,
)

def retained_request(season='2000-01'):
    source = Path('.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/seedorf-visible-identity-correction-v1/annual-fixture-bridge-v2') / f'{season}-annual-fixture-request-v2.json'
    if not source.is_file():
        pytest.skip('retained annual-fixture corpus request unavailable')
    return json.loads(source.read_text())


SEASON_MAP={'competitions':[{'country_catalog':'italy','competition_catalog':'seriea','source_competition_code':'IT1'}]}
ALIASES={77:('italy',('Annual Club','Provider Club'))}
TITLES={77:'Provider Club'}

def fixture(**updates):
    value={'match_id':123,'date':'2000-10-01','url':'https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/123',
           'provider_club_id':77,'provider_player_id':909,'provider_club_name':'Provider Club','provider_competition_code':'IT1'}
    value.update(updates);return value

def annual(**updates):
    value={'season':'2000-01','selector':{'country_catalog':'italy','competition_catalog':'seriea','club_name':'Annual Club'}}
    value.update(updates);return value

def report(team_id=77, player_id=909, competition='IT1', season_id='2000'):
    return f'''<html><head><title>Home - Away, 01/10/2000 - Test League - Match sheet | Transfermarkt</title>
    <meta name="keywords" content="Home, Away, Test League, 1. Spieltag, Saison 00/01"></head><body>
    <a href="/test/startseite/wettbewerb/{competition}/saison_id/{season_id}">Competition</a>
    <div class="large-6"><a href="/team/startseite/verein/{team_id}/saison_id/2000">Provider Club</a>
    <div class="large-7 aufstellung-vereinsseite"><div class="formation-player-container">
    <span class="formation-number-name"><a href="/full-name/profil/spieler/{player_id}">Surname</a></span>
    </div></div></div></body></html>'''.encode()

def test_synthetic_exact_provider_match_crosswalk():
    result=verify_report_bytes(report(),fixture(),annual(), 'Full Name', ALIASES,TITLES,SEASON_MAP)
    assert result['provider_player_id']==909 and result['provider_club_id']==77
    assert result['fixture_date']=='2000-10-01' and result['provider_competition_code']=='IT1'

@pytest.mark.parametrize('bad_fixture,bad_annual,bad_map,bad_body',[
    (fixture(provider_club_id=78),annual(),SEASON_MAP,report()),
    (fixture(provider_player_id=901),annual(),SEASON_MAP,report()),
    (fixture(date='2001-10-01'),annual(),SEASON_MAP,report()),
    (fixture(date='2000-10-02'),annual(),SEASON_MAP,report()),
    (fixture(provider_competition_code='IT2'),annual(),SEASON_MAP,report()),
    (fixture(),annual(selector={'country_catalog':'italy','competition_catalog':'seriea','club_name':'Other Club'}),SEASON_MAP,report()),
    (fixture(),annual(),{'competitions':[]},report()),
    (fixture(),annual(),SEASON_MAP,report(competition='IT2')),
    (fixture(),annual(),SEASON_MAP,report().replace(b'Test League - Match',b'Other League - Match')),
    (fixture(),annual(),SEASON_MAP,report(season_id='2001')),
])
def test_false_id_year_club_and_competition_crosswalks_rejected(bad_fixture,bad_annual,bad_map,bad_body):
    with pytest.raises(ValueError):
        verify_report_bytes(bad_body,bad_fixture,bad_annual,'Full Name',ALIASES,TITLES,bad_map)

def test_player_link_in_opponent_sidebar_is_not_own_starting_xi():
    body=report(team_id=78)
    with pytest.raises(ValueError,match='starting XI'):
        verify_report_bytes(body,fixture(),annual(),'Full Name',ALIASES,TITLES,SEASON_MAP)

def test_legacy_annual_policy_does_not_accept_fixture_dob_exception():
    from scripts.season_annual_row_identity_guard_v1 import verify
    request_path=Path('.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/seedorf-visible-identity-correction-v1/annual-fixture-bridge-v2/2000-01-annual-fixture-request-v2.json')
    if not request_path.is_file(): pytest.skip('retained current-parent corpus request unavailable')
    witness=json.loads(request_path.read_text())['changes'][0]['witness']
    legacy=copy.deepcopy(witness);legacy['identity_policy']='annual-source-row-person-identity-v1'
    with pytest.raises(ValueError,match='fixture evidence is required only'):
        verify(legacy)

@pytest.mark.parametrize('season',['2000-01','2001-02'])
def test_optional_retained_reports_and_annual_rows(season):
    root=Path('.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/seedorf-visible-identity-correction-v1/annual-fixture-bridge-v2')
    request_path=root/f'{season}-annual-fixture-request-v2.json'
    if not request_path.is_file(): pytest.skip('retained local source corpus absent')
    witness=json.loads(request_path.read_text())['changes'][0]['witness']
    output=verify_opening_fixture(witness['historical_fixture'],witness['annual_identity'],witness['full_name'])
    assert output['provider_player_id']==4168 and output['provider_club_id']==46
    assert output['provider_competition_code']=='IT1'
    assert output['annual_source_row']['full_name']==witness['full_name']
    assert output['identity_link_source']=='match-sheet-numeric-player-link-and-profile-name-slug'

def test_fixture_policy_still_requires_exact_old_source_dob():
    from scripts.season_annual_row_identity_guard_v1 import verify
    request=retained_request()
    witness=copy.deepcopy(request['changes'][0]['witness'])
    witness['annual_identity']['source_birth_date']='1976-04-01'
    with pytest.raises(ValueError,match='annual source row full name/DOB differs'):
        verify(witness)

def test_official_sources_must_agree_on_corrected_date():
    from scripts.season_adjudicated_player_facts_v1 import adjudicate
    request=retained_request()
    witness=copy.deepcopy(request['changes'][0]['witness'])
    witness['values']['birth_date']='1976-11-01'
    with pytest.raises(ValueError):
        adjudicate(witness)

def test_fixture_policy_requires_two_independent_official_hosts():
    from scripts.season_adjudicated_player_facts_v1 import adjudicate
    request=retained_request()
    witness=copy.deepcopy(request['changes'][0]['witness'])
    witness['official_sources']=[witness['official_sources'][1],copy.deepcopy(witness['official_sources'][1])]
    with pytest.raises(ValueError,match='independent published source hosts required'):
        adjudicate(witness)

def test_wrong_native_dob_preimage_is_rejected_optional_corpus(tmp_path):
    from scripts import season_source_verified_player_changes_v1 as source_changes
    prepare=source_changes.prepare
    from scripts import season_release_registry_v1 as registry
    root=Path('.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/seedorf-visible-identity-correction-v1/annual-fixture-bridge-v2')
    source=root/'2000-01-annual-fixture-request-v2.json'
    if not source.is_file(): pytest.skip('retained current-parent corpus request unavailable')
    request=json.loads(source.read_text())
    request['changes'][0]['native_before_birth_date']='1976-11-02'
    import tempfile
    with tempfile.TemporaryDirectory(prefix='.native-preimage-', dir=root) as folder:
        temp=Path(folder)/'wrong-native-dob-input.json'
        temp.write_text(json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n')
        with pytest.raises(ValueError,match='native preimage'):
            prepare(registry.load_registered_release(request['season'],request['release_id']),temp)


# Additive v3 exact-matchday and annual-row source-binding regressions.
@pytest.mark.parametrize('round_label',['11. Spieltag','21. Spieltag'])
def test_round_number_substrings_do_not_satisfy_first_matchday(round_label):
    body=report().replace(b'1. Spieltag',round_label.encode('ascii'))
    with pytest.raises(ValueError,match='matchday'):
        verify_report_bytes(body,fixture(),annual(),'Full Name',ALIASES,TITLES,SEASON_MAP)

def test_full_name_must_match_numeric_id_profile_slug():
    with pytest.raises(ValueError,match='full name'):
        verify_report_bytes(report(),fixture(),annual(),'Other Person',ALIASES,TITLES,SEASON_MAP)

def synthetic_preallocation():
    selector={'club_name':'Annual Club','country_catalog':'italy','competition_catalog':'seriea',
              'source_path':'italy/2000-2001/seriea/annual-club.txt','source_sha256':'a'*64}
    return selector, {'season':{'label':'2000/01'},'source_clubs':[{
        'selector':selector,'players':[{'source_row_index':9,'source_row_sha256':'b'*64,
        'facts':{'name':'Full Name','birth_date':'1976-11-01'}}]}]}

def annual_identity_binding(selector):
    return {'season':'2000-01','selector':selector,'source_row_sha256':'b'*64,
            'source_row_index':9,'source_birth_date':'1976-11-01'}

def test_annual_name_and_old_dob_are_replayed_from_unique_hashed_row():
    selector,preallocation=synthetic_preallocation()
    result=verify_annual_source_row_binding(annual_identity_binding(selector),'Full Name',preallocation)
    assert result['source_row_sha256']=='b'*64
    assert result['source_birth_date']=='1976-11-01'

@pytest.mark.parametrize('mutation',[
    {'full_name':'Other Person'},
    {'source_row_sha256':'c'*64},
    {'source_row_index':10},
    {'source_birth_date':'1976-04-01'},
    {'selector':{'club_name':'Other Club','country_catalog':'italy','competition_catalog':'seriea',
                 'source_path':'italy/2000-2001/seriea/other-club.txt','source_sha256':'d'*64}},
])
def test_annual_source_row_full_name_and_profile_join_mismatch_rejected(mutation):
    selector,preallocation=synthetic_preallocation()
    binding=annual_identity_binding(selector)
    binding.update(mutation)
    with pytest.raises(ValueError):
        verify_annual_source_row_binding(binding,binding.get('full_name','Full Name'),preallocation)
