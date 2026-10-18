import copy
import hashlib
import json
import pytest
from scripts import season_verified_opening_roster_sources_v1 as reader


@pytest.mark.parametrize('fault',['none','body_hash','receipt_url','receipt_hash'])
def test_original_body_requires_exact_receipt(tmp_path,monkeypatch,fault):
    path=tmp_path/'body.html';path.write_bytes(b'original')
    digest=hashlib.sha256(b'original').hexdigest()
    binding=dict(path='body.html',sha256=digest,url='https://www.soccerbase.com/example')
    receipt=dict(url=binding['url'],sha256=digest)
    if fault=='body_hash':binding['sha256']='0'*64
    elif fault=='receipt_url':receipt['url']='https://other.example/'
    elif fault=='receipt_hash':receipt['sha256']='0'*64
    path.with_suffix('.html.source.json').write_text(json.dumps(receipt))
    monkeypatch.setattr(reader.fields,'original_path',lambda _:path)
    if fault=='none':assert reader.body(binding)==b'original'
    else:
        with pytest.raises(ValueError):reader.body(binding)


def test_later_alias_requires_real_calendar_date(monkeypatch):
    raw=b'<table><tr id="tgc1"><td class="tournament"><a>National League</a></td><td class="dateTime"><span class="hide">2017-99-99 15:00</span></td></tr></table>'
    monkeypatch.setattr(reader,'body',lambda _:raw)
    with pytest.raises(ValueError):
        reader.published_alias('2017-18',dict(schedule={},competition='National League'),{},dict(game_id=1))


def test_world_country_labels_do_not_change_legacy_default():
    raw='<h1>Tunji Moses</h1><table><tr><th>Born</th><td>12 Sep, 1983</td></tr><tr><th>Nationality</th><td>France</td></tr></table>'
    args=dict(person_id=66030,name='Tunji Moses',birth_date='1983-09-12',
              url='https://www.soccerbase.com/players/player.sd?player_id=66030')
    with pytest.raises(ValueError):reader.countries.country(raw,**args)
    assert reader.countries.country(raw,**args,nationality_codes=reader.SOURCE_COUNTRIES)['nationality']=='FRA'


@pytest.fixture
def actual_group():
    path=reader.fields.registry.ROOT/'.local/consolidated-audit-20261009/Barrow2017-owned-roster-delivery-v1/opening-source-input.json'
    if not path.exists():pytest.skip('original local source cache unavailable')
    return reader.fields.pipeline.read_json_file(path)


def test_actual_eighteen_have_source_countries_and_separate_alias_authority(actual_group):
    result=reader.read('2017-18',actual_group)
    assert len(result['desired'])==18 and result['secondary_fact_gaps']==[]
    byron=next(r for r in result['desired'] if r['source_person']['provider_player_id']==58116)
    assert byron['membership']=='positive-original-provider-dated-opening-reserve'
    assert byron['source_display_aliases']['names'][0]['name']=='B Harrison'
    assert result['fixture']['date']=='2017-08-05'


def test_wrong_reviewed_opener_is_rejected(actual_group):
    group=copy.deepcopy(actual_group);group['expected_opening_game_id']=753880
    with pytest.raises(ValueError,match='first fixture'):reader.read('2017-18',group)


def test_partial_read_claims_only_selected_published_person(actual_group):
    group=copy.deepcopy(actual_group);group['reserves']=[];group['display_witnesses']={}
    result=reader.read('2017-18',group,selected_person_ids=[74228])
    assert len(result['desired'])==1
    assert result['desired'][0]['source_person']['name']=='Stuart Moore'
    assert result['selection']['complete_roster_biographies_verified'] is False
    assert result['selection']['original_match_XI_rows']==11


@pytest.mark.parametrize('selection',[[74228,74228],[999999999],[True],[]])
def test_partial_read_cannot_invent_or_duplicate_a_matchday_identity(actual_group,selection):
    group=copy.deepcopy(actual_group);group['reserves']=[];group['display_witnesses']={}
    with pytest.raises(ValueError,match='partial source'):
        reader.read('2017-18',group,selected_person_ids=selection)
