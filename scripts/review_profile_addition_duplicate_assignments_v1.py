"""Prove duplicate input assignments from original first-match jersey identity.

Not a same-name deletion policy. Require the exact original squad shirt number
and full name to identify the same numeric player in the target club's original
first league fixture, plus a bound original profile and two explicit source-row
assignments. Missing DOBs alone and absence from a match never authorize pruning.
This module reviews only; publication is a separately validated native delta.
"""
import hashlib
import re

from bs4 import BeautifulSoup
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_trabzon_opening_review_v1 as identity
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import season_historical_roster_audit_v1 as rosters
from scripts import season_italian_opening_layer_v1 as native
from scripts import season_opening_order_repair_v1 as ownership
from scripts.capture_transfermarkt_lineup_person_evidence_v1 import _profile_facts

SCHEMA = 'pm99-original-shirt-bound-duplicate-input-assignment-review-v1'
NUMERIC_SCHEMA = 'pm99-original-numeric-annual-and-match-duplicate-input-assignment-review-v2'


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def bound_annual_capture(release, club, pre, root):
    """Use the exact composed input, not an arbitrary revision or file glob.

    The older source loader predates revisioned backfills. Original page
    title/hash/player-table reparse still gates every admitted annual row.
    """
    plan_path = root / 'plan.json'
    plan = pipeline.read_json_file(plan_path)
    intake_binding = plan['source_intake']
    intake_path = (registry.ROOT / intake_binding['path']).resolve()
    registry.relative_workspace_path(intake_path)
    if registry.sha256_file(intake_path) != intake_binding['sha256']:
        raise ValueError('bound source intake changed')
    intake = pipeline.read_json_file(intake_path)
    if (registry.sha256_file(intake_path) != pre['sources']['source_intake_sha256']
            or intake['source_capture_sha256'] != pre['sources']['source_capture_sha256']):
        raise ValueError('original preallocation/composed input binding differs')
    # This is the explicit composition in the bound revision, never a search
    # for whichever historical file happens to have the preferred facts.
    capture_path = intake_path.parent / 'world-squads-composed.json'
    if not capture_path.is_file():
        return facts.annual_capture(release.season, club)
    document = pipeline.read_json_file(capture_path)
    if registry.sha256_file(capture_path) != intake['source_capture_sha256']:
        raise ValueError('original composed capture changed')
    if document.get('season', {}).get('label') != release.season[:4] + '/' + release.season[-2:]:
        raise ValueError('original composition is not selected season')
    names = rosters.club_names(rosters.club_group(club), club['name'], club.get('full_name', ''))
    rows = [c for c in document['clubs'] if rosters.source_group(c['country_catalog']) == rosters.club_group(club)
            and rosters.normalise(c['club_name']) in names]
    verifier = rosters.SourceVerifier(release.season)
    good = [(c, verifier.verify(c)) for c in rows]
    good = [(c, p) for c, p in good if p['status'] == 'raw-source-reparsed']
    if len(good) != 1:
        raise ValueError('bound composition lacks one original target-season club roster')
    capture, proof = good[0]
    proof = dict(proof, bound_intake=binding(intake_path), bound_capture=binding(capture_path))
    return capture, proof


def first_match_shirt(raw, club_id, person_id):
    page = BeautifulSoup(raw, 'lxml')
    boxes = []
    for box in page.select('div.large-6, div.aufstellung-box'):
        ids = {int(m[1]) for a in box.select('a[href]')
            if (m := re.search(r'/startseite/verein/(\d+)(?:/|$)', a['href']))}
        if ids == {int(club_id)} and box.select('.formation-player-container'):
            boxes.append(box)
    if len(boxes) != 1:
        raise ValueError('original club pitch box missing or ambiguous')
    witnesses = []
    for cell in boxes[0].select('.formation-player-container'):
        ids = {m[1] for a in cell.select('a[href]')
            if (m := re.search(r'/profil/spieler/(\d+)(?:/|$)', a['href']))}
        if ids != {str(person_id)}:
            continue
        shirts = cell.select('.tm-shirt-number')
        if len(shirts) != 1 or not shirts[0].get_text(strip=True).isdigit():
            raise ValueError('original numeric player lacks one literal match shirt')
        witnesses.append(int(shirts[0].get_text(strip=True)))
    if len(witnesses) != 1:
        raise ValueError('original match numeric player/shirt ambiguous')
    return witnesses[0]


