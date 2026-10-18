import copy
import pytest
from scripts import season_sourced_reserve_role_policy_v1 as policy


def inputs():
    row = {'player_id': 'reserve', 'before': {'facts': {'primary_position': 'D'}},
        'replacement': {'source_player': {'position': 'M'}, 'source_person': {'source_player_id': 99},
            'opening_eligibility': {'method': 'positive-first-fixture-substitute-id'}},
        'replacement_opening_evidence': {'starting_xi': {'10': 'Starter'}, 'substitutes': {'99': 'Reserve'}},
        'reserve_role_change': {'before': 'D', 'after': 'M', 'policy': policy.POLICY}}
    plan = {'resolution_policy': policy.RESOLUTION, 'bindings': {'reserve_role_policy': policy.POLICY,
        'published_person_supplement': {'path': 'bound-people'},
        'published_transfer_supplement': {'path': 'bound-transfers'}},
            'allow_sourced_outfield_reserve_role_changes': True}
    club = {'opening': {'starting_xi_player_ids': ['starter']}}
    return plan, row, club


def test_default_does_not_change_roles_and_explicit_policy_uses_actual_bench_position():
    plan, row, club = inputs()
    assert not policy.eligible(row['before'], row['replacement'])
    assert policy.eligible(row['before'], row['replacement'], True)
    policy.validate(plan, row, club)


@pytest.mark.parametrize('problem', ['old-keeper', 'new-keeper', 'unlisted-reserve', 'native-starter',
    'source-starter', 'missing-bench-id', 'undeclared', 'wrong-policy', 'forged-position', 'missing-public-input'])
def test_keeper_starter_unsourced_or_forged_changes_are_refused(problem):
    plan, row, club = inputs()
    if problem == 'old-keeper': row['before']['facts']['primary_position'] = 'G'
    if problem == 'new-keeper': row['replacement']['source_player']['position'] = 'G'
    if problem == 'unlisted-reserve': row['replacement']['opening_eligibility']['method'] = 'dated-opening-reserve-entry-exit-bracket'
    if problem == 'native-starter': club['opening']['starting_xi_player_ids'].append('reserve')
    if problem == 'source-starter': row['replacement_opening_evidence']['starting_xi']['99'] = 'Reserve'
    if problem == 'missing-bench-id': row['replacement_opening_evidence']['substitutes'].clear()
    if problem == 'undeclared': plan['allow_sourced_outfield_reserve_role_changes'] = False
    if problem == 'wrong-policy': plan['bindings']['reserve_role_policy'] = 'unknown'
    if problem == 'forged-position': row['reserve_role_change']['after'] = 'F'
    if problem == 'missing-public-input': del plan['bindings']['published_person_supplement']
    with pytest.raises(ValueError): policy.validate(plan, row, club)


def test_legacy_same_role_inputs_need_no_new_policy():
    _, row, club = inputs()
    row['replacement']['source_player']['position'] = 'D'
    assert policy.eligible(row['before'], row['replacement'])
    policy.validate({}, row, club)


def dated_inputs():
    plan, row, club = inputs()
    plan['resolution_policy'] = policy.DATED_RESOLUTION
    plan['bindings']['reserve_role_policy'] = policy.DATED_POLICY
    plan['allow_dated_outfield_reserve_role_changes'] = True
    row['reserve_role_change']['policy'] = policy.DATED_POLICY
    row['replacement']['opening_eligibility'] = {
        'method': 'dated-opening-reserve-entry-exit-bracket', 'date': '2021-08-07', 'source_club_id': 44,
        'interval': {'status': 'recorded-entry-and-exit-bracket-fixture', 'source_owner_club_id': 44,
            'entry': {'date': '2021-07-01', 'to_club_id': 44},
            'departure': {'date': '2022-01-01', 'from_club_id': 44}}}
    row['replacement']['raw_evidence'] = {'status': 'raw-source-reparsed'}
    row['replacement_opening_evidence'].update(date='2021-08-07', source_club_id=44, substitutes={})
    return plan, row, club


