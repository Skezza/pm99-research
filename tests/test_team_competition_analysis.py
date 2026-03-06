from app.team_competition_analysis import (
    LeagueAssignmentProbe,
    resolve_league_assignment_contract,
)


def _probe(
    *,
    method: str,
    confidence: str,
    candidate_country: str = "England",
    candidate_league: str = "Premier League",
    matches_assigned_competition: bool = True,
) -> LeagueAssignmentProbe:
    return LeagueAssignmentProbe(
        primary_code=0x7F,
        method=method,
        signal_name=method,
        signal_offset=0,
        signal_value_display="0x7F",
        candidate_competition=f"{candidate_country} / {candidate_league}",
        candidate_country=candidate_country,
        candidate_league=candidate_league,
        purity=0.9,
        support_count=5,
        total_count=6,
        confidence=confidence,
        assigned_competition="England / First Division",
        matches_assigned_competition=matches_assigned_competition,
    )


def test_resolve_league_assignment_contract_keeps_team_id_range_source():
    resolution = resolve_league_assignment_contract(
        current_country="England",
        current_league="First Division",
        current_source="team_id_range",
        probe=_probe(method="tertiary_signature", confidence="high", matches_assigned_competition=False),
    )

    assert resolution.source == "team_id_range"
    assert resolution.country == "England"
    assert resolution.league == "First Division"
    assert resolution.confidence == "high"
    assert resolution.status == "confirmed"
    assert resolution.promoted is False


def test_resolve_league_assignment_contract_promotes_sequence_fallback_with_strong_probe():
    resolution = resolve_league_assignment_contract(
        current_country="England",
        current_league="Second Division",
        current_source="sequence_fallback",
        probe=_probe(
            method="tertiary_signature",
            confidence="high",
            candidate_country="Italy",
            candidate_league="Serie A",
            matches_assigned_competition=False,
        ),
    )

    assert resolution.source == "competition_probe_contract"
    assert resolution.country == "Italy"
    assert resolution.league == "Serie A"
    assert resolution.confidence == "high"
    assert resolution.status == "probe-promoted"
    assert resolution.promoted is True
    assert resolution.promoted_from_source == "sequence_fallback"
    assert resolution.promoted_method == "tertiary_signature"


def test_resolve_league_assignment_contract_does_not_promote_primary_code_probe():
    resolution = resolve_league_assignment_contract(
        current_country="England",
        current_league="Second Division",
        current_source="sequence_fallback",
        probe=_probe(
            method="primary_code",
            confidence="high",
            candidate_country="Austria",
            candidate_league="Bundesliga",
            matches_assigned_competition=False,
        ),
    )

    assert resolution.source == "sequence_fallback"
    assert resolution.country == "England"
    assert resolution.league == "Second Division"
    assert resolution.promoted is False
    assert resolution.confidence == "review"
    assert resolution.status == "probe-mismatch"


def test_resolve_league_assignment_contract_promotes_unknown_source_with_medium_probe():
    resolution = resolve_league_assignment_contract(
        current_country="Unknown",
        current_league="Unknown League",
        current_source="unknown",
        probe=_probe(
            method="family_metadata_byte",
            confidence="medium",
            candidate_country="France",
            candidate_league="Division 1",
            matches_assigned_competition=False,
        ),
    )

    assert resolution.source == "competition_probe_contract"
    assert resolution.country == "France"
    assert resolution.league == "Division 1"
    assert resolution.confidence == "medium"
    assert resolution.status == "probe-promoted"
    assert resolution.promoted is True

