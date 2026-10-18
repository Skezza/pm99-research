"""Source-bound Preetz country and incompatible profile-role repair.

Two faulty dd6360 carriers only. The third scoped season already has Germany
and forward-compatible roles and is deliberately not rewritten. No FIFA claim.
"""
import copy
from datetime import date
import hashlib
from pathlib import Path
import re

from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_nationality import rewrite_indexed_native_nationalities
from app.indexed_jug_roles import rewrite_indexed_native_primary_roles
from scripts import season_original_country_policy_v2 as countries
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_order_repair_v1 as ownership
from scripts.build_original_carrier_label_20261017 import external

pipeline,registry,packages=countries.pipeline,countries.registry,countries.packages
SCHEMA='pm99-original-DFB-Hertha-Preetz-period-country-profile-v1'
MODE='known-good-baseline-original-Preetz-period-country-profile-v1'
PREFIX='sourced-preetz-period-profile-'
FILENAME='sourced-preetz-period-profile.json'
TARGETS={'2000-01':12468,'2001-02':12468}


def digest(raw):return hashlib.sha256(raw).hexdigest()
def filename(plan):return FILENAME


def parse_sources(dfb,hertha):
    dfb=' '.join(BeautifulSoup(dfb,'html.parser').get_text(' ',strip=True).split())
    hertha=' '.join(BeautifulSoup(hertha,'html.parser').get_text(' ',strip=True).split())
    if not re.search(r'Name:\s*Michael Preetz\s+Date of birth:\s*1967-08-17\s+Nation:\s*Germany',dfb):
        raise ValueError('official DFB exact full name/birthday/nation identity absent')
    if (not re.search(r'Stürmer zum besten Torjäger der Saison 1998/99',hertha)
            or not re.search(r'Michael Preetz wurde zum Nationalspieler und nahm am FIFA Confederations Cup 1999',hertha)
            or not re.search(r'Als Kapitän der Blau-Weißen zeigte er zwischen 2000 und 2003',hertha)):
        raise ValueError('official Hertha dated playing role, 1999 national career or 2000-2003 continuity absent')
    return dict(full_name='Michael Preetz',birth_date='1967-08-17',nationality='GER',
        period_country='DFB Germany identity corroborated by Hertha 1999 international career',
        historical_broad_role='F',fine_role_decision='Central Striker (12) is the explicit standard editorial mapping of sourced striker, not a claim to every historical secondary role',
        coverage='2000-01 and 2001-02; country and incompatible first profile role only; not an opening-XI or global roster approval')


def originals():
    result={}
    for key,url in (
        ('preetz-original-dfb-player-profile','https://datencenter.dfb.de/en/data-center/people/michael-preetz/player'),
        ('preetz-original-hertha-dated-playing-career','https://www.herthabsc.com/de/nachrichten/2018/08/14908-herzlichen-gluckwunsch-michael-preetz')):
        binding=external(key)
        metadata=pipeline.read_json_file(registry.ROOT/binding['source_receipt_path'])
        if binding['url']!=url or metadata.get('sha256')!=binding['sha256']:
            raise ValueError('original source URL/content receipt differs')
        result[key]=binding
    raw=[(registry.ROOT/b['path']).read_bytes() for b in result.values()]
    return result,parse_sources(*raw)


