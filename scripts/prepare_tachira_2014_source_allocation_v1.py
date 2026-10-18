"""Source-only16-slot feasibility for the original2014 Táchira opening.

Never counts a duplicate closure or writes native files. Dated presentation
roles take precedence over adjacent-calendar catalogues; unresolved conflicting
bench roles are excluded rather than guessed into a capacity-fitting selection.
"""
import copy
import itertools
import re
import unicodedata
from bs4 import BeautifulSoup
from scripts.capture_tachira_2014_original_people_v1 import join, source_rows
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_published_person_identity_v1 as people
from scripts import season_published_display_names_v1 as display
from scripts import season_published_family_component_v1 as families
from scripts import prepare_duplicate_club_disposition_v1 as allocation
from scripts import audit_published_player_identities_v1 as identities
from scripts import season_historical_roster_audit_v1 as roster


def name_words(value):
    unaccented = ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                         if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', unaccented).strip()


def dated_roles(actual, matched):
    _, raw, binding = source_rows('tachira-2014-original-season-presentation')
    text = BeautifulSoup(raw, 'html.parser').get_text(' ', strip=True)
    if ('viernes 08 de agosto' not in text or 'Temporada 2014-2015' not in text
            or 'Prensa Dvo Táchira' not in text or 'Daniel Farías, director técnico' not in text):
        raise ValueError('presentation lacks opening-period club attribution/coach')
    sections = [
        ('G', 'Los arqueros para esta nueva zafra serán ', 'En la defensa estarán '),
        ('D', 'En la defensa estarán ', 'La mitad del campo la defenderán '),
        ('M', 'La mitad del campo la defenderán ', 'El ataque lo potenciarán '),
        ('F', 'El ataque lo potenciarán ', 'El cuerpo técnico estará conformado '),
    ]
    roles = {}
    for role, start, end in sections:
        if text.count(start) != 1 or text.count(end) != 1:
            raise ValueError('dated role section missing or ambiguous')
        section = name_words(text.split(start, 1)[1].split(end, 1)[0])
        for row in matched:
            name = name_words(row['published_match_name'])
            if re.search(r'(?<![a-z])' + re.escape(name) + r'(?![a-z])', section):
                if row['source_player_id'] in roles:
                    raise ValueError('dated presentation assigns one person two roles')
                roles[row['source_player_id']] = dict(role=role, basis='dated2014-08-08-club-presentation', binding=binding)
    _, catalogue, catalogue_binding = source_rows('tachira-2014-original-season-role-catalogue')
    page = BeautifulSoup(catalogue, 'html.parser')
    if page.title is None or 'Plantilla Táchira - 2014/2015' not in page.title.get_text():
        raise ValueError('role catalogue period differs')
    # Only Orozco is absent from the presentation's midfield paragraph. Its
    # original season row explicitly publishes the full identity in image alt.
    rows = page.select('#squadTableMidfielder tbody tr')
    candidates = [r for r in rows if r.select_one('img[alt="Yohandry José Orozco Cujía"]')]
    named = [r for r in matched if r['published_match_name'] == 'Yohandry Orozco']
    if len(candidates) != 1 or len(named) != 1:
        raise ValueError('missing unique original season Orozco midfield row')
    roles[named[0]['source_player_id']] = dict(role='M', basis='original2014-15-season-full-name-role-row', binding=catalogue_binding)
    if len(roles) != 18:
        raise ValueError('source role review omits an opening person')
    # Cermeño's presentation says defender; both season-specific catalogues say
    # midfield. He is a used substitute, not an XI member. Exclude this pending
    # role disagreement from the chosen16; keep the original match intact.
    conflicts = [dict(source_player_id=271257, presentation_role='D', season_catalogue_role='M',
        policy='exclude-unresolved-bench-role-from-selected16-not-guess')]
    if roles[127844]['role'] != 'M':
        raise ValueError('dated Agnel midfield proof lost')
    return roles, conflicts, [binding, catalogue_binding]


