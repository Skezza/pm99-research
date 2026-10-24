import copy
import pytest
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_package_compiler_v2 as compiler
from scripts.test_season_package_compiler_v2 import (
    _native_package, _indexed_fdi, _dd6360_player_payload, _dd6361_player_payload,
)
from app.fdi_indexed import IndexedFDIFile


def fixture(family='dd6360'):
    package = _native_package()
    club = package['clubs'][0]
    club['division'] = 'preserve-existing-mode1-membership'
    club['opening'] = {'policy': 'preserve-existing-mode1', 'proof': club['proof']}
    player = package['players'][1]
    player['carrier_family'] = family
    plan = {'season': '2015-16', 'bindings': {'snapshot': {'project_url': 'https://example.org/pinned'}},
        'updates': [{'layer': 'main', 'player_id': player['id'], 'carrier_id': player['carrier_id'],
            'before': copy.deepcopy(player), 'replacement_opening_evidence': {'date': '2015-08-08'},
            'replacement': {'source_person': {'source_player_id': 99, 'birth_date': '1991-02-03',
                                              'given_name': 'Alex', 'family_name': 'King'},
                'source_player': {'name': 'Alex King', 'birth_date': '1991-02-03',
                    'position': 'D', 'nationality': 'ENG', 'height_cm': 180, 'weight_kg': 76}}}]}
    return package, plan


def test_private_compiler_view_matches_previous_filtered_inputs_without_mutation():
    package, _ = fixture()
    before = copy.deepcopy(package)
    changed = {package['players'][1]['id']}
    expected = copy.deepcopy(package)
    expected['players'] = [p for p in expected['players'] if p['id'] in changed]
    for club in expected['clubs']:
        club['roster_player_ids'] = [pid for pid in club['roster_player_ids'] if pid in changed]
        for key in ('starting_xi_player_ids', 'substitute_player_ids'):
            if key in club.get('opening', {}):
                club['opening'][key] = [pid for pid in club['opening'][key] if pid in changed]
    subset = delta._compiler_subset(package, changed)
    assert subset == {key: expected[key] for key in ('players', 'clubs')}
    subset['players'][0]['facts']['birth_date'] = '1900-01-01'
    subset['clubs'][0]['roster_player_ids'].clear()
    assert package == before


@pytest.mark.parametrize('family',['dd6360','dd6361'])
def test_approved_unknown_actor_keeps_native_date_without_inventing_birthday(family,monkeypatch):
    from scripts import season_original_fixture_display_v1 as fixture_display
    package,plan=fixture(family)
    replacement=plan['updates'][0]['replacement']
    replacement['source_person'].update(source_player_id='fixture-actor:test',birth_date=None,name='Trajkovic')
    replacement['source_player'].update(birth_date=None,name='Trajkovic')
    monkeypatch.setattr(fixture_display,'verify_actor',lambda p:'person-original-fixture-test')
    result=delta.updated_package(package,plan)
    assert result['players'][1]['facts']['birth_date']=={'policy':'preserve-existing-mode1'}
    gaps=result['players'][1]['fact_fallbacks']
    assert next(g for g in gaps if g['field']=='birth_date')['method']=='preserve-existing-mode1'
    payload=_dd6360_player_payload if family=='dd6360' else _dd6361_player_payload
    original=_indexed_fdi([(1,'',payload(1)),(2,'',payload(2))])
    delta.fit_display_names(original,result,plan)
    patched=delta.compile_players(original,result,{'player-02'},{'ENGLAND':30,'XXX':0})
    def birth_bytes(raw):
        entry=next(e for e in IndexedFDIFile.from_bytes(raw).entries if e.record_id==2)
        value=entry.decode_payload(raw);end=delta.roster.native_player(value,2)['name_end']
        return value[end+12:end+16]
    assert birth_bytes(original)==birth_bytes(patched)


def test_unknown_api_birthday_cannot_silently_become_a_native_fallback():
    package,plan=fixture()
    plan['updates'][0]['replacement']['source_person']['birth_date']=None
    plan['updates'][0]['replacement']['source_player']['birth_date']=None
    with pytest.raises(ValueError,match='lacks original fixture'):
        delta.updated_package(package,plan)


