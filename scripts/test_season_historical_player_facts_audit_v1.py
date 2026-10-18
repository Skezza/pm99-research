from scripts import season_historical_player_facts_audit_v1 as audit


def row(**facts):
    return {'facts': facts}


def test_missing_source_does_not_validate_default_england():
    assert audit.field_check('nationality', 'ENG', [row(nationality=None)])['status'] == 'no-independent-field-source'


def test_country_default_is_a_conflict_not_an_encoding_claim():
    result = audit.field_check('nationality', 'ENG', [row(nationality='POR')])
    assert result['status'] == 'conflict'
    assert not result['automatic_change_authorised']


def test_dual_nationalities_are_not_arbitrarily_selected():
    assert audit.field_check('nationality', 'ESP', [row(nationalities=['Spain', 'France'])])['status'] == 'compatible-but-source-ambiguous'
    assert audit.field_check('nationality', 'ENG', [row(nationalities=['Spain', 'France'])])['status'] == 'conflict-source-ambiguous'


def test_disagreeing_physical_measurements_remain_visible():
    assert audit.field_check('height_cm', 183, [row(height_cm=180), row(height_cm=183)])['status'] == 'compatible-but-source-ambiguous'


def test_preservation_is_not_historical_fact():
    assert audit.field_check('height_cm', {'policy': 'preserve-existing-mode1'}, [row(height_cm=183)])['status'] == 'recipe-missing-or-preserved'


def test_country_translation_is_explicit_not_club_country():
    assert audit.country('Portugal') == 'POR'
    assert audit.country('No such country') is None


def test_legacy_declared_country_table_label_can_be_checked_without_guessing_a_new_country():
    assert audit.field_check('nationality', 'CZECH REPUBLIC', [row(nationality='CZE')])['status'] == 'match'
    assert audit.field_check('nationality', 'LAT', [row(nationality='LVA')])['status'] == 'match'
