"""Source-bound Coady period-role exchange; prepare/bind/apply only.

The official Wolves period history resolves the annual broad-M conflict for the
2018/19 window. This adapter changes only Coady's broad D/fine CB profile fields.
It is not a publisher and never writes game-native input files.
"""
from __future__ import annotations
import copy, csv, hashlib, json
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from app.fdi_indexed import IndexedFDIFile
from scripts import season_exact_primary_position_delta_v2 as native_writer
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_opening_order_repair_v1 as owners
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry

ROOT=registry.ROOT
CAPTURE_DIR=ROOT/'.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/coady-centerback-correction-v1'
RECEIPT=CAPTURE_DIR/'capture_receipt.json'
SCHEMA='pm99-source-bound-wolves-coady-period-centreback-v1'
MODE='known-good-baseline-source-bound-wolves-coady-period-centreback-v1'
PREFIX='source-bound-wolves-coady-period-centreback-v1-'
TARGET=9896
SOURCES={
 'annual':('.local/external-sources/cache.footballsquads/eng/2018-2019/engprem/wolves.txt','60d7e222a677af8576a262e5b248d80fa007f2c72ba4290bd487f69f7bf0d002'),
 'fifa19':('.local/season-2015-16/fifa19-sofifa-backfill.csv','cd037495104afe0649e8d99d8b884d2589b0e621dc6a9932a65398621d094350'),
 'wolves_2019':('.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/coady-centerback-correction-v1/source-captures/wolves-20190215-coady-defence.html','f45a950b3d787eaa2dbd62ed578cbe201395a0ae8b9f204f39c85db9d1f01f31'),
 'wolves_2022':('.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/coady-centerback-correction-v1/source-captures/wolves-20220207-coady-three-defence.html','f8e6c5f6ddaec87701b35bb45c2227f976435df09338b67470d1be7882eb95f5'),
 'opener':('.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/coady-centerback-correction-v1/source-captures/skysports-wolves-everton-20180811.html','83d8d0070fb7ce4b53915a45496fdd1a0b1f41625abeeac84ddc8e4af7d32fd7'),
}
URLS={
 'wolves_2019':'https://www.wolves.co.uk/news/mens-first-team/20190215-coady-and-doherty-commit-futures-to-wolves/',
 'wolves_2022':'https://www.wolves.co.uk/news/features/20220207-300-club-conor-coady/',
 'opener':'https://www.skysports.com/football/wolverhampton-wanderers-vs-everton/teams/390766',
}

def _sha(b): return hashlib.sha256(b).hexdigest()
def _file_sha(path): return _sha(Path(path).read_bytes())
def _canon(value): return packages.canonical_json_bytes(value)
def _digest(value): return _sha(_canon(value))
class _Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self,data):
        if data.strip():self.parts.append(data.strip())
def _html(path):
    parser=_Text(); parser.feed(path.read_text(encoding='utf-8',errors='replace'))
    return ' '.join(parser.parts).lower()
