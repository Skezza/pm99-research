"""Publish seven bounded actual-game corrections only after source/runtime proof.

No builds or runner launches here. Every source replay is an existing sealed
game, checked again before publication; unaffected defaults stay unchanged.
"""
import copy
from datetime import UTC, datetime

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as fields
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import publish_historical_role_delta_v1 as publisher
from scripts import verify_city_opening_runtime_20261011 as profiles
from scripts import verify_profile_skill_digits_v1 as digits
from scripts import attest_registered_season_runtime_v1 as runtime
from scripts import verify_checkpoint_all26_v1 as regression
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.checkpoint_reserve_assignment_delivery_20261010 import binding
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

AUDIT = registry.ROOT / '.local/consolidated-audit-20261009'
FACTS = AUDIT / 'Scotland2000-label-manager-v1/larsson-facts'
HOLT = AUDIT / 'Holt2000-opening-exchange-v1'
KROOS = AUDIT / 'Werder2013-opening-review-v1'
ROLE = FACTS / '2004-05/compatible-role-completion'
OUT = AUDIT / 'larsson-holt-kroos-release-v120'
FACT_RELEASE = 'sourced-adjudicated-original-facts-20261018-r153a'
HOLT_RELEASE = 'sourced-norwich-original-opening-reserve-20261018-r154a'
KROOS_RELEASE = 'sourced-dated-kroos-midfield-20261018-r155a'
ROLE_RELEASE = 'sourced-compatible-larsson-forward-20261018-r156a'
HOLT_CASE = '0543df1f3f24c24c94e197f586ef328cb872295d77e5b5367d3432fcdd305013'


