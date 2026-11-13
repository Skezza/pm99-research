"""Bounded source701 admission using existing native roster/order/shirt writers.

The published fixture party remains in the retained source packet. The recipe
opening selection expresses the game's eleven starters and five substitutes.
"""
import copy
import hashlib
import json
import re
import csv
from datetime import datetime
import unicodedata
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import read_initial_order, patch_initial_orders, OrderReplacement
from app.indexed_jug_shirt_number import rewrite_indexed_native_shirt_numbers
from scripts import json_storage_io_v1 as storage_io
from scripts import season_roster_membership_payload_core_v1 as core
from scripts import season_release_registry_v1 as registry
from scripts import season_package_v2 as packages
from scripts import capture_transfermarkt_opening_lineups_v1 as capture

SCHEMA = 'pm99-source701-mode0-rebased-proposal-v2'
APPROVED_SOURCE_SHA256 = 'f03c5d9c503a366abfc252afbff1d6f21e231980528b1d48110ba8561192e603'
SELECTED = {324, 333, 344, 345, 346}

# Explicit reviewed provider-person to existing Native-person crosswalk.
PEOPLE = {
 '293257': (10343, 'Matija Sarkic', '1997-07-23'),
 '469064': (10455, 'Gavin Kilkenny', '2000-02-01'),
 '203127': (10414, 'Conor McGrandles', '1995-09-24'),
 '607199': (9593, 'Saikou Janneh', '2000-01-11'),
 '209291': (10355, 'Jack Bonham', '1993-09-14'),
 '13520': (10352, 'Phil Jagielka', '1982-08-17'),
 '621365': (10349, 'Tom Sparrow', '2002-12-06'),
 '444211': (10358, 'Will Smallbone', '2000-02-21'),
 '321169': (10356, 'Jordan Thompson', '1997-01-03'),
 '469958': (10354, 'Jacob Brown', '1998-04-10'),
}

def normalise(value):
    return ''.join(c.casefold() for c in unicodedata.normalize('NFKD', value) if c.isalnum() and not unicodedata.combining(c))


def source_bindings(doc):
    from scripts.season_source_bound_fixture_membership_v1 import _source_path
    # Authorisation is the exact reviewed immutable source packet, not model
    # agreement or an arbitrary rewritten row table.
    from scripts import season_pipeline_v2 as pipeline
    path = registry.ROOT/'.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/source701-mode0-roster-order-rebase-r705-v3/source701-mode0-roster-order-rebase-r705-v3.json'
    if registry.sha256_file(path) != APPROVED_SOURCE_SHA256 or pipeline.read_json_file(path) != doc:
        raise ValueError('transaction differs from reviewed source701 packet')
    rows = []
    for f in doc['opening_source_bindings']['fixtures']:
        p = _source_path(f['report_path'])
        if registry.sha256_file(p) != f['report_sha256']:
            raise ValueError('original opening fixture hash changed')
        rows.append(dict(path=f['report_path'], sha256=f['report_sha256']))
    for f in doc['target_club_shirt_numbers']:
        p = _source_path(f['source_path'])
        if registry.sha256_file(p) != f['source_sha256'] or f['exact_source_row'] not in storage_io.read_text(p):
            raise ValueError('target-club shirt source changed')
        rows.append(dict(path=f['source_path'], sha256=f['source_sha256']))
    published = set()
    for row in doc['target_club_shirt_numbers']:
        for fields in csv.reader(storage_io.read_text(registry.ROOT / row['source_path']).splitlines(), skipinitialspace=True):
            if len(fields) < 7:
                continue
            try:
                dob = datetime.strptime(fields[6], '%d-%m-%y').date().isoformat()
            except ValueError:
                continue
            published.add((normalise(fields[1]), dob))
    if any((normalise(name), dob) not in published for _, name, dob in PEOPLE.values()):
        raise ValueError('reviewed provider-person name/DOB lacks a retained annual row')
    row = doc['pearson_january_chronology']['contemporaneous_independent_report']
    p = _source_path(row['raw_body_path'])
    if registry.sha256_file(p) != row['raw_body_sha256']:
        raise ValueError('retained Pearson chronology changed')
    rows.append(dict(path=row['raw_body_path'], sha256=row['raw_body_sha256']))
    return rows


