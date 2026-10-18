"""Admit all remaining36 original coach cases on exact current game owners.

Same full names are not automatically the same person: four Altrincham claims
have independently dated different-person Sunderland/Wrexham witnesses. Recipe
person aliases must nevertheless remain distinct. Unverified seed names never
become certified people by resemblance to the corrected coach.
"""
from collections import defaultdict
import copy
import hashlib
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import remaining_manager_source_package_20261016 as sources
from scripts import season_august_manager_tenures_20261016 as prior
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import coupled_manager_timeline_admission_20261016 as coupled
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from scripts.season_package_display_alias_repair_v1 import _portable_source_text

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/remaining-manager-delivery-v1'
SOURCE = sources.ROOT / 'remaining36-source-package.json'
POLICY = 'remaining-original-August1-managers-primary-conflicts-and-distinct-same-name-people-v1'
COMPACT_ALIASES = {
    'Júlio César Leal': 'J. C. Leal', 'Ivar Morten Normark': 'I. M. Normark',
    'Per Joar Hansen': 'P. J. Hansen', 'Lars Arne Nilsen': 'L. A. Nilsen',
    'Juan Carlos Oblitas': 'J. C. Oblitas',
    'José Luis Mendilibar': 'Mendilibar',
}
_SOURCE_CACHE = None


def source_input_bindings(value):
    """Every consumed original document stays hash-bound when parsing is reused."""
    result = {}
    def walk(node):
        if isinstance(node, dict):
            for path_key, sha_key in (('path','sha256'),('raw_path','raw_sha256'),
                    ('receipt_path','receipt_sha256'),('decision_path','decision_sha256')):
                path, sha = node.get(path_key), node.get(sha_key)
                if isinstance(path,str) and isinstance(sha,str):
                    target = registry.ROOT / path
                    if target in result and result[target] != sha:
                        raise ValueError('same source input has contradictory hash bindings')
                    result[target] = sha
            for child in node.values():
                if isinstance(child,(dict,list)):
                    walk(child)
        elif isinstance(node,list):
            for child in node:
                walk(child)
    walk(value)
    return result


def extra_source_inputs():
    files = [Path(module.__file__) for module in (sources, sources.primary, sources.fresh,
        sources.sunderland, sources.history, sources.history.history, sources.primary.articles,
        coupled, prior.old.opening, prior.old.display)]
    files += [Path(__file__), sources.sunderland.ROOT / 'capture-result.json',
        sources.sunderland.ROOT / '289.html.source.json',
        prior.ROOT / 'phil-parkinson-original-identities.json']
    return files


def verified_sources():
    """Reparse once per process, then rehash originals; never cache native owners.

    This is deterministic memoisation of an already completed original-source
    replay, not approval from a boolean or a skip of changed source evidence.
    """
    global _SOURCE_CACHE
    if _SOURCE_CACHE is None:
        saved = pipeline.read_json_file(SOURCE)
        actual = sources.prepare()
        if actual != saved:
            raise ValueError('remaining36 source package no longer independently reproduces')
        bindings = source_input_bindings(actual)
        bindings[SOURCE] = registry.sha256_file(SOURCE)
        for path in extra_source_inputs():
            digest = registry.sha256_file(path)
            if path in bindings and bindings[path] != digest:
                raise ValueError('extra original source input disagrees with its retained hash')
            bindings[path] = digest
        _SOURCE_CACHE = dict(data=actual, canonical_sha256=pipeline.canonical_json_sha256(actual), inputs=bindings)
    for path, digest in _SOURCE_CACHE['inputs'].items():
        if registry.sha256_file(path) != digest:
            raise ValueError('original source input changed; cached source replay cannot be used')
    if pipeline.canonical_json_sha256(_SOURCE_CACHE['data']) != _SOURCE_CACHE['canonical_sha256']:
        raise ValueError('completed parsed source package was mutated')
    return copy.deepcopy(_SOURCE_CACHE['data'])


def display_name(name):
    alias, method = prior.old.display.short_name(name)
    if alias is None and name in COMPACT_ALIASES:
        # Explicit UI abbreviation only: retain full source identity and do
        # not pretend this establishes the legal extent of a family name.
        return COMPACT_ALIASES[name], 'ROOT-explicit-compact-coach-display-not-legal-family-name-claim'
    return alias, method


def coach_person_alias(name):
    # Keep the established writer's deterministic person aliases. They need
    # not encode a provider ID, but must never collide with a different person.
    return 'manager-historical-' + hashlib.sha256(name.encode()).hexdigest()[:24]


