"""Source-bound roster-link selection without player rewrites.

The original annual shirt identity and first-match numeric profile must prove
each input collision. This narrow layer cannot remove a starter, replace a
person or approve a historical squad merely by making a candidate disappear.
The opt-in source-selection policy instead requires a reparsed positive squad
and its original XI, and records seed omissions separately from duplicate bugs.
"""
import copy
import hashlib

from app.eq_roster_pruning import prune_visible_mode1_roster_payload
from scripts import review_profile_addition_duplicate_assignments_v1 as source
from scripts import season_italian_opening_layer_v1 as native
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA = 'pm99-source-bound-reserve-input-assignment-pruning-v1'
PREFIX = 'sourced-profile-assignment-pruning-'
FILENAME = 'sourced-profile-assignment-pruning.json'
SOURCE_SELECTION = 'source-selected-target-season-roster-v1'


def _verify_selection_fixture_year(season, country, code, fixture_date):
    from scripts import transfermarkt_calendar_year_policy_v1 as calendar
    from datetime import date
    year = int(season[:4])
    calendar.route_provider_year(year, code, country)  # retain Russia quarantine
    if country in calendar.AUDIT_CALENDAR_COUNTRIES and date.fromisoformat(fixture_date).year != year:
        raise ValueError('source roster selection rejects next-year calendar fixtures')


def _roster_rows(eq, club_id, plan):
    if plan.get('policy') != SOURCE_SELECTION:
        return native.roster_rows(eq, club_id)
    from app.fdi_indexed import IndexedFDIFile
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    index = IndexedFDIFile.from_bytes(eq)
    entries = [e for e in index.entries if e.record_id == club_id]
    if len(entries) != 1:
        raise ValueError('source roster selection club is absent or repeated')
    entry = entries[0]
    raw = eq[entry.payload_offset:entry.payload_offset + entry.payload_length]
    roster = parse_eq_external_team_roster_payload(raw, {})
    if roster is None or roster.mode_byte != 1 or any(row.flag not in (0, 1) for row in roster.rows):
        raise ValueError('source roster selection only preserves known opaque zero/one rows')
    return index, raw, [(row.player_record_id, row.flag) for row in roster.rows]


