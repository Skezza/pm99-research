"""Source-bound one-row mode-1 roster activation pilot for Madrid carrier 4."""
from __future__ import annotations
import copy, hashlib, json, tempfile
from pathlib import Path
from app.editor_actions import edit_team_roster_eq_jug_linked
from app.eq_jug_linked import load_eq_linked_team_rosters
from app.fdi_indexed import IndexedFDIFile
from scripts import season_package_v2 as packages, season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_within_club_reserve_repair_v1 import native_facts

SCHEMA='pm99-source-bound-madrid-mode1-row-activation-v1'
INPUT_SCHEMA=SCHEMA+'-input'
MODE='known-good-baseline-source-bound-madrid-mode1-row-activation-v1'
PREFIX='madrid-mode1-row-activation-'
KIND='single-mode1-row-visibility-pilot-not-causal-proof-v1'
RELEASE='sourced-riera-country-left-midfield-20261023-r204a'
SOURCE_REQUEST='.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/new-person-canonical-v1/opening-exchange-r199-celtic-request-v3.json'
SOURCE_PLAN='.local/historical-role-deltas-v1/2005-06/sourced-espanyol-city-madrid-ownership-20261023-r203a/opening-identity-exchange-516657010db58fe22e174837.json'

def sha(data): return hashlib.sha256(data).hexdigest()
def binding(path): return {'path':registry.relative_workspace_path(Path(path)), 'sha256':registry.sha256_file(Path(path))}
def source(value):
    p=(registry.ROOT/value['path']).resolve(); registry.relative_workspace_path(p)
    if not p.is_file() or registry.sha256_file(p)!=value['sha256']: raise ValueError('bound source hash mismatch')
    return p
def _native(eq,jug):
    # Parse the indexed EQ payload directly through the public linked-roster reader.
    from app.eq_jug_linked import parse_eq_external_team_roster_payload
    parsed=[]
    for entry in IndexedFDIFile.from_bytes(eq).entries:
        if entry.record_id==4:
            parsed.append(parse_eq_external_team_roster_payload(eq[entry.payload_offset:entry.payload_offset+entry.payload_length],{}))
    if len(parsed)!=1 or parsed[0] is None: raise ValueError('Madrid EQ record 4 is not one parseable linked roster')
    return parsed[0]
def _source_admission(input_value):
    req=source(input_value['source_request']); plan=source(input_value['ownership_plan'])
    request=pipeline.read_json_file(req); ownership=pipeline.read_json_file(plan)
    if request.get('schema')!='pm99-source-bound-opening-identity-exchange-v1-input': raise ValueError('unexpected source request schema')
    matches=[x for x in request.get('new_people',[]) if x.get('provider_player_id')==35522]
    if len(matches)!=1: raise ValueError('expected one source admission for provider 35522')
    row=matches[0]
    if (row.get('carrier_id')!=19 or row.get('birth_date')!='1985-06-05' or row.get('name')!='Rubén de la Red'
        or row.get('match')!='rm_august_bench'):
        raise ValueError('source admission does not bind the expected Rubén identity and unused-bench evidence')
    match=row['_provider_evidence']['rm_august_bench']
    match_path=registry.ROOT/match['path']
    if (match.get('date')!='2005-08-28' or match.get('membership_mode')!='classic-played-substitutes'
        or match.get('provider_club_id')!=418 or registry.sha256_file(match_path)!=match.get('sha256')):
        raise ValueError('original August unused-bench source binding differs')
    ownership_people=[x for x in ownership.get('request',{}).get('new_people',[]) if x.get('provider_player_id')==35522]
    if ownership.get('schema')!='pm99-source-bound-opening-identity-exchange-v1' or not ownership_people:
        raise ValueError('registered ownership plan lacks exact Rubén admission')
    if ownership.get('source_input') != input_value['source_request'] or ownership_people != [row]:
        raise ValueError('ownership artifact and original source request admission differ')
    from scripts import season_opening_identity_exchange_v1 as opening
    admitted = opening.new_person(row, request['evidence'])
    if (admitted['source_person']['source_player_id'] != 35522
            or admitted['source_player']['birth_date'] != '1985-06-05'
            or admitted['membership'] != 'original-published-August-bench-not-playing-claim'):
        raise ValueError('original source does not reproduce positive unused-bench membership')
    return {'provider_player_id':35522,'carrier_id':19,'name':row['name'],'birth_date':row['birth_date'],
        'match_alias':row['match'],'match_evidence':match,
        'source_request':input_value['source_request'],'ownership_plan':input_value['ownership_plan']}

