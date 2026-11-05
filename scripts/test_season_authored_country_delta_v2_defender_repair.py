"""An opt-in seed-role repair must never relax unrelated static controls."""
import copy
from types import SimpleNamespace

import pytest

from scripts import season_authored_country_delta_v2 as delta
from scripts.test_season_authored_country_delta_v2_static_openings import _request_harness


def _case(old_roles=(7,), new_roles=(4,), *, old_position='D', new_position='D', grade='source-receipt'):
    actor = {'facts': {'primary_position': old_position,
                       'fine_roles': {'policy': 'preserve-existing-mode1'}}}
    replacement = {'facts': {'primary_position': new_position, 'fine_roles': list(new_roles)},
                   'proof': {'grade': grade}}
    row = {'position': old_position, 'roles': list(old_roles) + [98] * (6-len(old_roles))}
    return actor, replacement, row


@pytest.mark.parametrize('old_roles', [(7,), (13, 11)])
def test_explicit_defender_repair_clears_only_incompatible_seed_candidates(old_roles):
    args = _case(old_roles)
    before = copy.deepcopy(args)
    assert delta._static_identity_roles(*args, repair_defender=True) == [4]
    assert args == before


def test_existing_static_contract_still_rejects_the_same_change_without_opt_in():
    with pytest.raises(ValueError, match='preserve matching native roles'):
        delta._static_identity_roles(*_case())


@pytest.mark.parametrize('old_roles', [(1,), (13, 1), ()])
def test_repair_cannot_discard_any_compatible_defensive_role_or_unassigned_set(old_roles):
    with pytest.raises(ValueError, match='contradictory roles'):
        delta._static_identity_roles(*_case(old_roles), repair_defender=True)


@pytest.mark.parametrize('new_roles', [(1,), (9,), (4, 14)])
def test_repair_is_not_a_general_fine_role_editor(new_roles):
    with pytest.raises(ValueError, match='generic D/4'):
        delta._static_identity_roles(*_case(new_roles=new_roles), repair_defender=True)


@pytest.mark.parametrize('grade', ['reviewed-editorial', 'static-contract', None])
def test_replacement_biography_cannot_be_an_unverified_static_placeholder(grade):
    with pytest.raises(ValueError, match='source-backed'):
        delta._static_identity_roles(*_case(grade=grade), repair_defender=True)


def test_new_broad_position_cannot_change_under_static_exception():
    with pytest.raises(ValueError, match='preserve matching native roles'):
        delta._static_identity_roles(*_case(new_position='M'), repair_defender=True)


@pytest.mark.parametrize('roles', [(18,), (255,), (True,)])
def test_unknown_or_noninteger_native_codes_cannot_be_normalized(roles):
    with pytest.raises(ValueError, match='contradictory roles'):
        delta._static_identity_roles(*_case(roles), repair_defender=True)


@pytest.mark.parametrize('missing', ['artifact', 'new-input', 'source-binding', 'wrong-hash',
                                    'inherited', 'inherited-path', 'duplicate-path'])
def test_source_grade_cannot_relabel_an_unbound_or_inherited_artifact(missing):
    actor = {'proof': {'artifact_id': 'receipt', 'grade': 'source-receipt'}}
    package = {'artifacts': [{'id': 'receipt', 'kind': 'season-input',
                             'relative_path': 'receipt.json', 'sha256': 'hash'}]}
    request = {'new_recipe_artifacts': [{'relative_path': 'receipt.json',
                 'path': 'inputs/receipt.json', 'sha256': 'hash'}]}
    authoring = {'source_bindings': [{'path': 'inputs/receipt.json', 'sha256': 'hash'}]}
    if missing == 'artifact':
        package['artifacts'] = []
    elif missing == 'new-input':
        request['new_recipe_artifacts'] = []
    elif missing == 'source-binding':
        authoring['source_bindings'] = []
    elif missing == 'wrong-hash':
        authoring['source_bindings'][0]['sha256'] = 'different'
    elif missing == 'duplicate-path':
        package['artifacts'].append(dict(package['artifacts'][0], id='other'))
    with pytest.raises(ValueError, match='hash-bound source input'):
        delta._static_repair_proof(actor, package, request, authoring,
            parent_artifact_ids={'receipt'} if missing == 'inherited' else set(),
            parent_artifact_paths={'receipt.json'} if missing == 'inherited-path' else set())


def _integrated(monkeypatch, tmp_path, *, final_order=5, final_position='D'):
    base, request, _, changed = _request_harness(
        monkeypatch, tmp_path, static=lambda snapshot: {'1': snapshot},
        role=7, position='D', compiled_jug='changed', opaque_parent=True)
    read = delta.p.read_json_file
    def documents(path):
        doc = copy.deepcopy(read(path))
        if path.name == 'child.json':
            doc['players'][0]['facts']['fine_roles'] = [4]
            doc['players'][0]['proof'] = {'grade': 'source-receipt', 'artifact_id': 'repair'}
            doc['artifacts'] = [{'id': 'repair', 'kind': 'season-input',
                'relative_path': 'proof.json', 'sha256': 'child-hash'}]
        elif path.name == 'authoring.json':
            doc['source_bindings'] = [{'path': 'proof.json', 'sha256': 'child-hash'}]
        return doc
    monkeypatch.setattr(delta.p, 'read_json_file', documents)
    monkeypatch.setattr('scripts.season_historical_roster_audit_v1.native_player',
        lambda payload, _carrier: {
            'roles': [4 if payload == b'compiled-actor' else 7, 98, 98, 98, 98, 98],
            'position': final_position if payload == b'compiled-actor' else 'D'})
    monkeypatch.setattr(delta, 'read_initial_order', lambda payload: SimpleNamespace(
        order=final_order if payload == b'compiled-actor' else 5))
    eq = (base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    jug = (base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    request['static_native_openings'] = {'1': delta.static_native_opening_snapshot(eq, jug, 1)}
    request['static_defender_fine_role_repairs'] = [101]
    (tmp_path/'proof.json').write_text('{}')
    request['new_recipe_artifacts'] = [{'path': 'proof.json',
        'relative_path': 'proof.json', 'sha256': 'child-hash'}]
    delta._CACHE.clear()
    return base, request, changed


def test_opt_in_is_checked_against_the_compiled_snapshot(monkeypatch, tmp_path):
    base, request, changed = _integrated(monkeypatch, tmp_path)
    result = delta._reconstruct(base, request)
    assert result['jug'] == changed
    assert result['eq'] == (base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    assert result['ent'] == b'ENT'


@pytest.mark.parametrize(('order', 'position'), [(6, 'D'), (5, 'M')])
def test_compiled_order_and_primary_changes_remain_forbidden(monkeypatch, tmp_path, order, position):
    base, request, _ = _integrated(monkeypatch, tmp_path, final_order=order, final_position=position)
    with pytest.raises(ValueError, match='startup controls or roles'):
        delta._reconstruct(base, request)


@pytest.mark.parametrize('repairs', [[True], [101, 101], [999], {'101': True}])
def test_flags_cannot_expand_the_selected_actor_scope(monkeypatch, tmp_path, repairs):
    base, request, _ = _integrated(monkeypatch, tmp_path)
    request['static_defender_fine_role_repairs'] = repairs
    with pytest.raises(ValueError, match='static defender repairs'):
        delta._reconstruct(base, request)
