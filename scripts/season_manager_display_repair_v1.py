#!/usr/bin/env python3
"""Prepare bounded manager display repairs; canonical identities stay intact.

No preferred registration or live-game mutation. Only declared, exclusively
owned written managers may acquire explicit native aliases. Ambiguous compound
names remain a visible queue rather than being split at the last word.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor')]
from app.ent_manager_profiles import parse_indexed_ent_manager_profile, replace_indexed_ent_manager_names
from app.fdi_indexed import IndexedFDIFile
from app.xor import xor_decode
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages
from scripts import season_package_compiler_v2 as compiler
from scripts import season_contextual_tactics_rollout_v1 as tactics
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph
from scripts.build_2015_english92_release import _rebuild_indexed
from scripts.season_package_display_alias_repair_v1 import _portable_source_text
from scripts.season_historical_roster_audit_v1 import normalise

# These are presentation aliases, not claims about the surname's legal extent.
# In particular Nuno remains Nuno, not the incorrect blind-last-token Santo.
COMMON_NAMES = {
    'James Alan Irvine': 'Irvine', 'Jimmy Floyd Hasselbaink': 'Hasselbaink',
    'Johannes Hoff Thorup': 'Thorup', 'Jon Dahl Tomasson': 'Tomasson',
    'Keith Alexander †': 'Alexander', 'Luiz Felipe Scolari': 'Scolari',
    'Nuno Espírito Santo': 'Nuno', 'Ole Gunnar Solskjaer': 'Solskjaer',
    'Quique Sanchez Flores': 'Quique Flores', 'Quique Sánchez Flores': 'Quique Flores',
    'Sir Bobby Robson': 'Robson',
}
PARTICLES = {'van', 'von', 'de', 'di', 'del', 'da', 'dos', 'du', 'den', 'der', 'ten', 'le'}


def short_name(name):
    if name in COMMON_NAMES:
        return COMMON_NAMES[name], 'explicit-common-display-name'
    parts = name.split()
    if len(parts) == 1:
        return name, 'existing-single-name'
    if len(parts) == 2:
        return parts[1], 'two-part-name-short-field'
    for i, part in enumerate(parts[1:-1], 1):
        if part.casefold() in PARTICLES:
            return ' '.join(parts[i:]), 'compound-name-particle-preserved'
    return None, 'ambiguous-compound-name-retained'


def collect_targets(layers):
    """Keep references to every recipe layer, not just the last equal row."""
    targets = {}
    for source in layers:
        owners = {}
        for club in source['clubs']:
            owners.setdefault(club['manager_id'], []).append(club)
        for manager in source['managers']:
            if manager.get('policy', 'write') != 'write':
                continue
            carrier = int(manager['carrier_id'])
            references, claimed = targets.setdefault(carrier, ([], owners.get(manager['id'], [])))
            if references and (references[0] != manager or claimed != owners.get(manager['id'], [])):
                raise ValueError('two canonical identities claim one manager carrier')
            references.append(manager)
    return targets


def reconcile_legacy_english(english, holders, names):
    """Rebind the legacy declarations to the already-proved native graph."""
    by_club = {c['carrier_id']: mid for mid, clubs in holders.items() for c in clubs}
    managers = {m['id']: m for m in english['managers']}
    changes = []
    for club in english['clubs']:
        manager = managers[club['manager_id']]
        mid = by_club.get(club['carrier_id'])
        expected = (manager.get('native_names') or {}).get('display_name', manager['name'])
        if (mid is None or len(holders[mid]) != 1 or
                normalise(names[mid]) != normalise(expected)):
            raise ValueError('legacy English canonical identity is not the exclusive native manager')
        changes.append({'manager_id': manager['id'], 'club_carrier_id': club['carrier_id'],
                        'before_carrier_id': manager['carrier_id'], 'after_carrier_id': mid,
                        'name': manager['name']})
        manager.update(carrier_id=mid, policy='write')
    return changes


def prepare(season, output, *, field_probe=False):
    if output.exists():
        raise ValueError('candidate output exists; never overwrite')
    release = registry.load_preferred_release(season)
    if not registry.validate_preferred_release(season, level='playable')['valid']:
        raise ValueError('current game failed its immutable hash check')
    package = json.loads(release.package_path.read_text())
    english = tactics.load_english(release, package)
    separate_english = english != package
    working = copy.deepcopy(package)
    english_working = copy.deepcopy(english) if separate_english else working
    ent = release.game_path / 'DBDAT/ENT98030.FDI'
    before = ent.read_bytes()
    index = IndexedFDIFile.from_bytes(before)
    entries = {e.record_id: e for e in index.entries}
    holders, names = _manager_graph(eq_path=release.game_path / 'DBDAT/EQ98030.FDI', ent_path=ent)
    legacy_bindings = []
    if season == '2015-16' and separate_english:
        legacy_bindings = reconcile_legacy_english(english_working, holders, names)
    targets = collect_targets((working, english_working) if separate_english else (working,))
    replacements, changes, unresolved = {}, [], []
    for carrier, (references, owners) in sorted(targets.items()):
        manager = references[0]
        short, method = short_name(manager['name'])
        entry = entries.get(carrier)
        reason = None
        if entry is None:
            reason = 'native manager record missing'
        elif len(owners) != 1 or [r['carrier_id'] for r in holders.get(carrier, [])] != [owners[0]['carrier_id']]:
            reason = 'native ownership is not exclusive and canonical'
        elif short is None:
            reason = method
        if reason:
            unresolved.append({'manager_id': manager['id'], 'carrier_id': carrier,
                               'name': manager['name'], 'reason': reason})
            continue
        raw = before[entry.payload_offset:entry.payload_offset + entry.payload_length]
        profile = parse_indexed_ent_manager_profile(raw, record_id=carrier)
        expected = (manager.get('native_names') or {}).get('display_name', manager['name'])
        if normalise(profile.display_name) != normalise(expected):
            unresolved.append({'manager_id': manager['id'], 'carrier_id': carrier, 'name': manager['name'],
                               'reason': 'native name is not the current canonical identity', 'native': profile.display_name})
            continue
        try:
            short.encode('cp1252')
        except UnicodeEncodeError:
            short = _portable_source_text(short)
            method += '-CP1252-display-transliteration'
        display = profile.display_name if profile.format == 'full_profile' else short
        if field_probe and carrier == 681:
            short, display, method = 'SHORTQA', 'FULLQA', 'disposable-field-isolation-probe-not-a-release'
        native_names = {'surname': short, 'display_name': display}
        updated = replace_indexed_ent_manager_names(raw, record_id=carrier,
            expected_surname=profile.surname, expected_display_name=profile.display_name, **native_names)
        for declaration in references:
            declaration['native_names'] = dict(native_names)
        if updated != raw:
            replacements[carrier] = xor_decode(updated)
            changes.append({'carrier_id': carrier, 'manager_id': manager['id'], 'name': manager['name'],
                'club': owners[0]['name'], 'club_carrier_id': owners[0]['carrier_id'],
                'before_surname': profile.surname, 'before_display_name': profile.display_name,
                'native_names': native_names, 'format': profile.format, 'method': method})
    if field_probe and not any(r['carrier_id'] == 681 and r['native_names']['surname'] == 'SHORTQA' for r in changes):
        raise ValueError('field probe requires the exact Chelsea full-profile manager carrier')
    after = _rebuild_indexed(before, index, replacements)
    after_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(after).entries}
    if set(after_entries) != set(entries):
        raise ValueError('manager directory IDs changed')
    for carrier, old in entries.items():
        new = after_entries[carrier]
        old_raw = before[old.payload_offset:old.payload_offset + old.payload_length]
        new_raw = after[new.payload_offset:new.payload_offset + new.payload_length]
        if carrier not in replacements and old_raw != new_raw:
            raise ValueError('unrelated manager bytes changed')
    if not field_probe:
        packages.validate_package(working)
        if separate_english:
            packages.validate_package(english_working)
    if separate_english:
        for artifact in working['artifacts']:
            if artifact['id'].startswith('english-contextual-package-'):
                artifact.update(relative_path='english-season-package.json',
                    sha256=hashlib.sha256(packages.canonical_json_bytes(english_working)).hexdigest())
    output.mkdir(parents=True)
    dbdat = output / 'DBDAT'
    dbdat.mkdir()
    # Proof input only: avoid copying hundreds of MB of unrelated portrait/kit
    # archives into each candidate. Publication inherits the real game's assets
    # and copies only the changed ENT from here. Do not register this folder.
    for file in ('EQ98030.FDI', 'JUG98030.FDI', 'ENT98030.FDI', 'TEXTOS.PKF', 'MINIFOTO.PKF',
                 'BIGCAMP.PKF', 'BIGESC.PKF', 'MINIESC.PKF', 'NANOESC.PKF', 'RIDIESC.PKF'):
        shutil.copy2(release.game_path / 'DBDAT' / file, dbdat / file)
    (dbdat / 'ENT98030.FDI').write_bytes(after)
    packages.write_canonical_package(output / 'season-package.json', working)
    if separate_english:
        packages.write_canonical_package(output / 'english-season-package.json', english_working)
    report = {'schema': 'pm99-manager-display-candidate-v1', 'season': season,
        'source_release_id': release.release_id, 'source_package_sha256': registry.canonical_document_sha256(release.package_path),
        'source_ent_sha256': hashlib.sha256(before).hexdigest(), 'after_ent_sha256': hashlib.sha256(after).hexdigest(),
        'source_eq_sha256': registry.sha256_file(release.game_path / 'DBDAT/EQ98030.FDI'),
        'source_jug_sha256': registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI'),
        'source_exe_path': str(release.game_path / 'MANAGPRE.EXE'),
        'canonical_names_changed': 0, 'changes': changes, 'unresolved': unresolved,
        'legacy_english_bindings': legacy_bindings,
        'changed_managers': len(changes), 'unresolved_count': len(unresolved), 'field_probe': field_probe,
        'scope': 'manager name segments only; no biography, links, player, tactics, rating or artwork edits',
        'registered': False, 'runtime_proven': False}
    pipeline.write_canonical_json(output / 'candidate-receipt.json', report)
    return {k: report[k] for k in ('season', 'changed_managers', 'unresolved_count', 'field_probe')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('season')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--field-probe', action='store_true')
    args = parser.parse_args()
    if args.season == 'all':
        if args.field_probe:
            raise ValueError('field-isolation probes are limited to one season')
        for season in registry.supported_seasons():
            print(json.dumps(prepare(season, args.output.resolve() / season / 'candidate-v1')), flush=True)
    else:
        print(json.dumps(prepare(args.season, args.output.resolve(), field_probe=args.field_probe)))
