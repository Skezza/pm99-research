"""Reconcile the cached 2000 Trabzon XI and test a bounded native correction.

Source-only milestone: no game, recipe or registration is written. The
candidate removes one misidentified duplicate link and changes startup-order
bytes only. Missing bench members and unsourced birthdays remain explicit.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from app.eq_roster_pruning import prune_visible_mode1_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, patch_owned_mode1_complete_orders
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_historical_roster_audit_v1 as annual
from scripts import season_italian_opening_layer_v1 as native
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts import season_tff_sourced_opening_xi_v1 as tff
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records

SCHEMA = 'pm99-Trabzon-2000-original-opening-duplicate-link-review-v1'
CACHE = '.local/transfermarkt-opening-plans-current-v1/2000-01'
PROFILES = (
    ('25296', 'ERHAN NAMLI', '1974-05-07',
     '25c0da31f2748d9d45ba8ccc2340f35e8ae7a9468fcb1a99add71226aa186ecb'),
    ('29662', 'VOLKAN KAHRAMAN', '1979-10-10',
     'f15cde304691ffa53b9689030505a2e8e8cec7ccddaf9db1ae81d33ff92d56eb'),
)


def key(name):
    # Provider slugs explicitly transliterate the Turkish dotless i.
    return annual.normalise(name.replace('ı', 'i').replace('İ', 'I'))


def original_person_links(raw, people):
    """Bind each numeric ID to its full original published profile URL slug.

    Never expand a surname or trust a generated capture's source_slug field.
    All occurrences of the same original ID must publish the same slug.
    """
    links = {}
    for a in BeautifulSoup(raw, 'lxml').select('a[href]'):
        url = urlparse(a['href'])
        if url.netloc not in ('', 'www.transfermarkt.co.uk'):
            continue
        match = re.fullmatch(r'/([^/]+)/profil/spieler/(\d+)(?:/)?', url.path)
        if match and match[2] in people:
            links.setdefault(match[2], set()).add(match[1])
    if set(links) != set(people) or any(len(v) != 1 for v in links.values()):
        raise ValueError('original player IDs have missing or conflicting full-name slugs')
    return {id: next(iter(slugs)) for id, slugs in links.items()}


def join_person(source_id, slug, annual_players, recipe_players, native_facts, *, dated_person=None):
    sources = [p for p in annual_players if key(p['name']) == key(slug)]
    if len(sources) != 1:
        raise ValueError('published full-name slug needs one literal annual identity')
    source = sources[0]
    candidates = [p for p in recipe_players if key(p.get('source_name') or p['name']) == key(source['name'])]
    if dated_person is not None:
        if key(dated_person.get('registered_name', '')) != key(source['name']):
            raise ValueError('dated original person belongs to another full-name identity')
        candidates = [p for p in candidates if native_facts[p['carrier_id']]['birth_date'] == dated_person['birth_date']]
    if len(candidates) != 1:
        raise ValueError('opening identity has missing/ambiguous native carrier; no first-name guessing')
    p = candidates[0]
    if (native_facts[p['carrier_id']]['position'] != source['position'] or
            p['facts']['primary_position'] != source['position']):
        raise ValueError('original annual broad position differs from native/recipe')
    return {'source_player_id': source_id, 'published_slug': slug,
            'source': source, 'carrier_id': p['carrier_id'], 'player_id': p['id'],
            'native': native_facts[p['carrier_id']],
            'identity_basis': 'original numeric match ID/full-name slug and unique target annual/recipe full name'
                + ('; retained native birthday matches original TFF person' if dated_person else ''),
            'birthday_independently_verified': dated_person is not None or
                (bool(source.get('birth_date')) and source['birth_date'] == native_facts[p['carrier_id']]['birth_date'])}


def profiles():
    rows = []
    for id, name, birthday, sha in PROFILES:
        url = 'https://www.tff.org/Default.aspx?kisiId=' + id + '&pageId=30'
        cache = registry.ROOT / '.local/consolidated-audit-20261009/tff-source-cache'
        path = cache / (hashlib.sha256(url.encode()).hexdigest() + '.html')
        receipt = json.loads(path.with_suffix('.source.json').read_text())
        if receipt != {'url': url, 'sha256': sha} or registry.sha256_file(path) != sha:
            raise ValueError('original TFF person receipt/preimage changed')
        binding = {'url': url, 'path': registry.relative_workspace_path(path), 'sha256': sha}
        tff.require_tff_binding(binding, 30, 'kisiid', id)
        parsed = tff.profile(path.read_bytes(), name)
        if parsed['birth_date'] != birthday:
            raise ValueError('original TFF birthday differs')
        rows.append({'person_id': id, **parsed, 'source': binding})
    return rows


def prepare(release=None):
    release = release or registry.load_preferred_release('2000-01')
    if release.season != '2000-01':
        raise ValueError('this source policy is explicitly limited to 2000/01')
    package = json.loads(release.package_path.read_text())
    club = next(c for c in package['clubs'] if c['carrier_id'] == 1002)
    if club['name'] != 'Trabzonspor':
        raise ValueError('native club identity changed')
    capture_path = registry.ROOT / CACHE / 'opening-lineups.json'
    capture = json.loads(capture_path.read_text())
    rows = [c for c in capture['clubs'] if c['source_selector'].get('transfermarkt_club_id') == 449]
    if len(rows) != 1:
        raise ValueError('ambiguous original club capture')
    row = rows[0]
    verified = opening.verify_opening(row, capture, registry.ROOT / CACHE / 'cache')
    if (verified['date'], row['source_match_id'], row['source_competition_code']) != ('2000-08-12', '951676', 'TR1'):
        raise ValueError('wrong original first domestic fixture')
    starters, bench = verified['starting_xi'], verified['substitutes']
    if len(starters) != 11 or len(bench) != 7 or set(starters) & set(bench):
        raise ValueError('original matchday must publish eleven plus seven distinct people')
    raw, _ = opening.verified_page(registry.ROOT / CACHE / 'cache', capture['source']['cache_files'], row['lineup_source_url'])
    slugs = original_person_links(raw, {**starters, **bench})
    annual_capture, annual_proof = facts.annual_capture('2000-01', club)
    people = [p for p in package['players'] if p['id'] in club['roster_player_ids']]
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    natives = {p['carrier_id']: facts.native_facts(jug, p['carrier_id']) for p in people}
    _, _, roster = native.roster_rows(eq, 1002)
    if [id for id, _ in roster] != [next(p['carrier_id'] for p in people if p['id'] == id) for id in club['roster_player_ids']]:
        raise ValueError('recipe/native roster preimages disagree')
    tff_people = profiles()
    xi = [join_person(id, slugs[id], annual_capture['players'], people, natives,
                     dated_person=tff_people[0] if id == '7213' else None)
          for id in (str(p['source_player_id']) for p in row['starting_xi'])]
    if len({p['carrier_id'] for p in xi}) != 11 or xi[0]['source']['position'] != 'G':
        raise ValueError('source XI does not have eleven carriers with goalkeeper first')
    erhan = next(p for p in xi if p['source_player_id'] == '7213')
    duplicate = [p for p in people if key(p.get('source_name') or p['name']) == key(erhan['source']['name'])
                 and p['carrier_id'] != erhan['carrier_id']]
    if (erhan['carrier_id'] != 8052 or len(duplicate) != 1 or duplicate[0]['carrier_id'] != 32505
            or key(natives[32505]['name']) != key(natives[8052]['name'])
            or natives[32505]['birth_date'] != '1977-09-17'):
        raise ValueError('reviewed duplicate preimage differs; no general same-name deletion policy')
    owners = ownership.native_owners(eq)
    if any(owners.get(id) != {1002} for id, _ in roster):
        raise ValueError('shared native player prevents exclusive full-XI order repair')
    xi_ids = [p['carrier_id'] for p in xi]
    reserve_ids = sorted((id for id, _ in roster if id not in xi_ids and id != 32505),
                         key=lambda id: (natives[id]['startup_order'], id))
    orders = [{'carrier_id': id, **natives[id], 'after': n}
              for n, id in enumerate(xi_ids + reserve_ids, 1)]
    bench_witnesses = []
    for id, label in bench.items():
        source = [p for p in annual_capture['players'] if key(p['name']) == key(slugs[id])]
        if len(source) != 1:
            raise ValueError('original bench full-name slug has no unique annual person')
        matches = [p['carrier_id'] for p in people if key(p.get('source_name') or p['name']) == key(source[0]['name'])]
        bench_witnesses.append({'source_player_id': id, 'published_name': label,
            'full_source_name': source[0]['name'], 'current_carriers': matches,
            'first_match_bench_membership_verified': True})
    return {'schema': SCHEMA, 'season': release.season, 'release_id': release.release_id,
        'package_sha256': registry.sha256_file(release.package_path),
        'jug_sha256': hashlib.sha256(jug).hexdigest(), 'eq_sha256': hashlib.sha256(eq).hexdigest(),
        'club_carrier_id': 1002, 'club_id': club['id'], 'before_club': club,
        'original_opening_capture_sha256': registry.sha256_file(capture_path),
        'original_fixture': verified, 'annual_proof': annual_proof, 'TFF_people': tff_people,
        'starting_xi': xi, 'bench_witnesses': bench_witnesses,
        'before_rows': [list(r) for r in roster],
        'after_rows': [list(r) for r in roster if r[0] != 32505], 'removed_link': 32505,
        'removal_basis': 'one published Erhan Namli annual/match identity; retained native DOB matches TFF25296; duplicate source/native name has wrong birthday',
        'orders': orders, 'startup_order_policy': 'original published pitch-grid order; remaining reserves stable old order/ID',
        'remaining_bench_gaps': [p for p in bench_witnesses if not p['current_carriers']],
        'unverified_XI_birthdays': [p['carrier_id'] for p in xi if not p['birthday_independently_verified']],
        'full_roster_historical_accuracy_approved': False, 'game_installed': False, 'registered': False}


def test_candidate(release, plan):
    """Exercise canonical native APIs in memory, no binary files emitted."""
    if prepare(release) != plan:
        raise ValueError('source-derived plan does not independently reproduce')
    jug = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
    eq = (release.game_path / 'DBDAT/EQ98030.FDI').read_bytes()
    index, raw, rows = native.roster_rows(eq, 1002)
    changed = prune_visible_mode1_roster_payload(raw, expected_rows=rows, removed_player_ids=[32505])
    candidate_eq = compiler._rebuild_indexed(eq, index, {1002: compiler.xor_decode(changed)})
    replacements = [OrderReplacement(r['carrier_id'], r['name'], r['startup_order'], r['after']) for r in plan['orders']]
    candidate_jug = patch_owned_mode1_complete_orders(jug, candidate_eq, club_record_id=1002, replacements=replacements)
    preserve_other_records(eq, candidate_eq, {1002})
    preserve_other_records(jug, candidate_jug, {r['carrier_id'] for r in plan['orders']})
    if patch_owned_mode1_complete_orders(candidate_jug, candidate_eq, club_record_id=1002, replacements=replacements) != candidate_jug:
        raise ValueError('candidate order repair is not idempotent')
    _, _, after = native.roster_rows(candidate_eq, 1002)
    if [list(r) for r in after] != plan['after_rows']:
        raise ValueError('candidate roster removal readback differs')
    readback = sorted((facts.native_facts(candidate_jug, id)['startup_order'], id) for id, _ in after)
    if readback[:11] != [(n, p['carrier_id']) for n, p in enumerate(plan['starting_xi'], 1)]:
        raise ValueError('candidate first XI readback differs')
    return {'schema': 'pm99-Trabzon-in-memory-native-candidate-proof-v1', 'status': 'PASS',
        'source_review_sha256': hashlib.sha256((json.dumps(plan, ensure_ascii=False,
            sort_keys=True, separators=(',', ':')) + '\n').encode()).hexdigest(),
        'implementation_sha256': registry.sha256_file(Path(__file__)),
        'candidate_eq_sha256': hashlib.sha256(candidate_eq).hexdigest(),
        'candidate_jug_sha256': hashlib.sha256(candidate_jug).hexdigest(),
        'XI_readback': readback[:11], 'roster_before': len(rows), 'roster_after': len(after),
        'unrelated_records_preserved': True, 'startup_order_idempotent': True,
        'native_files_written': 0, 'recipe_written': False, 'registered': False, 'runtime_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('source reviews are immutable; choose a new output directory')
    from scripts import consolidated_season_discovery_v1 as discovery
    before = discovery.bindings()
    release = registry.load_preferred_release('2000-01')
    plan = prepare(release)
    proof = test_candidate(release, plan)
    if discovery.bindings() != before:
        raise ValueError('current season bindings changed during source review')
    args.output.mkdir(parents=True)
    discovery.write_new(args.output / 'source-review.json', plan)
    discovery.write_new(args.output / 'native-candidate-proof.json', proof)
    print(json.dumps(proof), flush=True)
