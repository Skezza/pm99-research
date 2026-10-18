import pytest
from scripts import checkpoint_exact_primary_position_v1 as subject


def test_existing_position_checkpoint_cannot_be_republished(tmp_path):
    output=tmp_path/'output.json';output.touch()
    with pytest.raises(ValueError,match='must not repeat'):
        subject.run(tmp_path,'2021-22','actual','replay',tmp_path/'previous',output,'tag',[])


def test_position_checkpoint_refuses_intervening_default(monkeypatch,tmp_path):
    monkeypatch.setattr(subject.pipeline,'read_json_file',lambda path:dict(current_release_bindings=['original']))
    monkeypatch.setattr(subject,'bindings',lambda:['newer'])
    with pytest.raises(ValueError,match='defaults differ'):
        subject.run(tmp_path,'2021-22','actual','replay',tmp_path/'previous',tmp_path/'output','tag',[])
