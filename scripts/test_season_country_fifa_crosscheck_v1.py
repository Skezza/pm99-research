from scripts import season_country_fifa_crosscheck_v1 as subject


def player():return dict(name='#7 Liam Mandeville',source_name='Liam Mandeville',facts=dict(birth_date='1997-02-17'))


def index(country='England',edition=18,born='1997-02-17'):
    return {(edition,born):[dict(player_id='original-person',long_name='Liam Mandeville',short_name='L. Mandeville',
        dob=born,nationality_name=country,fifa_version=str(edition),fifa_update_date='2017-09-20')]}


def test_wrong_annual_spain_proposal_is_not_blindly_approved():
    result=subject.check(dict(before_player=player(),nationality='ESP'),'2017-18',index=index(),file_sha='test-source')
    assert result['status']=='contradiction-requires-resolution'
    assert result['FIFA_country']=='ENG' and result['country_truth_approved'] is False


def test_two_sources_agree_but_do_not_claim_global_historical_certification():
    result=subject.check(dict(before_player=player(),nationality='ENG'),'2017-18',index=index(),file_sha='test-source')
    assert result['status']=='corroborated' and result['country_truth_approved'] is False


def test_no_neighbouring_edition_or_other_birthday_substitution():
    assert subject.match(player(),'2016-17',index()) is None
    assert subject.match(player(),'2017-18',index(born='1997-02-18')) is None


def test_first_name_initial_only_is_not_a_full_person_match():
    person=player();person.update(name='L. Mandeville',source_name='L. Mandeville')
    assert subject.match(person,'2017-18',index()) is None


def test_two_published_people_with_same_full_name_and_birthday_refuse():
    data=index();data[18,'1997-02-17'].append(dict(data[18,'1997-02-17'][0],player_id='another-person'))
    assert subject.match(player(),'2017-18',data) is None


def test_distinct_congo_labels_remain_distinct():
    assert subject.code('Congo DR')=='COD'
    assert subject.code('Congo')=='CGO'
