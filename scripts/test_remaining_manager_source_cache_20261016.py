import copy
import pytest
from scripts import season_remaining_manager_tenures_20261016 as source


def fixture(tmp_path,monkeypatch):
    monkeypatch.setattr(source.registry,'ROOT',tmp_path)
    monkeypatch.setattr(source,'SOURCE',tmp_path/'source-package.json')
    monkeypatch.setattr(source,'_SOURCE_CACHE',None)
    original=tmp_path/'original.html';original.write_bytes(b'original historical source')
    doc=dict(claims=[dict(raw_sources=[dict(path='original.html',sha256=source.registry.sha256_file(original))])])
    source.pipeline.write_canonical_json(source.SOURCE,doc)
    calls=[]
    def parse():
        calls.append(True)
        return copy.deepcopy(doc)
    monkeypatch.setattr(source.sources,'prepare',parse)
    monkeypatch.setattr(source,'extra_source_inputs',lambda:[])
    return original,doc,calls


def test_original_replay_is_done_once_when_every_bound_input_is_unchanged(tmp_path,monkeypatch):
    _,doc,calls=fixture(tmp_path,monkeypatch)
    assert source.verified_sources()==doc
    assert source.verified_sources()==doc
    assert calls==[True]


def test_changed_original_is_refused_not_silently_approved_by_cache(tmp_path,monkeypatch):
    raw,_,calls=fixture(tmp_path,monkeypatch)
    source.verified_sources();raw.write_bytes(b'different historical source')
    with pytest.raises(ValueError,match='source input changed'):
        source.verified_sources()
    assert len(calls)==1


def test_changed_source_package_is_refused(tmp_path,monkeypatch):
    fixture(tmp_path,monkeypatch)
    source.verified_sources();source.SOURCE.write_bytes(b'changed package')
    with pytest.raises(ValueError,match='source input changed'):
        source.verified_sources()


def test_changed_parser_implementation_is_refused(tmp_path,monkeypatch):
    fixture(tmp_path,monkeypatch)
    code=tmp_path/'parser.py';code.write_bytes(b'original parser')
    monkeypatch.setattr(source,'extra_source_inputs',lambda:[code])
    source.verified_sources();code.write_bytes(b'different parser')
    with pytest.raises(ValueError,match='source input changed'):
        source.verified_sources()


def test_caller_edits_cannot_mutate_cached_source_truth(tmp_path,monkeypatch):
    _,doc,_=fixture(tmp_path,monkeypatch)
    first=source.verified_sources();first['claims'].clear()
    assert source.verified_sources()==doc


def test_internal_cache_mutation_is_detected(tmp_path,monkeypatch):
    fixture(tmp_path,monkeypatch)
    source.verified_sources();source._SOURCE_CACHE['data']['claims'].clear()
    with pytest.raises(ValueError,match='was mutated'):
        source.verified_sources()


def test_initial_source_replay_must_match_retained_package_before_cache_exists(tmp_path,monkeypatch):
    fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(source.sources,'prepare',lambda:dict(claims=[]))
    with pytest.raises(ValueError,match='independently reproduces'):
        source.verified_sources()
    assert source._SOURCE_CACHE is None


def test_same_input_cannot_have_contradictory_hashes():
    with pytest.raises(ValueError,match='contradictory hash'):
        source.source_input_bindings([dict(path='original.html',sha256='a'),dict(path='original.html',sha256='b')])
