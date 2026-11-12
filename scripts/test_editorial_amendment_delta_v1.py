"""Generic editorial amendment route: exact allowed-field writes, refusals, determinism, chaining.

Runs against the real preferred 2022/23 release read-only and in memory (no game is built here);
skipped when that local release is absent.
"""
import copy
import json
from types import SimpleNamespace

import pytest

from scripts import season_amendment_candidates_v1 as candidates
from scripts import season_editorial_amendment_delta_v1 as delta
from scripts import season_editorial_field_policy_v1 as policy
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from tools import season_manifest_amendments as amendments

SEASON = '2022-23'


@pytest.mark.parametrize('tamper', ['recipe', 'non_launch_asset'])
def test_candidate_integrity_checks_recipe_and_non_launch_assets(tmp_path, tamper):
    from scripts import pm99_season_amend_v1 as cli
    game = tmp_path / 'game'; game.mkdir()
    asset = game / 'unchanged-asset.dat'; asset.write_bytes(b'original asset')
    recipe = tmp_path / 'recipe.json'; recipe.write_text('{"editorial": 1}')
    inventory = tmp_path / 'inventory.json'
    pipeline.write_canonical_json(inventory, pipeline.build_tree_inventory(game))
    candidate = SimpleNamespace(game_path=game, inventory_path=inventory, package_path=recipe,
        locator=dict(package_canonical_sha256=registry.canonical_document_sha256(recipe)))
    cli.assert_candidate_integrity(candidate)
    if tamper == 'recipe':
        recipe.write_text('{"editorial": 2}')
    else:
        asset.write_bytes(b'changed asset')
    with pytest.raises(ValueError):
        cli.assert_candidate_integrity(candidate)


@pytest.fixture(scope='module')
def base():
    try:
        release = registry.load_preferred_release(SEASON)
        (release.game_path / 'DBDAT/JUG98030.FDI').stat()
    except Exception as exc:  # local-only game data
        pytest.skip(f'local {SEASON} release unavailable: {exc}')
    return release


@pytest.fixture(scope='module')
def package(base):
    return json.loads(base.package_path.read_text())


def outfield(package, *, name=None, club=None, skip=()):
    for index, p in enumerate(package['players']):
        if (p.get('carrier_family') == 'dd6361' and p['facts'].get('primary_position') in ('D', 'M', 'F')
                and isinstance(p['facts'].get('fine_roles'), list) and p['id'] not in skip
                and (name is None or p['name'] == name) and (club is None or p['club_id'] == club)):
            return index, p
    raise LookupError


def change(n, pointer, expected, new):
    return dict(id=f'change-{n:04d}', json_pointer=pointer, expected=expected, set=new, reason='test edit', evidence=None)


def request(*changes):
    return dict(origin='test', revision_id='working', season=SEASON, amendment_sha256='0' * 64, changes=list(changes))


@pytest.fixture(scope='module')
def scenario(base, package):
    """Position+rating on one player, scalar facts on another, a manager rename."""
    a_index, a = outfield(package, name='Joe Ackroyd')
    b_index, b = outfield(package, club=a['club_id'], skip={a['id']})
    taken = {p['facts']['shirt_number'] for p in package['players'] if p['club_id'] == b['club_id'] and isinstance(p['facts'].get('shirt_number'), int)}
    shirt = next(n for n in range(2, 99) if n not in taken)
    born = b['facts']['birth_date']
    new_born = born[:8] + ('02' if born[8:] != '02' else '03')
    mi, manager = next((i, m) for i, m in enumerate(package['managers']) if m.get('policy') == 'write' and m.get('native_names')
                       and len(m['name'].split()) == 2 and m['native_names']['surname'] == m['name'].split()[-1])
    new_manager = manager['name'].split()[0] + ' ' + manager['native_names']['surname'][::-1].capitalize()[:len(manager['native_names']['surname'])]
    old_position = a['facts']['primary_position']
    new_position = 'F' if old_position != 'F' else 'M'
    changes = [
        change(1, f'/players/{a_index}/facts/primary_position', old_position, new_position),
        change(2, f'/players/{a_index}/ratings/values/passing', a['ratings']['values']['passing'], 77 if a['ratings']['values']['passing'] != 77 else 78),
        change(3, f'/players/{b_index}/facts/shirt_number', b['facts']['shirt_number'], shirt),
        change(4, f'/players/{b_index}/facts/height_cm', b['facts']['height_cm'], b['facts']['height_cm'] + 1),
        change(5, f'/players/{b_index}/facts/weight_kg', b['facts']['weight_kg'], b['facts']['weight_kg'] + 1),
        change(6, f'/players/{b_index}/facts/birth_date', born, new_born),
        change(7, f'/managers/{mi}/name', manager['name'], new_manager),
    ]
    return SimpleNamespace(a=a, b=b, a_index=a_index, b_index=b_index, manager=manager, mi=mi, changes=changes,
                           new_position=new_position, shirt=shirt, new_born=new_born, new_manager=new_manager)


@pytest.fixture(scope='module')
def plan(base, scenario):
    return delta.prepare(base, request(*scenario.changes))


def update_for(plan, player):
    return next(u for u in plan['updates'] if u['carrier_id'] == player['carrier_id'])