def test_private_compiler_view_never_copies_unrelated_assets_or_players():
    class MustNotCopy:
        def __deepcopy__(self, memo):
            raise AssertionError('unrelated evidence copied during bounded compilation')
    package, _ = fixture()
    changed = {package['players'][1]['id']}
    package['assets'] = MustNotCopy()
    package['players'][0]['unrelated_test_evidence'] = MustNotCopy()
    subset = delta._compiler_subset(package, changed)
    assert len(subset['players']) == 1


def test_recipe_delta_preserves_all_other_people_clubs_tactics_kits_managers():
    package, plan = fixture()
    before = copy.deepcopy(package)
    after = delta.updated_package(package, plan)
    assert package == before
    for key in ('clubs', 'managers', 'calendar', 'scope'):
        assert after[key] == package[key]
    assert after['assets']['kits'] == package['assets']['kits']
    assert after['players'][0] == package['players'][0]
    assert after['players'][2:] == package['players'][2:]
    replacement = after['players'][1]
    assert replacement['facts']['birth_date'] == '1991-02-03'
    assert replacement['ratings']['values']['handling'] <= 20
    assert replacement['ratings']['values'] != package['players'][1]['ratings']['values']
    assert delta.updated_package(package, plan) == after


def test_changed_identity_cannot_keep_original_individual_skills_or_face():
    package, plan = fixture()
    player_id = package['players'][1]['id']
    portrait = next(p for p in package['assets']['portraits'] if p['player_id'] == player_id)
    portrait.update(status='applied', artifact_id='kit-home')
    result = delta.updated_package(package, plan)
    replacement = next(p for p in result['assets']['portraits'] if p['player_id'] == player_id)
    assert replacement['status'] == 'native-no-photo'
    assert 'artifact_id' not in replacement


def test_stale_row_is_rejected_not_applied_to_another_person():
    package, plan = fixture()
    package['players'][1]['facts']['birth_date'] = '1980-01-01'
    with pytest.raises(ValueError, match='exact prior'):
        delta.updated_package(package, plan)


def test_second_batch_keeps_first_person_and_its_evidence_intact():
    package, first_plan = fixture()
    first = delta.updated_package(package, first_plan)
    second_plan = copy.deepcopy(first_plan)
    target = first['players'][0]
    update = second_plan['updates'][0]
    update.update(player_id=target['id'], carrier_id=target['carrier_id'], before=copy.deepcopy(target))
    source = update['replacement']['source_player']
    source.update(name='Second Player', birth_date='1992-04-05', position=target['facts']['primary_position'])
    update['replacement']['source_person'].update(source_player_id=100, birth_date='1992-04-05',
                                                given_name='Second', family_name='Player')
    second = delta.updated_package(first, second_plan)
    assert second['players'][1] == first['players'][1]
    original_artifact = next(a for a in first['artifacts'] if a['id'].startswith('duplicate-ownership-plan-'))
    assert original_artifact in second['artifacts']
    ownership_artifacts = [a for a in second['artifacts'] if a['id'].startswith('duplicate-ownership-plan-')]
    assert len(ownership_artifacts) == 2
    assert len({a['relative_path'] for a in ownership_artifacts}) == 2
    assert first['players'][1]['proof'] == second['players'][1]['proof']


