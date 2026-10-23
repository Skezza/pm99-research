"""Self-contained, case-scoped Amavisca retirement and Espanyol XI adapter."""
from __future__ import annotations

import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path

from app.eq_jug_linked import parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, patch_initial_orders, read_initial_order
from scripts import season_opening_identity_exchange_v1 as exchange
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from scripts import season_package_v2 as packages
from scripts import season_within_club_reserve_repair_v1 as facts

MODE = 'known-good-baseline-source-backed-amavisca-retirement-xi-v4'
POLICY = 'amavisca-2005-espanyol-retirement-and-xi-v1'
SCHEMA = 'pm99-amavisca-exact-case-transaction-r194-v4'
INPUT_SCHEMA = 'pm99-amavisca-input-r194-v4'
FILENAME = 'amavisca-retirement-xi-r194-v4.json'
SOURCE_PLAN_FILENAME = 'amavisca-opening-xi-source-plan-r194-v4.json'
SOURCE_PLAN_ARTIFACT_ID = 'amavisca-opening-xi-source-plan-r194-v4'
FIXTURE_SHA256 = '9252b57e695e0876a47c10b1f245e42e1d7164dbcb01f76937ffc7e8cd7a8aa7'
CAPTURE_SHA256 = '72265700a67472afc484f34a0bfeed8565cc3629f3e561016f2426ba2b6b4900'
SCHEDULE_SHA256 = '6f0b1cc5f7f8a6252eabf4c3cb6e9ab7a98ef256aa7e9965d5a9eb845d971bf8'
PREALLOCATION_SHA256 = '6f0aaf53ee8f6dda9e641bf9d124548111036620fbddf29e512bddb81e6d6681'
CLUB_ID = 'club-8'
CLUB_CARRIER = 8
TARGET_PLAYER = 19
PRESERVED_FLAGGED = 18788
EXPECTED_ROWS = (
    (19, 0), (131, 0), (148, 0), (150, 0), (157, 0), (159, 0), (203, 0),
    (249, 0), (301, 0), (368, 0), (605, 0), (3892, 0), (4000, 0),
    (4003, 0), (4023, 0), (5311, 0), (8861, 0), (8928, 0), (14656, 0),
    (18784, 0), (18788, 1), (23886, 0), (23972, 0), (31493, 0),
)
ELPAIS_URL = 'https://elpais.com/diario/2005/08/06/deportes/1123279206_850215.html?outputType=amp'
ELPAIS_CANONICAL = 'https://elpais.com/diario/2005/08/06/deportes/1123279206_850215.html'
ELPAIS_SHA256 = '5381d792e1281223c867b1e4dfa2722053cc16bebdd93cb5ddaed62953c4fe7f'
LALIGA_URL = 'https://www.laliga.com/en-ES/news/what-became-of-amavisca?simple=true'
LALIGA_SHA256 = 'd3b59938d679f3286764ee41508e03f06a1d1fd6c0f1fe44a36a8b129d867800'
ROOT = registry.ROOT


class _Head(HTMLParser):
    def __init__(self):
        super().__init__()
        self.meta = {}
        self.links = []
        self.title = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'meta':
            key = values.get('name') or values.get('property')
            if key:
                self.meta[key] = values.get('content', '')
        if tag == 'link' and values.get('rel') == 'canonical':
            self.links.append(values.get('href', ''))

    def handle_endtag(self, tag):
        if tag == 'title':
            self.title = True


