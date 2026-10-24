"""Unique source policy for annual broad positions and editorial fine roles.

Plans use a separate schema, proof language, and SOURCE replay mode. The
existing native writer is called only through a private in-memory bridge for
the approved byte fields; its exact-FIFA plan schema and claims are not reused.
Publication and SOURCE replay retain the exact registered parent.
"""
import csv
import copy
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_exact_primary_position_delta_v2 as native_writer
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_exact_fifa_role_delta_v1 as fifa_roles
from scripts import season_package_v2 as packages
from scripts.season_within_club_reserve_repair_v1 import native_facts

ROOT = registry.ROOT
INPUT = ROOT / '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/annual-position-role-candidate-v1.json'
FIFA = ROOT / '.local/external-sources/sofifa-fifa16/male_players_legacy.csv'
SCHEMA = 'pm99-source-bound-annual-broad-position-editorial-fine-role-v1'
POLICY = 'annual-source-broad-position-editorial-compatible-fine-role-v1'
MODE = 'known-good-baseline-annual-source-broad-position-editorial-fine-role-v1'
PREFIX = 'source-bound-annual-position-role-'
_FIFA_ROWS_BY_SHA = {}


def filename(plan):
    if plan.get('schema') != SCHEMA or plan.get('policy') != POLICY:
        raise ValueError('unsupported annual role plan')
    return 'annual-source-role-plan-' + plan['transaction_id'] + '.json'


def artifact_id(plan):
    return PREFIX + plan['transaction_id']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _annual_row(change):
    if change['annual_source'].get('role_only_witness_not_opening_ownership_or_august_membership') is not True:
        raise ValueError('annual role source cannot be promoted into an opening ownership claim')
    ds = ROOT / change['annual_source']['dataset']
    raw = ROOT / change['annual_source']['source_file']
    if sha(ds) != change['annual_source']['dataset_sha256']:
        raise ValueError('annual dataset hash differs')
    dataset = json.loads(ds.read_text(encoding='utf-8'))
    if (dataset.get('schema_version') != 'pm99-footballsquads-season-capture-v1'
            or dataset.get('season', {}).get('label') != change['season'][:4] + '/' + change['season'][-2:]
            or dataset.get('source', {}).get('repository') != 'https://github.com/footballcsv/cache.footballsquads'):
        raise ValueError('annual source dataset identity/period differs')
    if sha(raw) != change['annual_source']['source_file_sha256']:
        raise ValueError('retained original annual source file hash differs')
    selected = change['annual_source']['source_row']
    expected = []
    for club in dataset['clubs']:
        if (club.get('source_path') == raw.relative_to(ROOT / '.local/external-sources/cache.footballsquads').as_posix()
                and club.get('source_sha256') == change['annual_source']['source_file_sha256']):
            for player in club['players']:
                if (player.get('name') == selected['name']
                        and player.get('birth_date') == selected['birth_date']
                        and player.get('position') == selected['position']):
                    expected.append((club, player))
    if (len(expected) != 1 or expected[0][0]['club_name'] != selected['source_club']):
        raise ValueError('annual source must resolve exactly one full-name/DOB/position row')
    rows = []
    for fields in csv.reader(raw.read_text(encoding='utf-8-sig').splitlines()):
        if len(fields) < 8 or fields[1].strip() != selected['name']:
            continue
        try:
            born = datetime.strptime(fields[6].strip(), '%d-%m-%y').date().isoformat()
        except ValueError:
            continue
        if born == selected['birth_date']:
            rows.append(fields)
    if (len(rows) != 1 or rows[0][3].strip() != selected['position']
            or rows[0][-1].strip() != selected['printed_club_field']):
        raise ValueError('original annual text row differs from captured full-name/DOB/role row')
    return dict(dataset_path=ds.relative_to(ROOT).as_posix(), dataset_sha256=sha(ds),
        source_file_path=raw.relative_to(ROOT).as_posix(), source_file_sha256=sha(raw),
        captured_club=expected[0][0]['club_name'], source_path=expected[0][0]['source_path'],
        source_line=rows[0], player=expected[0][1])