def _load_bound_sources():
    paths={k:ROOT/v[0] for k,v in SOURCES.items()}
    for k,p in paths.items():
        if _file_sha(p)!=SOURCES[k][1]:raise ValueError(f'Coady {k} source body SHA changed')
    receipt=json.loads(RECEIPT.read_text(encoding='utf-8'))
    if receipt.get('schema')!='pm99-coady-source-capture-receipt-v1':raise ValueError('Coady source capture receipt schema differs')
    receipt_sources={x.get('path'):x for x in receipt.get('sources',[])}
    for k in ('wolves_2019','wolves_2022','opener'):
        rel='source-captures/'+paths[k].name; row=receipt_sources.get(rel)
        if not row or row.get('sha256')!=SOURCES[k][1] or row.get('url')!=URLS[k] or row.get('http_status')!=200:
            raise ValueError(f'Coady {k} source receipt is missing or does not bind body')
    annual_lines=paths['annual'].read_text(encoding='utf-8').splitlines()
    annual_matches=[(n,line) for n,line in enumerate(annual_lines,1) if 'Conor Coady' in line]
    expected_annual='16, Conor Coady, ENG, M, 1.85, 75, 25-02-93, Liverpool, Huddersfield T'
    if annual_matches!=[(12,expected_annual)]:raise ValueError('Coady annual M conflict source row changed')
    with paths['fifa19'].open(newline='',encoding='utf-8-sig') as stream:
        fifa_rows=[x for x in csv.DictReader(stream) if x.get('sofifa_id')=='202048']
    if len(fifa_rows)!=1:raise ValueError('Coady FIFA19 ID missing or ambiguous')
    fifa=fifa_rows[0]
    expected={'long_name':'Conor  Coady','dob':'1993-02-25','nationality':'England','club':'Wolverhampton Wanderers','player_positions':'CB','team_position':'CB','team_jersey_number':'16'}
    if any(fifa.get(k)!=v for k,v in expected.items()):raise ValueError('Coady FIFA19 exact identity/role row differs')
    txt19=_html(paths['wolves_2019'])
    if not all(x in txt19 for x in ('after performing in midfield during his opening two campaigns','transformed into the linchpin of the defence since nuno espirito santo','part of the back three')):
        raise ValueError('official Wolves 2019 period-specific defensive claim missing')
    txt22=_html(paths['wolves_2022'])
    if 'moved to the centre of a three-man defence for wolves from the 2017/18 season onwards' not in txt22:
        raise ValueError('official Wolves 2017/18 role history missing')
    opener=_html(paths['opener'])
    if '11th august 2018' not in opener or 'c coady' not in opener:raise ValueError('dated opener lineup source missing')
    return paths,fifa,expected_annual

def filename(plan):
    _require_plan_header(plan)
    return f'coady-period-centreback-{plan["transaction_id"]}.json'
def artifact_id(plan):
    _require_plan_header(plan)
    return PREFIX+plan['transaction_id']
def _require_plan_header(plan):
    if not isinstance(plan,dict) or plan.get('schema')!=SCHEMA or plan.get('mode')!=MODE:
        raise ValueError('Coady exchange schema/mode differs')