def files(base):
    game = base.game_path / 'DBDAT'
    return [(game / n).read_bytes() for n in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI')]


def test_only_declared_fields_change_and_everything_else_is_identical(base, scenario, plan):
    jug, eq, ent = files(base)
    new_jug, new_eq = delta.apply(jug, eq, plan)
    new_ent = delta.apply_ent(ent, plan)
    assert new_eq == eq                                    # rosters, lineups, tactics untouched
    old, new = delta._entries(jug), delta._entries(new_jug)
    assert old.keys() == new.keys() and len(new_jug) == len(jug)
    changed = {c for c in old if old[c].decode_payload(jug) != new[c].decode_payload(new_jug)}
    assert changed == {scenario.a['carrier_id'], scenario.b['carrier_id']}
    a0, a1 = (delta._native_values(e[scenario.a['carrier_id']].decode_payload(j), scenario.a['carrier_id']) for e, j in ((old, jug), (new, new_jug)))
    assert (a0['position'], a1['position']) == (scenario.a['facts']['primary_position'], scenario.new_position)
    assert a1['ratings']['passing'] == scenario.changes[1]['set']
    assert all(a1['ratings'][k] == a0['ratings'][k] for k in a0['ratings'] if k != 'passing')
    assert all(delta.fifa.compatible(scenario.new_position, r) for r in a1['roles'])   # coherent coarse/fine role
    assert a1['roles'] == update_for(plan, scenario.a)['dependent_changes'][0]['after']
    assert (a1['nationality_code'], a1['birth_date'], a1['height_cm'], a1['shirt_number']) == (
        a0['nationality_code'], a0['birth_date'], a0['height_cm'], a0['shirt_number'])
    b0, b1 = (delta._native_values(e[scenario.b['carrier_id']].decode_payload(j), scenario.b['carrier_id']) for e, j in ((old, jug), (new, new_jug)))
    assert (b1['shirt_number'], b1['height_cm'], b1['weight_kg'], b1['birth_date']) == (
        scenario.shirt, b0['height_cm'] + 1, b0['weight_kg'] + 1, scenario.new_born)
    assert (b1['ratings'], b1['position'], b1['roles'], b1['nationality_code']) == (b0['ratings'], b0['position'], b0['roles'], b0['nationality_code'])
    # Every differing byte of the file lies inside a declared record byte (exact count, nothing else).
    declared = sum(len(u['native_bytes']) for u in plan['updates'])
    assert sum(x != y for x, y in zip(jug, new_jug)) == declared
    # ENT: exactly the one manager record may differ.
    ent_old, ent_new = delta._entries(ent), delta._entries(new_ent)
    differing = {c for c in ent_old if ent_old[c].decode_payload(ent) != ent_new[c].decode_payload(new_ent)}
    assert differing <= {scenario.manager['carrier_id']}


def test_manager_native_name_is_derived_and_reported(plan, scenario):
    row = plan['manager_updates'][0]
    assert row['after_name'] == scenario.new_manager and row['before_name'] == scenario.manager['name']
    assert row['after_native_names']['surname'] == delta._short_name(scenario.new_manager)


@pytest.mark.parametrize('name,short', [('Erik ten Hag', 'ten Hag'), ('Nuri Şahin', 'Sahin'), ('Graham Potter Jr', 'Potter'), ('Pep Guardiola', 'Guardiola')])
def test_manager_short_name_follows_existing_record_conventions(name, short):
    assert delta._short_name(name) == short


def test_plan_is_deterministic_and_application_is_idempotent(base, scenario, plan):
    again = delta.prepare(base, request(*copy.deepcopy(scenario.changes)))
    assert pipeline.canonical_json_bytes(again) == pipeline.canonical_json_bytes(plan)
    jug, eq, ent = files(base)
    once = delta.apply(jug, eq, plan)
    assert delta.apply(once[0], once[1], plan) == once == delta.apply(jug, eq, plan)
    assert delta.apply_ent(delta.apply_ent(ent, plan), plan) == delta.apply_ent(ent, plan)
    delta.verify(base, plan)
    tampered = copy.deepcopy(plan)
    field = next(f for f in update_for(tampered, scenario.a)['fields'] if f['field'] == 'primary_position')
    field['after'] = 'D' if field['after'] != 'D' else 'M'
    with pytest.raises(ValueError):
        delta.verify(base, tampered)


def test_recipe_changes_only_the_declared_fields_and_is_labelled_editorial(base, package, plan, scenario):
    result = delta.bind(package, plan)
    packages.validate_package(result)
    before, after = package, result

    def differences(a, b, path=''):
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a or key not in b:
                    yield f'{path}/{key}'
                else:
                    yield from differences(a[key], b[key], f'{path}/{key}')
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b) and all(isinstance(x, dict) for x in a):
            for i, (x, y) in enumerate(zip(a, b)):
                yield from differences(x, y, f'{path}/{i}')
        elif a != b:
            yield path
    paths = set(differences(before, after))
    a, b = scenario.a_index, scenario.b_index
    allowed = {f'/players/{a}/facts/primary_position', f'/players/{a}/facts/fine_roles', f'/players/{a}/ratings/values/passing',
               f'/players/{a}/ratings/provenance/method', f'/players/{a}/ratings/provenance/proof_grade',
               f'/players/{a}/ratings/provenance/source_ids',
               f'/players/{b}/facts/shirt_number', f'/players/{b}/facts/height_cm', f'/players/{b}/facts/weight_kg',
               f'/players/{b}/facts/birth_date', f'/managers/{scenario.mi}/name', '/artifacts', '/sources'}
    nested = {p for p in paths if p.startswith('/managers/') and p.startswith(f'/managers/{scenario.mi}/native_names')}
    assert paths - nested <= allowed, sorted(paths - nested - allowed)
    assert any(s['id'] == delta.source_id(plan) and s['proof_grade'] == 'reviewed-editorial' and 'not source evidence' in s['title']
               for s in result['sources'])            # human editorial change, honestly labelled
    with pytest.raises(ValueError, match='source-bound reconstruction'):
        delta.reject_factory_recipe(result)               # never factory-compiled from a clean base


