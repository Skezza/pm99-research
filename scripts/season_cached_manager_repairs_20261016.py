"""Reparse cached exact-club first fixtures for real current manager mistakes.

No new scrape or game write. An old mismatch label is not authority: both the
original schedule/report and actual current exclusive ENT owner are reread.
Full canonical identity and bounded native display alias remain separate.
"""
import collections
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_manager_display_repair_v1 as display
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from scripts.capture_ntf_historical_carrier_squads_v1 import CALENDAR_YEAR_COUNTRIES
from scripts.backfill_exact_opening_club_aliases_v1 import unique_capture

REVIEWS=registry.ROOT/'.local/duplicate-ownership-v3/exact-side-opening-source-repairs-r4/opening'


def exclusive_source_clubs(rows):
    owners=collections.defaultdict(list)
    for row in rows:
        if row['status']=='original-first-fixture-reparsed':
            owners[row['evidence']['source_club_id']].append(row)
    allowed=set()
    for same in owners.values():
        playable=[r for r in same if r['playable']]
        if len(same)==1:allowed.add(same[0]['club_id'])
        elif len(playable)==1:allowed.add(playable[0]['club_id'])
    return allowed


def prepare(release):
    report_path=REVIEWS/release.season/'opening-review.json'
    report=pipeline.read_json_file(report_path)
    if report['schema_version']!=opening.SCHEMA or report['season']!=release.season:
        raise ValueError('wrong cached historical opening review')
    package=pipeline.read_json_file(release.package_path)
    clubs={c['id']:c for c in package['clubs']};managers={m['id']:m for m in package['managers']}
    eq=release.game_path/'DBDAT/EQ98030.FDI';ent=release.game_path/'DBDAT/ENT98030.FDI'
    holders,names=_manager_graph(eq_path=eq,ent_path=ent)
    allowed=exclusive_source_clubs(report['clubs'])
    capture_path=registry.ROOT/report['bindings']['opening_capture_path']
    if registry.sha256_file(capture_path)!=report['bindings']['opening_capture_sha256']:
        raise ValueError('cached opening capture changed')
    capture=pipeline.read_json_file(capture_path)
    updates=[];unresolved=[];unchanged=0
    for row in report['clubs']:
        if row['status']!='original-first-fixture-reparsed' or not row['evidence'].get('manager'):
            continue
        club=clubs.get(row['club_id']);current=managers.get(club.get('manager_id')) if club else None
        if current is None:continue
        target=row['evidence']['manager']
        if opening._normalise(current['name'])==opening._normalise(target):
            unchanged+=1;continue
        try:
            if club['name']!=row['club'] or club['carrier_id']!=row['carrier_id']:
                raise ValueError('current club label/carrier differs from original source target')
            if club['id'] not in allowed:
                raise ValueError('source club has ambiguous multiple native representations')
            if roster.club_group(club) in CALENDAR_YEAR_COUNTRIES and row['evidence']['date'][:4]!=release.season[:4]:
                raise ValueError('calendar-country fixture lies outside target start year')
            owner=current['carrier_id']
            if [r['carrier_id'] for r in holders.get(owner,[])]!=[club['carrier_id']]:
                raise ValueError('current native manager is not exclusively owned by target club')
            captured=unique_capture(club,capture['clubs'])
            if captured is None:raise ValueError('no unique explicit captured club identity')
            proof=opening.verify_opening(captured,capture,capture_path.parent/'cache')
            if (proof['source_club_id'],proof['date'],proof['manager'])!=(
                    row['evidence']['source_club_id'],row['evidence']['date'],target):
                raise ValueError('original exact-club fixture/manager does not reparse to the saved claim')
            alias,method=display.short_name(target)
            if alias is None:raise ValueError('native display needs an explicit compound-name alias')
            from scripts import season_package_compiler_v2 as compiler
            alias=compiler._pm99_text(alias,label='source-bound manager short display')
            updates.append(dict(club_id=club['id'],club_carrier_id=club['carrier_id'],club=club['name'],
                manager_id=current['id'],carrier_id=owner,before=current['name'],before_policy=current.get('policy'),
                native_before=names[owner],after=target,native_after=alias,
                first_fixture_date=proof['date'],evidence=proof,native_manager_owner_count=1,
                native_display_basis=method))
        except (ValueError,KeyError) as exc:
            unresolved.append(dict(club_id=club['id'],club=club['name'],before=current['name'],
                proposed=target,reason=str(exc)))
    counts=collections.Counter(opening._normalise(r['after']) for r in updates)
    ambiguous=[r for r in updates if counts[opening._normalise(r['after'])]>1]
    unresolved.extend(dict(club_id=r['club_id'],club=r['club'],before=r['before'],
        proposed=r['after'],reason='same sourced manager at multiple first-fixture clubs; needs dated reconciliation') for r in ambiguous)
    updates=[r for r in updates if counts[opening._normalise(r['after'])]==1]
    return dict(schema_version='pm99-historical-manager-plan-v1',season=release.season,release_id=release.release_id,
        package_sha256=registry.sha256_file(release.package_path),eq_sha256=registry.sha256_file(eq),
        ent_sha256=registry.sha256_file(ent),audit_path=registry.relative_workspace_path(report_path),
        audit_sha256=registry.sha256_file(report_path),updates=updates,unresolved=unresolved,
        independently_reparsed_current_manager_corrections=True,
        implementation_inputs=[dict(path=registry.relative_workspace_path(Path(p)),sha256=registry.sha256_file(Path(p)))
            for p in (__file__,opening.__file__,display.__file__)],
        summary=dict(corrections=len(updates),canonical_names_already_match=unchanged,
            mismatches_requiring_further_review=len(unresolved)),historical_verification_complete=False)


def main():
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    root=registry.ROOT/'.local/consolidated-audit-20261009/cached-manager-source-repairs-20261016-v1'
    for season in registry.supported_seasons():
        release=registry.load_preferred_release(season)
        path=root/'source-plans'/season/(release.release_id+'.json')
        if path.exists():
            plan=pipeline.read_json_file(path)
            if plan['package_sha256']!=registry.sha256_file(release.package_path):
                raise ValueError('prepared manager source recipe changed')
        else:
            plan=prepare(release);path.parent.mkdir(parents=True,exist_ok=True);retained(path,plan)
        print(dict(season=season,**plan['summary'],native_writes=0),flush=True)


if __name__=='__main__':main()