def prepare(output, baseline_release_id=None):
    if output.exists():
        raise ValueError('source-only allocation is immutable')
    actual, matched, original_bindings = join()
    role_rows, conflicts, role_bindings = dated_roles(actual, matched)
    biography = ROOT.parent / 'tachira-2014-original-person-identities-v1.json'
    document = pipeline.read_json_file(biography)
    if document['historical_opening_inputs'] != original_bindings:
        raise ValueError('biography query originally bound different sources')
    index, _ = identities.load_identity_snapshot()
    index, review = people.merge(index, document)
    if review['refused']:
        raise ValueError('original identities conflict with pinned publisher people')
    persons = {p['source_player_id']: p for b in document['batches'] for p in b['people']}
    if set(persons) != {r['source_player_id'] for r in matched}:
        raise ValueError('opening biographies incomplete')
    release = (registry.load_registered_release('2014-15', baseline_release_id) if baseline_release_id
               else registry.load_preferred_release('2014-15'))
    layers = list(planner.package_layers(release))
    owners = [(label, package, path, c) for label, package, path in layers for c in package['clubs'] if c['carrier_id'] == 2953]
    if len(owners) != 1:
        raise ValueError('fixed native club has multiple recipe owners')
    layer, package, package_path, club = owners[0]
    if club['name'] != 'Minervén' or any('tachira' in roster.normalise(c['name']) for _, p, _ in layers for c in p['clubs']):
        raise ValueError('baseline club changed or replacement club already exists')
    slots = [p for p in package['players'] if p['club_id'] == club['id']]
    if len(slots) != 16:
        raise ValueError('original fixed16 capacity changed')
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    orders = allocation.startup_orders(jug, slots)
    xi = [r['source_player_id'] for r in matched[:11]]
    bench = [r['source_player_id'] for r in matched[11:] if r['source_player_id'] != 271257]
    trials = []
    for extras in itertools.combinations(bench, 5):
        ids = xi + list(extras)
        desired = []
        for n, id in enumerate(ids):
            person = {k: copy.deepcopy(v) for k, v in persons[id].items() if k != 'published_name_variants'}
            desired.append(dict(source_person=person,
                source_player=dict(name=person['name'], birth_date=person['birth_date'], position=role_rows[id]['role'],
                    nationality=None, height_cm=None, weight_kg=None, shirt_number=None),
                membership='starting_xi' if n < 11 else 'published-opening-match-substitute',
                raw_evidence=dict(status='raw-source-reparsed', local_path=original_bindings[0]['path'], source_sha256=original_bindings[0]['sha256']),
                source_role_basis=role_rows[id], secondary_facts_status='unconfirmed-log-not-inherit-as-source-fact'))
        allocation.validate_opening_birth_dates(desired, actual['fixture_date'])
        try:
            fitted = allocation.allocate(jug, slots, desired, display.claims(biography),
                published_families=families.claims(biography, ids), opening_slot_orders=orders, allow_keeper_order_exchange=True)
        except ValueError as exc:
            trials.append(dict(extra_ids=list(extras), reason=str(exc)))
            continue
        break
    else:
        raise ValueError('no positive first-XI/published-bench16 fits original native windows: ' + str(trials))
    outside = []
    for _, p, _ in layers:
        clubs = {c['id']: c['name'] for c in p['clubs']}
        for player in p['players']:
            key = identities.key(player, index)
            if player['club_id'] != club['id'] and key and key[0] == 'published-person' and key[1] in ids:
                outside.append(dict(source_player_id=key[1], carrier_id=player['carrier_id'], club=clubs[player['club_id']], native_recipe_player=player))
    result = dict(schema_version='pm99-private-original-tachira2014-fixed16-feasibility-v1', season='2014-15',
        policy='original-dated-club-press-XI-plus-published-bench-fixed-capacity-v1', baseline_release_id=release.release_id,
        layer=layer, baseline_package=dict(path=registry.relative_workspace_path(package_path), sha256=registry.sha256_file(package_path)),
        before_club=club, new_club='Deportivo Tachira', country='venezuela', transfermarkt_club_id=13297,
        original_opening=actual, original_bindings=original_bindings + role_bindings,
        biography_input=dict(path=registry.relative_workspace_path(biography), sha256=registry.sha256_file(biography)),
        desired_people=desired, allocation=fitted, selected_bench_ids=list(extras),
        capacity_selection_policy='First published-bench-order combination of5 positively dated people with uncontested sourced broad roles fitting all16 windows',
        unsuccessful_capacity_sets=trials, role_disagreements=conflicts, outside_identity_owners=outside,
        native_writes=0, publication_authorised=False,
        remaining=['secondary facts/dated nationality', 'source-bound manager/ground/kits',
                   'native compilation/readback', 'full exact source reconstruction', 'actual runtime proof'])
    pipeline.write_canonical_json(output, result)
    return result


if __name__ == '__main__':
    result = prepare(ROOT.parent / 'tachira-2014-fixed16-source-feasibility-v1.json')
    print(dict(people=len(result['desired_people']), outside_owners=len(result['outside_identity_owners']),
        bench=result['selected_bench_ids'], native_writes=0), flush=True)
