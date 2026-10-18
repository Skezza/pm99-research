import copy

from scripts import prepare_coupled_foreign_native_v1 as native


def test_carrier_exchange_rates_destination_and_preserves_input(monkeypatch):
    ofk=[{'id':f'p{i}','carrier_id':i,'club_id':'club-706','name':f'Old{i}'} for i in range(1,19)]
    celta=[{'id':f'p{i}','carrier_id':i,'club_id':'club-48','name':f'Old{i}'} for i in range(20,45)]
    initial={'players':ofk+celta,'clubs':[
        {'carrier_id':706,'roster_player_ids':[p['id'] for p in ofk]},
        {'carrier_id':48,'roster_player_ids':[p['id'] for p in celta]}]}
    original=copy.deepcopy(initial)
    captured=[]
    monkeypatch.setattr(native.ofk_native,'compose_recipe',lambda *args:
        (copy.deepcopy(initial),{'old':'original-OFK-source'},set(p['id'] for p in ofk)))
    def update(package,composition):
        captured.extend(copy.deepcopy(composition['updates']))
        return copy.deepcopy(package)
    monkeypatch.setattr(native.delta,'updated_package',update)
    monkeypatch.setattr(native.packages,'validate_package',lambda package:None)
    def move(id,name):
        return {'player_id':f'p{id}','carrier_id':id,'replacement':{'source':'original'},
            'display':{'display_name':name}}
    proposal={'coupled_native_carrier_exchange':{'OFK_to_Celta':18,'Celta_to_OFK':20},
        'coupled_Celta_allocation':[move(18,'Madinda')],
        'coupled_OFK_transferred_allocation':[move(20,'Drazic')]}
    result,_,selected=native.compose_recipe(initial,proposal)
    assert initial==original
    assert {row['carrier_id']:row['before']['club_id'] for row in captured}=={18:'club-48',20:'club-706'}
    players={p['carrier_id']:p for p in result['players']}
    assert players[18]['club_id']=='club-48' and players[20]['club_id']=='club-706'
    assert players[18]['name']=='Madinda' and players[20]['name']=='Drazic'
    ofk_result=next(c for c in result['clubs'] if c['carrier_id']==706)
    celta_result=next(c for c in result['clubs'] if c['carrier_id']==48)
    assert len(ofk_result['roster_player_ids'])==18 and len(celta_result['roster_player_ids'])==25
    assert 'p20' in ofk_result['roster_player_ids'] and 'p18' not in ofk_result['roster_player_ids']
    assert 'p18' in celta_result['roster_player_ids'] and 'p20' not in celta_result['roster_player_ids']
    assert selected=={f'p{i}' for i in range(1,19)}|{'p20'}