@pytest.mark.parametrize('build,fragment', [
    (lambda s, p: change(1, f'/players/{s.a_index}/ratings/values/passing', s.a['ratings']['values']['passing'] + 1, 50), 'stale'),
    (lambda s, p: change(1, f'/players/{s.a_index}/ratings/values/passing', s.a['ratings']['values']['passing'], 0), 'whole number'),
    (lambda s, p: change(1, f'/players/{s.a_index}/ratings/values/passing', s.a['ratings']['values']['passing'], 100), 'whole number'),
    (lambda s, p: change(1, f'/players/{s.a_index}/ratings/values/passing', s.a['ratings']['values']['passing'], 70.5), 'whole number'),
    (lambda s, p: change(1, f'/players/{s.a_index}/facts/primary_position', s.a['facts']['primary_position'], 'G'), 'goalkeeper'),
    (lambda s, p: change(1, f'/players/{s.a_index}/facts/primary_position', s.a['facts']['primary_position'], 'X'), 'goalkeeper'),
    (lambda s, p: change(1, f'/players/{s.a_index}/name', s.a['name'], 'Someone Else'), 'name'),
    (lambda s, p: change(1, '/clubs/0/manager_id', p['clubs'][0].get('manager_id'), 'manager-1'), 'relational'),
    (lambda s, p: change(1, '/clubs/0/name', p['clubs'][0]['name'], 'New Club'), 'club label'),
    (lambda s, p: change(1, f'/players/{s.a_index}/facts/fine_roles', s.a['facts']['fine_roles'], [1]), 'unsupported player fact'),
    (lambda s, p: change(1, f'/players/{s.a_index}/ratings/values/nonsense', 1, 2), 'unsupported rating key'),
    (lambda s, p: change(1, f'/players/{s.a_index}/facts/shirt_number', s.a['facts']['shirt_number'], s.b['facts']['shirt_number']) if s.a['club_id'] == s.b['club_id'] else None, 'already worn'),
    (lambda s, p: change(1, f'/players/{s.a_index}/facts/birth_date', s.a['facts']['birth_date'], 'not-a-date'), 'YYYY-MM-DD'),
    (lambda s, p: change(1, f'/players/{s.a_index}/facts/height_cm', s.a['facts']['height_cm'], 300), 'whole number'),
    (lambda s, p: change(1, f'/players/{s.a_index}/facts/nationality', s.a['facts']['nationality'], 'XXX'), 'not representable'),
    (lambda s, p: change(1, f'/managers/{s.mi}/name', s.manager['name'], ' padded '), 'surrounding spaces'),
    (lambda s, p: change(1, f'/managers/{s.mi}/name', s.manager['name'], 'Ωmega Boss'), 'codepage'),
    (lambda s, p: change(1, '/players/99999999/facts/shirt_number', 1, 2), 'stale index'),
])
def test_stale_unsupported_and_invalid_edits_are_refused(base, package, scenario, build, fragment):
    row = build(scenario, package)
    if row is None:
        pytest.skip('scenario players are at different clubs')
    with pytest.raises(ValueError, match=fragment):
        delta.prepare(base, request(row))


def test_no_op_duplicate_and_preserved_records_are_refused(base, package, scenario):
    with pytest.raises(ValueError, match='does not change'):
        delta.prepare(base, request(change(1, f'/players/{scenario.a_index}/ratings/values/passing', 58, 58)))
    pointer = f'/players/{scenario.a_index}/ratings/values/passing'
    value = scenario.a['ratings']['values']['passing']
    with pytest.raises(ValueError, match='duplicate'):
        delta.prepare(base, request(change(1, pointer, value, 60), change(2, pointer, value, 61)))
    mode1 = next(i for i, p in enumerate(package['players']) if isinstance(p['facts'].get('primary_position'), dict))
    with pytest.raises(ValueError):
        delta.prepare(base, request(change(1, f'/players/{mode1}/facts/shirt_number', package['players'][mode1]['facts'].get('shirt_number'), 5)))
    foreign = next(i for i, m in enumerate(package['managers']) if m.get('policy') != 'write')
    with pytest.raises(ValueError, match='preserved/foreign'):
        delta.prepare(base, request(change(1, f'/managers/{foreign}/name', package['managers'][foreign]['name'], 'New Name')))


def test_birth_year_limit_depends_on_the_release_executable(base, scenario):
    import dataclasses
    row = change(1, f'/players/{scenario.b_index}/facts/birth_date', scenario.b['facts']['birth_date'], '2101-01-01')
    with pytest.raises(ValueError, match='birth year'):
        delta.prepare(base, request(row))
    # A release without the modern-birth-year executable guard may not take years after 1999.
    legacy = dataclasses.replace(base, locator={k: v for k, v in base.locator.items() if k != 'sourced_birth_year_plan_path'})
    with pytest.raises(ValueError, match='1930-1999'):
        delta.prepare(legacy, request(change(1, f'/players/{scenario.b_index}/facts/birth_date', scenario.b['facts']['birth_date'], '2001-01-01')))


