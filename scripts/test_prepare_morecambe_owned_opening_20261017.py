import copy
import pytest
from scripts import prepare_morecambe_owned_opening_20261017 as subject


def inputs():
    names=['David McKearney','John Hardiker','Andy Fensome','Mark Wright','Steve Walters',
        'Stuart Drummond','Kenny Takano','Adriano Rigoglioso','Phil Eastwood','John Norman',
        'Andy Banks','Andy Heald','Paul McGuire','Leon Smith','Chris Price','Jamie Murphy','Ryan Black','Garry Thompson']
    positions=['D']*4+['M']*4+['F']*2+['G','M','M','F','M','D','F','F']
    people=[dict(id=f'p{n}',carrier_id=n,club_id='club',name=name,source_name=name,
        facts=dict(birth_date='1970-01-01')) for n,name in zip(range(10986,11004),names)]
    wanted=[]
    ordering=[16]+list(range(10))+list(range(10,16))+[17]
    for number,i in enumerate(ordering):
        name='Mark Smith' if i==16 else names[i]
        wanted.append(dict(source_person=dict(source_player_id='source-'+name),
            source_player=dict(name=name,birth_date='1973-01-02' if i==16 else '1970-01-01',
                position='G' if i==16 else positions[i]),
            membership='starting_xi' if number<11 else 'published_bench'))
    native={p['carrier_id']:dict(name=p['name'],roles=[subject.CENTRAL[pos]]+[98]*5)
        for p,pos in zip(people,positions)}
    return dict(clubs=[dict(id='club',name='Morecambe',carrier_id=3312)],players=people),wanted,native,{n:{3312} for n in native}


def test_same_person_slots_not_reallocated_and_inputs_unchanged():
    args=inputs();before=copy.deepcopy(args)
    rows=subject.decide(*args)
    assert args==before
    assert len(rows)==18 and sum(r['identity_changed'] for r in rows)==1
    assert rows[0]['carrier_id']==11002 and rows[0]['fine_roles']==[0]
    assert all(r['replacement']['source_player']['name']==r['before']['source_name'] for r in rows[1:])


@pytest.mark.parametrize('problem',['keeper','missing-person','duplicate-person','known-date','outside-copy','shared-carrier','wrong-label','wrong-slot'])
def test_adversarial_opening_and_identity_fail_closed(problem):
    package,wanted,native,owners=inputs()
    if problem=='keeper':wanted[0]['source_player']['position']='F'
    if problem=='missing-person':wanted.pop()
    if problem=='duplicate-person':wanted[-1]['source_person']=wanted[-2]['source_person']
    if problem=='known-date':package['players'][0]['facts']['birth_date']='1960-01-01'
    if problem=='outside-copy':package['players'].append(dict(package['players'][0],club_id='another'))
    if problem=='shared-carrier':owners[10986]={3312,3301}
    if problem=='wrong-label':package['clubs'][0]['name']='Barrow'
    if problem=='wrong-slot':package['players'][16]['source_name']='Another Reserve'
    with pytest.raises(ValueError):subject.decide(package,wanted,native,owners)


@pytest.mark.parametrize('broad,bad,expected',[('G',10,0),('D',8,4),('M',2,9),('F',9,12)])
def test_bad_inherited_specialism_is_not_approved_by_permissive_audit(broad,bad,expected):
    args=inputs()
    row=next(p for p in args[1] if p['source_player']['position']==broad and p['source_player']['name']!='Mark Smith')
    person=next(p for p in args[0]['players'] if p['name']==row['source_player']['name'])
    args[2][person['carrier_id']]['roles']=[bad]+[98]*5
    result=subject.decide(*args)
    decision=next(r for r in result if r['carrier_id']==person['carrier_id'])
    assert decision['fine_roles']==[expected]
    assert 'editorial' in decision['fine_role_basis']
