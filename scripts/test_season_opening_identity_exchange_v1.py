from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path

import pytest

from scripts import season_opening_identity_exchange_v1 as subject


ROOT = Path(__file__).resolve().parents[1]
NORWICH_REPORT = ROOT / ".local/transfermarkt-opening-plans-current-v1/2000-01/cache/report/3138386.html"
NORWICH_FIXTURE = {
    "path": str(NORWICH_REPORT.relative_to(ROOT)),
    "sha256": "0c230e9810a6bcfb148fbd912feef5405462842edc259fcef176894a23d14980",
    "url": "https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/3138386",
    "provider_club_id": 1123,
    "date": "2000-08-12",
    "membership_mode": "classic-played-substitutes",
}


@pytest.fixture
def norwich_report():
    if not NORWICH_REPORT.is_file():
        pytest.skip('retained original Norwich match unavailable')
    return NORWICH_REPORT


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


@pytest.mark.parametrize('part', ['request', 'canonical'])
def test_profile_rejects_spoofed_source_origin(source_profile, part):
    path, selection, evidence = source_profile
    if part == 'request':
        evidence['profile']['url'] = evidence['profile']['url'].replace('www.transfermarkt.us', 'example.org')
    else:
        path.write_text(path.read_text().replace('www.transfermarkt.us', 'example.org'))
    with pytest.raises(ValueError, match='origin'):
        subject.read_transfermarkt_profile(evidence['profile'], selection['provider_player_id'])


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


def test_classic_played_substitutes_are_exact_club_used_people_not_a_complete_bench(norwich_report):
    xi, used = subject.match_people(NORWICH_FIXTURE)
    assert len(xi) == 11
    assert [(row['display_name'], row['source_player_id']) for row in used] == [
        ('Gaetano Giallanza', '11521'),
        ('Adrian Forbes', '44590'),
        ('Raymond de Waard', '186208'),
    ]
    assert all(row['membership_basis'] == 'published-used-substitute-not-complete-bench' for row in used)
    # A goals-section participant from the opponent is not a Norwich member.
    assert '222092' not in {row['source_player_id'] for row in xi + used}


@pytest.mark.parametrize('field,value,match', [
    ('provider_club_id', 9999, 'exact club box'),
    ('date', '2000-08-13', 'match date'),
])
def test_classic_substitutes_reject_wrong_club_or_date(field, value, match, norwich_report):
    forged = dict(NORWICH_FIXTURE, **{field: value})
    with pytest.raises(ValueError, match=match):
        subject.match_people(forged)


def test_classic_substitutes_reject_wrong_original_sha(norwich_report):
    forged = dict(NORWICH_FIXTURE, sha256='0' * 64)
    with pytest.raises(ValueError, match='source changed'):
        subject.match_people(forged)


def test_classic_substitution_outgoing_person_must_be_current_club_participant(tmp_path, monkeypatch, norwich_report):
    from bs4 import BeautifulSoup

    page = BeautifulSoup(NORWICH_REPORT.read_bytes(), 'html.parser')
    target = None
    for event in page.select('li.sb-aktion-heim, li.sb-aktion-gast'):
        badge = event.select_one('.sb-aktion-wappen')
        if badge and badge.select_one('a[href*="/verein/1123/"]') and event.select_one('.sb-aktion-wechsel-aus a[href]'):
            target = event.select_one('.sb-aktion-wechsel-aus a[href]')
            break
    assert target is not None
    import re
    target['href'] = re.sub(r'(/spieler/)\d+', r'\g<1>999999', target['href'])
    altered = tmp_path / 'altered-match.html'
    altered.write_text(str(page), encoding='utf-8')
    monkeypatch.setattr(subject, 'original', lambda _value: altered)

    with pytest.raises(ValueError, match='exact club participants'):
        subject.match_people(NORWICH_FIXTURE)


def test_classic_mode_ignores_same_club_goal_or_card_without_substitution(tmp_path, monkeypatch, norwich_report):
    from bs4 import BeautifulSoup

    page = BeautifulSoup(NORWICH_REPORT.read_bytes(), 'html.parser')
    events = page.select_one('#sb-wechsel ul')
    events.append(BeautifulSoup('''<li class="sb-aktion-heim"><div class="sb-aktion-wappen">
        <a href="/club/startseite/verein/1123/saison_id/2000">Norwich City</a></div>
        <div class="sb-aktion-aktion">Yellow card</div></li>''', 'html.parser').li)
    altered = tmp_path / 'report-with-card.html'
    altered.write_text(str(page), encoding='utf-8')
    monkeypatch.setattr(subject, 'original', lambda _value: altered)

    xi, used = subject.match_people(NORWICH_FIXTURE)
    assert len(xi) == 11
    assert [row['source_player_id'] for row in used] == ['11521', '44590', '186208']


