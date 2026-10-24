"""Source-bound two-slot Serena/Gimmelli publisher adapter.

This private proposal uses the publisher's assignment API and existing native
compiler. It never writes game/package bytes directly. Actual use requires a
fresh rebase request against the approved registered parent and the publisher
dispatch additions documented in the adjacent integration proposal.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_editorial_ratings_v1 as ratings
from scripts import season_historical_role_plan_v1 as historical_roles
from scripts import season_exact_fifa_role_delta_v1 as exact_roles
from scripts import season_package_v2 as packages
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_historical_roster_audit_v1 as roster
from scripts.season_within_club_reserve_repair_v1 import native_facts
from scripts.season_opening_order_repair_v1 import native_owners

ROOT = registry.ROOT
CASE_ID = 'f8bfdbd97229f85ba3a79315c26e472845fa65fd56eec0d7471ab06a640c8e29'
SCHEMA = 'pm99-source-bound-gimmelli-serena-inter-two-slot-v1'
INPUT_SCHEMA = SCHEMA + '-input'
MODE = 'known-good-baseline-source-bound-Inter-Serena-Gimmelli-two-slot-replacement-v1'
PREFIX = 'sourced-gimmelli-serena-inter-2000-01-'
STORIA_URL = 'https://www.storiainter.com/Notes/AltrePartite/Stagione%202000-01.htm'
DFB_URL = 'https://datencenter.dfb.de/europa-league/2000-2001/mannschaft/inter-mailand'
SERENA_URL = 'https://www.inter.it/it/archivio_giocatore/G0693'
SERENA_ROLE_URL = 'https://www.transfermarkt.com/michele-serena/profil/spieler/5777'
MODEL_ID = 'source-gimmelli-editorial-ratings-v1'


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value) -> bytes:
    return packages.canonical_json_bytes(value)


def artifact_id(plan: dict) -> str:
    if plan.get('schema') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('unsupported Serena/Gimmelli plan')
    return PREFIX + plan['transaction_id']


def filename(plan: dict) -> str:
    return artifact_id(plan) + '.json'


def exact_parent(base) -> dict:
    game = base.game_path
    result = {
        'manifest_sha256': base.manifest_sha256,
        'package_sha256': sha(Path(base.package_path).read_bytes()),
        'jug_sha256': sha((game / 'DBDAT/JUG98030.FDI').read_bytes()),
        'eq_sha256': sha((game / 'DBDAT/EQ98030.FDI').read_bytes()),
        'minifoto_sha256': sha((game / 'DBDAT/MINIFOTO.PKF').read_bytes()),
        'inventory_sha256': sha(Path(base.inventory_path).read_bytes()),
    }
    loose = {}
    for carrier in (4211, 14660):
        path = game / 'DBDAT/MINIFOTO' / f'J96{carrier:05d}.BMP'
        if path.is_symlink():
            raise ValueError('selected loose bitmap is a symlink')
        raw = path.read_bytes() if path.is_file() else None
        loose[str(carrier)] = {'path': f'DBDAT/MINIFOTO/J96{carrier:05d}.BMP',
            'present': raw is not None, 'sha256': sha(raw) if raw is not None else None,
            'bytes': len(raw) if raw is not None else 0}
    result['selected_loose_bitmaps'] = loose
    return result


def read_sources(request: dict) -> tuple[dict, dict]:
    expected = {'storia', 'dfb', 'gimmelli_adjudication', 'serena_profiles'}
    rows = request.get('sources')
    if not isinstance(rows, dict) or set(rows) != expected:
        raise ValueError('source input requires the four explicit bound sources')
    bodies, bindings = {}, {}
    for name, row in rows.items():
        if set(row) != {'path', 'sha256', 'url', 'representation'}:
            raise ValueError('source binding fields differ: ' + name)
        path = Path(row['path'])
        if not path.is_absolute():
            path = ROOT / path
        if path.is_symlink():
            raise ValueError('source path must not be a symlink: ' + name)
        path = path.resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
            raise ValueError('source is not a retained workspace file: ' + name)
        raw = path.read_bytes()
        if sha(raw) != row['sha256']:
            raise ValueError('source SHA differs: ' + name)
        bodies[name] = raw
        bindings[name] = {'path': str(path.relative_to(ROOT)), 'sha256': sha(raw),
                          'url': row['url'], 'representation': row['representation'],
                          'bytes': len(raw)}
    if bindings['storia']['url'] != STORIA_URL or bindings['dfb']['url'] != DFB_URL:
        raise ValueError('Storia/DFB source URL mismatch')
    if bindings['serena_profiles']['url'] != 'local://serena-profile-adjudication-v1':
        raise ValueError('Serena profile receipt URL mismatch')
    return bodies, bindings


def validate_sources(bodies: dict) -> dict:
    storia = BeautifulSoup(bodies['storia'], 'html.parser').get_text('\n', strip=True)
    aug14 = storia.find('Trieste, 14 agosto 2000')
    aug28 = storia.find('Milano, 28 agosto 2000, finale')
    if aug14 < 0 or aug28 < 0:
        raise ValueError('dated Inter source entries missing')
    end14 = storia.find('Inter - Olympiakos 2-2', aug14)
    if end14 < 0 or end14 > aug28:
        end14 = aug28
    row14 = ' '.join(storia[aug14:end14].split())
    row28 = ' '.join(storia[aug28:aug28 + 1000].split())
    match14 = row14.find('Inter:')
    bench14 = row14.find('A disposizione:')
    if (('Inter - Maiorca 1-0' not in row14) or match14 < 0 or bench14 < match14
            or 'M. Serena (83’ Gimmelli)' not in row14[match14:bench14]
            or 'Gimmelli' in row14[bench14:]):
        raise ValueError('Aug14 Serena XI/Gimmelli substitution source differs')
    match28 = row28.find('Inter:')
    bench28 = row28.find('A disposizione:')
    if ('Inter - Olympiakos 2-2' not in row28 or match28 < 0 or bench28 < match28
            or 'M. Serena' not in row28[match28:bench28]
            or 'Macellari' not in row28[match28:bench28]
            or 'Gimmelli' not in row28[bench28:]):
        raise ValueError('Aug28 Serena/Gimmelli source entry differs')

    soup = BeautifulSoup(bodies['dfb'], 'html.parser')
    def row_for(name):
        matches = []
        for table in soup.select('table'):
            head = table.find('thead')
            if not head or ' '.join(head.get_text(' ', strip=True).split()) != 'Abwehr':
                continue
            matches.extend(tr for tr in table.select('tbody tr') if name in tr.get_text(' ', strip=True))
        if len(matches) != 1:
            raise ValueError('DFB must contain exactly one defender row for ' + name)
        return [' '.join(x.get_text(' ', strip=True).split())
                for x in matches[0].find_all(['th', 'td'], recursive=False)]
    gimmelli = row_for('Roberto Gimmelli')
    serena = row_for('Michele Serena')
    if gimmelli != ['38', 'Roberto Gimmelli (bis 30.06.2001)', '16.07.1982']:
        raise ValueError('DFB Gimmelli defender/DOB/shirt row differs')
    if serena != ['6', 'Michele Serena (bis 30.06.2001)', '10.03.1970']:
        raise ValueError('DFB Serena defender/DOB/shirt row differs')

    adjudication = json.loads(bodies['gimmelli_adjudication'])
    if (adjudication.get('schema') != 'pm99-gimmelli-identity-source-adjudication-v2'
            or adjudication.get('case_id') != CASE_ID):
        raise ValueError('Gimmelli source adjudication differs')
    secondary = adjudication.get('nationality_secondary_evidence', [])
    if len(secondary) != 2 or any(sha(row['extract'].encode()) != row.get('extract_sha256')
                                  for row in secondary):
        raise ValueError('Gimmelli ITA secondary extracts are not hash-bound')
    domains = {urlparse(row.get('url', '')).hostname for row in secondary}
    if (len(domains) != 2 or None in domains
            or not any('italienischer' in row['extract'].casefold() for row in secondary)
            or not any('nacionalidad: italia' in row['extract'].casefold() for row in secondary)):
        raise ValueError('two distinct retained ITA secondary nationality extracts are required')

    profiles = json.loads(bodies['serena_profiles'])
    if profiles.get('schema') != 'pm99-serena-source-profile-adjudication-v1' or profiles.get('case_id') != CASE_ID:
        raise ValueError('Serena profile adjudication differs')
    by_url = {r.get('url'): r for r in profiles.get('sources', [])}
    inter = by_url.get(SERENA_URL)
    tm = by_url.get(SERENA_ROLE_URL)
    if not inter or not tm:
        raise ValueError('official Inter and Transfermarkt Serena profile extracts required')
    for row in (inter, tm):
        if sha(row['extract'].encode()) != row.get('extract_sha256'):
            raise ValueError('Serena web extract SHA differs')
    if ('Michele Serena' not in inter['extract'] or 'Difensore' not in inter['extract'] or 'Italia' not in inter['extract']
            or '10-03-1970' not in inter['extract']):
        raise ValueError('official Inter Serena identity/broad role/nationality extract differs')
    if ('Michele Serena' not in tm['extract'] or 'Position: Left-Back' not in tm['extract']
            or tm.get('representation') != 'web search result extraction; direct open returned anti-bot page, not raw HTML'):
        raise ValueError('Serena profile fine-role evidence/representation differs')
    lb = historical_roles.ROLE_MAP.get('LB')
    if lb != 2 or not exact_roles.compatible('D', lb) or not exact_roles.compatible('D', 4):
        raise ValueError('retained left-back role does not map to a D-compatible native code')
    return {
        'opening_membership': {
            '2000-08-14': {'fixture': 'Inter–Maiorca 1–0', 'Serena': 'starts',
                           'Gimmelli': 'enters for Serena at 83 minutes'},
            '2000-08-28': {'fixture': 'Inter–Olympiakos 2–2',
                           'Serena': 'starts and is replaced at 46 minutes',
                           'Gimmelli': 'named in substitutes'},
        },
        'dfb_rows': {'Gimmelli': gimmelli, 'Serena': serena, 'section': 'Abwehr'},
        'shirt_storage_limit': 'DFB numbers are source evidence only; mode-1 native shirt storage is unproven, so preserve the existing destination-carrier shirt bytes.',
        'nationality': {'Serena': 'ITA via official Inter profile',
                        'Gimmelli': 'ITA via two separately retained secondary web extracts; DFB table has no nationality field'},
        'fine_roles': {'Serena': {'profile_label': 'Left-Back', 'mapped_label': 'LB',
                                  'native_code': lb, 'claim_limit': 'profile role; not a dated 2000 tactical placement'},
                       'Gimmelli': {'native_code': 4,
                                    'claim_limit': 'explicit editorial CB code; DFB only supports broad Abwehr/D'}},
        'weight_conflict': '11v11 Serena profile reports 76kg; preserve existing recipe/native 79kg and do not update it.',
    }


def rating_for_gimmelli(actor, request):
    model_path = ROOT / 'scripts/season_editorial_ratings_v1.py'
    if sha(model_path.read_bytes()) != request['rating_policy']['model_sha256']:
        raise ValueError('pinned editorial model hash differs')
    policy = request['rating_policy']
    value = {
        'schema_version': ratings.INPUT_SCHEMA,
        'snapshot_date': policy['snapshot_date'],
        'hierarchy': {'schema_version': ratings.HIERARCHY_SCHEMA,
                      'snapshot_date': policy['snapshot_date'],
                      'clubs': [{'club_id': actor['club_id'], 'strength': policy['italy_club_strength'],
                                 'source_ids': [MODEL_ID]}]},
        'players': [{'player_id': actor['id'], 'person_id': 'person-source-dfb-gimmelli-1982-07-16',
                     'club_id': actor['club_id'], 'position': 'D', 'birth_date': '1982-07-16',
                     'height_cm': None, 'squad_status': 'opening_squad'}],
    }
    output = ratings.build_rating_output(value)
    row = output['player_ratings'][0]['ratings']
    if not 1 <= row['values']['handling'] <= 20:
        raise ValueError('outfield handling cap failed')
    return {
        'stored': {'profile': row['profile'], 'values': copy.deepcopy(row['values']),
                   'provenance': {'method': 'deterministic editorial rating model v1',
                                  'proof_grade': 'reviewed-editorial', 'source_ids': [MODEL_ID]}},
        'input': value, 'model_sha256': ratings.MODEL_SHA256,
        'output_sha256': sha(canonical(output)),
    }


def prepare(base, input_path) -> dict:
    request_path = Path(input_path)
    if not request_path.is_absolute():
        request_path = ROOT / request_path
    if request_path.is_symlink() or not request_path.is_file():
        raise ValueError('request must be a regular workspace file')
    request_path = request_path.resolve()
    if not request_path.is_relative_to(ROOT.resolve()):
        raise ValueError('request must be a retained non-symlink workspace file')
    request = json.loads(request_path.read_text(encoding='utf-8'))
    if request.get('schema') != INPUT_SCHEMA or request.get('case_id') != CASE_ID:
        raise ValueError('exact typed two-slot request required')
    if base.season != '2000-01' or base.release_id != request.get('release_id'):
        raise ValueError('request must name exact registered 2000-01 parent')
    parent = exact_parent(base)
    if parent != request.get('parent'):
        raise ValueError('exact parent manifest/package/JUG/EQ/MINIFOTO hashes differ')
    bodies, source_bindings = read_sources(request)
    source_facts = validate_sources(bodies)
    package = json.loads(Path(base.package_path).read_text(encoding='utf-8'))
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    by_carrier = {p['carrier_id']: p for p in package['players']}
    by_club = {c['carrier_id']: c for c in package['clubs']}
    if any(row.get('id') == MODEL_ID for row in package.get('sources', [])):
        raise ValueError('editorial rating source ID collision; use a new adapter version')
    if any(row.get('id', '').startswith(PREFIX) for row in package.get('artifacts', [])):
        raise ValueError('prior Serena/Gimmelli layer exists; this transaction is not stackable')
    expected = {14660: ('Stephane Dalmat', 'S. Dalmat', 'M', '1979-02-16', 11,
                        [16, 10, 12, 98, 98, 98]),
                4211: ('Michele Serena', 'Michele Serena', 'D', '1970-03-10', 98,
                       [17, 10, 16, 12, 98, 98])}
    before = {}
    native_before = {}
    entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(jug).entries}
    for carrier, (srcname, display, broad, dob, order, old_roles) in expected.items():
        p = by_carrier.get(carrier)
        nf = native_facts(jug, carrier)
        if (p is None or p['club_id'] != 'club-225' or p['source_name'] != srcname
                or p['name'] != display or nf['name'].casefold() != display.casefold()
                or p['facts']['birth_date'] != dob or nf['birth_date'] != dob
                or nf['position'] != broad or nf['startup_order'] != order):
            raise ValueError('two-slot identity/order/native preimage differs at ' + str(carrier))
        payload = entries[carrier].decode_payload(jug)
        _, roles = read_indexed_native_roles(payload, carrier)
        if roles != old_roles:
            raise ValueError('two-slot fine-role native preimage differs at ' + str(carrier))
        before[carrier] = copy.deepcopy(p)
        native_before[str(carrier)] = {'facts': nf, 'fine_roles': roles,
            'payload_sha256': sha(payload), 'opening_order': nf['startup_order']}
    if native_owners(eq).get(14660) != {225} or native_owners(eq).get(4211) != {225}:
        raise ValueError('both targets must remain exclusively linked to Inter225')
    psg = by_carrier.get(7275)
    if psg is None or psg.get('source_name') != 'Stéphane Dalmat' or psg['club_id'] != 'club-502':
        raise ValueError('PSG Dalmat preservation anchor differs')
    if any(p['carrier_id'] not in (14660, 4211) and
           (p.get('source_name') or p['name']).casefold().find('gimmelli') >= 0
           for p in package['players']):
        raise ValueError('Gimmelli already appears elsewhere in preferred package')
    if len(by_club[225]['roster_player_ids']) != 36:
        raise ValueError('Inter roster membership preimage differs')
    selected_player_ids = {'player-4211', 'player-14660'}
    old_portraits = [copy.deepcopy(row) for row in package['assets']['portraits']
                     if row['player_id'] in selected_player_ids]
    if len(old_portraits) != 2:
        raise ValueError('both exact parent portrait metadata rows are required')

    # Source entries assign identities to the current native startup-order slots.
    # The package deliberately retains its mode-1 opening policy and does not
    # encode a declarative XI/substitute list for this club.
    club = by_club[225]
    if club.get('opening', {}).get('policy') != 'preserve-existing-mode1':
        raise ValueError('Inter mode-1 opening policy preimage changed')

    plan = {
        'schema': SCHEMA, 'mode': MODE, 'case_id': CASE_ID, 'season': base.season,
        'release_id': base.release_id, 'source_input': {
            'path': str(request_path.relative_to(ROOT)), 'sha256': sha(request_path.read_bytes())},
        'parent': parent, 'package_document_sha256': sha(canonical(package)),
        'sources': source_bindings, 'source_facts': source_facts,
        'native_before': native_before,
        'slots': {}, 'preserved': {'club_225': copy.deepcopy(club),
                                  'PSG_Dalmat_7275': copy.deepcopy(psg),
                                  'whole_roster_count': len(club['roster_player_ids'])},
        'portrait_scope': {'minifoto_pre_sha256': parent['minifoto_sha256'],
                           'selected_loose_preimages': copy.deepcopy(parent['selected_loose_bitmaps']),
                           'package_portrait_rows_before': old_portraits,
                           'policy': 'clear only selected old-identity portrait flags/loose paths; preserve all unrelated image bytes'},
        'scope': {'changed_carriers': [4211, 14660], 'eq_unchanged': True,
                  'native_startup_order_bytes_unchanged': True,
                  'all_unselected_recipe_players_exact': True,
                  'all_unselected_native_records_exact': True,
                  'build_source_runtime_publication': 'not performed'},
    }
    from scripts import season_editorial_ratings_v1 as er
    if sha((ROOT / 'scripts/season_editorial_ratings_v1.py').read_bytes()) != request['rating_policy']['model_sha256']:
        raise ValueError('rating model file snapshot changed')
    g = rating_for_gimmelli(before[4211], request)
    gimmelli_rating = copy.deepcopy(g['stored'])
    gimmelli_rating['provenance']['source_ids'] = [MODEL_ID]
    plan['slots']['4211'] = {
        'player_id': before[4211]['id'], 'before': before[4211],
        'after': {'person_id': 'person-source-dfb-gimmelli-1982-07-16',
                  'name': 'Gimmelli', 'source_name': 'Roberto Gimmelli',
                  'birth_date': '1982-07-16', 'nationality': 'ITA', 'primary_position': 'D',
                  'fine_roles': [4], 'shirt_number': {'policy': 'preserve-existing-mode1'},
                  'height_cm': {'policy': 'preserve-existing-mode1'},
                  'weight_kg': {'policy': 'preserve-existing-mode1'},
                  'ratings': gimmelli_rating},
        'rating_input': g['input'], 'rating_model_sha256': g['model_sha256'],
        'rating_output_sha256': g['output_sha256'],
        'fine_role_status': 'editorial CB role [4], not a DFB fine-role claim',
        'display_window': {'display': 'Gimmelli', 'full_name_retained_in_source_name': True},
    }
    target = before[14660]
    source_serena = before[4211]
    plan['slots']['14660'] = {
        'player_id': target['id'], 'before': target,
        'after': {'person_id': source_serena['person_id'], 'name': 'Serena', 'source_name': 'Michele Serena',
                  'birth_date': '1970-03-10', 'nationality': 'ITA', 'primary_position': 'D',
                  'fine_roles': [2], 'shirt_number': {'policy': 'preserve-existing-mode1'},
                  'height_cm': source_serena['facts']['height_cm'],
                  'weight_kg': source_serena['facts']['weight_kg'],
                  'ratings': copy.deepcopy(source_serena['ratings'])},
        'fine_role_status': 'source profile Left-Back mapped LB→2; not a dated 2000 tactical placement',
        'rating_status': 'all ten current recipe/native ratings preserved exactly',
        'weight_status': 'existing79kg preserved despite 11v11 profile76kg conflict',
    }
    plan['transaction_id'] = sha(canonical(plan))[:24]
    return plan


def _post_actor(before: dict, slot: dict, aid: str) -> dict:
    actor = copy.deepcopy(before)
    carrier = slot['before']['carrier_id']
    proof = {'artifact_id': aid, 'grade': 'source-receipt'}
    f = slot['after']
    actor.update(person_id=f['person_id'], name=f['name'], source_name=f['source_name'])
    actor['facts'] = {**before['facts'], 'birth_date': f['birth_date'],
                          'nationality': f['nationality'], 'primary_position': f['primary_position'],
                          'fine_roles': copy.deepcopy(f['fine_roles']),
                          'shirt_number': f['shirt_number']}
    if carrier == 4211:
        actor['facts']['height_cm'] = {'policy': 'preserve-existing-mode1'}
        actor['facts']['weight_kg'] = {'policy': 'preserve-existing-mode1'}
        preserved = {'height_cm', 'weight_kg', 'shirt_number'}
    else:
        actor['facts']['height_cm'] = copy.deepcopy(f['height_cm'])
        actor['facts']['weight_kg'] = copy.deepcopy(f['weight_kg'])
        actor['facts']['shirt_number'] = {'policy': 'preserve-existing-mode1'}
        preserved = {'shirt_number'}
    actor['ratings'] = copy.deepcopy(f['ratings'])
    actor['fact_fallbacks'] = [row for row in before.get('fact_fallbacks', [])
                                   if row.get('field') not in {'birth_date', 'nationality', 'primary_position',
                                                               'fine_roles', 'shirt_number', 'height_cm', 'weight_kg'}]
    for field in sorted(preserved):
        actor['fact_fallbacks'].append({'field': field, 'method': 'preserve-existing-mode1',
                'proof': copy.deepcopy(proof), 'value': {'policy': 'preserve-existing-mode1'},
                'reason': ('Mode-1 shirt-number storage is unproven; the DFB number remains source evidence only.'
                           if field == 'shirt_number' else
                           'No supported target-period measurement is bound; preserve this carrier byte.')})
    actor['fact_fallbacks'].sort(key=lambda row: row['field'])
    actor['proof'] = copy.deepcopy(proof)
    return actor


def _source_rows(plan: dict) -> tuple[list[dict], dict]:
    aid = artifact_id(plan)
    sources = [
        {'id': 'source-' + aid, 'title': 'Storia Inter friendlies, DFB 2000/01 roster, Inter and Serena profile receipts',
         'uri': STORIA_URL, 'proof_grade': 'source-receipt', 'evidence_artifact_id': aid},
        {'id': MODEL_ID, 'title': 'Deterministic editorial Gimmelli rating model v1',
         'uri': 'local://scripts/season_editorial_ratings_v1.py', 'proof_grade': 'reviewed-editorial',
         'evidence_artifact_id': aid},
    ]
    proof = {'id': 'proof-' + aid, 'artifact_id': aid, 'grade': 'source-receipt',
        'covers': ['two dated Inter opening cohort memberships',
        'DFB defender identity DOB and shirt numbers', 'Serena official identity/nationality and profile fine role',
        'Gimmelli explicitly editorial fine role and ratings', 'no old portrait reused']}
    return sources, proof


def _portrait_rows(plan: dict) -> list[dict]:
    aid = artifact_id(plan)
    proof = {'artifact_id': aid, 'grade': 'source-receipt'}
    return [{'player_id': pid, 'status': 'native-no-photo', 'proof': copy.deepcopy(proof),
        'review_reason': 'Identity replacement has no supplied replacement portrait; old identity photo not reused.'}
        for pid in ('player-14660', 'player-4211')]


def materialize_package(parent_package: dict, plan: dict) -> dict:
    result = copy.deepcopy(parent_package)
    people = {p['carrier_id']: p for p in result['players']}
    aid = artifact_id(plan)
    proof = {'artifact_id': aid, 'grade': 'source-receipt'}
    for raw_carrier in ('4211', '14660'):
        carrier = int(raw_carrier)
        slot = plan['slots'][raw_carrier]
        actor = people[carrier]
        if actor != slot['before']:
            raise ValueError('whole-package target preimage differs at ' + str(carrier))
        actor.clear(); actor.update(_post_actor(slot['before'], slot, aid))
    assets = result['assets']
    target_ids = {'player-4211', 'player-14660'}
    old = [row for row in assets['portraits'] if row['player_id'] in target_ids]
    if len(old) != 2:
        raise ValueError('both old portrait metadata entries must exist before replacement')
    assets['portraits'] = [row for row in assets['portraits'] if row['player_id'] not in target_ids]
    assets['portraits'].extend(_portrait_rows(plan))
    assets['portraits'].sort(key=lambda row: row['player_id'])
    result['artifacts'].append({'id': aid, 'kind': 'season-input',
        'sha256': sha(canonical(plan)), 'media_type': 'application/json',
        'relative_path': filename(plan)})
    result['artifacts'].sort(key=lambda row: row['id'])
    source_rows, proof_row = _source_rows(plan)
    result['sources'].extend(source_rows)
    result['sources'].sort(key=lambda row: row['id'])
    result['proofs'].append(proof_row)
    result['proofs'].sort(key=lambda row: row['id'])
    packages.validate_package(result, strict=False)
    # Entire non-target recipe remains byte-for-byte object-equal.
    for p in parent_package['players']:
        if p['carrier_id'] not in (4211, 14660):
            if next(q for q in result['players'] if q['id'] == p['id']) != p:
                raise ValueError('unselected player changed: ' + p['id'])
    for key in ('clubs', 'managers', 'calendar', 'migration'):
        if result[key] != parent_package[key]:
            raise ValueError('unselected package section changed: ' + key)
    return result


def _is_exact_post_package(package: dict, plan: dict) -> bool:
    """Reverse only this complete layer and require the exact parent document hash."""
    restored = copy.deepcopy(package)
    aid = artifact_id(plan)
    artifact = {'id': aid, 'kind': 'season-input', 'sha256': sha(canonical(plan)),
                'media_type': 'application/json', 'relative_path': filename(plan)}
    artifact_rows = [row for row in restored.get('artifacts', []) if row.get('id') == aid]
    if artifact_rows != [artifact]:
        return False
    expected_sources, expected_proof = _source_rows(plan)
    for expected in expected_sources:
        rows = [row for row in restored.get('sources', []) if row.get('id') == expected['id']]
        if rows != [expected]:
            return False
    proof_rows = [row for row in restored.get('proofs', []) if row.get('id') == expected_proof['id']]
    if proof_rows != [expected_proof]:
        return False
    people = {row['carrier_id']: row for row in restored.get('players', [])}
    for raw_carrier in ('4211', '14660'):
        carrier = int(raw_carrier)
        slot = plan['slots'][raw_carrier]
        expected = _post_actor(slot['before'], slot, aid)
        if people.get(carrier) != expected:
            return False
        people[carrier].clear(); people[carrier].update(copy.deepcopy(slot['before']))
    targeted = {'player-4211', 'player-14660'}
    actual_portraits = [row for row in restored.get('assets', {}).get('portraits', [])
                        if row.get('player_id') in targeted]
    if actual_portraits != _portrait_rows(plan):
        return False
    restored['assets']['portraits'] = [row for row in restored['assets']['portraits']
                                       if row.get('player_id') not in targeted]
    restored['assets']['portraits'].extend(copy.deepcopy(plan['portrait_scope']['package_portrait_rows_before']))
    restored['assets']['portraits'].sort(key=lambda row: row['player_id'])
    restored['artifacts'] = [row for row in restored['artifacts'] if row.get('id') != aid]
    restored['sources'] = [row for row in restored['sources']
                           if row.get('id') not in {item['id'] for item in expected_sources}]
    restored['proofs'] = [row for row in restored['proofs'] if row.get('id') != expected_proof['id']]
    restored['artifacts'].sort(key=lambda row: row['id'])
    restored['sources'].sort(key=lambda row: row['id'])
    restored['proofs'].sort(key=lambda row: row['id'])
    return sha(canonical(restored)) == plan['package_document_sha256']


def apply_pair(base, jug: bytes, eq: bytes, plan: dict) -> tuple[bytes, bytes]:
    if exact_parent(base) != plan['parent']:
        raise ValueError('registered parent changed')
    original = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    original_eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if eq != original_eq:
        raise ValueError('EQ is invariant for this transaction')
    package = json.loads(Path(base.package_path).read_text(encoding='utf-8'))
    post_package = materialize_package(package, plan)
    codes = compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    selected = {slot['player_id'] for slot in plan['slots'].values()}
    candidate = delta.compile_players(original, post_package, selected, codes)
    before = {e.record_id: e for e in IndexedFDIFile.from_bytes(original).entries}
    after = {e.record_id: e for e in IndexedFDIFile.from_bytes(candidate).entries}
    if before.keys() != after.keys():
        raise ValueError('indexed JUG carrier directory changed')
    changed = [cid for cid, entry in before.items()
               if entry.decode_payload(original) != after[cid].decode_payload(candidate)]
    if changed != [4211, 14660]:
        raise ValueError('expected only source-positive Inter actors to change: ' + repr(changed))
    for cid, expected_name, dob, broad, fine, order in (
            (4211, 'Gimmelli', '1982-07-16', 'D', 4, 98),
            (14660, 'Serena', '1970-03-10', 'D', 2, 11)):
        facts = native_facts(candidate, cid)
        payload = after[cid].decode_payload(candidate)
        _, native_roles = read_indexed_native_roles(payload, cid)
        native_row = roster.native_player(payload, cid)
        nationality = payload[native_row['name_end'] + 8] ^ 0x61
        expected_country = compiler._country_code('ITA', dict(codes))
        if (facts['name'].casefold() != expected_name.casefold() or facts['birth_date'] != dob
                or facts['position'] != broad or facts['startup_order'] != order
                or native_roles[0] != fine or nationality != expected_country):
            raise ValueError('native readback differs for actor ' + str(cid) + ': ' + repr((facts, native_roles, nationality)))
    # Exact bytes for all other native player payloads; order stays on each slot.
    if candidate == original:
        raise ValueError('native transaction unexpectedly produced no change')
    if jug not in (original, candidate):
        raise ValueError('apply accepts only exact full parent or full postimage')
    return candidate, original_eq


def _bound_base(plan: dict):
    if plan.get('schema') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('wrong Serena/Gimmelli schema or mode')
    base = registry.load_registered_release(plan.get('season'), plan.get('release_id'))
    if exact_parent(base) != plan.get('parent'):
        raise ValueError('registered source parent no longer matches the plan')
    return base


def verify(base, plan: dict) -> None:
    if plan.get('schema') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('wrong Serena/Gimmelli schema or mode')
    registered = _bound_base(plan)
    if (Path(registered.package_path).resolve() != Path(base.package_path).resolve()
            or Path(registered.game_path).resolve() != Path(base.game_path).resolve()):
        raise ValueError('verify requires the exact registered release object')
    input_path = Path(plan['source_input']['path'])
    if not input_path.is_absolute():
        input_path = ROOT / input_path
    if input_path.is_symlink() or not input_path.is_file():
        raise ValueError('bound source request is missing or is a symlink')
    input_path = input_path.resolve()
    if not input_path.is_relative_to(ROOT.resolve()) or sha(input_path.read_bytes()) != plan['source_input']['sha256']:
        raise ValueError('bound source request path/hash changed')
    reproduced = prepare(registered, input_path)
    if canonical(reproduced) != canonical(plan):
        raise ValueError('source-bound plan does not reproduce exactly')


def bind(package: dict, plan: dict) -> dict:
    base = _bound_base(plan)
    verify(base, plan)
    raw = Path(base.package_path).read_bytes()
    original = json.loads(raw)
    if sha(raw) != plan['parent']['package_sha256'] or sha(canonical(original)) != plan['package_document_sha256']:
        raise ValueError('exact complete registered recipe preimage differs')
    supplied = canonical(package)
    if supplied == canonical(original):
        return materialize_package(original, plan)
    if _is_exact_post_package(package, plan):
        return copy.deepcopy(package)
    raise ValueError('bind accepts only the exact complete parent or exact complete postimage package')


def apply(jug: bytes, eq: bytes, plan: dict) -> tuple[bytes, bytes]:
    base = _bound_base(plan)
    verify(base, plan)
    original_jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    original_eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if sha(original_jug) != plan['parent']['jug_sha256'] or sha(original_eq) != plan['parent']['eq_sha256']:
        raise ValueError('exact registered JUG/EQ parent differs')
    return apply_pair(base, jug, eq, plan)


def selected_carriers(plan: dict) -> set[int]:
    if plan.get('schema') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('wrong Serena/Gimmelli schema or mode')
    return {4211, 14660}


def apply_minifoto(data: bytes, plan: dict) -> bytes:
    base = _bound_base(plan)
    verify(base, plan)
    original = (base.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
    if sha(original) != plan['parent']['minifoto_sha256']:
        raise ValueError('exact registered MINIFOTO parent differs')
    expected, _ = delta.no_photo_archive(original, selected_carriers(plan))
    if data not in (original, expected):
        raise ValueError('MINIFOTO accepts only complete preimage or exact selected no-photo postimage')
    return expected


def remove_loose_bitmap(data: bytes | None, carrier_id: int, plan: dict) -> None:
    if carrier_id not in selected_carriers(plan):
        raise ValueError('loose image removal is limited to the two selected carriers')
    expected = plan['portrait_scope']['selected_loose_preimages'][str(carrier_id)]
    if data is None:
        if expected['present']:
            raise ValueError('selected loose bitmap preimage is unexpectedly absent')
        return None
    if (not expected['present'] or len(data) != expected['bytes']
            or sha(data) != expected['sha256']):
        raise ValueError('selected loose bitmap differs from its exact bound preimage')
    return None


def source_artifact(plan: dict) -> dict:
    raw = canonical(plan)
    return {'filename': filename(plan), 'document': copy.deepcopy(plan),
            'sha256': sha(raw), 'bytes': raw}


def reject_factory_recipe(package: dict) -> None:
    prefix = PREFIX
    if any(a.get('id', '').startswith(prefix) for a in package.get('artifacts', [])):
        raise ValueError('Serena/Gimmelli recipe requires source-bound replay; factory compilation cannot reconstruct this layer')


def _source_preflight(previous):
    # Return before touching inherited locator fields for every other receipt.
    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    relative = getattr(previous, 'locator', {}).get('sourced_profile_assignment_plan_path')
    if not relative:
        raise ValueError('Serena/Gimmelli SOURCE receipt lacks assignment-plan locator')
    plan_path = (ROOT / relative).resolve()
    if not plan_path.is_relative_to(ROOT.resolve()):
        raise ValueError('SOURCE assignment plan escaped the workspace')
    plan = pipeline.read_json_file(plan_path)
    if plan.get('schema') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('SOURCE locator names a different adapter plan')
    base = _bound_base(plan)
    verify(base, plan)
    expected_plan_path = (Path(previous.package_path).parent / filename(plan)).resolve()
    if (plan_path != expected_plan_path
            or registry.sha256_file(plan_path) != receipt.get('original_profile_assignment_plan_sha256')):
        raise ValueError('SOURCE plan path or raw file SHA differs from its compiler receipt')
    package_path = Path(previous.package_path)
    package = pipeline.read_json_file(package_path)
    artifact_rows = [a for a in package.get('artifacts', []) if a.get('id') == artifact_id(plan)]
    if (len(artifact_rows) != 1 or artifact_rows[0].get('relative_path') != filename(plan)
            or artifact_rows[0].get('sha256') != sha(canonical(plan))
            or registry.sha256_file(plan_path) != sha(canonical(plan))):
        raise ValueError('SOURCE package artifact is not the exact canonical plan document')
    if not _is_exact_post_package(package, plan):
        raise ValueError('SOURCE would discard or alter a complete recipe change')
    descriptor = package_path.parent / 'role-delta-input.json'
    expected_descriptor = {'season': base.season, 'release_id': base.release_id,
        'package_sha256': registry.sha256_file(base.package_path),
        'jug_sha256': registry.sha256_file(base.game_path / 'DBDAT/JUG98030.FDI'),
        'updates': [], 'unresolved': []}
    if pipeline.read_json_file(descriptor) != expected_descriptor:
        raise ValueError('SOURCE inert role descriptor differs')
    for release in (base, previous):
        pipeline.assert_tree_matches_inventory(release.game_path, pipeline.read_json_file(release.inventory_path))
    return {'receipt': receipt, 'plan': plan, 'plan_path': plan_path,
            'base': base, 'package': package, 'descriptor': descriptor,
            'inventory': pipeline.read_json_file(previous.inventory_path)}


def reconstruction(previous, release_id: str):
    prepared = _source_preflight(previous)
    if prepared is None:
        return None
    base = prepared['base']
    plan = prepared['plan']
    plan_path = prepared['plan_path']
    package_path = Path(previous.package_path)
    package = prepared['package']
    descriptor = prepared['descriptor']
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(base.season, descriptor, release_id=release_id,
        source_release_id=base.release_id, profile_assignment_plan_path=plan_path)
    rebuilt = registry.load_registered_release(base.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, prepared['inventory'])
    if Path(rebuilt.package_path).read_bytes() != package_path.read_bytes():
        raise ValueError('SOURCE complete recipe bytes differ after reconstruction')
    return {'season': base.season, 'release_id': release_id,
        'complete_game_inventory_identical': True, 'complete_recipe_identical': True,
        'compilation_mode': MODE}


def rebase_request(base, output_path: str | Path, template_path: str | Path) -> dict:
    """Write a new immutable request for an already-registered exact parent.

    This is deliberately separate from prepare: after r223 is registered the
    caller passes that release and a new output path. Existing requests stay
    untouched, and every retained source body is revalidated before rebasing.
    """
    if base.season != '2000-01':
        raise ValueError('adapter request rebase is limited to season 2000-01')
    template = Path(template_path)
    if not template.is_absolute():
        template = ROOT / template
    if template.is_symlink() or not template.is_file():
        raise ValueError('request template must be a retained regular file')
    template = template.resolve()
    if not template.is_relative_to(ROOT.resolve()):
        raise ValueError('request template escaped the workspace')
    request = json.loads(template.read_text(encoding='utf-8'))
    if request.get('schema') != INPUT_SCHEMA or request.get('case_id') != CASE_ID:
        raise ValueError('request template schema/case differs')
    read_sources(request)
    request['season'] = base.season
    request['release_id'] = base.release_id
    request['parent'] = exact_parent(base)
    output = Path(output_path)
    if not output.is_absolute():
        output = ROOT / output
    resolved_parent = output.parent.resolve()
    if not resolved_parent.is_relative_to(ROOT.resolve()):
        raise ValueError('rebase output must remain in the retained workspace')
    output = resolved_parent / output.name
    if output.exists() or output.is_symlink():
        raise ValueError('rebase output must be a new path; preserve prior requests')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical(request))
    return {'path': str(output.resolve().relative_to(ROOT)), 'sha256': sha(output.read_bytes()),
            'parent': request['parent'], 'release_id': base.release_id}
