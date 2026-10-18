"""Exact period-country/keeper-role correction, not an ownership approval.

Eight source-scoped faulty records only. Four already have the correct keeper
role. Nine other scoped records have correct facts and must not be rebuilt.
"""
import copy
from datetime import date
import hashlib
from pathlib import Path
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_nationality import rewrite_indexed_native_nationalities
from app.indexed_jug_roles import rewrite_indexed_native_roles
from scripts import season_original_country_policy_v2 as countries
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_order_repair_v1 as ownership
from scripts.build_original_carrier_label_20261017 import external

pipeline,registry,packages=countries.pipeline,countries.registry,countries.packages
SCHEMA='pm99-original-Kiraly-1998-2016-Hungary-and-goalkeeper-profile-v1'
MODE='known-good-baseline-original-Kiraly-period-country-keeper-profile-v1'
PREFIX='sourced-kiraly-period-profile-'
FILENAME='sourced-kiraly-period-profile.json'
TARGETS={'2000-01':2211,'2001-02':2211,'2002-03':2211,'2003-04':2211,
    '2004-05':8492,'2005-06':9683,'2006-07':9709,'2007-08':9475}


def digest(raw):return hashlib.sha256(raw).hexdigest()
def filename(plan):return FILENAME


def parse_source(raw):
    page=BeautifulSoup(raw,'html.parser')
    if [h.get_text(' ',strip=True) for h in page.select('h1')]!=['Gábor Király']:
        raise ValueError('original nationality article identifies another person')
    boxes=[b for b in page.select('table.infobox') if b.select('.bday')]
    if len(boxes)!=1 or [b.get_text(strip=True) for b in boxes[0].select('.bday')]!=['1976-04-01']:
        raise ValueError('one literal full-name/birthday identity required')
    positions=[];international=False;rows=[]
    for tr in boxes[0].select('tr'):
        cells=tr.find_all(['th','td'],recursive=False)
        if len(cells)>=2 and cells[0].get_text(' ',strip=True)=='Position':
            positions.append(cells[1].get_text(' ',strip=True))
        headings=tr.select('th.infobox-header')
        if headings:
            international=headings[0].get_text(' ',strip=True)=='International career'
            continue
        if international and len(cells)>=2:
            rows.append([cells[0].get_text(' ',strip=True),cells[1].get_text(' ',strip=True)])
    if positions!=['Goalkeeper'] or rows!=[['1993–1994','Hungary U18'],['1996–1997','Hungary U21'],['1998–2016','Hungary']]:
        raise ValueError('literal original goalkeeper or complete dated Hungary international chronology differs')
    return dict(name='Gábor Király',birth_date='1976-04-01',nationality='HUN',position='G',
        national_representation=dict(from_year=1998,to_year=2016,country='Hungary'),
        first_keeper_role=0,role_grade='standard-editorial-native-goalkeeper-mapping-of-literal-career-role',
        current_citizenship_birthplace_club_country_used=False,opening_ownership_approved=False)


def original():
    binding=external('haladas2000-kiraly-retained-original-career')
    receipt=pipeline.read_json_file(registry.ROOT/binding['source_receipt_path'])
    if binding['url']!='https://en.wikipedia.org/wiki/G%C3%A1bor_Kir%C3%A1ly' or receipt.get('sha256')!=binding['sha256']:
        raise ValueError('original full biography URL/content receipt differs')
    return binding,parse_source((registry.ROOT/binding['path']).read_bytes())


