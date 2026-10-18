#!/usr/bin/env python3
"""Compile a complete coupled source transaction, never a singleton loophole.

Private candidate only. Normal publication, asset identity and exact runner
proof remain mandatory; no registration or historical-clearance claim here.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import prepare_paired_whole_club_dispositions_v1 as paired
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from app.player_initial_order import OrderReplacement, patch_owned_mode1_keeper_exchange

SCHEMA = 'pm99-private-paired-whole-club-native-candidate-v1'


def recipe_inputs(package, baseline_directory, overrides=None):
    """Resolve exact older inputs without confusing a later same-name delta."""
    from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact
    overrides = overrides or {}
    result = {}
    for artifact in package['artifacts']:
        if not artifact.get('relative_path'):
            continue
        relative = Path(artifact['relative_path'])
        if relative.is_absolute() or '..' in relative.parts or not relative.parts:
            raise ValueError('unsafe coupled recipe input')
        if artifact['id'].startswith(('duplicate-ownership-plan-', 'coupled-dated-manager-', 'whole-club-dated-manager-')):
            # These are generated and checked separately in this transaction.
            continue
        source = overrides.get(str(relative), baseline_directory / relative)
        binding = verify_recipe_artifact(source, artifact['sha256'])
        if relative in result and result[relative][0] != source:
            raise ValueError('conflicting coupled recipe input')
        result[relative] = (source, binding)
    if set(overrides) - {str(path) for path in result}:
        raise ValueError('unused coupled recipe input override')
    return result


def dated_manager_identity(payload, fixture_date):
    """Keep a publisher manager ID: two Phil Parkinsons are not one person."""
    name=native.managers._manager_at(payload,fixture_date)
    target=native.managers.date.fromisoformat(fixture_date);candidates=[]
    for row in native.managers.BeautifulSoup(payload,'html.parser').select('table tr'):
        cells=row.select('td');link=row.select_one('a[href*="/managers/manager.sd?manager_id="]')
        if len(cells)<3 or link is None or link.get_text(' ',strip=True)!=name:continue
        found=re.fullmatch(r'/managers/manager\.sd\?manager_id=([1-9][0-9]*)',link.get('href',''))
        if found is None:raise ValueError('dated manager lacks one original numeric publisher identity')
        try:
            start=native.managers._date(cells[1].get_text(' ',strip=True))
            end_text=cells[2].get_text(' ',strip=True)
            end=native.managers.date.max if end_text.casefold()=='present' else native.managers._date(end_text)
        except ValueError:continue
        if start<=target<=end:candidates.append((start,end,int(found.group(1))))
    if not candidates:raise ValueError('dated manager has no bound publisher identity')
    latest=max(r[0] for r in candidates);ids={r[2] for r in candidates if r[0]==latest}
    if len(ids)!=1:raise ValueError('dated manager identity is ambiguous despite its matching name')
    return name,next(iter(ids))


def independently_replay_sources(proposals):
    with tempfile.TemporaryDirectory(prefix='pm99-paired-source-replay-') as temporary:
        for p in proposals:
            path = Path(temporary) / f"{p['before_club']['carrier_id']}.json"
            native.source.prepare(p['season'], p['before_club']['carrier_id'], p['new_club'],
                native.original(p['bindings']['published_person_supplement']),
                native.original(p['bindings']['published_transfer_supplement']), native.original(p['entity_binding']),
                path, capacity_bundle=p.get('capacity_policy_bundle'), baseline_release_id=p['release_id'],
                inspect_collisions=True, snapshot_binding=p['bindings'].get('snapshot'),
                allow_keeper_order_exchange=bool(p.get('allow_keeper_order_exchange')),
                identity_review_path=(native.original(p['bindings']['provider_identity_review'])
                    if p['bindings'].get('provider_identity_review') else None),
                allow_original_matchday_only_club_identity=bool(p.get('allow_original_matchday_only_club_identity')),
                allow_original_provider_career_reserves=bool(p.get('allow_original_provider_career_reserves')),
                exclude_unpublished_bench_birth_dates=bool(p.get('exclude_unpublished_bench_birth_dates')),
                fit_verified_reserve_pool=bool(p.get('fit_verified_reserve_pool')),
                retained_source_label_review_path=(native.original(p['bindings']['retained_duplicate_label_review'])
                    if p['bindings'].get('retained_duplicate_label_review') else None))
            if json.loads(path.read_text()) != p:
                raise ValueError('coupled source proposal differs from independent original replay')


def prepare(pair_path, managers, output, input_overrides=None):
    if output.exists():
        raise ValueError('paired native candidate is immutable')
    pair = json.loads(pair_path.read_text())
    if pair.get('schema_version') not in (paired.SCHEMA,paired.SINGLETON_SCHEMA) or pair.get('publication_authorised') is not False:
        raise ValueError('paired native candidate needs complete explicit source-only group')
    proposals = [json.loads(native.original(b).read_text()) for b in pair['proposals']]
    if paired.source_guard(pair,proposals) != pair['source_guard']:
        raise ValueError('saved coupled source guard does not independently reproduce')
    if any((p['season'], p['release_id']) != (pair['season'], pair['release_id']) for p in proposals):
        raise ValueError('coupled group wrapper has a different season or native baseline')
    if set(managers) != {p['before_club']['carrier_id'] for p in proposals}:
        raise ValueError('every coupled club needs its own dated original manager')
    release = registry.load_registered_release(pair['season'], pair['release_id'])
    for p in proposals:
        if any(registry.sha256_file(path) != sha for path, sha in (
            (release.package_path, p['package_sha256']),
            (release.game_path / 'DBDAT/JUG98030.FDI', p['jug_sha256']),
            (release.game_path / 'DBDAT/EQ98030.FDI', p['eq_sha256']))):
            raise ValueError('coupled original native baseline changed')
    implementations = {'paired_source': Path(paired.__file__), 'paired_native': Path(__file__),
        'whole_source': Path(native.source.__file__), 'whole_native': Path(native.__file__),
        'original_replayer': Path(native.source.replay.__file__), 'roster_reader': Path(native.source.roster.__file__),
        'fact_composer': Path(native.delta.__file__), 'compiler': Path(native.delta.compiler.__file__),
        'person_reader': Path(native.source.persons.__file__), 'history_reader': Path(native.source.histories.__file__),
        'source_context': ROOT / 'scripts/season_duplicate_source_context_v1.py',
        'source_policy': Path(native.source.soccerbase.__file__), 'manager_reader': Path(native.managers.__file__),
        'capacity': Path(native.capacity.__file__)}
    import app.player_initial_order as initial_order
    implementations['owned_keeper_exchange']=Path(initial_order.__file__)
    from scripts import season_whole_club_keeper_exchange_v1 as whole_keeper
    implementations['recipe_keeper_replayer']=Path(whole_keeper.__file__)
    if any(p.get('equivalent_original_opening_captures') for p in proposals):
        from scripts import season_equivalent_soccerbase_openings_v1 as equivalent_openings
        implementations['equivalent_original_opening_reader']=Path(equivalent_openings.__file__)
    if any(person.get('source_identity_resolution', {}).get('secondary_birthday_policy') ==
            'original-numeric-Soccerbase-missing-DOB-bound-secondary-publishers-v2'
            for p in proposals for person in p['desired_people']):
        from scripts import season_external_soccerbase_birthday_v2 as secondary_birthdays
        implementations['secondary_publisher_birthday_reader']=Path(secondary_birthdays.__file__)
        implementations['secondary_numeric_birthday_bridge']=Path(secondary_birthdays.prior.__file__)
    if any(person.get('source_role_basis', {}).get('policy') ==
            'original-numeric-bench-actor-and-exact-DOB-official-club-biographical-role-v1'
            for p in proposals for person in p['desired_people']):
        from scripts import season_original_secondary_bench_role_v1 as secondary_bench
        implementations['secondary_official_bench_role_reader']=Path(secondary_bench.__file__)
    if any(p['bindings'].get('retained_duplicate_label_review') for p in proposals):
        from scripts import season_retained_duplicate_club_identity_v1 as retained_identity
        implementations['retained_duplicate_identity_reader']=Path(retained_identity.__file__)
        implementations['original_authored_club_reader']=Path(retained_identity.source.__file__)
    if any(p.get('allow_original_provider_career_reserves') for p in proposals):
        from scripts import season_original_soccerbase_reserves_v1 as originals
        implementations['original_provider_reserve_reader']=Path(originals.__file__)
        import scripts.capture_soccerbase_august_squads_v1 as original_facts
        implementations['original_provider_fact_reader']=Path(original_facts.__file__)
    hashes = {k: registry.sha256_file(p) for k, p in implementations.items()}
    # Perform cheap native fitting/preflight IN MEMORY before the expensive
    # source replay. Neither phase writes a game. Both original-source decisions
    # still independently reproduce before any candidate/native file is saved.
    package = json.loads(release.package_path.read_text()); result = copy.deepcopy(package)
    holdings, _ = native._manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI',
        ent_path=release.game_path / 'DBDAT/ENT98030.FDI')
    compositions = []; managers_proof = []; changed = set(); player_carriers = set(); manager_carriers = set()
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    ent = (release.game_path / 'DBDAT/ENT98030.FDI').read_bytes()
    # Compose both complete squads while all old coaches are still unchanged.
    # Moving one real coach first may temporarily collide with his old wrong
    # assignment on the other retired carrier. Validate only the fully composed
    # manager transaction below; do not loosen package uniqueness checks.
    for p in proposals:
        result, composition = native.compile_recipe(result, p)
        compositions.append(composition)
    for p in proposals:
        club, slots = native.validate_allocation(package, p); carrier = club['carrier_id']
        changed.update(slots); player_carriers.update(r['carrier_id'] for r in p['allocation'])
        manager_path = managers[carrier]; receipt = json.loads(manager_path.with_name(manager_path.name + '.source.json').read_text())
        team_id = p['original_opening']['source_capture']['source_path'].split('/')[2]
        if receipt != {'url': f'https://www.soccerbase.com/teams/team.sd?team_id={team_id}&teamTabs=managers',
                       'sha256': registry.sha256_file(manager_path)}:
            raise ValueError('manager original URL/SHA belongs to another coupled club')
        name,source_manager_id = dated_manager_identity(manager_path.read_bytes(), p['original_opening']['fixture']['date'])
        short, _ = native.manager_display.short_name(name)
        if short is None:
            raise ValueError('coupled manager has no proved native display form')
        manager = next(m for m in result['managers'] if m['id'] == club['manager_id']); mid = manager['carrier_id']
        if [c['carrier_id'] for c in holdings.get(mid, [])] != [carrier] or mid in manager_carriers:
            raise ValueError('coupled club does not exclusively own its distinct native manager')
        manager_carriers.add(mid)
        names = {'surname': short, 'display_name': short}
        index = native.IndexedFDIFile.from_bytes(ent); entry = next(e for e in index.entries if e.record_id == mid)
        payload = native.delta.compiler._patch_ent_name(entry.decode_payload(ent), mid,
            native.delta.compiler._pm99_text(name, label='coupled dated manager'), native_names=names)
        ent = native.delta.compiler._rebuild_indexed(ent, index, {mid: payload})
        artifact = f'coupled-dated-manager-{pair["season"]}-{carrier}'
        filename = f'manager-original-{carrier}.html'
        manager.update(name=name, policy='write', native_names=names,
            person_id=f'manager-soccerbase-{source_manager_id}',
            proof={'artifact_id': artifact, 'grade': 'source-receipt'})
        result['artifacts'].append({'id': artifact, 'kind': 'season-input', 'sha256': receipt['sha256'],
            'media_type': 'text/html', 'relative_path': filename})
        managers_proof.append({'carrier_id': carrier, 'manager_carrier_id': mid, 'name': name,
            'source_manager_id':source_manager_id,
            'native_names': names, 'path': registry.relative_workspace_path(manager_path),
            'sha256': receipt['sha256'], 'relative_path': filename})
        for row in p['allocation']:
            if row.get('same_carrier_name_capacity'):
                jug, claim = native.capacity.recover_slot(jug, row['carrier_id'], p['capacity_policy_bundle'])
                if claim != row['same_carrier_name_capacity']:
                    raise ValueError('coupled same-carrier capacity recovery changed')
        target = next(c for c in result['clubs'] if c['id'] == club['id'])
        players = {x['id']: x for x in result['players']}
        eq = native.rewrite_roster(eq, carrier, [players[id]['carrier_id'] for id in target['roster_player_ids']])
        entry = next(e for e in native.IndexedFDIFile.from_bytes(eq).entries if e.record_id == carrier)
        short_old, full_old, _ = native.labels.prefix_parts(entry.decode_payload(eq))
        eq, _ = native.labels.rewrite_club_labels(eq, [{'carrier_id': carrier, 'native_before': short_old,
            'native_full_before': full_old,
            'native_after': native.delta.compiler._pm99_text(p['new_club'], label='coupled sourced club')}])
    result['artifacts'].sort(key=lambda a: a['id']); native.package_v2.validate_package(result, strict=False)
    # Check inherited evidence before source replay or any candidate write.
    inputs = recipe_inputs(result, release.package_path.parent, input_overrides)
    countries = native.delta.compiler._extract_country_codes_from_textos(release.game_path / 'DBDAT/TEXTOS.PKF')
    jug = native.delta.compile_players(jug, result, changed, countries)
    exchanges=[]
    for p in proposals:
        rows=p.get('startup_order_exchange',[])
        if rows:
            current_club=next(c for c in result['clubs'] if c['id']==p['before_club']['id'])
            if whole_keeper.validate_scope(result,current_club,p)!=rows:
                raise ValueError('compiled coupled keeper exchange is not bound to its complete recipe')
            before_exchange=jug
            jug=patch_owned_mode1_keeper_exchange(jug,eq,
                whole_keeper.bound_native_replacements(jug,rows))
            changed_bytes=[i for i,(a,b) in enumerate(zip(before_exchange,jug)) if a!=b]
            if len(changed_bytes)!=2:raise ValueError('owned keeper exchange did not change exactly two starter bytes')
            exchanges.append({'club_carrier_id':p['before_club']['carrier_id'],'rows':rows,
                'changed_file_offsets':changed_bytes,'all_other_bytes_preserved':True})
    for p in proposals:
        before = native.source.startup_orders((release.game_path / 'DBDAT/JUG98030.FDI').read_bytes(),
            [r['before_recipe'] for r in p['allocation']])
        after = native.source.startup_orders(jug, [r['before_recipe'] for r in p['allocation']])
        expected={r['carrier_id']:r.get('native_startup_order_after',before[r['carrier_id']]) for r in p['allocation']}
        if expected != after or any(not native.source.opening_edge(after[r['carrier_id']], r['replacement'])
                                  for r in p['allocation']):
            raise ValueError('coupled source XI differs from the preserved native startup slots')
    club_carriers = {p['before_club']['carrier_id'] for p in proposals}
    for filename, data, allowed in (('JUG98030.FDI', jug, player_carriers),
                                  ('EQ98030.FDI', eq, club_carriers), ('ENT98030.FDI', ent, manager_carriers)):
        native.preserve_other_records((release.game_path / 'DBDAT' / filename).read_bytes(), data, allowed)
    archive, photo_offsets = native.delta.no_photo_archive(
        (release.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes(), player_carriers)
    independently_replay_sources(proposals)
    estimated = len(jug) + len(eq) + len(ent) + len(archive) + 64 * 1024**2
    if shutil.disk_usage(release.game_path).free - estimated < 8 * 1024**3:
        raise ValueError('paired native candidate would cross the 8-GiB reserve')
    if any(registry.sha256_file(path) != hashes[k] for k, path in implementations.items()):
        raise ValueError('coupled implementation changed during independent replay')
    output.mkdir(parents=True); shutil.copytree(release.game_path, output / 'game', copy_function=os.link)
    for name, data in (('JUG98030.FDI', jug), ('EQ98030.FDI', eq), ('ENT98030.FDI', ent), ('MINIFOTO.PKF', archive)):
        path = output / 'game/DBDAT' / name
        if path.read_bytes() != data:
            temporary = output / (name + '.partial'); temporary.write_bytes(data); os.replace(temporary, path)
    for carrier in photo_offsets:
        path = output / 'game/DBDAT/MINIFOTO' / f'J96{carrier:05d}.BMP'
        if path.exists(): path.unlink()
    pipeline.write_canonical_json(output / 'season-package.json', result)
    for composition in compositions:
        pipeline.write_canonical_json(output / native.delta.plan_filename(composition), composition)
    for manager in managers_proof:
        os.link(ROOT / manager['path'], output / manager['relative_path'])
    for artifact in result['artifacts']:
        if not (relative := artifact.get('relative_path')): continue
        relative = Path(relative)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe coupled recipe artifact')
        target = output / relative
        if not target.exists():
            previous = inputs.get(relative, (release.package_path.parent / relative,))[0]
            from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact
            verify_recipe_artifact(previous, artifact['sha256'])
            target.parent.mkdir(parents=True, exist_ok=True); os.link(previous, target)
        from scripts.publish_contextual_tactics_delta_v1 import verify_recipe_artifact
        verify_recipe_artifact(target, artifact['sha256'])
    holders, names = native._manager_graph(eq_path=output / 'game/DBDAT/EQ98030.FDI',
        ent_path=output / 'game/DBDAT/ENT98030.FDI')
    for m in managers_proof:
        if names[m['manager_carrier_id']] != m['native_names']['display_name'] or [
                c['carrier_id'] for c in holders.get(m['manager_carrier_id'], [])] != [m['carrier_id']]:
            raise ValueError('coupled native manager readback failed')
    from scripts.closeout_duplicate_ownership_batch_v1 import freeze_implementations
    frozen = freeze_implementations(implementations, hashes, output / 'frozen-implementations')
    proof = {'schema_version': SCHEMA, 'season': pair['season'], 'source_release_id': release.release_id,
        'source_pair': {'path': registry.relative_workspace_path(pair_path), 'sha256': registry.sha256_file(pair_path)},
        'corrected_slots': len(changed), 'new_clubs': [p['new_club'] for p in proposals], 'managers': managers_proof,
        'both_complete_original_sources_independently_replayed': True, 'all_collisions_retired_atomically': True,
        'native_startup_XI_membership_verified': True, 'startup_controls_byte_identical': not bool(exchanges),
        'bounded_owned_keeper_exchanges':exchanges,'unrelated_startup_controls_byte_identical':True,
        'unrelated_native_records_byte_identical': True, 'registered': False, 'publication_authorised': False,
        'inherited_recipe_bindings': {str(relative): {'path': registry.relative_workspace_path(source), **binding}
            for relative, (source, binding) in inputs.items()},
        'historical_release': False, 'runtime_XI_verified': False,
        'implementation_bindings': {k: {'path': registry.relative_workspace_path(frozen[k]), 'sha256': hashes[k]}
            for k in implementations},
        'native_hashes': {n: registry.sha256_file(output / 'game/DBDAT' / n)
            for n in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF')},
        'remaining': ['independent compiled fact readback', 'actual runner rosters', 'new kit/ground identity',
                      'mode1 deployment not historically proven', 'no-new-duplicate audit', 'normal release publication']}
    pipeline.write_canonical_json(output / 'candidate-receipt.json', proof)
    return proof


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--source-pair', type=Path, required=True)
    p.add_argument('--manager', action='append', required=True, help='NATIVE_CLUB_CARRIER=ORIGINAL_HTML')
    p.add_argument('--recipe-input', action='append', default=[], help='RELATIVE_INPUT=EXACT_RETAINED_ORIGINAL')
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    managers = {}
    for value in a.manager:
        carrier, path = value.split('=', 1)
        if int(carrier) in managers: raise ValueError('duplicate dated manager carrier')
        managers[int(carrier)] = Path(path)
    overrides = {}
    for value in a.recipe_input:
        relative, path = value.split('=', 1)
        if relative in overrides: raise ValueError('duplicate recipe input override')
        overrides[relative] = Path(path)
    result = prepare(a.source_pair, managers, a.output, overrides)
    print(json.dumps({'private_candidate': str(a.output), 'slots': result['corrected_slots'],
                      'registered': False, 'publication_authorised': False}), flush=True)
