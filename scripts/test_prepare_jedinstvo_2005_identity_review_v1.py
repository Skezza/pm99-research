from copy import deepcopy
import pytest
from scripts import jedinstvo_2005_original_opening_v1 as opening
from scripts import prepare_jedinstvo_2005_identity_review_v1 as review


def inputs():
    labels=opening.XI+['Franca','Čindrak','Ćurkić']
    actual=dict(season='2005-06',fixture_date='2005-08-06',club='Jedinstvo Bijelo Polje',
        starting_xi=opening.XI.copy(),used_substitutes=[dict(name=n) for n in labels[11:]])
    identities={i:dict(name=n if ' ' in n else 'Given '+n,birth_date='1980-01-01',position='G' if i==0 else 'D')
        for i,n in enumerate(labels)}
    return actual,identities,deepcopy(identities)


def test_original_labels_join_uniquely_without_invented_bench():
    result=review.join_opening(*inputs())
    assert len(result)==14 and result[1]['canonical_published_name']=='Ermin Drndar'
    assert result[10]['canonical_published_name']=='Ekrem Drndar'
    assert result[-1]['membership']=='used-opening-substitute'


@pytest.mark.parametrize('mutation',['dob','name','missing','ambiguous','keeper','date','count','repeat'])
def test_wrong_or_ambiguous_identity_rejected(mutation):
    actual,identities,people=inputs()
    if mutation=='dob':people[1]['birth_date']='1981-01-01'
    if mutation=='name':people[1]['name']='Ekrem Drndar'
    if mutation=='missing':people.pop(1)
    if mutation=='ambiguous':identities[99]=dict(identities[2],name='Other Pešić')
    if mutation=='keeper':identities[0]['position']='F'
    if mutation=='date':actual['fixture_date']='2005-08-13'
    if mutation=='count':actual['starting_xi'].pop()
    if mutation=='repeat':actual['starting_xi'][2]='Jovšić'
    with pytest.raises(ValueError):review.join_opening(actual,identities,people)


def report():
    return ('<title>Borba, 11. 07. 2005., S. 12 — Library</title>'
        'Ugovorne obaveze sa Jedinstvom Mladen Kaluđerović iz Dečića, koji igra na\n'
        'poziciji štopera i Bojan Šljivančanin iz pljevaljskog\nRudara '
        'granitnu odbranu Jedinstva čine kolosi').encode()


def test_original_linewraps_allowed():
    review.signed_arrival_report(report())


@pytest.mark.parametrize('old,new',[
    ('11. 07. 2005.','11. 07. 2006.'),('Mladen Kaluđerović','Wrong Player'),
    ('Bojan Šljivančanin','Wrong Player'),('poziciji štopera','poziciji napadača')])
def test_wrong_signed_arrival_date_person_or_role_rejected(old,new):
    with pytest.raises(ValueError):review.signed_arrival_report(report().decode().replace(old,new).encode())
