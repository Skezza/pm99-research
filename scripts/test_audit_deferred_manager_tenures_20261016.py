from datetime import date
import pytest
from scripts import audit_deferred_manager_tenures_20261016 as subject


def raw(club='1',second=False):
    row='<tr><td><a href="/a/profil/trainer/7" title="Coach One">One</a></td><td></td><td>01/01/1999</td><td>31/12/2001</td></tr>'
    if second:row+='<tr><td><a href="/b/profil/trainer/8" title="Coach Two">Two</a></td><td></td><td>01/01/2000</td><td>31/12/2000</td></tr>'
    return ('<link rel="canonical" href="https://www.transfermarkt.co.uk/club/mitarbeiterhistorie/verein/'+club+'"><table class="items"><tbody>'+row+'</tbody></table>').encode()


def test_filename_never_substitutes_for_canonical_club():
    with pytest.raises(ValueError,match='club identity differs'):
        subject.tenure(raw('2'),1,date(2000,8,1))


def test_literal_tenure_covers_requested_august():
    result=subject.tenure(raw(),1,date(2000,8,1))
    assert (result['manager'],result['source_manager_id'],result['date'])==('Coach One','7','2000-08-01')


def test_no_following_year_or_current_manager_fallback():
    with pytest.raises(subject.history.ManagerHistoryError,match='0 managers'):
        subject.tenure(raw(),1,date(2020,8,1))


def test_good_copy_cannot_hide_overlapping_appointments(tmp_path,monkeypatch):
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    a=tmp_path/'a.html';b=tmp_path/'b.html'
    a.write_bytes(raw());b.write_bytes(raw(second=True))
    result=subject.inspect([a,b],1,date(2000,8,1))
    assert result['status']=='conflicting-original-tenure-claims'
    assert len(result['claims'])==1 and len(result['unusable'])==1


def test_conflicting_caches_cannot_be_majority_voted_away(tmp_path,monkeypatch):
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    a=tmp_path/'a.html';b=tmp_path/'b.html'
    a.write_bytes(raw());b.write_bytes(raw().replace(b'Coach One',b'Coach Two'))
    assert subject.inspect([a,b],1,date(2000,8,1))['status']=='conflicting-original-tenure-claims'


def test_self_declared_canonical_is_not_download_provenance(tmp_path,monkeypatch):
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    path=tmp_path/'1.html';path.write_bytes(raw())
    claim=subject.inspect([path],1,date(2000,8,1),{})['claims'][0]
    assert not claim['original_download_receipt_verified']


def test_download_provenance_requires_exact_club_and_original_hash(tmp_path,monkeypatch):
    monkeypatch.setattr(subject.registry,'ROOT',tmp_path)
    path=tmp_path/'1.html';path.write_bytes(raw())
    digest=subject.registry.sha256_file(path)
    receipts={(1,digest):[dict(receipt_path='original.json',receipt_sha256='bound-hash')]}
    claim=subject.inspect([path],1,date(2000,8,1),receipts)['claims'][0]
    assert claim['original_download_receipt_verified']
    assert claim['download_receipts']==receipts[(1,digest)]
    assert not subject.inspect([path],1,date(2000,8,1),{(2,digest):[1]})['claims'][0]['original_download_receipt_verified']
