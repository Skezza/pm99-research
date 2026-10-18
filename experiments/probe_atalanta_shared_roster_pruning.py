"""Private count-changing runtime probe; never publish or relax compiler guards.

Reuses established native serializers and the exclusive whole-XI writer.
Historical reserve membership is not certified by this mechanics experiment.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]
from app.fdi_indexed import IndexedFDIFile
from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.eq_roster_pruning import prune_visible_mode1_roster_payload
from app.player_initial_order import OrderReplacement, patch_owned_mode1_complete_orders
from scripts import season_release_registry_v1 as registry
from scripts import season_package_compiler_v2 as compiler
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_pipeline_v2 as pipeline
from scripts.season_art_transaction_v1 import atomic_bytes
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records


def prepare(output):
    if output.exists():
        raise ValueError('private probe output is immutable')
    release = registry.load_preferred_release('2006-07')
    if release.release_id != 'sourced-goalkeeper-role-repairs-20261007-r50a':
        raise ValueError('probe requires the independently inspected R50 baseline')
    preflight_path = ROOT / '.local/opening-xi-repairs-20261008/italian-preflight/current-native-preflight.json'
    if registry.sha256_file(preflight_path) != '19f6006942af831a8b63c30732417b10e13b7ca784ec20b41a345aeca952fd88':
        raise ValueError('exact native preflight changed')
    preflight = next(c for c in json.loads(preflight_path.read_text())['clubs'] if c['season'] == '2006-07')
    for name, expected in preflight['game_files_before'].items():
        if registry.sha256_file(release.game_path / name) != expected:
            raise ValueError('probe game input changed')
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    index = IndexedFDIFile.from_bytes(eq)
    entry = next(e for e in index.entries if e.record_id == 223)
    raw = eq[entry.payload_offset:entry.payload_offset + entry.payload_length]
    roster = parse_eq_external_team_roster_payload(raw, {})
    removed = {3150, 4165, 4372}
    owners = ownership.native_owners(eq)
    if roster is None or roster.mode_byte != 1 or len(roster.rows) != 29 or any(r.flag for r in roster.rows):
        raise ValueError('probe requires exact all-visible 29-row mode1 source')
    if removed != {r.player_record_id for r in roster.rows if owners[r.player_record_id] != {223}}:
        raise ValueError('probe selected links are not exactly the inspected shared rows')
    retained = [r.player_record_id for r in roster.rows if r.player_record_id not in removed]
    changed_raw = prune_visible_mode1_roster_payload(raw,
        expected_rows=[(r.player_record_id, r.flag) for r in roster.rows],
        removed_player_ids=sorted(removed))
    first = roster.rows[0].raw_row_offset
    if raw[:first - 1] != changed_raw[:first - 1] or len(changed_raw) != len(raw) - 15:
        raise ValueError('probe pruning changed non-roster club bytes')
    candidate_eq = compiler._rebuild_indexed(eq, index, {223: compiler.xor_decode(changed_raw)})
    preserve_other_records(eq, candidate_eq, {223})
    after_owners = ownership.native_owners(candidate_eq)
    if any(after_owners.get(id) != owners[id] - {223} for id in removed):
        raise ValueError('pruning affected another club ownership link')
    wanted = preflight['candidate_XI_carriers']
    if len(wanted) != 11 or len(set(wanted)) != 11 or not set(wanted) <= set(retained):
        raise ValueError('probe candidate XI is not eleven distinct retained players')
    native = {id: facts.native_facts(jug, id) for id in retained}
    reserves = sorted(set(retained) - set(wanted), key=lambda id: (native[id]['startup_order'], id))
    orders = [OrderReplacement(id, native[id]['name'], native[id]['startup_order'], n)
              for n, id in enumerate(wanted + reserves, 1)]
    candidate_jug = patch_owned_mode1_complete_orders(jug, candidate_eq,
        club_record_id=223, replacements=orders)
    preserve_other_records(jug, candidate_jug, set(retained))
    if patch_owned_mode1_complete_orders(candidate_jug, candidate_eq,
            club_record_id=223, replacements=[OrderReplacement(id, native[id]['name'], n, n)
                for n, id in enumerate(wanted + reserves, 1)]) != candidate_jug:
        raise ValueError('probe whole-XI replay is not idempotent')
    output.mkdir(parents=True)
    dbdat = output / 'DBDAT'
    dbdat.mkdir()
    # Tiny override tree: unchanged files are shared read-only by hardlinks;
    # changed generated files are new inodes, never written through links.
    for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'MINIFOTO.PKF',
                 'BIGCAMP.PKF', 'BIGESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF'):
        if name == 'JUG98030.FDI':
            atomic_bytes(dbdat / name, candidate_jug)
        elif name == 'EQ98030.FDI':
            atomic_bytes(dbdat / name, candidate_eq)
        else:
            os.link(release.game_path / 'DBDAT' / name, dbdat / name)
    report = {'schema_version': 'pm99-private-mode1-roster-pruning-mechanics-probe-v1',
        'season': release.season, 'release_id': release.release_id, 'club_carrier_id': 223,
        'source_game': registry.relative_workspace_path(release.game_path),
        'source_preflight_sha256': registry.sha256_file(preflight_path),
        'source_native_hashes': preflight['game_files_before'],
        'removed_links': sorted(removed), 'before_roster_count': 29, 'after_roster_count': 26,
        'candidate_XI': wanted, 'startup_orders': [vars(row) for row in orders],
        'other_club_payloads_identical': True, 'other_player_payloads_identical': True,
        'shared_removed_player_payloads_identical': True, 'order_replay_idempotent': True,
        'JUG_changed_bytes': sum(a != b for a, b in zip(jug, candidate_jug)),
        'outputs': {name: registry.sha256_file(dbdat / name) for name in ('JUG98030.FDI', 'EQ98030.FDI')},
        'historical_approval': False, 'publishable': False, 'registered': False,
        'scope': 'private roster-count/initial-order mechanics only; source alias and reserve approval still separate'}
    pipeline.write_canonical_json(output / 'probe-receipt.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    print(json.dumps(prepare(parser.parse_args().output)), flush=True)
