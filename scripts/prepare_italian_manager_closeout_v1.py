#!/usr/bin/env python3
"""Prepare source-bound manager repairs and an explicitly non-approval census.

Does not change the preferred catalogue or write game databases. Retained HTML
is required: UEFA appointment/report and the Atalanta summer-season account.
Counts of inherited declarations are review candidates, not proven defects.
"""
import json
from pathlib import Path
from bs4 import BeautifulSoup
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts.audit_2015_world_release_semantics_v1 import _manager_graph

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '.local/editorial-closeout-20261008'


def source(name, url, required):
    path = OUTPUT / 'sources' / name
    text = BeautifulSoup(path.read_bytes(), 'html.parser').get_text(' ', strip=True)
    for phrase in required:
        if phrase.casefold() not in text.casefold():
            raise ValueError(f'Original source missing required anchor: {phrase}')
    return {'path': registry.relative_workspace_path(path),
            'sha256': registry.sha256_file(path), 'url': url}


def prepare(season, name, surname, sources):
    release = registry.load_preferred_release(season)
    package = json.loads(release.package_path.read_text())
    club = next(c for c in package['clubs'] if c['carrier_id'] == 223)
    manager = next(m for m in package['managers'] if m['id'] == club['manager_id'])
    holders, names = _manager_graph(eq_path=release.game_path/'DBDAT/EQ98030.FDI',
                                   ent_path=release.game_path/'DBDAT/ENT98030.FDI')
    carrier = manager['carrier_id']
    if [c['carrier_id'] for c in holders[carrier]] != [223]:
        raise ValueError('Manager not exclusively owned by the target club')
    if manager['name'] != 'Roberto Mancini' or names[carrier] != 'Mancini':
        raise ValueError('Expected inherited manager preimage changed')
    evidence = {'policy': 'contemporary-manager-report-plus-opening-season-continuity-v1',
                'manager': name, 'raw_sources': sources,
                'limit': 'No invented first-fixture manager-page reparse; authority is retained dated appointment/season continuity evidence.'}
    row = {'club_id': club['id'], 'club_carrier_id': 223, 'club': club['name'],
           'manager_id': manager['id'], 'carrier_id': carrier,
           'before': manager['name'], 'before_policy': manager['policy'],
           'native_before': names[carrier], 'after': name, 'native_after': surname,
           'native_manager_owner_count': 1, 'evidence': evidence}
    result = {'schema_version': 'pm99-historical-manager-plan-v1', 'season': season,
              'release_id': release.release_id, 'package_sha256': registry.sha256_file(release.package_path),
              'eq_sha256': registry.sha256_file(release.game_path/'DBDAT/EQ98030.FDI'),
              'ent_sha256': registry.sha256_file(release.game_path/'DBDAT/ENT98030.FDI'),
              'updates': [row], 'unresolved': [], 'historical_verification_complete': False}
    folder = OUTPUT / season; folder.mkdir(parents=True, exist_ok=True)
    pipeline.write_canonical_json(folder/'manager-plan.json', result)
    control = {'season': season, 'release_id': release.release_id,
               'package_sha256': registry.sha256_file(release.package_path),
               'jug_sha256': registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'),
               'updates': [], 'unresolved': []}
    pipeline.write_canonical_json(folder/'role-control-plan.json', control)
    return {'season': season, 'club': club['name'], 'before': names[carrier],
            'after': surname, 'exclusively_owned': True, 'installed': False}


def census():
    rows = []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        package = json.loads(release.package_path.read_text())
        manager_lookup = {m['id']: m for m in package['managers']}
        inherited = []
        for club in package['clubs']:
            manager = manager_lookup.get(club.get('manager_id'))
            if manager and manager.get('proof', {}).get('artifact_id') == 'world-2015-club-metadata-dispositions' and season != '2015-16':
                inherited.append({'club_id': club['id'], 'club': club['name'], 'manager': manager['name']})
        rows.append({'season': season, 'release_id': release.release_id,
                     'package_sha256': registry.sha256_file(release.package_path),
                     'clubs': len(package['clubs']), 'players': len(package['players']),
                     'non_target_2015_manager_declarations': inherited,
                     'kit_preserve_declarations': sum(k['policy'].startswith('preserve') for k in package['assets']['kits'])})
    result = {'schema_version': 'pm99-editorial-declaration-census-v1', 'rows': rows,
              'non_target_2015_manager_declarations': sum(len(r['non_target_2015_manager_declarations']) for r in rows),
              'kit_preserve_declarations': sum(r['kit_preserve_declarations'] for r in rows),
              'scope': 'Provenance/declaration review candidates only, not a count of historically incorrect managers or rendered kits. Separate applied asset layers can override kit declarations.'}
    pipeline.write_canonical_json(OUTPUT/'all26-declaration-census.json', result)
    return {k: result[k] for k in ['non_target_2015_manager_declarations', 'kit_preserve_declarations']}


def main():
    palermo = source('palermo-delneri-20050531.html', 'https://www.uefa.com/news-media/news/01a9-0f84745a5c02-5fd4f2f4b599-1000--del-neri-to-push-palermo-on/', ['May 31, 2005', 'Palermo have appointed Luigi Del Neri'])
    atalanta = source('atalanta-colantuono-20061110.html', 'https://www.uefa.com/news-media/news/01bb-0f848ead368c-a33b40753366-1000--atalanta-up-the-italian-ante/', ['November 10, 2006', 'Atalanta coach Stefano Colantuono'])
    summer = source('atalanta-season-2006-07.html', 'https://it.wikipedia.org/wiki/Atalanta_Bergamasca_Calcio_2006-2007', ['conferma', 'Stefano Colantuono', '2006-2007'])
    print(json.dumps(prepare('2005-06', 'Luigi Del Neri', 'Del Neri', [palermo])), flush=True)
    print(json.dumps(prepare('2006-07', 'Stefano Colantuono', 'Colantuono', [atalanta, summer])), flush=True)
    print(json.dumps(census()), flush=True)


if __name__ == '__main__':
    main()
