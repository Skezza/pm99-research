from scripts.review_season_portrait_materialisation_v1 import source_issues


def fixture():
    player = {'name': 'Lucas Pérez', 'facts': {'birth_date': '1988-09-10'}}
    source = {'sofifa_id': '199354', 'short_name': 'Lucas Pérez',
              'long_name': 'Lucas Pérez Martínez', 'dob': '1988-09-10'}
    row = {'name': player['name'], 'source_edition': 15,
           'source_image_url': 'https://cdn.sofifa.net/players/199/354/15_120.png'}
    return row, player, source


def test_exact_identity_and_edition_are_accepted():
    assert source_issues(*fixture()) == []


def test_url_to_another_player_or_edition_is_rejected():
    row, player, source = fixture()
    row['source_image_url'] = 'https://cdn.sofifa.net/players/200/949/16_120.png'
    assert 'image-url-identity-or-edition-mismatch' in source_issues(row, player, source)


def test_matching_alias_does_not_excuse_conflicting_birthday():
    row, player, source = fixture()
    player['facts']['birth_date'] = '1992-08-13'
    assert 'source-birth-date-not-corroborated' in source_issues(row, player, source)


def test_source_name_must_match_recipe_not_merely_manifest():
    row, player, source = fixture()
    player['name'] = 'Lucas Moura'
    assert 'recipe-player-name-mismatch' in source_issues(row, player, source)