def _fifa_row(change):
    file_hash = sha(FIFA)
    if file_hash != change['corroboration']['fifa_file_sha256']:
        raise ValueError('retained FIFA legacy file hash differs')
    wanted = change['corroboration']['record']
    key = (file_hash, wanted['fifa_version'], wanted['player_id'])
    matches = _FIFA_ROWS_BY_SHA.get(key)
    if matches is None:
        fields = ('fifa_version', 'fifa_update_date', 'player_id', 'long_name', 'dob', 'player_positions')
        with FIFA.open(encoding='utf-8-sig', newline='') as stream:
            matches = [{name: row[name] for name in fields} for row in csv.DictReader(stream)
                       if row['fifa_version'] == wanted['fifa_version']
                       and row['player_id'] == wanted['player_id']]
        _FIFA_ROWS_BY_SHA[key] = matches
    if len(matches) != 1 or any(matches[0][name] != wanted[name]
            for name in ('long_name', 'dob', 'player_positions')):
        raise ValueError('cited FIFA person ID/edition row is absent, ambiguous or differs')
    version = int(wanted['fifa_version'])
    target_version = int(change['season'][:4]) - 1999
    exact = version == target_version
    if exact and matches[0]['fifa_update_date'] != wanted.get('fifa_update_date'):
        raise ValueError('exact-edition FIFA update date differs')
    if not exact and change['season'] != '2013-14':
        raise ValueError('later edition is permitted only as stated Kilkenny corroboration')
    return dict(record={k: matches[0][k] for k in ('fifa_version','fifa_update_date','player_id','long_name','dob','player_positions')},
        exact_target_edition=exact, sha256=sha(FIFA))


def prepare(base, input_path=INPUT):
    request_path = Path(input_path)
    if (request_path.is_absolute() is False and not (ROOT / request_path).resolve().is_relative_to(ROOT.resolve())):
        raise ValueError('annual source input path escapes the workspace')
    if not request_path.is_absolute():
        request_path = ROOT / request_path
    if not request_path.resolve().is_relative_to(ROOT.resolve()) or not request_path.is_file():
        raise ValueError('annual source input must be a retained workspace file')
    request = json.loads(request_path.read_text(encoding='utf-8'))
    selected = [r for r in request['changes'] if r['season'] == base.season and r['release_id'] == base.release_id]
    if len(selected) != 1:
        raise ValueError('input must select exactly one matching registered parent')
    change = selected[0]
    annual = _annual_row(change)
    fifa = _fifa_row(change)
    package = pipeline.read_json_file(base.package_path)
    player = next((p for p in package['players'] if p['carrier_id'] == change['carrier_id']), None)
    if player is None:
        raise ValueError('carrier is absent from exact parent recipe')
    actor_name = re.sub(r'^#\d+\s*', '', player.get('source_name') or player['name'])
    if (roster.normalise(actor_name) != roster.normalise(change['name'])
            or player['facts'].get('birth_date') != change['birth_date']
            or annual['player']['name'] != change['name']
            or annual['player']['birth_date'] != change['birth_date']
            or annual['player']['position'] != change['target']['primary_position_after']):
        raise ValueError('annual full-name/DOB/broad position does not bind the selected actor')
    jug_path, eq_path = base.game_path / 'DBDAT/JUG98030.FDI', base.game_path / 'DBDAT/EQ98030.FDI'
    jug, eq = jug_path.read_bytes(), eq_path.read_bytes()
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    if change['carrier_id'] not in entries:
        raise ValueError('native carrier record is absent')
    payload = entries[change['carrier_id']].decode_payload(jug)
    native = roster.native_player(payload, change['carrier_id'])
    native_biography = native_facts(jug, change['carrier_id'])
    owner = ownership.native_owners(eq).get(change['carrier_id'])
    clubs = {c['id']: c for c in package['clubs']}
    if (roster.normalise(native['name']) != roster.normalise(player['name'])
            or native_biography['birth_date'] != change['birth_date']
            or native['position'] != change['target']['native_primary_before']
            or player['facts']['primary_position'] != native['position']
            or owner != {clubs[player['club_id']]['carrier_id']}):
        raise ValueError('native identity, broad preimage or exclusive recipe owner differs')
    labels = change['target']['fine_role_labels'] if 'fine_role_labels' in change['target'] else [change['target']['fine_role_label']]
    role_map = {'CM': 9, 'RM': 6, 'CAM': 9, 'LM': 10, 'RW': 11, 'ST': 12, 'LW': 13}
    fine = list(dict.fromkeys(role_map[x] for x in labels))
    broad = change['target']['primary_position_after']
    if (not fine or any(not fifa_roles.compatible(broad, role) for role in fine)
            or native['position'] == broad):
        raise ValueError('compatible explicit role projection or changed broad source required')
    source_row = fifa['record']
    if (roster.normalise(source_row['long_name']) != roster.normalise(change['name'])
            or source_row['dob'] != change['birth_date']
            or fine != change['target']['fine_roles_after']):
        raise ValueError('FIFA corroboration identity or explicit fine-role target differs')
    if fifa['exact_target_edition']:
        labels_in_source = [x.strip() for x in source_row['player_positions'].split(',')]
        mapped = list(dict.fromkeys(role_map[x] for x in labels_in_source))
        if fine != mapped:
            raise ValueError('exact FIFA fine-role projection differs from raw role labels')
    before_player = copy.deepcopy(player)
    update = dict(carrier_id=change['carrier_id'], before_player=before_player,
        before_native=native, primary_position=broad, fine_roles=fine,
        source=source_row, dated_annuals=[annual],
        source_admission=dict(annual_position='source fact', fine_roles=change['target']['fine_role_status'],
            fifa_exact_target_edition=fifa['exact_target_edition'], fifa=fifa))
    plan = dict(schema=SCHEMA, policy=POLICY, mode=MODE,
        season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path), jug_sha256=registry.sha256_file(jug_path),
        eq_sha256=registry.sha256_file(eq_path), targets=[change['carrier_id']], updates=[update],
        source_input=dict(path=registry.relative_workspace_path(request_path), sha256=sha(request_path)),
        source_bindings=[dict(path=annual[k], sha256=annual[h]) for k,h in (
            ('dataset_path','dataset_sha256'),('source_file_path','source_file_sha256'))]
            + [dict(path=registry.relative_workspace_path(FIFA), sha256=sha(FIFA))],
        implementation_inputs=[dict(path=registry.relative_workspace_path(Path(__file__)), sha256=sha(__file__)),
            dict(path=registry.relative_workspace_path(ROOT/'scripts/season_exact_primary_position_delta_v2.py'),
                 sha256=registry.sha256_file(ROOT/'scripts/season_exact_primary_position_delta_v2.py'))],
        source_policy='exact annual full-name/DOB broad-position source; compatible fine-role projection separately labeled; exact-edition FIFA used only when same-name/DOB exists; no August role or ownership claim',
        scope='Only selected broad-position recipe field and six fine-role bytes. Native preimage/ownership checked. All other profile facts, names, DOB, countries, skills, orders, tactics, managers, photos, kits, EQ and unrelated bytes preserved.')
    plan['transaction_id'] = native_writer.digest(plan)[:24]
    return plan


