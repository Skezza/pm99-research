from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scripts import season_dated_reserve_membership_v1 as subject
from scripts import season_opening_identity_exchange_v1 as exchange


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / '.local/consolidated-audit-20261009/Goram2000-opening-review-v1'
INDEX_PATH = AUDIT / 'source-evidence-index-v2.json'
SOURCE_KEYS = (
    'greening_aug16_match',
    'greening_tm_squad_2000_01',
    'greening_tm_profile',
)
MANCHESTER_UNITED = {'name': 'Manchester United', 'full_name': 'Manchester United'}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def greening_case(tmp_path, monkeypatch):
    if not INDEX_PATH.is_file():
        pytest.skip('retained Goram source-evidence-index-v2 unavailable')
    index = json.loads(INDEX_PATH.read_text(encoding='utf-8'))
    assert index['schema_version'] == 'pm99-goram-opening-source-evidence-index-v2'
    assert index['season'] == '2000-01'
    evidence = {}
    paths = {}
    for key in SOURCE_KEYS:
        record = index['sources'][key]
        source_path = AUDIT / 'source-cache-v1' / record['relative_path']
        raw = source_path.read_bytes()
        assert _sha(raw) == record['sha256']
        target = tmp_path / 'retained' / (key + '.html')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        relative = target.relative_to(tmp_path).as_posix()
        paths[key] = target
        evidence[key] = {
            'path': relative,
            'sha256': record['sha256'],
            'url': record['url'],
        }
    fixture_page = BeautifulSoup(paths['greening_aug16_match'].read_bytes(), 'lxml')
    aria = fixture_page.select_one('time.sdc-site-match-header__detail-time')['aria-label']
    stamp = re.search(r'\b(\d{1,2})(?:st|nd|rd|th) ([A-Za-z]+) (\d{4})\b', aria)
    assert stamp is not None
    parsed_date = datetime.strptime(' '.join(stamp.groups()), '%d %B %Y').date().isoformat()
    assert parsed_date == '2000-08-16'
    evidence['greening_aug16_match']['date'] = parsed_date

    monkeypatch.setattr(subject.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(
        subject.registry, 'relative_workspace_path',
        lambda path: Path(path).resolve().relative_to(tmp_path.resolve()).as_posix(),
    )
    selection = {
        'name': 'Jonathan Greening',
        'birth_date': '1979-01-02',
        'provider_player_id': 3865,
        'profile': 'greening_tm_profile',
        'position': 'M',
        'fine_roles': [9],
        'profile_position': 'Central Midfield',
        'nationality': 'ENG',
        'nationality_label': 'England',
        'opening_contract': {
            'policy': subject.SKY_POLICY,
            'opening_date': '2000-08-16',
            'fixture': 'greening_aug16_match',
            'season_roster': 'greening_tm_squad_2000_01',
            'club_name': 'Manchester United',
            'provider_club_id': 985,
        },
    }
    return selection, evidence, paths


def _rewrite(case, key, transform):
    _selection, evidence, paths = case
    page = BeautifulSoup(paths[key].read_bytes(), 'lxml')
    transform(page)
    raw = str(page).encode('utf-8')
    paths[key].write_bytes(raw)
    evidence[key]['sha256'] = _sha(raw)
    return page


def _greening_row(page):
    return next(
        row for row in page.select('.sdc-site-team-lineup__col dd.sdc-site-team-lineup__player-name')
        if row.select_one('.sdc-site-team-lineup__player-initial').get('title') == 'Jonathan'
        and row.select_one('.sdc-site-team-lineup__player-surname').get_text(' ', strip=True) == 'Greening'
    )


def _assert_rejected(case, *, season='2000-01', club=MANCHESTER_UNITED):
    selection, evidence, _paths = case
    with pytest.raises(ValueError):
        subject.verify(selection, evidence, season=season, club=club)


def _synthetic_case(tmp_path, monkeypatch):
    """Small parser fixture; synthetic and explicitly not source evidence."""
    sky_url = 'https://www.skysports.com/football/manchester-united-vs-city/teams/12345'
    annual_url = 'https://www.transfermarkt.co.uk/manchester-united/kader/verein/985/saison_id/2000'
    sky = f'''<!doctype html><html><head><link rel="canonical" href="{sky_url}"></head><body>
      <time class="sdc-site-match-header__detail-time" aria-label="3:00pm, Wednesday 16th August 2000"></time>
      <div class="sdc-site-match-header__team-name-block">Manchester United</div>
      <div class="sdc-site-match-header__team-name-block">Manchester City</div>
      <div class="sdc-site-team-lineup__col">
        <div class="sdc-site-team-lineup__header--main"><img class="sdc-site-team-lineup__team-badge" alt="Manchester United"></div>
        <dl class="sdc-site-team-lineup__players--subs"><dd class="sdc-site-team-lineup__player-name">
          <span class="sdc-site-team-lineup__player-initial" title="Testgiven">T.</span>
          <span class="sdc-site-team-lineup__player-surname">Sample</span>
        </dd></dl>
      </div>
      <div class="sdc-site-team-lineup__col">
        <div class="sdc-site-team-lineup__header--main"><img class="sdc-site-team-lineup__team-badge" alt="Manchester City"></div>
        <dl class="sdc-site-team-lineup__players--subs"></dl>
      </div></body></html>'''.encode()
    annual = f'''<!doctype html><html><head><link rel="canonical" href="https://www.transfermarkt.co.uk/manchester-united/kader/verein/985"></head>
      <title>Manchester United - Detailed squad 00/01 | Transfermarkt</title><body>
      <select name="saison_id"><option value="2000" selected>00/01</option></select>
      <table class="items"><tbody><tr><td><a href="/testgiven-sample/profil/spieler/7654">Testgiven Sample</a></td></tr></tbody></table>
      </body></html>'''.encode()
    sources = {
        'fixture': ('sky.html', sky, sky_url, '2000-08-16'),
        'annual': ('annual.html', annual, annual_url, None),
    }
    evidence, paths = {}, {}
    for key, (filename, raw, url, stamp) in sources.items():
        path = tmp_path / filename
        path.write_bytes(raw)
        paths[key] = path
        evidence[key] = {'path': filename, 'sha256': _sha(raw), 'url': url}
        if stamp:
            evidence[key]['date'] = stamp
    monkeypatch.setattr(subject.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(subject.registry, 'relative_workspace_path',
                        lambda path: Path(path).resolve().relative_to(tmp_path.resolve()).as_posix())
    selection = {
        'name': 'Testgiven Sample', 'provider_player_id': 7654,
        'opening_contract': {
            'policy': subject.SKY_POLICY, 'opening_date': '2000-08-16',
            'fixture': 'fixture', 'season_roster': 'annual',
            'club_name': 'Manchester United', 'provider_club_id': 985,
        },
    }
    return selection, evidence, paths


def test_synthetic_parser_fixture_positive_and_explicitly_not_retained_evidence(tmp_path, monkeypatch):
    selection, evidence, paths = _synthetic_case(tmp_path, monkeypatch)
    assert subject.verify(selection, evidence, season='2000-01', club=MANCHESTER_UNITED) == '2000-08-16'
    assert _sha(paths['fixture'].read_bytes()) == evidence['fixture']['sha256']


def test_sky_starting_xi_policy_does_not_claim_bench_or_change_old_policy(tmp_path, monkeypatch):
    case = _synthetic_case(tmp_path, monkeypatch)
    selection, evidence, _paths = case
    selection['opening_contract']['policy'] = subject.SKY_XI_POLICY
    with pytest.raises(ValueError, match='starting XI'):
        subject.verify(selection, evidence, season='2000-01', club=MANCHESTER_UNITED)
    _rewrite(case, 'fixture', lambda page: page.select_one(
        '.sdc-site-team-lineup__players--subs').__setitem__(
            'class', ['sdc-site-team-lineup__players']))
    assert subject.verify(selection, evidence, season='2000-01', club=MANCHESTER_UNITED) == '2000-08-16'
    selection['opening_contract']['policy'] = subject.SKY_POLICY
    with pytest.raises(ValueError, match='bench'):
        subject.verify(selection, evidence, season='2000-01', club=MANCHESTER_UNITED)


@pytest.mark.parametrize('fault', ['duplicate', 'opponent', 'wrong_date'])
def test_sky_starting_xi_policy_retains_exact_person_club_date_guards(tmp_path, monkeypatch, fault):
    case = _synthetic_case(tmp_path, monkeypatch)
    selection, evidence, paths = case
    selection['opening_contract']['policy'] = subject.SKY_XI_POLICY
    def transform(page):
        dl = page.select_one('.sdc-site-team-lineup__players--subs')
        dl['class'] = ['sdc-site-team-lineup__players']
        if fault == 'duplicate':
            dl.append(copy.deepcopy(dl.select_one('dd')))
        elif fault == 'opponent':
            page.select('.sdc-site-team-lineup__col')[1].append(dl.extract())
    _rewrite(case, 'fixture', transform)
    if fault == 'wrong_date':
        evidence['fixture']['date'] = '2000-09-16'
    with pytest.raises(ValueError):
        subject.verify(selection, evidence, season='2000-01', club=MANCHESTER_UNITED)


@pytest.mark.parametrize('fault', ['foreign_link', 'conflicting_same_id_name'])
def test_sky_annual_identity_rejects_foreign_origin_and_conflicting_name(tmp_path, monkeypatch, fault):
    case = _synthetic_case(tmp_path, monkeypatch)
    selection, evidence, _paths = case
    def transform(page):
        link = page.select_one('table.items a')
        if fault == 'foreign_link':
            link['href'] = 'https://attacker.invalid/testgiven-sample/profil/spieler/7654'
        else:
            conflicting = copy.deepcopy(link)
            conflicting.string = 'Different Person'
            link.parent.append(conflicting)
    _rewrite(case, 'annual', transform)
    with pytest.raises(ValueError):
        subject.verify(selection, evidence, season='2000-01', club=MANCHESTER_UNITED)


@pytest.mark.parametrize('fault', [
    'wrong_date_metadata', 'wrong_date_body', 'wrong_club_header',
    'wrong_squad_year', 'wrong_squad_id', 'wrong_squad_full_name',
])
def test_synthetic_parser_fixture_rejects_date_club_and_annual_identity(tmp_path, monkeypatch, fault):
    selection, evidence, paths = _synthetic_case(tmp_path, monkeypatch)
    if fault == 'wrong_date_metadata':
        evidence['fixture']['date'] = '2000-08-17'
    elif fault == 'wrong_date_body':
        raw = paths['fixture'].read_bytes().replace(b'16th August 2000', b'17th August 2000')
        paths['fixture'].write_bytes(raw)
        evidence['fixture']['sha256'] = _sha(raw)
    elif fault == 'wrong_club_header':
        raw = paths['fixture'].read_bytes().replace(b'>Manchester United</div>', b'>United XI</div>', 1)
        paths['fixture'].write_bytes(raw)
        evidence['fixture']['sha256'] = _sha(raw)
    elif fault == 'wrong_squad_year':
        evidence['annual']['url'] = evidence['annual']['url'].replace('saison_id/2000', 'saison_id/2001')
    elif fault == 'wrong_squad_id':
        raw = paths['annual'].read_bytes().replace(b'/spieler/7654', b'/spieler/76540')
        paths['annual'].write_bytes(raw)
        evidence['annual']['sha256'] = _sha(raw)
    elif fault == 'wrong_squad_full_name':
        raw = paths['annual'].read_bytes().replace(b'Testgiven Sample', b'Testgiven Other')
        paths['annual'].write_bytes(raw)
        evidence['annual']['sha256'] = _sha(raw)
    with pytest.raises(ValueError):
        subject.verify(selection, evidence, season='2000-01', club=MANCHESTER_UNITED)


def test_retained_greening_august_bench_and_dispatcher_are_source_bound(greening_case):
    selection, evidence, _paths = greening_case

    assert subject.verify(
        selection, evidence, season='2000-01', club=MANCHESTER_UNITED,
    ) == '2000-08-16'
    admitted = exchange.new_person(selection, evidence)
    assert admitted['source_person'] == {
        'name': 'Jonathan Greening',
        'birth_date': '1979-01-02',
        'source_player_id': 3865,
        'source_provider': 'transfermarkt',
        'source_profile_url': evidence['greening_tm_profile']['url'],
    }
    assert admitted['membership'] == 'original-published-August-Sky-bench-not-played-appearance-claim'


@pytest.mark.parametrize('fault', [
    'wrong_season', 'wrong_date_metadata', 'wrong_date_in_original', 'wrong_host',
    'wrong_canonical', 'opponent_only', 'sidebar_only', 'initials_only', 'duplicate_player',
    'not_bench', 'wrong_target_header', 'wrong_team_badge', 'id_prefix',
    'wrong_annual_url_year', 'wrong_annual_page_year', 'wrong_annual_full_name',
    'wrong_annual_selected_year', 'missing_annual_selected_year', 'wrong_native_club',
])
def test_sky_guard_rejects_wrong_date_club_or_numeric_identity(greening_case, fault):
    selection, evidence, _paths = greening_case
    selection = copy.deepcopy(selection)
    evidence = copy.deepcopy(evidence)

    if fault == 'wrong_season':
        _assert_rejected((selection, evidence, greening_case[2]), season='2001-02')
        return
    if fault == 'wrong_date_metadata':
        evidence['greening_aug16_match']['date'] = '2000-08-17'
    elif fault == 'wrong_date_in_original':
        _rewrite(greening_case, 'greening_aug16_match', lambda page: page.select_one(
            'time.sdc-site-match-header__detail-time').__setitem__(
                'aria-label', '8:00pm, Thursday 17th August 2000'))
        evidence['greening_aug16_match']['sha256'] = greening_case[1]['greening_aug16_match']['sha256']
    elif fault == 'wrong_host':
        evidence['greening_aug16_match']['url'] = evidence['greening_aug16_match']['url'].replace(
            'www.skysports.com', 'www.skysports.com.attacker.example')
    elif fault == 'wrong_canonical':
        _rewrite(greening_case, 'greening_aug16_match', lambda page: page.select_one(
            'link[rel="canonical"]').__setitem__(
                'href', 'https://www.skysports.com/football/another-match/teams/113616'))
        evidence['greening_aug16_match']['sha256'] = greening_case[1]['greening_aug16_match']['sha256']
    elif fault == 'opponent_only':
        selection['opening_contract']['club_name'] = 'Manchester City'
        _assert_rejected((selection, evidence, greening_case[2]),
                         club={'name': 'Manchester City', 'full_name': 'Manchester City'})
        return
    elif fault == 'sidebar_only':
        def sidebar(page):
            row = _greening_row(page)
            row.decompose()
            aside = page.new_tag('aside')
            aside.string = 'Jonathan Greening'
            page.body.append(aside)
        _rewrite(greening_case, 'greening_aug16_match', sidebar)
        evidence['greening_aug16_match']['sha256'] = greening_case[1]['greening_aug16_match']['sha256']
    elif fault == 'initials_only':
        def initials(page):
            initial = _greening_row(page).select_one('.sdc-site-team-lineup__player-initial')
            initial['title'] = 'J.'
        _rewrite(greening_case, 'greening_aug16_match', initials)
        evidence['greening_aug16_match']['sha256'] = greening_case[1]['greening_aug16_match']['sha256']
    elif fault == 'duplicate_player':
        def duplicate(page):
            row = _greening_row(page)
            page.select_one('.sdc-site-team-lineup__players--subs').append(copy.deepcopy(row))
        _rewrite(greening_case, 'greening_aug16_match', duplicate)
        evidence['greening_aug16_match']['sha256'] = greening_case[1]['greening_aug16_match']['sha256']
    elif fault == 'not_bench':
        def starter_only(page):
            row = _greening_row(page)
            row.extract()
            columns = page.select('.sdc-site-team-lineup__col')
            target = next(c for c in columns if c.select_one(
                '.sdc-site-team-lineup__header--main img.sdc-site-team-lineup__team-badge'
            ).get('alt') == 'Manchester United')
            target.select_one('.sdc-site-team-lineup__players:not(.sdc-site-team-lineup__players--subs)').append(row)
        _rewrite(greening_case, 'greening_aug16_match', starter_only)
        evidence['greening_aug16_match']['sha256'] = greening_case[1]['greening_aug16_match']['sha256']
    elif fault == 'wrong_target_header':
        def wrong_header(page):
            next(h for h in page.select('.sdc-site-match-header__team-name-block')
                 if h.get_text(' ', strip=True) == 'Manchester United').string = 'Manchester City'
        _rewrite(greening_case, 'greening_aug16_match', wrong_header)
        evidence['greening_aug16_match']['sha256'] = greening_case[1]['greening_aug16_match']['sha256']
    elif fault == 'wrong_team_badge':
        def wrong_badge(page):
            badge = next(img for img in page.select(
                '.sdc-site-team-lineup__header--main img.sdc-site-team-lineup__team-badge')
                if img.get('alt') == 'Manchester United')
            badge['alt'] = 'Manchester City'
        _rewrite(greening_case, 'greening_aug16_match', wrong_badge)
        evidence['greening_aug16_match']['sha256'] = greening_case[1]['greening_aug16_match']['sha256']
    elif fault == 'id_prefix':
        def prefix_id(page):
            row = next(r for r in page.select('table.items > tbody > tr') if r.select_one(
                'a[href="/jonathan-greening/profil/spieler/3865"]'))
            row.select_one('a[href="/jonathan-greening/profil/spieler/3865"]')['href'] = \
                '/jonathan-greening/profil/spieler/38650'
        _rewrite(greening_case, 'greening_tm_squad_2000_01', prefix_id)
        evidence['greening_tm_squad_2000_01']['sha256'] = greening_case[1]['greening_tm_squad_2000_01']['sha256']
    elif fault == 'wrong_annual_url_year':
        evidence['greening_tm_squad_2000_01']['url'] = evidence['greening_tm_squad_2000_01']['url'].replace(
            'saison_id/2000', 'saison_id/2001')
    elif fault == 'wrong_annual_page_year':
        def annual_year(page):
            page.select_one('link[rel="canonical"]')['href'] = \
                'https://www.transfermarkt.co.uk/manchester-united/kader/verein/985/saison_id/2001'
            page.title.string = 'Manchester United - Detailed squad 01/02 | Transfermarkt'
        _rewrite(greening_case, 'greening_tm_squad_2000_01', annual_year)
        evidence['greening_tm_squad_2000_01']['sha256'] = greening_case[1]['greening_tm_squad_2000_01']['sha256']
    elif fault == 'wrong_annual_full_name':
        def annual_name(page):
            page.select_one('table.items > tbody > tr a[href="/jonathan-greening/profil/spieler/3865"]').string = 'Jonathan Green'
        _rewrite(greening_case, 'greening_tm_squad_2000_01', annual_name)
        evidence['greening_tm_squad_2000_01']['sha256'] = greening_case[1]['greening_tm_squad_2000_01']['sha256']
    elif fault == 'wrong_annual_selected_year':
        def selected_year(page):
            option = page.select_one('select[name="saison_id"] option[selected]')
            assert option is not None
            option['value'] = '2001'
        _rewrite(greening_case, 'greening_tm_squad_2000_01', selected_year)
        evidence['greening_tm_squad_2000_01']['sha256'] = greening_case[1]['greening_tm_squad_2000_01']['sha256']
    elif fault == 'missing_annual_selected_year':
        def no_selected_year(page):
            for option in page.select('select[name="saison_id"] option[selected]'):
                del option['selected']
        _rewrite(greening_case, 'greening_tm_squad_2000_01', no_selected_year)
        evidence['greening_tm_squad_2000_01']['sha256'] = greening_case[1]['greening_tm_squad_2000_01']['sha256']
    elif fault == 'wrong_native_club':
        _assert_rejected((selection, evidence, greening_case[2]),
                         club={'name': 'Manchester City', 'full_name': 'Manchester City'})
        return

    _assert_rejected((selection, evidence, greening_case[2]))