def resolve_collisions(package, updates, holders, native_names, reports):
    proposed = {r['manager_id']: r for r in updates}
    by_name = defaultdict(list); by_person = defaultdict(list); warnings = []
    managers = {m['id']: m for m in package['managers']}
    clubs = {c['manager_id']: c for c in package['clubs']}
    for manager in package['managers']:
        change = proposed.get(manager['id'])
        name = change['after'] if change else manager['name']
        person = coach_person_alias(name) if change else manager.get('person_id')
        by_name[prior.old.opening._normalise(name)].append(manager['id'])
        if person is not None:
            by_person[person].append(manager['id'])
    for ids in by_person.values():
        if len(ids) > 1 and any(mid in proposed for mid in ids):
            raise ValueError('new coach person alias collides with another actual canonical owner: ' +
                '; '.join(clubs[mid]['name'] + ' -> ' + (proposed[mid]['after'] if mid in proposed else managers[mid]['name']) for mid in ids))
    for ids in by_name.values():
        if len(ids) < 2:
            continue
        for mid in ids:
            if mid not in proposed:
                continue
            row = proposed[mid]; peer = row['evidence'].get('same_name_peer')
            if peer is None:
                others = [other for other in ids if other != mid]
                if all(managers[other].get('policy') == 'preserve-existing-mode1'
                        and managers[other].get('person_id') is None for other in others):
                    # A stock label with no reconciled identity is not proof
                    # that the newly sourced person is assigned elsewhere.
                    # Keep its club/identity problem OPEN; never certify it as
                    # a genuine namesake or a second dated coach appointment.
                    warnings.extend(dict(club_id=clubs[other]['id'], club=clubs[other]['name'],
                        manager_id=other, name=managers[other]['name'],
                        reason='unqualified stock name resemblance; native club/roster ownership and manager identity remain open, not a verified second coach')
                        for other in others)
                    continue
                raise ValueError('same-name qualified coach needs positive distinct-person or coupled owner evidence: ' + row['after'] +
                    ' at ' + ', '.join(clubs[other]['name'] for other in ids))
            matched = False
            for other in ids:
                if other == mid:
                    continue
                manager = managers[other]; club = clubs[other]
                if club['name'] == peer['club']:
                    published = reports.get(club['id'], {}).get('evidence', {})
                    if (published.get('source_club_id') != peer['source_club_id']
                            or manager['name'] != peer['manager']
                            or peer['source_manager_id'] == row['source_manager_id']
                            or native_names.get(manager['carrier_id']) not in (manager['name'], row['native_after'])
                            or [c['carrier_id'] for c in holders.get(manager['carrier_id'], [])] != [club['carrier_id']]):
                        raise ValueError('same-name peer source identity or actual native club owner differs')
                    matched = True
                elif manager.get('policy') == 'preserve-existing-mode1' and manager.get('person_id') is None:
                    warnings.append(dict(club_id=club['id'], club=club['name'], manager_id=other,
                        name=manager['name'], reason='unverified inherited same-name placeholder remains open; not certified as either published coach'))
                else:
                    raise ValueError('another same-name canonical coach lacks independent distinct-person owner proof')
            if not matched:
                raise ValueError('published distinct same-name peer is absent from actual recipe/native graph')
    return warnings


