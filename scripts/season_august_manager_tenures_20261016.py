"""Admit original August1 coach histories, never following-year match coaches.

Each target is joined to the earlier country-scoped exact club capture, its
original fixture pages, original raw tenure page and original download body.
Ambiguous canonical identities remain deferred. No writes or source fetching.
"""
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_cached_manager_repairs_20261016 as old
from scripts import audit_deferred_manager_tenures_20261016 as histories
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from scripts.backfill_exact_opening_club_aliases_v1 import unique_capture
from scripts.season_package_display_alias_repair_v1 import _portable_source_text

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/august-manager-tenures-v1'
AUDIT = histories.ROOT / 'deferred-tenure-source-audit-v2.json'
POLICY = 'original-August1-tenure-with-positive-exact-club-and-download-receipt-v1'


def checked_json(path, sha):
    if registry.sha256_file(path) != sha:
        raise ValueError('bound source document changed')
    return pipeline.read_json_file(path)


def noncolliding(package, updates):
    """Full-name collisions need coupled owner/person proofs, not a new alias."""
    selected = list(updates); deferred = []
    while selected:
        proposed = {r['manager_id']: r for r in selected}
        names = defaultdict(list)
        for manager in package['managers']:
            name = proposed[manager['id']]['after'] if manager['id'] in proposed else manager['name']
            names[old.opening._normalise(name)].append(manager['id'])
        blocked = {mid for ids in names.values() if len(ids) > 1 for mid in ids if mid in proposed}
        if not blocked:
            break
        deferred.extend(dict(club_id=r['club_id'], club=r['club'], proposed=r['after'],
            reason='canonical full name already belongs to another coach slot; separate dated source-person reconciliation required')
            for r in selected if r['manager_id'] in blocked)
        selected = [r for r in selected if r['manager_id'] not in blocked]
    return selected, deferred


