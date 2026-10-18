from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import season_dated_reserve_membership_v1 as subject


SELECTOR = {
    'club_name': 'Internazionale',
    'competition_catalog': 'seriea',
    'country_catalog': 'italy',
}
ALIASES_PATH = 'seasons/2000-01/opening-lineup-club-identity-aliases-v1.json'
TM_URL = 'https://www.transfermarkt.co.uk/inter-milan/kader/verein/46/saison_id/2000/plus/1'
DFB_URL = 'https://datencenter.dfb.de/europa-league/2000-2001/mannschaft/inter-mailand'
NATIVE_CLUB = {
    'name': 'Internazionale', 'full_name': 'Internazionale',
    'division': 'preserve-existing-mode1-membership', 'carrier_id': 225,
}


def _write(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _entry_page(*, joined='01/07/2000', from_id=1307, provider_id=21231,
                name='Corrado Colombo', birthday='03/08/1979',
                canonical_club=46, season=2000, signed_from=True):
    signed = (f'<a title="AC Pistoiese" href="/us-pistoiese-1921/startseite/verein/{from_id}/saison_id/2000">'
              '<img alt="AC Pistoiese" src="pistoiese.png"></a>'
              if signed_from else '')
    return f'''<!doctype html><html><head>
      <link rel="canonical" href="https://www.transfermarkt.co.uk/inter-milan/kader/verein/{canonical_club}/saison_id/{season}/plus/1">
      <title>Inter Milan - Detailed squad 00/01 | Transfermarkt</title></head><body>
      <h1>Inter Milan - Detailed squad 00/01</h1>
      <table class="items"><thead><tr><th>#</th><th>Player</th><th>Date of birth/Age</th>
      <th>Nat.</th><th>Current club</th><th>Height</th><th>Foot</th><th>Joined</th>
      <th>Signed from</th></tr></thead><tbody><tr><td>27</td>
      <td><a href="/corrado-colombo/profil/spieler/{provider_id}">{name}</a></td>
      <td>{birthday} (21)</td><td>Italy</td><td>Retired</td><td>1.88m</td><td>right</td>
      <td>{joined}</td><td>{signed}</td></tr></tbody></table></body></html>'''.encode()


def _exit_page(*, leave='02.10.2000', name='Corrado Colombo', birthday='03.08.1979',
               club='Inter Mailand', heading='Kader Europa League 2000/2001'):
    return f'''<!doctype html><html><head><title>Inter Mailand, Europa League 2000/01</title></head><body>
      <h2>{club}</h2><h3>{heading}</h3>
      <table><tbody><tr class="c-Table-body-row"><td>27</td>
      <td>{name} <small>(bis {leave})</small></td><td>{birthday}</td>
      </tr></tbody></table></body></html>'''.encode()


@pytest.fixture
def evidence_case(tmp_path, monkeypatch):
    monkeypatch.setattr(subject.registry, 'ROOT', tmp_path)
    monkeypatch.setattr(
        subject.registry, 'relative_workspace_path',
        lambda path: Path(path).resolve().relative_to(tmp_path.resolve()).as_posix(),
    )
    entry_path = tmp_path / 'entry.html'
    exit_path = tmp_path / 'exit.html'
    aliases_path = tmp_path / ALIASES_PATH
    entry_hash = _write(entry_path, _entry_page())
    exit_hash = _write(exit_path, _exit_page())
    aliases_doc = {
        'schema_version': 'pm99-transfermarkt-opening-lineup-club-identity-aliases-v1',
        'aliases': [{'source_selector': SELECTOR, 'transfermarkt_club_id': 46}],
    }
    aliases_bytes = json.dumps(aliases_doc, sort_keys=True, separators=(',', ':')).encode()
    aliases_hash = _write(aliases_path, aliases_bytes)
    selection = {
        'name': 'Corrado Colombo',
        'birth_date': '1979-08-03',
        'provider_player_id': 21231,
        'opening_contract': {
            'policy': subject.POLICY,
            'opening_date': '2000-08-23',
            'provider_club_id': 46,
            'source_selector': deepcopy(SELECTOR),
            'entry': 'entry',
            'exit': 'exit',
            'club_identity_aliases': 'aliases',
        },
    }
    evidence = {
        'entry': {
            'path': 'entry.html', 'sha256': entry_hash, 'url': TM_URL,
            'anchors': ['Corrado Colombo', '01/07/2000'],
            'date_anchor': '01/07/2000', 'event_date': '2000-07-01',
            'person_row': {
                'provider_player_id': 21231, 'date_column': 'Joined',
                'date_literal': '01/07/2000', 'from_club_id': 1307,
            },
        },
        'exit': {
            'path': 'exit.html', 'sha256': exit_hash, 'url': DFB_URL,
            'anchors': ['Inter Mailand', 'Kader Europa League 2000/2001',
                        'Corrado Colombo', '02.10.2000', '03.08.1979'],
            'date_anchor': '02.10.2000', 'event_date': '2000-10-02',
            'dfb_registration_row': {
                'season_start_year': 2000, 'roster_heading': 'Kader Europa League 2000/2001',
                'club_heading': 'Inter Mailand', 'full_name': 'Corrado Colombo',
                'birthday_literal': '03.08.1979', 'date_kind': 'bis',
            },
        },
        'aliases': {'path': ALIASES_PATH, 'sha256': aliases_hash},
    }
    return selection, evidence, entry_path, exit_path, aliases_path


def test_positive_dated_entry_and_registration_exit_prove_august_not_matchday(evidence_case):
    selection, evidence, *_ = evidence_case
    assert subject.verify(selection, evidence, season='2000-01',
                          club=NATIVE_CLUB) == '2000-08-23'


@pytest.mark.parametrize(('entry_date', 'exit_date'), [
    ('25/08/2000', '02.10.2000'),
    ('01/07/2000', '31.07.2000'),
])
def test_interval_must_cover_target_august_date(evidence_case, entry_date, exit_date):
    selection, evidence, entry_path, exit_path, _ = evidence_case
    entry_bytes = _entry_page(joined=entry_date)
    exit_bytes = _exit_page(leave=exit_date)
    evidence['entry'].update(sha256=_write(entry_path, entry_bytes), date_anchor=entry_date,
                             event_date='2000-' + ('08-25' if entry_date.startswith('25') else '07-01'),
                             anchors=['Corrado Colombo', entry_date],
                             person_row={**evidence['entry']['person_row'], 'date_literal': entry_date})
    parsed_exit = '2000-10-02' if exit_date.startswith('02') else '2000-07-31'
    evidence['exit'].update(sha256=_write(exit_path, exit_bytes), date_anchor=exit_date,
                            event_date=parsed_exit,
                            anchors=['Inter Mailand', 'Kader Europa League 2000/2001',
                                     'Corrado Colombo', exit_date, '03.08.1979'])
    with pytest.raises(ValueError, match='bracket'):
        subject.verify(selection, evidence, season='2000-01',
                       club=NATIVE_CLUB)


@pytest.mark.parametrize('fault', [
    'wrong_native_club', 'wrong_provider_id', 'wrong_name', 'wrong_dob',
    'wrong_alias_path', 'wrong_alias_hash', 'wrong_entry_source_year',
    'wrong_target_season', 'wrong_alias_mapping', 'wrong_exit_url_year',
    'wrong_entry_canonical_club', 'wrong_joined_person', 'wrong_from_club',
    'missing_signed_from', 'wrong_exit_date_kind', 'wrong_exit_header',
    'wrong_exit_person', 'wrong_exit_dob', 'wrong_club_argument',
])
def test_guard_rejects_identity_origin_and_source_tampering(evidence_case, fault):
    selection, evidence, entry_path, exit_path, _ = evidence_case
    selection = deepcopy(selection)
    evidence = deepcopy(evidence)
    if fault == 'wrong_native_club':
        selection['opening_contract']['source_selector']['club_name'] = 'AC Milan'
    elif fault == 'wrong_provider_id':
        selection['provider_player_id'] = 21232
    elif fault == 'wrong_name':
        selection['name'] = 'Corrado Colombo Jr'
    elif fault == 'wrong_dob':
        selection['birth_date'] = '1979-08-04'
    elif fault == 'wrong_alias_path':
        evidence['aliases']['path'] = 'seasons/2001-02/opening-lineup-club-identity-aliases-v1.json'
    elif fault == 'wrong_alias_hash':
        evidence['aliases']['sha256'] = '0' * 64
    elif fault == 'wrong_entry_source_year':
        evidence['entry']['url'] = evidence['entry']['url'].replace('saison_id/2000', 'saison_id/2001')
    elif fault == 'wrong_target_season':
        with pytest.raises(ValueError):
            subject.verify(selection, evidence, season='2001-02', club=NATIVE_CLUB)
        return
    elif fault == 'wrong_alias_mapping':
        alias_file = evidence_case[-1]
        wrong_doc = {
            'schema_version': 'pm99-transfermarkt-opening-lineup-club-identity-aliases-v1',
            'aliases': [{'source_selector': deepcopy(SELECTOR), 'transfermarkt_club_id': 47}],
        }
        evidence['aliases']['sha256'] = _write(
            alias_file, json.dumps(wrong_doc, sort_keys=True, separators=(',', ':')).encode())
    elif fault == 'wrong_exit_url_year':
        evidence['exit']['url'] = evidence['exit']['url'].replace('2000-2001', '2001-2002')
    elif fault == 'wrong_entry_canonical_club':
        entry_path.write_bytes(_entry_page(canonical_club=47))
        evidence['entry']['sha256'] = hashlib.sha256(entry_path.read_bytes()).hexdigest()
    elif fault == 'wrong_joined_person':
        entry_path.write_bytes(_entry_page(provider_id=21232))
        evidence['entry']['sha256'] = hashlib.sha256(entry_path.read_bytes()).hexdigest()
    elif fault == 'wrong_from_club':
        evidence['entry']['person_row']['from_club_id'] = 46
    elif fault == 'missing_signed_from':
        entry_path.write_bytes(_entry_page(signed_from=False))
        evidence['entry']['sha256'] = hashlib.sha256(entry_path.read_bytes()).hexdigest()
    elif fault == 'wrong_exit_date_kind':
        evidence['exit']['dfb_registration_row']['date_kind'] = 'ab'
    elif fault == 'wrong_exit_header':
        evidence['exit']['dfb_registration_row']['roster_heading'] = 'Kader Bundesliga 2000/2001'
    elif fault == 'wrong_exit_person':
        evidence['exit']['dfb_registration_row']['full_name'] = 'Someone Else'
    elif fault == 'wrong_exit_dob':
        evidence['exit']['dfb_registration_row']['birthday_literal'] = '04.08.1979'
    with pytest.raises(ValueError):
        subject.verify(selection, evidence, season='2000-01',
                       club=({**NATIVE_CLUB, 'name': 'AC Milan', 'full_name': 'AC Milan'}
                             if fault == 'wrong_club_argument' else NATIVE_CLUB))


def test_actual_colombo_joined_row_and_dfb_exit_bracket_are_source_bound():
    root = Path(__file__).resolve().parents[1]
    entry_path = root / '.local/consolidated-audit-20261009/Gresko2000-Inter-opening-review-v1/source/transfermarkt-inter-squad-2000-01.html'
    exit_path = root / '.local/consolidated-audit-20261009/Gresko2000-Inter-opening-review-v1/source/dfb-inter-europa-league-2000-01.html'
    aliases_path = root / ALIASES_PATH
    if not all(path.is_file() for path in (entry_path, exit_path, aliases_path)):
        pytest.skip('retained original Colombo Inter ownership sources unavailable')
    selection = {
        'name': 'Corrado Colombo', 'birth_date': '1979-08-03', 'provider_player_id': 21231,
        'opening_contract': {
            'policy': subject.POLICY, 'opening_date': '2000-08-23',
            'provider_club_id': 46, 'source_selector': deepcopy(SELECTOR),
            'entry': 'entry', 'exit': 'exit', 'club_identity_aliases': 'aliases',
        },
    }
    evidence = {
        'entry': {
            'path': str(entry_path.relative_to(root)),
            'sha256': hashlib.sha256(entry_path.read_bytes()).hexdigest(),
            'url': TM_URL, 'anchors': ['Corrado Colombo', '01/07/2000'],
            'date_anchor': '01/07/2000', 'event_date': '2000-07-01',
            'person_row': {
                'provider_player_id': 21231, 'date_column': 'Joined',
                'date_literal': '01/07/2000', 'from_club_id': 1307,
            },
        },
        'exit': {
            'path': str(exit_path.relative_to(root)),
            'sha256': hashlib.sha256(exit_path.read_bytes()).hexdigest(),
            'url': DFB_URL,
            'anchors': ['Inter Mailand', 'Kader Europa League 2000/2001',
                        'Corrado Colombo', '02.10.2000', '03.08.1979'],
            'date_anchor': '02.10.2000', 'event_date': '2000-10-02',
            'dfb_registration_row': {
                'season_start_year': 2000, 'roster_heading': 'Kader Europa League 2000/2001',
                'club_heading': 'Inter Mailand', 'full_name': 'Corrado Colombo',
                'birthday_literal': '03.08.1979', 'date_kind': 'bis',
            },
        },
        'aliases': {
            'path': ALIASES_PATH,
            'sha256': hashlib.sha256(aliases_path.read_bytes()).hexdigest(),
        },
    }
    assert subject.verify(selection, evidence, season='2000-01', club=NATIVE_CLUB) == '2000-08-23'


def test_prepared_colombo_request_reparses_identity_and_bracket_without_bench_claim():
    root = Path(__file__).resolve().parents[1]
    path = root / '.local/consolidated-audit-20261009/Gresko2000-Inter-opening-review-v1/gresko-colombo-request-v1.json'
    if not path.is_file():
        pytest.skip('prepared original Colombo request unavailable')
    request = json.loads(path.read_text())
    assert request['season'] == '2000-01'
    assert len(request['new_people']) == 1
    row = request['new_people'][0]
    assert row['provider_player_id'] == 21231
    assert subject.exchange.new_person(row, request['evidence'])['membership'] == \
        'dated-opening-contract-bracket-not-matchday-claim'
