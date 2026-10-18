import pytest
from scripts import season_tff_sourced_opening_xi_v1 as m


@pytest.mark.parametrize('position,old,wanted',[('F',0,8),('F',9,8),('M',1,9),('M',4,9),
    ('D',8,4),('G',4,0),('D',1,None),('D',3,None),('M',9,None),('F',8,None),('G',0,None)])
def test_only_contradictory_labels_receive_editorial_central_roles(position,old,wanted):
    assert m.conservative_role(position,old)==wanted


def test_original_profile_binding_cannot_relabel_a_different_person_url():
    m.require_tff_binding({'url':'https://www.tff.org/Default.aspx?pageId=30&kisiId=1224041'},30,'kisiid',1224041)
    for url in ['https://www.tff.org/Default.aspx?pageId=30&kisiId=1252986',
                'https://other.org/Default.aspx?pageId=30&kisiId=1224041',
                'https://www.tff.org/Default.aspx?pageId=30&kisiId=1224041&kisiId=1224041',
                'https://www.tff.org/Default.aspx?pageId=31&kisiId=1224041']:
        with pytest.raises(ValueError):m.require_tff_binding({'url':url},30,'kisiid',1224041)


def sheet():
    links = ''.join(f'<span id="team_grdTakim1_rptKadrolar_ctl{i}_formaNo">{i}.</span>'
        f'<a id="team_grdTakim1_rptKadrolar_ctl{i}_lnkOyuncu" href="Default.aspx?pageId=30&amp;kisiId={i}">PERSON {i}</a>' for i in range(1,12))
    return ('<html><head><title>GAZİANTEPSPOR GALATASARAY A.Ş. - Match</title></head>'
        '<span id="match_lblTarih">9.08.2009 - 19:30</span>'
        '<span id="match_lblOrganizasyonAdi">Turkcell Süper Lig</span>'+links+'</html>').encode('cp1254')


def test_literal_original_person_ids_not_name_deduplication():
    raw=sheet().replace(b'PERSON 2<',b'PERSON 1<')
    result=m.sheet(raw,'2009-08-09','GAZİANTEPSPOR','GALATASARAY A.Ş.')
    assert len(result)==11 and result[0]['registered_name']==result[1]['registered_name']
    assert result[0]['tff_id'] != result[1]['tff_id']


@pytest.mark.parametrize('problem',['date','club','competition','repeat-id','repeat-shirt','absent-player','wrong-provider-page'])
def test_wrong_original_fixture_and_ambiguous_ids_refuse(problem):
    raw=sheet();day='2009-08-09';home='GAZİANTEPSPOR'
    if problem=='date':day='2009-08-10'
    if problem=='club':home='OTHER CLUB'
    if problem=='competition':raw=raw.replace(b'Turkcell',b'Other')
    if problem=='repeat-id':raw=raw.replace(b'kisiId=2"',b'kisiId=1"')
    if problem=='repeat-shirt':raw=raw.replace(b'ctl2_formaNo">2.',b'ctl2_formaNo">1.')
    if problem=='absent-player':raw=raw.replace(b'ctl11_lnkOyuncu',b'ctl11_missing')
    if problem=='wrong-provider-page':raw=raw.replace(b'pageId=30',b'pageId=31')
    with pytest.raises(ValueError):m.sheet(raw,day,home,'GALATASARAY A.Ş.')


def profile():
    prefix='person_OyuncuDisplay1_oyuncuBilgileri_'
    return ''.join(f'<span id="{prefix}{key}">{value}</span>' for key,value in
        [('lblAdi','REAL FULL NAME'),('Label10','Doğum Tarihi'),('Label2','17 Kasım 1978'),('Label3','TC')]).encode('cp1254')


def test_profile_birthday_and_explicit_Turkish_nationality_alias():
    assert m.profile(profile(),'REAL FULL NAME')=={'registered_name':'REAL FULL NAME','birth_date':'1978-11-17','nationality':'TUR'}


@pytest.mark.parametrize('problem',['wrong-person','wrong-label','missing-DOB','invalid-date'])
def test_wrong_profile_is_not_an_identity_witness(problem):
    raw=profile();name='REAL FULL NAME'
    if problem=='wrong-person':name='OTHER PERSON'
    if problem=='wrong-label':raw=raw.replace('Doğum Tarihi'.encode('cp1254'),b'Other field')
    if problem=='missing-DOB':raw=raw.replace(b'Label2',b'Other')
    if problem=='invalid-date':raw=raw.replace(b'17 Kas',b'31 Kas')
    with pytest.raises(ValueError):m.profile(raw,name)


def test_positive_first_fixture_policy_can_read_past_section_without_merging_names():
    raw=('=  Gaziantepspor - Turkish Süper Lig 2009/10\n\n'
         'Number, Name, Nat, Pos, Height, Weight, Date of Birth, Birth Place, Previous Club\n'
         '99, Júlio César, BRA, F, 1.76, 75, 26-02-80, Place, Club\n'
         '== Past Players\n'
         'Number, Name, Nat, Pos, Height, Weight, Date of Birth, Birth Place, New Club\n'
         '55, Júlio César, BRA, D, 1.83, 78, 17-11-78, Place, Club\n').encode()
    rows=m.annual_rows(raw,'2009-10','Gaziantepspor')
    assert len(rows)==2 and rows[0]['name']==rows[1]['name']
    assert [(r['birth_date'],r['position'],r['past_player']) for r in rows]==[
        ('1980-02-26','F',False),('1978-11-17','D',True)]
    with pytest.raises(ValueError):m.annual_rows(raw,'2010-11','Gaziantepspor')


def biography():
    return ('<h1>Beto (footballer, born October 1981)</h1><table class="infobox">'
        '<tr><th>Full name</th><td>André Roberto Soares da Silva</td></tr>'
        '<tr><td><span class="bday">1981-10-25</span></td></tr></table>').encode()


def test_nickname_full_identity_bridge_needs_published_full_name_and_DOB():
    source={'name':'Beto','birth_date':'1981-10-25'}
    assert m.biography_alias(biography(),source,'ANDRE ROBERTO SOARES DA SILVA')['sporting_name']=='Beto'
    for raw in [biography().replace(b'1981-10-25',b'1981-10-02'),biography().replace(b'Roberto',b'Other'),biography().replace(b'Full name',b'Nickname')]:
        with pytest.raises(ValueError):m.biography_alias(raw,source,'ANDRE ROBERTO SOARES DA SILVA')
