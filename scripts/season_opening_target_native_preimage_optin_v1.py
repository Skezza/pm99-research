"""Case-scoped target-preimage opt-in for r199 carrier 19 only.

This module adds no native writer. It
validates the one old native actor being wholly replaced by a source-admitted
new person when its package deliberately retains mode-1 fallback facts and
its baseline rating vector is not the native record's decoded skill vector.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry
from scripts.season_opening_identity_exchange_v1 import match_people
from scripts import season_complete_mode1_opening_v1 as complete
from scripts.season_historical_roster_audit_v1 import normalise
from scripts.season_within_club_reserve_repair_v1 import native_facts as read_native_facts

POLICY = 'exact-r199-amavisca-native-preimage-replaced-by-source-admitted-ruben-v1'
RELEASE_ID = 'sourced-espanyol-retirement-order-20261023-r199a'
SEASON = '2005-06'
CARRIER = 19
OWNER = 4
OLD_NAME = 'José Emilio AMAVISCA Gárate'
OLD_DOB = '1971-06-19'
NEW_PROVIDER_ID = 35522
NEW_NAME = 'Rubén de la Red'
NEW_DOB = '1985-06-05'
ELPAIS_PATH = '.local/consolidated-audit-20261009/parallel-rc-20261023/celtic/crossclub-2005-first5/amavisca/originals/elpais-no-more-playing.html'
ELPAIS_SHA = '5381d792e1281223c867b1e4dfa2722053cc16bebdd93cb5ddaed62953c4fe7f'
ELPAIS_URL = 'https://elpais.com/diario/2005/08/06/deportes/1123279206_850215.html?outputType=amp'
ELPAIS_RECEIPT_PATH = ELPAIS_PATH.removesuffix('.html') + '.source.json'
ELPAIS_RECEIPT_SHA = 'bd3a9d7aa2bd70ba1e78e60e9836dddd73e20b94949cca4c679639fa5b544ae5'
EXPECTED_NATIVE_SKILLS = {
    'speed': 87, 'stamina': 86, 'aggression': 81, 'quality': 82, 'heading': 67,
    'dribbling': 77, 'passing': 76, 'shooting': 72, 'tackling': 53, 'handling': 11,
}
EXPECTED_PACKAGE_RATINGS = {
    'aggression': 82, 'dribbling': 53, 'handling': 11, 'heading': 76,
    'passing': 67, 'quality': 87, 'shooting': 72, 'speed': 86, 'stamina': 81,
    'tackling': 77,
}
EXPECTED_RAW_PAYLOAD_SHA = 'a1ee163bf8353b5b2c3d5149025790775c7d0bea144b79a88fd4ba24c1c10f7b'
EXPECTED_DECODED_PAYLOAD_SHA = '139e30b33b07411bab2a8236d628fb136fc7d63b47f7e0fbe16a157242f78c01'
EXPECTED_JUG_SHA = 'c99c5ad353c20840e83762f274cffc7864eb559a7f9cd59cb4a6ed730b686377'
EXPECTED_EQ_SHA = 'bf4070a4b60117728425040ea1044b1d95c7d64c17bec307262b576b47f7f012'
EXPECTED_PACKAGE_SHA = '998b7f307ac46ab9e00b4ce8c2780440d1fe0c9b1dcbe6a1dc62dec0cfd9e6f5'
EXPECTED_PACKAGE_RATING_VALUES_SHA = 'ed92790d7b97a522fdda8c45c7f4c818a72427332811a4314651c1d8d957f412'
PANDIANI_PATH = '.local/consolidated-audit-20261009/parallel-rc-20261023/celtic/crossclub-2005-first5/riera-source/jan2006-official-transfer-html/pandiani-espanyol-transfer.html'
PANDIANI_SHA = 'eb41276176fb839352b1c98063df3d0eb4e89a65941928306c50c3cd59b9ccc0'
PANDIANI_URL = 'https://www.uefa.com/uefaeuropaleague/news/01b1-0e6d58cd6be5-ac9ac923f3e5-1000--espanyol-pick-up-pandiani/'
PANDIANI_RECEIPT_PATH = PANDIANI_PATH.removesuffix('.html') + '.source.json'
PANDIANI_RECEIPT_SHA = 'a7597a5fc005648852bf85316586468d6fff4146688243f5932eea16fbd04bef'
EXPECTED_MANIFEST_SHA = 'f9654f1d9f54693b32a6cc0fdda0e32309ba0d7dbb81dde5408b4f479d7d9a06'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _assert_retirement_evidence(request: dict) -> None:
    rows = [r for r in request.get('retirements', []) if r.get('carrier_id') == CARRIER]
    if len(rows) != 1:
        raise ValueError('carrier 19 opt-in requires one exact Amavisca retirement row')
    row = rows[0]
    if (row.get('name'), row.get('birth_date')) != (OLD_NAME, OLD_DOB):
        raise ValueError('Amavisca native retirement identity differs')
    key = 'amavisca_elpais_aug6'
    if key not in row.get('corroboration', []) or key not in request.get('evidence', {}):
        raise ValueError('exact Aug 6 El País retirement source must be bound to carrier 19')
    value = request['evidence'][key]
    if (value.get('path'), value.get('sha256'), value.get('url')) != (ELPAIS_PATH, ELPAIS_SHA, ELPAIS_URL):
        raise ValueError('Amavisca retirement source path/hash/URL differs')
    body = (registry.ROOT / ELPAIS_PATH).resolve(strict=True)
    receipt = (registry.ROOT / ELPAIS_RECEIPT_PATH).resolve(strict=True)
    if (not body.is_relative_to(registry.ROOT.resolve()) or sha(body.read_bytes()) != ELPAIS_SHA
            or not receipt.is_relative_to(registry.ROOT.resolve())
            or sha(receipt.read_bytes()) != ELPAIS_RECEIPT_SHA):
        raise ValueError('Amavisca retirement body or receipt hash differs')
    if json.loads(receipt.read_text()) != {'sha256': ELPAIS_SHA, 'url': ELPAIS_URL}:
        raise ValueError('Amavisca source receipt does not bind body hash and URL')
    page = BeautifulSoup(body.read_bytes(), 'lxml')
    text = ' '.join(page.get_text(' ', strip=True).split())
    date = page.select_one('meta[property="article:published_time"]')
    if (not all(a in text for a in ('Amavisca', 'No jugaré más', 'Espanyol'))
            or date is None or date.get('content') != '2005-08-06T00:00:00+02:00'):
        raise ValueError('Amavisca retirement statement or exact Aug 6 publication date differs')


def _assert_ownership_graph(request: dict, owners: dict[int, set[int]]) -> None:
    moves = [m for m in request.get('moves', [])
             if m.get('source') == 9142 and m.get('destination') == 8928]
    if len(moves) != 1 or (moves[0].get('from_club'), moves[0].get('to_club')) != ('english-club-310', 'club-8'):
        raise ValueError('Riera 9142-to-8928 ownership move is required')
    if ('riera_arrival' not in moves[0].get('evidence', [])
            or 'riera_august_positive' not in request.get('evidence', {})):
        raise ValueError('Riera move must carry dated arrival and positive August witness')
    evidence=request.get('evidence',{})
    arrival=evidence.get('riera_arrival',{})
    if (arrival.get('path'),arrival.get('sha256'),arrival.get('url'),arrival.get('date_anchor'),arrival.get('event_date')) != (
        '.local/consolidated-audit-20261009/parallel-rc-20261023/celtic/crossclub-2005-first5/riera-source/uefa/riera-wings-into-espanyol.html',
        'cf1b5e472dc47f7b23f4bca554bafcdb85051bc8824c50f20497233930c79b79',
        'https://www.uefa.com/uefaeuropaleague/news/0257-0de68328be3e-adfe0130a228-1000--riera-wings-into-espanyol/',
        'July 7, 2005','2005-07-07'):
        raise ValueError('Riera dated Espanyol arrival binding differs')
    rmatch=evidence.get('riera_august_positive',{})
    if (rmatch.get('path'),rmatch.get('sha256'),rmatch.get('url'),rmatch.get('provider_club_id'),rmatch.get('date'),rmatch.get('membership_mode')) != (
        '.local/transfermarkt-opening-plans-current-v1/2005-06/cache/report/37216.html',
        '9252b57e695e0876a47c10b1f245e42e1d7164dbcb01f76937ffc7e8cd7a8aa7',
        'https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/37216',714,'2005-08-28','classic-played-substitutes'):
        raise ValueError('Riera positive August appearance binding differs')
    xi,used_subs=match_people(rmatch)
    if (any(p.get('source_player_id')=='7373' for p in xi)
            or sum(p.get('source_player_id')=='7373' for p in used_subs)!=1):
        raise ValueError('Riera positive numeric August used-substitute witness differs')
    new = request.get('new_people', [])
    croft = [r for r in new if r.get('carrier_id') == 9142]
    ruben = [r for r in new if r.get('carrier_id') == CARRIER]
    if (len(croft) != 1 or croft[0].get('provider_player_id') != 27510
            or len(ruben) != 1 or ruben[0].get('provider_player_id') != NEW_PROVIDER_ID
            or (ruben[0].get('name'), ruben[0].get('birth_date'), ruben[0].get('club_id'))
               != (NEW_NAME, NEW_DOB, 'club-4')):
        raise ValueError('carrier 19 must be replaced only by the exact Real Madrid Rubén admission')
    if 19 in {m.get('source') for m in request.get('moves', [])}:
        raise ValueError('carrier 19 is a replacement target, never a moved source')
    pandiani = [r for r in request.get('retirements', []) if r.get('carrier_id') == 8928]
    if len(pandiani) != 1 or (pandiani[0].get('name'), pandiani[0].get('birth_date')) != ('Walter Pandiani', '1976-04-27'):
        raise ValueError('displaced Espanyol Pandiani retirement must remain explicit')
    if 'pandiani_january_arrival' not in pandiani[0].get('evidence', []):
        raise ValueError('Pandiani Birmingham-to-Espanyol dated source must be bound')
    value=request.get('evidence',{}).get('pandiani_january_arrival',{})
    if (value.get('path'),value.get('sha256'),value.get('url'),value.get('date_anchor'),value.get('event_date')) != (
        PANDIANI_PATH,PANDIANI_SHA,PANDIANI_URL,'January 12, 2006','2006-01-12'):
        raise ValueError('Pandiani retirement source path/hash/URL/date differs')
    body=(registry.ROOT/PANDIANI_PATH).resolve(strict=True)
    receipt=(registry.ROOT/PANDIANI_RECEIPT_PATH).resolve(strict=True)
    if (not body.is_relative_to(registry.ROOT.resolve()) or sha(body.read_bytes())!=PANDIANI_SHA
            or not receipt.is_relative_to(registry.ROOT.resolve()) or sha(receipt.read_bytes())!=PANDIANI_RECEIPT_SHA
            or json.loads(receipt.read_text())!={'sha256':PANDIANI_SHA,'url':PANDIANI_URL}):
        raise ValueError('Pandiani retirement body/receipt binding differs')
    ptext=' '.join(BeautifulSoup(body.read_bytes(),'lxml').get_text(' ',strip=True).split())
    if not all(a in ptext for a in ('Thursday, January 12, 2006','Walter Pandiani','Birmingham City FC','RCD Espanyol')):
        raise ValueError('Pandiani dated ownership transition text differs')
    birmingham = [p for p in request.get('retirements', []) if p.get('carrier_id') == 1858]
    if birmingham or owners.get(1858) != {301}:
        raise ValueError('Birmingham Pandiani carrier 1858 must remain owned by 301')
    if owners.get(8928) != {8} or owners.get(9142) != {310} or owners.get(CARRIER) != {OWNER}:
        raise ValueError('all current target owners must be exclusive and exact')
    # Official row-backed profiles are rebound by dispatch; the request may not
    # substitute a different numeric identity or match locator.
    if ruben[0].get('match') != 'rm_august_bench':
        raise ValueError('Rubén positive August match key differs')


def verify_target_native_preimage(base, request: dict, package: dict, jug: bytes,
                                  eq: bytes, actor: dict, native: dict,
                                  native_skills: dict, owners: dict[int, set[int]]) -> dict:
    claims = request.get('target_native_preimage_opt_ins')
    if not isinstance(claims, list) or len(claims) != 1:
        raise ValueError('exactly one target-native-preimage opt-in is required')
    claim = claims[0]
    required = {'policy','carrier_id','release_id','season','manifest_sha256','package_sha256',
        'jug_sha256','eq_sha256','record_id','payload_offset','payload_length',
        'encoded_payload_sha256','decoded_payload_sha256','native_name','native_birth_date',
        'native_position','native_startup_order','native_skills','package_actor_id',
        'package_name','package_person_id','package_club_id','package_fallback_fields',
        'package_rating_values_sha256','replacement_provider_id','replacement_name',
        'replacement_birth_date','replacement_club_id','retirement_source_key'}
    if not isinstance(claim, dict) or set(claim) != required:
        raise ValueError('target-native-preimage claim fields must be exact')
    if (claim['policy'],claim['carrier_id'],claim['release_id'],claim['season']) != (POLICY,CARRIER,RELEASE_ID,SEASON):
        raise ValueError('this opt-in is restricted to r199 carrier 19')
    if (base.release_id,base.season,base.manifest_sha256) != (RELEASE_ID,SEASON,EXPECTED_MANIFEST_SHA):
        raise ValueError('target-native-preimage parent release binding differs')
    package_path=base.package_path
    if (registry.canonical_document_sha256(package_path) != EXPECTED_PACKAGE_SHA
            or sha(jug) != EXPECTED_JUG_SHA or sha(eq) != EXPECTED_EQ_SHA):
        raise ValueError('target-native-preimage parent package/JUG/EQ hashes differ')
    expected_actor=next((p for p in package['players'] if p.get('carrier_id')==CARRIER),None)
    if expected_actor is None or actor != expected_actor:
        raise ValueError('target-native-preimage package actor differs from supplied actor')
    for key,value in {
        'manifest_sha256':EXPECTED_MANIFEST_SHA,'package_sha256':EXPECTED_PACKAGE_SHA,
        'jug_sha256':EXPECTED_JUG_SHA,'eq_sha256':EXPECTED_EQ_SHA,
        'record_id':CARRIER,'native_name':OLD_NAME,'native_birth_date':OLD_DOB,
        'native_position':'M','native_startup_order':24,'native_skills':EXPECTED_NATIVE_SKILLS,
        'package_actor_id':'player-19','package_name':OLD_NAME,'package_person_id':'person-19',
        'package_club_id':'club-4','package_fallback_fields':['birth_date','fine_roles','height_cm','nationality','primary_position','shirt_number','weight_kg'],
        'package_rating_values_sha256':EXPECTED_PACKAGE_RATING_VALUES_SHA,
        'replacement_provider_id':NEW_PROVIDER_ID,'replacement_name':NEW_NAME,
        'replacement_birth_date':NEW_DOB,'replacement_club_id':'club-4',
        'retirement_source_key':'amavisca_elpais_aug6'}.items():
        if claim.get(key) != value:
            raise ValueError(f'target-native-preimage claim differs: {key}')
    if (actor.get('id'),actor.get('name'),actor.get('person_id'),actor.get('club_id')) != ('player-19',OLD_NAME,'person-19','club-4'):
        raise ValueError('target-native-preimage actor identity/owner differs')
    if set(actor.get('facts',{})) != set(claim['package_fallback_fields']):
        raise ValueError('declared fallback field set differs')
    if any(actor['facts'][field] != {'policy':'preserve-existing-mode1'} for field in claim['package_fallback_fields']):
        raise ValueError('carrier 19 package must declare preserve-existing-mode1 for every fallback field')
    # Reuse the existing retained-field API, but only after exact policy checks
    # and only for this one fully replaced target.
    if (not complete.retained_field_matches(actor['facts']['birth_date'],native['birth_date'])
            or not complete.retained_field_matches(actor['facts']['primary_position'],native['position'])):
        raise ValueError('declared retained DOB/position fallback does not match native preimage')
    rating_values=actor.get('ratings',{}).get('values')
    if (not isinstance(rating_values,dict)
            or sha(json.dumps(rating_values,sort_keys=True,separators=(',',':')).encode()) != claim['package_rating_values_sha256']
            or rating_values != EXPECTED_PACKAGE_RATINGS):
        raise ValueError('Amavisca package rating preimage differs')
    if native != {'name':OLD_NAME,'birth_date':OLD_DOB,'position':'M','startup_order':24}:
        raise ValueError('Amavisca native identity/DOB/position/order preimage differs')
    if native_skills != EXPECTED_NATIVE_SKILLS:
        raise ValueError('Amavisca native skill preimage differs')
    if native_skills == rating_values:
        raise ValueError('target-native-preimage opt-in is unnecessary when package ratings already match')
    index=IndexedFDIFile.from_bytes(jug)
    entries=[e for e in index.entries if e.record_id==CARRIER]
    if len(entries)!=1:
        raise ValueError('carrier 19 must have one indexed native record')
    entry=entries[0]; raw=jug[entry.payload_offset:entry.payload_offset+entry.payload_length]
    decoded=entry.decode_payload(jug)
    if (entry.payload_offset,entry.payload_length,sha(raw),sha(decoded)) != (
        152237,81,EXPECTED_RAW_PAYLOAD_SHA,EXPECTED_DECODED_PAYLOAD_SHA):
        raise ValueError('carrier 19 raw/decoded native payload preimage differs')
    if (claim['payload_offset'],claim['payload_length'],claim['encoded_payload_sha256'],claim['decoded_payload_sha256']) != (
        entry.payload_offset,entry.payload_length,sha(raw),sha(decoded)):
        raise ValueError('explicit target native payload hash/offset differs')
    if owners.get(CARRIER)!={OWNER} or owners.get(8928)!={8} or owners.get(9142)!={310}:
        raise ValueError('target native owner sets differ')
    _assert_ownership_graph(request,owners)
    birmingham_actor=next((p for p in package['players'] if p.get('carrier_id')==1858),None)
    if (birmingham_actor is None or (birmingham_actor.get('name'),
            birmingham_actor.get('facts',{}).get('birth_date'),birmingham_actor.get('club_id'))
            != ('Walter Pandiani','1976-04-27','english-club-301')
            or read_native_facts(jug,1858) != {'name':'Walter PANDIANI','birth_date':'1976-04-27','position':'F','startup_order':11}):
        raise ValueError('Birmingham Pandiani native/package identity owner must remain exact')
    _assert_retirement_evidence(request)
    return {'policy':POLICY,'carrier_id':CARRIER,'action':'replace-complete-native-actor',
        'native_name':OLD_NAME,'native_birth_date':OLD_DOB,
        'source_bound':True,'payload_sha256':sha(raw),'native_skills':dict(native_skills),
        'scope':'bypass only package-vs-native fallback DOB/position and package-vs-native rating preimages for carrier19, which is fully replaced by validated Rubén; owner/name/order/whole-parent and all other actor guards remain strict'}