def annual_numeric_identity(raw, name, expected_id):
    page = BeautifulSoup(raw, 'lxml')
    witnesses = []
    for row in page.select('table.items > tbody > tr'):
        names = [a for a in row.select('td.hauptlink a[href]')
            if identity.key(a.get_text(' ', strip=True)) == identity.key(name)]
        if not names:
            continue
        ids = {m[1] for a in row.select('a[href]')
            if (m := re.search(r'/profil/spieler/(\d+)(?:/|$)', a['href']))}
        if ids != {str(expected_id)}:
            raise ValueError('original annual full-name row identifies a different numeric person')
        witnesses.append(str(expected_id))
    if witnesses != [str(expected_id)]:
        raise ValueError('original annual numeric identity missing or ambiguous')
    return dict(source_player_id=str(expected_id), published_full_name=name,
        policy='one original annual full-name row with same exact numeric identity as original first XI')


def prove_projection_pair(people, projected, annual, profile, shirt, *, numeric_identity=None):
    # The source projection must declare two rows for this one jersey identity;
    # person hashes must identify those exact rows, not just similar surnames.
    name = identity.key(profile['published_full_name'])
    raw = [p for p in annual if identity.key(p['name']) == name]
    rows = [p for p in projected if identity.key(p['facts']['name']) == name]
    if len(raw) != 1 or len(rows) != 2:
        raise ValueError('annual/projection same-name identity not unique')
    if (raw[0].get('birth_date') is not None or
            (numeric_identity is None and raw[0].get('shirt_number') != shirt)):
        raise ValueError('annual unknown-DOB row lacks identical original match shirt')
    if numeric_identity is not None and numeric_identity['source_player_id'] != profile['source_player_id']:
        raise ValueError('annual/profile original numeric identities differ')
    additions = [p for p in rows if p.get('opening_xi_origin') == 'profiled-first-fixture-addition'
        and p.get('opening_source_player_id') == profile['source_player_id']]
    inherited = [p for p in rows if not p.get('opening_source_player_id')]
    if len(additions) != 1 or len(inherited) != 1 or inherited[0]['facts'] != raw[0]:
        raise ValueError('not one exact original annual row plus one exact profiled addition')
    born = profile.get('published_birth_date')
    if not born or additions[0]['facts'].get('birth_date') != born:
        raise ValueError('profiled addition original birthday differs or is unavailable')
    mapping = {p['person_id']: p for p in people}
    expected = {'person-source-' + row['source_row_sha256'] for row in rows}
    if len(mapping) != 2 or set(mapping) != expected:
        raise ValueError('native recipe people are not these two explicit input assignments')
    retained = mapping['person-source-' + additions[0]['source_row_sha256']]
    removed = mapping['person-source-' + inherited[0]['source_row_sha256']]
    if (retained['facts'].get('birth_date') != born
            or removed['facts'].get('birth_date') != {'policy': 'preserve-existing-mode1'}
            or identity.key(retained.get('source_name', '')) != name
            or identity.key(removed.get('source_name', '')) != name):
        raise ValueError('recipe profiled identity or explicit unresolved annual preimage differs')
    return retained, removed