def _read_bound_source(spec, *, expected_url, expected_sha, source_kind):
    if not isinstance(spec, dict) or set(spec) != {'path', 'sha256', 'url'}:
        raise ValueError('source witness must be exact path/hash/url triple')
    if spec['url'] != expected_url or spec['sha256'] != expected_sha:
        raise ValueError('source witness URL/hash differs from retained original')
    rel = Path(spec['path'])
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('source path must be workspace-relative')
    path = (ROOT / rel).resolve(strict=True)
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('source path escapes workspace')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('source original hash differs')
    receipt_path = path.with_suffix('.source.json')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt != {'sha256': expected_sha, 'url': spec['url']}:
        raise ValueError('source receipt differs from exact original')
    text = raw.decode('utf-8', errors='strict')
    if source_kind == 'elpais':
        parser = _Head(); parser.feed(text)
        published = parser.meta.get('article:published_time')
        canonical = parser.links
        if (published != '2005-08-06T00:00:00+02:00' or canonical != [ELPAIS_CANONICAL]
                or 'José Emilio Amavisca Gárate' not in text
                or 'No jugaré más' not in text or 'Espanyol' not in text):
            raise ValueError('EL PAÍS exact article identity/date/retirement anchors differ')
        return dict(url=spec['url'], sha256=expected_sha, published='2005-08-06',
                    canonical=canonical[0], anchors=['José Emilio Amavisca Gárate', 'No jugaré más', 'Espanyol'])
    # LALIGA is a later corroborating retrospective, not contemporaneous.
    if ('Amavisca' not in text or '2005' not in text or 'Espanyol' not in text):
        raise ValueError('LALIGA retrospective identity/retirement/club anchors differ')
    return dict(url=spec['url'], sha256=expected_sha, publication='2013-10-24',
                anchors=['Amavisca', '2005', 'Espanyol'])


def verify_retirement_sources(evidence):
    if not isinstance(evidence, dict) or set(evidence) != {'elpais', 'laliga'}:
        raise ValueError('both exact retirement source witnesses are required')
    ep = _read_bound_source(evidence['elpais'], expected_url=ELPAIS_URL,
                            expected_sha=ELPAIS_SHA256, source_kind='elpais')
    liga = _read_bound_source(evidence['laliga'], expected_url=LALIGA_URL,
                              expected_sha=LALIGA_SHA256, source_kind='laliga')
    return {'elpais': ep, 'laliga': liga,
            'date_admission': 'EL PAIS article:published_time; not generic dated_source parser'}


def _verify_release(release, package, jug, eq, parent):
    if (release.season != '2005-06' or release.release_id != parent['release_id']
            or release.manifest_sha256 != parent['manifest_sha256']):
        raise ValueError('release identity is outside this exact case')
    for label, value in (('package', package), ('jug', jug), ('eq', eq)):
        if hashlib.sha256(value).hexdigest() != parent[f'{label}_sha256']:
            raise ValueError(f'{label} parent hash differs from explicit input binding')


def _fixture_spec():
    season = ROOT / '.local/transfermarkt-opening-plans-current-v1/2005-06'
    def binding(path):
        return {'path': registry.relative_workspace_path(path), 'sha256': registry.sha256_file(path)}
    return dict(path='.local/transfermarkt-opening-plans-current-v1/2005-06/cache/report/37216.html',
        sha256=registry.sha256_file(season / 'cache/report/37216.html'),
        url='https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/37216',
        provider_club_id=714, competition='ES1', date='2005-08-28', season_start_year=2005,
        membership_mode='classic-played-substitutes', fixture_basis='recorded-first-league-fixture',
        first_league_capture=binding(season / 'opening-lineups-transfermarkt.json'),
        schedule_source={**binding(season / 'cache/schedule/2005/714.html'),
            'url':'https://www.transfermarkt.co.uk/espanyol-barcelona/spielplan/verein/714/saison_id/2005'})


def _fixture_and_xi():
    fixture = _fixture_spec()
    if (fixture['sha256'] != FIXTURE_SHA256
            or fixture['first_league_capture']['sha256'] != CAPTURE_SHA256
            or fixture['schedule_source']['sha256'] != SCHEDULE_SHA256):
        raise ValueError('first fixture evidence preimage differs from retained captures')
    exchange.verify_first_league_fixture(fixture)
    xi, bench = exchange.match_people(fixture)
    if len(xi) != 11 or len({p['source_player_id'] for p in xi}) != 11:
        raise ValueError('fixture does not provide exactly eleven distinct XI identities')
    return fixture, xi, bench


def _check_package_club(package):
    clubs = [c for c in package['clubs'] if c.get('carrier_id') == CLUB_CARRIER]
    if len(clubs) != 1 or clubs[0].get('id') != CLUB_ID or clubs[0].get('name') != 'Espanyol':
        raise ValueError('exact Espanyol recipe carrier8 identity required')
    return clubs[0]