def source_step(season, child_id, replay_id, module):
    child = registry.load_registered_release(season, child_id)
    plan_path = registry.ROOT / child.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(plan_path)
    parent = registry.load_registered_release(season, plan['release_id'])
    module.verify(parent, plan)
    if module.bind(pipeline.read_json_file(parent.package_path), plan) != pipeline.read_json_file(child.package_path):
        raise ValueError('actual correction recipe does not reproduce')
    jug = (parent.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (parent.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    actual = ((child.game_path / 'DBDAT/JUG98030.FDI').read_bytes(),
              (child.game_path / 'DBDAT/EQ98030.FDI').read_bytes())
    if module.apply(jug, eq, plan) != actual or module.apply(*actual, plan) != actual:
        raise ValueError('actual native correction or idempotence differs')
    replay = registry.load_registered_release(season, replay_id)
    pipeline.assert_tree_matches_inventory(replay.game_path, pipeline.read_json_file(child.inventory_path))
    if replay.package_path.read_bytes() != child.package_path.read_bytes():
        raise ValueError('complete SOURCE recipe replay differs')
    return dict(season=season, release_id=child_id, parent=parent.release_id,
        source_plan=binding(plan_path), native_exact=True, idempotent=True,
        complete_SOURCE_game_and_recipe_exact=True, replay_release=replay_id)


def startup_review(root, season, release_id):
    release = registry.load_registered_release(season, release_id)
    review = pipeline.read_json_file(root / 'startup-visual-review.json')
    transport = pipeline.read_json_file(root / 'startup-transport.json')
    screen = registry.ROOT / review['screenshot']
    summary = pipeline.read_json_file(registry.ROOT / transport['evidence'] / 'summary.json')
    team = (summary.get('route_summaries', {}).get('line_up') or {}).get('team_identity') or {}
    if (review.get('method') != 'assistant-original-image-visual-review'
            or review.get('original_frame_visually_inspected') is not True
            or review['release_manifest_sha256'] != release.manifest_sha256
            or review['observed_team'] != 'Stoke City' or review['observed_date'] != season[:4] + '-08-01'
            or registry.sha256_file(screen) != review['screenshot_sha256']
            or transport['exit_code'] != 0 or transport['release_manifest_sha256'] != release.manifest_sha256
            or summary.get('success') is not True or summary.get('phase_reached') != 'return_from_line_up'
            or summary.get('release_manifest_sha256') != release.manifest_sha256
            or summary.get('output_inventory_fingerprint') != release.locator['game_inventory_fingerprint']
            or team.get('matched') is not True or 'stoke' not in team.get('observed_normalized', '').split()):
        raise ValueError('genuine exact-release startup review required')
    return registry.ROOT / transport['evidence']


def run():
    previous = AUDIT / 'release-delivery-checklist-v119.json'
    output = AUDIT / 'release-delivery-checklist-v120.json'
    if output.exists():
        raise ValueError('v120 already completed; advance, do not repeat publication')
    OUT.mkdir(exist_ok=True)
    original = pipeline.read_json_file(previous)
    parents = {row['season']: row for row in original['current_release_bindings']}
    targets = {f'{year}-{str(year+1)[-2:]}': FACT_RELEASE for year in range(2000, 2006)}
    targets.update({'2000-01': HOLT_RELEASE, '2004-05': ROLE_RELEASE, '2013-14': KROOS_RELEASE})
    for current in bindings():
        season = current['season']
        if current != parents[season] and current['release_id'] != targets.get(season):
            raise ValueError('unexpected preferred change; preserve intervening work')
    steps = []
    evidence = []
    for year in range(2000, 2006):
        season = f'{year}-{str(year+1)[-2:]}'
        steps.append(source_step(season, FACT_RELEASE,
            'replayed-adjudicated-original-facts-20261018-r153b', fields))
        for name in ('native-and-unchanged-proof.json', 'complete-SOURCE-replay.json'):
            evidence.append(binding(FACTS / season / name))
    steps.append(source_step('2000-01', HOLT_RELEASE, 'replayed-norwich-original-opening-reserve-20261018-r154b', exchange))
    steps.append(source_step('2004-05', ROLE_RELEASE, 'replayed-compatible-larsson-forward-20261018-r156b', fields))
    steps.append(source_step('2013-14', KROOS_RELEASE, 'replayed-dated-kroos-midfield-20261018-r155b', fields))
    profile_rows = {'2000-01': [(9962, 'dewaard', '', 'Waard'), (12209, 'holt', '', 'Holt'), (7879, 'larsson', '', 'Larsson')],
                    '2004-05': [(1790, 'larsson', '', 'Larsson')],
                    '2013-14': [(11344, 'kroos', '', 'Kroos')]}
    roots, startup = {}, {}
    for season, release_id in targets.items():
        root = HOLT if season == '2000-01' else ROLE if season == '2004-05' else KROOS if season == '2013-14' else FACTS / season
        roots[season] = root
        rows = profile_rows.get(season, [(7879 if season in ('2001-02', '2002-03') else 8078 if season == '2003-04' else 2613, 'larsson', '', 'Larsson')])
        profiles.verify_profiles(root, season, release_id, rows)
        digits.verify_profiles(root, season, release_id, rows)
        startup[season] = startup_review(root, season, release_id)
        for name in ('startup-transport.json', 'startup-visual-review.json'):
            evidence.append(binding(root / name))
        for _, label, _, _ in rows:
            for suffix in ('profile-transport', 'profile-visual-review', 'native-runtime-proof', 'original-digit-proof', 'original-age-proof'):
                evidence.append(binding(root / (label + '-' + suffix + '.json')))
    original2015 = verify_original2015()
    retained(OUT / 'prepublication-proof.json', dict(steps=steps, original2015=original2015,
        affected_seasons=sorted(targets), source_native_runtime_all_passed=True,
        counts=dict(Larsson_corrected_DOBs=6, Larsson_corrected_countries=6,
                    wrong_Norwich_Holt_copy_replaced=1, Kroos_broad_roles=1, Larsson_conflicting_role_sets=1)))
    for season, release_id in targets.items():
        chain = [parents[season]['release_id']]
        if season in ('2000-01', '2004-05'):
            chain.append(FACT_RELEASE)
        chain.append(release_id)
        publisher.register_completed_delta(season, release_id, verified_ancestor_chain=chain)
        final_path = roots[season] / 'final-attestation.json'
        if final_path.exists():
            release = registry.load_preferred_release(season)
            if registry._validate_runtime_attestation(release):
                raise ValueError('existing final runtime attestation no longer verifies')
        else:
            retained(final_path, runtime.attest(season=season, evidence_dir=startup[season]))
        evidence.append(binding(roots[season] / 'final-attestation.json'))
    current = bindings()
    for row in current:
        if row['season'] not in targets and row != parents[row['season']]:
            raise ValueError('unaffected preferred release changed')
    result = copy.deepcopy(original)
    if len(result['cross_club_dispositions']) != 55 or result['remaining_cross_club_cases'] != 2754:
        raise ValueError('original frozen progress counters differ')
    if any(row['case_id'] == HOLT_CASE for row in result['cross_club_dispositions']):
        raise ValueError('Holt case already disposed')
    result['cross_club_dispositions'].append(dict(case_id=HOLT_CASE, season='2000-01',
        state='confirmed-fault-repaired-current-game', retained='Gary Holt at Kilmarnock12209',
        replacement='Raymond de Waard at Norwich9962; original August12 played substitute',
        delivery=binding(HOLT / 'native-and-unchanged-proof.json')))
    result.update(previous_checklist=binding(previous), utc=datetime.now(UTC).isoformat(),
        current_release_bindings=current, remaining_cross_club_cases=2753,
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', machine='joe-Vostro-3350',
        all_required_work_complete=False,
        next_batch='Celtic2000 Lennon ownership then further frozen ownership cases; Werder2013 Garcia/full roster remains open. No whole-roster or all26 historical RC approval.')
    result['additional_confirmed_findings'].append(dict(id='Larsson-six-season-facts-Holt-opening-owner-Kroos-midfield-v120',
        state='delivered-native-SOURCE-and-genuine-runner-verified', correction_evidence=binding(OUT / 'prepublication-proof.json'),
        scope='12 corrected Larsson facts, one conflicting legacy role set, one wrong-owner Holt reserve, one Kroos broad position. Original birthday247 and duplicate2809 denominators unchanged. Compatible biography fine role, not exact-period FIFA evidence.'))
    result['new_required_followups'].append(dict(id='Gary-Holt-2000-retained-incompatible-fine-role',
        season='2000-01', carrier_id=12209, status='confirmed-inherited-fine-role-conflict-open',
        observed_broad_role='MIDFIELDER', observed_fine_role='SWEEPER',
        evidence=binding(HOLT / 'holt-profile-visual-review.json'),
        scope='Kilmarnock ownership and preserved ten skills verified; fine role was not approved by ownership correction. Scope canonical identity across26 before bounded role repair. Not an extra frozen duplicate case.'))
    for followup in result['new_required_followups']:
        if followup['id'] == 'HenrikLarsson2000-country-and-source-birthday':
            followup.update(status='delivered-six-linked-seasons-native-SOURCE-and-genuine-runner-verified',
                delivery=binding(OUT / 'prepublication-proof.json'),
                scope='Six exact canonical actors corrected; twelve fields. Two already-correct records unchanged; same-name-only actors not merged. Original 247 date-mismatch denominator unchanged.')
        elif followup['id'] == 'Werder2013-Kroos-opening-position':
            followup.update(status='broad-position-delivered-opening-XI-still-open',
                delivery=binding(KROOS / 'kroos-native-runtime-proof.json'),
                scope='Dated broad M and compatible central role delivered. StartingXI/order remain part of open coupled WerderGarcia opening-roster correction; no full XI approval.')
    result['delivered_evidence'].extend(evidence + [binding(OUT / 'prepublication-proof.json'), original2015])
    result['fresh_runtime_runs_this_checklist'] = [dict(season=s, release_id=targets[s], evidence=registry.relative_workspace_path(startup[s])) for s in sorted(targets)]
    retained(output, result)
    regression.verify(output, OUT / 'all26-postdelivery-regression.json')
    print('v120 delivered: seven defaults, 56/2809 crossclub cases disposed, 2753 candidates remain; original2015 and other19 defaults preserved', flush=True)


if __name__ == '__main__':
    run()
