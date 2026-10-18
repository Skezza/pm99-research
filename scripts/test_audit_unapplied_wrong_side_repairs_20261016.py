from scripts.audit_unapplied_wrong_side_repairs_20261016 import classify, native_name_matches


def test_rejected_complete_opponent_is_not_a_source_correction():
    correct=list(range(11));wrong=list(range(20,31))
    assert classify(wrong,correct,wrong)=='confirmed-opponent-XI-still-in-current-game'
    assert classify(correct,correct,wrong)=='corrected-source-XI-present-in-current-game'


def test_partial_identity_or_mixed_roster_is_not_a_confirmed_whole_opponent():
    correct=list(range(11));wrong=list(range(20,31))
    assert classify(correct[:10]+[None],correct,wrong)=='unresolved-exact-person-identity'
    assert classify(correct[:10]+[correct[0]],correct,wrong)=='unresolved-exact-person-identity'
    assert classify(correct[:5]+wrong[:6],correct,wrong)=='mixed-current-XI-needs-individual-source-review'


def test_only_actual_native_trailing_space_padding_is_ignored():
    assert native_name_matches('DAVID RAYA   ','David Raya')
    assert not native_name_matches('#1 DAVID RAYA','David Raya')
    assert not native_name_matches('D. RAYA','David Raya')
    assert not native_name_matches('DAVID RAY','David Raya')
    assert not native_name_matches(' DAVID RAYA','David Raya')