def test_position_edit_keeps_fine_role_coherent_not_just_the_coarse_byte(base, package, scenario):
    """A defender moved to forward cannot keep a sweeper/back role active."""
    index, defender = next((i, p) for i, p in outfield(package, skip=()) and enumerate(package['players'])
        if p.get('carrier_family') == 'dd6361' and p['facts'].get('primary_position') == 'D'
        and isinstance(p['facts'].get('fine_roles'), list) and all(r in (1, 2, 3, 4, 5) for r in p['facts']['fine_roles']))
    plan = delta.prepare(base, request(change(1, f'/players/{index}/facts/primary_position', 'D', 'F')))
    after = plan['updates'][0]['dependent_changes'][0]['after']
    assert after == delta.DEFAULT_FINE_ROLES['F'] and not set(after) & {1, 2, 3, 4, 5}
    jug, eq, _ = files(base)
    new_jug, _ = delta.apply(jug, eq, plan)
    row = delta._native_values(delta._entries(new_jug)[defender['carrier_id']].decode_payload(new_jug), defender['carrier_id'])
    assert row['position'] == 'F' and row['roles'] == after


def test_edited_release_is_a_valid_parent_for_the_next_edit(base, package, plan, scenario, tmp_path):
    """Chain: parent -> child (plan applied) -> grandchild planned over the child's real bytes and recipe."""
    jug, eq, ent = files(base)
    child_jug, _ = delta.apply(jug, eq, plan)
    child_ent = delta.apply_ent(ent, plan)
    child_package = delta.bind(package, plan)
    game = tmp_path / 'game/DBDAT'
    game.mkdir(parents=True)
    (game / 'JUG98030.FDI').write_bytes(child_jug)
    (game / 'EQ98030.FDI').write_bytes(eq)
    (game / 'ENT98030.FDI').write_bytes(child_ent)
    (game / 'TEXTOS.PKF').write_bytes((base.game_path / 'DBDAT/TEXTOS.PKF').read_bytes())
    (tmp_path / 'season-package.json').write_bytes(packages.canonical_json_bytes(child_package))
    child = SimpleNamespace(season=SEASON, release_id='edited-child', manifest_sha256='c' * 64, locator=base.locator,
                            package_path=tmp_path / 'season-package.json', game_path=tmp_path / 'game')
    a = scenario.a_index
    # The child's recipe now holds the edited values: re-editing from the OLD value is stale...
    with pytest.raises(ValueError, match='stale'):
        delta.prepare(child, request(change(1, f'/players/{a}/ratings/values/passing', scenario.a['ratings']['values']['passing'], 60)))
    # ...and the new edit starts from the child's value and leaves the parent's earlier edits in place.
    edited = scenario.changes[1]['set']
    second = delta.prepare(child, request(change(1, f'/players/{a}/ratings/values/passing', edited, 61),
                                         change(2, f'/players/{a}/facts/primary_position', scenario.new_position, scenario.a['facts']['primary_position'])))
    assert second['release_id'] == 'edited-child' and second['jug_sha256'] == delta.digest(child_jug)
    grandchild, _jug, _ = delta._derive(child, second['request'])
    values = delta._native_values(delta._entries(_jug)[scenario.a['carrier_id']].decode_payload(_jug), scenario.a['carrier_id'])
    assert values['ratings']['passing'] == 61 and values['position'] == scenario.a['facts']['primary_position']
    old_child = delta._entries(child_jug)
    new = delta._entries(_jug)
    assert {c for c in old_child if old_child[c].decode_payload(child_jug) != new[c].decode_payload(_jug)} == {scenario.a['carrier_id']}
    # The first edit's other bytes (player B's scalars, manager name) survive into the grandchild.
    b1 = delta._native_values(new[scenario.b['carrier_id']].decode_payload(_jug), scenario.b['carrier_id'])
    assert (b1['shirt_number'], b1['birth_date']) == (scenario.shirt, scenario.new_born)


def test_policy_classification_matches_what_the_workbook_offers():
    assert policy.classify('/players/3/ratings/values/speed') == ('player-rating', 3, 'speed')
    assert policy.classify('/players/3/facts/primary_position') == ('player-fact', 3, 'primary_position')
    assert policy.classify('/managers/4/name') == ('manager-name', 4, 'name')
    for bad in ('/players/3/name', '/clubs/1/name', '/clubs/1/manager_id', '/managers/4/carrier_id', '/players/3/facts/fine_roles', '/kits/0/x'):
        assert not policy.supported(bad) and policy.reason_unsupported(bad)


# --- CLI/service ---------------------------------------------------------------------

@pytest.fixture
def cli(tmp_path, monkeypatch):
    from scripts import pm99_season_amend_v1 as amend
    monkeypatch.setattr(amend, 'BUILDS_ROOT', tmp_path / 'builds')
    monkeypatch.setattr(candidates, 'BUILDS_ROOT', tmp_path / 'builds')
    monkeypatch.setattr(amend.candidates, 'BUILDS_ROOT', tmp_path / 'builds')
    return amend


