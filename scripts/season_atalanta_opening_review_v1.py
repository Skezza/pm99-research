"""Reparse original Atalanta opening-XI evidence without publishing a game.

This is a source review, not a transfer-date inference or compiler bypass.
It binds the successful private pruning probe to its eleven original starters.
Remaining reserve membership and cold-build replay remain separate gates.
"""
import json
import re
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from scripts import season_historical_roster_audit_v1 as annual
from scripts import season_mode1_sourced_keeper_slot_v1 as sky
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_within_club_reserve_repair_v1 as roster


def biography(raw, title):
    """Read only explicit identity and finite senior playing-career rows."""
    page = BeautifulSoup(raw, 'lxml')
    headings, boxes = page.select('h1'), page.select('table.infobox')
    if len(headings) != 1 or headings[0].get_text(' ', strip=True) != title or len(boxes) != 1:
        raise ValueError('biography title/infobox differs')
    box = boxes[0]
    birthdays = box.select('.bday')
    if len(birthdays) != 1:
        raise ValueError('biography needs one literal birthday')
    birthday = date.fromisoformat(birthdays[0].get_text(strip=True)).isoformat()
    full_names, career = [], []
    sporting_names = [n.get_text(' ', strip=True) for n in box.select('caption.infobox-title')]
    section, senior_headers = False, 0
    for row in box.select('tr'):
        headers = row.select('th.infobox-header')
        if headers:
            section = headers[0].get_text(' ', strip=True).rstrip('*').strip() == 'Senior career'
            senior_headers += int(section)
            continue
        cells = row.find_all(['th', 'td'], recursive=False)
        if len(cells) >= 2 and cells[0].get_text(' ', strip=True) == 'Full name':
            full_names.append(cells[1].get_text(' ', strip=True))
        elif len(cells) == 1 and 'infobox-above' in cells[0].get('class', []):
            sporting_names.append(cells[0].get_text(' ', strip=True))
        if not section or len(cells) < 2:
            continue
        years = cells[0].get_text(' ', strip=True)
        if years in ('Years', 'Total'):
            continue
        match = re.fullmatch(r'(\d{4})(?:[–-](\d{4}))?', years)
        club = cells[1].get_text(' ', strip=True)
        if match is None or not club:
            raise ValueError('unsupported or incomplete senior-career row')
        start, end = int(match[1]), int(match[2] or match[1])
        if start > end:
            raise ValueError('reversed senior-career interval')
        career.append({'club': club.replace('→', '').replace('(loan)', '').strip(),
                       'start_year': start, 'end_year': end,
                       'loan': '→' in club or '(loan)' in club.casefold()})
    if senior_headers != 1 or not career:
        raise ValueError('one complete senior-career section is required')
    return {'title': title, 'birth_date': birthday, 'full_names': full_names,
            'sporting_names': sporting_names, 'senior_career': career}


def adriano_bridge(raw, source):
    person = biography(raw, 'Adriano (footballer, born April 1982)')
    if (person['sporting_names'] != ['Adriano']
            or person['full_names'] != ['Adriano Pereira da Silva']
            or source['name'] != 'Adriano Pereira'
            or source['birth_date'] != person['birth_date']
            or source['position'] != 'D'):
        raise ValueError('Adriano sporting/full-name/birthday bridge differs')
    spells = [r for r in person['senior_career'] if r['start_year'] <= 2006 <= r['end_year']]
    if (len(spells) != 1 or spells[0]['club'] != 'Atalanta' or spells[0]['loan']
            or not spells[0]['start_year'] < 2006 < spells[0]['end_year']):
        raise ValueError('Adriano has no unambiguous interior-year Atalanta spell')
    return dict(person, policy='reviewed-exact-sporting-name/full-name-prefix/DOB/interior-year-v1',
                exact_transfer_date_claimed=False)