def _prepare_source_selection(release, cases):
    """Omit explicitly selected seed links, not classify people as duplicates.

    A positive, reparsed target-season cohort and its complete sourced XI are
    mandatory. Omission is a roster selection, not evidence of retirement or
    different-club ownership. Keep every player object and JUG byte intact.
    """
    from scripts import season_historical_club_label_full_cohort_optin_v2 as full
    from scripts.season_source_bound_fixture_membership_v1 import _source_path
    from app.fdi_indexed import IndexedFDIFile
    from datetime import date
    from scripts.season_frozen_fixture_reserve_v2 import heading_name
    package = pipeline.read_json_file(release.package_path)
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    jug_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    _, owners = full._native_owner_index(eq)
    reviews = []
    for case in cases:
        if case.get('policy') != SOURCE_SELECTION:
            raise ValueError('source roster selection cannot mix removal policies')
        club = next(c for c in package['clubs'] if c['carrier_id'] == case['club_carrier_id'])
        artifact_id = full.ARTIFACT_PREFIX + release.season
        artifact = next(a for a in package['artifacts'] if a['id'] == artifact_id)
        path = _source_path(case['preallocation']['path'])
        if (registry.sha256_file(path) != case['preallocation']['sha256']
                or artifact['sha256'] != case['preallocation']['sha256']):
            raise ValueError('source roster selection preallocation changed')
        original = pipeline.read_json_file(path)
        cohort = full._source_rows(original, case['source_selector'])
        source_club = dict(club, name=cohort['selector']['club_name'], full_name=cohort['selector']['club_name'])
        capture, raw_proof = source.bound_annual_capture(release, source_club, original, path.parent)
        if any(capture.get(k) != cohort['selector'].get(k)
               for k in ('country_catalog', 'competition_catalog', 'club_name', 'source_path', 'source_sha256')):
            raise ValueError('source selection annual capture is not the exact cohort selector')
        lineup = pipeline.read_json_file(path.parent / 'opening-lineups.json')
        matches = [m for m in lineup['clubs'] if all(m['source_selector'].get(k) == cohort['selector'].get(k)
                   for k in ('country_catalog', 'competition_catalog', 'club_name'))]
        if len(matches) != 1:
            raise ValueError('source selection needs one exact original opening fixture')
        opening_proof = source.opening.verify_opening(matches[0], lineup, path.parent / 'cache')
        _verify_selection_fixture_year(release.season, cohort['selector']['country_catalog'],
            matches[0].get('source_competition_code'), opening_proof['date'])
        if opening_proof['date'] != cohort['opening_fixture_date']:
            raise ValueError('source selection opening fixture date differs')
        _, _, before = _roster_rows(eq, club['carrier_id'], {'policy': SOURCE_SELECTION})
        player_index = {p['id']: p for p in package['players']}
        actors = [player_index[id] for id in club['roster_player_ids']]
        if len(actors) != len(before) or [p['carrier_id'] for p in actors] != [id for id, flag in before]:
            raise ValueError('source roster selection recipe actors differ')
        positive = [p for p in actors if p.get('policy') != 'preserve-existing-mode1'
                    and (p['carrier_id'], 0) in before
                    and any(full._matches(p, row) for row in cohort['players'])]
        subset = copy.deepcopy(package)
        subset['players'] = positive
        subset_club = copy.deepcopy(club)
        subset_club['roster_player_ids'] = [p['id'] for p in positive]
        bindings = full._bind_cohort(subset, subset_club, cohort, require_all=True,
            expected_artifact_id=artifact_id, owners=owners,
            native_players=full._native_jug_identity_index(jug, [p['carrier_id'] for p in positive]))
        full._assert_unique_source_cohort(original, cohort, positive, full.club_group(club))
        supported = {r['native_player_carrier_id'] for r in bindings}
        source_rows = {r['source_row_index']: r for r in cohort['players']}
        profile_proofs = []
        for binding in bindings:
            row = source_rows[binding['source_row_index']]
            payload = jug_entries[binding['native_player_carrier_id']].decode_payload(jug)
            parsed = source.rosters.native_player(payload, binding['native_player_carrier_id'])
            end = parsed['name_end']
            born = date(int.from_bytes(bytes(b ^ 0x61 for b in payload[end+14:end+16]), 'little'),
                        payload[end+13] ^ 0x61, payload[end+12] ^ 0x61).isoformat()
            if row['facts'].get('birth_date') and born != row['facts']['birth_date']:
                raise ValueError('source selection native birthday differs from original person')
            if row.get('opening_xi_origin') != 'profiled-first-fixture-addition':
                if row['facts'] not in capture['players']:
                    raise ValueError('source selection annual row differs from reparsed capture')
                continue
            ident = row['opening_source_player_id']
            persons = pipeline.read_json_file(path.parent / 'opening-lineup-person-evidence.json')
            urls = [r['url'] for r in persons['source']['cache_files']
                    if r['url'].rstrip('/').endswith('/spieler/' + ident)]
            if len(urls) != 1 or ident not in opening_proof['starting_xi']:
                raise ValueError('source selection profiled addition lacks original first-XI identity')
            body, proof = source.opening.verified_page(path.parent / 'person-cache', persons['source']['cache_files'], urls[0])
            facts = source._profile_facts(body, player={'source_player_id': ident})
            if (facts.get('published_birth_date') != born
                    or source.identity.key(facts['published_full_name']) != source.identity.key(heading_name(row['facts']['name']))):
                raise ValueError('source selection original profile identity differs')
            profile_proofs.append(proof)
        xi = {source_rows[r['source_row_index']].get('opening_xi_order'): r['native_player_carrier_id']
              for r in bindings if source_rows[r['source_row_index']].get('opening_xi_order') in range(1, 12)}
        if (len(supported) < 16 or set(xi) != set(range(1, 12))
                or not cohort.get('opening_xi_complete')):
            raise ValueError('source selection needs 16 active supported survivors and the complete sourced XI')
        if {source_rows[r['source_row_index']].get('opening_source_player_id') for r in bindings
                if r['native_player_carrier_id'] in set(xi.values())} != set(opening_proof['starting_xi']):
            raise ValueError('source selection protected XI differs from reparsed original report')
        removed = case['removed_player_carrier_ids']
        if (not removed or len(set(removed)) != len(removed)
                or any(type(id) is not int for id in removed)
                or set(removed) & supported):
            raise ValueError('source selection cannot remove a supported person')
        by_id = {p['carrier_id']: p for p in actors}
        if any(id not in by_id or by_id[id].get('policy') != 'preserve-existing-mode1'
               or before.count((id, 0)) != 1 for id in removed):
            raise ValueError('only explicit flag-zero whole-actor seed links may be omitted')
        # Bind any independently reviewed historical disposition too. It is not
        # inferred from absence in this cohort, nor needed to select a roster.
        for evidence in case.get('decision_evidence', []):
            if registry.sha256_file(_source_path(evidence['path'])) != evidence['sha256']:
                raise ValueError('source selection decision evidence changed')
        reviews.append(dict(case_id=case['id'], club_id=club['id'],
            club_carrier_id=club['carrier_id'], native_roster_before=[list(row) for row in before],
            removed_player_carrier_ids=removed, supported_native_ids=sorted(supported),
            sourced_xi_native_ids=[xi[i] for i in range(1, 12)],
            source_bindings=bindings, raw_source_proof=raw_proof,
            original_opening=opening_proof, original_profile_additions=profile_proofs))
    result = dict(schema=SCHEMA, policy=SOURCE_SELECTION, season=release.season,
        release_id=release.release_id, package_sha256=registry.sha256_file(release.package_path),
        package_canonical_sha256=digest(packages.canonical_json_bytes(package)),
        jug_sha256=digest(jug), eq_sha256=digest(eq), fixed_cases=cases, reviews=reviews,
        scope='Explicit seed roster-link omissions after positive target-season source selection; all sourced XI, at least16 active source-supported players, every JUG byte/player object/portrait, retained opaque flag-one rows and other native club links preserved. Omission alone is not a duplicate, retirement or ownership finding.')
    if any(a['id'].startswith(PREFIX) for a in package['artifacts']):
        result['layer_suffix'] = result['package_sha256'][:12]
    groups(result)
    return result


