from types import SimpleNamespace as NS

import pytest

from scripts import season_opening_identity_exchange_v1 as subject
from scripts import season_complete_mode1_opening_v1 as complete


@pytest.mark.parametrize('explicit', [True, False])
def test_no_identity_order_only_never_calls_player_compiler(tmp_path,monkeypatch,explicit):
    game=tmp_path/'DBDAT';game.mkdir()
    (game/'JUG98030.FDI').write_bytes(b'original jug')
    (game/'EQ98030.FDI').write_bytes(b'original eq')
    monkeypatch.setattr(subject.registry,'load_registered_release',lambda *args:NS(game_path=tmp_path,package_path='package'))
    monkeypatch.setattr(subject.pipeline,'read_json_file',lambda _:dict(players=[]))
    monkeypatch.setattr(subject,'bind',lambda package,plan:package)
    monkeypatch.setattr(subject.delta.compiler,'_extract_country_codes_from_textos',lambda _: {})
    monkeypatch.setattr(subject.delta,'compile_players',lambda *args:pytest.fail('empty player compiler invoked'))
    monkeypatch.setattr(complete,'apply',lambda jug,eq,plan:jug)
    monkeypatch.setattr(subject,'preserve_other_records',lambda *args:None)
    monkeypatch.setattr(subject.IndexedFDIFile,'from_bytes',lambda _:NS(entries=[]))
    plan=dict(season='2000-01',release_id='parent',jug_sha256=subject.digest(b'original jug'),
        eq_sha256=subject.digest(b'original eq'),decisions=[],request=dict(orders=[]))
    if explicit:
        plan['complete_mode1_opening']=dict(policy=complete.ORDER_ONLY_POLICY,orders=[])
        assert subject.apply(b'original jug',b'original eq',plan)==(b'original jug',b'original eq')
    else:
        with pytest.raises(ValueError,match='empty compilation'):
            subject.apply(b'original jug',b'original eq',plan)
