"""Private standard-API adapter for the source-backed Rawle -> Forbes change.

This is isolated review code. It exposes the profile-assignment publisher
hooks, but has not been installed in the shared publisher/compiler dispatch.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from scripts import season_duplicate_ownership_delta_v1 as delta
from scripts import season_package_v2 as package_v2
from scripts import season_package_compiler_v2 as compiler
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_soccerbase_original_opening_v1 as soccerbase_original
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from app.fdi_indexed import IndexedFDIFile

MODE = 'known-good-baseline-source-bound-soccerbase-rawle-forbes-v1'
SCHEMA = 'pm99-source-bound-soccerbase-rawle-forbes-v1'
DOB = '1976-10-22'
PLAYER_NAME = 'Scott Forbes'
SOCCERBASE_ID = 'soccerbase:21684'
CARRIER = 33254
CLUB_CARRIER = 390
PARENT_RELEASE_PREFIX = 'sourced-altrincham-macc-opening-20261024-r211'
SOURCE_DIR = Path('.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/crossclub-firsttwo-research-v1/rawle-correction-candidate-v1')
CAPTURE_RECEIPT = SOURCE_DIR / 'replacement-source-capture-receipt.json'
FILENAME_PREFIX = 'rawle-forbes-source-plan-'


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raw_sources(root: Path) -> tuple[dict[str, dict], dict]:
    receipt_path = root / CAPTURE_RECEIPT
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('schema') != 'rawle-replacement-source-capture-v2':
        raise ValueError('unexpected Rawle replacement source capture schema')
    sources = {r['slug']: r for r in receipt.get('sources', [])}
    required = {
        'southend-opener-11v11': 'https://www.11v11.com/matches/southend-united-v-brighton-and-hove-albion-12-august-2000-881/',
        'scott-forbes-11v11-profile': 'https://www.11v11.com/players/scott-forbes-6332/',
        'scott-forbes-canvey-2003': 'https://www.canveyfc.com/2003/squad.htm',
        'scott-forbes-sky-profile': 'https://www.skysports.com/football/player/14997/scott-forbes',
        'southend-opener-soccerbase': 'https://www.soccerbase.com/matches/additional_information.sd?id_game=286673',
        'scott-forbes-soccerbase-profile': 'https://www.soccerbase.com/players/player.sd?player_id=21684',
    }
    if set(required) - set(sources):
        raise ValueError('required raw source captures are missing')
    for slug, url in required.items():
        row = sources[slug]
        if row.get('url') != url or row.get('final_url') != url or row.get('http_status') != 200:
            raise ValueError('raw source URL/status binding differs: ' + slug)
        path = root / row['raw_path']
        if _sha(path) != row['raw_sha256']:
            raise ValueError('raw source body hash changed: ' + slug)
    # Bind the paired wrong-owner chronology source separately. The Forbes
    # match/profile sources do not establish why Rawle is the displaced actor.
    secondary_path = root / SOURCE_DIR.parent / 'web-source-capture-receipt.json'
    secondary = json.loads(secondary_path.read_text())
    rawle_rows = [r for r in secondary.get('sources', []) if r.get('slug') == 'rawle-11v11-profile']
    if len(rawle_rows) != 1 or rawle_rows[0].get('requested_url') != 'https://www.11v11.com/players/mark-rawle-14289/':
        raise ValueError('Rawle chronology source receipt is missing or ambiguous')
    rawle = rawle_rows[0]
    if _sha(root / rawle['raw_path']) != rawle['raw_sha256']:
        raise ValueError('Rawle chronology body hash changed')
    sources['rawle-career-11v11'] = {
        'slug': 'rawle-career-11v11', 'url': rawle['requested_url'], 'final_url': rawle['final_url'],
        'http_status': rawle['http_status'], 'raw_path': rawle['raw_path'],
        'raw_sha256': rawle['raw_sha256'], 'raw_bytes': rawle['raw_bytes'],
        'captured_utc': rawle['captured_utc'], 'secondary_receipt_sha256': _sha(secondary_path),
    }
    return sources, receipt


def _text(root: Path, row: dict) -> tuple[BeautifulSoup, str]:
    page = BeautifulSoup((root / row['raw_path']).read_bytes(), 'lxml')
    text = ' '.join(page.get_text(' ', strip=True).split())
    return page, text


def verify_sources(root: Path, plan: dict | None = None) -> dict:
    sources, receipt = _raw_sources(root)
    match11, match_text = _text(root, sources['southend-opener-11v11'])
    profile11, profile_text = _text(root, sources['scott-forbes-11v11-profile'])
    canvey, canvey_text = _text(root, sources['scott-forbes-canvey-2003'])
    sky, sky_text = _text(root, sources['scott-forbes-sky-profile'])
    match_sb, match_sb_text = _text(root, sources['southend-opener-soccerbase'])
    rawle_page, rawle_text = _text(root, sources['rawle-career-11v11'])
    # True Soccerbase participant identity is the match page's existing provider
    # player link; the candidate's Soccerbase profile is a separate capture.
    sb_capture = sources['scott-forbes-soccerbase-profile']
    sb_profile_url = 'https://www.soccerbase.com/players/player.sd?player_id=21684'
    sb_receipt_path = root / sb_capture['raw_path']
    if not sb_receipt_path.is_file() or sb_capture['url'] != sb_profile_url:
        raise ValueError('captured original Soccerbase Forbes profile is missing or misbound')
    sb_raw = sb_receipt_path.read_bytes()
    sb_sha = hashlib.sha256(sb_raw).hexdigest()
    sb_page = BeautifulSoup(sb_raw, 'lxml')
    sb_text = ' '.join(sb_page.get_text(' ', strip=True).split())
    match_title = match11.title.get_text(' ', strip=True) if match11.title else ''
    profile_title = profile11.title.get_text(' ', strip=True) if profile11.title else ''
    if match_title != 'Southend United v Brighton and Hove Albion, 12 August 2000 - 11v11 match report':
        raise ValueError('11v11 match source title/date changed')
    if not all(v in match_text for v in (
            'Scott Forbes for Scott Houghton 73',
            'Scott Forbes were all making their Shrimpers debut')):
        raise ValueError('11v11 original opening match does not establish the Forbes used-sub identity')
    if profile_title != 'Scott Forbes Football Player Statistics | 11v11.com' or not all(v in profile_text for v in (
            'Scott Forbes', '22 October 1976', 'Nationality English', 'Position Midfielder',
            'Southend United 10 Aug 2000 30 Jun 2002')):
        raise ValueError('11v11 Forbes identity/career facts changed')
    if not all(v in canvey_text for v in (
            'Scott Forbes', 'Born 22nd October 1976', 'left-sided midfielder',
            'Southend United then offered him a contract')):
        raise ValueError('Canvey club bio no longer corroborates the selected DOB/role/career')
    if not all(v in sky_text for v in ('Scott Forbes', '03/12/1976', 'Position: Midfielder')):
        raise ValueError('Sky DOB conflict capture changed; do not silently drop known conflict')
    rawle_title = rawle_page.title.get_text(' ', strip=True) if rawle_page.title else ''
    if (rawle_title != 'Mark Rawle Football Player Statistics | 11v11.com'
            or not all(v in rawle_text for v in (
                'Mark Rawle', '27 April 1979', 'Boston United 01 Feb 1999 23 Feb 2001',
                'Southend United 23 Feb 2001 19 Jun 2003'))):
        raise ValueError('Rawle chronology no longer proves the Southend assignment postdates the 2000 opener')
    # The Soccerbase report binds the exact source-provider ID to the live match
    # row; 11v11 supplies the independently full-name-resolved display identity.
    linked = [a for a in match_sb.select('a[href]')
              if a.get_text(' ', strip=True) == 'S Forbes'
              and parse_qs(urlparse(a['href']).query) == {'player_id': ['21684']}]
    if len(linked) != 1:
        raise ValueError('Soccerbase first-match report no longer binds S Forbes to player_id 21684')
    row_text = ' '.join(linked[0].find_parent('tr').get_text(' ', strip=True).split())
    if not all(v in row_text for v in ('M', '73')):
        raise ValueError('Soccerbase Forbes report no longer proves a midfielder used-sub')
    # Source profile DOB is not available from Soccerbase, so explicitly permit
    # that omission and bind the name/ID only. Do not substitute another ID.
    parsed = soccerbase_original.profile(sb_raw, {
        'provider_player_id': 21684,
        'source_player_id': SOCCERBASE_ID,
    }, sb_profile_url, allow_missing_birth_date=True)
    if (sb_sha != sb_capture['raw_sha256']
            or (parsed['name'], parsed['birth_date'], parsed['source_player_id']) != (PLAYER_NAME, None, SOCCERBASE_ID)):
        raise ValueError('Soccerbase original profile identity does not match the selected candidate')
    if 'Southend' not in sb_text or '01 Jun, 00' not in sb_text or '01 Jul, 02' not in sb_text:
        raise ValueError('Soccerbase profile no longer dates Forbes at Southend')
    return {
        'mode': MODE,
        'source_receipt_sha256': _sha(root / CAPTURE_RECEIPT),
        'sources': {k: {'path': v['raw_path'], 'url': v['url'], 'sha256': v['raw_sha256']} for k, v in sources.items() if k in {
            'southend-opener-11v11', 'scott-forbes-11v11-profile', 'scott-forbes-canvey-2003',
            'scott-forbes-sky-profile', 'southend-opener-soccerbase', 'rawle-career-11v11'}},
        'rawle_chronology_receipt_sha256': sources['rawle-career-11v11']['secondary_receipt_sha256'],
        'soccerbase_profile': {'url': sb_profile_url, 'path': str(sb_receipt_path.relative_to(root)), 'sha256': sb_sha,
            'source_player_id': SOCCERBASE_ID, 'name': parsed['name'], 'dob_on_soccerbase_profile': None,
            'southend_period_text_confirmed': True},
        'match_identity': {'fixture_date': '2000-08-12', 'club': 'Southend United',
            'full_name': PLAYER_NAME, 'provider_player_id': 21684, 'source_position': 'M',
            'used_sub_minute': 73, 'replaced': 'Scott Houghton'},
        'dob_policy': {'chosen': DOB, 'supports': ['11v11 profile', 'dated Canvey FC squad biography'],
            'conflict': {'source': 'Sky Sports', 'published': '1976-12-03'},
            'selected_despite_conflict_by_root_policy': True},
        'secondary_facts': {'height_cm': None, 'weight_kg': None,
            'shirt_number': 'unavailable', 'photo': 'not sourced; native-no-photo'},
        'role_policy': {'broad': 'M', 'fine_role': 10,
            'basis': 'source describes a left-sided midfielder; code 10 is editorial-compatible, not exact edition assignment'},
    }


def _parent(base, plan: dict | None = None) -> tuple[dict, Path, Path]:
    if base.season != '2000-01' or not base.release_id.startswith(PARENT_RELEASE_PREFIX):
        raise ValueError('Rawle/Forbes adapter requires a registered 2000-01 Altrincham/Macc parent')
    registered = registry.load_registered_release(base.season, base.release_id)
    if (registered.package_path != base.package_path or registered.game_path != base.game_path
            or registered.release_manifest_path != base.release_manifest_path
            or registered.manifest_sha256 != base.manifest_sha256):
        raise ValueError('Rawle/Forbes parent object differs from the registered release')
    package_path = base.package_path
    package_bytes = package_path.read_bytes()
    package = json.loads(package_bytes)
    game_dir = base.game_path
    if package.get('season', {}).get('label') != '2000/01':
        raise ValueError('parent package is not 2000-01')
    manifest_path = base.release_manifest_path
    manifest_sha = _sha(manifest_path)
    if manifest_sha != base.manifest_sha256:
        raise ValueError('registered parent manifest pin is stale')
    if plan is not None:
        parent = plan['parent']
        if (parent['release_id'] != base.release_id or parent['manifest_sha256'] != manifest_sha
                or parent['package_sha256'] != hashlib.sha256(package_bytes).hexdigest()
                or parent['eq_sha256'] != _sha(game_dir / 'DBDAT/EQ98030.FDI')
                or parent['jug_sha256'] != _sha(game_dir / 'DBDAT/JUG98030.FDI')
                or parent['native_files'].get('MINIFOTO.PKF') != _sha(game_dir / 'DBDAT/MINIFOTO.PKF')):
            raise ValueError('Rawle/Forbes plan is stale against its exact registered parent pins')
    return package, package_path, game_dir


def _parent_native(base, plan: dict | None = None) -> dict:
    """Check the semantic native preimage and pin only relevant parent files."""
    game = base.game_path
    paths = {name: game / 'DBDAT' / name for name in
             ('JUG98030.FDI', 'EQ98030.FDI', 'MINIFOTO.PKF')}
    hashes = {name: _sha(path) for name, path in paths.items()}
    jug = paths['JUG98030.FDI'].read_bytes()
    eq = paths['EQ98030.FDI'].read_bytes()
    entries = {entry.record_id: entry for entry in IndexedFDIFile.from_bytes(jug).entries}
    if CARRIER not in entries:
        raise ValueError('Rawle native carrier is missing')
    payload = entries[CARRIER].decode_payload(jug)
    actual = roster.native_player(payload, CARRIER)
    end = actual['name_end']
    birth_date = {'day': payload[end + 12] ^ 0x61,
                  'month': payload[end + 13] ^ 0x61,
                  'year': int.from_bytes(bytes(x ^ 0x61 for x in payload[end + 14:end + 16]), 'little')}
    from scripts import season_opening_order_repair_v1 as ownership
    if (actual.get('name') != 'Mark RAWLE' or actual.get('position') != 'M'
            or actual.get('roles', [None])[0] != 9
            or birth_date != {'day': 27, 'month': 4, 'year': 1979}
            or ownership.native_owners(eq).get(CARRIER) != {CLUB_CARRIER}):
        raise ValueError('native preimage is not the exact Southend-owned Mark Rawle carrier')
    loose_photo = game / 'DBDAT/MINIFOTO' / f'J96{CARRIER:05d}.BMP'
    if loose_photo.exists() or loose_photo.is_symlink():
        raise ValueError('displaced Rawle loose portrait is present; publication must remove it explicitly')
    if plan is not None and (plan['parent'].get('native_files') != hashes
            or plan['parent'].get('target_native_preimage') != {
                'carrier_id': CARRIER, 'name': actual['name'], 'position': actual['position'],
                'fine_roles': actual['roles'], 'birth_date': birth_date,
                'active_owner_carriers': [CLUB_CARRIER], 'loose_portrait_absent': True}):
        raise ValueError('Rawle native preimage or relevant native file pins changed')
    return {'native_files': hashes,
        'target_native_preimage': {'carrier_id': CARRIER, 'name': actual['name'],
            'position': actual['position'], 'fine_roles': actual['roles'],
            'birth_date': birth_date, 'active_owner_carriers': [CLUB_CARRIER],
            'loose_portrait_absent': True}}


def _before_rows(package: dict) -> tuple[dict, dict, dict]:
    southend = [c for c in package['clubs'] if c.get('carrier_id') == CLUB_CARRIER]
    boston = [c for c in package['clubs'] if c.get('carrier_id') == 3314]
    if len(southend) != 1 or len(boston) != 1:
        raise ValueError('Southend/Boston source club carriers are not unique')
    by_id = {p['id']: p for p in package['players']}
    rawle = by_id.get('english-player-33254')
    if (rawle is None or rawle['carrier_id'] != CARRIER or rawle['name'] != 'Mark Rawle'
            or rawle['source_name'] != 'Mark Rawle' or rawle['facts'].get('birth_date') != '1979-04-27'
            or rawle['club_id'] != southend[0]['id'] or southend[0]['roster_player_ids'].count(rawle['id']) != 1):
        raise ValueError('wrong Rawle carrier is not the exact Southend slot expected')
    boston_rawle = [p for p in package['players'] if p.get('carrier_id') == 11027]
    if (len(boston_rawle) != 1 or boston_rawle[0]['name'] != 'Mark Rawle'
            or boston_rawle[0]['facts'].get('birth_date') != '1979-04-27'
            or boston_rawle[0]['club_id'] != boston[0]['id']
            or boston[0]['roster_player_ids'].count(boston_rawle[0]['id']) != 1):
        raise ValueError('Boston Rawle preservation target changed')
    if len(southend[0]['roster_player_ids']) != 25:
        raise ValueError('Southend roster capacity/preimage differs from expected 25 rows')
    if any((p.get('name') or '').casefold() == 'scott forbes'
           or (p.get('source_name') or '').casefold() == 'scott forbes' for p in package['players']):
        raise ValueError('Scott Forbes already exists in the package; do not overwrite/duplicate')
    return rawle, southend[0], boston_rawle[0]


def prepare(base) -> dict:
    root = registry.ROOT
    evidence = verify_sources(root)
    package, package_path, game_dir = _parent(base)
    native = _parent_native(base)
    before, southend, boston = _before_rows(package)
    match = evidence['sources']['southend-opener-soccerbase']
    report_path = root / match['path']
    sb_profile = root / evidence['soccerbase_profile']['path']
    plan_row = {
        'layer': 'main', 'player_id': before['id'], 'carrier_id': CARRIER,
        'club_id': southend['id'], 'club': southend['name'], 'before': copy.deepcopy(before),
        'wrong_owner_evidence': {'basis': 'dated Rawle transfer: Boston through 2001-02-23; Southend starts 2001-02-23',
            'raw_sources': [{'path': evidence['sources']['rawle-career-11v11']['path'],
                             'sha256': evidence['sources']['rawle-career-11v11']['sha256']}],
            'preserved_boston_player_id': boston['id'], 'preserved_boston_carrier_id': 11027},
        'replacement': {
            'source_player': {'name': PLAYER_NAME, 'birth_date': DOB, 'position': 'M', 'nationality': 'ENG',
                'height_cm': None, 'weight_kg': None},
            'source_person': {'source_provider': 'soccerbase', 'source_player_id': SOCCERBASE_ID,
                'provider_player_id': 21684, 'name': PLAYER_NAME, 'birth_date': DOB,
                'source_profile_url': evidence['soccerbase_profile']['url'],
                'identity_policy': 'Soccerbase-ID-with-cross-source-full-name-and-disclosed-DOB-disagreement-v1',
                'dob_evidence': evidence['dob_policy']},
            'raw_evidence': {'local_path': str(sb_profile.relative_to(root)),
                'source_sha256': evidence['soccerbase_profile']['sha256'],
                'url': evidence['soccerbase_profile']['url'], 'provider_player_id': 21684,
                'dob_is_published_on_this_page': False},
            'opening_eligibility': {'method': 'positive-first-fixture-substitute-id',
                'date': '2000-08-12', 'source_club_id': 'soccerbase:2393'},
            'source_identity_capture': evidence['sources']['scott-forbes-11v11-profile'],
            'career_identity_capture': evidence['sources']['scott-forbes-canvey-2003'],
            'source_position_basis': 'Soccerbase match report has S Forbes (M) and 73-minute entry; 11v11 full-name match report confirms Scott Forbes.',
            'portrait_policy': 'no-photo; disallow displaced Mark Rawle image',
        },
        'replacement_opening_evidence': {
            'source_club_id': 'soccerbase:2393', 'date': '2000-08-12',
            'source_match_id': 'soccerbase:286673', 'source_url': match['url'],
            'starting_xi': [], 'substitutes': [SOCCERBASE_ID],
            'raw_sources': [{'path': match['path'], 'sha256': match['sha256']},
                {'path': evidence['sources']['southend-opener-11v11']['path'],
                 'sha256': evidence['sources']['southend-opener-11v11']['sha256']}],
            'full_name_resolution': '11v11 exact name and matchday appearance cross-checked against Soccerbase player_id 21684',
        },
        'owner_evidence': {'raw_sources': [{'path': evidence['sources']['rawle-career-11v11']['path'],
                                             'sha256': evidence['sources']['rawle-career-11v11']['sha256']}],
            'claim': 'The Rawle timeline places this actor at Boston on the 2000-08-12 opening date, before his 2001-02-23 Southend move.'},
        'replacement_role_projection': {'broad_position': 'M', 'fine_roles': [10],
            'policy': 'editorial-compatible-left-midfielder-projection-v1',
            'not_claimed': 'Exact FIFA edition role or source-authored fine-role code.'},
        'preserve_roster_order': True,
    }
    plan = {
        'schema_version': SCHEMA, 'mode': MODE, 'season': '2000-01', 'release_id': base.release_id,
        'parent': {'release_id': base.release_id, 'manifest_path': str(base.release_manifest_path.relative_to(root)),
            'manifest_sha256': base.manifest_sha256, 'package_path': str(package_path.relative_to(root)),
            'package_sha256': _sha(package_path), 'native_files': native['native_files'],
            'target_native_preimage': native['target_native_preimage'],
            'eq_sha256': _sha(game_dir / 'DBDAT/EQ98030.FDI'),
            'jug_sha256': _sha(game_dir / 'DBDAT/JUG98030.FDI')},
        'package_sha256': _sha(package_path), 'jug_sha256': _sha(game_dir / 'DBDAT/JUG98030.FDI'),
        'source_title': 'Original Soccerbase 12 Aug 2000 used-sub identity plus independently corroborated Scott Forbes biography',
        'proof_covers': ['dated-wrong-opening-owner-removal', 'positive-first-fixture-used-sub',
            'full-name-Soccerbase-player-ID-binding', 'DOB-cross-source-conflict-disclosed',
            'native-no-photo', 'deterministic-editorial-ratings'],
        'bindings': {'snapshot': {'project_url': match['url']},
            'source_capture_receipt': {'path': str(CAPTURE_RECEIPT), 'sha256': _sha(root / CAPTURE_RECEIPT)},
            'raw_sources': [{'path': v['path'], 'sha256': v['sha256'], 'url': v['url']}
                for k,v in evidence['sources'].items()],
            'soccerbase_profile': evidence['soccerbase_profile']},
        'source_verification': evidence,
        'updates': [plan_row],
        'summary': {'target_carrier_id': CARRIER, 'target_club_carrier_id': CLUB_CARRIER,
            'target_roster_rows_before_after': [25, 25], 'preserve_boston_carrier_id': 11027},
        'historical_verification_complete': False,
        'registered': False, 'build_authorized': False, 'publication_authorized': False,
    }
    verify(base, plan)
    return plan


def verify(base, plan: dict) -> dict:
    root = registry.ROOT
    if plan.get('schema_version') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('unsupported Rawle/Forbes standard plan')
    evidence = verify_sources(root)
    if evidence != plan.get('source_verification'):
        raise ValueError('source verification facts differ from immutable plan')
    package, package_path, game_dir = _parent(base, plan)
    native = _parent_native(base, plan)
    before, southend, boston = _before_rows(package)
    row = plan['updates'][0] if len(plan.get('updates', [])) == 1 else None
    sb_profile = evidence['soccerbase_profile']
    expected_person = {'source_provider':'soccerbase', 'source_player_id':SOCCERBASE_ID,
        'provider_player_id':21684, 'name':PLAYER_NAME, 'birth_date':DOB,
        'source_profile_url':sb_profile['url'],
        'identity_policy':'Soccerbase-ID-with-cross-source-full-name-and-disclosed-DOB-disagreement-v1',
        'dob_evidence':evidence['dob_policy']}
    expected_opening = {'source_club_id':'soccerbase:2393', 'date':'2000-08-12',
        'source_match_id':'soccerbase:286673',
        'source_url':evidence['sources']['southend-opener-soccerbase']['url'],
        'starting_xi':[], 'substitutes':[SOCCERBASE_ID],
        'raw_sources':[{'path':evidence['sources']['southend-opener-soccerbase']['path'],
                        'sha256':evidence['sources']['southend-opener-soccerbase']['sha256']},
                       {'path':evidence['sources']['southend-opener-11v11']['path'],
                        'sha256':evidence['sources']['southend-opener-11v11']['sha256']}],
        'full_name_resolution':'11v11 exact name and matchday appearance cross-checked against Soccerbase player_id 21684'}
    expected_owner_sources = [{'path':evidence['sources']['rawle-career-11v11']['path'],
                               'sha256':evidence['sources']['rawle-career-11v11']['sha256']}]
    expected_source_bindings = [{'path':v['path'],'sha256':v['sha256'],'url':v['url']}
        for v in evidence['sources'].values()]
    expected_evidence_path = str((root / sb_profile['path']).relative_to(root))
    expected_raw_evidence = {'local_path':expected_evidence_path,'source_sha256':sb_profile['sha256'],
        'url':sb_profile['url'],'provider_player_id':21684,'dob_is_published_on_this_page':False}
    if (row is None or row.get('before') != before or row.get('carrier_id') != CARRIER
            or row.get('layer') != 'main' or row.get('player_id') != before['id']
            or row.get('club_id') != southend['id'] or row['replacement']['source_person']['source_player_id'] != SOCCERBASE_ID
            or row['replacement']['source_player'] != {'name':PLAYER_NAME,'birth_date':DOB,'position':'M','nationality':'ENG','height_cm':None,'weight_kg':None}
            or row['replacement']['source_person'] != expected_person
            or row['replacement']['raw_evidence'] != expected_raw_evidence
            or row['replacement']['opening_eligibility'] != {'method':'positive-first-fixture-substitute-id','date':'2000-08-12','source_club_id':'soccerbase:2393'}
            or row['replacement_opening_evidence'] != expected_opening
            or row['replacement_role_projection'] != {'broad_position':'M','fine_roles':[10],
                'policy':'editorial-compatible-left-midfielder-projection-v1',
                'not_claimed':'Exact FIFA edition role or source-authored fine-role code.'}
            or row['wrong_owner_evidence'] != {'basis':'dated Rawle transfer: Boston through 2001-02-23; Southend starts 2001-02-23',
                'raw_sources':expected_owner_sources,'preserved_boston_player_id':boston['id'],
                'preserved_boston_carrier_id':11027}
            or row['owner_evidence'] != {'raw_sources':expected_owner_sources,
                'claim':'The Rawle timeline places this actor at Boston on the 2000-08-12 opening date, before his 2001-02-23 Southend move.'}
            or row['preserve_roster_order'] is not True
            or row['replacement']['source_identity_capture'] != evidence['sources']['scott-forbes-11v11-profile']
            or row['replacement']['career_identity_capture'] != evidence['sources']['scott-forbes-canvey-2003']):
        raise ValueError('private plan changes identity, source, parent, role, or opening match facts')
    if (row['replacement'].get('source_position_basis') != 'Soccerbase match report has S Forbes (M) and 73-minute entry; 11v11 full-name match report confirms Scott Forbes.'
            or row['replacement'].get('portrait_policy') != 'no-photo; disallow displaced Mark Rawle image'
            or row.get('club') != southend['name']
            or plan.get('season') != '2000-01' or plan.get('release_id') != base.release_id
            or plan.get('package_sha256') != plan['parent']['package_sha256']
            or plan.get('jug_sha256') != plan['parent']['jug_sha256']):
        raise ValueError('private plan role/source summary or release binding changed')
    if plan['bindings']['source_capture_receipt'] != {'path':str(CAPTURE_RECEIPT),'sha256':_sha(root / CAPTURE_RECEIPT)}:
        raise ValueError('source capture receipt binding changed')
    if (plan['bindings'].get('raw_sources') != expected_source_bindings
            or plan['bindings'].get('soccerbase_profile') != sb_profile
            or plan['bindings'].get('snapshot') != {'project_url':evidence['sources']['southend-opener-soccerbase']['url']}
            or plan.get('summary') != {'target_carrier_id':CARRIER,'target_club_carrier_id':CLUB_CARRIER,
                'target_roster_rows_before_after':[25,25],'preserve_boston_carrier_id':11027}
            or plan.get('source_title') != 'Original Soccerbase 12 Aug 2000 used-sub identity plus independently corroborated Scott Forbes biography'
            or plan.get('proof_covers') != ['dated-wrong-opening-owner-removal','positive-first-fixture-used-sub',
                'full-name-Soccerbase-player-ID-binding','DOB-cross-source-conflict-disclosed',
                'native-no-photo','deterministic-editorial-ratings']
            or plan.get('historical_verification_complete') is not False
            or plan.get('registered') is not False or plan.get('build_authorized') is not False
            or plan.get('publication_authorized') is not False):
        raise ValueError('private plan source/parent bindings or authorization flags changed')
    if plan['parent'].get('manifest_path') != str(base.release_manifest_path.relative_to(root)):
        raise ValueError('Rawle plan manifest locator changed')
    return {'verified':True, 'parent_manifest_sha256':base.manifest_sha256,
        'parent_package_sha256':_sha(package_path), 'parent_native_files':native['native_files'],
        'parent_eq_sha256':_sha(game_dir / 'DBDAT/EQ98030.FDI'),
        'parent_jug_sha256':_sha(game_dir / 'DBDAT/JUG98030.FDI'),
        'boston_player_id_preserved':boston['id'], 'source_verification':evidence}


def bind(package: dict, plan: dict) -> dict:
    base = registry.load_registered_release(plan.get('season'), plan.get('release_id'))
    verify(base, plan)
    parent, _, _ = _parent(base, plan)
    incoming = package_v2.canonical_json_bytes(package)
    if incoming != package_v2.canonical_json_bytes(parent):
        # Postimage acceptance is checked only after the exact bound document
        # has been independently reconstructed below.
        pass
    package = parent
    result = delta.updated_package(parent, plan)
    target = next(p for p in result['players'] if p['id'] == plan['updates'][0]['player_id'])
    # Generic duplicate delta defaults to central mid. We use its existing
    # package/rating/profile/native writer, then apply this source-bounded
    # editorially compatible left-midfielder role only to the selected actor.
    target['facts']['fine_roles'] = [10]
    package_v2.validate_package(result, strict=False)
    # Exact order/ownership is source invariant; no new player/club row added.
    old_club = next(c for c in package['clubs'] if c['carrier_id'] == CLUB_CARRIER)
    new_club = next(c for c in result['clubs'] if c['carrier_id'] == CLUB_CARRIER)
    if len(new_club['roster_player_ids']) != 25 or new_club['roster_player_ids'] != old_club['roster_player_ids']:
        raise ValueError('replacement changed Southend native roster membership/order/capacity')
    if result['clubs'] != package['clubs'] or result['managers'] != package['managers']:
        raise ValueError('replacement changed a club or manager declaration')
    if result['calendar'] != package['calendar'] or result['migration'] != package['migration']:
        raise ValueError('replacement changed calendar/migration metadata')
    for key in package:
        if key not in {'players', 'assets', 'artifacts', 'sources', 'proofs'} and result.get(key) != package[key]:
            raise ValueError('replacement changed unrelated package section: ' + key)
    old_artifacts = {a['id']:a for a in package['artifacts']}
    new_artifacts = {a['id']:a for a in result['artifacts']}
    if (len(new_artifacts) != len(old_artifacts)+1
            or any(new_artifacts.get(k) != v for k,v in old_artifacts.items())):
        raise ValueError('replacement changed unrelated source artifacts')
    for key, values in package['assets'].items():
        if key == 'portraits':
            old_other = [v for v in values if v.get('player_id') != target['id']]
            new_other = [v for v in result['assets'][key] if v.get('player_id') != target['id']]
            target_portraits = [v for v in result['assets'][key] if v.get('player_id') == target['id']]
            if old_other != new_other or len(target_portraits) != 1 or target_portraits[0].get('status') != 'native-no-photo':
                raise ValueError('replacement changed unrelated assets or did not remove the displaced portrait')
        elif result['assets'].get(key) != values:
            raise ValueError('replacement changed a non-target asset category')
    for key in ('sources', 'proofs'):
        old_rows = package[key]
        new_rows = result[key]
        if new_rows[:-1] == old_rows:
            continue
        old_by_id = {r['id']:r for r in old_rows}
        new_by_id = {r['id']:r for r in new_rows}
        if any(new_by_id.get(k) != v for k,v in old_by_id.items()) or len(new_rows) != len(old_rows)+1:
            raise ValueError('replacement changed unrelated ' + key)
    # Make the full proof plan a separately named, content-addressed artifact.
    plan_digest = hashlib.sha256(package_v2.canonical_json_bytes(plan)).hexdigest()
    artifact_id = 'duplicate-ownership-plan-2000-01-' + plan_digest[:12]
    artifact = next(a for a in result['artifacts'] if a['id'] == artifact_id)
    artifact['relative_path'] = filename(plan)
    if artifact['sha256'] != hashlib.sha256(package_v2.canonical_json_bytes(plan)).hexdigest():
        raise ValueError('duplicate ownership plan artifact hash is not canonical')
    if incoming not in (package_v2.canonical_json_bytes(parent),
                        package_v2.canonical_json_bytes(result)):
        raise ValueError('Rawle bind accepts only its exact complete package preimage/postimage')
    return result


def apply(jug: bytes, eq: bytes, plan: dict) -> tuple[bytes, bytes]:
    base = registry.load_registered_release(plan.get('season'), plan.get('release_id'))
    verify(base, plan)
    package, _, game_dir = _parent(base, plan)
    before_jug = (game_dir / 'DBDAT/JUG98030.FDI').read_bytes()
    before_eq = (game_dir / 'DBDAT/EQ98030.FDI').read_bytes()
    bound_package = bind(package, plan)
    country_codes = compiler._extract_country_codes_from_textos(game_dir / 'DBDAT/TEXTOS.PKF')
    player_id = plan['updates'][0]['player_id']
    after_jug = delta.compile_planned_players(before_jug, bound_package, {player_id}, country_codes, plan)
    if after_jug == before_jug:
        raise ValueError('native candidate postimage did not change')
    index0, index1 = IndexedFDIFile.from_bytes(before_jug), IndexedFDIFile.from_bytes(after_jug)
    old_entries = {e.record_id:e for e in index0.entries}; new_entries={e.record_id:e for e in index1.entries}
    if old_entries.keys() != new_entries.keys():
        raise ValueError('native player carrier set changed')
    changed = [carrier for carrier, e in old_entries.items()
               if e.decode_payload(before_jug) != new_entries[carrier].decode_payload(after_jug)]
    if changed != [CARRIER]:
        raise ValueError(f'native byte postimage touched unexpected player carriers: {changed[:20]}')
    old_entry, new_entry = old_entries[CARRIER], new_entries[CARRIER]
    if (index0.record_count != index1.record_count or index0.reserved_a != index1.reserved_a
            or index0.reserved_b != index1.reserved_b or index0.index_end_offset != index1.index_end_offset
            or [(e.record_id,e.key,e.index_offset) for e in index0.entries]
            != [(e.record_id,e.key,e.index_offset) for e in index1.entries]):
        raise ValueError('native postimage changed JUG directory identity/order')
    allowed_directory_bytes = set()
    for old_item, new_item in zip(index0.entries,index1.entries):
        key_len = before_jug[old_item.index_offset+4]
        if after_jug[new_item.index_offset+4] != key_len:
            raise ValueError('native postimage changed an indexed JUG key length')
        field = old_item.index_offset+5+key_len
        allowed_directory_bytes.update(range(field,field+8))
        if before_jug[old_item.index_offset:field] != after_jug[new_item.index_offset:field]:
            raise ValueError('native postimage changed a JUG record ID/key')
    directory_end = index0.entries[0].payload_offset
    if (index1.entries[0].payload_offset != directory_end
            or any(before_jug[i] != after_jug[i] for i in range(directory_end)
                   if i not in allowed_directory_bytes)):
        raise ValueError('native postimage changed JUG directory bytes outside offset/length fields')
    def gaps(data, index):
        ordered = sorted(index.entries,key=lambda e:e.payload_offset)
        result=[]
        for left,right in zip(ordered,ordered[1:]):
            result.append(data[left.payload_offset+left.payload_length:right.payload_offset])
        last=ordered[-1]
        result.append(data[last.payload_offset+last.payload_length:])
        return result
    if gaps(before_jug,index0) != gaps(after_jug,index1):
        raise ValueError('native postimage changed opaque JUG inter-record/trailing bytes')
    if _sha(base.package_path) != plan['parent']['package_sha256']:
        raise ValueError('in-memory compile changed the parent recipe file on disk')
    if _sha(game_dir / 'DBDAT/JUG98030.FDI') != plan['parent']['jug_sha256']:
        raise ValueError('in-memory compile changed the parent JUG file on disk')
    if _sha(game_dir / 'DBDAT/EQ98030.FDI') != plan['parent']['eq_sha256']:
        raise ValueError('in-memory compile changed the parent EQ file on disk')
    eq_after = before_eq
    if eq_after != before_eq:
        raise ValueError('in-memory actor replacement unexpectedly changed EQ roster')
    target = next(p for p in bound_package['players'] if p['id'] == player_id)
    payload = new_entries[CARRIER].decode_payload(after_jug)
    actual = roster.native_player(payload, CARRIER)
    end = actual['name_end']
    dob = {'day':payload[end+12]^0x61,'month':payload[end+13]^0x61,
        'year':int.from_bytes(bytes(x^0x61 for x in payload[end+14:end+16]),'little')}
    if (actual['name'].casefold() != PLAYER_NAME.casefold() or actual['position'] != 'M' or actual['roles'][0] != 10
            or dob != {'day':22,'month':10,'year':1976}):
        raise ValueError('in-memory native postimage readback differs from admitted actor: '
            + repr({'name':actual.get('name'),'position':actual.get('position'),
                    'roles':actual.get('roles'),'dob':dob}))
    # Check unchanged Boston actor plus all other records are exact in native and recipe.
    before_package = package
    before_players = {p['id']:p for p in before_package['players']}
    after_players = {p['id']:p for p in bound_package['players']}
    for pid, p in before_players.items():
        if pid != player_id and after_players.get(pid) != p:
            raise ValueError('in-memory package changed an unrelated actor: '+pid)
    boston = next(p for p in bound_package['players'] if p.get('carrier_id') == 11027)
    old_boston = next(p for p in before_package['players'] if p.get('carrier_id') == 11027)
    if boston != old_boston:
        raise ValueError('Boston Rawle changed in candidate package')
    report = {'postimage_sha256':hashlib.sha256(after_jug).hexdigest(),
        'postimage_bytes':len(after_jug),'changed_native_carriers':changed,
        'selected_record_payload_offset':old_entry.payload_offset,
        'selected_record_payload_length':old_entry.payload_length,
        'selected_record_postimage_payload_offset':new_entry.payload_offset,
        'selected_record_postimage_payload_length':new_entry.payload_length,
        'directory_offset_length_fields_rebuilt':True,
        'non_target_payloads_and_opaque_gaps_unchanged':True,
        'target_native_readback':{'carrier_id':CARRIER,'name':actual['name'],'position':actual['position'],
            'fine_roles':actual['roles'],'dob':dob},
        'eq_sha256_unchanged':hashlib.sha256(before_eq).hexdigest(),
        'jug_preimage_sha256':hashlib.sha256(before_jug).hexdigest(),
        'boston_rawle_preserved':True,'unrelated_recipe_players_preserved':True,
        'one_selected_actor_changed':True,'postimage_bytes_retained_only_in_memory':True}
    if (jug, eq) not in ((before_jug, before_eq), (after_jug, before_eq)):
        raise ValueError('paired JUG/EQ apply accepts only the exact full preimage or postimage')
    report['paired_preimage_or_postimage_only'] = True
    return after_jug, before_eq


def filename(plan: dict) -> str:
    if plan.get('schema_version') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('unsupported Rawle/Forbes plan filename request')
    digest = hashlib.sha256(package_v2.canonical_json_bytes(plan)).hexdigest()
    return FILENAME_PREFIX + digest[:12] + '.json'


def source_artifact(plan: dict) -> dict:
    """Return the exact typed source plan written by the standard publisher."""
    base = registry.load_registered_release(plan.get('season'), plan.get('release_id'))
    verify(base, plan)
    document = copy.deepcopy(plan)
    digest = hashlib.sha256(package_v2.canonical_json_bytes(document)).hexdigest()
    if digest != hashlib.sha256(package_v2.canonical_json_bytes(plan)).hexdigest():
        raise ValueError('Rawle source artifact changed after plan verification')
    return {'filename': filename(plan), 'document': document, 'sha256': digest}


def selected_carriers(plan: dict) -> set[int]:
    if plan.get('schema_version') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('unsupported Rawle/Forbes portrait selection plan')
    return {CARRIER}


def apply_minifoto(archive: bytes, plan: dict) -> bytes:
    base = registry.load_registered_release(plan.get('season'), plan.get('release_id'))
    verify(base, plan)
    original = (base.game_path / 'DBDAT/MINIFOTO.PKF').read_bytes()
    if archive != original:
        raise ValueError('MINIFOTO apply accepts only the exact pinned parent archive')
    result, offsets = delta.no_photo_archive(original, selected_carriers(plan))
    if offsets != {CARRIER: []} or result != original:
        # This parent is recorded as a no-photo input, so a non-empty hit means
        # the source wrong-owner photo must be deliberately cleared/re-reviewed.
        raise ValueError('pinned parent unexpectedly contains a Rawle portrait; clear and rebind explicitly')
    loose = base.game_path / 'DBDAT/MINIFOTO' / f'J96{CARRIER:05d}.BMP'
    if loose.exists() or loose.is_symlink():
        raise ValueError('pinned parent contains the displaced identity loose portrait')
    return result


def reject_factory_recipe(package: dict) -> None:
    if any(a.get('relative_path', '').startswith(FILENAME_PREFIX)
           for a in package.get('artifacts', [])):
        raise ValueError('Rawle/Forbes recipe requires its typed source reconstruction')


def reconstruction(previous, release_id):
    """Replay only a child whose own compiler receipt names this exact MODE."""
    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    receipt = pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    # Test the child's receipt mode before consulting any inherited locator.
    locator = previous.locator or {}
    relative = locator.get('sourced_profile_assignment_plan_path')
    if not relative:
        raise ValueError('Rawle/Forbes SOURCE lacks its typed assignment plan locator')
    path = (registry.ROOT / relative).resolve()
    plan = pipeline.read_json_file(path)
    if plan.get('schema_version') != SCHEMA or plan.get('mode') != MODE:
        raise ValueError('Rawle/Forbes SOURCE locator points to another plan schema/mode')
    if (path != (previous.package_path.parent / filename(plan)).resolve()
            or registry.sha256_file(path) != receipt.get('original_profile_assignment_plan_sha256')):
        raise ValueError('Rawle/Forbes compiler receipt does not bind the exact saved plan')
    artifact = source_artifact(plan)
    artifact_path = previous.package_path.parent / artifact['filename']
    if registry.sha256_file(artifact_path) != artifact['sha256']:
        raise ValueError('Rawle/Forbes retained source artifact hash differs')
    base = registry.load_registered_release(plan['season'], plan['parent']['release_id'])
    verify(base, plan)
    expected_package = bind(pipeline.read_json_file(base.package_path), plan)
    if pipeline.read_json_file(previous.package_path) != expected_package:
        raise ValueError('Rawle/Forbes SOURCE recipe differs from its exact typed postimage')
    descriptor_path = previous.package_path.parent / 'role-delta-input.json'
    descriptor = pipeline.read_json_file(descriptor_path)
    wanted = {'season': plan['season'], 'release_id': base.release_id,
        'package_sha256': plan['parent']['package_sha256'],
        'jug_sha256': plan['parent']['native_files']['JUG98030.FDI'],
        'updates': [], 'unresolved': []}
    if descriptor != wanted:
        raise ValueError('Rawle/Forbes replay descriptor is not the exact inert parent pin')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, descriptor_path, release_id=release_id,
        source_release_id=base.release_id, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,
        pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != expected_package:
        raise ValueError('Rawle/Forbes complete SOURCE replay changed its exact recipe')
    return {'season': previous.season, 'release_id': release_id,
        'complete_game_inventory_identical': True, 'complete_recipe_identical': True,
        'compilation_mode': MODE}
