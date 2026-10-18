from scripts import audit_duplicate_club_cohorts_v1 as audit


def club(id, name, division='League Two'):
    return {'carrier_id': id, 'name': name, 'division': division}


def test_many_shared_players_are_not_automatic_club_ownership():
    people = {('full-name-' + str(i), '1980-01-01') for i in range(10)}
    row = audit.classify_pair(club(1, 'First'), club(2, 'Second'), people, people, None, None)
    assert row['basis'] == 'large-player-cohort-overlap-candidate-only'
    assert row['whole_club_replacement_authorised'] is False
    assert audit.classify_pair(club(1, 'First'), club(2, 'Second'), people, {('one', '1980')}, None, None) is None


def test_identical_published_club_id_is_a_distinct_evidence_class():
    source = {'source_club_id': 123}
    row = audit.classify_pair(club(1, 'First'), club(2, 'Second'), set(), set(), source, source)
    assert row['basis'] == 'independently-reparsed-same-published-club-id'
    assert row['whole_club_replacement_authorised'] is False


def test_country_scope_excludes_foreign_homonyms():
    assert audit.classify_pair(club(1, 'United'), club(200, 'United', 'preserve-existing-mode1-membership'),
                               set(), set(), None, None) is None


def test_shirt_label_is_not_an_initial_guess_or_dob_override():
    p = {'name': '#13 Kevin Long', 'facts': {'birth_date': '1990-08-18'}}
    assert audit.identity(p) == ('kevinlong', '1990-08-18')
    assert audit.identity({**p, 'name': '#13 K. Long'}) == ('klong', '1990-08-18')