def prepare(base):
    if getattr(base,'season',None)!='2018-19' or not getattr(base,'release_id',None):
        raise ValueError('Coady role adapter requires a registered 2018-19 parent')
    registered=registry.load_registered_release(base.season,base.release_id)
    if (Path(base.package_path).resolve()!=Path(registered.package_path).resolve()
        or Path(base.game_path).resolve()!=Path(registered.game_path).resolve()
        or base.manifest_sha256!=registered.manifest_sha256):
        raise ValueError('Coady parent is not the exact registered release')
    paths,fifa,annual_line=_load_bound_sources()
    package=pipeline.read_json_file(base.package_path)
    actors=[p for p in package['players'] if p.get('carrier_id')==TARGET]
    if len(actors)!=1:raise ValueError('Coady carrier9896 missing/ambiguous')
    player=actors[0]
    clubs={c['id']:c for c in package['clubs']}
    if (player.get('name')!='Conor Coady' or player.get('source_name')!='Conor Coady'
        or player.get('facts',{}).get('birth_date')!='1993-02-25'
        or player['facts'].get('primary_position')!='M' or player['facts'].get('fine_roles')!=[9]
        or clubs[player['club_id']].get('carrier_id')!=333):
        raise ValueError('Coady exact semantic package preimage/Wolves owner differs')
    club=clubs[player['club_id']]
    opening=club.get('opening',{})
    if (opening.get('fixture_date')!='2018-08-11' or opening.get('formation')!='3-4-3'
        or player['id'] not in opening.get('starting_xi_player_ids',[])):
        raise ValueError('Coady dated opening-XI/formation package context differs')
    slots=[x for x in opening.get('tactics_context',{}).get('slots',[]) if x.get('player_id')==player['id']]
    if len(slots)!=1 or slots[0].get('role')!='LCB':
        raise ValueError('Coady opening tactical centre-back context differs')
    jug_path=Path(base.game_path)/'DBDAT/JUG98030.FDI'; eq_path=Path(base.game_path)/'DBDAT/EQ98030.FDI'
    jug,eq=jug_path.read_bytes(),eq_path.read_bytes()
    if _sha(jug)!=registry.sha256_file(jug_path) or _sha(eq)!=registry.sha256_file(eq_path):raise ValueError('Coady native bytes changed during read')
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    if TARGET not in entries:raise ValueError('Coady native carrier absent')
    payload=entries[TARGET].decode_payload(jug); native=roster.native_player(payload,TARGET)
    if (payload[2:5]!=bytes.fromhex('dd6361') or owners.native_owners(eq).get(TARGET)!={333}
        or roster.normalise(native['name'])!='conorcoady' or native['position']!='M'
        or native['roles']!=[9,98,98,98,98,98]):
        raise ValueError('Coady exact native semantic preimage/exclusive owner differs')
    end=native['name_end']
    dob=date(int.from_bytes(bytes(x^0x61 for x in payload[end+14:end+16]),'little'),
             payload[end+13]^0x61,payload[end+12]^0x61).isoformat()
    if dob!='1993-02-25':raise ValueError('Coady native DOB differs')
    source_bindings=[]
    for k,(rel,sha) in SOURCES.items():
        source_bindings.append({'source_id':k,'path':rel,'sha256':sha,'url':URLS.get(k)})
    receipt_rel=RECEIPT.relative_to(ROOT).as_posix()
    source_bindings.append({'source_id':'source_capture_receipt','path':receipt_rel,'sha256':_file_sha(RECEIPT)})
    writer_path=ROOT/'scripts/season_exact_primary_position_delta_v2.py'
    plan={'schema':SCHEMA,'mode':MODE,'season':base.season,'release_id':base.release_id,
      'parent':{'manifest_sha256':base.manifest_sha256,'package_sha256':_file_sha(base.package_path),
        'native_files':{'JUG98030.FDI':_sha(jug),'EQ98030.FDI':_sha(eq)}},
      'target':{'carrier_id':TARGET,'actor_id':player['id'],'club_id':player['club_id'],'club_carrier_id':333,
        'name':'Conor Coady','birth_date':'1993-02-25','before':{'primary_position':'M','fine_roles':[9]},
        'after':{'primary_position':'D','fine_roles':[4]},'native_before':native,
        'dated_source_conflict':{'2018_19_annual_position':'M','resolution':'official period-specific Wolves account says Coady moved from midfield to defence after Nuno arrived; 2017/18 onwards centre of three-man defence. Record M as annual conflict, select D for 2018/19 window.'},
        'fifa19':{k:fifa[k] for k in ('sofifa_id','long_name','dob','club','player_positions','team_position','team_jersey_number')},
        'opening_context':{'fixture_date':'2018-08-11','formation':'3-4-3','tactical_role':'LCB'}},
      'source_bindings':source_bindings,
      'implementation_binding':{'native_writer':'scripts/season_exact_primary_position_delta_v2.py','sha256':_file_sha(writer_path)},
      'scope':'Only carrier9896 primary-position byte M->D and active fine-role byte 9->4, plus matching package facts. No skill/DOB/country/identity/ownership/order/tactics/photo/asset changes.',
      'rebase_policy':'All parent package and native hashes are captured from supplied registered base. Prepare again against any later 2018-19 child (including Batth r214); this plan cannot be rebound across parents.'}
    plan['transaction_id']=_digest(plan)[:24]
    return plan

def verify(base,plan):
    _require_plan_header(plan)
    if _canon(prepare(base))!=_canon(plan):raise ValueError('Coady official source/parent/identity plan does not reproduce')
    return True