def test_playable_modern_replacement_writes_actual_u16_birth_year():
    package, plan = fixture('dd6361')
    package['clubs'][0]['division'] = 'Premier League'
    plan['updates'][0]['replacement']['source_player']['birth_date'] = '2003-01-03'
    plan['updates'][0]['replacement']['source_person']['birth_date'] = '2003-01-03'
    result = delta.updated_package(package, plan)
    original = _indexed_fdi([(1, '', _dd6361_player_payload(1)), (2, '', _dd6361_player_payload(2))])
    delta.fit_display_names(original, result, plan)
    patched = delta.compile_players(original, result, {'player-02'}, {'ENGLAND': 30, 'XXX': 0})
    entry = next(e for e in IndexedFDIFile.from_bytes(patched).entries if e.record_id == 2)
    payload = entry.decode_payload(patched)
    end = delta.roster.native_player(payload, 2)['name_end']
    assert int.from_bytes(bytes(b ^ 0x61 for b in payload[end + 14:end + 16]), 'little') == 2003
    assert delta.compile_players(patched, result, {'player-02'}, {'ENGLAND': 30, 'XXX': 0}) == patched
    native_skills = {field: payload[-16 + i] ^ 0x61 for i, field in enumerate(compiler.SKILLS)}
    assert compiler._patch_dd6361_mode1_safe_fields(
        payload, position=None, nationality=None, birth_day=None, birth_month=None,
        birth_year=None, height=None, weight=None, skills=native_skills) == payload


@pytest.mark.parametrize('family',['dd6360','dd6361'])
def test_genuine_soccerbase_identity_compiles_without_fake_tm_id_or_other_record_changes(family):
    package,plan=fixture(family)
    plan['updates'][0]['replacement']['source_person'].update(
        source_player_id='soccerbase:555',source_provider='soccerbase')
    result=delta.updated_package(package,plan)
    assert result['players'][1]['person_id']=='person-soccerbase-555'
    builder=_dd6360_player_payload if family=='dd6360' else _dd6361_player_payload
    original=_indexed_fdi([(1,'',builder(1)),(2,'',builder(2))])
    delta.fit_display_names(original,result,plan)
    patched=delta.compile_players(original,result,{'player-02'},{'ENGLAND':30,'XXX':0})
    before={e.record_id:e.decode_payload(original) for e in IndexedFDIFile.from_bytes(original).entries}
    after={e.record_id:e.decode_payload(patched) for e in IndexedFDIFile.from_bytes(patched).entries}
    assert after[1]==before[1] and after[2]!=before[2]
    assert delta.compile_players(patched,result,{'player-02'},{'ENGLAND':30,'XXX':0})==patched


@pytest.mark.parametrize('family', ['dd6360', 'dd6361'])
@pytest.mark.parametrize('playable', [False, True])
def test_native_outfield_reserve_uses_its_own_actual_position_without_other_record_changes(family, playable):
    package, plan = fixture(family)
    if playable:
        package['clubs'][0]['division'] = 'Premier League'
    assert plan['updates'][0]['before']['facts']['primary_position'] == 'M'
    plan['updates'][0]['replacement']['source_player']['position'] = 'D'
    result = delta.updated_package(package, plan)
    maker = _dd6360_player_payload if family == 'dd6360' else _dd6361_player_payload
    # The previous fixture declared M but its compact native record was D;
    # that accidentally missed an actual two-byte position change. Use a
    # real M preimage, including a non-default parser-side position byte.
    target = bytearray(maker(2))
    end = delta.roster.native_player(target, 2)['name_end']
    target[end + 10], target[end + 11] = 2 ^ 0x61, 2 ^ 0x61
    original = _indexed_fdi([(1, '', maker(1)), (2, '', bytes(target))])
    delta.fit_display_names(original, result, plan)
    before = copy.deepcopy(result)
    patched = delta.compile_players(original, result, {'player-02'}, {'ENGLAND': 30, 'XXX': 0})
    assert result == before
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(patched).entries}
    actual = delta.roster.native_player(entries[2].decode_payload(patched), 2)
    assert actual['position'] == 'D' and actual['roles'][0] == 4
    old = {e.record_id: e for e in IndexedFDIFile.from_bytes(original).entries}
    assert entries[1].decode_payload(patched) == old[1].decode_payload(original)
    old_payload = old[2].decode_payload(original)
    new_payload = entries[2].decode_payload(patched)
    new_end = actual['name_end']
    assert new_payload[:8] == old_payload[:8]
    assert new_payload[new_end:new_end + 2] == old_payload[end:end + 2]
    assert new_payload[new_end + 9] == old_payload[end + 9]
    assert delta.compile_players(patched, result, {'player-02'}, {'ENGLAND': 30, 'XXX': 0}) == patched