def verify(base, plan, input_path=INPUT):
    rebuilt = prepare(base, input_path)
    if rebuilt != plan:
        raise ValueError('annual source/parent/native/FIFA evidence no longer reproduces the plan')


def bind(package, plan):
    if plan.get('schema') != SCHEMA or plan.get('policy') != POLICY:
        raise ValueError('annual role binding requires the unique source policy')
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan, ROOT / plan['source_input']['path'])
    if registry.sha256_file(base.package_path) != plan['package_sha256'] or pipeline.read_json_file(base.package_path) != package:
        raise ValueError('annual role recipe preimage differs from the exact parent')
    result = copy.deepcopy(package)
    people = {p['carrier_id']: p for p in result['players']}
    for row in plan['updates']:
        actor = people.get(row['carrier_id'])
        if actor != row['before_player']:
            raise ValueError('annual role actor preimage changed')
        actor['facts']['primary_position'] = row['primary_position']
        actor['facts']['fine_roles'] = list(row['fine_roles'])
        if 'fact_fallbacks' in actor:
            actor['fact_fallbacks'] = [f for f in actor['fact_fallbacks']
                                       if f['field'] not in ('primary_position', 'fine_roles')]
    artifact = dict(id=artifact_id(plan), kind='season-input', relative_path=filename(plan),
        sha256=hashlib.sha256(packages.canonical_json_bytes(plan)).hexdigest(), media_type='application/json')
    result['artifacts'].append(artifact)
    result['artifacts'].sort(key=lambda x: x['id'])
    result['proofs'].append(dict(id='proof-' + artifact['id'], grade='source-receipt',
        artifact_id=artifact['id'], covers=['annual-source-broad-position',
            'editorial-compatible-fine-role-projection-not-tactical-deployment']))
    result['proofs'].sort(key=lambda x: x['id'])
    packages.validate_package(result)
    return result


