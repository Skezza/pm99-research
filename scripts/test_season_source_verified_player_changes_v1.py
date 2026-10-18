import copy
import pytest
from scripts import season_source_verified_player_changes_v1 as changes


def plan():
    return dict(schema=changes.SCHEMA,kind=changes.KIND,updates=[dict(
        carrier_id=1,before={},nationality='ENG',field_mask=['nationality'],
        native_mask=dict(file='DBDAT/JUG98030.FDI',record_offset=8,
                         file_offset=108,before=1,after=2),
        source_identity={},source={},source_receipt={},expected_owner=3)])


def test_exact_single_byte_mask_is_admitted():
    changes.validate_mask(plan())


@pytest.mark.parametrize('fault',[
    'rating','extra_field','extra_offset','negative','boolean','overflow',
    'no_change','duplicate_carrier','duplicate_offset','wrong_file'])
def test_masks_cannot_authorise_other_changes(fault):
    value=plan();row=value['updates'][0];mask=row['native_mask']
    if fault=='rating':row['field_mask']=['ratings']
    elif fault=='extra_field':row['ratings']={}
    elif fault=='extra_offset':mask['other_offset']=109
    elif fault=='negative':mask['record_offset']=-1
    elif fault=='boolean':mask['before']=True
    elif fault=='overflow':mask['after']=256
    elif fault=='no_change':mask['after']=mask['before']
    elif fault=='duplicate_carrier':value['updates'].append(copy.deepcopy(row))
    elif fault=='duplicate_offset':
        second=copy.deepcopy(row);second['carrier_id']=2;value['updates'].append(second)
    elif fault=='wrong_file':mask['file']='DBDAT/EQ98030.FDI'
    with pytest.raises(ValueError):changes.validate_mask(value)


def test_source_backed_recipe_cannot_be_factory_rebuilt():
    with pytest.raises(ValueError,match='SOURCE'):
        changes.reject_factory_recipe({'artifacts':[{'id':changes.PREFIX+'example'}]})


def test_unaffected_recipe_is_not_refused():
    changes.reject_factory_recipe({'artifacts':[]})


@pytest.fixture
def retained_plan():
    path=changes.registry.ROOT/'.local/consolidated-audit-20261009/Hyde2013-native-delivery-v1/source-backed-player-changes-5c5ef71468f2c09144e9c650.json'
    if not path.exists():pytest.skip('local original-source evidence unavailable')
    value=changes.pipeline.read_json_file(path)
    return changes.registry.load_registered_release(value['season'],value['release_id']),value


def test_existing_country_plan_still_reproduces(retained_plan):
    base,value=retained_plan
    changes.verify(base,value)


@pytest.mark.parametrize('fault',['offset','before','country','source_hash','input_hash','extra_rating'])
def test_real_bound_plan_rejects_tampering(retained_plan,fault):
    base,value=retained_plan;value=copy.deepcopy(value)
    if fault=='offset':value['updates'][0]['native_mask']['file_offset']+=1
    elif fault=='before':value['updates'][0]['native_mask']['before']^=1
    elif fault=='country':value['updates'][0]['nationality']='SCO'
    elif fault=='source_hash':value['updates'][0]['source']['sha256']='0'*64
    elif fault=='input_hash':value['source_input']['sha256']='0'*64
    elif fault=='extra_rating':value['updates'][0]['ratings']={}
    with pytest.raises(ValueError):changes.verify(base,value)