def document(base, *rows, manifest=None, sha=None):
    doc = amendments.empty_document(SEASON)
    for row in rows:
        doc = amendments.stage_change(doc, manifest_id=manifest or f'preferred-release/{base.release_id}/season-package.json',
            manifest_sha256=sha or registry.sha256_file(base.package_path), json_pointer=row['json_pointer'],
            expected=row['expected'], replacement=row['set'], reason=row['reason'], evidence=None)
    return doc


def test_cli_dry_run_reports_exact_edits_and_builds_nothing(base, scenario, cli, tmp_path):
    before_catalog = registry.sha256_file(registry.CATALOG_PATH)
    report = cli.apply_amendments(SEASON, document=document(base, *scenario.changes), dry_run=True)
    assert report['status'] in ('planned', 'planned-blocked-by-disk') and report['dry_run'] is True
    assert report['preferred_changed'] is False and report['registered_as_preferred'] is False
    assert report['candidate_release_id'].startswith('edited-2022-23-') and len(report['summary']) == 3
    assert any('fine_roles' in d for row in report['summary'] for d in row['dependent'])
    assert registry.sha256_file(registry.CATALOG_PATH) == before_catalog
    assert not registry.locator_path(SEASON, report['candidate_release_id']).parent.exists()
    saved = json.loads((tmp_path / 'builds' / SEASON / report['transaction_id'] / 'plan.json').read_text())
    assert saved['schema'] == delta.SCHEMA
    # Same staged edits -> same candidate id and transaction (deterministic).
    again = cli.apply_amendments(SEASON, document=document(base, *scenario.changes), dry_run=True)
    assert (again['candidate_release_id'], again['transaction_id']) == (report['candidate_release_id'], report['transaction_id'])


def test_cli_rejects_stale_hash_other_manifests_and_unsupported_edits(base, scenario, cli):
    good = scenario.changes[1]
    with pytest.raises(cli.AmendmentBuildError) as stale:
        cli.apply_amendments(SEASON, document=document(base, good, sha='f' * 64), dry_run=True)
    assert stale.value.status == 'stale' and 're-stage' in str(stale.value)
    with pytest.raises(cli.AmendmentBuildError) as none:
        cli.apply_amendments(SEASON, document=document(base, good, manifest='runtime-recipe/old.json'), dry_run=True)
    assert none.value.status == 'nothing-to-build' and none.value.details['ignored'][0]['manifest_id'] == 'runtime-recipe/old.json'
    mixed = document(base, good)
    mixed = amendments.stage_change(mixed, manifest_id='runtime-recipe/old.json', manifest_sha256='a' * 64, json_pointer='/x/0', expected=1,
                                    replacement=2, reason='other manifest', evidence=None)
    report = cli.apply_amendments(SEASON, document=mixed, dry_run=True)
    assert [r['manifest_id'] for r in report['ignored_changes']] == ['runtime-recipe/old.json'] and report['applied_change_ids'] == ['change-0001']
    bad = dict(json_pointer=f'/players/{scenario.a_index}/name', expected=scenario.a['name'], set='Renamed Player', reason='x')
    with pytest.raises(cli.AmendmentBuildError, match='name edits are not carried'):
        cli.apply_amendments(SEASON, document=document(base, bad), dry_run=True)


def test_cli_refuses_to_build_when_the_disk_reserve_would_be_breached(base, scenario, cli):
    with pytest.raises(cli.AmendmentBuildError) as blocked:
        cli.apply_amendments(SEASON, document=document(base, scenario.changes[1]), minimum_free_bytes=10 ** 15)
    assert blocked.value.status == 'blocked-by-disk' and blocked.value.details['disk']['shortfall_bytes'] > 0
    assert not registry.locator_path(SEASON, blocked.value.details['candidate_release_id']).parent.exists()
    with pytest.raises(ValueError, match='at least 6 GiB'):
        cli.apply_amendments(SEASON, document=document(base, scenario.changes[1]), minimum_free_bytes=1)   # guard is not lowered


def test_receipt_must_match_the_exact_staged_document(base, scenario, cli, tmp_path):
    doc = document(base, scenario.changes[1])
    working = tmp_path / 'working.json'
    amendments.write_document(working, doc)
    receipt = dict(schema_version=amendments.RECEIPT_SCHEMA, season=SEASON,
                   amendment_sha256=amendments.sha256_bytes(amendments.canonical_json_bytes(doc)), outputs=[], change_count=1)
    receipt_path = tmp_path / 'amendment-receipt.json'
    receipt_path.write_text(json.dumps(receipt))
    loaded, origin = cli.load_document(SEASON, amendments_path=working, receipt_path=receipt_path)
    assert origin == 'hash-bound-materialisation-receipt' and loaded == doc
    receipt['amendment_sha256'] = '0' * 64
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(cli.AmendmentBuildError, match='changed after materialising'):
        cli.load_document(SEASON, amendments_path=working, receipt_path=receipt_path)
    with pytest.raises(cli.AmendmentBuildError, match='no staged amendments'):
        cli.load_document(SEASON, amendments_path=tmp_path / 'missing.json')