def _native_preflight(release, package, jug, eq, parent):
    _verify_release(release, package, jug, eq, parent)
    club = _check_package_club(json.loads(package))
    index = IndexedFDIFile.from_bytes(eq)
    entries = [entry for entry in index.entries if entry.record_id == CLUB_CARRIER]
    if len(entries) != 1:
        raise ValueError('exact EQ club record8 required')
    entry = entries[0]
    raw = eq[entry.payload_offset:entry.payload_offset + entry.payload_length]
    roster = parse_eq_external_team_roster_payload(raw, {})
    rows = tuple((r.player_record_id, r.flag) for r in roster.rows) if roster else ()
    if roster is None or roster.mode_byte != 1 or rows != EXPECTED_ROWS:
        raise ValueError('exact 24-row Espanyol native ordered preimage required')
    owners = ownership.native_owners(eq)
    if owners.get(TARGET_PLAYER) != {4, 8} or owners.get(PRESERVED_FLAGGED) != {8}:
        raise ValueError('target/shared and retained-flagged carrier owner sets differ')
    jf = facts.native_facts(jug, PRESERVED_FLAGGED)
    if (jf['startup_order'] != 99 or jf['name'] != 'F. FRÉDSON'
            or jf['birth_date'] != '1981-02-22' or jf['position'] != 'M'):
        raise ValueError('exact preserved Frédson JUG identity/order differs')
    af = facts.native_facts(jug, TARGET_PLAYER)
    if (af['name'] != 'José Emilio AMAVISCA Gárate' or af['birth_date'] != '1971-06-19'
            or af['position'] != 'M' or af['startup_order'] != 24):
        raise ValueError('exact Amavisca native identity/preimage differs')
    return club, raw, roster, owners, jf


def _prepare_case(release, package, jug, eq, source_evidence, parent):
    """Validate complete exact preimage and return only a JSON-safe plan."""
    source_proof = verify_retirement_sources(source_evidence)
    club, raw, roster, owners_before, fr_before = _native_preflight(release, package, jug, eq, parent)
    fixture, xi, bench = _fixture_and_xi()
    pre_path = ROOT / '.local/transfermarkt-opening-plans-current-v1/2005-06/opening-squad-preallocation.json'
    if registry.sha256_file(pre_path) != PREALLOCATION_SHA256:
        raise ValueError('original XI preallocation preimage differs')
    pre = json.loads(pre_path.read_text())
    groups = [g for g in pre['source_clubs'] if g.get('selector', {}).get('club_name') == 'Espanyol']
    if len(groups) != 1 or not groups[0].get('opening_xi_complete'):
        raise ValueError('exact Espanyol source preallocation XI required')
    projected = sorted((p for p in groups[0]['players'] if type(p.get('opening_xi_order')) is int),
                       key=lambda p: p['opening_xi_order'])
    if ([str(p['opening_source_player_id']) for p in projected] != [p['source_player_id'] for p in xi]
            or [p['opening_xi_order'] for p in projected] != list(range(1, 12))):
        raise ValueError('source XI order does not reproduce retained first-fixture XI')
    actors = [p for p in json.loads(package)['players'] if p['club_id'] == CLUB_ID]
    by_person = {p['person_id']: p for p in actors}
    xi_carriers = []
    for source in projected:
        actor = by_person.get('person-source-' + source['source_row_sha256'])
        if (actor is None or actor['carrier_id'] == PRESERVED_FLAGGED
                or actor['facts']['birth_date'] != source['facts']['birth_date']
                or exchange.roster.normalise(actor.get('source_name') or actor['name'])
                    != exchange.roster.normalise(source['facts']['name'])):
            raise ValueError('source XI-to-recipe identity/DOB binding differs')
        xi_carriers.append(actor['carrier_id'])
    if len(set(xi_carriers)) != 11:
        raise ValueError('XI does not map one-to-one to native carriers')
    target_row = roster.rows[0]
    if (target_row.player_record_id != TARGET_PLAYER or target_row.flag != 0
            or ownership.native_owners(eq).get(TARGET_PLAYER) != {4, 8}):
        raise ValueError('exact target19 native row/ownership differs')
    orderable = [r.player_record_id for r in roster.rows if r.flag == 0 and r.player_record_id != TARGET_PLAYER]
    if len(orderable) != 22 or not set(xi_carriers) <= set(orderable):
        raise ValueError('post-unlink exact 22 flag-zero actors and complete XI required')
    owners_after_unlink = {pid: ids - ({8} if pid == TARGET_PLAYER else set())
                           for pid, ids in owners_before.items()}
    if any(owners_after_unlink.get(pid) != {8} for pid in orderable):
        raise ValueError('every orderable post-unlink actor must be exclusive to Espanyol8')
    jindex = {e.record_id: e for e in IndexedFDIFile.from_bytes(jug).entries}
    if any(read_initial_order(jindex[pid].decode_payload(jug)).family != 'dd6360' for pid in orderable):
        raise ValueError('orderable carrier has unsupported native order family')
    tail = sorted(set(orderable) - set(xi_carriers),
                  key=lambda pid: (facts.native_facts(jug, pid)['startup_order'], pid))
    ordered = xi_carriers + tail
    if len(ordered) != 22 or len(set(ordered)) != 22:
        raise ValueError('22-row order permutation is not unique')
    replacements = [dict(carrier_id=pid, name=facts.native_facts(jug, pid)['name'],
                         before=facts.native_facts(jug, pid)['startup_order'], after=n)
                    for n, pid in enumerate(ordered, 1)]
    return {
        'schema': 'pm99-amavisca-exact-case-transaction-v1', 'policy': POLICY,
        'season': release.season, 'release_id': release.release_id,
        'manifest_sha256': parent['manifest_sha256'],
        'package_sha256': parent['package_sha256'], 'jug_sha256': parent['jug_sha256'], 'eq_sha256': parent['eq_sha256'],
        'club_id': CLUB_ID, 'club_carrier_id': CLUB_CARRIER,
        'expected_rows': [list(row) for row in EXPECTED_ROWS],
        'target': {'carrier_id': TARGET_PLAYER, 'flag': 0, 'before_owners': [4, 8], 'after_owners': [4]},
        'preserved_flagged': {'carrier_id': PRESERVED_FLAGGED, 'flag': 1,
            'native_name': fr_before['name'], 'birth_date': fr_before['birth_date'],
            'position': fr_before['position'], 'startup_order': fr_before['startup_order']},
        'source_proof': source_proof,
        'fixture': {'date': fixture['date'], 'source_player_ids': [p['source_player_id'] for p in xi]},
        'preallocation_sha256': registry.sha256_file(pre_path),
        'xi_carriers': xi_carriers,
        'order_replacements': replacements,
        'retirement_policy': 'unlink-only-from-Espanyol; preserve carrier19 and Madrid recipe/native link unresolved',
        'native_scope': 'remove EQ8 row19 only; order 22 flag-zero EQ8-exclusive actors; leave row18788/JUG record untouched'
    }


