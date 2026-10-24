"""Source-bound Riera country and editorial-compatible role correction.

The only supported actor is Riera after the registered opening-ownership
transaction moves carrier 9142 to 8928. Spain is one of the target-year dual
national flags and is selected as footballing-country based on a dated UEFA
youth representation statement. Left Midfield is an editorial compatible
projection supported by the target-year profile row and UEFA's left-winger
description; this is not exact-edition FIFA evidence.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_nationality import rewrite_indexed_native_nationalities
from app.indexed_jug_roles import read_indexed_native_roles, rewrite_indexed_native_roles
from scripts import season_opening_identity_exchange_v1 as opening_exchange
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as packages
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_transfermarkt_squad_biography_v1 as squad
from scripts.season_exact_fifa_role_delta_v1 import compatible
from scripts.season_historical_role_plan_v1 import HTML_ROLES
from scripts.season_within_club_reserve_repair_v1 import native_facts

SCHEMA = 'pm99-source-bound-Riera-postownership-country-editorial-role-v1'
INPUT_SCHEMA = SCHEMA + '-input'
KIND = 'riera-Spain-left-midfielder-compatible-editorial-projection-v1'
PREFIX = 'riera-postownership-country-role-'
MODE = 'known-good-baseline-source-bound-Riera-postownership-country-role-v1'
SCOPE = ('Only carrier 8928 recipe nationality ENG->ESP and fine_roles [9]->[10], plus its one native country byte '
         'and six native fine-role slots. Broad M, identity/DOB, ratings, all other actor facts, owners/orders, '
         'skills, tactics, managers and assets are preserved. Country is footballing representation from dated '
         'sources; LM is an editorial compatible projection, not exact-edition FIFA evidence.')

def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def binding(path: Path) -> dict:
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))

def source_path(value: dict) -> Path:
    if not isinstance(value, dict) or set(('path','sha256')) - set(value):
        raise ValueError('explicit workspace-relative Riera source binding required')
    path = (registry.ROOT / value['path']).resolve()
    registry.relative_workspace_path(path)
    if not path.is_file() or registry.sha256_file(path) != value['sha256']:
        raise ValueError('retained Riera source file hash differs')
    return path

def _verify_receipt(body: dict, receipt: dict) -> None:
    path = source_path(receipt)
    value = pipeline.read_json_file(path)
    if value.get('url') != body['url'] or value.get('sha256') != body['sha256']:
        raise ValueError('Riera source receipt does not bind source URL/body')

def _source_witness(request: dict) -> dict:
    evidence = request['evidence']
    annual = evidence['annual']; birth = annual['birth_date_witness']; uefa = evidence['uefa']
    source_path(annual); _verify_receipt(annual, annual['receipt'])
    source_path(birth); _verify_receipt(birth, birth['receipt'])
    uefa_path = source_path(uefa); _verify_receipt(uefa, uefa['receipt'])
    parsed = squad.read(annual, 7373, season='2005-06', club_name='RCD Espanyol Barcelona', provider_club_id=714)
    if (parsed['published_full_name'] != 'Albert Riera' or parsed['published_birth_date'] != '1982-04-15'
            or parsed['published_profile_position'] != 'Left Midfield'
            or set(parsed['published_nationality_label'].split(' / ')) != {'Spain','Russia'}):
        raise ValueError('exact target-year Riera squad row identity/country/role differs')
    url = urlsplit(uefa['url']); page = BeautifulSoup(uefa_path.read_bytes(), 'lxml')
    canonical = page.select_one('link[rel="canonical"]')
    dates = [meta.get('content') for meta in page.select('meta[property="article:published_time"]')]
    text = ' '.join(page.get_text(' ', strip=True).split())
    expected_url = 'https://www.uefa.com/uefaeuropaleague/news/0257-0de68328be3e-adfe0130a228-1000--riera-wings-into-espanyol/'
    if (url.scheme != 'https' or url.hostname != 'www.uefa.com' or uefa['url'] != expected_url
            or canonical is None or canonical.get('href') != expected_url
            or not any(isinstance(value,str) and value.startswith('2005-07-07') for value in dates)
            or 'Spanish youth international' not in text or 'left-winger' not in text
            or not any(name in text for name in ('Albert Riera','Alberto Riera'))):
        raise ValueError('dated original UEFA Spanish youth/left-wing witness differs')
    fine = HTML_ROLES.get('leftmidfield')
    if fine != 10 or not compatible('M', fine):
        raise ValueError('target-year Left Midfield does not map to compatible LM 10')
    return dict(provider_player_id=7373, name=parsed['published_full_name'], birth_date=parsed['published_birth_date'],
        annual_detail=parsed['published_profile_position'], nationality_labels=['Spain','Russia'], selected_country='ESP',
        country_policy='Spanish youth international representation; dual nationality flags retained, no exclusivity claim',
        uefa_event_date='2005-07-07', uefa_role_phrase='left-winger', broad_position='M', fine_roles=[10],
        role_policy='editorial-compatible-left-midfielder-projection-not-exact-edition-FIFA',
        bindings={key:dict(path=value['path'],sha256=value['sha256'],url=value['url'],receipt=binding(source_path(value['receipt'])))
            for key,value in (('target_year_squad',annual),('independent_birthday',birth),('dated_UEFA',uefa))})

def _ownership_parent(base, request):
    """Bind the actual registered r203 ownership release and source transaction."""
    parent = request['parent']
    locator_path = registry.locator_path(base.season, base.release_id)
    locator = pipeline.read_json_file(locator_path)
    if (registry.sha256_file(locator_path) != parent['locator_sha256']
            or registry.sha256_file(base.compiler_receipt_path) != parent['compiler_receipt_sha256']
            or base.season != request['season'] or base.release_id != parent['release_id']
            or base.manifest_sha256 != parent['manifest_sha256']
            or registry.canonical_document_sha256(base.package_path) != parent['package_sha256']
            or registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI') != parent['jug_sha256']
            or registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI') != parent['eq_sha256']
            or registry.sha256_file(base.game_path/'DBDAT/TEXTOS.PKF') != parent['textos_sha256']):
        raise ValueError('Riera correction parent does not match exact registered release hashes')
    locator_value = locator.get('sourced_profile_assignment_plan_path')
    ownership_binding = parent['ownership_plan']
    if locator_value != ownership_binding['path']:
        raise ValueError('registered release locator names another ownership source plan')
    ownership_path = source_path(ownership_binding)
    receipt = pipeline.read_json_file(base.compiler_receipt_path)
    ownership_plan = pipeline.read_json_file(ownership_path)
    if (receipt.get('compilation_mode') != opening_exchange.MODE
            or receipt.get('original_profile_assignment_plan_sha256') != ownership_binding['sha256']
            or ownership_plan.get('schema') != opening_exchange.SCHEMA
            or ownership_plan.get('transaction_id') != ownership_binding['transaction_id']
            or ownership_plan.get('release_id') != parent['ownership_source_release_id']
            or ownership_plan.get('season') != base.season
            or not any(row.get('source') == 9142 and row.get('destination') == 8928 for row in ownership_plan.get('request',{}).get('moves',[]))):
        raise ValueError('r203 registered compiler receipt/ownership plan transaction differs')
    artifact_id = opening_exchange.PREFIX + ownership_plan['transaction_id']
    artifacts = [a for a in pipeline.read_json_file(base.package_path).get('artifacts',[]) if a.get('id') == artifact_id]
    expected_plan_sha = digest(packages.canonical_json_bytes(ownership_plan))
    if len(artifacts) != 1 or artifacts[0].get('sha256') != expected_plan_sha:
        raise ValueError('r203 package does not retain exact ownership transaction artifact')
    return dict(locator_sha256=registry.sha256_file(locator_path),ownership_plan=ownership_binding,
        ownership_transaction_id=ownership_plan['transaction_id'],ownership_source_release_id=ownership_plan['release_id'],
        compiler_receipt_sha256=registry.sha256_file(base.compiler_receipt_path),
        source_profile_assignment_plan_sha256=receipt['original_profile_assignment_plan_sha256'])

def prepare(base, input_path):
    path = Path(input_path).resolve(); registry.relative_workspace_path(path)
    request = pipeline.read_json_file(path)
    if (request.get('schema') != INPUT_SCHEMA or request.get('kind') != KIND or request.get('season') != base.season
            or request.get('carrier_id') != 8928
            or request.get('expected_preimage') != dict(provider_player_id=7373,full_name='Albert Riera',birth_date='1982-04-15',
                club_carrier_id=8,nationality='ENG',broad_position='M',fine_roles=[9])
            or request.get('target') != dict(nationality='ESP',fine_roles=[10],broad_position='M',
                role_policy='editorial-compatible-left-midfielder-projection-not-exact-edition-FIFA')):
        raise ValueError('Riera exact identity, expected parent facts or two-field target differs')
    ownership_binding = _ownership_parent(base, request)
    package = pipeline.read_json_file(base.package_path)
    actors = {p['carrier_id']:p for p in package['players']}; actor=actors[8928]
    clubs={c['id']:c for c in package['clubs']}
    if (actor.get('source_name') != 'Albert Riera' or actor['facts'].get('birth_date') != '1982-04-15'
            or actor['facts'].get('primary_position') != 'M' or actor['facts'].get('nationality') != 'ENG'
            or actor['facts'].get('fine_roles') != [9] or actor['club_id'] not in clubs
            or clubs[actor['club_id']].get('carrier_id') != 8):
        raise ValueError('r203 package Riera actor is not the exact expected preimage')
    jug_path=base.game_path/'DBDAT/JUG98030.FDI'; eq_path=base.game_path/'DBDAT/EQ98030.FDI'
    jug=jug_path.read_bytes(); eq=eq_path.read_bytes(); textos=base.game_path/'DBDAT/TEXTOS.PKF'
    if ownership.native_owners(eq).get(8928) != {8}:
        raise ValueError('r203 native Riera ownership is not exclusively Espanyol 8')
    native=native_facts(jug,8928); entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries}
    entry=entries[8928]; payload=entry.decode_payload(jug); end,roles=read_indexed_native_roles(payload,8928)
    countries=compiler._extract_country_codes_from_textos(textos)
    if (native['name'].casefold()!='albert riera' or native['birth_date']!='1982-04-15' or native['position']!='M'
            or roles != [9,98,98,98,98,98]
            or (payload[end+8]^0x61) != compiler._country_code('ENG',countries)):
        raise ValueError('r203 native Riera identity/country/role preimage differs')
    witness=_source_witness(request)
    esp=compiler._country_code('ESP',countries)
    if esp==compiler._country_code('ENG',countries): raise ValueError('native country table has no distinct ESP code')
    masks=[]
    for i in range(6):
        offset=end+2+i; absolute=entry.payload_offset+offset
        masks.append(dict(file='DBDAT/JUG98030.FDI',carrier_id=8928,record_offset=offset,file_offset=absolute,
            before=jug[absolute],after=11 if i==0 else 0,field='fine_roles'))
    offset=end+8; absolute=entry.payload_offset+offset
    masks.append(dict(file='DBDAT/JUG98030.FDI',carrier_id=8928,record_offset=offset,file_offset=absolute,
        before=jug[absolute],after=esp,field='nationality'))
    roles_after,_=rewrite_indexed_native_roles(jug,{8928:[10]})
    native_after,_=rewrite_indexed_native_nationalities(roles_after,{8928:esp})
    changed={i for i,(a,b) in enumerate(zip(jug,native_after)) if a!=b}
    allowed={m['file_offset'] for m in masks if m['before']!=m['after']}
    if changed != allowed:
        raise ValueError('native writer changed bytes outside Riera role/country masks')
    result=dict(schema=SCHEMA,kind=KIND,season=base.season,release_id=base.release_id,
        parent=dict(manifest_sha256=base.manifest_sha256,package_sha256=registry.canonical_document_sha256(base.package_path),
            jug_sha256=digest(jug),eq_sha256=digest(eq),textos_sha256=registry.sha256_file(textos),**ownership_binding),
        source_input=binding(path),carrier_id=8928,before_actor=copy.deepcopy(actor),
        before_actor_sha256=digest(packages.canonical_json_bytes(actor)),before_native=dict(facts=native,roles=roles,
            nationality_code=payload[end+8]^0x61,record_sha256=digest(payload)),
        after_fields=dict(nationality='ESP',fine_roles=[10]),native_masks=masks,native_post_sha256=digest(native_after),
        source_witness=witness,scope=SCOPE)
    result['transaction_id']=digest(packages.canonical_json_bytes(result))[:24]
    return result

def verify(base, plan):
    if (plan.get('schema') != SCHEMA or not isinstance(plan.get('source_input'),dict)
            or registry.sha256_file(source_path(plan['source_input'])) != plan['source_input']['sha256']
            or packages.canonical_json_bytes(prepare(base,registry.ROOT/plan['source_input']['path']))
                != packages.canonical_json_bytes(plan)):
        raise ValueError('Riera source/native plan does not independently reproduce')

def validate_mask(plan):
    if (plan.get('schema')!=SCHEMA or plan.get('kind')!=KIND or plan.get('carrier_id')!=8928
            or plan.get('after_fields')!=dict(nationality='ESP',fine_roles=[10]) or len(plan.get('native_masks',[]))!=7):
        raise ValueError('exact Riera country + six-role correction required')
    masks=plan['native_masks']; offsets=set()
    if ([m['record_offset']-masks[0]['record_offset'] for m in masks] != list(range(7))
            or [m['field'] for m in masks] != ['fine_roles']*6+['nationality']
            or [m['after'] for m in masks] != [11,0,0,0,0,0,plan['native_masks'][6]['after']]):
        raise ValueError('Riera native postmask permits only ordered role slots and country byte')
    for mask in masks:
        if (set(mask)!={'file','carrier_id','record_offset','file_offset','before','after','field'}
                or mask['file']!='DBDAT/JUG98030.FDI' or mask['carrier_id']!=8928
                or any(type(mask[k]) is not int for k in ('record_offset','file_offset','before','after'))
                or not 0<=mask['before']<=255 or not 0<=mask['after']<=255 or mask['file_offset'] in offsets):
            raise ValueError('malformed Riera source-bound native field mask')
        offsets.add(mask['file_offset'])

def filename(plan):
    if plan.get('schema')!=SCHEMA: raise ValueError('unsupported Riera plan schema')
    return PREFIX+plan['transaction_id']+'.json'

def artifact_id(plan):
    if plan.get('schema')!=SCHEMA: raise ValueError('unsupported Riera plan schema')
    return PREFIX+plan['transaction_id']

def bind(package, plan):
    validate_mask(plan); base=registry.load_registered_release(plan['season'],plan['release_id']); verify(base,plan)
    if packages.canonical_json_bytes(package)!=packages.canonical_json_bytes(pipeline.read_json_file(base.package_path)):
        raise ValueError('Riera bind requires exact registered complete package preimage')
    if registry.canonical_document_sha256(base.package_path)!=plan['parent']['package_sha256']:
        raise ValueError('Riera package hash differs from plan preimage')
    result=copy.deepcopy(package); actor=next(p for p in result['players'] if p['carrier_id']==8928)
    if digest(packages.canonical_json_bytes(actor))!=plan['before_actor_sha256']:
        raise ValueError('Riera complete package actor preimage differs')
    actor['facts']['nationality']='ESP'; actor['facts']['fine_roles']=[10]
    if 'fact_fallbacks' in actor:
        actor['fact_fallbacks']=[f for f in actor['fact_fallbacks'] if f.get('field') not in {'nationality','fine_roles'}]
    aid=artifact_id(plan); plan_sha=digest(packages.canonical_json_bytes(plan))
    result['artifacts']=[a for a in result.get('artifacts',[]) if a.get('id')!=aid]+[
        dict(id=aid,kind='season-input',relative_path=filename(plan),sha256=plan_sha,media_type='application/json')]
    result['proofs']=[p for p in result.get('proofs',[]) if p.get('id') not in {aid+'-country-proof',aid+'-role-proof'}]+[
        dict(id=aid+'-country-proof',grade='source-captured',artifact_id=aid,
            covers=['target-year Spain/Russia published flags','dated UEFA Spanish youth representation; selected footballing-country ESP']),
        dict(id=aid+'-role-proof',grade='reviewed-editorial',artifact_id=aid,
            covers=['target-year Left Midfield row','compatible LM 10 editorial projection; not exact-edition FIFA'])]
    result['artifacts'].sort(key=lambda x:x['id']); result['proofs'].sort(key=lambda x:x['id'])
    packages.validate_package(result)
    return result

def apply(jug,eq,plan):
    validate_mask(plan); base=registry.load_registered_release(plan['season'],plan['release_id']); verify(base,plan)
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); expected_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if digest(before)!=plan['parent']['jug_sha256'] or digest(expected_eq)!=plan['parent']['eq_sha256'] or digest(eq)!=plan['parent']['eq_sha256']:
        raise ValueError('Riera native parent/JUG/EQ hashes differ')
    roles,_=rewrite_indexed_native_roles(before,{8928:[10]})
    countries=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    after,_=rewrite_indexed_native_nationalities(roles,{8928:compiler._country_code('ESP',countries)})
    changed={i for i,(a,b) in enumerate(zip(before,after)) if a!=b}
    allowed={m['file_offset'] for m in plan['native_masks'] if m['before']!=m['after']}
    if changed!=allowed or digest(after)!=plan['native_post_sha256']:
        raise ValueError('Riera native delta escaped exact country/role mask')
    for m in plan['native_masks']:
        if before[m['file_offset']]!=m['before'] or after[m['file_offset']]!=m['after']:
            raise ValueError('Riera native field pre/post byte differs')
    if (len(jug)!=len(before) or digest(jug) not in {plan['parent']['jug_sha256'],plan['native_post_sha256']}):
        raise ValueError('Riera patch accepts only exact complete preimage or postimage')
    if digest(jug)==plan['native_post_sha256'] and bytes(jug)!=after:
        raise ValueError('Riera complete native postimage differs on whole-file replay')
    return (after if digest(jug)==plan['parent']['jug_sha256'] else bytes(jug), bytes(eq))

def reject_factory_recipe(package):
    if any(a.get('id','').startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('Riera correction recipe requires exact source-bound reconstruction')

def reconstruction(previous,release_id):
    # Receipt mode is the first gate so unrelated releases are ignored without touching plan paths.
    receipt_path = getattr(previous, 'compiler_receipt_path', None)
    if receipt_path is None:
        return None
    receipt=pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode')!=MODE: return None
    relative=previous.locator.get('sourced_profile_assignment_plan_path')
    if not relative: raise ValueError('Riera SOURCE receipt lacks assignment-plan locator')
    plan_path=registry.ROOT/relative; plan=pipeline.read_json_file(plan_path)
    if plan.get('schema')!=SCHEMA: raise ValueError('Riera SOURCE receipt points to another plan kind')
    base=registry.load_registered_release(previous.season,plan['release_id']); verify(base,plan)
    if (plan_path.resolve()!=(previous.package_path.parent/filename(plan)).resolve()
            or registry.sha256_file(plan_path)!=receipt.get('original_profile_assignment_plan_sha256')):
        raise ValueError('Riera SOURCE receipt/plan path or SHA differs')
    package=pipeline.read_json_file(previous.package_path)
    if bind(pipeline.read_json_file(base.package_path),plan)!=package:
        raise ValueError('Riera SOURCE would discard recipe changes')
    aid=artifact_id(plan); descriptor=previous.package_path.parent/'role-delta-input.json'
    if pipeline.read_json_file(descriptor)!=dict(season=base.season,release_id=base.release_id,
            package_sha256=plan['parent']['package_sha256'],jug_sha256=plan['parent']['jug_sha256'],updates=[],unresolved=[]):
        raise ValueError('Riera SOURCE inert role descriptor differs')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,source_release_id=base.release_id,
        profile_assignment_plan_path=plan_path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():
        raise ValueError('Riera whole SOURCE recipe differs')
    return dict(season=previous.season,release_id=release_id,complete_game_inventory_identical=True,
        complete_recipe_identical=True,compilation_mode=MODE)
