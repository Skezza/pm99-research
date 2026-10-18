import copy
import json
import pytest
from scripts import verify_sourced_opening_broad_roles_v1 as v
from scripts.test_verify_sourced_goalkeeper_roles_v1 import setup as keeper_fixture


def setup(tmp_path,monkeypatch):
    releases,path,output,offset=keeper_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(v.source,'verify_broad_roles',lambda base,plan:None)
    opening=tmp_path/'opening.json';opening.write_text('{"starting_xi":[]}')
    plan={'release_id':'baseline','opening_plan_path':'opening.json',
          'updates':[{'carrier_id':2,'player_id':'keeper','fine_roles':[8]}]}
    path.write_text(json.dumps(plan))
    new=bytearray((releases['repair'].game_path/'DBDAT/JUG98030.FDI').read_bytes())
    new[offset:offset+6]=bytes([9,0,0,0,0,0])
    (releases['repair'].game_path/'DBDAT/JUG98030.FDI').write_bytes(new)
    package=json.loads(releases['baseline'].package_path.read_text())
    changed=copy.deepcopy(package);changed['players'][0]['facts']['fine_roles']=[8]
    releases['repair'].package_path.write_text(json.dumps(changed))
    from scripts import season_package_compiler_v2 as compiler
    monkeypatch.setattr(compiler,'_extract_country_codes_from_textos',lambda path:{})
    monkeypatch.setattr(v.source,'replay',lambda jug,eq,package,path,countries:(jug,[{}]))
    return releases,path,output,offset


def test_only_the_declared_role_bytes_and_recipe_roles_change(tmp_path,monkeypatch):
    releases,path,output,offset=setup(tmp_path,monkeypatch)
    assert v.verify('2000-01','repair',path,output)['corrected_labels']==1
    with pytest.raises(ValueError,match='immutable'):v.verify('2000-01','repair',path,output)


@pytest.mark.parametrize('drift',['native-role','other-byte','kit','rating'])
def test_role_fix_cannot_hide_another_change(tmp_path,monkeypatch,drift):
    releases,path,output,offset=setup(tmp_path,monkeypatch);release=releases['repair']
    if drift=='kit':(release.game_path/'DBDAT/RIDIESC.PKF').write_bytes(b'changed kit')
    elif drift=='rating':
        package=json.loads(release.package_path.read_text());package['players'][0]['facts']['quality']=99
        release.package_path.write_text(json.dumps(package))
    else:
        jug=bytearray((release.game_path/'DBDAT/JUG98030.FDI').read_bytes())
        jug[offset if drift=='native-role' else offset+7]^=1
        (release.game_path/'DBDAT/JUG98030.FDI').write_bytes(jug)
    with pytest.raises(ValueError):v.verify('2000-01','repair',path,output)
