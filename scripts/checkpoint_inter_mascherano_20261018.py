"""Publish two narrowly corrected games only after genuine exact-player proof."""
import copy
from datetime import UTC, datetime
from scripts.checkpoint_larsson_holt_kroos_20261018 import (
    AUDIT, fields, exchange, source_step, startup_review, binding, retained,
    profiles, digits, runtime, publisher, registry, pipeline, bindings,
    verify_original2015, regression)

CASE = '0df0bf39ba56e883fe0b683623a1db23bddce5ee79a8bb5153474bc36b231163'
TARGETS = {
    '2000-01': dict(root=AUDIT / 'Gresko2000-Inter-opening-review-v1',
        release='sourced-inter-august-contract-reserve-20261018-r160a',
        replay='replayed-inter-august-contract-reserve-20261018-r160b',
        source=exchange, rows=[(21373, 'colombo_inter', '', 'Colombo'),
                               (11445, 'gresko', '', 'Gresko')]),
    '2010-11': dict(root=AUDIT / 'Mascherano2010-dated-role-v1',
        release='sourced-dated-mascherano-midfield-20261018-r161a',
        replay='replayed-dated-mascherano-midfield-20261018-r161b',
        source=fields, rows=[(8066, 'mascherano', '', 'Mascherano')]),
}


def run():
    previous = AUDIT / 'release-delivery-checklist-v122.json'
    output = AUDIT / 'release-delivery-checklist-v123.json'
    if output.exists():
        raise ValueError('completed checkpoint must not repeat')
    original = pipeline.read_json_file(previous)
    old = {row['season']: row for row in original['current_release_bindings']}
    if len(original['cross_club_dispositions']) != 58 or original['remaining_cross_club_cases'] != 2751:
        raise ValueError('frozen progress baseline differs')
    if any(row['case_id'] == CASE for row in original['cross_club_dispositions']):
        raise ValueError('Gresko already disposed')
    for row in bindings():
        target = TARGETS.get(row['season'])
        if row != old[row['season']] and not (target and row['release_id'] == target['release']):
            raise ValueError('preferred baseline changed; inspect before publication')
    steps, startups = [], {}
    for season, item in TARGETS.items():
        steps.append(source_step(season, item['release'], item['replay'], item['source']))
        profiles.verify_profiles(item['root'], season, item['release'], item['rows'])
        digits.verify_profiles(item['root'], season, item['release'], item['rows'])
        startups[season] = startup_review(item['root'], season, item['release'])
    original2015 = verify_original2015()
    for season, item in TARGETS.items():
        retained(item['root'] / 'prepublication-proof.json', dict(
            steps=steps, original2015=original2015,
            scope='One August Inter ownership correction and one dated Liverpool role correction; not global roster or historical approval.'))
    # All evidence must pass above before either preferred default is changed.
    for season, item in TARGETS.items():
        publisher.register_completed_delta(season, item['release'])
        final = item['root'] / 'final-attestation.json'
        if final.exists():
            if registry._validate_runtime_attestation(registry.load_preferred_release(season)):
                raise ValueError('existing runtime attestation no longer validates')
        else:
            retained(final, runtime.attest(season=season, evidence_dir=startups[season]))
    current = bindings()
    for row in current:
        if row['season'] not in TARGETS and row != old[row['season']]:
            raise ValueError('one of other24 preferred releases changed')
    result = copy.deepcopy(original)
    variations_path = AUDIT / 'annual-role-dispositions-20261018-v1/reviewed-broad-variations-v1.json'
    variations = pipeline.read_json_file(variations_path)
    if (variations.get('actual_game_corrections') != 0
            or variations.get('frozen_duplicate_cases_closed') != 0
            or len(variations['cases']) != 3):
        raise ValueError('broad-role exceptions must not be counted as repairs')
    for case in variations['cases']:
        current_release = registry.load_preferred_release(case['season'])
        if (current_release.release_id != case['current_release']
                or registry.sha256_file(current_release.package_path) != case['package_sha256']):
            raise ValueError('reviewed broad-role exception baseline changed')
        for original_source in (case['period_source'], case['annual_source']):
            path = original_source.get('path') or original_source['raw_path']
            if registry.sha256_file(registry.ROOT / path) != original_source['sha256']:
                raise ValueError('reviewed broad-role original changed')
        matches = [row for row in result['additional_confirmed_findings'] if row['id'] == case['id']]
        if len(matches) != 1:
            raise ValueError('one original broad-position review candidate required')
        matches[0].update(state=case['disposition'], native_fix_required=False,
            classification='legitimate-period-broad-role-variation-not-a-confirmed-bug',
            correction_evidence=binding(variations_path), scope=case['scope'])
    result['cross_club_dispositions'].append(dict(case_id=CASE, season='2000-01',
        state='confirmed-fault-repaired-current-game',
        retained='Original Bayer Leverkusen Gresko11445 exact, genuine profile verified',
        replacement='Inter21373 Corrado Colombo: positive July entry/October exit August contract bracket, not a matchday appearance claim',
        delivery=binding(TARGETS['2000-01']['root'] / 'native-and-unchanged-proof.json')))
    finding = dict(id='country-source-position-2010-11-8066', season='2010-11',
        carrier_id=8066, state='repaired-and-runtime-verified',
        scope='Liverpool Mascherano defender/CB to dated midfielder/compatible DM; two native bytes, unrelated facts/skills/assets preserved',
        correction_evidence=binding(TARGETS['2010-11']['root'] / 'mascherano-native-runtime-proof.json'))
    existing = [i for i, row in enumerate(result['additional_confirmed_findings']) if row['id'] == finding['id']]
    if len(existing) > 1:
        raise ValueError('ambiguous role finding')
    if existing:
        result['additional_confirmed_findings'][existing[0]].update(finding)
    else:
        result['additional_confirmed_findings'].append(finding)
    result.update(previous_checklist=binding(previous), utc=datetime.now(UTC).isoformat(),
        current_release_bindings=current, remaining_cross_club_cases=2750,
        all_required_work_complete=False,
        next_batch='Continue source-positive Hearts McKenna/Celtic/Werder opening ownership and independently admitted current position issues. 59/2809 disposed,2750 unclosed candidates, not2750 confirmed bugs.')
    evidence = [original2015, binding(variations_path)]
    for item in TARGETS.values():
        root = item['root']
        evidence.extend(binding(root / name) for name in (
            'native-and-unchanged-proof.json', 'complete-SOURCE-replay.json',
            'prepublication-proof.json', 'final-attestation.json',
            'startup-transport.json', 'startup-visual-review.json'))
        for _, label, _, _ in item['rows']:
            evidence.extend(binding(root / (label + '-' + suffix + '.json')) for suffix in (
                'profile-transport', 'profile-visual-review', 'native-runtime-proof',
                'original-digit-proof', 'original-age-proof'))
    result['delivered_evidence'].extend(evidence)
    result['fresh_runtime_runs_this_checklist'] = [dict(season=season,
        release_id=item['release'], evidence=registry.relative_workspace_path(startups[season]),
        profiles=[row[1] for row in item['rows']]) for season, item in TARGETS.items()]
    retained(output, result)
    regression.verify(output, TARGETS['2000-01']['root'] / 'all26-postdelivery-regression.json')
    print('v123: actual Inter owner and Liverpool role corrections delivered;59/2809 disposed,2750 unclosed candidates', flush=True)


if __name__ == '__main__':
    run()
