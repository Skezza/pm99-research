"""Admit a positive2002 Shinnik actor; never call a native starter a reserve.

The source provider lists a complete target-year registration row attributed
to RFPL. Independently compare birthday with the original biography, require a
positive interior-year playing spell and original numerical dated appearance.
The actual wrong Shinnik actor occupies startup8, so eventual repair MUST use
an explicitly authorised starting-player transaction, not the bench-only path.
"""
from datetime import UTC, datetime
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_wikipedia_career_identity_v1 as wiki
from scripts import season_within_club_reserve_repair_v1 as native
from scripts.prepare_stoke_alias_identity_evidence_20261016 import original
from scripts.audit_shtanyuk_runtime_aliases_20261016 import ROOT
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

BIO = 'https://en.wikipedia.org/wiki/Dmitri_Khomukha'
SQUAD = 'https://100bombardirov.ru/ru/2002/squad/shn.htm'
FIXTURE = 'https://www.transfermarkt.co.uk/spartak-moscow_shinnik-yaroslavl/index/spielbericht/2833981'


def registration(page):
    headings = [h.get_text(' ',strip=True) for h in page.find_all('h1')]
    if len(headings) != 1 or 'Шинник' not in headings[0] or not headings[0].endswith('2002'):
        raise ValueError('one explicit original Shinnik2002 registration heading required')
    rows = []
    for table in page.find_all('table'):
        section = None
        for tr in table.find_all('tr'):
            text = tr.get_text(' ',strip=True)
            if text in ('Вратари', 'Защитники', 'Полузащитники', 'Нападающие'):
                section = text
            cells = tr.find_all('td',recursive=False)
            links = [a for a in tr.find_all('a',href=True) if a['href'] == '../../player/h/1285.htm']
            if not links:
                continue
            if (len(links) != 1 or len(cells) != 13 or section != 'Полузащитники'
                    or links[0].get_text(' ',strip=True) != 'Дмитрий Хомуха'):
                raise ValueError('registered actor has ambiguous identity/position/columns')
            countries = [i.get('alt') for i in cells[2].find_all('img')]
            if countries != ['Туркмения'] or cells[0].get_text(strip=True) != '7':
                raise ValueError('original literal nationality or shirt label changed')
            if cells[9].get_text(strip=True) or cells[10].get_text(strip=True):
                raise ValueError('midseason registration changes require separate dated admission')
            rows.append(dict(name='Dmitri Khomukha', published_Cyrillic_name=links[0].get_text(' ',strip=True),
                source_person_id='100bombardirov:1285', birth_date=datetime.strptime(cells[3].get_text(strip=True),'%d.%m.%Y').date().isoformat(),
                nationality='TKM', position='M', height_cm=int(cells[4].get_text(strip=True)),
                weight_kg=int(cells[5].get_text(strip=True)), shirt_number=7,
                first_registered_year=int(cells[11].get_text(strip=True)), unresolved_fields=[]))
    if len(rows) != 1:
        raise ValueError('one explicit numeric Shinnik2002 registration row required')
    return rows[0]


def prepare():
    folder = ROOT / 'Shinnik2002-originals'
    _, bio = original(folder, 'khomukha-biography', BIO)
    page, squad = original(folder, 'Shinnik2002-registered-squad', SQUAD)
    _, fixture_binding = original(folder, 'Shinnik2002-opening-report', FIXTURE)
    person, owner = wiki.read((registry.ROOT/bio['path']).read_bytes(), 'Dmitri_Khomukha', BIO,
        '2002-08-01', 'Shinnik Yaroslavl', 'russia', expected_name='Dmitri Khomukha')
    facts = registration(page)
    fixture = opening.match_team((registry.ROOT/fixture_binding['path']).read_bytes(), 2374, '2002-03-12')
    if (facts['birth_date'] != person['birth_date'] or facts['birth_date'] != '1969-08-23'
            or facts['first_registered_year'] != 2001
            or fixture['starting_xi'].get('24143') != 'Dmitriy Khomukha'):
        raise ValueError('registration, biography or dated numerical appearance disagrees')
    base = registry.load_registered_release('2002-03','sourced-remaining-manager-tenures-20261016-r116a')
    package = pipeline.read_json_file(base.package_path)
    if any(roster.normalise(p.get('source_name') or p['name']) in ('dmitrikhomukha','dmitriykhomukha')
            for p in package['players']):
        raise ValueError('positive actor already represented; cannot create another duplicate')
    data = (base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    wrong = native.native_facts(data,7972)
    if wrong != dict(name='Shtanyuk',birth_date='1900-01-01',position='D',startup_order=8):
        raise ValueError('wrong-owner preimage changed; inspect before source admission')
    return dict(schema='pm99-Shinnik2002-positive-Khomukha-actor-v1',
        originals=[bio,squad,fixture_binding], source_player=facts, source_person=person, owner_evidence=owner,
        positive_early_season_appearance=fixture, earliest_fixture_claimed=False,
        source_fixture_round=2, Cyrillic_and_Latin_identity_bridge=dict(
            published_names=['Дмитрий Хомуха','Dmitri Khomukha','Dmitriy Khomukha'], birthday_agrees=True),
        native_wrong_owner=dict(carrier_id=7972,club_carrier_id=757,fields=wrong),
        bench_only_transaction_allowed=False, selected_starter_change_requires_explicit_policy=True,
        season=base.season, release_id=base.release_id, manifest_sha256=base.manifest_sha256,
        package_sha256=registry.sha256_file(base.package_path), native_writes=0, recipe_writes=0, cases_closed=0,
        source_credit='100 бомбардиров: historical squad details attributed by that page to RFPL; Wikipedia biography; original Transfermarkt dated appearance.',
        machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4')


def main():
    path=ROOT/'Shinnik2002-positive-Khomukha-admission.json'
    if path.exists():
        raise ValueError('completed original actor admission must not repeat')
    retained(path,dict(utc=datetime.now(UTC).isoformat(),**prepare()))
    print(dict(positive2002_actor='Dmitri Khomukha',native_wrong_actor_is_starter=True,
        bench_only_repair_refused=True,native_writes=0,cases_closed=0),flush=True)


if __name__=='__main__':
    main()
