import pytest
from scripts import radnicki_nis_2002_original_opening_v1 as opening


def source():
    body=' '.join(['IGRALI U PRVENSTVU (33 igrača)',opening.CATALOGUE,opening.COACH,
        '1.KOLO: RADNIČKI (N) – C. ZVEZDA 0:0',opening.DATE,opening.LINE,
        '2.KOLO: RADNIČKI (N) – ZEMUN 0:2 (0:1)'])
    return ('<html><h1>'+opening.TITLE+'</h1><p>'+body+'</p></html>').encode()


def test_first_eleven_and_used_three_are_uniquely_expanded_from_published_names():
    result=opening.parse(source())
    assert len(result['starting_xi'])==11
    assert result['starting_xi'][0]['name']=='Srđan Soldatović'
    assert result['starting_xi'][2]['name']=='Dragan Đorđević'
    assert result['starting_xi'][7]['name']=='Saša Stojanović'
    assert [(r['name'],r['minute']) for r in result['used_substitutes']]==[
        ('Aleksandar Stanković',82),('Milinko Ilić',70),('Saša Jovanović',58)]
    assert result['unused_substitutes'] is None
    assert result['native_writes']==0


@pytest.mark.parametrize('before,after',[(opening.TITLE,'2003/04'),
    (opening.DATE,opening.DATE.replace('10.08.','17.08.')),
    (opening.LINE,opening.LINE.replace('Soldatović,','Other,',1)),
    (opening.COACH,opening.COACH.replace('1-5.','6-17.',1)),
    ('33 igrača','34 igrača')])
def test_changed_period_match_or_coach_rejected(before,after):
    with pytest.raises(ValueError):opening.parse(source().replace(before.encode(),after.encode()))


def test_annual_presence_does_not_become_opening_reserve_membership():
    result=opening.parse(source())
    assert len(result['annual_identity_catalogue'])==33
    assert result['unused_substitutes'] is None and not result['publication_authorised']


def test_uninitialled_shared_family_is_ambiguous():
    with pytest.raises(ValueError,match='no unique'):
        opening.expand_label('Milenković',opening.parse(source())['annual_identity_catalogue'])


def test_second_match_cannot_be_relabelled_first():
    raw=source().replace(opening.DATE.encode(),b'')
    raw=raw.replace(b'</p>',opening.DATE.encode()+b'</p>')
    with pytest.raises(ValueError,match='not bound'):opening.parse(raw)


def test_other_official_club_path_refused():
    with pytest.raises(ValueError,match='URL'):opening.parse(source(),'https://fkradnickinis.rs/other/')