def prepare(base):
    if base.season not in TARGETS:raise ValueError('season has no confirmed faulty scoped Kiraly actor')
    binding,decision=original();year=int(base.season[:4])
    if not decision['national_representation']['from_year']<year<decision['national_representation']['to_year']:
        raise ValueError('target year not inside explicit sourced national representation')
    package=pipeline.read_json_file(base.package_path);carrier=TARGETS[base.season]
    matches=[p for p in package['players'] if p['carrier_id']==carrier]
    if len(matches)!=1:raise ValueError('one actual source-authored recipe actor required')
    player=matches[0];club=next(c for c in package['clubs'] if c['id']==player['club_id'])
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    entries=[e for e in IndexedFDIFile.from_bytes(jug).entries if e.record_id==carrier]
    if len(entries)!=1:raise ValueError('one actual native actor required')
    payload=entries[0].decode_payload(jug);native=roster.native_player(payload,carrier);end=native['name_end']
    birthday=date(int.from_bytes(bytes(v^0x61 for v in payload[end+14:end+16]),'little'),payload[end+13]^0x61,payload[end+12]^0x61).isoformat()
    codes=countries.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    expected_country='GERMANY' if year<=2003 else 'ENGLAND'
    before_roles=[12,8,98,98,98,98] if year<=2003 else [0,98,98,98,98,98]
    code,label=countries.native_country('HUN',codes)
    if (player.get('policy')=='preserve-existing-mode1' or roster.normalise(player.get('source_name') or player['name'])!='gaborkiraly'
            or player['facts']['birth_date']!=decision['birth_date'] or birthday!=decision['birth_date']
            or roster.normalise(native['name'])!=roster.normalise(player['name'])
            or ownership.native_owners(eq).get(carrier)!={club['carrier_id']}
            or native['position']!='G' or player['facts']['primary_position']!='G'
            or native['roles']!=before_roles or payload[end+8]^0x61!=codes[expected_country]):
        raise ValueError('exact Kiraly identity/birthday/owner/keeper/country-role preimage differs')
    return dict(schema=SCHEMA,season=base.season,release_id=base.release_id,carrier_id=carrier,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=digest(jug),eq_sha256=digest(eq),
        before_player=player,before_native=native,before_country=expected_country,
        nationality='HUN',native_country_code=code,native_label=label,fine_roles=[0],
        original=binding,source_decision=decision,
        expected_native_byte_changes=3 if year<=2003 else 1,
        implementation_inputs=[dict(path=registry.relative_workspace_path(Path(p)),sha256=registry.sha256_file(Path(p)))
            for p in (__file__,countries.__file__)],
        scope='Only exact original-name/DOB-matched Kiraly country byte and, in2000-2003 only, incompatible inherited striker fine roles. Standard editorial GK0 from literal sourced goalkeeper. Names, dates, ten skills, broadG, orders, ownership, tactics, clubs, managers, photos, kits and EXE unchanged. Not historical opening-owner or squad approval; duplicates stay separate cases.')


def verify(base,plan):
    if plan.get('schema')!=SCHEMA or prepare(base)!=plan:raise ValueError('Kiraly original source/native plan differs')


def bind(package,plan):
    if plan.get('schema')!=SCHEMA or digest(packages.canonical_json_bytes(package))!=plan['package_sha256']:
        raise ValueError('Kiraly whole recipe preimage differs')
    result=copy.deepcopy(package);p=next(p for p in result['players'] if p['carrier_id']==plan['carrier_id'])
    if p!=plan['before_player']:raise ValueError('Kiraly actor preimage differs')
    p['facts'].update(nationality='HUN',fine_roles=[0])
    p['fact_fallbacks']=[f for f in p.get('fact_fallbacks',[]) if f['field'] not in ('nationality','fine_roles')]
    result['artifacts'].append(dict(id=PREFIX+plan['season'],kind='season-input',relative_path=FILENAME,
        sha256=digest(packages.canonical_json_bytes(plan)),media_type='application/json'))
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    if plan.get('schema')!=SCHEMA:raise ValueError('Kiraly schema differs')
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify(base,plan)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    if digest(before)!=plan['jug_sha256'] or digest(eq)!=plan['eq_sha256']:raise ValueError('Kiraly whole native preimage differs')
    after,_=rewrite_indexed_native_nationalities(before,{plan['carrier_id']:plan['native_country_code']})
    if plan['before_native']['roles'][0]!=0:after,_=rewrite_indexed_native_roles(after,{plan['carrier_id']:[0]})
    entry=next(e for e in IndexedFDIFile.from_bytes(before).entries if e.record_id==plan['carrier_id'])
    offsets=(2,3,8) if plan['expected_native_byte_changes']==3 else (8,)
    allowed={entry.payload_offset+plan['before_native']['name_end']+offset for offset in offsets}
    if len(before)!=len(after) or {i for i,(a,b) in enumerate(zip(before,after)) if a!=b}!=allowed:
        raise ValueError('Kiraly correction changed bytes outside exact country/keeper-role fields')
    if jug not in (before,after):raise ValueError('Kiraly input neither complete preimage nor postimage')
    return after,eq


def reconstruction(previous,release_id):
    receipt=getattr(previous,'compiler_receipt_path',None)
    if receipt is None or pipeline.read_json_file(receipt).get('compilation_mode')!=MODE:return None
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    package=pipeline.read_json_file(previous.package_path);artifact=next(a for a in package['artifacts'] if a['id']==PREFIX+previous.season)
    if (path.resolve()!=(previous.package_path.parent/FILENAME).resolve() or registry.sha256_file(path)!=artifact['sha256']
            or bind(pipeline.read_json_file(base.package_path),plan)!=package):raise ValueError('Kiraly SOURCE would discard recipe edits')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('Kiraly SOURCE descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():raise ValueError('Kiraly complete SOURCE recipe differs')
    return dict(season=previous.season,complete_game_inventory_identical=True,complete_recipe_identical=True,compilation_mode=MODE)
