"""A late annual snapshot is not the authority for the opening squad."""
import copy
import pytest
from scripts import prepare_stoke_vandeurzen_reserve_20261016 as subject


def values():
    return [dict(name='Jurgen Vandeurzen', birth_date='1974-01-26'),
        dict(anchor='2002-08-01', owner=dict(club='Stoke City', entry_year=2001, departure_year=2003, loan=False)),
        dict(date='2002-08-10', source_club_id=512, positive_substitution=dict(source_player_id=20366,
            name='Jurgen Vandeurzen', club_id=512, replaced_player_id=13561, replaced_player_name='Kris Commons')),
        dict(name='Jurgen Van Deurzen', birth_date='1974-01-26', position='M', nationality=None,
            height_cm=170, weight_kg=70, shirt_number=27, unresolved_fields=['nationality']), []]


def test_positive_bench_and_tenure_allow_explicit_annual_omission():
    args = values(); before = copy.deepcopy(args)
    result = subject.reconcile(*args)
    assert args == before
    assert result['current_annual_omission_explicit']
    assert result['source_player']['nationality'] is None
    assert result['source_player']['shirt_number'] is None
    assert result['source_player']['birth_date'] == '1974-01-26'


@pytest.mark.parametrize('index,key,value,reason', [
    (0, 'birth_date', '1972-01-26', 'full-name/DOB'),
    (2, 'date', '2003-08-10', 'opening substitution'),
    (2, 'source_club_id', 513, 'opening substitution'),
    (2, 'positive_substitution', {'source_player_id': 20367}, 'opening substitution'),
])
def test_wrong_person_year_club_or_provider_id_refused(index, key, value, reason):
    args = values(); args[index][key] = value
    with pytest.raises(ValueError, match=reason):
        subject.reconcile(*args)


def test_career_entry_boundary_not_promoted_to_positive_august_tenure():
    args = values(); args[1]['owner']['entry_year'] = 2002
    with pytest.raises(ValueError, match='senior ownership'):
        subject.reconcile(*args)


def test_changed_current_annual_is_not_silently_waived():
    args = values(); args[4].append(dict(name='Jurgen Vandeurzen'))
    with pytest.raises(ValueError, match='omission changed'):
        subject.reconcile(*args)


def event(club=512, incoming=20366, outgoing=13561):
    return f'<div id="sb-wechsel"><ul><li><div class="sb-aktion-wappen">' \
        f'<a href="/stoke-city/startseite/verein/{club}/saison_id/2002">Stoke</a></div>' \
        f'<span class="sb-aktion-wechsel-ein"><a title="Jurgen Vandeurzen" href="/player/spieler/{incoming}/saison/2002">Vandeurzen</a></span>' \
        f'<span class="sb-aktion-wechsel-aus"><a title="Kris Commons" href="/player/spieler/{outgoing}/saison/2002">Commons</a></span></li></ul></div>'


def test_original_incoming_substitution_is_not_mislabelled_as_a_full_bench():
    assert subject.substitution(event())['source_player_id'] == 20366


@pytest.mark.parametrize('kwargs', [dict(club=5120), dict(incoming=203660), dict(outgoing=135610)])
def test_substitution_requires_exact_not_prefix_club_and_person_ids(kwargs):
    with pytest.raises(ValueError, match='one exact original'):
        subject.substitution(event(**kwargs))


def test_two_identical_events_are_ambiguous_not_arbitrarily_selected():
    with pytest.raises(ValueError, match='one exact original'):
        subject.substitution(event() + event())