def filename(plan):
    suffix = plan.get('layer_suffix', '')
    return 'sourced-profile-assignment-pruning' + ('-' + suffix if suffix else '') + '.json'


def artifact_id(plan):
    suffix = plan.get('layer_suffix', '')
    return PREFIX + plan['season'] + ('-' + suffix if suffix else '')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(release, cases):
    cases = sorted(copy.deepcopy(cases), key=lambda c: c['id'])
    if not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('pruning needs unique nonempty fixed cases')
    if any(c.get('policy') == SOURCE_SELECTION for c in cases):
        return _prepare_source_selection(release, cases)
    reviews = []
    for case in cases:
        try:
            review = source.prepare(release, case)
        except ValueError as exc:
            if str(exc) != 'annual unknown-DOB row lacks identical original match shirt':
                raise
            review = source.prepare(release, case, numeric_annual=True)
        reviews.append(review)
    if any(r['removed_is_current_native_starter'] for r in reviews):
        raise ValueError('reserve policy cannot remove a native starter')
    removed = [r['removed_player']['carrier_id'] for r in reviews]
    retained = [r['retained_player']['carrier_id'] for r in reviews]
    if len(set(removed)) != len(removed) or set(removed) & set(retained):
        raise ValueError('duplicate or overlapping pruning identities')
    result = dict(schema=SCHEMA, season=release.season, release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),
        package_canonical_sha256=digest(packages.canonical_json_bytes(pipeline.read_json_file(release.package_path))),
        jug_sha256=registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
        eq_sha256=registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
        fixed_cases=cases, reviews=reviews,
        scope='Remove only source-proved duplicate reserve roster links and recipe assignments; every native player, startup order, skill, fact, manager, tactic and asset unchanged.')
    if any(a['id'].startswith(PREFIX) for a in pipeline.read_json_file(release.package_path)['artifacts']):
        result['layer_suffix'] = result['package_sha256'][:12]
    return result


def verify(release, plan):
    if plan.get('schema') != SCHEMA or prepare(release, plan['fixed_cases']) != plan:
        raise ValueError('original reserve assignment proof no longer reproduces')