def prune_exact_payload(raw, expected_rows):
    """Case-local pruner with hardbound ordered preimage and preserved flag."""
    roster = parse_eq_external_team_roster_payload(raw, {})
    actual = tuple((r.player_record_id, r.flag) for r in roster.rows) if roster else ()
    if actual != EXPECTED_ROWS or actual != tuple(expected_rows) or roster.mode_byte != 1:
        raise ValueError('exact Espanyol8 ordered EQ preimage differs')
    kept = [r for r in roster.rows if r.player_record_id != TARGET_PLAYER]
    first = roster.rows[0].raw_row_offset
    if (roster.rows[0].player_record_id != TARGET_PLAYER or roster.rows[0].flag != 0
            or roster.rows[-1].raw_row_offset + 5 != len(raw)
            or raw[first - 1] != len(roster.rows)
            or any(r.raw_row_offset != first + n * 5 for n, r in enumerate(roster.rows))):
        raise ValueError('exact count/target/terminal row preimage differs')
    if tuple((r.player_record_id, r.flag) for r in roster.rows if r.flag) != ((PRESERVED_FLAGGED, 1),):
        raise ValueError('only exact retained Frédson flag1 row is admitted')
    out = raw[:first - 1] + bytes([len(kept)]) + b''.join(
        raw[r.raw_row_offset:r.raw_row_offset + 5] for r in kept)
    check = parse_eq_external_team_roster_payload(out, {})
    if (check is None or tuple((r.player_record_id, r.flag) for r in check.rows)
            != tuple((r.player_record_id, r.flag) for r in kept)
            or out[:first - 1] != raw[:first - 1]
            or any(out[r.raw_row_offset:r.raw_row_offset + 5] != raw[old.raw_row_offset:old.raw_row_offset + 5]
                   for r, old in zip(check.rows, kept))):
        raise ValueError('exact retained row/prefix readback differs')
    return out


