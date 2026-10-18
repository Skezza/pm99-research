from scripts.verify_foreign_portrait_sources_v1 import english_identity_issues
from scripts.reconcile_foreign_portrait_biographies_v1 import english_biography_verdict
from scripts import probe_sourced_factory_kit_v1 as kits
from scripts import season_kit_render_bindings_v1 as renderer
import pytest


def identity():
    player = {'name': 'Rob Elliot', 'facts': {'birth_date': '1986-04-30'}}
    receipt = {'player': 'Rob Elliot', 'portrait_source': 'fifa16', 'portrait_player_id': 167931,
               'source_url': 'https://cdn.sofifa.net/players/167/931/16_120.png'}
    person = {'short_name': 'Rob Elliot', 'long_name': 'Robert Elliot', 'dob': '1986-04-30'}
    return player, receipt, person


def test_missing_secondary_date_does_not_discard_correct_portrait():
    player, receipt, person = identity()
    player['facts'] = {}
    issues, warnings = english_identity_issues(player, receipt, person, None)
    assert not issues
    assert warnings == ['recipe-birthday-missing-not-an-identity-veto']


def test_url_cannot_silently_substitute_different_player_id():
    player, receipt, person = identity()
    receipt['source_url'] = receipt['source_url'].replace('/931/', '/932/')
    assert 'image-url-not-bound-to-declared-edition-and-id' in english_identity_issues(player, receipt, person, None)[0]


def test_undated_manual_photo_is_not_an_era_pass():
    player, receipt, _ = identity()
    receipt['portrait_source'] = 'reviewed-manual'
    manual = {'player': 'Rob Elliot', 'source_url': receipt['source_url'], 'temporal_note': 'Current profile of a player from 2015'}
    assert english_identity_issues(player, receipt, None, manual)[0] == ['manual-photo-era-not-corroborated']
    manual['temporal_note'] = '2014 player photograph, captured with labelled identity'
    assert not english_identity_issues(player, receipt, None, manual)[0]


def test_missing_id_and_out_of_era_url_are_logged_not_crashes():
    player, receipt, _ = identity()
    receipt.update(portrait_source='fifa20', portrait_player_id=None)
    assert set(english_identity_issues(player, receipt, None, None)[0]) == {
        'portrait-id-not-declared-in-original-receipt', 'portrait-edition-outside-two-year-era-window'}


def test_biography_can_separate_wrong_secondary_birthday_from_right_face():
    page = {'page_id': 1, 'title': 'Robert Elliot', 'birth_date': '1986-04-30', 'name_keys': []}
    row = {'name': 'Rob Elliot', 'dated_source_name': 'Robert Elliot', 'recipe_birth_date': '1986-04-01',
           'source_birth_date': '1986-04-30', 'issues': ['source-and-recipe-birthday-conflict-needs-corroboration']}
    index = {'rob elliot': [page], 'robert elliot': [page]}
    assert english_biography_verdict(row, index)['cleared_issues'] == row['issues']
    index['robert elliot'] = [{**page, 'page_id': 2}]
    assert not english_biography_verdict(row, index)['cleared_issues']


def test_kit_patch_rejects_wrapper_and_pixel_depth_changes():
    path = renderer.ROOT / '.local/season-pipeline-v2/pm99-base-clean/DBDAT/MINIESC.PKF'
    if not path.is_file():
        pytest.skip('local native corpus absent')
    records = renderer._record_index(path)
    if not records:
        pytest.skip('local native corpus absent')
    record = records[4]
    assert kits.checked_pixel_replacement(record, record.raw_bitmap) == record.raw_bitmap
    changed = bytearray(record.raw_bitmap)
    changed[6] ^= 1
    with pytest.raises(ValueError, match='wrapper'):
        kits.checked_pixel_replacement(record, bytes(changed))
    changed = bytearray(record.raw_bitmap)
    changed[record.pixel_offset - 1] ^= 1
    with pytest.raises(ValueError, match='8-bit'):
        kits.checked_pixel_replacement(record, bytes(changed))