def groups(plan):
    if plan.get('schema') != SCHEMA or not plan.get('reviews'):
        raise ValueError('unsupported reserve assignment pruning plan')
    if plan.get('policy') == SOURCE_SELECTION:
        result = {}
        for review in plan['reviews']:
            cid = review['club_carrier_id']
            before = [tuple(row) for row in review['native_roster_before']]
            supported = set(review['supported_native_ids'])
            xi = review['sourced_xi_native_ids']
            removed = review['removed_player_carrier_ids']
            if (len(supported) < 16 or len(xi) != 11 or len(set(xi)) != 11
                    or not set(xi) <= supported or not removed
                    or len(set(removed)) != len(removed) or set(removed) & supported
                    or any(before.count((id, 0)) != 1 for id in supported | set(removed))):
                raise ValueError('source roster selection protected cohort/preimage differs')
            group = result.setdefault(cid, dict(before=before, removed=[]))
            if group['before'] != before or set(group['removed']) & set(removed):
                raise ValueError('source roster selection repeated or inconsistent removals')
            group['removed'].extend(removed)
        for group in result.values():
            group['after'] = [row for row in group['before'] if row[0] not in set(group['removed'])]
            if len(group['after']) < 16:
                raise ValueError('source roster selection violates minimum roster size')
        return result
    groups = {}
    removed_all, kept_all = set(), set()
    for r in plan['reviews']:
        bad, keep = r['removed_player'], r['retained_player']
        if (r.get('schema') not in (source.SCHEMA, source.NUMERIC_SCHEMA) or not r.get('duplicate_input_assignment_proved')
                or r.get('removed_is_current_native_starter') is not False
                or r['native_before'][str(bad['carrier_id'])]['startup_order'] <= 11
                or r['season'] != plan['season'] or r['release_id'] != plan['release_id']
                or any(r[k] != plan[k] for k in ('package_sha256', 'jug_sha256', 'eq_sha256'))
                or bad['carrier_id'] == keep['carrier_id'] or bad['carrier_id'] in removed_all):
            raise ValueError('unapproved reserve removal or mismatched baseline')
        removed_all.add(bad['carrier_id'])
        kept_all.add(keep['carrier_id'])
        g = groups.setdefault(r['club_carrier_id'], dict(before=r['native_roster_before'], removed=[]))
        if g['before'] != r['native_roster_before']:
            raise ValueError('same club has inconsistent native roster preimages')
        g['removed'].append(bad['carrier_id'])
    if removed_all & kept_all:
        raise ValueError('a retained identity is also marked for removal')
    for g in groups.values():
        g['before'] = [tuple(r) for r in g['before']]
        if any(g['before'].count((id, 0)) != 1 for id in g['removed']):
            raise ValueError('exact reserve roster link missing or repeated')
        g['after'] = [r for r in g['before'] if r[0] not in set(g['removed'])]
        if len(g['after']) < 16:
            raise ValueError('pruning would violate capacity-fitting matchday minimum')
    return groups