@pytest.mark.parametrize('offset', [0, 1, 9])
def test_position_change_cannot_waive_unrelated_startup_or_control_bytes(monkeypatch, offset):
    package, plan = fixture('dd6360')
    result = delta.updated_package(package, plan)
    original = _indexed_fdi([(1, '', _dd6360_player_payload(1)), (2, '', _dd6360_player_payload(2))])
    delta.fit_display_names(original, result, plan)
    real = delta.rewrite_indexed_native_roles
    def corrupt(data, roles):
        patched, changes = real(data, roles)
        index = IndexedFDIFile.from_bytes(patched)
        entry = next(e for e in index.entries if e.record_id == 2)
        payload = bytearray(entry.decode_payload(patched))
        end = delta.roster.native_player(payload, 2)['name_end']
        payload[end + offset] ^= 1
        return compiler._rebuild_indexed(patched, index, {2: bytes(payload)}), changes
    monkeypatch.setattr(delta, 'rewrite_indexed_native_roles', corrupt)
    with pytest.raises(ValueError, match='club/shirt/startup controls'):
        delta.compile_players(original, result, {'player-02'}, {'ENGLAND': 30, 'XXX': 0})


@pytest.mark.parametrize('family', ['dd6360', 'dd6361'])
@pytest.mark.parametrize('playable', [False, True])
def test_native_delta_preserves_other_records_and_is_deterministic(family, playable):
    package, plan = fixture(family)
    if playable:
        package['clubs'][0]['division'] = 'premier'
    result = delta.updated_package(package, plan)
    maker = _dd6360_player_payload if family == 'dd6360' else _dd6361_player_payload
    original = _indexed_fdi([(1, '', maker(1)), (2, '', maker(2))])
    aliases = delta.fit_display_names(original, result, plan)
    assert aliases[0]['method'] in ('full-sourced-name', 'published-full-surname', 'published-given-initial-and-full-surname')
    patched = delta.compile_players(original, result, {'player-02'}, {'ENGLAND': 30, 'XXX': 0})
    before = IndexedFDIFile.from_bytes(original)
    after = IndexedFDIFile.from_bytes(patched)
    assert before.entries[0].decode_payload(original) == after.entries[0].decode_payload(patched)
    old = before.entries[1].decode_payload(original)
    new = after.entries[1].decode_payload(patched)
    old_end = delta.roster.native_player(old, 2)['name_end']
    new_end = delta.roster.native_player(new, 2)['name_end']
    assert old[:8] == new[:8]
    assert old[old_end:old_end + 2] == new[new_end:new_end + 2]
    assert delta.compile_players(original, result, {'player-02'}, {'ENGLAND': 30, 'XXX': 0}) == patched
    # An already-correct delta is a native no-op, not another wide rewrite.
    assert delta.compile_players(patched, result, {'player-02'}, {'ENGLAND': 30, 'XXX': 0}) == patched


@pytest.mark.parametrize('family', ['dd6360', 'dd6361'])
def test_unknown_replacement_country_preserves_exact_native_byte(family):
    package, plan = fixture(family)
    result = delta.updated_package(package, plan)
    result['players'][1]['facts']['nationality'] = {'policy': 'preserve-existing-mode1'}
    maker = _dd6360_player_payload if family == 'dd6360' else _dd6361_player_payload
    original = _indexed_fdi([(1, '', maker(1)), (2, '', maker(2))])
    delta.fit_display_names(original, result, plan)
    patched = delta.compile_players(original, result, {'player-02'}, {'ENGLAND': 30, 'XXX': 0})
    before = {e.record_id: e.decode_payload(original) for e in IndexedFDIFile.from_bytes(original).entries}
    after = {e.record_id: e.decode_payload(patched) for e in IndexedFDIFile.from_bytes(patched).entries}
    old_end = delta.roster.native_player(before[2], 2)['name_end']
    new_end = delta.roster.native_player(after[2], 2)['name_end']
    assert before[2][old_end+8] == after[2][new_end+8]
    assert after[1] == before[1]
    assert delta.compile_players(patched, result, {'player-02'}, {'ENGLAND': 30, 'XXX': 0}) == patched