def test_play_can_target_a_registered_unpreferred_candidate_without_changing_the_catalogue():
    import subprocess
    import sys
    candidate = next((c['release_id'] for c in candidates.list_candidates(SEASON, registry.ROOT / '.local/season-amendment-builds-v1')), None)
    if candidate is None:
        pytest.skip('no locally built candidate to address')
    before = registry.sha256_file(registry.CATALOG_PATH)
    out = subprocess.run([sys.executable, str(registry.ROOT / 'scripts/pm99_season_play_v1.py'), SEASON, '--release-id', candidate, '--print-command'],
                         capture_output=True, text=True, cwd=registry.ROOT, env=dict(__import__('os').environ, PYTHONPATH=''))
    assert out.returncode == 0 and candidate in out.stdout and out.stdout.strip().endswith('wine ./MANAGPRE.EXE')
    bad = subprocess.run([sys.executable, str(registry.ROOT / 'scripts/pm99_season_play_v1.py'), SEASON, '--release-id', 'no-such-release', '--print-command'],
                         capture_output=True, text=True, cwd=registry.ROOT)
    assert bad.returncode != 0
    assert registry.sha256_file(registry.CATALOG_PATH) == before


# --- round 2: record-specific gating, bounded cache, honest build outcomes --------------------------------

def find_player(package, carrier):
    for index, p in enumerate(package['players']):
        if p['carrier_id'] == carrier:
            return index, p
    pytest.skip(f'carrier {carrier} is not in the local recipe')


def test_unrelated_unknown_or_preserved_facts_do_not_block_a_rating_edit(base, package):
    """Sparrow has an unknown weight and Casemiro a preserved shirt; neither blocks an edit of a different field."""
    for carrier in (10349, 4019):
        index, player = find_player(package, carrier)
        assert any(isinstance(v, dict) for v in player['facts'].values())        # the premise: an unrelated unknown/preserved fact
        old = player['ratings']['values']['passing']
        plan = delta.prepare(base, request(change(1, f'/players/{index}/ratings/values/passing', old, old - 1 if old > 1 else 2)))
        row = plan['updates'][0]
        assert len(row['native_bytes']) == 1                                      # exactly one skill byte
        assert row['native_after']['ratings']['passing'] == plan['updates'][0]['fields'][0]['after']
        jug, eq, _ = files(base)
        new_jug, new_eq = delta.apply(jug, eq, plan)
        assert new_eq == eq and sum(a != b for a, b in zip(jug, new_jug)) == 1
        bound = delta.bind(package, plan)
        # the untouched unknown/preserved facts are carried over exactly
        assert bound['players'][index]['facts'] == player['facts']


def test_the_edited_field_itself_is_still_gated_on_its_own_record_format(base, package):
    index, sparrow = find_player(package, 10349)
    unknown = next(k for k, v in sparrow['facts'].items() if isinstance(v, dict))
    for field, fragment in ((unknown, 'unknown/preserved'),):
        with pytest.raises(ValueError, match=fragment):
            delta.prepare(base, request(change(1, f'/players/{index}/facts/{field}', sparrow['facts'][field], 70)))
    index, casemiro = find_player(package, 4019)
    shirt = casemiro['facts']['shirt_number']
    assert isinstance(shirt, dict)
    with pytest.raises(ValueError, match='unknown/preserved|dd6361'):
        delta.prepare(base, request(change(1, f'/players/{index}/facts/shirt_number', shirt, 9)))


def test_compact_dd6360_shirt_and_position_and_goalkeepers_are_refused_with_record_reasons(package):
    compact = copy.deepcopy(next(p for p in package['players'] if p.get('carrier_family') == 'dd6360'))
    compact['facts']['shirt_number'] = 9
    compact['facts']['primary_position'], compact['facts']['fine_roles'] = 'M', [9]
    assert 'dd6361' in policy.record_reason('player-fact', compact, 'primary_position')
    assert 'dd6361' in policy.record_reason('player-fact', compact, 'shirt_number')
    assert policy.record_reason('player-rating', compact, 'passing') is None
    keeper = next(p for p in package['players'] if p.get('carrier_family') == 'dd6361' and p['facts'].get('primary_position') == 'G')
    assert 'goalkeeper' in policy.record_reason('player-fact', keeper, 'primary_position')
    assert policy.record_reason('player-rating', keeper, 'handling') is None
    foreign = next(m for m in package['managers'] if m.get('policy') != 'write')
    assert 'preserved/foreign' in policy.record_reason('manager-name', foreign, 'name')
    assert policy.record_reason('player-fact', {'carrier_family': 'dd6361', 'facts': {'primary_position': 'D', 'fine_roles': {'policy': 'x'}}}, 'primary_position')


def test_2015_dd6360_rating_edit_plans_when_native_agrees():
    try:
        old = registry.load_preferred_release('2015-16')
        package = json.loads(old.package_path.read_text())
        (old.game_path / 'DBDAT/JUG98030.FDI').stat()
    except Exception as exc:
        pytest.skip(f'2015/16 release unavailable: {exc}')
    index, varane = next(((i, p) for i, p in enumerate(package['players']) if 'Varane' in p['name'] and p.get('carrier_family') == 'dd6360'), (None, None))
    if varane is None:
        pytest.skip('no dd6360 Varane in the local 2015 recipe')
    value = varane['ratings']['values']['passing']
    plan = delta.prepare(old, dict(request(change(1, f'/players/{index}/ratings/values/passing', value, value - 1)), season='2015-16'))
    assert len(plan['updates'][0]['native_bytes']) == 1 and plan['updates'][0]['family'] == 'dd6360'   # dry plan only; nothing written


