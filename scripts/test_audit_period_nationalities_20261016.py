from scripts.audit_period_nationalities_20261016 import unanimous


def test_no_claim_or_conflicting_nationalities_are_not_guessed():
    assert unanimous([]) is None
    assert unanimous([dict(nationality='ENG'),dict(nationality='SCO')]) is None


def test_exact_period_claims_can_agree_across_different_clubs():
    assert unanimous([dict(nationality='FRA',source_club='a'),dict(nationality='FRA',source_club='b')])=='FRA'
