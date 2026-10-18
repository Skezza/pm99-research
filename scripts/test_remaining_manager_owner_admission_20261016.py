from types import SimpleNamespace
import pytest
from scripts import season_remaining_manager_tenures_20261016 as source
from scripts import coupled_manager_timeline_admission_20261016 as coupled


def test_country_scoped_aliases_never_select_an_unrelated_basel_club(monkeypatch):
    monkeypatch.setattr(coupled.roster,'club_group',lambda c:c['country'])
    clubs=[dict(id='right',name='Basel',full_name='Basel',country='switzerland'),
        dict(id='wrong-country',name='Basel',full_name='Basel',country='germany'),
        dict(id='different-club',name='Black Stars Basel',full_name='Black Stars Basel',country='switzerland')]
    assert [c['id'] for c in coupled.exact_native_clubs(dict(clubs=clubs),26)]==['right']


def test_duplicate_native_club_aliases_are_not_arbitrarily_assigned_a_coach(monkeypatch):
    monkeypatch.setattr(coupled,'originals',lambda:[dict(source_club_id=26,path='must-not-read')])
    monkeypatch.setattr(coupled,'exact_native_clubs',lambda *a:[dict(id='a',name='Basel'),dict(id='b',name='FC Basel 1893')])
    monkeypatch.setattr(coupled,'original_roster_owner',lambda *a:(None,None))
    rows,unchanged,unresolved=coupled.claims_for(SimpleNamespace(),dict(managers=[]),{}, {},lambda _:None)
    assert rows==unchanged==[] and len(unresolved)==1
    assert unresolved[0]['manager_approved'] is False


def collision_fixture():
    package=dict(managers=[dict(id='a',carrier_id=10,name='King',policy='preserve-existing-mode1'),
        dict(id='b',carrier_id=20,name='Phil Parkinson',person_id='legacy-peer3540',policy='write')],
        clubs=[dict(id='altrincham',manager_id='a',carrier_id=1,name='Altrincham'),
            dict(id='sunderland',manager_id='b',carrier_id=2,name='Sunderland')])
    row=dict(manager_id='a',after='Phil Parkinson',source_manager_id='84629',native_after='Parkinson',
        evidence=dict(same_name_peer=dict(club='Sunderland',source_club_id=289,manager='Phil Parkinson',source_manager_id='3540')))
    holders={20:[dict(carrier_id=2)]}; names={20:'Phil Parkinson'}
    reports={'sunderland':dict(evidence=dict(source_club_id=289))}
    return package,row,holders,names,reports


def test_distinct_original_people_with_same_name_keep_distinct_person_aliases():
    package,row,holders,names,reports=collision_fixture()
    assert source.resolve_collisions(package,[row],holders,names,reports)==[]


def test_same_published_person_id_is_not_waived_as_a_namesake():
    package,row,holders,names,reports=collision_fixture()
    row['evidence']['same_name_peer']['source_manager_id']='84629'
    with pytest.raises(ValueError,match='peer source identity'):
        source.resolve_collisions(package,[row],holders,names,reports)


def test_shared_native_peer_owner_is_not_waived():
    package,row,holders,names,reports=collision_fixture()
    holders[20].append(dict(carrier_id=3))
    with pytest.raises(ValueError,match='native club owner'):
        source.resolve_collisions(package,[row],holders,names,reports)


def test_person_alias_collision_is_refused_even_for_proven_distinct_namesakes():
    package,row,holders,names,reports=collision_fixture()
    package['managers'][1]['person_id']=source.coach_person_alias('Phil Parkinson')
    with pytest.raises(ValueError,match='person alias collides'):
        source.resolve_collisions(package,[row],holders,names,reports)


def test_other_qualified_identity_cannot_be_hidden_as_a_stock_name():
    package,row,holders,names,reports=collision_fixture()
    row['evidence']['same_name_peer']=None
    with pytest.raises(ValueError,match='qualified coach'):
        source.resolve_collisions(package,[row],holders,names,reports)


def test_unqualified_stock_name_remains_an_open_warning_not_a_verified_namesake():
    package,row,holders,names,reports=collision_fixture()
    package['managers'][1].pop('person_id');package['managers'][1]['policy']='preserve-existing-mode1'
    row['evidence']['same_name_peer']=None
    warnings=source.resolve_collisions(package,[row],holders,names,reports)
    assert len(warnings)==1 and 'remain open' in warnings[0]['reason']


def test_compact_editorial_alias_does_not_guess_legal_family_names_globally():
    alias,reason=source.display_name('Júlio César Leal')
    assert alias=='J. C. Leal' and 'not-legal-family-name-claim' in reason
    assert source.display_name('Unknown Three Parts')[0] is None
