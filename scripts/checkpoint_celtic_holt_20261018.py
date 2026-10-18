"""Publish the composed Celtic ownership/Holt role fix, after genuine runner proof."""
import copy
from datetime import UTC, datetime
from scripts.checkpoint_larsson_holt_kroos_20261018 import (
    AUDIT, fields, exchange, source_step, startup_review, binding, retained,
    profiles, digits, runtime, publisher, registry, pipeline, bindings,
    verify_original2015, regression)
from scripts import build_celtic_lennon_burchill_20261018 as celtic
from scripts import build_holt_compatible_role_20261018 as holt

CASE = '47ca91f51d09393fdb65c808c77cc8adf34715d2400f39aedd61587bc6b52c1b'


def run():
    previous = AUDIT / 'release-delivery-checklist-v120.json'
    output = AUDIT / 'release-delivery-checklist-v121.json'
    if output.exists():
        raise ValueError('completed Celtic checkpoint must not repeat')
    original = pipeline.read_json_file(previous)
    old = {row['season']: row for row in original['current_release_bindings']}
    for row in bindings():
        if row != old[row['season']] and not (row['season'] == '2000-01' and row['release_id'] == holt.RELEASE):
            raise ValueError('preferred defaults changed beyond the admitted final game')
    steps = [source_step('2000-01', celtic.RELEASE, celtic.REPLAY, exchange),
             source_step('2000-01', holt.RELEASE, holt.REPLAY, fields)]
    rows = [(19261, 'burchill', '', 'Burchill'), (12209, 'holt', '', 'Holt')]
    profiles.verify_profiles(holt.ROOT, '2000-01', holt.RELEASE, rows)
    digits.verify_profiles(holt.ROOT, '2000-01', holt.RELEASE, rows)
    startup = startup_review(holt.ROOT, '2000-01', holt.RELEASE)
    original2015 = verify_original2015()
    retained(holt.ROOT / 'prepublication-proof.json', dict(steps=steps, original2015=original2015,
        original_firstXI_orders_tactics_managers_kits_preserved=True,
        scope='One frozen Lennon ownership case and one independently confirmed Holt fine-role conflict; not global Celtic roster approval.'))
    publisher.register_completed_delta('2000-01', holt.RELEASE,
        verified_ancestor_chain=[celtic.BASE, celtic.RELEASE, holt.RELEASE])
    final = holt.ROOT / 'final-attestation.json'
    if final.exists():
        if registry._validate_runtime_attestation(registry.load_preferred_release('2000-01')):
            raise ValueError('existing final attestation differs')
    else:
        retained(final, runtime.attest(season='2000-01', evidence_dir=startup))
    current = bindings()
    if any(row != old[row['season']] for row in current if row['season'] != '2000-01'):
        raise ValueError('one of other25 preferred releases changed')
    if len(original['cross_club_dispositions']) != 56 or original['remaining_cross_club_cases'] != 2753:
        raise ValueError('fixed progress baseline differs')
    result = copy.deepcopy(original)
    if any(row['case_id'] == CASE for row in result['cross_club_dispositions']):
        raise ValueError('Lennon already disposed')
    result['cross_club_dispositions'].append(dict(case_id=CASE, season='2000-01',
        state='confirmed-fault-repaired-current-game', retained='Neil Lennon Leicester9130 exact',
        replacement='Mark Burchill Celtic19261, original July30 firstleague bench; full source name, explicitly published native family display',
        delivery=binding(celtic.ROOT / 'native-and-unchanged-proof.json')))
    result.update(previous_checklist=binding(previous), utc=datetime.now(UTC).isoformat(),
        current_release_bindings=current, remaining_cross_club_cases=2752,
        all_required_work_complete=False,
        next_batch='Source-positive Monaco Panucci/Hearts McKenna and unresolved Gresko/WerderGarcia/Celtic ownership; frozen57disposed/2752candidates, no global historical RC claim.')
    for followup in result['new_required_followups']:
        if followup['id'] == 'Gary-Holt-2000-retained-incompatible-fine-role':
            followup.update(status='delivered-native-SOURCE-and-genuine-runner-verified',
                delivery=binding(holt.ROOT / 'holt-native-runtime-proof.json'),
                scope='Only original Kilmarnock12209 conflicting Sweeper/CentreBack set replaced by compatible published CentralMidfield9. Eight other original Holt actors compatible/untouched; wrong Norwich copy already replaced. Not exact-edition FIFA claim.')
    evidence = [original2015]
    for root in (celtic.ROOT, holt.ROOT):
        evidence.extend(binding(root / name) for name in ('native-and-unchanged-proof.json', 'complete-SOURCE-replay.json'))
    evidence.extend(binding(holt.ROOT / name) for name in ('prepublication-proof.json', 'final-attestation.json', 'startup-transport.json', 'startup-visual-review.json'))
    for _, label, _, _ in rows:
        evidence.extend(binding(holt.ROOT / (label + '-' + suffix + '.json')) for suffix in ('profile-transport', 'profile-visual-review', 'native-runtime-proof', 'original-digit-proof', 'original-age-proof'))
    result['delivered_evidence'].extend(evidence)
    result['fresh_runtime_runs_this_checklist'] = [dict(season='2000-01', release_id=holt.RELEASE,
        evidence=registry.relative_workspace_path(startup), profiles=['burchill', 'holt'])]
    retained(output, result)
    regression.verify(output, holt.ROOT / 'all26-postdelivery-regression.json')
    print('v121 delivered: Lennon owner and Holt fine-role fixes current;57/2809disposed,2752unclosedcandidates', flush=True)


if __name__ == '__main__':
    run()
