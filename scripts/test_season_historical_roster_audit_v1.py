"""Independent-source joins and native loader offsets must fail conservatively."""
import copy
import pytest
from scripts import season_historical_roster_audit_v1 as audit
from scripts import season_package_compiler_v2 as compiler
from scripts.test_season_package_compiler_v2 import _dd6360_player_payload, _dd6361_player_payload


def candidate(name='Lamine Yamal', dob='2007-07-13'):
    return {'facts': {'name': name, 'birth_date': dob}}


def player(name='Lamine Yamal', dob='2007-07-13'):
    return {'name': name, 'facts': {'birth_date': dob}}


def test_name_and_date_are_both_checked():
    basis, matches = audit.source_matches(player(), [candidate(), candidate(dob='1997-07-13')])
    assert basis == 'name-and-birth-date'
    assert matches == [candidate()]


def test_conflicting_date_is_not_verified():
    assert audit.source_matches(player(), [candidate(dob='1997-07-13')])[0] == 'birth-date-disagrees'


def test_missing_date_is_not_upgraded_to_identity_proof():
    assert audit.source_matches(player(dob=None), [candidate()])[0] == 'name-only'


def test_no_fuzzy_surname_or_initial_identity_guess():
    assert audit.source_matches(player(name='L. Yamal'), [candidate()]) == ('not-found', [])


def test_original_source_name_survives_native_alias():
    target = player(name='Yamal')
    target['source_name'] = 'Lamine Yamal'
    assert audit.source_matches(target, [candidate()])[0] == 'name-and-birth-date'


def test_accents_are_presentation_not_another_person():
    assert audit.normalise('Raphaël Varane') == audit.normalise('Raphael VARANE')


def test_duplicate_identity_uses_full_source_names_not_country_or_display():
    left = player('Hatswell', '1975-02-08')
    left.update(source_name='Wayne Hatswell')
    right = player('Wayne Hatswell', '1975-02-08')
    left['facts']['nationality'] = 'XXX'
    right['facts']['nationality'] = 'ENG'
    assert audit.person_identity_key(left) == audit.person_identity_key(right)
    right['facts']['birth_date'] = '1975-02-09'
    assert audit.person_identity_key(left) != audit.person_identity_key(right)


def test_same_birthday_and_display_alias_do_not_merge_distinct_source_people():
    left = player('E. Espinal', '1982-11-14')
    right = player('E. Espinal', '1982-11-14')
    left['source_name'] = 'Elpys Jose Espinal'
    right['source_name'] = 'Elpys Vinicio Espinal'
    assert audit.person_identity_key(left) != audit.person_identity_key(right)


def test_missing_date_is_not_a_duplicate_identity_certificate():
    assert audit.person_identity_key(player(dob=None)) is None


@pytest.mark.parametrize('payload_factory', [_dd6360_player_payload, _dd6361_player_payload])
def test_native_roles_start_after_two_bytes(payload_factory):
    raw = bytearray(payload_factory(1))
    end = compiler._native_dd6360_role_start(raw)
    raw[end + 1] = 1 ^ 0x61  # skipped byte looks like a goalkeeper
    raw[end + 2:end + 8] = bytes(x ^ 0x61 for x in [4, 5, 3, 15, 0, 0])
    result = audit.native_player(bytes(raw), 1)
    assert result['display_role'] == 'Sweeper'
    assert result['roles'] == [3, 4, 2, 14, 98, 98]


def test_native_identity_mismatch_is_a_read_error():
    with pytest.raises(ValueError, match='self-ID'):
        audit.native_player(_dd6360_player_payload(1), 2)


@pytest.mark.parametrize('position,role,expected', [('F', 3, True), ('F', 11, False), ('D', 12, True),
                                                 ('M', 14, False), ('G', 12, True), ('G', 0, False)])
def test_conservative_compatibility(position, role, expected):
    assert audit.role_conflict(position, role) == expected


def test_preserved_position_does_not_become_a_historical_claim():
    assert not audit.role_conflict({'policy': 'preserve-existing-mode1'}, 3)


def test_audit_leaves_input_objects_unchanged():
    target, rows = player(), [candidate()]
    before = copy.deepcopy((target, rows))
    audit.source_matches(target, rows)
    assert (target, rows) == before


@pytest.mark.parametrize('provider,title,expected', [
    ('ntf', 'Guarani Asunción (2000) | National Football Teams', ('Guarani Asunción', '2000')),
    ('transfermarkt', 'Barcelona - Detailed squad 00/01 | Transfermarkt', ('Barcelona', '00/01')),
])
def test_raw_document_binds_club_and_season(provider, title, expected):
    assert audit.historical_html_title(f'<title>{title}</title>'.encode(), provider, '2000-01', 'spain') == expected


def test_next_year_is_not_accepted_for_split_year_club():
    with pytest.raises(ValueError, match='outside'):
        audit.historical_html_title(b'<title>Barcelona - Detailed squad 2001 | Transfermarkt</title>',
                                    'transfermarkt', '2000-01', 'spain')


def test_unknown_html_title_is_not_self_certified_from_capture():
    with pytest.raises(ValueError, match='identity'):
        audit.historical_html_title(b'<title>Untitled</title>', 'ntf', '2000-01', 'spain')


def test_aliases_are_country_scoped():
    assert audit.normalise('Crvena Zvezda Beograd') in audit.club_names('serbia', 'Red Star')
    assert audit.normalise('Crvena Zvezda Beograd') not in audit.club_names('spain', 'Red Star')


def test_title_like_text_inside_script_is_not_a_document_title():
    raw = b'<script>let x = "<title>Fake - Squad 00/01 | Transfermarkt</title>";</script><title>Barcelona - Squad 00/01 | Transfermarkt</title>'
    assert audit.historical_html_title(raw, 'transfermarkt', '2000-01', 'spain')[0] == 'Barcelona'


def test_strict_calendar_source_must_name_start_year_not_the_following_year():
    with pytest.raises(ValueError, match='outside'):
        audit.historical_html_title(b'<title>Club - Squad 2001 | Transfermarkt</title>', 'transfermarkt',
                                    '2000-01', 'finland', allow_calendar_ending_year=False)


def test_completed_raw_reparse_reuse_requires_identical_captures_and_raw_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    original = tmp_path / 'source.txt'; original.write_bytes(b'original synthetic external source')
    digest = audit.registry.sha256_file(original)
    binding = [{'path': 'capture.json', 'sha256': 'a' * 64}]
    row = {'source_path': 'club.txt', 'source_sha256': digest, 'players': []}
    proof = {'status': 'raw-source-reparsed', 'source_path': 'club.txt', 'source_sha256': digest, 'local_path': 'source.txt'}
    prior = {'schema_version': audit.SCHEMA, 'season': '2000-01', 'bindings': {'sources': binding}, 'raw_sources': [proof]}
    assert audit.SourceVerifier('2000-01', prior, binding).verify(row) == proof
    with pytest.raises(ValueError, match='changed captures'):
        audit.SourceVerifier('2000-01', prior, [])
    original.write_bytes(b'changed source')
    with pytest.raises(ValueError, match='source changed'):
        audit.SourceVerifier('2000-01', prior, binding)