def prepare(base):
    source_audit = pipeline.read_json_file(AUDIT)
    if source_audit['original_deferred'] != 85:
        raise ValueError('original deferred denominator changed')
    cases = [r for r in source_audit['rows'] if r['season'] == base.season
        and r['status'] == 'unanimous-reparsed-August1-tenure-candidate'
        and any(c['original_download_receipt_verified'] for c in r['claims'])]
    package = pipeline.read_json_file(base.package_path)
    clubs = {c['id']: c for c in package['clubs']}
    managers = {m['id']: m for m in package['managers']}
    report_path = old.REVIEWS / base.season / 'opening-review.json'
    report = pipeline.read_json_file(report_path)
    if report['season'] != base.season or report['schema_version'] != old.opening.SCHEMA:
        raise ValueError('wrong original club opening report')
    allowed = old.exclusive_source_clubs(report['clubs'])
    capture_path = registry.ROOT / report['bindings']['opening_capture_path']
    capture = checked_json(capture_path, report['bindings']['opening_capture_sha256'])
    reports = {r['club_id']: r for r in report['clubs']}
    receipts = histories.receipt_index()
    holders, native_names = _manager_graph(eq_path=base.game_path / 'DBDAT/EQ98030.FDI',
        ent_path=base.game_path / 'DBDAT/ENT98030.FDI')
    updates = []; unresolved = []
    for case in cases:
        club = clubs[case['club_id']]; manager = managers[club['manager_id']]
        try:
            original = checked_json(registry.ROOT / case['decision_path'], case['decision_sha256'])
            deferred = [d['row'] for d in original['deferred'] if d['row']['club_id'] == club['id']]
            if len(deferred) != 1:
                raise ValueError('original deferred case must join exactly once')
            prior = deferred[0]; opening_row = reports[club['id']]
            if (club['name'], club['carrier_id'], manager['id'], manager['carrier_id']) != (
                    prior['club'], prior['club_carrier_id'], prior['manager_id'], prior['carrier_id']):
                raise ValueError('actual club or native coach slot differs from original exact-club target')
            if opening_row['club'] != club['name'] or club['id'] not in allowed:
                raise ValueError('source club has ambiguous or changed native representation')
            captured = unique_capture(club, capture['clubs'])
            if captured is None:
                raise ValueError('no unique positive country-scoped captured club')
            original_fixture = old.opening.verify_opening(captured, capture, capture_path.parent / 'cache')
            if original_fixture != prior['evidence'] or int(original_fixture['source_club_id']) != int(case['source_club_id']):
                raise ValueError('original fixture club identity no longer independently reparses')
            at = date(int(base.season[:4]), 8, 1)
            identities = set(); checked = []
            for claim in case['claims']:
                raw = registry.ROOT / claim['path']
                if registry.sha256_file(raw) != claim['sha256']:
                    raise ValueError('original tenure raw bytes changed')
                parsed = histories.tenure(raw.read_bytes(), case['source_club_id'], at)
                if any(parsed[k] != claim[k] for k in ('manager', 'source_manager_id', 'source_url', 'date')):
                    raise ValueError('original tenure does not reparse to saved identity/date')
                identities.add((parsed['manager'], parsed['source_manager_id']))
                witnesses = receipts.get((case['source_club_id'], claim['sha256']), [])
                if claim['original_download_receipt_verified']:
                    for witness in claim['download_receipts']:
                        checked_json(registry.ROOT / witness['receipt_path'], witness['receipt_sha256'])
                        if witness not in witnesses or witness['original_download_url'] != parsed['source_url']:
                            raise ValueError('original download receipt body does not bind raw URL/SHA')
                    if not claim['download_receipts']:
                        raise ValueError('no original download body')
                    checked.append(dict(path=claim['path'], sha256=claim['sha256'], url=parsed['source_url']))
            if len(identities) != 1 or not checked:
                raise ValueError('original tenures disagree or lack original download receipts')
            name, person = next(iter(identities))
            alias, method = old.display.short_name(name)
            if alias is None:
                raise ValueError('source coach needs an explicit compound surname alias')
            alias = _portable_source_text(alias)
            owners = [c['carrier_id'] for c in holders.get(manager['carrier_id'], [])]
            if owners != [club['carrier_id']]:
                raise ValueError('actual native coach does not have exclusive target owner')
            updates.append(dict(club_id=club['id'], club_carrier_id=club['carrier_id'], club=club['name'],
                manager_id=manager['id'], carrier_id=manager['carrier_id'], before=manager['name'],
                before_policy=manager.get('policy'), native_before=native_names[manager['carrier_id']],
                after=name, native_after=alias, native_display_basis=method, native_manager_owner_count=1,
                first_fixture_date=at.isoformat(), source_manager_id=person,
                evidence=dict(date=at.isoformat(), source_club_id=case['source_club_id'], manager=name,
                    source_manager_id=person, raw_sources=checked, source_url=checked[0]['url'],
                    authority='published coach tenure covering actual August1, not following-year fixture',
                    original_fixture_used_for_club_identity_only=original_fixture,
                    download_claims=case['claims']),
                source_audit_case=dict(decision_path=case['decision_path'], decision_sha256=case['decision_sha256'])))
        except (ValueError, KeyError) as exc:
            unresolved.append(dict(club_id=club['id'], club=club['name'], reason=str(exc)))
    selected, collisions = noncolliding(package, updates)
    unresolved.extend(collisions)
    return dict(schema_version='pm99-historical-manager-plan-v1', season=base.season,
        release_id=base.release_id, package_sha256=registry.sha256_file(base.package_path),
        eq_sha256=registry.sha256_file(base.game_path / 'DBDAT/EQ98030.FDI'),
        ent_sha256=registry.sha256_file(base.game_path / 'DBDAT/ENT98030.FDI'),
        audit_path=registry.relative_workspace_path(AUDIT), audit_sha256=registry.sha256_file(AUDIT),
        updates=selected, unresolved=unresolved, policy=POLICY,
        independently_reparsed_current_manager_corrections=True,
        implementation_inputs=[dict(path=registry.relative_workspace_path(Path(p)), sha256=registry.sha256_file(Path(p)))
            for p in (__file__, histories.__file__, old.opening.__file__, old.display.__file__)],
        summary=dict(original_receipt_backed_candidates=len(cases), corrections=len(selected),
            mismatches_requiring_further_review=len(unresolved)), historical_verification_complete=False)


def main():
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    ROOT.mkdir(parents=True, exist_ok=True)
    seasons = sorted({r['season'] for r in pipeline.read_json_file(AUDIT)['rows']
        if r['status'] == 'unanimous-reparsed-August1-tenure-candidate'
        and any(c['original_download_receipt_verified'] for c in r['claims'])})
    results = []
    for season in seasons:
        base = registry.load_preferred_release(season)
        plan = prepare(base)
        path = ROOT / season / 'manager-plan.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        retained(path, plan)
        results.append(dict(season=season, **plan['summary'], plan_path=registry.relative_workspace_path(path),
            plan_sha256=registry.sha256_file(path)))
        print(dict(season=season, **plan['summary']), flush=True)
    retained(ROOT / 'source-admission-summary.json', dict(seasons=results,
        original_receipt_backed_candidates=sum(r['original_receipt_backed_candidates'] for r in results),
        admitted=sum(r['corrections'] for r in results), unresolved=sum(r['mismatches_requiring_further_review'] for r in results),
        native_writes=0, manager_cases_closed=0))


if __name__ == '__main__':
    main()
