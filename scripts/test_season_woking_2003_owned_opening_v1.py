from types import SimpleNamespace
import pytest
from bs4 import BeautifulSoup
from scripts import season_woking_2003_owned_opening_v1 as source
from scripts import build_woking_owned_opening_20261011 as build


def test_wrong_season_refuses_before_source_io():
    with pytest.raises(ValueError,match='2003 only'):
        source.prepare(SimpleNamespace(season='2004-05'))


def test_selected_carriers_are_exact_separate_native_families():
    assert source.selected_carriers({})==set(range(11141,11157))|{33060}


def test_factory_rebuild_cannot_drop_paired_ownership():
    source.reject_factory_recipe(dict(artifacts=[]))
    with pytest.raises(ValueError,match='source-bound'):
        source.reject_factory_recipe(dict(artifacts=[dict(id=source.PREFIX+'2003-04')]))


def test_original_anchors_are_literal_not_approximate():
    page=BeautifulSoup('<p>Nationality   England</p>','lxml')
    source.require(page,'Nationality England')
    with pytest.raises(ValueError):source.require(page,'Nationality Wales')


def test_skill_family_marker_follows_two_byte_record_header(monkeypatch):
    raw=b'\x7f\x01\xdd\x63\x61'+b'\x61'*20+bytes(v^0x61 for v in range(10))+b'\x61'*6
    entry=SimpleNamespace(record_id=33060,decode_payload=lambda data:raw)
    monkeypatch.setattr(build,'IndexedFDIFile',SimpleNamespace(from_bytes=lambda data:SimpleNamespace(entries=[entry])))
    assert build.skills(b'ignored',33060)==dict(zip(build.delta.compiler.SKILLS,range(9)),handling=9)


@pytest.mark.parametrize('fault',['appointment','departure','heading','interior_year'])
def test_manager_requires_all_original_temporal_and_identity_anchors(monkeypatch,fault):
    appointment=('Friday, 8 November, 2002 Glenn Cockerill has been appointed the new manager '
                 'nearly a month as acting manager Geoff Chapple')
    departure=('Thursday, 29 March 2007 Woking have sacked manager Glenn Cockerill '
               'Cockerill replaced Geoff Chapple as caretaker manager at Kingfield in October 2002')
    wiki='<h1>Glenn Cockerill</h1><p>2002–2007 Woking</p>'
    pages={source.URLS['woking-original-bbc-appointment']:appointment,
           source.URLS['woking-original-bbc-departure']:departure,
           source.URLS['glenn-cockerill-original-wikipedia']:wiki}
    def raw(key,proofs):
        text=pages[source.URLS[key]]
        return text.encode(),BeautifulSoup(text,'lxml')
    monkeypatch.setattr(source,'raw_source',raw)
    assert source.manager([])['name']=='Glenn Cockerill'
    if fault=='appointment':pages[source.URLS['woking-original-bbc-appointment']]=appointment.replace('2002','2004')
    if fault=='departure':pages[source.URLS['woking-original-bbc-departure']]=departure.replace('2007','2003')
    if fault=='heading':pages[source.URLS['glenn-cockerill-original-wikipedia']]=wiki.replace('<h1>Glenn','<h1>Joe')
    if fault=='interior_year':pages[source.URLS['glenn-cockerill-original-wikipedia']]=wiki.replace('2002–2007','2004–2007')
    with pytest.raises(ValueError):source.manager([])
