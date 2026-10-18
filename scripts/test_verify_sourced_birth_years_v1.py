import copy
import json
import pytest
from app.fdi_indexed import IndexedFDIFile
from scripts import verify_sourced_birth_years_v1 as module
from scripts.test_verify_sourced_goalkeeper_roles_v1 import setup as goal_fixture


def setup(tmp_path,monkeypatch):
    releases,path,output,role_offset=goal_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(module.source,'verify',lambda release,plan:None)
    before=(releases['baseline'].game_path/'DBDAT/JUG98030.FDI').read_bytes()
    entry=IndexedFDIFile.from_bytes(before).entries[0]
    native=module.audit.native_player(entry.decode_payload(before),2)
    plan={'release_id':'baseline','updates':[{'carrier_id':2,'birth_date':'2004-11-16'}]}
    path.write_text(json.dumps(plan))
    package={'players':[{'id':'keeper','carrier_id':2,'name':native['name'],
        'facts':{'birth_date':'2004-11-16','quality':50}}],'artifacts':[],'proofs':[]}
    releases['baseline'].package_path.write_text(json.dumps(package))
    after=bytearray(before);year_offset=role_offset+12
    after[year_offset:year_offset+2]=(2004).to_bytes(2,'little')
    releases['repair'].game_path.joinpath('DBDAT/JUG98030.FDI').write_bytes(after)
    repaired=copy.deepcopy(package)
    repaired['artifacts']=[{'id':module.source.PREFIX+'2000-01'}]
    releases['repair'].package_path.write_text(json.dumps(repaired))
    releases['repair'].locator['sourced_birth_year_plan_path']='plan.json'
    return releases,path,output,role_offset,year_offset


def test_actual_native_birthday_reduction_is_independently_measured(tmp_path,monkeypatch):
    releases,path,output,role,year=setup(tmp_path,monkeypatch)
    result=module.verify('2000-01','repair',path,output)
    assert result['before_birthday_disagreements']==1
    assert result['after_birthday_disagreements']==0
    with pytest.raises(ValueError,match='immutable'):
        module.verify('2000-01','repair',path,output)


@pytest.mark.parametrize('problem',['year','role','kit','fact'])
def test_a_date_fix_must_not_hide_other_mutations(tmp_path,monkeypatch,problem):
    releases,path,output,role,year=setup(tmp_path,monkeypatch)
    release=releases['repair']
    if problem in ('year','role'):
        target=release.game_path/'DBDAT/JUG98030.FDI';raw=bytearray(target.read_bytes())
        raw[year if problem=='year' else role]^=1;target.write_bytes(raw)
    elif problem=='kit':(release.game_path/'DBDAT/RIDIESC.PKF').write_bytes(b'wrong kit')
    else:
        package=json.loads(release.package_path.read_text());package['players'][0]['facts']['quality']=99
        release.package_path.write_text(json.dumps(package))
    with pytest.raises(ValueError):module.verify('2000-01','repair',path,output)
    assert not output.exists()