def reports(doc, players):
    receipts = []
    for f in doc['opening_source_bindings']['fixtures']:
        page = BeautifulSoup(storage_io.read_bytes(registry.ROOT / f['report_path']), 'html.parser')
        def side(box):
            ids = {int(m[1]) for a in box.select('a[href]') if (m := re.search(r'/startseite/verein/(\d+)(?:/|$)', a['href']))}
            return ids == {f['provider_club_id']}
        boxes = [b for b in page.select('.aufstellung-box') if side(b)]
        if not boxes:
            boxes = [b for b in page.select('.large-6') if side(b)]
        if len(boxes) != 1:
            raise ValueError('fixture side is not uniquely source-club bound')
        xi, subs, _, _ = capture._modern_lineup(boxes[0])
        if [r['source_player_id'] for r in xi] != f['xi_provider_ids'] or [r['source_player_id'] for r in subs] != f['sub_provider_ids']:
            raise ValueError('original published opening party differs')
        for person in xi + subs:
            source_id = person['source_player_id']
            if source_id in PEOPLE:
                pid, name, dob = PEOPLE[source_id]
                if normalise(person['display_name']) != normalise(name) or normalise(players[pid]['source_name']) != normalise(name) or players[pid]['facts']['birth_date'] != dob:
                    raise ValueError('fixture provider-person and Native person crosswalk differs')
        receipts.append(dict(club_carrier=f['club_carrier_id'], source_match_id=f['source_match_id'], fixture_date=f['fixture_date'], published_XI=len(xi), published_bench=len(subs), identity_review_exceptions=[]))
    return receipts