def prepare(base,input_path):
    path=Path(input_path).resolve(); registry.relative_workspace_path(path); inp=pipeline.read_json_file(path)
    if inp.get('schema')!=INPUT_SCHEMA or base.season!='2005-06' or base.release_id!=RELEASE:
        raise ValueError('activation input is scoped to the registered r204a 2005-06 parent')
    loc=registry.locator_path(base.season,base.release_id)
    expected=inp['parent']
    observed={'release_id':base.release_id,'manifest_sha256':base.manifest_sha256,
      'package_sha256':registry.canonical_document_sha256(base.package_path),
      'jug_sha256':registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
      'eq_sha256':registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI'),
      'locator_sha256':registry.sha256_file(loc)}
    if observed!=expected: raise ValueError('registered parent bindings differ')
    package=pipeline.read_json_file(base.package_path); actors=[p for p in package['players'] if p.get('carrier_id')==19]
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if len(actors)!=1 or actors[0].get('source_name')!='Rubén de la Red' or actors[0]['facts'].get('birth_date')!='1985-06-05': raise ValueError('carrier 19 package identity differs')
    if actors[0].get('club_id') != 'club-4' or actors[0].get('person_id') != 'person-transfermarkt-35522':
        raise ValueError('Rubén recipe club or source person identity differs')
    from scripts.season_opening_order_repair_v1 import native_owners
    if native_owners(eq).get(19) != {4}:
        raise ValueError('Rubén must have only the one Madrid native reference')
    facts=native_facts(jug,19)
    if facts.get('name')!='Rubén DE LA RED' or facts.get('birth_date')!='1985-06-05' or facts.get('startup_order')!=24: raise ValueError('native carrier 19 identity/order differs')
    roster=_native(eq,jug)
    if roster.mode_byte!=1 or roster.full_club_name!='Real Madrid' or len(roster.rows)!=25: raise ValueError('target roster mode/team/count differs')
    target=[r for r in roster.rows if r.slot_index==3]
    if len(target)!=1 or (target[0].player_record_id,target[0].flag)!=(19,1): raise ValueError('exact target row is no longer slot4/player19/flag1')
    preserved={(r.player_record_id,r.flag) for r in roster.rows}
    if not {(16478,1),(20192,1)}.issubset(preserved): raise ValueError('other Madrid flagged rows differ')
    # Startup order 24 is unique among native members whose order is playable
    # (the linked-row flag has unconfirmed semantics and is not an order filter).
    orders=[]
    from scripts.season_within_club_reserve_repair_v1 import native_facts as nf
    for r in roster.rows:
        orders.append((r.player_record_id,nf(jug,r.player_record_id).get('startup_order')))
    if sum(order==24 for _,order in orders)!=1 or (19,24) not in orders: raise ValueError('startup order 24 is not unique among native members')
    admission=_source_admission(inp)
    rows=[[r.player_record_id,r.flag] for r in roster.rows]
    result={'schema':SCHEMA,'kind':KIND,'season':base.season,'release_id':base.release_id,'parent':observed,
      'source_input':binding(path),'source_admission':admission,'target':{'eq_record_id':4,'club':'Real Madrid','mode':1,
        'slot_number':4,'player_record_id':19,'old_flag':1,'new_flag':0,'name':'Rubén de la Red','birth_date':'1985-06-05',
        'startup_order':24,'active_order_is_unique':True},'other_flagged_rows':[[16478,1],[20192,1]],
      'eq_rows_before':rows,'eq_preimage_sha256':sha(eq),'jug_preimage_sha256':sha(jug),
      'scope':'One target EQ roster flag byte only. JUG, package actors/facts, all other EQ bytes and all other flags preserved. Visibility pilot only; no causal claim about flag semantics.'}
    after,offset=_writer(eq,jug)
    result['eq_flag_offset']=offset; result['eq_postimage_sha256']=sha(after)
    result['transaction_id']=sha(packages.canonical_json_bytes(result))[:24]
    return result

def _writer(eq,jug):
    with tempfile.TemporaryDirectory(prefix='madrid-activation-') as td:
        eqp=Path(td)/'EQ98030.FDI'; jp=Path(td)/'JUG98030.FDI'; eqp.write_bytes(eq); jp.write_bytes(jug)
        edit_team_roster_eq_jug_linked(team_file=str(eqp),player_file=str(jp),eq_record_id=4,slot_number=4,player_record_id=19,flag=0,write_changes=True)
        out=eqp.read_bytes()
    diffs=[i for i,(a,b) in enumerate(zip(eq,out)) if a!=b]
    if len(diffs)!=1 or len(eq)!=len(out): raise ValueError('canonical editor writer changed more than one byte')
    return out,diffs[0]