def prepare(base):
    source_package = verified_sources()
    claims = [r for r in source_package['claims'] if r['season'] == base.season]
    package = pipeline.read_json_file(base.package_path)
    clubs = {c['id']: c for c in package['clubs']}; managers = {m['id']: m for m in package['managers']}
    report_path = prior.old.REVIEWS / base.season / 'opening-review.json'
    report = pipeline.read_json_file(report_path); reports = {c['club_id']: c for c in report['clubs']}
    if report['season'] != base.season or report['schema_version'] != prior.old.opening.SCHEMA:
        raise ValueError('original exact-club review identity differs')
    allowed = prior.old.exclusive_source_clubs(report['clubs'])
    capture_path = registry.ROOT / report['bindings']['opening_capture_path'] if claims else None
    capture = prior.checked_json(capture_path, report['bindings']['opening_capture_sha256']) if claims else None
    holders, native_names = _manager_graph(eq_path=base.game_path / 'DBDAT/EQ98030.FDI',
        ent_path=base.game_path / 'DBDAT/ENT98030.FDI')
    updates = []
    for claim in claims:
        club = clubs[claim['club_id']]; manager = managers[club['manager_id']]
        original = claim['original_deferred_case']
        decision = prior.checked_json(registry.ROOT / original['decision_path'], original['decision_sha256'])
        rows = [d['row'] for d in decision['deferred'] if d['row']['club_id'] == club['id']]
        if len(rows) != 1:
            raise ValueError('original deferred target must join once')
        old = rows[0]
        if (club['name'], club['carrier_id'], manager['id'], manager['carrier_id']) != (
                old['club'], old['club_carrier_id'], old['manager_id'], old['carrier_id']):
            raise ValueError('actual native club or manager slot changed from original source target')
        if club['id'] not in allowed or reports[club['id']]['club'] != club['name']:
            raise ValueError('original club identity has ambiguous native representations')
        captured = prior.unique_capture(club, capture['clubs'])
        if captured is None:
            raise ValueError('positive country-scoped exact captured club missing')
        fixture = prior.old.opening.verify_opening(captured, capture, capture_path.parent / 'cache')
        if fixture != old['evidence'] or fixture['source_club_id'] != claim['source_club_id']:
            raise ValueError('original numerical fixture club identity no longer independently reparses')
        if claim['date'] != base.season[:4] + '-08-01':
            raise ValueError('coach authority must cover actual target August1')
        if [c['carrier_id'] for c in holders.get(manager['carrier_id'], [])] != [club['carrier_id']]:
            raise ValueError('actual native manager slot is not exclusively owned by target club')
        alias, method = display_name(claim['manager'])
        if alias is None:
            raise ValueError('source manager needs explicit supported compound native alias')
        alias = _portable_source_text(alias)
        updates.append(dict(club_id=club['id'], club_carrier_id=club['carrier_id'], club=club['name'],
            manager_id=manager['id'], carrier_id=manager['carrier_id'], before=manager['name'],
            before_policy=manager.get('policy'), native_before=native_names[manager['carrier_id']],
            after=claim['manager'], native_after=alias, native_display_basis=method, native_manager_owner_count=1,
            first_fixture_date=claim['date'], source_manager_id=claim['source_manager_id'],
            evidence=dict(date=claim['date'], manager=claim['manager'], source_manager_id=claim['source_manager_id'],
                source_club_id=claim['source_club_id'], source_url=claim['source_url'], raw_sources=claim['raw_sources'],
                authority=claim['source_policy'], original_fixture_used_for_club_identity_only=fixture,
                primary_resolution=claim['primary_resolution'], same_name_peer=claim['same_name_peer']),
            original_deferred_case=original))
    extra_rows, compatible, source_gaps = coupled.claims_for(base, package, native_names,
        {r['club_id']: r for r in updates}, display_name)
    for extra in extra_rows:
        club, manager, claim = extra['club'], extra['manager'], extra['claim']
        if [c['carrier_id'] for c in holders.get(manager['carrier_id'], [])] != [club['carrier_id']]:
            raise ValueError('additional coupled native coach owner is not exclusive')
        updates.append(dict(club_id=club['id'], club_carrier_id=club['carrier_id'], club=club['name'],
            manager_id=manager['id'], carrier_id=manager['carrier_id'], before=manager['name'],
            before_policy=manager.get('policy'), native_before=native_names[manager['carrier_id']],
            after=claim['manager'], native_after=_portable_source_text(extra['alias']),
            native_display_basis=extra['alias_method'], native_manager_owner_count=1,
            first_fixture_date=claim['date'], source_manager_id=claim['source_manager_id'],
            evidence=dict(date=claim['date'], manager=claim['manager'], source_manager_id=claim['source_manager_id'],
                source_club_id=extra['source']['source_club_id'], source_url=claim['source_url'],
                raw_sources=[dict(path=extra['source']['path'], sha256=extra['source']['sha256'], url=extra['source']['url'])],
                authority='positive-original-coupled-club-August1-history', same_name_peer=None,
                club_entity_admission=extra['entity_admission'], original_download=extra['source']),
            original_deferred_case=None))
    warnings = resolve_collisions(package, updates, holders, native_names, reports)
    plan = dict(schema_version='pm99-historical-manager-plan-v1', season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path), eq_sha256=registry.sha256_file(base.game_path / 'DBDAT/EQ98030.FDI'),
        ent_sha256=registry.sha256_file(base.game_path / 'DBDAT/ENT98030.FDI'),
        audit_path=registry.relative_workspace_path(SOURCE), audit_sha256=registry.sha256_file(SOURCE),
        updates=updates, unresolved=[], broader_unverified_warnings=warnings, policy=POLICY,
        compatible_coupled_coaches_unchanged=compatible, coupled_club_source_gaps=source_gaps,
        independently_reparsed_current_manager_corrections=True,
        implementation_inputs=[dict(path=registry.relative_workspace_path(Path(p)), sha256=registry.sha256_file(Path(p)))
            for p in (__file__, sources.__file__, sources.primary.__file__, coupled.__file__, prior.old.opening.__file__, prior.old.display.__file__)],
        summary=dict(original_deferred_cases=len(claims), corrections=len(updates),
            additional_coupled_club_changes=len(extra_rows), compatible_coaches_unchanged=len(compatible),
            coupled_club_source_gaps=len(source_gaps),
            canonical_label_changes=sum(r['before'] != r['after'] for r in updates),
            visible_native_name_changes=sum(r['native_before'] != r['native_after'] for r in updates),
            broader_unverified_warnings=len(warnings), mismatches_requiring_further_review=0),
        historical_verification_complete=False)
    inert = dict(season=base.season, release_id=base.release_id, package_sha256=plan['package_sha256'],
        jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
    # Exercise the actual recipe writer before any native build; this catches
    # canonical alias collisions rather than merely comparing name spellings.
    if updates:
        publisher.updated_package(package, inert, manager_plan=plan)
    return plan


def main():
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    from scripts import build_august_manager_tenures_20261016 as previous
    admission = pipeline.read_json_file(prior.ROOT / 'source-admission-summary.json')
    previous_seasons = {r['season'] for r in admission['seasons'] if r['corrections']}
    delivered = pipeline.read_json_file(prior.ROOT / 'final-delivery-summary.json')
    if (delivered['state'] != 'delivered-native-SOURCE-and-runner-verified'
            or delivered['canonical_updates'] != 49 or delivered['deferred_remaining'] != 36):
        raise ValueError('previous49 must actually be delivered before this source batch')
    verified_sources()  # one complete source replay; each season still checks input hashes
    seasons = registry.supported_seasons()
    plans = []; failures = []
    # Validate the entire source/native set first; a later failure must not
    # leave a mixture of frozen plans from different source implementations.
    for season in seasons:
        base = (registry.load_registered_release(season, previous.RELEASE) if season in previous_seasons
            else registry.load_preferred_release(season))
        try:
            plan = prepare(base)
        except ValueError as exc:
            failure = dict(season=season, source_parent=base.release_id, error=str(exc), native_writes=0,
                manager_cases_closed=0, approved=False)
            failures.append(failure)
            print(failure, flush=True)
            continue
        plans.append(plan)
        print(dict(season=season, **plan['summary'], native_writes=0), flush=True)
    if failures:
        # Inspect every independent season before returning the next repair
        # queue. Never discard later failures by stopping at the first one.
        from datetime import UTC, datetime
        diagnostic = sources.ROOT / ('admission-failures-' + datetime.now(UTC).strftime('%H%M%S') + '.json')
        pipeline.write_canonical_json(diagnostic, dict(failures=failures,
            independently_admissible_seasons=[p['season'] for p in plans], native_writes=0,
            frozen_plans_written=0, scope='Unapproved diagnostic only; no game builds or case closures.'))
        raise ValueError('source admission failed in ' + str(len(failures)) + ' seasons; inspect ' + str(diagnostic))
    if sum(p['summary']['original_deferred_cases'] for p in plans) != 36:
        raise ValueError('all original remaining36 cases must be admitted or explicitly blocked')
    ROOT.mkdir(parents=True, exist_ok=True); rows = []
    for plan in plans:
        path = ROOT / plan['season'] / ('manager-plan.json' if plan['updates'] else 'no-change-source-review.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        retained(path, plan)
        rows.append(dict(season=plan['season'], **plan['summary'], source_parent=plan['release_id'],
            source_plan=dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))))
    retained(ROOT / 'source-admission-summary.json', dict(seasons=rows,
        original_deferred_cases_admitted=36, admitted_cases=sum(len(p['updates']) for p in plans),
        additional_coupled_club_changes=sum(p['summary']['additional_coupled_club_changes'] for p in plans),
        pending_prior49_publication=False, prior49_delivery=delivered['checklist'], native_writes=0, manager_cases_closed=0,
        canonical_label_changes=sum(p['summary']['canonical_label_changes'] for p in plans),
        visible_native_name_changes=sum(p['summary']['visible_native_name_changes'] for p in plans),
        broader_unverified_warnings=[w for p in plans for w in p['broader_unverified_warnings']]))


if __name__ == '__main__':
    main()
