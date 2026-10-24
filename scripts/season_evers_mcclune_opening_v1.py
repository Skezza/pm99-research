"""Private publisher-shaped Evers/McClune transaction candidate.

The plan is exact-parent-bound through its explicit request, but has no pinned
release ID or parent file digests in code. This permits rebasing the retained
source request onto a later registered 2000-01 child without reacquiring source.
All native writes are returned as bytes; this module never writes game files.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from statistics import median

from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, read_initial_order, patch_initial_orders
from app.xor import xor_encode, xor_decode
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_package_v2 as packages, season_package_compiler_v2 as compiler
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts.season_opening_order_repair_v1 import native_owners

MODE = 'source-bound-evers-mcclune-opening-ownership-v1'
SCHEMA = 'pm99-source-bound-evers-mcclune-opening-v1'
PREFIX = 'source-bound-evers-mcclune-'
INPUT_SCHEMA = SCHEMA + '-input'
WEB_PATH = '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/evers-correction-proposal-v1/mcclune-11v11-web-response.json'
WEB_RECEIPT = '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/evers-correction-proposal-v1/mcclune-11v11-web-response.source.json'
EVERS_ROOT = '.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/crossclub-firsttwo-research-v1'
EVERS_SOURCES = {
    'career': (EVERS_ROOT + '/raw/evers-soccerbase-profile.html', '66cb94ead4c9ff5a088a05d9161e74ec3643bbd3e34793dafcc1855bec0b14f1'),
    'contemporary': (EVERS_ROOT + '/raw/evers-contemporary-2000-reading.html', 'eee0bc902b75445ac7c6764c4313c3ebdc1db12623c702b3f4d6e9aaf2cbb336'),
    'plymouth_opener': (EVERS_ROOT + '/raw/evers-plymouth-opening-match.html', '878680ababeb4d785fff4be732bb702da6c853f84e89d2e6c797296a4dbd7078'),
    'stjohnstone_opener': ('.local/transfermarkt-opening-plans-current-v1/2000-01/cache/report/3838374.html', '8c7a07e4ccafd12914e3e7d0ac96ee4febd0853a4d90460e168b68e803511525'),
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact_bytes(plan):
    # canonical_json_bytes supplies exactly one terminal LF; no self-hash is
    # embedded in the document, so the package artifact hashes this full file.
    return packages.canonical_json_bytes(plan)


def filename(plan):
    return PREFIX + plan['transaction_id'] + '.json'


def artifact_id(plan):
    return PREFIX + plan['transaction_id']


def selected_carriers(plan):
    verify(registry.load_registered_release(plan['season'], plan['release_id']), plan)
    return {29917}


def _safe_input(path):
    p = Path(path)
    if not p.is_absolute():
        p = registry.ROOT / p
    p = p.resolve()
    if not p.is_relative_to(registry.ROOT.resolve()) or p.is_symlink() or not p.is_file():
        raise ValueError('input must be a retained workspace file')
    return p


def _sha_file(path):
    return digest(Path(path).read_bytes())


def _web_text():
    p = (registry.ROOT / WEB_PATH).resolve()
    rp = (registry.ROOT / WEB_RECEIPT).resolve()
    if not p.is_relative_to(registry.ROOT.resolve()) or not rp.is_relative_to(registry.ROOT.resolve()):
        raise ValueError('McClune source path escaped workspace')
    b = p.read_bytes()
    recbytes = rp.read_bytes()
    rec = json.loads(recbytes)
    text = json.loads(b)
    if (rec.get('response_sha256') != digest(b)
            or rec.get('representation') != 'web-extracted-text, not raw HTML'
            or rec.get('url') != 'https://www.11v11.com/players/david-mcclune-14445/'
            or not isinstance(text, str)):
        raise ValueError('McClune original web-text/receipt binding differs')
    anchors = ['David McClune', 'Date of birth  | 08 February 1983',
               'Nationality  | Scottish', 'Position  | Full back',
               'St Johnstone  | 09 Aug 1999',
               '2000-01  | St Johnstone  | Scottish Premier League  | 5']
    if any(x not in text for x in anchors):
        raise ValueError('McClune web-extracted profile facts do not reproduce')
    return p, b, text, rp, recbytes, rec


def _check_evers_sources():
    read = {}
    for key, (rel, expected) in EVERS_SOURCES.items():
        p = (registry.ROOT / rel).resolve()
        if not p.is_relative_to(registry.ROOT.resolve()):
            raise ValueError('Evers source escaped workspace: ' + key)
        b = p.read_bytes()
        if digest(b) != expected:
            raise ValueError('retained Evers source hash changed: ' + key)
        read[key] = b.decode('utf-8', 'replace')
    if not all(x in read['career'] for x in ['Reading', 'St Johnstone', 'Plymouth', '08 Mar, 01', '13 Oct, 00', '15 Jan, 01']):
        raise ValueError('Evers original career chronology anchors missing')
    if not all(x in read['contemporary'] for x in ['Reading midfielder Sean Evers', 'returned to Reading']):
        raise ValueError('Evers contemporary Reading corroboration missing')
    if 'Sean Evers' in read['plymouth_opener']:
        raise ValueError('Plymouth opener unexpectedly identifies Evers')
    return {k: {'path': EVERS_SOURCES[k][0], 'sha256': EVERS_SOURCES[k][1]} for k in EVERS_SOURCES}


def _base_hashes(base):
    return {
        'manifest_sha256': base.manifest_sha256,
        'package_sha256': _sha_file(base.package_path),
        'jug_sha256': _sha_file(base.game_path / 'DBDAT/JUG98030.FDI'),
        'eq_sha256': _sha_file(base.game_path / 'DBDAT/EQ98030.FDI'),
    }


def rebase_request(base, input_path):
    """Return an exact-child request using retained source bindings, no rescrape."""
    p = _safe_input(input_path)
    request = pipeline.read_json_file(p)
    if request.get('schema') != INPUT_SCHEMA or base.season != '2000-01':
        raise ValueError('Evers request and registered 2000-01 parent required')
    result = copy.deepcopy(request)
    result['release_id'] = base.release_id
    result['parent'] = _base_hashes(base)
    return result


def prepare(base, input_path):
    p = _safe_input(input_path)
    request = pipeline.read_json_file(p)
    if request.get('schema') != INPUT_SCHEMA or request.get('season') != '2000-01':
        raise ValueError('exact case-scoped Evers request required')
    if base.season != request['season'] or base.release_id != request['release_id']:
        raise ValueError('request must name the exact registered 2000-01 parent')
    if _base_hashes(base) != request.get('parent'):
        raise ValueError('explicit parent manifest/package/JUG/EQ hashes differ')
    pkg = pipeline.read_json_file(base.package_path)
    jug = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    webp, webbytes, _, webreceipt, webrecbytes, webrec = _web_text()
    evers_sources = _check_evers_sources()
    p_by = {x['carrier_id']: x for x in pkg['players']}
    c_by = {x['carrier_id']: x for x in pkg['clubs']}
    ev_stj, ev_ply = p_by[29917], p_by[33121]
    if (ev_stj['name'], ev_stj['facts']['birth_date'], ev_stj['club_id']) != ('Sean Evers', '1977-10-10', c_by[1261]['id']):
        raise ValueError('St Johnstone Evers target preimage differs')
    if (ev_ply['name'], ev_ply['facts']['birth_date'], ev_ply['club_id']) != ('Sean Evers', '1977-10-10', c_by[385]['id']):
        raise ValueError('Plymouth Evers source preimage differs')
    if any(x['name'].casefold() == 'david mcclune' for x in pkg['players']):
        raise ValueError('McClune already represented in package')
    owners = native_owners(eq)
    if owners.get(29917) != {1261} or owners.get(33121) != {385}:
        raise ValueError('exact Evers native owners differ')
    from scripts.season_within_club_reserve_repair_v1 import native_facts
    for carrier in (29917, 33121):
        facts = native_facts(jug, carrier)
        if (facts['name'].casefold(), facts['birth_date']) != ('sean evers', '1977-10-10'):
            raise ValueError('native Evers preimage differs')
    rosters = {cid: c_by[cid]['roster_player_ids'] for cid in (338, 1261, 385)}
    before_counts = dict(Reading338=len(rosters[338]), StJohnstone1261=len(rosters[1261]), Plymouth385=len(rosters[385]))
    if before_counts != {'Reading338': 25, 'StJohnstone1261': 23, 'Plymouth385': 25}:
        raise ValueError('target roster counts differ')
    jix = IndexedFDIFile.from_bytes(jug); jentries = {e.record_id: e for e in jix.entries}
    player_by_id = {x['id']: x for x in pkg['players']}
    order_by_carrier = {}
    for cid in (338, 385):
        for player_id in rosters[cid]:
            carrier = player_by_id[player_id]['carrier_id']
            order_by_carrier[carrier] = read_initial_order(jentries[carrier].decode_payload(jug)).order
        observed = sorted(order_by_carrier[player_by_id[pid]['carrier_id']] for pid in rosters[cid])
        if observed != list(range(1, len(rosters[cid]) + 1)):
            raise ValueError('Reading/Plymouth current startup orders are not contiguous')
    evers_order = order_by_carrier[33121]
    if not 1 <= evers_order <= 25:
        raise ValueError('Plymouth Evers startup order is outside its roster')
    order_changes = []
    for pid in rosters[385]:
        actor = player_by_id[pid]; carrier = actor['carrier_id']
        old = order_by_carrier[carrier]
        after = 26 if carrier == 33121 else (old - 1 if old > evers_order else old)
        if after != old:
            order_changes.append({'carrier_id': carrier, 'name': read_initial_order(jentries[carrier].decode_payload(jug)).name,
                                  'before': old, 'after': after})
    after_ply = sorted(x['after'] for x in order_changes if x['carrier_id'] != 33121)
    unchanged_ply = [order_by_carrier[player_by_id[pid]['carrier_id']] for pid in rosters[385]
                     if player_by_id[pid]['carrier_id'] != 33121 and order_by_carrier[player_by_id[pid]['carrier_id']] < evers_order]
    after_ply = sorted(unchanged_ply + after_ply)
    if after_ply != list(range(1, 25)):
        raise ValueError('Plymouth startup order compaction does not produce contiguous 1..24')
    rating_model_path = registry.ROOT / 'scripts/season_rating_calibration_v3.py'
    rating_model_sha = _sha_file(rating_model_path)
    from scripts import season_rating_calibration_v3 as rating_v3
    rating_actor = copy.deepcopy(ev_stj)
    rating_actor['source_name'] = 'David McClune'; rating_actor['name'] = 'McClune'
    rating_actor['person_id'] = 'person-source-' + digest(b'11v11:14445')
    rating_actor['club_id'] = c_by[1261]['id']
    rating_actor['facts'] = {'birth_date': '1983-02-08', 'fine_roles': [1, 2], 'height_cm': 170,
        'nationality': 'SCO', 'primary_position': 'D',
        'shirt_number': copy.deepcopy(ev_stj['facts']['shirt_number']), 'weight_kg': 65}
    rating_strength = median(ply['ratings']['values']['quality'] for ply in pkg['players']
        if ply['club_id'] == c_by[1261]['id'] and ply['carrier_id'] != 29917)
    rating_input = {'player': rating_actor, 'strength': rating_strength,
                    'state': 'unknown', 'snapshot': '2000-08-01', 'model_sha256': rating_model_sha}
    rating_values = rating_v3.editorial(rating_actor, rating_strength, 'unknown', dt.date(2000, 8, 1))
    rating_values['handling'] = max(1, min(20, rating_values['handling']))
    rating_audit = {'model_sha256': rating_model_sha,
        'input_sha256': digest(packages.canonical_json_bytes(rating_input)),
        'output_sha256': digest(packages.canonical_json_bytes(rating_values)),
        'proof_grade': 'reviewed-editorial', 'does_not_preserve_old_ratings': True}
    plan = {
        'schema': SCHEMA, 'mode': MODE, 'season': base.season, 'release_id': base.release_id,
        'source_input': {'path': registry.relative_workspace_path(p), 'sha256': digest(p.read_bytes())},
        'request': request,
        'parent': request['parent'],
        'web_text_source': {'path': registry.relative_workspace_path(webp), 'sha256': digest(webbytes),
            'receipt_path': registry.relative_workspace_path(webreceipt), 'receipt_sha256': digest(webrecbytes),
            'representation': 'web-extracted-text, not raw HTML', 'provider_id': '14445',
            'receipt_url': webrec['url']},
        'evers_sources': evers_sources,
        'updates': [
            {'operation': 'replace-identity-in-place', 'carrier_id': 29917,
             'before_player_id': ev_stj['id'], 'before_name': 'Sean Evers',
             'new_identity': {'source_name': 'David McClune', 'name': 'McClune', 'provider': '11v11',
                'provider_id': '14445', 'birth_date': '1983-02-08', 'nationality': 'SCO',
                'primary_position': 'D', 'height_cm': 170, 'weight_kg': 65, 'fine_roles': [1, 2],
                'fine_role_policy': 'editorial projection of unsided source label Full back into both flank options; no side-specific historical claim',
                'native_display_policy': 'surname from original full heading; full name exceeds carrier29917 native name window'},
             'membership_policy': 'dated club membership from 09 Aug 1999; no opener XI/bench appearance claim'},
            {'operation': 'move-existing-identity', 'carrier_id': 33121,
             'player_id': ev_ply['id'], 'name': 'Sean Evers', 'before_club_carrier': 385,
             'after_club_carrier': 338,
             'membership_policy': 'Reading career through 08 Mar 2001 and contemporary 03 Oct 2000 Reading-midfielder article; no opening XI/bench claim'}],
        'expected_roster_counts': {'before': before_counts,
            'after': {'Reading338': 26, 'StJohnstone1261': 23, 'Plymouth385': 24}},
        'startup_order_changes': order_changes,
        'rating_model': {'module': 'scripts.season_rating_calibration_v3',
                         'path': 'scripts/season_rating_calibration_v3.py', 'sha256': rating_model_sha,
                         'method': 'editorial', 'snapshot': '2000-08-01', 'state': 'unknown'},
        'rating_audit': rating_audit,
        'coverage_note': 'This corrects dated club ownership only. It does not certify the complete matchday bench; optional Martin Phillips cohort coverage is not included. Reading26 capacity remains runtime-unproven.',
        'scope': 'Replace only carrier29917 identity, sourced facts, declared native-preserve fallbacks, deterministic versioned editorial ratings and target no-photo/proof/source/artifact metadata; move existing Evers33121 from Plymouth to Reading reserve order26, preserving his facts/skills/photo; compact the six following Plymouth initial-order bytes20..25 to19..24 as explicitly listed. Preserve StJ fixed23 rows, Reading original25, Plymouth other24 identities, every other fact/skill/asset/tactic/manager and all unrelated native bytes. Full Plymouth matchday bench is not certified; Martin Phillips remains unrepresented.',
    }
    plan['transaction_id'] = digest(packages.canonical_json_bytes(plan))[:24]
    return plan


def verify(base, plan):
    if plan.get('schema') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('Evers unique schema/mode mismatch')
    source = _safe_input(registry.ROOT / plan['source_input']['path'])
    if digest(source.read_bytes()) != plan['source_input']['sha256'] or prepare(base, source) != plan:
        raise ValueError('Evers request, source or native preimage no longer reproduces')


def bind(package, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan)
    if package != pipeline.read_json_file(base.package_path) or digest(packages.canonical_json_bytes(package)) != plan['parent']['package_sha256']:
        raise ValueError('whole-package exact parent preimage required')
    result = copy.deepcopy(package)
    players = {p['carrier_id']: p for p in result['players']}
    clubs = {c['carrier_id']: c for c in result['clubs']}
    evers, mc = players[33121], players[29917]
    if evers['id'] != plan['updates'][1]['player_id'] or mc['id'] != plan['updates'][0]['before_player_id']:
        raise ValueError('stable recipe actor IDs differ')
    clubs[385]['roster_player_ids'].remove(evers['id'])
    clubs[338]['roster_player_ids'].append(evers['id'])
    evers['club_id'] = clubs[338]['id']
    mc['source_name'] = 'David McClune'; mc['name'] = 'McClune'
    mc['person_id'] = 'person-source-' + digest(b'11v11:14445')
    mc['club_id'] = clubs[1261]['id']
    mc['facts'] = {'birth_date': '1983-02-08', 'fine_roles': [1, 2], 'height_cm': 170,
        'nationality': 'SCO', 'primary_position': 'D',
        'shirt_number': copy.deepcopy(mc['facts']['shirt_number']), 'weight_kg': 65}
    from scripts import season_rating_calibration_v3 as rating_v3
    model_path = registry.ROOT / 'scripts/season_rating_calibration_v3.py'
    if digest(model_path.read_bytes()) != plan['rating_model']['sha256']:
        raise ValueError('McClune editorial rating model changed after prepare')
    strength = median(p['ratings']['values']['quality'] for p in result['players']
        if p['club_id'] == clubs[1261]['id'] and p['carrier_id'] != 29917)
    rating_input = {'player': copy.deepcopy(mc), 'strength': strength,
                    'state': plan['rating_model']['state'], 'snapshot': plan['rating_model']['snapshot'],
                    'model_sha256': plan['rating_model']['sha256']}
    vals = rating_v3.editorial(mc, strength, 'unknown', dt.date(2000, 8, 1))
    vals['handling'] = max(1, min(20, vals['handling']))
    rating_input_sha = digest(packages.canonical_json_bytes(rating_input))
    rating_output_sha = digest(packages.canonical_json_bytes(vals))
    if (rating_input_sha, rating_output_sha) != (plan['rating_audit']['input_sha256'], plan['rating_audit']['output_sha256']):
        raise ValueError('McClune deterministic editorial rating input/output differs from prepared proof')
    mc['ratings'] = {'profile': 'pm99-visible-skills-v1', 'values': vals,
        'provenance': {'method': 'identity-club-role-age-optional-editorial-calibration-v3',
            'proof_grade': 'reviewed-editorial', 'source_ids': ['source-bound-rating-calibration-v3']}}
    aid = artifact_id(plan); sid = 'source-' + aid
    proof = {'artifact_id': aid, 'grade': 'source-receipt'}
    mc['proof'] = copy.deepcopy(proof); evers['proof'] = copy.deepcopy(proof)
    for fallback in mc.get('fact_fallbacks', []):
        if fallback['field'] == 'shirt_number':
            fallback['proof'] = copy.deepcopy(proof)
            fallback['reason'] = 'Existing native shirt byte preserved; no opening source shirt number claimed.'
    portraits = result['assets']['portraits']
    portraits[:] = [x for x in portraits if x.get('player_id') != mc['id']]
    portraits.append({'player_id': mc['id'], 'status': 'native-no-photo', 'proof': copy.deepcopy(proof),
        'review_reason': 'Old Evers portrait removed after identity replacement; no McClune portrait sourced.'})
    portraits.sort(key=lambda x: x['player_id'])
    result['artifacts'].append({'id': aid, 'kind': 'season-input', 'sha256': digest(_artifact_bytes(plan)),
        'media_type': 'application/json', 'relative_path': filename(plan)})
    result['artifacts'].sort(key=lambda x: x['id'])
    result['sources'].append({'id': sid, 'title': 'Dated McClune membership and Evers ownership correction',
        'uri': 'https://www.11v11.com/players/david-mcclune-14445/', 'proof_grade': 'source-receipt',
        'evidence_artifact_id': aid})
    result['sources'].sort(key=lambda x: x['id'])
    result['proofs'].append({'id': 'proof-' + aid, 'artifact_id': aid, 'grade': 'source-receipt',
        'covers': ['dated-St-Johnstone-squad-membership', 'Evers-Reading-opening-season-ownership',
                   'two-false-opening-owner-links-corrected']})
    result['proofs'].sort(key=lambda x: x['id'])
    packages.validate_package(result, strict=False)
    return result


def source_artifact(plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan)
    data = _artifact_bytes(plan)
    return {'filename': filename(plan), 'document': copy.deepcopy(plan), 'sha256': digest(data), 'bytes': data}


def apply(jug, eq, plan):
    base = registry.load_registered_release(plan['season'], plan['release_id'])
    verify(base, plan)
    oldj = (base.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    olde = (base.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    if (digest(oldj), digest(olde)) != (plan['parent']['jug_sha256'], plan['parent']['eq_sha256']):
        raise ValueError('current registered native pair differs from bound parent')
    input_pair = (digest(jug), digest(eq))
    pre = (digest(oldj), digest(olde))
    package = bind(pipeline.read_json_file(base.package_path), plan)
    codes = compiler._extract_country_codes_from_textos(base.game_path / 'DBDAT/TEXTOS.PKF')
    candidate = delta.compile_players(oldj, package, {'player-29917'}, codes)
    replacements = [OrderReplacement(x['carrier_id'], x['name'], x['before'], x['after'])
                    for x in plan['startup_order_changes']]
    candidate = patch_initial_orders(candidate, replacements)
    candidate_index = IndexedFDIFile.from_bytes(candidate)
    candidate_entries = {e.record_id: e for e in candidate_index.entries}
    post_order = {}
    for cid in (338, 385):
        club = next(c for c in package['clubs'] if c['carrier_id'] == cid)
        orders = [read_initial_order(candidate_entries[next(p['carrier_id'] for p in package['players'] if p['id'] == pid)].decode_payload(candidate)).order
                  for pid in club['roster_player_ids']]
        post_order[cid] = sorted(orders)
    if post_order != {338: list(range(1, 27)), 385: list(range(1, 25))}:
        raise ValueError('Reading/Plymouth startup order postimage is not contiguous')
    eq_index = IndexedFDIFile.from_bytes(olde); eq_entries = {e.record_id: e for e in eq_index.entries}
    carrier_by_player = {p['id']: p['carrier_id'] for p in package['players']}; changed = {}
    for cid in (338, 385):
        club = next(c for c in package['clubs'] if c['carrier_id'] == cid)
        order_ids = [carrier_by_player[x] for x in club['roster_player_ids']]
        ent = eq_entries[cid]; decoded = ent.decode_payload(olde)
        if int(compiler.extract_indexed_team_payload_metadata(xor_encode(decoded))['record_mode']) != 0:
            raise ValueError('Reading/Plymouth must retain proven mode0 native roster editing')
        changed[cid] = xor_decode(compiler._rewrite_roster_tail(xor_encode(decoded), order_ids))
    candidate_eq = compiler._rebuild_indexed(olde, eq_index, changed)
    from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
    changed_order_carriers = {x['carrier_id'] for x in plan['startup_order_changes']}
    preserve_other_records(oldj, candidate, changed_order_carriers | {29917})
    preserve_other_records(olde, candidate_eq, {338, 385})
    owners = native_owners(candidate_eq)
    if owners.get(29917) != {1261} or owners.get(33121) != {338} or 33121 in owners.get(385, set()):
        raise ValueError('native owner graph differs from approved transaction')
    counts = {}
    idx = IndexedFDIFile.from_bytes(candidate_eq)
    for cid in (338, 1261, 385):
        ent = next(e for e in idx.entries if e.record_id == cid)
        parsed = compiler.parse_eq_external_team_roster_payload(candidate_eq[ent.payload_offset:ent.payload_offset + ent.payload_length], {})
        if parsed is None: raise ValueError('native roster readback failed')
        counts[cid] = len(parsed.rows)
    if counts != {338: 26, 1261: 23, 385: 24}:
        raise ValueError('native roster post-counts differ')
    post = (digest(candidate), digest(candidate_eq))
    if input_pair not in (pre, post):
        raise ValueError('only complete exact preimage or complete postimage pair accepted')
    return candidate, candidate_eq


def reject_factory_recipe(package):
    if any(a.get('id', '').startswith(PREFIX) for a in package.get('artifacts', [])):
        raise ValueError('Evers/McClune transaction requires source-bound reconstruction')


def reconstruction(previous, release_id):
    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    relative = getattr(previous, 'locator', {}).get('sourced_profile_assignment_plan_path')
    if not relative:
        raise ValueError('Evers SOURCE receipt lacks assignment-plan locator')
    path = (registry.ROOT / relative).resolve()
    if not path.is_relative_to(registry.ROOT.resolve()):
        raise ValueError('Evers SOURCE plan escaped workspace')
    plan = pipeline.read_json_file(path)
    if plan.get('schema') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('Evers SOURCE points to another plan schema/mode')
    base = registry.load_registered_release('2000-01', plan['release_id'])
    verify(base, plan)
    expected_path = (previous.package_path.parent / filename(plan)).resolve()
    if path != expected_path or digest(path.read_bytes()) != receipt.get('original_profile_assignment_plan_sha256'):
        raise ValueError('Evers SOURCE plan path/SHA differs from compiler receipt')
    if pipeline.read_json_file(previous.package_path) != bind(pipeline.read_json_file(base.package_path), plan):
        raise ValueError('Evers SOURCE recipe does not reproduce bound postimage')
    descriptor = previous.package_path.parent / 'role-delta-input.json'
    expected_descriptor = {'season': '2000-01', 'release_id': base.release_id,
        'package_sha256': plan['parent']['package_sha256'],
        'jug_sha256': plan['parent']['jug_sha256'], 'updates': [], 'unresolved': []}
    if pipeline.read_json_file(descriptor) != expected_descriptor:
        raise ValueError('Evers SOURCE inert role descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish('2000-01', descriptor, release_id=release_id,
        source_release_id=base.release_id, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release('2000-01', release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('Evers SOURCE complete recipe replay differs')
    return {'season': '2000-01', 'release_id': release_id,
        'complete_game_inventory_identical': True, 'complete_recipe_identical': True,
        'compilation_mode': MODE}