def prepare(base):
    if base.season not in TARGETS:raise ValueError('no confirmed faulty Preetz target in this season')
    sources,decision=originals()
    package=pipeline.read_json_file(base.package_path);carrier=TARGETS[base.season]
    matches=[p for p in package['players'] if p['carrier_id']==carrier]
    if len(matches)!=1:raise ValueError('unique recipe actor required')
    player=matches[0];club=next(c for c in package['clubs'] if c['id']==player['club_id'])
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes();eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    entries=[e for e in IndexedFDIFile.from_bytes(jug).entries if e.record_id==carrier]
    if len(entries)!=1:raise ValueError('unique actual native actor required')
    payload=entries[0].decode_payload(jug);native=roster.native_player(payload,carrier);end=native['name_end']
    birth=date(int.from_bytes(bytes(v^0x61 for v in payload[end+14:end+16]),'little'),payload[end+13]^0x61,payload[end+12]^0x61).isoformat()
    codes=countries.compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    code,label=countries.native_country('GER',codes)
    if (player.get('source_name')!='Michael Preetz' or player['facts']['birth_date']!=decision['birth_date']
            or birth!=decision['birth_date'] or roster.normalise(player['name'])!='mpreetz'
            or roster.normalise(native['name'])!=roster.normalise(player['name'])
            or club['carrier_id']!=421 or ownership.native_owners(eq).get(carrier)!={421}
            or native['family']!='dd6360' or native['position']!='F' or player['facts']['primary_position']!='F'
            or native['roles']!=[9,98,98,98,98,98] or payload[end+8]^0x61!=codes['NORWAY']):
        raise ValueError('exact sourced Preetz name/date/exclusive ownership/faulty native preimage differs')
    return dict(schema=SCHEMA,season=base.season,release_id=base.release_id,carrier_id=carrier,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=digest(jug),eq_sha256=digest(eq),
        before_player=player,before_native=native,before_country_code=codes['NORWAY'],
        nationality='GER',native_country_code=code,native_label=label,fine_roles=[12],
        original_sources=sources,source_decision=decision,
        implementation_inputs=[dict(path=registry.relative_workspace_path(p),sha256=registry.sha256_file(p))
            for p in (Path(__file__),Path(countries.__file__))],
        scope='Exactly two native bytes: Norway country to Germany; incompatible first fine-role 9 to standard editorial striker12. All other five role bytes, broad position, identities, dates, ten skills, orders, ownership, tactics, club names, managers, kits, portraits, EXE and other seasons preserved. The sourced striker mapping is editorial, not FIFA or full secondary-role certification.')


def verify(base,plan):
    if plan.get('schema')!=SCHEMA or prepare(base)!=plan:raise ValueError('Preetz source/native plan did not reproduce')


def bind(package,plan):
    if plan.get('schema')!=SCHEMA or digest(packages.canonical_json_bytes(package))!=plan['package_sha256']:
        raise ValueError('Preetz recipe preimage differs')
    result=copy.deepcopy(package);p=next(p for p in result['players'] if p['carrier_id']==plan['carrier_id'])
    if p!=plan['before_player']:raise ValueError('Preetz person preimage differs')
    p['facts'].update(nationality='GER',fine_roles=[12])
    p['fact_fallbacks']=[f for f in p.get('fact_fallbacks',[]) if f['field'] not in ('nationality','fine_roles')]
    result['artifacts'].append(dict(id=PREFIX+plan['season'],kind='season-input',relative_path=FILENAME,
        sha256=digest(packages.canonical_json_bytes(plan)),media_type='application/json'))
    result['artifacts'].sort(key=lambda a:a['id']);packages.validate_package(result)
    return result


def apply(jug,eq,plan):
    if plan.get('schema')!=SCHEMA:raise ValueError('Preetz native schema differs')
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    if digest(before)!=plan['jug_sha256'] or digest(eq)!=plan['eq_sha256']:raise ValueError('Preetz whole native preimage differs')
    verify(base,plan)
    patched,_=rewrite_indexed_native_primary_roles(before,{plan['carrier_id']:(9,12)})
    after,_=rewrite_indexed_native_nationalities(patched,{plan['carrier_id']:plan['native_country_code']})
    entry=next(e for e in IndexedFDIFile.from_bytes(before).entries if e.record_id==plan['carrier_id'])
    allowed={entry.payload_offset+plan['before_native']['name_end']+offset for offset in (2,8)}
    if len(before)!=len(after) or {i for i,(a,b) in enumerate(zip(before,after)) if a!=b}!=allowed:
        raise ValueError('Preetz correction is not exactly the two declared bytes')
    if jug not in (before,after):raise ValueError('Preetz input neither complete preimage nor postimage')
    return after,eq


def reconstruction(previous,release_id):
    receipt=getattr(previous,'compiler_receipt_path',None)
    if receipt is None or pipeline.read_json_file(receipt).get('compilation_mode')!=MODE:return None
    path=registry.ROOT/previous.locator['sourced_profile_assignment_plan_path'];plan=pipeline.read_json_file(path)
    base=registry.load_registered_release(previous.season,plan['release_id']);verify(base,plan)
    package=pipeline.read_json_file(previous.package_path)
    artifact=next(a for a in package['artifacts'] if a['id']==PREFIX+previous.season)
    if (path.resolve()!=(previous.package_path.parent/FILENAME).resolve() or registry.sha256_file(path)!=artifact['sha256']
            or bind(pipeline.read_json_file(base.package_path),plan)!=package):raise ValueError('Preetz SOURCE would discard edited recipe')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['package_sha256'],jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('Preetz SOURCE descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():raise ValueError('Preetz complete SOURCE recipe differs')
    return dict(season=previous.season,complete_game_inventory_identical=True,complete_recipe_identical=True,compilation_mode=MODE)