# Public case-adapter contract. Parent identity is read from the explicit input
# document on every call; parent identity and bytes are supplied by that input.
def _safe_input(input_path):
    path=Path(input_path)
    if not path.is_absolute(): path=ROOT/path
    path=path.resolve(strict=False)
    if not path.is_relative_to(ROOT.resolve()): raise ValueError('input path escapes workspace')
    path=path.resolve(strict=True)
    raw=path.read_bytes(); doc=json.loads(raw)
    if doc.get('schema')!=INPUT_SCHEMA: raise ValueError('wrong exact-case input schema')
    doc['_resolved_path']=path
    doc['_workspace_path']=path.relative_to(ROOT).as_posix()
    doc['_input_sha256']=hashlib.sha256(raw).hexdigest()
    return doc


def _source_bindings(doc, base):
    parent=doc.get('parent')
    required={'season','release_id','manifest_sha256','package_sha256','jug_sha256','eq_sha256'}
    if not isinstance(parent,dict) or set(parent)!=required or parent['season']!='2005-06':
        raise ValueError('input needs explicit exact parent identity and all four hashes')
    _verify_release(base,base.package_path.read_bytes(),(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(),(base.game_path/'DBDAT/EQ98030.FDI').read_bytes(),parent)
    expected_fixture={'report_path':'.local/transfermarkt-opening-plans-current-v1/2005-06/cache/report/37216.html',
        'url':'https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/37216','sha256':FIXTURE_SHA256,
        'capture_path':'.local/transfermarkt-opening-plans-current-v1/2005-06/opening-lineups-transfermarkt.json',
        'capture_sha256':CAPTURE_SHA256,'schedule_path':'.local/transfermarkt-opening-plans-current-v1/2005-06/cache/schedule/2005/714.html',
        'schedule_sha256':SCHEDULE_SHA256}
    if doc.get('fixture')!=expected_fixture: raise ValueError('fixture/capture/schedule source path, URL or digest differs')
    if doc.get('preallocation')!={'path':'.local/transfermarkt-opening-plans-current-v1/2005-06/opening-squad-preallocation.json','sha256':PREALLOCATION_SHA256}:
        raise ValueError('opening source preallocation path or digest differs')
    proof_results=[]
    for spec in doc.get('parent_proofs',[]):
        if set(spec)!={'path','sha256'}: raise ValueError('parent source proof must bind exact path and hash')
        p=(ROOT/spec['path']).resolve(strict=True)
        if not p.is_relative_to(ROOT.resolve()): raise ValueError('parent proof escapes workspace')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=spec['sha256']: raise ValueError('r194 source proof changed')
        proof_results.append((spec['path'],json.loads(raw)))
    by_path={path:data for path,data in proof_results}
    native=[data for _,data in proof_results if data.get('release_id')==parent['release_id'] and data.get('manifest_sha256')==parent['manifest_sha256']]
    if not native or any(not x.get('all_other_bytes_and_files_exact') or x.get('carriers')!=[28340] or x.get('changed_native_bytes')!=1 for x in native):
        raise ValueError('exact Danish-country parent proof does not match selected release')
    source_replay=[data for _,data in proof_results if data.get('complete_game_inventory_identical') is True and data.get('complete_recipe_identical') is True]
    if not source_replay: raise ValueError('complete SOURCE replay proof missing for parent')
    cplan=doc['country_preservation']; cp=by_path.get(cplan['country_plan_path'])
    country_update=next((x for x in cp.get('updates',[]) if x.get('carrier_id')==28340 and x.get('nationality')=='DEN'),None) if cp else None
    if country_update is None or country_update.get('native_mask',{}).get('file_offset')!=cplan['file_offset'] or country_update.get('native_mask',{}).get('after')!=cplan['postimage_byte']:
        raise ValueError('explicit carrier28340 Denmark country-plan proof missing')
    for key,spec in doc['retirement_sources'].items():
        source={k:spec[k] for k in ('path','sha256','url')}
        receipt=(ROOT/spec['receipt_path']).resolve(strict=True)
        if not receipt.is_relative_to(ROOT.resolve()): raise ValueError('retirement receipt escapes workspace')
        rb=receipt.read_bytes()
        if hashlib.sha256(rb).hexdigest()!=spec['receipt_sha256'] or json.loads(rb)!={'sha256':spec['sha256'],'url':spec['url']}:
            raise ValueError(f'{key} source receipt does not match exact retained original')
    return {'parent':parent,'parent_proofs':[{'path':s['path'],'sha256':s['sha256']} for s in doc['parent_proofs']],
        'retirement_sources':doc['retirement_sources'],'fixture':doc['fixture'],'preallocation':doc['preallocation'],
        'country_preservation':cplan,'input_path':doc['_workspace_path'],'input_sha256':doc['_input_sha256']}


def prepare(base,input_path):
    doc=_safe_input(input_path)
    bindings=_source_bindings(doc,base)
    package=base.package_path.read_bytes(); jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    evidence={k:{name:spec[name] for name in ('path','sha256','url')} for k,spec in doc['retirement_sources'].items()}
    plan=_prepare_case(base,package,jug,eq,evidence,bindings['parent'])
    pre_path=ROOT/doc['preallocation']['path']; pre= json.loads(pre_path.read_text(encoding='utf-8'))
    group=next(g for g in pre['source_clubs'] if g.get('selector',{}).get('club_name')=='Espanyol')
    projected=sorted((p for p in group['players'] if type(p.get('opening_xi_order')) is int),key=lambda p:p['opening_xi_order'])
    actors={p['carrier_id']:p for p in json.loads(package)['players'] if p.get('club_id')==CLUB_ID}
    plan['schema']=SCHEMA
    plan['input_path']=bindings['input_path'];plan['input_sha256']=bindings['input_sha256'];plan['parent']=bindings['parent'];plan['source_bindings']=bindings
    derived_xi=[{'opening_xi_order':n,'source_row_sha256':s['source_row_sha256'],'source_player_id':str(s['opening_source_player_id']),'carrier_id':cid,'full_name':actors[cid].get('source_name') or actors[cid]['name'],'birth_date':actors[cid]['facts']['birth_date']} for n,(s,cid) in enumerate(zip(projected,plan['xi_carriers']),1)]
    if doc.get('xi_bindings')!=derived_xi: raise ValueError('explicit input XI crosswalk does not rederive from source and current package')
    plan['xi_bindings']=derived_xi
    if len(plan['xi_bindings'])!=11: raise ValueError('complete ordered XI crosswalk required')
    plan['country_preservation']=bindings['country_preservation']
    plan['source_plan_artifact']=_source_plan_artifact(plan)
    candidate=_native_candidate(package,jug,eq,plan)
    plan['output_hashes']=[candidate['jug_sha256'],candidate['eq_sha256']]
    return plan


def verify(base,plan):
    if plan.get('schema')!=SCHEMA: raise ValueError('exact r194 v4 plan required')
    if prepare(base,plan['input_path'])!=plan: raise ValueError('saved plan/input/source bindings changed')
    return True


def reconstruct_source(base,source_plan_document):
    if not isinstance(source_plan_document,dict) or source_plan_document.get('schema')!='pm99-amavisca-source-opening-xi-plan-r194-v4':
        raise ValueError('unsupported Amavisca SOURCE replay artifact')
    plan=prepare(base,source_plan_document['input_path'])
    if plan['source_plan_artifact']['document']!=source_plan_document:
        raise ValueError('Amavisca SOURCE replay artifact does not rederive from bound originals')
    return plan


def bind(package,plan):
    if not isinstance(package,dict) or packages.sha256_bytes(packages.canonical_json_bytes(package))!=plan['parent']['package_sha256']:
        raise ValueError('exact parent recipe package required')
    out=json.loads(json.dumps(package,ensure_ascii=False))
    club=next((c for c in out['clubs'] if c.get('carrier_id')==CLUB_CARRIER),None)
    madrid=next((c for c in out['clubs'] if c.get('carrier_id')==4 and c.get('id')=='club-4'),None)
    target=next((p for p in out['players'] if p.get('carrier_id')==TARGET_PLAYER),None)
    if club is None or madrid is None or target is None or club!=_check_package_club(out): raise ValueError('exact club/player recipe preimage required')
    target_id=target['id']
    if target_id not in madrid['roster_player_ids'] or target_id not in club['roster_player_ids']:
        raise ValueError('Amavisca must retain Madrid link while removing only Espanyol link')
    club['roster_player_ids']=[pid for pid in club['roster_player_ids'] if pid!=target_id]
    if 'shared_preserve_player_ids' in club:
        club['shared_preserve_player_ids']=[pid for pid in club['shared_preserve_player_ids'] if pid!=target_id]
    target['club_id']='club-4'
    den=next((p for p in out['players'] if p.get('carrier_id')==28340),None)
    if den is None or den.get('facts',{}).get('nationality')!='DEN': raise ValueError('r194 Denmark fact lost in recipe binding')
    source_artifact=plan['source_plan_artifact']
    if (source_artifact.get('filename')!=SOURCE_PLAN_FILENAME
            or packages.sha256_bytes(packages.canonical_json_bytes(source_artifact['document']))!=source_artifact.get('sha256')
            or source_artifact.get('artifact_id')!=SOURCE_PLAN_ARTIFACT_ID):
        raise ValueError('exact source-plan artifact binding is invalid')
    artifact_id=SOURCE_PLAN_ARTIFACT_ID
    proof={'id':artifact_id,'kind':'season-input','media_type':'application/json',
        'relative_path':source_artifact['filename'],'sha256':source_artifact['sha256']}
    out.setdefault('artifacts',[])[:]=[a for a in out['artifacts'] if a.get('id')!=artifact_id]+[proof]
    out.setdefault('sources',[])[:]=[s for s in out['sources'] if s.get('id')!='amavisca-opening-xi-source-r194-v4']+[
        {'id':'amavisca-opening-xi-source-r194-v4','title':'Hash-bound Amavisca opening XI and carrier order mapping',
         'proof_grade':'source-captured','evidence_artifact_id':artifact_id}]
    out.setdefault('proofs',[])[:]=[p for p in out['proofs'] if p.get('id')!='amavisca-opening-xi-source-proof-r194-v4']+[
        {'id':'amavisca-opening-xi-source-proof-r194-v4','grade':'source-captured','artifact_id':artifact_id,
         'covers':['ordered opening XI source-row identity, DOB, native carrier, and proposed startup order']}]
    from scripts.season_package_v2 import validate_package
    out['artifacts'].sort(key=lambda a:a['id']);out['sources'].sort(key=lambda s:s['id']);out['proofs'].sort(key=lambda p:p['id'])
    validate_package(out,strict=False)
    return out


def _native_candidate(package,jug,eq,plan):
    package_obj=json.loads(package) if isinstance(package,(bytes,bytearray)) else package
    recipe=bind(package_obj,plan)
    index=IndexedFDIFile.from_bytes(eq);entry=next(e for e in index.entries if e.record_id==CLUB_CARRIER)
    payload=eq[entry.payload_offset:entry.payload_offset+entry.payload_length]
    pruned=prune_exact_payload(payload,tuple(map(tuple,plan['expected_rows'])))
    candidate_eq=compiler._rebuild_indexed(eq,index,{CLUB_CARRIER:compiler.xor_decode(pruned)})
    from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
    preserve_other_records(eq,candidate_eq,{CLUB_CARRIER})
    repl=[OrderReplacement(x['carrier_id'],x['name'],x['before'],x['after']) for x in plan['order_replacements']]
    candidate_jug=patch_initial_orders(jug,repl,allow_compact=True)
    preserve_other_records(jug,candidate_jug,{r.record_id for r in repl})
    before={e.record_id:e.decode_payload(jug) for e in IndexedFDIFile.from_bytes(jug).entries}
    after={e.record_id:e.decode_payload(candidate_jug) for e in IndexedFDIFile.from_bytes(candidate_jug).entries}
    if before[PRESERVED_FLAGGED]!=after[PRESERVED_FLAGGED]: raise ValueError('Frédson complete JUG payload changed')
    c=plan['country_preservation']; cid=c['carrier_id']
    if jug[c['file_offset']]!=c['postimage_byte'] or candidate_jug[c['file_offset']]!=c['postimage_byte']:
        raise ValueError('r194 Danish country byte was not preserved')
    owners=ownership.native_owners(candidate_eq)
    if owners.get(TARGET_PLAYER)!={4} or owners.get(PRESERVED_FLAGGED)!={8}: raise ValueError('native owner postcondition differs')
    return {'package':recipe,'jug':candidate_jug,'eq':candidate_eq,'jug_sha256':hashlib.sha256(candidate_jug).hexdigest(),'eq_sha256':hashlib.sha256(candidate_eq).hexdigest()}


def apply(jug,eq,plan):
    base=registry.load_registered_release(plan['season'],plan['parent']['release_id'])
    verify(base,plan)
    package=base.package_path.read_bytes();parent_jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();parent_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    incoming=(hashlib.sha256(jug).hexdigest(),hashlib.sha256(eq).hexdigest())
    before=(plan['parent']['jug_sha256'],plan['parent']['eq_sha256']);after=tuple(plan['output_hashes'])
    if incoming not in (before,after): raise ValueError('only complete exact parent or complete exact post-pair is accepted')
    candidate=_native_candidate(package,parent_jug,parent_eq,plan)
    if incoming==after:
        if bytes(jug)!=candidate['jug'] or bytes(eq)!=candidate['eq']: raise ValueError('post-pair bytes differ from fresh replay')
        return bytes(jug),bytes(eq)
    if incoming==before: return candidate['jug'],candidate['eq']
    raise ValueError('native pair mismatch')


def filename(plan):
    if plan.get('schema')!=SCHEMA: raise ValueError('unsupported Amavisca plan schema')
    return FILENAME


def artifact_id(plan):
    if plan.get('schema')!=SCHEMA: raise ValueError('unsupported Amavisca plan schema')
    return SOURCE_PLAN_ARTIFACT_ID


def _source_plan_artifact(plan):
    keys=('policy','season','release_id','manifest_sha256','package_sha256','jug_sha256','eq_sha256',
          'input_path','input_sha256','parent','source_bindings','source_proof','fixture','preallocation_sha256',
          'xi_bindings','xi_carriers','target','preserved_flagged','expected_rows','order_replacements',
          'retirement_policy','native_scope','country_preservation')
    document={'schema':'pm99-amavisca-source-opening-xi-plan-r194-v4',**{k:plan[k] for k in keys if k in plan}}
    raw=packages.canonical_json_bytes(document)
    return {'filename':SOURCE_PLAN_FILENAME,'artifact_id':SOURCE_PLAN_ARTIFACT_ID,
            'sha256':hashlib.sha256(raw).hexdigest(),'document':document}


def reconstruction(previous, release_id):
    from scripts import season_pipeline_v2 as pipeline
    receipt = pipeline.read_json_file(previous.compiler_receipt_path)
    if receipt.get('compilation_mode') != MODE:
        return None
    path = ROOT / previous.locator['sourced_profile_assignment_plan_path']
    plan = pipeline.read_json_file(path)
    base = registry.load_registered_release(previous.season, plan['parent']['release_id'])
    verify(base, plan)
    source_path = previous.package_path.parent / SOURCE_PLAN_FILENAME
    if registry.sha256_file(source_path) != plan['source_plan_artifact']['sha256']:
        raise ValueError('Amavisca retained SOURCE artifact changed')
    if reconstruct_source(base, pipeline.read_json_file(source_path)) != plan:
        raise ValueError('Amavisca retained SOURCE artifact does not reconstruct its plan')
    if bind(pipeline.read_json_file(base.package_path), plan) != pipeline.read_json_file(previous.package_path):
        raise ValueError('edited Amavisca recipe cannot silently reconstruct an older release')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season, previous.package_path.parent / 'role-delta-input.json',
        release_id=release_id, source_release_id=base.release_id, profile_assignment_plan_path=path)
    rebuilt = registry.load_registered_release(previous.season, release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes() != previous.package_path.read_bytes():
        raise ValueError('Amavisca complete recipe SOURCE replay differs')
    if not registry.validate_preferred_release(previous.season, level='playable', release_id=release_id)['valid']:
        raise ValueError('Amavisca SOURCE replay failed registered playable gate')
    return dict(season=previous.season, release_id=release_id,
        complete_game_inventory_identical=True, complete_recipe_identical=True,
        clean_machine_parent_reconstruction=False, compilation_mode=MODE)
