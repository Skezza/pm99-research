"""Join original first14 plus two bracketed reserves; no native writes.

Calendar catalogues provide explicit person links and secondary facts only.
Four shortened/misspelled names require the linked original biography and an
exact birthday, not fuzzy matching or arbitrary initial expansion.
"""
import datetime as dt
import re

from bs4 import BeautifulSoup

from scripts import tachira_2015_original_opening_v1 as opening
from scripts import tachira_2015_original_linked_people_v1 as linked
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts.capture_source_bound_people_v1 import capture_ids
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_historical_transfer_review_v1 as transfer

ALIASES = {
    177: (140129, 'Alan Liebeskind'),
    194: (201413, 'José Miguel Reyes'),
    146: (295058, 'José Luis Marrufo'),
    288: (146516, 'Marcos Sánchez'),
}


def catalogue(key, year):
    _, raw, binding = source_rows(key)
    page = BeautifulSoup(raw, 'html.parser')
    if page.title is None or not page.title.get_text().startswith(f'Deportivo Táchira - Detailed squad {year} ('):
        raise ValueError('identity catalogue identifies another club/calendar year')
    result = {}
    for tr in page.select('table.items > tbody > tr'):
        links = {a.get('href'): a.get_text(' ',strip=True) for a in tr.select('a[href*="/profil/spieler/"]')}
        if not links:
            continue
        if len(links) != 1:
            raise ValueError('original identity row is ambiguous')
        href, name = next(iter(links.items()))
        match = re.search(r'/profil/spieler/(\d+)(?:/|$)', href)
        cells = tr.find_all('td', recursive=False)
        birthday = re.fullmatch(r'(\d{2})/(\d{2})/(\d{4}) \(\d+\)', cells[2].get_text(' ',strip=True)) if len(cells)==10 else None
        if match is None or birthday is None or int(match[1]) in result:
            raise ValueError('explicit original identity/DOB missing or duplicated')
        day, month, year = map(int, birthday.groups())
        result[int(match[1])] = dict(name=name, birth_date=dt.date(year,month,day).isoformat())
    return result, binding


