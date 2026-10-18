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


def height_plan():
    value = plan()
    value['kind'] = changes.HEIGHT_KIND
    row = value['updates'][0]
    row.pop('nationality'); row.pop('source_receipt')
    row.update(height_cm=173, field_mask=['height_cm'])
    row['native_mask'].update(record_offset=16, before=66, after=173)
    return value


def test_adult_height_mask_and_recipe_only_completion_are_explicit():
    value = height_plan()
    changes.validate_mask(value)
    value['updates'][0]['native_mask']['before'] = 173
    changes.validate_mask(value)


@pytest.mark.parametrize('fault', ['country', 'rating', 'height', 'mask', 'boolean', 'offset'])
def test_adult_height_mask_never_authorises_other_fields(fault):
    value = height_plan(); row = value['updates'][0]
    if fault == 'country': row['nationality'] = 'ENG'
    if fault == 'rating': row['field_mask'] = ['ratings']
    if fault == 'height': row['height_cm'] = 300
    if fault == 'mask': row['native_mask']['after'] = 174
    if fault == 'boolean': row['height_cm'] = True
    if fault == 'offset': row['native_mask']['file_offset'] = -1
    with pytest.raises(ValueError): changes.validate_mask(value)


def test_adult_height_writer_changes_one_byte_and_rejects_unrelated_preimage(tmp_path, monkeypatch):
    from types import SimpleNamespace
    folder = tmp_path / 'DBDAT'; folder.mkdir()
    before = bytes([66] * 200); eq = b'unchanged EQ'
    (folder / 'JUG98030.FDI').write_bytes(before)
    monkeypatch.setattr(changes.registry, 'load_registered_release', lambda *args: SimpleNamespace(game_path=tmp_path))
    monkeypatch.setattr(changes, 'verify', lambda *args: None)
    value = height_plan(); value.update(season='2013-14', release_id='parent', eq_sha256=changes.digest(eq))
    after, after_eq = changes.apply(before, eq, value)
    assert after_eq == eq and len(after) == len(before)
    assert [i for i, (a, b) in enumerate(zip(before, after)) if a != b] == [108]
    assert after[108] == 173
    assert changes.apply(after, eq, value) == (after, eq)
    wrong = bytearray(after); wrong[109] ^= 1
    with pytest.raises(ValueError, match='pre/postimages'):
        changes.apply(bytes(wrong), eq, value)


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
