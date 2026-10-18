"""Replay original foreign-club sources and test the exact fixed18 allocation.

Source-only feasibility, NOT a release or a duplicate-case closure. In
particular this does not relabel an English/Soccerbase transaction as Serbian.
Manager/ground/kit, native writing, exact reconstruction and runtime remain
separate requirements before this proposal may be published.
"""
import copy
import re

from bs4 import BeautifulSoup

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_historical_transfer_review_v1 as transfer
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_transfer_history_v1 as histories
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import capture_transfermarkt_opening_lineups_v1 as openings
from scripts.capture_ofk_2004_original_people_20261010 import original
from scripts.capture_ofk_2004_reserve_brackets_20261010 import original_ids
from scripts.capture_stock_replacement_sources_20261010 import ROOT

POLICY = 'original-foreign-fixed-capacity-XI-plus-strict-dated-reserves-v1'
SCHEMA = 'pm99-private-original-foreign-source-allocation-v1'
AUDIT = ROOT.parent


def dated_manager_ground(raw):
    page = BeautifulSoup(raw, 'html.parser')
    home = page.select_one('.sb-team.sb-heim a.sb-vereinslink')
    date = page.select_one('.sb-datum a[href$="/datum/2004-08-20"]')
    if home is None or home.get('href') != '/ofk-belgrad/startseite/verein/53/saison_id/2004' or date is None:
        raise ValueError('ground proof is not the dated target home fixture')
    grounds = page.select('a[href="/stadion/stadion/verein/53/saison_id/2004"]')
    if len(grounds) != 1 or grounds[0].get_text(' ', strip=True) != 'Omladinski stadion':
        raise ValueError('dated original stadium is missing or ambiguous')
    sections = [section for section in page.select('.aufstellung-box')
        if section.select_one('.aufstellung-unterueberschrift-mannschaft a.sb-vereinslink[href="/ofk-belgrad/startseite/verein/53/saison_id/2004"]')]
    if len(sections) != 1:
        raise ValueError('dated original target lineup is missing or ambiguous')
    coaches = sections[0].select('a[href*="/profil/trainer/"]')
    if (len(coaches) != 1 or coaches[0].get('href') != '/branko-babic/profil/trainer/4219'
            or coaches[0].get_text(' ', strip=True) != 'Branko Babic'):
        raise ValueError('dated original coach identifies another person')
    return dict(date='2004-08-20', source_club_id=53, home_club='OFK Beograd',
        manager='Branko Babic', source_manager_id=4219,
        ground='Omladinski stadion', source_match_id=3142214)


def annual_roles(raw, expected_year=2004, expected_club_name='OFK Beograd'):
    page = BeautifulSoup(raw, 'html.parser')
    period = f'{expected_year % 100:02d}/{(expected_year + 1) % 100:02d}'
    if page.title is None or f'{expected_club_name} - Detailed squad {period}' not in page.title.get_text():
        raise ValueError('annual roster title identifies another club or period')
    result = {}
    for tr in page.select('table.items > tbody > tr'):
        ids = {int(m.group(1)) for a in tr.select('a[href*="/profil/spieler/"]')
            if (m := re.search(r'/profil/spieler/(\d+)(?:/|$)', a.get('href', '')))}
        if not ids:
            continue
        if len(ids) != 1:
            raise ValueError('annual broad-role row identifies multiple people')
        id = next(iter(ids))
        role = tr.select_one('td.rueckennummer')
        broad = {'Goalkeeper': 'G', 'Defender': 'D', 'Midfield': 'M', 'Attack': 'F'}.get(
            role.get('title') if role else None)
        if broad is None or id in result:
            raise ValueError('annual broad-role row is unknown or duplicated')
        result[id] = broad
    return result