def prepare(release, case, *, numeric_annual=False):
    if case['season'] != release.season:
        raise ValueError('duplicate case targets another season')
    package = pipeline.read_json_file(release.package_path)
    club = next(c for c in package['clubs'] if c['id'] == case['club_id'])
    people = [p for p in package['players'] if p['carrier_id'] in {q['carrier_id'] for q in case['players']}]
    if len(people) != 2 or any(p['club_id'] != club['id'] for p in people):
        raise ValueError('duplicate input case not two people owned by the exact club')
    root = registry.ROOT / '.local/transfermarkt-opening-plans-current-v1' / release.season
    pre_path = root / 'opening-squad-preallocation.json'
    artifact = next(a for a in package['artifacts'] if a['id'] == 'opening-squad-preallocation-' + release.season)
    if artifact['sha256'] != registry.sha256_file(pre_path):
        raise ValueError('original input preallocation not bound by current recipe')
    pre = pipeline.read_json_file(pre_path)
    capture, annual_proof = bound_annual_capture(release, club, pre, root)
    projected = [c for c in pre['source_clubs'] if c['selector']['club_name'] == capture['club_name']
        and c['selector']['country_catalog'] == capture['country_catalog']
        and c['selector']['competition_catalog'] == capture['competition_catalog']]
    if len(projected) != 1:
        raise ValueError('exact original projection club missing or ambiguous')
    projected = projected[0]
    lineup_path = root / 'opening-lineups.json'
    lineup = pipeline.read_json_file(lineup_path)
    matches = [c for c in lineup['clubs'] if c['source_selector']['club_name'] == capture['club_name']
        and c['source_selector']['country_catalog'] == capture['country_catalog']
        and c['source_selector']['competition_catalog'] == capture['competition_catalog']]
    if len(matches) != 1:
        raise ValueError('exact original first fixture missing or ambiguous')
    match = matches[0]
    witness = opening.verify_opening(match, lineup, root / 'cache')
    if projected['opening_fixture_date'] != witness['date'] or not projected['opening_xi_complete']:
        raise ValueError('projection lacks the same complete original first XI/date')
    wanted = identity.key(people[0]['source_name'])
    additions = [q for q in projected['players'] if identity.key(q['facts']['name']) == wanted
        and q.get('opening_xi_origin') == 'profiled-first-fixture-addition']
    if len(additions) != 1:
        raise ValueError('case lacks one original profiled first-fixture addition')
    id = additions[0]['opening_source_player_id']
    if id not in witness['starting_xi']:
        raise ValueError('addition is not positively published in original target XI')
    raw_match, _ = opening.verified_page(root / 'cache', lineup['source']['cache_files'], match['lineup_source_url'])
    slugs = identity.original_person_links(raw_match, {id})
    if identity.key(slugs[id]) != wanted:
        raise ValueError('full original numeric match slug identifies another person')
    person_path = root / 'opening-lineup-person-evidence.json'
    persons = pipeline.read_json_file(person_path)
    urls = [q['url'] for q in persons['source']['cache_files'] if q['url'].rstrip('/').endswith('/spieler/' + id)]
    if len(urls) != 1 or '/'+slugs[id]+'/profil/spieler/'+id not in urls[0]:
        raise ValueError('original same numeric profile identity missing or ambiguous')
    raw_profile, profile_proof = opening.verified_page(root / 'person-cache', persons['source']['cache_files'], urls[0])
    profile = _profile_facts(raw_profile, player={'source_player_id': id})
    shirt = first_match_shirt(raw_match, witness['source_club_id'], id)
    numeric_identity = None
    if numeric_annual:
        annual_path = registry.ROOT / annual_proof['local_path']
        if registry.sha256_file(annual_path) != annual_proof['source_sha256']:
            raise ValueError('original annual numeric witness changed')
        numeric_identity = annual_numeric_identity(annual_path.read_bytes(), profile['published_full_name'], id)
    retained, removed = prove_projection_pair(people, projected['players'], capture['players'], profile, shirt,
        numeric_identity=numeric_identity)
    proof_id = 'opening-squad-preallocation-' + release.season
    if any(p['proof']['artifact_id'] != proof_id for p in people):
        raise ValueError('one recipe identity comes from an unrelated person source')
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    _, _, roster = native.roster_rows(eq, club['carrier_id'])
    before = {str(p['carrier_id']): facts.native_facts(jug, p['carrier_id']) for p in people}
    if before[str(retained['carrier_id'])]['birth_date'] != profile['published_birth_date']:
        raise ValueError('retained native birthday differs from original positive-match profile')
    if any(roster.count((p['carrier_id'], 0)) != 1 for p in people):
        raise ValueError('duplicate native links not each exactly once in target roster')
    owners = ownership.native_owners(eq)
    if any(owners.get(p['carrier_id']) != {club['carrier_id']} for p in people):
        raise ValueError('shared native identity prevents exclusive duplicate pruning')
    result = dict(schema=NUMERIC_SCHEMA if numeric_annual else SCHEMA, case_id=case['id'], season=release.season,
        release_id=release.release_id, package_sha256=registry.sha256_file(release.package_path),
        jug_sha256=hashlib.sha256(jug).hexdigest(), eq_sha256=hashlib.sha256(eq).hexdigest(),
        club_id=club['id'], club_carrier_id=club['carrier_id'],
        source_bindings=[binding(pre_path), binding(lineup_path), binding(person_path)],
        original_annual_source=annual_proof, original_profile=profile_proof,
        first_fixture=witness, matched_original_shirt=shirt,
        retained_player=retained, removed_player=removed, native_before=before,
        native_roster_before=[list(q) for q in roster],
        duplicate_input_assignment_proved=True, native_writes=0,
        removed_is_current_native_starter=before[str(removed['carrier_id'])]['startup_order'] <= 11,
        scope='One raw annual jersey identity was allocated again as its original positive-first-XI numeric profile. This proves duplicate input assignment, not full-squad completeness or unrelated DOB/skills/portrait approval.')
    if numeric_annual:
        result.update(original_annual_numeric_identity=numeric_identity,
            scope='The exact same original numeric player was allocated from annual squad and positive first-XI profile rows. Shirt-number disagreement is retained, not guessed away. No full-squad or unrelated facts approval.')
    return result
