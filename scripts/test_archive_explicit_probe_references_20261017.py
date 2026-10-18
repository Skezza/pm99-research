import pytest
from scripts import archive_superseded_2004_probes_20261017 as subject


def setup(monkeypatch,tmp_path):
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    monkeypatch.setattr(subject.registry,'CATALOG_PATH',tmp_path/'data/catalog.json')
    monkeypatch.setattr(subject.registry,'LOCAL_ROOT',tmp_path/'registry')
    monkeypatch.setattr(subject,'SOURCE',tmp_path/'.local')
    monkeypatch.setattr(subject,'NAMES',('exact-retired-probe',))


@pytest.mark.parametrize('relative',['data/catalog.json','registry/releases/2000-01/release/metadata/manifest.json',
    '.local/historical-role-deltas-v1/2000-01/release/source-plan.json'])
def test_reference_in_any_catalog_registered_or_SOURCE_metadata_refuses(monkeypatch,tmp_path,relative):
    setup(monkeypatch,tmp_path);path=tmp_path/relative;path.parent.mkdir(parents=True)
    path.write_text('{"path":".local/exact-retired-probe/required-input.json"}')
    with pytest.raises(ValueError,match='references a probe'):subject.no_registered_references()


def test_unrelated_metadata_and_native_bitmap_tree_are_not_target_dependencies(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    folder=tmp_path/'.local/historical-role-deltas-v1/2000-01/release/game/DBDAT/MINIFOTO';folder.mkdir(parents=True)
    (folder/'native.bmp').write_bytes(b'not recipe metadata')
    subject.no_registered_references()


def test_hardlinked_metadata_is_read_once_without_omitting_reference_scope(monkeypatch,tmp_path):
    import os
    setup(monkeypatch,tmp_path)
    folder=tmp_path/'data';folder.mkdir()
    first=folder/'first.json';first.write_text('{"unrelated":true}')
    os.link(first,folder/'second.json')
    real=type(first).read_text;seen=[]
    def record(path,*args,**kwargs):
        seen.append(path);return real(path,*args,**kwargs)
    monkeypatch.setattr(type(first),'read_text',record)
    subject.no_registered_references()
    assert len(seen)==1


def test_extra_source_folder_called_game_is_not_blindly_pruned(monkeypatch,tmp_path):
    setup(monkeypatch,tmp_path)
    extra=tmp_path/'extra';path=extra/'research/game/source-plan.json'
    path.parent.mkdir(parents=True)
    path.write_text('{"input":".local/exact-retired-probe/source.json"}')
    with pytest.raises(ValueError,match='references a probe'):
        subject.no_registered_references(extra_roots=(extra,))