def compose(parent, main, english, eq, jug, doc):
    sources = source_bindings(doc)
    pin = doc['parent']
    if (parent.season, parent.release_id, parent.manifest_sha256, registry.sha256_file(parent.package_path)) != (pin['season'], pin['release_id'], pin['manifest_sha256'], pin['package_sha256']):
        raise ValueError('source transaction parent differs')
    for name, expected in pin['native_sha256'].items():
        if registry.sha256_file(parent.game_path/'DBDAT'/name) != expected:
            raise ValueError('source transaction native parent differs')
    if eq != storage_io.read_bytes(parent.game_path / 'DBDAT/EQ98030.FDI') or jug != storage_io.read_bytes(parent.game_path / 'DBDAT/JUG98030.FDI'):
        raise ValueError('memory inputs differ from pinned parent')
    if packages.canonical_json_bytes(main) != storage_io.read_bytes(parent.package_path):
        raise ValueError('supplied main recipe differs from immutable parent')
    from scripts.season_source_bound_fixture_membership_v1 import _layer_path
    if packages.canonical_json_bytes(english) != storage_io.read_bytes(_layer_path(main, parent.package_path, 'english-season-package.json')):
        raise ValueError('supplied English recipe differs from immutable parent')
    players_by_carrier = {x['carrier_id']: x for x in main['players']}
    from scripts import season_package_compiler_v2 as compiler, season_historical_roster_audit_v1 as audit
    native_entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    for pid, name, dob in PEOPLE.values():
        payload = native_entries[pid].decode_payload(jug)
        person = audit.native_player(payload, pid)
        fields = compiler._read_native_dd6360_fields(payload, person['name_end'])
        actual_dob = f"{fields['birth_year']:04}-{fields['birth_month']:02}-{fields['birth_day']:02}"
        if normalise(person['name']) != normalise(name) or actual_dob != dob:
            raise ValueError('Native name/DOB differs from reviewed provider-person')
    raw_receipts = reports(doc, players_by_carrier)
    # Semantically reread the qualified contemporary secondary report.
    bbc = doc['pearson_january_chronology']['contemporaneous_independent_report']
    text = BeautifulSoup(storage_io.read_bytes(registry.ROOT / bbc['raw_body_path']), 'html.parser').get_text(' ', strip=True).casefold()
    if not all(word in text for word in ('pearson', 'stoke', 'bournemouth', 'loan')):
        raise ValueError('retained secondary report lacks the named loan context')
    claims = doc['approved_membership_changes']
    moves = [dict(player_record_id=x['carrier_id'], from_club_carrier_id=x['from_club'], to_club_carrier_id=x['to_club']) for x in claims['moves']]
    removals = [dict(player_record_id=x['carrier_id'], from_club_carrier_id=x['from_club']) for x in claims['remove_false_or_unowned_links']]
    if set(doc['transaction']['changed_EQ_club_carriers']) != SELECTED:
        raise ValueError('source transaction selects other clubs')
    desired = {cid: [(x['flag'], x['carrier_id']) for x in doc['clubs'][str(cid)]['after_rows']] for cid in SELECTED}
    _, _, native, _ = core._read_rosters(eq)
    for cid in SELECTED:
        if [(x.flag, x.player_record_id) for x in native[cid].rows] != [(x['flag'], x['carrier_id']) for x in doc['clubs'][str(cid)]['before_rows']]:
            raise ValueError('native roster preimage changed')
    eq_after, receipt = core.rewrite_membership_transaction(eq, moves=moves, removals=removals, desired_rosters=desired)
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    orders = []
    for cid in sorted(SELECTED):
        for row in doc['clubs'][str(cid)]['after_rows']:
            field = read_initial_order(entries[row['carrier_id']].decode_payload(jug))
            if field.name != row['native_name']:
                raise ValueError('source actor native identity differs')
            orders.append(OrderReplacement(row['carrier_id'], field.name, field.order, row['order']))
    jug_after = patch_initial_orders(jug, orders)
    shirts = {}
    for row in doc['target_club_shirt_numbers']:
        pid = row['carrier_id']; payload = entries[pid].decode_payload(jug)
        fields = next(csv.reader([row['exact_source_row']], skipinitialspace=True))
        if (int(fields[0]) != row['new_target_shirt_number']
            or normalise(fields[1]) != normalise(players_by_carrier[pid]['source_name'])
            or datetime.strptime(fields[6], '%d-%m-%y').date().isoformat() != players_by_carrier[pid]['facts']['birth_date']
            or players_by_carrier[pid]['person_id'] != row['person_id']
            or players_by_carrier[pid]['facts']['shirt_number'] != row['old_recipe_shirt_number']
            or not any(m['player_record_id'] == pid and m['to_club_carrier_id'] == row['target_club_carrier_id'] for m in moves)):
            raise ValueError('shirt source name/DOB/known identity/number/target crosswalk differs')
        shirts[pid] = dict(native_name=read_initial_order(payload).name, before_number=payload[7]^0x61, number=row['new_target_shirt_number'])
    jug_after, _ = rewrite_indexed_native_shirt_numbers(jug_after, shirts)
    main_after = copy.deepcopy(main)
    english_after = copy.deepcopy(english)
    # The older English artifact still contains the pre705 identities. Bring
    # only these two existing English actors forward from the proven parent.
    current = {x['carrier_id']: x for x in main['players']}
    for i, actor in enumerate(english_after['players']):
        if actor['carrier_id'] in {9270, 10349}:
            english_after['players'][i] = copy.deepcopy(current[actor['carrier_id']])
    # Copy the existing parent citations needed by those two projected actors.
    for key, wanted in [('artifacts', {'source705-identity-bound-height-unknown-weight-united-shirt-root-v4'}),
                        ('sources', {'source-bound-rating-calibration-v3'})]:
        known = {row['id'] for row in english_after[key]}
        english_after[key].extend(copy.deepcopy(row) for row in main[key] if row['id'] in wanted and row['id'] not in known)
    required = {row['evidence_artifact_id'] for row in english_after['sources'] if row['id'] == 'source-bound-rating-calibration-v3'}
    known = {row['id'] for row in english_after['artifacts']}
    english_after['artifacts'].extend(copy.deepcopy(row) for row in main['artifacts'] if row['id'] in required and row['id'] not in known)
    english_after['artifacts'].sort(key=lambda row: row['id'])
    english_after['sources'].sort(key=lambda row: row['id'])
    for package in (main_after, english_after):
        players = {x['carrier_id']: x for x in package['players']}
        clubs = {x['carrier_id']: x for x in package['clubs']}
        for row in moves:
            pid, target = row['player_record_id'], row['to_club_carrier_id']
            players[pid]['club_id'] = clubs[target]['id']
            players[pid]['facts']['shirt_number'] = shirts[pid]['number']
        for cid in SELECTED:
            club = clubs[cid]
            ids = [players[pid]['id'] for _, pid in desired[cid]]
            if club['opening']['starting_xi_player_ids'] != ids[:11]:
                raise ValueError('transaction would change a starting XI')
            club['roster_player_ids'] = ids
            club['opening']['substitute_player_ids'] = ids[11:16]
        packages.validate_package(package)
    stoke_ids = {players_by_carrier[PEOPLE[x][0]]['id'] for x in doc['opening_source_bindings']['fixtures'][0]['sub_provider_ids']}
    stoke = next(x for x in main_after['clubs'] if x['carrier_id'] == 344)
    if not stoke_ids <= set(stoke['roster_player_ids']) or stoke['opening']['substitute_player_ids'] != [players_by_carrier[x]['id'] for x in (10355, 10352, 10349, 10358, 10354)]:
        raise ValueError('published seven or approved five gamebench people not retained')
    # Retain all published bench evidence in the hash-bound source packet;
    # game selection has five substitutes, and every proposed member remains
    # in the complete roster. No historical seven-to-five equivalence claimed.
    from scripts import season_package_v2 as package_v2
    overlay = [x for x in main_after['artifacts'] if x.get('relative_path','').endswith('english-season-package.json')]
    if len(overlay) != 1:
        raise ValueError('English layer binding is ambiguous')
    overlay[0]['sha256'] = hashlib.sha256(package_v2.canonical_json_bytes(english_after)).hexdigest()
    return dict(source_bindings=sources, raw_report_reconstruction=raw_receipts, roster_payload_receipt=receipt,
                outputs=dict(main_package=main_after, english_package=english_after, eq=eq_after, jug=jug_after))