def select_reserves(events, annual_ids, fixture_date, xi):
    result = []
    for id in sorted(events):
        bracket = transfer.transfer_interval(events[id], fixture_date)
        if (id not in xi and id in annual_ids
                and bracket.get('status') == 'recorded-entry-and-exit-bracket-fixture'
                and bracket['source_owner_club_id'] == 53):
            result.append(dict(source_player_id=id, annual_name=annual_ids[id], bracket=bracket))
    return result


def replay_sources(*, secondary_facts=False):
    annual, annual_binding = original_ids(2004)
    annual_raw, _ = original('ofk-beograd-2004')
    roles = annual_roles(annual_raw)
    schedule, schedule_binding = original('ofk-beograd-2004-schedule')
    report, report_binding = original('ofk-first-fixture-2004-3142214')
    class Offline:
        def get(self, url, key):
            if url == schedule_binding['url']: return schedule
            if url == report_binding['url']: return report
            raise ValueError('source replay requested an unbound original URL')
    ref = openings.TeamRef('OFK Beograd', 'OFK Beograd', 53,
        '/ofk-belgrad/startseite/verein/53', 'exact-original-club-id')
    fixture = openings._first_fixture(ref, season_start_year=2004, competition_code='SER1', cache=Offline())
    if (fixture['match_id'], fixture['date']) != ('3142214', '2004-08-20'):
        raise ValueError('original earliest domestic fixture changed')
    opening = openings._lineup_from_report(ref, fixture, Offline())
    if opening['declared_manager'] != 'Branko Babic':
        raise ValueError('original dated manager changed')
    xi_ids = [int(row['source_player_id']) for row in opening['starting_xi']]
    if len(xi_ids) != 11 or len(set(xi_ids)) != 11:
        raise ValueError('original first XI repeats or omits people')
    history_path = AUDIT / 'ofk-2004-intersection-history-v1.json'
    events, history_review = histories.merge({}, pipeline.read_json_file(history_path))
    reserves = select_reserves(events, annual, fixture['date'], set(xi_ids))
    if len(reserves) != 7:
        raise ValueError('positive dated reserves do not complete18 fixed slots')
    bindings = [annual_binding, schedule_binding, report_binding,
        dict(path=registry.relative_workspace_path(history_path), sha256=registry.sha256_file(history_path))]
    claims_path = AUDIT / 'ofk-2004-positive-fixed18-source-claims-v1.json'
    claims = pipeline.read_json_file(claims_path)
    expected = dict(season='2004-05', first_fixture=fixture, original_opening=opening,
        opening_xi_ids=sorted(xi_ids), dated_reserves=reserves, original_bindings=bindings,
        native_writes=0, approved_for_native_publication=False,
        scope='Positive18 dated people only. Original unused match bench absent; manager name published in actual fixture. Native identity/assets/replay/runtime proof still required.')
    if claims != expected:
        raise ValueError('retained source claims do not reproduce from original pages/histories')
    people_path = AUDIT / 'ofk-2004-original-person-identities-v1.json'
    document = pipeline.read_json_file(people_path)
    expected_inputs = bindings + [dict(path=registry.relative_workspace_path(claims_path),
        sha256=registry.sha256_file(claims_path))]
    if document['historical_opening_inputs'] != expected_inputs:
        raise ValueError('original biography query has different historical inputs')
    _, review = people.merge({}, document)
    parsed = [p for batch in document['batches'] for p in batch['people']]
    ids = xi_ids + [r['source_player_id'] for r in reserves]
    by_id = {p['source_player_id']: p for p in parsed}
    if len(by_id) != 18 or set(by_id) != set(ids) or review['refused']:
        raise ValueError('original confirmed biographies do not match18 selected people')
    desired = []
    match_roles = {'Goalkeeper': 'G', 'Defenders': 'D', 'Midfielders': 'M', 'Forwards': 'F'}
    for i, id in enumerate(ids):
        person = {k: copy.deepcopy(v) for k, v in by_id[id].items() if k != 'published_name_variants'}
        role = match_roles.get(opening['starting_xi'][i]['source_position_group']) if i < 11 else roles[id]
        if role not in ('G', 'D', 'M', 'F') or (i < 11 and role != roles.get(id)):
            raise ValueError('dated match and annual broad role disagree')
        desired.append(dict(source_person=person,
            source_player=dict(name=person['name'], birth_date=person['birth_date'], position=role,
                nationality=None, height_cm=None, weight_kg=None, shirt_number=None),
            membership='starting_xi' if i < 11 else 'positive-original-dated-opening-reserve',
            raw_evidence=dict(status='raw-source-reparsed', local_path=annual_binding['path'],
                source_sha256=annual_binding['sha256']),
            source_role_basis='original-first-fixture-position-group' if i < 11 else 'original-target-annual-broad-group',
            secondary_facts_status='unconfirmed-log-not-inherit-as-source-fact'))
    allocation.validate_opening_birth_dates(desired, fixture['date'])
    secondary_review = None
    if secondary_facts:
        from scripts import ofk_2004_original_secondary_facts_v1 as secondary
        facts = secondary.parse(annual_raw, desired)
        for row in desired:
            fact = facts[row['source_person']['source_player_id']]
            row['source_player'].update(nationality=fact['nationality'], height_cm=fact['height_cm'])
            row['secondary_facts_status'] = fact
        secondary_review = dict(policy=secondary.POLICY, facts=[facts[id] for id in sorted(facts)],
            native_country_jurisdiction_normalisation_declared=True,
            current_player_feed_attributes_used=False, annual_appearance_used_as_ownership=False)
    bindings.append(dict(path=registry.relative_workspace_path(people_path), sha256=registry.sha256_file(people_path)))
    result = dict(first_fixture=fixture, original_opening=opening, desired_people=desired,
        original_bindings=bindings, original_biography_review=review, original_history_review=history_review)
    if secondary_review is not None: result['secondary_fact_review'] = secondary_review
    return result