def join():
    _, raw, match_binding = source_rows('tachira-2015-first-original-match11178-validated-v2')
    actual = opening.parse(raw)
    # The captured competition index independently identifies this first match.
    _, index_raw, index_binding = source_rows('tachira-2015-first-original-competition-index')
    index = BeautifulSoup(index_raw,'html.parser')
    cards=[c for c in index.select('.history-match-card')
        if c.select_one('a[href="../equipos/perfil.php?id=dta"]')]
    first=cards[0] if cards else None
    if (first is None or first.select_one('a[href="ficha.php?div=1&id=11178"]') is None
            or first.select_one('.international-match-date').get_text(strip=True)!='11 de Julio del 2015 - 7:00pm'
            or first.select_one('.international-match-competition').get_text(strip=True)!='Jornada 1'):
        raise ValueError('report is not the first original competition fixture for the target club')
    original, annual_binding = catalogue('tachira-2014', 2015)
    later, later_binding = catalogue('tachira-2015', 2016)
    catalogues = dict(original)
    for id, person in later.items():
        if id in catalogues and catalogues[id] != person:
            raise ValueError('adjacent catalogues conflict about original identity')
        catalogues[id] = person
    _, press_raw, press_binding = source_rows('tachira-2015-first-second-week-club-press')
    press = BeautifulSoup(press_raw,'html.parser').get_text(' ',strip=True)
    if ('18 citados por Daniel Farías' not in press or 'Fecha: Domingo 19/07/2015.' not in press
            or 'Prensa Deportivo Táchira' not in press or 'Estadio: Pueblo Nuevo, San Cristóbal' not in press):
        raise ValueError('original second-week attribution/date/manager/ground missing')
    bindings = [match_binding,index_binding,annual_binding,later_binding,press_binding]
    matched = []
    for row in actual['starting_xi']+actual['used_substitutes']:
        if row['source_person_id'] in ALIASES:
            id, canonical_name = ALIASES[row['source_person_id']]
            _, bio_raw, bio_binding = source_rows(f"tachira-2015-foro-linked-person{row['source_person_id']}-validated-v1")
            biography = linked.parse(bio_raw, f"https://www.forovinotinto.com/equipos/jugador.php?id={row['source_person_id']}")
            bindings.append(bio_binding)
            if id == 146516:
                _, profile_raw, profile_binding = source_rows('tachira-2015-marcos-original-full-profile')
                profile = BeautifulSoup(profile_raw,'html.parser')
                values = [n.get_text(' ',strip=True) for n in profile.select('.info-table__content--bold')]
                canonical = profile.select_one('link[rel="canonical"]')
                if (canonical is None or canonical.get('href') != 'https://www.transfermarkt.co.uk/marcos-sanchez/profil/spieler/146516'
                        or 'Marcos Aníbal Sánchez Mullins' not in values or '23/12/1989 (36)' not in values):
                    raise ValueError('original full Marcos identity differs')
                bindings.append(profile_binding)
                birth_date = '1989-12-23'
            else:
                person = catalogues[id]
                if person['name'] != canonical_name:
                    raise ValueError('explicit linked alias identifies another original person')
                birth_date = person['birth_date']
            if biography['birth_date'] != birth_date:
                raise ValueError('linked original biography and stable-ID birthday disagree')
            basis = 'explicit-linked-original-biography-and-exact-stable-ID-birthday'
        else:
            candidates = [(id,p) for id,p in catalogues.items() if roster.normalise(p['name'])==roster.normalise(row['published_name'])]
            if len(candidates)!=1:
                raise ValueError('original match name has no unique explicit catalogue identity')
            id, person = candidates[0]
            canonical_name, birth_date = person['name'],person['birth_date']
            basis = 'exact-normalised-published-match-name-and-original-catalogue-link'
        matched.append(dict(original_match_person=row, source_player_id=id, canonical_published_name=canonical_name,
            birth_date=birth_date, position=row['position'], membership='starting_xi' if len(matched)<11 else 'used-opening-match-substitute',
            identity_basis=basis))
    history_path = ROOT.parent/'tachira-2015-reserve-original-history-v1.json'
    events, review = histories.merge({},pipeline.read_json_file(history_path))
    bindings.append(dict(path=registry.relative_workspace_path(history_path),sha256=registry.sha256_file(history_path)))
    for id, role in [(308226,'G'),(271263,'M')]:
        bracket = transfer.transfer_interval(events[id],actual['fixture_date'])
        person = original[id]
        if (bracket.get('status')!='recorded-entry-and-exit-bracket-fixture' or bracket['source_owner_club_id']!=13297
                or person['name'] not in press):
            raise ValueError('reserve lacks both positive opening bracket and actual club-press corroboration')
        # Check the actual explicit-ID broad group, not a manually assumed role.
        for key in ('tachira-2014','tachira-2015'):
            annual = BeautifulSoup(source_rows(key)[1],'html.parser')
            rows = [tr for tr in annual.select('table.items > tbody > tr')
                if tr.select_one(f'a[href$="/profil/spieler/{id}"]')]
            group = rows[0].select_one('td.rueckennummer') if len(rows)==1 else None
            expected = {'G':'Goalkeeper','M':'Midfield'}[role]
            if group is None or group.get('title')!=expected:
                raise ValueError('reserve broad role not explicitly confirmed in both catalogues')
        matched.append(dict(source_player_id=id,canonical_published_name=person['name'],birth_date=person['birth_date'],
            position=role,membership='positive-bracketed-opening-reserve',bracket=bracket,
            identity_basis='explicit-original-catalogue-link-and-transfer-person-ID',
            role_policy='uncontested-secondary-catalogue-broad-role-not-invented-first-match-bench'))
    if len(matched)!=16 or len({r['source_player_id'] for r in matched})!=16:
        raise ValueError('positive fixed16 identities are incomplete or repeated')
    return actual,matched,bindings


def capture():
    actual, matched, inputs = join()
    output = ROOT.parent/'tachira-2015-original-person-identities-v1.json'
    document = capture_ids([r['source_player_id'] for r in matched],ROOT.parent/'tachira-2015-original-people',output,inputs)
    persons = {p['source_player_id']:p for b in document['batches'] for p in b['people']}
    if any(b['gaps'] for b in document['batches']) or any(persons[r['source_player_id']]['birth_date']!=r['birth_date'] for r in matched):
        raise ValueError('original biography gaps/conflicts require review before native approval')
    pipeline.write_canonical_json(ROOT.parent/'tachira-2015-original16-identity-links-v1.json',
        dict(season=actual['season'],original_match=actual,original_bindings=inputs,matched_people=matched,
            people_document=dict(path=registry.relative_workspace_path(output),sha256=registry.sha256_file(output)),
            native_writes=0,publication_authorised=False,
            limitation='First14 plus two bracketed members; week2 only corroborates membership/ground, never supplies a fictional opening bench. Calendar catalogues only identity/secondary facts.'))
    return document


if __name__=='__main__':
    result=capture()
    print(dict(confirmed_people=sum(len(b['people']) for b in result['batches']),native_writes=0),flush=True)