def prepare(release=None):
    release = release or registry.load_preferred_release('2006-07')
    root = registry.ROOT / '.local/opening-xi-repairs-20261008'
    probe_path = root / 'atalanta-pruning-probe/probe-receipt.json'
    probe = json.loads(probe_path.read_text())
    if release.release_id != probe['release_id']:
        raise ValueError('review must extend the actual probed preferred baseline')
    for relative, expected in probe['source_native_hashes'].items():
        if registry.sha256_file(release.game_path / relative) != expected:
            raise ValueError('probed native baseline changed')
    old_path = registry.ROOT / '.local/critical-path-repairs-20261007/2006-07/keeper-plan-r49.json'
    old = json.loads(old_path.read_text())
    package = json.loads(release.package_path.read_text())
    club = next(c for c in package['clubs'] if c['carrier_id'] == 223)
    capture, proof = roster.annual_capture('2006-07', club)
    results = sky.original(old['bindings']['league_results'])
    receipt = json.loads(sky.original(old['bindings']['league_results_receipt']).read_text())
    for key in ('requested_url', 'response_url'):
        sky.dates.validate_url(receipt[key], release.season, 'I1')
    if receipt['sha256'] != registry.sha256_file(results):
        raise ValueError('original fixture results receipt changed')
    first = sky.dates.first_fixture(results.read_bytes(), release.season, 'I1', 'Atalanta')
    if first['fixture'] != old['first_fixture']['fixture']:
        raise ValueError('original first fixture changed')
    fixture = first['fixture']
    sheet = sky.report(sky.original(old['bindings']['lineup_report']).read_bytes(),
                       old['bindings']['report_url'], 'Atalanta', fixture['away'], fixture['date'])
    source_dir = root / 'italian-preflight/sources'
    alias_path = source_dir / 'adriano-pereira-wikipedia.html'
    adriano = next(p for p in capture['players'] if p['name'] == 'Adriano Pereira')
    alias = adriano_bridge(alias_path.read_bytes(), adriano)
    players = {p['carrier_id']: p for p in package['players']}
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    approved = []
    for carrier in probe['candidate_XI']:
        player = players[carrier]
        name = player.get('source_name') or player['name']
        matches = [p for p in capture['players'] if p['name'] == name]
        native = roster.native_facts(jug, carrier)
        sheet_name = 'Adriano' if carrier == 4571 else name
        if (len(matches) != 1 or sheet['starting_xi_names'].count(sheet_name) != 1
                or native['birth_date'] != matches[0]['birth_date']
                or native['position'] != matches[0]['position']
                or player['facts'].get('birth_date') != native['birth_date']):
            raise ValueError('source starter/native identity/birthday/broad role differs')
        approved.append({'carrier_id': carrier, 'player_id': player['id'], 'sheet_name': sheet_name,
                         'source': matches[0], 'native': native})
    if len(approved) != 11 or {r['sheet_name'] for r in approved} != set(sheet['starting_xi_names']):
        raise ValueError('candidate set is not the exact eleven original starters')
    if sum(r['source']['position'] == 'G' for r in approved) != 1 or approved[0]['source']['position'] != 'G':
        raise ValueError('source keeper is not uniquely at slot one')
    removals = []
    for carrier, file, title in [(3150, 'salvatore-fresi-wikipedia.html', 'Salvatore Fresi'),
                                 (4372, 'giovanni-tedesco-wikipedia.html', 'Giovanni Tedesco')]:
        path = source_dir / file
        person = biography(path.read_bytes(), title)
        native = roster.native_facts(jug, carrier)
        if (native['birth_date'] != person['birth_date']
                or annual.normalise(players[carrier].get('source_name') or players[carrier]['name']) != annual.normalise(title)
                or any(r['club'] == 'Atalanta' for r in person['senior_career'])
                or any(p['name'] == title for p in capture['players'])
                or title in sheet['starting_xi_names'] + sheet['bench_names']):
            raise ValueError('stale-link review contradicts original identities/career/squad/sheet')
        removals.append({'carrier_id': carrier, 'person': person,
                         'source_url': 'https://en.wikipedia.org/wiki/' + title.replace(' ', '_'),
                         'source_path': registry.relative_workspace_path(path),
                         'source_sha256': registry.sha256_file(path),
                         'basis': 'reviewed complete senior career plus annual/fixture absence; not an exact transfer-date proof'})
    left, right = roster.native_facts(jug, 4165), roster.native_facts(jug, 21149)
    bernardini = [p for p in capture['players'] if p['name'] == 'Antonio Bernardini']
    if (len(bernardini) != 1 or left['birth_date'] != right['birth_date']
            or left['birth_date'] != bernardini[0]['birth_date']
            or annual.normalise(left['name']) != annual.normalise(bernardini[0]['name'])
            or players[21149].get('source_name') != bernardini[0]['name']
            or players[21149]['facts'].get('birth_date') != right['birth_date']
            or left['position'] != right['position']
            or left['position'] != bernardini[0]['position']):
        raise ValueError('shared/exclusive Bernardini records are not the same native/annual identity')
    removals.append({'carrier_id': 4165, 'retained_carrier_id': 21149,
                     'basis': 'remove duplicate Atalanta link only; shared native person remains unchanged elsewhere',
                     'native_identity': left, 'annual_identity': bernardini[0]})
    return {'schema_version': 'pm99-Atalanta-original-opening-XI-source-review-v1',
            'season': release.season, 'source_release_id': release.release_id,
            'source_package_sha256': registry.sha256_file(release.package_path),
            'source_bindings': old['bindings'], 'first_fixture': first,
            'annual_proof': proof, 'original_XI_bench': sheet, 'approved_XI_identities': approved,
            'adriano_alias_review': alias, 'alias_source_path': registry.relative_workspace_path(alias_path),
            'alias_source_url': 'https://en.wikipedia.org/wiki/Adriano_(footballer,_born_April_1982)',
            'alias_source_sha256': registry.sha256_file(alias_path), 'reviewed_link_removals': removals,
            'private_probe_path': registry.relative_workspace_path(probe_path),
            'private_probe_sha256': registry.sha256_file(probe_path),
            'source_XI_identity_review_passed': True,
            'candidate_startup_slot_order_policy': 'reviewed editorial ordering of the sourced XI set; Sky does not publish this slot order',
            'missing_original_bench_players': ['Andrea Soncin', 'Marino Defendi'],
            'reserve_opening_membership_approved': False, 'historical_formation_approved': False,
            'compiler_replay_integrated': False, 'publishable': False, 'registered': False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = prepare()
    pipeline.write_canonical_json(args.output, report)
    print(json.dumps({'source_XI_identity_review_passed': True, 'publishable': False,
                      'output': str(args.output)}))