def test_dated_reserve_retains_sourced_outfield_role_only_with_explicit_new_policy():
    plan, row, club = dated_inputs()
    assert not policy.eligible(row['before'], row['replacement'])
    assert not policy.eligible(row['before'], row['replacement'], True)
    assert policy.eligible(row['before'], row['replacement'], True, True)
    policy.validate(plan, row, club)


@pytest.mark.parametrize('problem', ['no-opt-in', 'legacy-resolution', 'legacy-policy',
    'old-keeper', 'new-keeper', 'missing-entry', 'missing-exit', 'same-day-entry',
    'same-day-exit', 'reversed-interval', 'invalid-date', 'owner-conflict', 'entry-club-conflict',
    'exit-club-conflict', 'wrong-opening-club', 'wrong-opening-date', 'incomplete-interval',
    'native-starter', 'source-starter', 'unreparsed-facts', 'no-squad-proof', 'forged-position',
    'no-public-history'])
def test_dated_reserve_does_not_bypass_original_evidence_or_starting_keeper_guards(problem):
    plan, row, club = dated_inputs()
    proof = row['replacement']['opening_eligibility']; interval = proof['interval']
    if problem == 'no-opt-in': del plan['allow_dated_outfield_reserve_role_changes']
    if problem == 'legacy-resolution': plan['resolution_policy'] = policy.RESOLUTION
    if problem == 'legacy-policy': plan['bindings']['reserve_role_policy'] = policy.POLICY
    if problem == 'old-keeper': row['before']['facts']['primary_position'] = 'G'
    if problem == 'new-keeper': row['replacement']['source_player']['position'] = 'G'
    if problem == 'missing-entry': del interval['entry']
    if problem == 'missing-exit': del interval['departure']
    if problem == 'same-day-entry': interval['entry']['date'] = proof['date']
    if problem == 'same-day-exit': interval['departure']['date'] = proof['date']
    if problem == 'reversed-interval': interval['departure']['date'] = '2020-01-01'
    if problem == 'invalid-date': proof['date'] = '2021-02-30'
    if problem == 'owner-conflict': interval['source_owner_club_id'] = 45
    if problem == 'entry-club-conflict': interval['entry']['to_club_id'] = 45
    if problem == 'exit-club-conflict': interval['departure']['from_club_id'] = 45
    if problem == 'wrong-opening-club': row['replacement_opening_evidence']['source_club_id'] = 45
    if problem == 'wrong-opening-date': row['replacement_opening_evidence']['date'] = '2021-08-08'
    if problem == 'incomplete-interval': interval['status'] = 'entry-only'
    if problem == 'native-starter': club['opening']['starting_xi_player_ids'].append(row['player_id'])
    if problem == 'source-starter': row['replacement_opening_evidence']['starting_xi']['99'] = 'Reserve'
    if problem == 'unreparsed-facts': row['replacement']['raw_evidence']['status'] = 'cached-summary'
    if problem == 'no-squad-proof': del row['replacement']['raw_evidence']
    if problem == 'forged-position': row['reserve_role_change']['after'] = 'F'
    if problem == 'no-public-history': del plan['bindings']['published_transfer_supplement']
    with pytest.raises(ValueError): policy.validate(plan, row, club)


def test_new_policy_still_accepts_original_positive_bench_position_and_legacy_is_unchanged():
    legacy_plan, legacy_row, club = inputs()
    assert policy.recognised(legacy_plan)
    policy.validate(legacy_plan, legacy_row, club)
    plan = copy.deepcopy(legacy_plan); row = copy.deepcopy(legacy_row)
    plan.update(resolution_policy=policy.DATED_RESOLUTION, allow_dated_outfield_reserve_role_changes=True)
    plan['bindings']['reserve_role_policy'] = policy.DATED_POLICY
    row['reserve_role_change']['policy'] = policy.DATED_POLICY
    policy.validate(plan, row, club)