def reject_factory_recipe(package):
    if any(a['id'].startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('annual source role needs its exact SOURCE plan; factory recompilation refused')


def _writer_bridge(plan):
    """Use the existing native byte writer without borrowing its FIFA schema."""
    return dict(schema=native_writer.SCHEMA, season=plan['season'], release_id=plan['release_id'],
        jug_sha256=plan['jug_sha256'], eq_sha256=plan['eq_sha256'],
        updates=[{k: row[k] for k in ('carrier_id', 'before_native', 'primary_position', 'fine_roles')}
                 for row in plan['updates']])


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan, ROOT / plan['source_input']['path'])
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    before_eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if (hashlib.sha256(before).hexdigest() != plan['jug_sha256']
            or hashlib.sha256(before_eq).hexdigest() != plan['eq_sha256'] or eq != before_eq):
        raise ValueError('annual role SOURCE native parent or full EQ differs')
    patched, patched_eq = native_writer.apply(jug, eq, _writer_bridge(plan))
    repeat, repeat_eq = native_writer.apply(patched, patched_eq, _writer_bridge(plan))
    if (repeat, repeat_eq) != (patched, patched_eq):
        raise ValueError('annual role native writer is not idempotent')
    owner_before = ownership.native_owners(before_eq)
    owner_after = ownership.native_owners(patched_eq)
    if owner_after != owner_before:
        raise ValueError('annual role SOURCE changed the exact native owner map')
    return patched, patched_eq


def reconstruction(previous, release_id):
    # The receipt guard must run before reading any inherited plan locator.
    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    relative = (previous.locator or {}).get('sourced_profile_assignment_plan_path')
    if not relative:
        return None
    path = registry.ROOT / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(registry.ROOT.resolve()) or not path.is_file():
        raise ValueError('annual role source locator escapes workspace')
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA:
        return None
    if plan.get('policy') != POLICY or receipt.get('original_profile_assignment_plan_sha256') != registry.sha256_file(path):
        raise ValueError('annual role receipt/plan binding differs')
    base = registry.load_registered_release(previous.season, plan['release_id'])
    verify(base, plan, ROOT / plan['source_input']['path'])
    package = pipeline.read_json_file(previous.package_path)
    if bind(pipeline.read_json_file(base.package_path), plan) != package:
        raise ValueError('annual role SOURCE would discard recipe edits')
    artifact = next((a for a in package['artifacts'] if a['id'] == artifact_id(plan)), None)
    if (artifact is None or path.resolve() != (previous.package_path.parent / filename(plan)).resolve()
            or artifact['sha256'] != hashlib.sha256(packages.canonical_json_bytes(plan)).hexdigest()):
        raise ValueError('annual role source artifact path/hash differs')
    for release in (base, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    descriptor_path = previous.package_path.parent / 'role-delta-input.json'
    descriptor = pipeline.read_json_file(descriptor_path)
    expected = dict(season=base.season, release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),
        jug_sha256=registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'), updates=[], unresolved=[])
    if descriptor != expected:
        raise ValueError('annual role SOURCE requires exact inert source descriptor')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor_path, release_id=release_id,
        source_release_id=base.release_id, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != package:
        raise ValueError('annual role SOURCE changed the complete recipe')
    return dict(season=previous.season, release_id=release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True)


def build_postimage(base, plan):
    verify(base, plan)
    before = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    after, out_eq = apply(before, eq, plan)
    if out_eq != eq or len(after) != len(before):
        raise ValueError('existing native writer changed EQ or JUG length')
    entry = next(e for e in IndexedFDIFile.from_bytes(after).entries if e.record_id == plan['targets'][0])
    payload = entry.decode_payload(after)
    native = roster.native_player(payload, plan['targets'][0])
    end, roles = read_indexed_native_roles(payload, plan['targets'][0])
    update = plan['updates'][0]
    if (end != update['before_native']['name_end'] or native['position'] != update['primary_position']
            or roles != update['fine_roles'] + [98] * (6 - len(update['fine_roles']))):
        raise ValueError('existing writer postimage readback differs')
    return after, eq
