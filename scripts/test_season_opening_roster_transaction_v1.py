"""Source701 transaction integration; retained source corpus is optional in CI."""
import copy
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'upstream/pm99-skezmod-db-editor')]
from scripts import season_opening_roster_transaction_v1 as t
from scripts import season_source_bound_fixture_membership_v1 as f
from scripts import season_release_registry_v1 as r
from scripts import season_pipeline_v2 as p

@pytest.fixture(scope='module')
def data():
    path=ROOT/'.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/source701-mode0-roster-order-rebase-r705-v3/source701-mode0-roster-order-rebase-r705-v3.json'
    if not path.exists():pytest.skip('retained original source corpus unavailable')
    doc=p.read_json_file(path);base=r.load_registered_release('2022-23',doc['parent']['release_id']);main=p.read_json_file(base.package_path);eng=p.read_json_file(f._layer_path(main,base.package_path,'english-season-package.json'));eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes();jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    return base,main,eng,eq,jug,doc

def test_exact_approved_native_postimages_and_five_gamebench_preserve_all_people(data):
    base,main,eng,eq,jug,doc=data;result=t.compose(*data);out=result['outputs'];proof=p.read_json_file(ROOT/'.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/source701-mode0-roster-order-rebase-r705-v3/root-native-memory-transaction-preflight-v1.json')
    assert t.hashlib.sha256(out['eq']).hexdigest()==proof['output_eq_sha256']
    assert t.hashlib.sha256(out['jug']).hexdigest()==proof['output_jug_sha256']
    old={x['carrier_id']:x for x in main['players']};new={x['carrier_id']:x for x in out['main_package']['players']}
    moved={x['carrier_id']for x in doc['approved_membership_changes']['moves']}
    for pid in old:
        if pid not in moved:assert old[pid]==new[pid]
        else:
            expected=copy.deepcopy(new[pid]);expected['club_id']=old[pid]['club_id'];expected['facts']['shirt_number']=old[pid]['facts']['shirt_number'];assert expected==old[pid]
    oldclubs={x['carrier_id']:x for x in main['clubs']}
    for club in out['main_package']['clubs']:
        cid=club['carrier_id'];before=oldclubs[cid]
        if cid not in t.SELECTED:assert club==before
        else:
            assert len(club['opening']['substitute_player_ids'])==5
            assert club['opening']['starting_xi_player_ids']==before['opening']['starting_xi_player_ids']
            assert club['opening']['tactics_context']==before['opening']['tactics_context']
    assert len(out['main_package']['players'])==len(main['players'])
    stoke=next(x for x in out['main_package']['clubs']if x['carrier_id']==344)
    assert [new_id for new_id in stoke['roster_player_ids']if new_id in {'english-player-10455','english-player-10362'}]==['english-player-10455','english-player-10362']
    assert new[10349]['source_name']==old[10349]['source_name']

@pytest.mark.parametrize('mutation',['source','main','english','eq'])
def test_reject_unapproved_source_or_changed_parent_inputs(data,mutation):
    base,main,eng,eq,jug,doc=data
    if mutation=='source':doc=copy.deepcopy(doc);doc['clubs']['344']['after_rows'][0]['carrier_id']=999
    elif mutation=='main':main=copy.deepcopy(main);main['players'][0]['name']='Changed'
    elif mutation=='english':eng=copy.deepcopy(eng);eng['players'][0]['name']='Changed'
    elif mutation=='eq':eq=bytes([eq[0]^1])+eq[1:]
    with pytest.raises(ValueError):t.compose(base,main,eng,eq,jug,doc)

def test_swapped_provider_to_native_identity_crosswalk_is_rejected(data, monkeypatch):
    # Both people and annual DOBs remain valid; only their provider-ID pairing
    # is wrong. The original report must expose that swap before any write.
    bonham, sparrow = t.PEOPLE['209291'], t.PEOPLE['621365']
    monkeypatch.setitem(t.PEOPLE, '209291', sparrow)
    monkeypatch.setitem(t.PEOPLE, '621365', bonham)
    with pytest.raises(ValueError, match='fixture provider-person'):
        t.compose(*data)