def prepare(output, *, secondary_facts=False, baseline_release_id=None):
    if output.exists(): raise ValueError('source allocation is immutable')
    source = replay_sources(secondary_facts=secondary_facts)
    release = (registry.load_registered_release('2004-05', baseline_release_id) if baseline_release_id
        else registry.load_preferred_release('2004-05'))
    layers = list(planner.package_layers(release))
    matches = [(name, package, path, c) for name, package, path in layers
        for c in package['clubs'] if c['carrier_id'] == 706]
    if len(matches) != 1: raise ValueError('foreign carrier must have exactly one recipe owner')
    layer, package, path, club = matches[0]
    if club['name'] != 'Becej': raise ValueError('foreign baseline identity changed')
    if any(c['name'].casefold() == 'ofk beograd' for _, p, _ in layers for c in p['clubs']):
        raise ValueError('proposed target already exists')
    slots = [p for p in package['players'] if p['club_id'] == club['id']]
    if len(slots) != 18: raise ValueError('foreign fixed capacity changed')
    original = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    orders = allocation.startup_orders(original, slots)
    people_path = AUDIT / 'ofk-2004-original-person-identities-v1.json'
    ids = [r['source_person']['source_player_id'] for r in source['desired_people']]
    fitted = allocation.allocate(original, slots, source['desired_people'], display.claims(people_path),
        published_families=families.claims(people_path, ids),
        opening_slot_orders=orders, allow_keeper_order_exchange=True)
    result = dict(schema_version=SCHEMA, policy=POLICY, season='2004-05', layer=layer,
        before_club=club, new_club='OFK Beograd', country='serbia', transfermarkt_club_id=53,
        baseline_release_id=release.release_id,
        baseline_package=dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path)),
        baseline_jug_sha256=registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
        allocation=fitted, **source, native_writes=0, approved_for_native_publication=False,
        remaining_requirements=['target club/ground/kit assets', 'source-bound manager/native identity',
            'complete native write/readback', 'exact reconstruction', 'fresh runtime verification'])
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    prepare(AUDIT / 'ofk-2004-fixed18-private-allocation-v1.json')