class Fake:
    """A copy-on-disk parent release for cache/stale-byte tests (the real release is never modified)."""

    def __init__(self, base, tmp_path):
        import shutil
        self.season, self.release_id, self.manifest_sha256 = base.season, 'fake-parent', 'd' * 64
        self.locator = dict(base.locator)
        self.package_path, self.game_path = tmp_path / 'season-package.json', tmp_path / 'game'
        (self.game_path / 'DBDAT').mkdir(parents=True)
        shutil.copy(base.package_path, self.package_path)
        for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'TEXTOS.PKF'):
            shutil.copy(base.game_path / 'DBDAT' / name, self.game_path / 'DBDAT' / name)


def test_cache_is_bounded_and_every_hit_revalidates_its_preimage(base, package, scenario, tmp_path):
    fake = Fake(base, tmp_path)
    req = request(scenario.changes[1])
    first = delta.prepare(fake, req)
    assert delta.prepare(fake, req)['transaction_id'] == first['transaction_id']          # genuine hit
    # Stale bytes: change an UNRELATED native player byte after the plan was cached.
    jug = bytearray((fake.game_path / 'DBDAT/JUG98030.FDI').read_bytes())
    other = next(e for c, e in delta._entries(bytes(jug)).items() if c != scenario.a['carrier_id'])
    jug[other.payload_offset + 9] ^= 0x01
    (fake.game_path / 'DBDAT/JUG98030.FDI').write_bytes(bytes(jug))
    second = delta.prepare(fake, req)
    assert second['jug_sha256'] == delta.digest(bytes(jug)) != first['jug_sha256']       # re-derived from the new bytes, not served stale
    assert second['transaction_id'] != first['transaction_id']
    # A cached plan for the old bytes must not be applied to the new ones.
    with pytest.raises(ValueError, match='preimage'):
        delta._checked_against(fake, first)
    # Recipe drift is caught on a hit too.
    changed = json.loads(fake.package_path.read_text())
    changed['players'][scenario.a_index]['ratings']['values']['passing'] += 3
    fake.package_path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='stale'):
        delta.prepare(fake, req)
    # Locator change relevant to the plan (birth-year guard) is part of the fingerprint.
    fake.package_path.write_bytes(base.package_path.read_bytes())
    delta.prepare(fake, req)
    before = delta._source_fingerprint(fake)
    fake.locator.pop('sourced_birth_year_plan_path', None)
    assert delta._source_fingerprint(fake) != before


def test_cache_never_holds_more_than_its_limit(base, package, scenario, tmp_path):
    fake = Fake(base, tmp_path)
    for n in (60, 61, 62, 63):
        delta.prepare(fake, request(change(1, f'/players/{scenario.a_index}/ratings/values/passing', scenario.a['ratings']['values']['passing'], n)))
    assert len(delta._CACHE) <= delta.CACHE_LIMIT


# --- CLI outcomes: failures are failures, history is kept -----------------------------------------------

DEMO_WORKING = registry.ROOT / '.local/amendment-demo-20261112/seasons-2022-23/2022-23/editorial-amendments/working.json'
DEMO_CANDIDATE = 'edited-2022-23-5be1905c4161'


@pytest.fixture
def demo(cli):
    try:
        registry.load_registered_release(SEASON, DEMO_CANDIDATE)
        doc = amendments.load_or_empty(DEMO_WORKING, season=SEASON)
    except Exception as exc:
        pytest.skip(f'demonstration candidate unavailable: {exc}')
    return doc


def passing_proof():
    return dict(complete_game_inventory_identical=True, complete_recipe_identical=True, release_id=DEMO_CANDIDATE + '-src')


def test_failed_playable_validation_is_not_success_and_offers_no_play_command(demo, cli, monkeypatch, tmp_path):
    real = registry.validate_preferred_release
    monkeypatch.setattr(registry, 'validate_preferred_release', lambda *a, **k: dict(real(*a, **k), valid=False, missing=['MANAGPRE.EXE']))
    with pytest.raises(cli.AmendmentBuildError) as failed:
        cli.apply_amendments(SEASON, document=demo, minimum_free_bytes=6 * 1024 ** 3)
    assert failed.value.status == 'validation-failed' and 'not usable' in str(failed.value)
    report = failed.value.details
    assert report['status'] == 'validation-failed' and 'play_command' not in report
    assert json.loads((tmp_path / 'builds' / SEASON / report['transaction_id'] / 'build-report.json').read_text())['status'] == 'validation-failed'
    assert candidates.list_candidates(SEASON, tmp_path / 'builds') == []                 # never listed as a usable candidate


def test_failed_requested_verification_is_failure_with_evidence_and_no_play_command(demo, cli, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, '_registered', lambda season, rid: False)
    def broken(*args, **kwargs):
        raise ValueError('rebuild differs from the candidate')
    monkeypatch.setattr(cli.editorial, 'reconstruction', broken)
    with pytest.raises(cli.AmendmentBuildError) as failed:
        cli.apply_amendments(SEASON, document=demo, verify_reconstruction=True, minimum_free_bytes=6 * 1024 ** 3)
    assert failed.value.status == 'verification-failed' and 'rebuild differs' in str(failed.value)
    report = failed.value.details
    assert report['source_reconstruction']['error'] == 'rebuild differs from the candidate' and 'play_command' not in report
    assert report['verified_in_this_run'] is True and len(report['verification_history']) == 1
    stored = tmp_path / 'builds' / SEASON / report['transaction_id'] / 'verifications' / report['verification_history'][0]
    assert 'error' in json.loads(stored.read_text())                                        # the failed attempt is itself retained
    assert candidates.list_candidates(SEASON, tmp_path / 'builds') == []
    # A reconstruction that "succeeds" without proving equality is also a failure.
    monkeypatch.setattr(cli.editorial, 'reconstruction', lambda *a, **k: dict(complete_game_inventory_identical=True))
    with pytest.raises(cli.AmendmentBuildError, match='FAILED'):
        cli.apply_amendments(SEASON, document=demo, verify_reconstruction=True, minimum_free_bytes=6 * 1024 ** 3)


