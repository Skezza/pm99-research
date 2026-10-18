import hashlib
import json
import pytest
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts import season_release_registry_v1 as registry
from scripts.test_season_soccerbase_original_opening_v1 import person


def biography():
    return dict(person(), name='Nathan Ashmore', birth_date='1990-02-22')


def test_unique_exact_name_and_dob_bridge_preserves_both_provider_namespaces():
    source = biography()
    target = {'source_player_id': 777, 'name':'Nathan Ashmore', 'birth_date':'1990-02-22'}
    result = replay.bridge(source, {('nathanashmore','1990-02-22'):{777:target}})
    assert result['soccerbase_person']['source_player_id']=='soccerbase:50514'
    assert result['transfermarkt_person']['source_player_id']==777
    assert not result['ownership_established_by_identity_bridge']


@pytest.mark.parametrize('kind', ['initial-only','wrong-dob','ambiguous'])
def test_initials_wrong_dob_and_multiple_entities_never_bridge(kind):
    p = biography(); key=('nathanashmore','1990-02-22')
    if kind=='initial-only': key=('nashmore','1990-02-22')
    if kind=='wrong-dob': key=('nathanashmore','1990-02-23')
    people={key:{777:{'source_player_id':777}}}
    if kind=='ambiguous': people[key][778]={'source_player_id':778}
    assert replay.bridge(p, people)['transfermarkt_person'] is None


def test_original_receipt_rehashes_bytes_and_keeps_url(tmp_path,monkeypatch):
    monkeypatch.setattr(registry,'ROOT',tmp_path)
    p=tmp_path/'player'/'50514.html';p.parent.mkdir();p.write_bytes(b'<h1>Nathan Ashmore</h1>')
    url='https://www.soccerbase.com/players/player.sd?player_id=50514'
    p.with_name(p.name+'.source.json').write_text(json.dumps({'url':url,
        'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}))
    proofs=[];raw, actual_url=replay.read_original(tmp_path,'player',50514,proofs)
    assert actual_url==url and raw==p.read_bytes() and len(proofs)==1
    p.write_bytes(b'<h1>Different Person</h1>')
    with pytest.raises(ValueError,match='receipt differs'):
        replay.read_original(tmp_path,'player',50514,[])