def verify(base,plan):
    inp=source(plan['source_input'])
    if packages.canonical_json_bytes(prepare(base,inp))!=packages.canonical_json_bytes(plan): raise ValueError('plan does not reproduce from registered parent and exact source inputs')
def filename(plan): return PREFIX+plan['transaction_id']+'.json'
def artifact_id(plan): return PREFIX+plan['transaction_id']
def bind(package,plan):
    base=registry.load_registered_release(plan['season'],plan['release_id']); verify(base,plan)
    if packages.canonical_json_bytes(package)!=packages.canonical_json_bytes(pipeline.read_json_file(base.package_path)): raise ValueError('bind requires exact registered package preimage')
    out=copy.deepcopy(package); aid=artifact_id(plan); plansha=sha(packages.canonical_json_bytes(plan))
    out['artifacts']=sorted([a for a in out.get('artifacts',[]) if a.get('id')!=aid]+[{'id':aid,'kind':'season-input','relative_path':filename(plan),'sha256':plansha,'media_type':'application/json'}],key=lambda x:x['id'])
    out['proofs']=sorted([p for p in out.get('proofs',[]) if p.get('id')!=aid+'-pilot']+[{'id':aid+'-pilot','artifact_id':aid,'grade':'source-captured','covers':['source-admitted-native-mode1-row-activation-pilot-not-causal-proof']}],key=lambda x:x['id'])
    packages.validate_package(out)
    return out
def reject_factory_recipe(package):
    if any(a.get('id','').startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('Madrid mode-1 activation requires source-bound reconstruction')
def reconstruction(previous,release_id):
    # The mode check must precede every inherited locator/artifact lookup.
    receipt_path=getattr(previous,'compiler_receipt_path',None)
    if receipt_path is None: return None
    receipt=pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode')!=MODE: return None
    relative=getattr(previous,'locator',{}).get('sourced_profile_assignment_plan_path')
    if not relative: raise ValueError('Madrid activation SOURCE receipt lacks assignment-plan locator')
    plan_path=(registry.ROOT/relative).resolve(); plan=pipeline.read_json_file(plan_path)
    if plan.get('schema')!=SCHEMA: raise ValueError('Madrid activation SOURCE receipt points to another plan schema')
    base=registry.load_registered_release(previous.season,plan['release_id']); verify(base,plan)
    if (plan_path!=(previous.package_path.parent/filename(plan)).resolve()
        or registry.sha256_file(plan_path)!=receipt.get('original_profile_assignment_plan_sha256')):
        raise ValueError('Madrid activation SOURCE receipt path or plan SHA differs')
    package=pipeline.read_json_file(previous.package_path)
    if bind(pipeline.read_json_file(base.package_path),plan)!=package:
        raise ValueError('Madrid activation SOURCE would discard recipe changes')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['parent']['package_sha256'],jug_sha256=plan['parent']['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('Madrid activation SOURCE inert role descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,
        profile_assignment_plan_path=plan_path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():
        raise ValueError('Madrid activation SOURCE complete package replay differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,
        complete_recipe_identical=True,compilation_mode=MODE)
def apply(jug,eq,plan):
    if plan.get('schema')!=SCHEMA: raise ValueError('wrong plan schema')
    base=registry.load_registered_release(plan['season'],plan['release_id'])
    verify(base,plan)
    if sha(jug)!=plan['jug_preimage_sha256']: raise ValueError('JUG preimage differs')
    if sha(eq)==plan['eq_postimage_sha256']:
        return jug,eq
    if sha(eq)!=plan['eq_preimage_sha256']: raise ValueError('EQ is neither complete preimage nor exact postimage')
    roster=_native(eq,jug); target=[r for r in roster.rows if r.slot_index==3]
    if roster.mode_byte!=1 or len(target)!=1 or (target[0].player_record_id,target[0].flag)!=(19,1): raise ValueError('native target row preimage differs')
    out,offset=_writer(eq,jug)
    if offset!=plan['eq_flag_offset'] or sha(out)!=plan['eq_postimage_sha256']: raise ValueError('writer result differs from prepared postimage')
    diffs=[i for i,(a,b) in enumerate(zip(eq,out)) if a!=b]
    if diffs!=[offset] or out[offset]!=0: raise ValueError('apply changed bytes outside exact flag')
    return jug,out
