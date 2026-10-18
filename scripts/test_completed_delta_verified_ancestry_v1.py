from types import SimpleNamespace
import pytest
from scripts import publish_historical_role_delta_v1 as subject


def fixture(monkeypatch):
    releases={name:SimpleNamespace(release_id=name,package_path=name+'-package',
        compiler_receipt_path=name+'-compiler',build_chain_path=name+'-chain') for name in ('base','identity','shirt','final','sibling')}
    parents={'identity':'base','shirt':'identity','final':'shirt','sibling':'base'}
    receipts={name+'-compiler':dict(source_season_package_sha256=parent+'-package-sha',
        source_compiler_receipt_sha256=parent+'-compiler-sha',source_build_chain_sha256=parent+'-chain-sha')
        for name,parent in parents.items()}
    monkeypatch.setattr(subject.registry,'load_registered_release',lambda season,name:releases[name])
    monkeypatch.setattr(subject.pipeline,'read_json_file',lambda path:receipts[path])
    monkeypatch.setattr(subject.registry,'canonical_document_sha256',lambda path:path+'-sha')
    monkeypatch.setattr(subject.registry,'sha256_file',lambda path:path+'-sha')
    return releases,receipts


def test_every_composed_edge_is_checked_without_any_catalogue_mutation(monkeypatch):
    releases,_=fixture(monkeypatch)
    subject._verify_completed_delta_ancestry('2001-02',releases['base'],'final',['base','identity','shirt','final'])


@pytest.mark.parametrize('chain',[['base','final'],['base','identity','final'],
    ['base','sibling','shirt','final'],['identity','shirt','final'],['base','identity','shirt'],
    ['base','identity','identity','shirt','final'],[],None,'base,final'])
def test_no_skipped_sibling_cyclic_or_guessed_parent_chain(monkeypatch,chain):
    releases,_=fixture(monkeypatch)
    with pytest.raises(ValueError):
        subject._verify_completed_delta_ancestry('2001-02',releases['base'],'final',chain)


@pytest.mark.parametrize('field',['source_season_package_sha256','source_compiler_receipt_sha256','source_build_chain_sha256'])
def test_each_of_the_three_existing_guards_still_blocks_each_edge(monkeypatch,field):
    releases,receipts=fixture(monkeypatch);receipts['shirt-compiler'][field]='changed'
    with pytest.raises(ValueError,match='parent edge'):
        subject._verify_completed_delta_ancestry('2001-02',releases['base'],'final',['base','identity','shirt','final'])