def test_repeat_requests_keep_prior_proof_and_never_claim_a_new_verification(demo, cli, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, '_registered', lambda season, rid: True)
    monkeypatch.setattr(cli, '_compare_existing_check', lambda *a: passing_proof())
    first = cli.apply_amendments(SEASON, document=demo, verify_reconstruction=True, minimum_free_bytes=6 * 1024 ** 3)
    assert first['status'] == 'already-built' and first['verified_in_this_run'] is True and first['built_this_run'] is False
    proof_name = first['verification_history'][0]
    # Repeat WITHOUT --verify-reconstruction (and a dry run): the earlier exact matching proof is carried, not re-claimed.
    again = cli.apply_amendments(SEASON, document=demo, dry_run=True, minimum_free_bytes=6 * 1024 ** 3)
    proof = again['source_reconstruction']
    assert proof['verified_in_this_run'] is False and proof['carried_forward_from'] == proof_name and again['verified_in_this_run'] is False
    assert again['dry_run'] is True and again['built_this_run'] is False
    # The earlier report was archived by content hash, not lost; the verification record is immutable.
    evidence = tmp_path / 'builds' / SEASON / first['transaction_id']
    archived = [json.loads(p.read_text()) for p in (evidence / 'history').glob('build-report-*.json')]
    assert any(a.get('verified_in_this_run') is True and a['source_reconstruction']['complete_recipe_identical'] for a in archived)
    assert len(list((evidence / 'verifications').glob('*.json'))) == 1
    # A repeat with nothing earlier to carry says so instead of inventing a proof.
    for p in (evidence / 'verifications').glob('*.json'):
        p.unlink()
    (evidence / 'verifications').rmdir()
    (evidence / 'build-report.json').unlink()
    fresh = cli.apply_amendments(SEASON, document=demo, minimum_free_bytes=6 * 1024 ** 3)
    assert fresh['source_reconstruction'] is None and fresh['verified_in_this_run'] is False


def test_legacy_report_proof_is_kept_as_history_without_claiming_it_ran_now(demo, cli, tmp_path):
    first = cli.apply_amendments(SEASON, document=demo, dry_run=True, minimum_free_bytes=6 * 1024 ** 3)
    evidence = tmp_path / 'builds' / SEASON / first['transaction_id']
    old = json.loads((evidence / 'build-report.json').read_text())
    old['source_reconstruction'] = passing_proof()
    (evidence / 'build-report.json').write_text(json.dumps(old))
    carried = cli.apply_amendments(SEASON, document=demo, dry_run=True, minimum_free_bytes=6 * 1024 ** 3)
    assert carried['source_reconstruction']['verified_in_this_run'] is False and carried['source_reconstruction']['imported_from']


def test_a_check_on_an_existing_candidate_says_nothing_was_built(demo, cli):
    report = cli.apply_amendments(SEASON, document=demo, dry_run=True, minimum_free_bytes=6 * 1024 ** 3)
    assert report['status'] == 'already-built' and report['dry_run'] is True and report['built_this_run'] is False
    assert report['candidate_release_id'] == DEMO_CANDIDATE


def test_candidate_can_be_the_parent_of_the_next_edit_and_wrong_manifests_fail_explicitly(demo, package, cli):
    child = registry.load_registered_release(SEASON, DEMO_CANDIDATE)
    child_package = json.loads(child.package_path.read_text())
    index = next(i for i, p in enumerate(child_package['players']) if p['name'] == 'Joe Ackroyd')
    value = child_package['players'][index]['ratings']['values']['shooting']
    row = dict(json_pointer=f'/players/{index}/ratings/values/shooting', expected=value, set=value + 1, reason='chain')
    right = document(child, row)
    report = cli.apply_amendments(SEASON, document=right, parent_id=DEMO_CANDIDATE, dry_run=True, minimum_free_bytes=6 * 1024 ** 3)
    assert report['parent_release_id'] == DEMO_CANDIDATE and report['status'] in ('planned', 'planned-blocked-by-disk')
    assert report['preferred_release_id'] != DEMO_CANDIDATE and report['summary'][0]['edits'] == [f'shooting: {value} -> {value + 1}']
    # Staged against the preferred recipe but built on the candidate: refused, naming what it was staged against.
    parent_doc = document(registry.load_preferred_release(SEASON), row)
    with pytest.raises(cli.AmendmentBuildError, match='Staged against other manifests') as wrong:
        cli.apply_amendments(SEASON, document=parent_doc, parent_id=DEMO_CANDIDATE, dry_run=True)
    assert wrong.value.status == 'nothing-to-build'
    # Staged against a different revision of the same manifest id: stale.
    with pytest.raises(cli.AmendmentBuildError) as stale:
        cli.apply_amendments(SEASON, document=document(child, row, sha='e' * 64), parent_id=DEMO_CANDIDATE, dry_run=True)
    assert stale.value.status == 'stale'
