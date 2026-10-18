from scripts import season_historical_roster_audit_v1 as roster


def original(group, name, full_name=''):
    groups = {group, 'english-non-league'} if group == 'england' else {group}
    names = {name, full_name} - {''}
    for aliases in (roster.ntf_source.ALIASES, roster.ntf_source.HISTORICAL_ALIASES):
        for (country, baseline), variants in aliases.items():
            if country in groups and ({roster.normalise(baseline), *(roster.normalise(v) for v in variants)} &
                                      {roster.normalise(n) for n in names}):
                names.update((baseline, *variants))
    return {roster.normalise(n) for n in names}


def test_cached_expansion_matches_original_for_every_published_alias_and_scope():
    for table in (roster.ntf_source.ALIASES, roster.ntf_source.HISTORICAL_ALIASES):
        for (country, baseline), variants in table.items():
            for name in (baseline, *variants):
                for scope in (country, 'england', None):
                    assert roster.club_names(scope, name) == original(scope, name)
                    assert roster.club_names(scope, name, baseline) == original(scope, name, baseline)


def test_returned_sets_are_independent_and_alias_edits_invalidate_cache(monkeypatch):
    monkeypatch.setattr(roster.ntf_source, 'ALIASES', {('england', 'A'): ('B',), ('england', 'B'): ('C',)})
    monkeypatch.setattr(roster.ntf_source, 'HISTORICAL_ALIASES', {})
    names = roster.club_names('england', 'A')
    names.add('unrelated')
    assert roster.club_names('england', 'A') == {'a', 'b', 'c'}
    roster.ntf_source.ALIASES[('england', 'A')] = ('D',)
    assert roster.club_names('england', 'A') == {'a', 'd'}
    assert roster.club_names(None, 'A') == {'a'}


def test_original_order_dependent_one_pass_semantics_are_preserved(monkeypatch):
    monkeypatch.setattr(roster.ntf_source, 'ALIASES', {('england', 'B'): ('C',), ('england', 'A'): ('B',)})
    monkeypatch.setattr(roster.ntf_source, 'HISTORICAL_ALIASES', {})
    assert roster.club_names('england', 'A') == original('england', 'A') == {'a', 'b'}
