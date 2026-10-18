from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import season_opening_identity_exchange_v1 as subject


@pytest.fixture
def source_profile(tmp_path, monkeypatch):
    path = tmp_path / 'profile.html'
    path.write_text('''<link rel="canonical" href="https://www.transfermarkt.us/sample/profil/spieler/12">
        <h1 class="data-header__headline-wrapper">Sample Player</h1>
        <span itemprop="birthDate">Oct 10, 1988 (38)</span>
        <span itemprop="nationality">Benin</span>
        <span class="data-header__label">Position:<span class="data-header__content">Centre-Forward</span></span>''')
    monkeypatch.setattr(subject, 'original', lambda value: path)
    monkeypatch.setattr(subject, 'match_people', lambda value: ([], [dict(source_player_id='12', display_name='Sample Player')]))
    selection = dict(provider_player_id=12, name='Sample Player', birth_date='1988-10-10',
        profile='profile', match='fixture', profile_position='Centre-Forward', position='F',
        fine_roles=[12], nationality_label='Benin', nationality='BEN')
    evidence = dict(profile=dict(path='profile.html', sha256='bound', url='https://www.transfermarkt.us/sample/profil/spieler/12'),
                    fixture=dict(date='2013-08-17'))
    return path, selection, evidence


def test_new_person_exact_us_date_and_identity_without_present_day_body_facts(source_profile):
    _, selection, evidence = source_profile
    result = subject.new_person(selection, evidence)
    assert result['source_person']['birth_date'] == '1988-10-10'
    assert result['source_player']['nationality'] == 'BEN'
    assert result['source_player']['height_cm'] is None
    assert result['source_player']['weight_kg'] is None


@pytest.mark.parametrize('field,value', [('nationality', 'ENG'), ('nationality_label', 'England'),
    ('birth_date', '1989-10-10'), ('name', 'Someone Else'), ('fine_roles', [4]),
    ('position', 'D'), ('profile_position', 'Goalkeeper'), ('provider_player_id', 13)])
def test_new_person_rejects_wrong_identity_roles_or_nationality(source_profile, field, value):
    _, selection, evidence = source_profile
    selection[field] = value
    with pytest.raises(ValueError): subject.new_person(selection, evidence)


def test_new_person_rejects_sidebar_link_in_another_canonical_profile(source_profile):
    path, selection, evidence = source_profile
    path.write_text(path.read_text().replace('/spieler/12', '/spieler/99'))
    with pytest.raises(ValueError, match='canonical'): subject.new_person(selection, evidence)


def test_new_person_rejects_non_august_and_missing_bench(source_profile, monkeypatch):
    _, selection, evidence = source_profile
    evidence['fixture']['date'] = '2013-09-01'
    with pytest.raises(ValueError, match='August'): subject.new_person(selection, evidence)
    evidence['fixture']['date'] = '2013-08-17'
    monkeypatch.setattr(subject, 'match_people', lambda value: ([], []))
    with pytest.raises(ValueError, match='published bench'): subject.new_person(selection, evidence)


@pytest.mark.parametrize('bad', [None, 'wrong-date', 'missing-date', 'missing-anchor'])
def test_dated_source_requires_reproducible_literal_date(tmp_path, monkeypatch, bad):
    path = tmp_path / 'source.html'
    path.write_text('<p>Werder Bremen Ludovic Obraniak (ab 30.01.2014)</p>')
    monkeypatch.setattr(subject, 'original', lambda value: path)
    source = dict(anchors=['Ludovic Obraniak (ab 30.01.2014)'], date_anchor='30.01.2014', event_date='2014-01-30')
    if bad == 'wrong-date': source['event_date'] = '2013-01-30'
    if bad == 'missing-date': source.pop('date_anchor')
    if bad == 'missing-anchor': source['anchors'] = ['30.01.2013']
    if bad is None: subject.dated_source(source)
    else:
        with pytest.raises(ValueError): subject.dated_source(source)


def test_provider_bench_mapping_cannot_cross_two_resulting_people(monkeypatch):
    bench = [dict(source_player_id='12', display_name='Sample One'), dict(source_player_id='13', display_name='Sample Two')]
    monkeypatch.setattr(subject, 'match_people', lambda value: ([], bench))
    package = dict(players=[dict(carrier_id=1, name='Sample One'), dict(carrier_id=2, name='Sample Two')])
    row = dict(match='fixture', bench_mapping=[dict(provider_player_id=12, carrier_id=1), dict(provider_player_id=13, carrier_id=2)])
    subject.verify_bench_mapping(package, row, {'fixture': {}})
    row['bench_mapping'][0]['carrier_id'], row['bench_mapping'][1]['carrier_id'] = 2, 1
    with pytest.raises(ValueError, match='another resulting identity'):
        subject.verify_bench_mapping(package, row, {'fixture': {}})


@pytest.mark.parametrize('mutation', [False, True])
def test_unselected_ordered_record_only_allows_the_order_byte(monkeypatch, mutation):
    monkeypatch.setattr(subject, 'read_initial_order', lambda raw: SimpleNamespace(order=raw[-1]))
    monkeypatch.setattr(subject, 'replace_initial_order', lambda raw, order, **kw: raw[:-1] + bytes([order]))
    before = b'IDENTITY-FACTS-SKILLS\x0e'
    after = before[:-1] + b'\x0f'
    if mutation: after = b'WRONG' + after[5:]
    if mutation:
        with pytest.raises(ValueError, match='startup-order byte'):
            subject.verify_order_only_record(before, after)
    else: subject.verify_order_only_record(before, after)


def test_full_name_spelling_fold_does_not_accept_surnames_or_initials():
    assert subject.published_name_key('Thomas Sørensen') == subject.published_name_key('Thomas Sörensen')
    assert subject.published_name_key('Thomas Sørensen') != subject.published_name_key('Sørensen')
    assert subject.published_name_key('Thomas Sørensen') != subject.published_name_key('T. Sørensen')


def test_bench_source_club_cannot_be_an_unrelated_destination(tmp_path, monkeypatch):
    path = tmp_path / 'match.html'
    path.write_text('<a href="/cardiff/startseite/verein/603" title="Cardiff City">Cardiff City</a>')
    monkeypatch.setattr(subject, 'original', lambda value: path)
    subject.verify_match_club(dict(provider_club_id=603), 'Cardiff City')
    with pytest.raises(ValueError, match='destination native club'):
        subject.verify_match_club(dict(provider_club_id=603), 'Stoke City')


def test_factory_refuses_native_exchange_and_unrelated_reconstruction_is_untouched(tmp_path):
    with pytest.raises(ValueError, match='source reconstruction'):
        subject.reject_factory_recipe(dict(artifacts=[dict(id=subject.PREFIX + 'example')]))
    subject.reject_factory_recipe(dict(artifacts=[]))
    assert subject.reconstruction(SimpleNamespace(locator={}), 'unused') is None


def test_reconstruction_does_not_follow_an_inherited_other_type_locator(tmp_path):
    import json
    compiler = tmp_path / 'compiler.json'
    compiler.write_text(json.dumps(dict(compilation_mode='a-newer-unrelated-layer')))
    previous = SimpleNamespace(compiler_receipt_path=compiler,
        locator=dict(sourced_profile_assignment_plan_path='must-not-be-opened'))
    assert subject.reconstruction(previous, 'unused') is None
