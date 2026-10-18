from types import SimpleNamespace
from scripts import rehearse_country_only_ancestry_20261017 as subject


def test_readonly_explicit_release_rehearsal_records_concurrent_publication(monkeypatch,tmp_path):
    catalog=tmp_path/'catalog.json';catalog.write_bytes(b'before')
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    monkeypatch.setattr(subject.registry,'CATALOG_PATH',catalog)
    actual=SimpleNamespace(release_id='actual',game_path=tmp_path/'game')
    monkeypatch.setattr(subject.registry,'load_registered_release',lambda *args:actual)
    def verify(*args):
        catalog.write_bytes(b'another season published concurrently')
        return [dict(carrier_id=12,nationality='SCO',native_country_code=49)],{12:dict(path='dated-source')},dict(edges=[{},{}])
    monkeypatch.setattr(subject.ancestry,'verify',verify)
    monkeypatch.setattr(subject.ancestry.v2.compiler,'_extract_country_codes_from_textos',lambda path:dict(SCOTLAND=49))
    saved=[];monkeypatch.setattr(subject,'retained',lambda path,proof:saved.append(proof))
    subject.main()
    assert len(saved)==1
    proof=saved[0]
    assert proof['preferred_writes']==proof['regenerated_seasons']==0
    assert proof['concurrent_external_default_advance_observed'] is True
    assert proof['preferred_catalog_unchanged_during_rehearsal'] is False
    assert proof['final_semantic_countries'][0]['native_label']=='SCOTLAND'