def bind(package,plan):
    _require_plan_header(plan)
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    verify(base,plan)
    if _file_sha(base.package_path)!=plan['parent']['package_sha256']:
        raise ValueError('Coady exact whole package parent changed')
    result=copy.deepcopy(package)
    if _canon(result)!=_canon(pipeline.read_json_file(base.package_path)):
        raise ValueError('Coady bind package is not exact bound parent')
    player=next(p for p in result['players'] if p.get('carrier_id')==TARGET)
    before=copy.deepcopy(player)
    player['facts']['primary_position']='D'; player['facts']['fine_roles']=[4]
    expected=copy.deepcopy(before); expected['facts']['primary_position']='D'; expected['facts']['fine_roles']=[4]
    if player!=expected:
        raise ValueError('Coady bind changed fields outside the declared two profile facts')
    aid=artifact_id(plan)
    result['artifacts'].append({'id':aid,'kind':'season-input','relative_path':filename(plan),
        'sha256':_digest(plan),'media_type':'application/json'})
    result['proofs'].append({'id':'proof-'+aid,'grade':'source-receipt','artifact_id':aid,
        'covers':['exact-Coady-identity','period-specific-Wolves-defender-role','FIFA19-CB-role','annual-M-conflict-disposition']})
    result['artifacts'].sort(key=lambda x:x['id']); result['proofs'].sort(key=lambda x:x['id'])
    packages.validate_package(result)
    return result

def apply(jug,eq,plan):
    _require_plan_header(plan)
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    verify(base,plan)
    if _sha(jug) not in (plan['parent']['native_files']['JUG98030.FDI'],):
        original=(Path(base.game_path)/'DBDAT/JUG98030.FDI').read_bytes()
        post_expected=None
        if _sha(original)!=plan['parent']['native_files']['JUG98030.FDI']:
            raise ValueError('Coady native JUG parent changed')
    else:
        original=jug
    if _sha(eq)!=plan['parent']['native_files']['EQ98030.FDI']:
        raise ValueError('Coady exact EQ parent changed')
    row={'carrier_id':TARGET,'before_player':next(p for p in pipeline.read_json_file(base.package_path)['players'] if p.get('carrier_id')==TARGET),
         'before_native':plan['target']['native_before'],'primary_position':'D','fine_roles':[4]}
    low={'schema':native_writer.SCHEMA,'season':plan['season'],'release_id':plan['release_id'],
      'package_sha256':plan['parent']['package_sha256'],'jug_sha256':plan['parent']['native_files']['JUG98030.FDI'],
      'eq_sha256':plan['parent']['native_files']['EQ98030.FDI'],'updates':[row]}
    out,out_eq=native_writer.apply(jug,eq,low)
    return out,out_eq

def reject_factory_recipe(package):
    if any(str(a.get('id','')).startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('Coady period-role layer requires its source-bound reconstruction')

def reconstruction(previous,release_id):
    receipt_path=getattr(previous,'compiler_receipt_path',None)
    if receipt_path is None:return None
    receipt=pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode')!=MODE:return None
    relative=getattr(previous,'locator',{}).get('sourced_profile_assignment_plan_path')
    if not relative:raise ValueError('Coady SOURCE receipt lacks its typed plan path')
    path=(ROOT/relative).resolve(strict=True)
    plan=pipeline.read_json_file(path)
    _require_plan_header(plan)
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    verify(base,plan)
    if path!=(previous.package_path.parent/filename(plan)).resolve() or _file_sha(path)!=receipt.get('original_profile_assignment_plan_sha256'):
        raise ValueError('Coady SOURCE plan path/hash differs from receipt')
    expected=bind(pipeline.read_json_file(base.package_path),plan)
    if _canon(pipeline.read_json_file(previous.package_path))!=_canon(expected):
        raise ValueError('Coady SOURCE package differs from exact source-bound recipe')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    expected_descriptor={'season':base.season,'release_id':base.release_id,
       'package_sha256':plan['parent']['package_sha256'],'jug_sha256':plan['parent']['native_files']['JUG98030.FDI'],
       'updates':[],'unresolved':[]}
    if pipeline.read_json_file(descriptor)!=expected_descriptor:raise ValueError('Coady SOURCE role descriptor is not inert exact parent')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=plan['release_id'],profile_assignment_plan_path=path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if _canon(pipeline.read_json_file(rebuilt.package_path))!=_canon(expected):raise ValueError('Coady whole SOURCE recipe replay differs')
    return {'season':previous.season,'release_id':release_id,'complete_game_inventory_identical':True,
       'complete_recipe_identical':True,'compilation_mode':MODE}