def test_new_person_membership_labels_played_substitute_without_claiming_complete_bench(source_profile, monkeypatch):
    _path, selection, evidence = source_profile
    evidence['fixture'].update(date='2000-08-12', membership_mode='classic-played-substitutes')
    monkeypatch.setattr(subject, 'match_people', lambda _value: ([], [dict(source_player_id='12', display_name='Sample Player',
        membership_basis='published-used-substitute-not-complete-bench')]))
    result = subject.new_person(selection, evidence)
    assert result['membership'] == 'original-published-opening-used-substitute'


def test_classic_played_substitutes_cannot_authorise_complete_bench_order(tmp_path, monkeypatch):
    from scripts import season_opening_order_repair_v1 as ownership

    input_path = tmp_path / 'request.json'
    input_path.write_text('{}', encoding='utf-8')
    game = tmp_path / 'game'
    (game / 'DBDAT').mkdir(parents=True)
    (game / 'DBDAT/JUG98030.FDI').write_bytes(b'jug')
    (game / 'DBDAT/EQ98030.FDI').write_bytes(b'eq')
    evidence_path = tmp_path / 'match.html'
    evidence_path.write_text('fixture')
    evidence = {'fixture': dict(path='match.html', sha256='bound', date='2000-08-12',
        membership_mode='classic-played-substitutes', anchors=['exact reviewed report'])}

    clubs = [dict(id=1, carrier_id=10, name='Club One'), dict(id=2, carrier_id=20, name='Club Two')]
    players = []
    by_carrier = {}
    for club_id, start, name_prefix in ((1, 100, 'One'), (2, 200, 'Two')):
        for slot in range(1, 13):
            carrier = start + slot
            actor = dict(id=f'player-{carrier}', carrier_id=carrier, club_id=club_id,
                name=f'{name_prefix} Player {slot}', source_name=f'{name_prefix} Player {slot}',
                person_id=f'person-{carrier}',
                facts=dict(birth_date=f'1970-01-{slot:02d}'), ratings=dict(values={'quality': 10}))
            players.append(actor)
            by_carrier[carrier] = actor
    package = dict(players=players, clubs=clubs)
    request = dict(schema=subject.INPUT_SCHEMA, season='2000-01', release_id='fixture-release', evidence=evidence,
        moves=[dict(source=112, destination=212, from_club=1, to_club=2, evidence=['fixture']),
               dict(source=212, destination=112, from_club=2, to_club=1, evidence=['fixture'])],
        retirements=[], new_people=[],
        orders=[dict(match='fixture', club_carrier_id=10, full_order=list(range(101, 113)), bench_mapping=[])])
    base = SimpleNamespace(season='2000-01', release_id='fixture-release',
        package_path=tmp_path / 'package.json', game_path=game)
    monkeypatch.setattr(subject.pipeline, 'read_json_file',
        lambda path: request if Path(path) == input_path else package)
    monkeypatch.setattr(subject.registry, 'sha256_file', lambda _path: 'a' * 64)
    monkeypatch.setattr(subject, 'binding', lambda _path: dict(path='request.json', sha256='a' * 64))
    monkeypatch.setattr(subject, 'original', lambda _value: evidence_path)
    monkeypatch.setattr(subject, 'source_text', lambda _value: 'exact reviewed report')
    monkeypatch.setattr(subject, 'dated_source', lambda _value: None)
    monkeypatch.setattr(subject, 'verify_match_club', lambda *_args: None)
    monkeypatch.setattr(subject, 'skills', lambda _jug, carrier: by_carrier[carrier]['ratings']['values'])
    monkeypatch.setattr(ownership, 'native_owners', lambda _eq: {112: {10}, 212: {20}})

    def native(_jug, carrier):
        row = by_carrier[carrier]
        return dict(startup_order=carrier % 100, birth_date=row['facts']['birth_date'], name=row['name'])

    monkeypatch.setattr(subject.facts, 'native_facts', native)
    monkeypatch.setattr(subject, 'match_people', lambda _fixture: pytest.fail(
        'played substitutes must be rejected before treating them as an ordered complete bench'))

    with pytest.raises(ValueError, match='not a complete published bench'):
        subject.prepare(base, input_path)
