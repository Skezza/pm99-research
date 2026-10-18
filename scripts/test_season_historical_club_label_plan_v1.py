import copy

import pytest
from scripts import season_historical_club_label_plan_v1 as labels
from scripts import publish_historical_role_delta_v1 as publisher
from scripts.test_season_package_compiler_v2 import _indexed_fdi, _native_package


def inline(text):
    value = text.encode('cp1252')
    return bytes(v ^ 0x61 for v in len(value).to_bytes(2, 'little')) + value


def payload(stadium='Original Ground'):
    return b'opaque' + bytes(v ^ 0x61 for v in (120).to_bytes(2, 'little')) + b'\xdd\x63\x61\x83' + inline('Old Club') + inline(stadium) + b'\x18\x91' + inline('Old Club FC') + b'unknown roster manager ratings tail'


def change():
    return {'carrier_id': 307, 'native_before': 'Old Club', 'native_full_before': 'Old Club FC', 'native_after': 'Werder Bremen'}


def test_variable_length_label_preserves_ground_roster_owner_and_unrelated_records():
    before = _indexed_fdi([(307, '', payload()), (308, '', payload())])
    after, changes = labels.rewrite_club_labels(before, [change()])
    old = labels.IndexedFDIFile.from_bytes(before); new = labels.IndexedFDIFile.from_bytes(after)
    a = old.entries[0].decode_payload(before); b = new.entries[0].decode_payload(after)
    assert labels.prefix_parts(a)[2] == labels.prefix_parts(b)[2]
    assert labels.prefix_parts(b)[:2] == ('Werder Bremen', 'Werder Bremen')
    assert old.entries[1].decode_payload(before) == new.entries[1].decode_payload(after)
    assert len(changes) == 1
    second = {**change(), 'native_before': 'Werder Bremen', 'native_full_before': 'Werder Bremen'}
    assert labels.rewrite_club_labels(after, [second]) == (after, [])


def test_ground_whitespace_normalisation_is_not_an_authorised_label_write():
    before = _indexed_fdi([(307, '', payload('Original  Ground'))])
    with pytest.raises(ValueError, match='ground'):
        labels.rewrite_club_labels(before, [change()])


def test_stale_or_duplicate_native_label_binding_is_rejected():
    before = _indexed_fdi([(307, '', payload())])
    with pytest.raises(ValueError, match='before-state'):
        labels.rewrite_club_labels(before, [{**change(), 'native_before': 'Different'}])
    with pytest.raises(ValueError, match='duplicate'):
        labels.rewrite_club_labels(before, [change(), change()])


def test_recipe_label_delta_preserves_players_rosters_and_prior_role_provenance():
    package = _native_package(); original = copy.deepcopy(package)
    club = package['clubs'][0]
    control = {'season': '2015-16', 'updates': [], 'unresolved': []}
    plan = {'updates': [{'club_id': club['id'], 'carrier_id': club['carrier_id'],
        'before': club['name'], 'before_full': club.get('full_name'), 'after': 'Werder Bremen',
        'identity_after': 'source-club-germany-werder-bremen'}]}
    result = publisher.updated_package(package, control, club_plan=plan)
    assert package == original
    for key in package.keys() - {'clubs', 'artifacts', 'proofs'}:
        assert result[key] == package[key]
    assert result['clubs'][0]['roster_player_ids'] == club['roster_player_ids']
    assert result['clubs'][0]['name'] == 'Werder Bremen'
    assert not any(a['relative_path'] == 'role-plan.json' for a in result['artifacts'] if 'relative_path' in a)


def test_second_label_layer_preserves_original_proofs_and_source_artifact():
    package = _native_package(); club = package['clubs'][0]
    control = {'season':'2015-16','updates':[],'unresolved':[]}
    first = {'updates':[dict(club_id=club['id'],carrier_id=club['carrier_id'],
        before=club['name'],before_full=club.get('full_name'),after='First Club',identity_after='first')]}
    once = publisher.updated_package(package,control,club_plan=first)
    older = next(a for a in once['artifacts'] if a['id']=='historical-club-label-plan-2015-16')
    second = {'updates':[dict(club_id=club['id'],carrier_id=club['carrier_id'],
        before='First Club',before_full='First Club',after='Second Club',identity_after='second')]}
    twice = publisher.updated_package(once,control,club_plan=second)
    assert older in twice['artifacts']
    assert all(p in twice['proofs'] for p in once['proofs'])
    newest = next(a for a in twice['artifacts'] if a['id']==twice['clubs'][0]['proof']['artifact_id'])
    assert newest['relative_path'].startswith('club-update-')
    assert newest['relative_path'] != older['relative_path']
