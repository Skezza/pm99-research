import pytest
import copy

from scripts import season_manager_display_repair_v1 as repair


@pytest.mark.parametrize('name,expected', [
    ('Arsène Wenger', 'Wenger'), ('Louis van Gaal', 'van Gaal'),
    ('Erik ten Hag', 'ten Hag'), ('Nuno Espírito Santo', 'Nuno'),
    ('Roberto Di Matteo', 'Di Matteo'), ('Régis Le Bris', 'Le Bris'),
    ('Jimmy Floyd Hasselbaink', 'Hasselbaink'), ('Ole Gunnar Solskjaer', 'Solskjaer'),
    ('Keith Alexander †', 'Alexander'), ('Sir Bobby Robson', 'Robson'),
    ('Abelardo', 'Abelardo'), ('Jean-Paul de Jong', 'de Jong'),
])
def test_common_names_and_compounds_are_not_blind_last_tokens(name, expected):
    assert repair.short_name(name)[0] == expected


def test_unknown_multiple_given_or_family_names_remain_queued():
    assert repair.short_name('Unverified Multiple Names')[0] is None


def test_existing_output_is_never_overwritten(tmp_path):
    with pytest.raises(ValueError, match='never overwrite'):
        repair.prepare('2016-17', tmp_path)


def test_equal_manager_rows_keep_references_in_both_recipe_layers():
    main = {'managers': [{'id': 'm', 'carrier_id': 7, 'name': 'Eddie Howe', 'policy': 'write'}],
            'clubs': [{'carrier_id': 301, 'manager_id': 'm', 'name': 'Bournemouth'}]}
    english = copy.deepcopy(main)
    refs, _ = repair.collect_targets([main, english])[7]
    assert len(refs) == 2
    for row in refs:
        row['native_names'] = {'surname': 'Howe', 'display_name': 'Howe'}
    assert main['managers'][0]['native_names'] == english['managers'][0]['native_names']


def test_legacy_binding_uses_exclusive_native_graph_not_the_old_carrier():
    english = {'managers': [{'id': 'm', 'carrier_id': 3, 'name': 'Arsene Wenger'}],
               'clubs': [{'carrier_id': 309, 'manager_id': 'm'}]}
    changes = repair.reconcile_legacy_english(english, {620: [{'carrier_id': 309}]}, {620: 'Arsène Wenger'})
    assert english['managers'][0]['carrier_id'] == 620
    assert english['managers'][0]['policy'] == 'write'
    assert english['managers'][0]['name'] == 'Arsene Wenger'
    assert changes[0]['before_carrier_id'] == 3
    english['managers'][0]['native_names'] = {'surname': 'Wenger', 'display_name': 'Wenger'}
    repair.reconcile_legacy_english(english, {620: [{'carrier_id': 309}]}, {620: 'Wenger'})
    assert english['managers'][0]['name'] == 'Arsene Wenger'
    with pytest.raises(ValueError, match='exclusive native manager'):
        repair.reconcile_legacy_english(english, {620: [{'carrier_id': 309}]}, {620: 'Wrong Manager'})