def apply(jug, eq, plan):
    reviewed = groups(plan)
    if digest(jug) != plan['jug_sha256']:
        raise ValueError('reserve pruning cannot change or substitute the native player file')
    replacements, states = {}, []
    index = None
    for club_id, g in reviewed.items():
        index, raw, rows = _roster_rows(eq, club_id, plan)
        if rows == g['before']:
            states.append('before')
            changed = _prune(raw, g, plan)
            replacements[club_id] = compiler.xor_decode(changed)
        elif rows == g['after']:
            states.append('after')
        else:
            raise ValueError('reserve roster preimage differs')
    if len(set(states)) != 1:
        raise ValueError('partially applied reserve batch is not an approved preimage')
    if replacements and digest(eq) != plan['eq_sha256']:
        raise ValueError('whole club database preimage differs')
    if not replacements:
        # Idempotence accepts only the exact complete postimage, not a game
        # with matching target rows but unrelated edits hidden elsewhere.
        baseline = registry.load_registered_release(plan['season'], plan['release_id'])
        original = (baseline.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
        if digest(original) != plan['eq_sha256']:
            raise ValueError('immutable reserve pruning baseline changed')
        expected_replacements = {}
        for club_id, g in reviewed.items():
            original_index, raw, rows = _roster_rows(original, club_id, plan)
            if rows != g['before']:
                raise ValueError('immutable reserve roster baseline changed')
            changed = _prune(raw, g, plan)
            expected_replacements[club_id] = compiler.xor_decode(changed)
        expected = compiler._rebuild_indexed(original, original_index, expected_replacements)
        if eq != expected:
            raise ValueError('reserve pruning postimage has unrelated native changes')
    result = compiler._rebuild_indexed(eq, index, replacements) if replacements else eq
    preserve_other_records(eq, result, set(reviewed))
    for club_id, g in reviewed.items():
        if _roster_rows(result, club_id, plan)[2] != g['after']:
            raise ValueError('pruning readback differs from exact approved roster')
    return jug, result


def _prune(raw, group, plan):
    options = ({'preserve_unselected_flag_one': True}
               if plan.get('policy') == SOURCE_SELECTION else {})
    return prune_visible_mode1_roster_payload(raw, expected_rows=group['before'],
        removed_player_ids=group['removed'], **options)


def bind(package, plan):
    groups(plan)
    if digest(packages.canonical_json_bytes(package)) != plan['package_canonical_sha256']:
        raise ValueError('whole reserve recipe preimage differs')
    result = copy.deepcopy(package)
    removed_ids = set()
    if plan.get('policy') == SOURCE_SELECTION:
        players = {p['id']: p for p in result['players']}
        for review in plan['reviews']:
            club = next(c for c in result['clubs'] if c['id'] == review['club_id'])
            if club['carrier_id'] != review['club_carrier_id']:
                raise ValueError('source roster selection recipe club differs')
            removed = set(review['removed_player_carrier_ids'])
            selected = [id for id in club['roster_player_ids'] if players[id]['carrier_id'] in removed]
            if len(selected) != len(removed):
                raise ValueError('source roster selection recipe removal differs')
            opening = club.get('opening', {})
            if set(selected) & set(opening.get('starting_xi_player_ids', []) + opening.get('substitute_player_ids', [])):
                raise ValueError('source roster selection cannot remove an explicitly selected XI or substitute')
            club['roster_player_ids'] = [id for id in club['roster_player_ids'] if id not in selected]
            if 'shared_preserve_player_ids' in club:
                club['shared_preserve_player_ids'] = [id for id in club['shared_preserve_player_ids'] if id not in selected]
        # Retained opaque seed records remain declared, even if now unrostered.
        # Neither retirement nor historical owner is inferred for those objects.
        return _bind_artifact(result, plan)
    for r in plan['reviews']:
        bad, keep = r['removed_player'], r['retained_player']
        for expected in (bad, keep):
            actual = [p for p in result['players'] if p['id'] == expected['id']]
            if actual != [expected]:
                raise ValueError('reserve recipe person preimage differs')
        clubs = [c for c in result['clubs'] if bad['id'] in c['roster_player_ids']]
        if (len(clubs) != 1 or clubs[0]['id'] != r['club_id']
                or clubs[0]['carrier_id'] != r['club_carrier_id']
                or keep['id'] not in clubs[0]['roster_player_ids']
                or bad['id'] in clubs[0].get('starting_xi_player_ids', [])):
            raise ValueError('reserve recipe owner or opening XI differs')
        clubs[0]['roster_player_ids'].remove(bad['id'])
        if 'shared_preserve_player_ids' in clubs[0]:
            clubs[0]['shared_preserve_player_ids'] = [id for id in clubs[0]['shared_preserve_player_ids'] if id != bad['id']]
        removed_ids.add(bad['id'])
    result['players'] = [p for p in result['players'] if p['id'] not in removed_ids]
    for owner in (result, result.get('assets', {})):
        if 'portraits' in owner:
            owner['portraits'] = [p for p in owner['portraits'] if p['player_id'] not in removed_ids]
    return _bind_artifact(result, plan)


def _bind_artifact(result, plan):
    id = artifact_id(plan)
    if any(a['id'] == id for a in result['artifacts']):
        raise ValueError('reserve assignment layer already present')
    result['artifacts'].append(dict(id=id, kind='season-input', relative_path=filename(plan),
        sha256=digest(packages.canonical_json_bytes(plan)), media_type='application/json'))
    result['artifacts'].sort(key=lambda a: a['id'])
    packages.validate_package(result)
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('reserve pruning recipe requires source-bound reconstruction; factory compilation must not drop this layer')


def reconstruction(previous, release_id):
    if not getattr(previous, 'locator', {}).get('sourced_profile_assignment_plan_path'):
        return None
    from scripts import publish_historical_role_delta_v1 as publisher
    package = pipeline.read_json_file(previous.package_path)
    path = registry.ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(path)
    from scripts import season_authored_country_delta_v1 as authored_country
    from scripts import season_authored_country_delta_v2 as authored_country_v2
    from scripts import season_authored_player_roles_v1 as authored_player_roles
    if plan.get('schema') == authored_player_roles.SCHEMA:
        return authored_player_roles.reconstruction(previous, release_id)
    if plan.get('schema') == authored_country_v2.SCHEMA:
        return authored_country_v2.reconstruction(previous, release_id)
    if plan.get('schema') == authored_country.SCHEMA:
        return authored_country.reconstruction(previous, release_id)
    from scripts import season_source_bound_reserve_transfer_v1 as reserve_transfer
    if plan.get('schema') == reserve_transfer.SCHEMA:
        return reserve_transfer.reconstruction(previous, release_id)
    from scripts import season_source_bound_fixture_membership_v1 as fixture_membership
    if plan.get('schema') == fixture_membership.PROFILE_SCHEMA:
        return fixture_membership.reconstruction(previous, release_id)
    from scripts import season_source_bound_birthday_disagreements_v1 as birthdays
    if plan.get('schema') == birthdays.SCHEMA:
        return birthdays.reconstruction(previous, release_id)
    from scripts import season_source_bound_shirt_numbers_v1 as shirts
    if plan.get('schema') == shirts.SCHEMA:
        return shirts.reconstruction(previous, release_id)
    from scripts import season_arsenal_2021_owned_opening_v1 as arsenal
    if plan.get('schema') == arsenal.SCHEMA:
        return arsenal.reconstruction(previous, release_id)
    from scripts import season_quality_only_delta_v1 as quality_only
    if plan.get('schema') == quality_only.SCHEMA:
        return quality_only.reconstruction(previous, release_id)
    from scripts import season_city_2024_opening_exchange_v1 as city
    if plan.get('schema') == city.SCHEMA:
        return city.reconstruction(previous, release_id)
    from scripts import season_woking_2003_owned_opening_v1 as woking
    if plan.get('schema') == woking.SCHEMA:
        return woking.reconstruction(previous, release_id)
    from scripts import season_source_bound_duplicate_opening_v1 as opening
    if plan.get('schema') == opening.SCHEMA:
        return opening.reconstruction(previous, release_id)
    from scripts import season_source_bound_namesake_dates_v1 as dates
    if plan.get('schema') == dates.SCHEMA:
        return dates.reconstruction(previous, release_id)
    from scripts import season_original_secondary_facts_v1 as secondary_facts
    if plan.get('schema') == secondary_facts.SCHEMA:
        return secondary_facts.reconstruction(previous, release_id)
    from scripts import season_stevenage_opening_repair_v1 as stevenage
    if plan.get('schema') == stevenage.SCHEMA:
        return stevenage.reconstruction(previous, release_id)
    from scripts import season_boreham_opening_repair_v1 as boreham
    if plan.get('schema') == boreham.SCHEMA:
        return boreham.reconstruction(previous, release_id)
    from scripts import season_barrow_opening_repair_v1 as barrow
    if plan.get('schema') == barrow.SCHEMA:
        return barrow.reconstruction(previous, release_id)
    if path.resolve() != (previous.package_path.parent / filename(plan)).resolve():
        raise ValueError('reserve pruning replay locator is not the exact local layer')
    artifacts = [a for a in package['artifacts'] if a['id'] == artifact_id(plan)]
    if len(artifacts) != 1 or artifacts[0]['relative_path'] != filename(plan):
        raise ValueError('reserve pruning replay requires one exact current layer')
    if registry.sha256_file(path) != artifacts[0]['sha256']:
        raise ValueError('reserve pruning replay artifact changed')
    baseline = registry.load_registered_release(previous.season, plan['release_id'])
    verify(baseline, plan)
    if packages.canonical_json_bytes(bind(pipeline.read_json_file(baseline.package_path), plan)) != packages.canonical_json_bytes(package):
        raise ValueError('edited recipe cannot use exact reserve pruning replay; no edits discarded')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    expected = dict(season=previous.season, release_id=baseline.release_id,
        package_sha256=registry.sha256_file(baseline.package_path),
        jug_sha256=registry.sha256_file(baseline.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
    if pipeline.read_json_file(descriptor) != expected:
        raise ValueError('reserve pruning replay descriptor differs')
    for release in (baseline, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    publisher.publish(previous.season, descriptor, release_id=release_id,
        profile_assignment_plan_path=path, source_release_id=baseline.release_id)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if packages.canonical_json_bytes(pipeline.read_json_file(rebuilt.package_path)) != packages.canonical_json_bytes(package):
        raise ValueError('reserve pruning replay recipe differs')
    return dict(season=previous.season, release_id=release_id, source_release_id=baseline.release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True, reused=False,
        compilation_mode=('source-bound-reviewed-roster-selection-known-good-reconstruction-not-factory-compile'
            if plan.get('policy') == SOURCE_SELECTION else
            'source-bound-reserve-assignment-known-good-reconstruction-not-factory-compile'))
