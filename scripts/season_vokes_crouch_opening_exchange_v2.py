"""Source-bound 2018/19 Vokes/Crouch opening ownership correction.

The proposal swaps two existing EQ->JUG links and destination-order bytes,
and applies two date-scoped shirt-number facts from the original opening
reports. JUG identities/ratings stay on their original carriers. Publication and runtime acceptance remain separate from source admission.
"""
from __future__ import annotations
import copy, hashlib, json, tempfile
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from app.editor_actions import edit_team_roster_eq_jug_linked
from app.eq_jug_linked import load_eq_linked_team_rosters, parse_eq_external_team_roster_payload
from app.fdi_indexed import IndexedFDIFile
from app.player_initial_order import OrderReplacement, patch_initial_orders, read_initial_order
from app.indexed_jug_shirt_number import rewrite_indexed_native_shirt_numbers
from scripts import season_package_v2 as packages, season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.season_opening_order_repair_v1 import native_owners
from scripts.season_within_club_reserve_repair_v1 import native_facts

SCHEMA = 'pm99-source-bound-vokes-crouch-opening-exchange-v2'
INPUT_SCHEMA = SCHEMA + '-input'
MODE = 'source-backed-vokes-crouch-openingswap-shirts-20261024-v2'
KIND = 'dated-opening-roster-link-and-order-exchange'
PREFIX = 'vokes-crouch-opening-exchange-v2-'
SEASON = '2018-19'
RELEASE = 'sourced-ohara-midfield-role-20261023-r206a'
V = {'carrier':10744,'name':'Sam Vokes','native_name':'Sam VOKES','dob':'1989-10-21','source_id':'48078','source_club':1132,'target_club':304,'before_club':351,'source_match':'3050174','source_date':'2018-08-12','eq':351,'slot':13,'order_before':13,'order_after':17}
C = {'carrier':7942,'name':'Peter Crouch','native_name':'Peter CROUCH','dob':'1981-01-30','source_id':'4072','source_club':512,'target_club':351,'before_club':304,'source_match':'3053576','source_date':'2018-08-05','eq':304,'slot':17,'order_before':17,'order_after':13}
CLUBS = {'burnley':{'carrier':304,'full_name':'Burnley'},'stoke':{'carrier':351,'full_name':'Stoke City'}}

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def filename(plan): return PREFIX + plan['transaction_id'] + '.json'
def artifact_id(plan): return PREFIX + plan['transaction_id']
def _binding(path, url=None):
    p=Path(path).resolve(); rel=registry.relative_workspace_path(p)
    if p.is_symlink() or not p.is_file(): raise ValueError('source binding must be a retained regular file')
    out={'path':rel,'sha256':registry.sha256_file(p)}
    if url is not None: out['url']=url
    return out

def _read_binding(ref):
    p=(registry.ROOT/ref['path']).resolve(); registry.relative_workspace_path(p)
    if p.is_symlink() or not p.is_file() or registry.sha256_file(p)!=ref['sha256']:
        raise ValueError('bound source file changed or escaped workspace')
    return p.read_bytes()

class _CapturedHtml(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.title_parts=[]; self.text_parts=[]; self.links=[]
        self.rows=[]; self._row=None; self._in_title=False; self._anchor_href=None; self._anchor_parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag.lower()=='title': self._in_title=True
        if tag.lower()=='tr': self._row={'parts':[],'links':[]}
        if tag.lower()=='a': self._anchor_href=attrs.get('href'); self._anchor_parts=[]
    def handle_endtag(self,tag):
        if tag.lower()=='title': self._in_title=False
        if tag.lower()=='a' and self._anchor_href is not None:
            link=(self._anchor_href,' '.join(' '.join(self._anchor_parts).split()))
            self.links.append(link)
            if self._row is not None: self._row['links'].append(link)
            self._anchor_href=None; self._anchor_parts=[]
        if tag.lower()=='tr' and self._row is not None:
            self.rows.append({'text':' '.join(' '.join(self._row['parts']).split()),'links':self._row['links']})
            self._row=None
    def handle_data(self,data):
        self.text_parts.append(data)
        if self._in_title: self.title_parts.append(data)
        if self._anchor_href is not None: self._anchor_parts.append(data)
        if self._row is not None: self._row['parts'].append(data)
    @property
    def title(self): return ' '.join(' '.join(self.title_parts).split())
    @property
    def text(self): return ' '.join(' '.join(self.text_parts).split())

def _html(data):
    parser=_CapturedHtml(); parser.feed(data.decode('utf-8','replace')); parser.close(); return parser

def _parent(base, request):
    expected=request.get('parent',{})
    actual={'season':base.season,'release_id':base.release_id,'manifest_sha256':base.manifest_sha256,
      'locator_sha256':registry.sha256_file(registry.locator_path(base.season,base.release_id)),
      'package_sha256':registry.sha256_file(base.package_path),
      'jug_sha256':registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
      'eq_sha256':registry.sha256_file(base.game_path/'DBDAT/EQ98030.FDI')}
    if actual!=expected or (base.season,base.release_id)!=(SEASON,RELEASE):
        raise ValueError('exact registered r206a parent/preimages required')
    return actual

def _source_membership(request):
    bindings=request['source_bindings']
    raw_lineups=_read_binding(bindings['opening_lineups'])
    if sha(raw_lineups)!=bindings['opening_lineups']['sha256']:
        raise ValueError('opening-lineups source binding changed')
    lineups=json.loads(raw_lineups)
    reports={}
    for key,person,club,date,match,name in (
        ('burnley_match_report','vokes',1132,'2018-08-12','3050174','Sam Vokes'),
        ('stoke_match_report','crouch',512,'2018-08-05','3053576','Peter Crouch')):
        ref=bindings[key]; raw=_read_binding(ref); page=_html(raw)
        title=page.title
        display_date='12/08/2018' if person=='vokes' else '05/08/2018'
        club_title='Burnley FC' if person=='vokes' else 'Stoke City'
        if match not in ref.get('url','') or display_date not in title or club_title not in title:
            raise ValueError(f'{name}: original fixture report URL/title/date mismatch')
        candidates=[x for x in lineups.get('clubs',[]) if str(x.get('source_match_id'))==match
                    and x.get('source_selector',{}).get('transfermarkt_club_id')==club
                    and x.get('first_league_fixture_date')==date]
        if len(candidates)!=1: raise ValueError(f'{name}: exact team fixture missing/ambiguous in retained source lineup')
        clubrow=candidates[0]
        player=request['actors'][person]
        bench=[x for x in clubrow.get('substitutes',[]) if str(x.get('source_player_id'))==player['source_player_id'] and x.get('display_name')==name]
        if str(player.get('source_player_id'))!=({'vokes':'48078','crouch':'4072'}[person]):
            raise ValueError(f'{name}: exact provider identity ID differs')
        if len(bench)!=1: raise ValueError(f'{name}: expected one positive unused/used substitute source row')
        href=f'/'+('sam-vokes' if person=='vokes' else 'peter-crouch')+f'/profil/spieler/{player["source_player_id"]}'
        links=[a for a in page.links if a[0].endswith(href) and a[1]==name]
        if not links: raise ValueError(f'{name}: original match report lacks exact source profile link')
        source_rows=[r for r in page.rows if (href, name) in r['links']]
        if len(source_rows)!=1: raise ValueError(f'{name}: expected one exact original lineup row')
        row_parts=source_rows[0]['text'].split()
        if len(row_parts)<3 or row_parts[1:3]!=name.split(): raise ValueError(f'{name}: original lineup row identity differs')
        try: source_shirt=int(row_parts[0])
        except (ValueError,IndexError) as exc: raise ValueError(f'{name}: original fixture row has no numeric shirt') from exc
        expected_shirt=request['shirt_targets'][person]['number']
        shirt_target=request['shirt_targets'][person]
        if (source_shirt!=expected_shirt or shirt_target.get('evidence_match_id')!=match
            or shirt_target.get('evidence_source_player_id')!=player['source_player_id']):
            raise ValueError(f'{name}: opening source jersey or match/player witness binding differs')
        reports[person]={'match_id':match,'date':date,'club_id':club,'source_player_id':player['source_player_id'],
          'name':name,'membership':'positive-published-match-substitute','shirt_number':source_shirt,
          'raw_lineup_row':source_rows[0]['text'],'source_lineup_path':bindings['opening_lineups']['path'],
          'source_lineup_sha256':bindings['opening_lineups']['sha256'],'report_path':ref['path'],'report_sha256':ref['sha256'],
          'report_url':ref['url']}
    official=_html(_read_binding(bindings['official_january_transfer_list']))
    receipt=json.loads(_read_binding(bindings['official_transfer_receipt']))
    body_sha=bindings['official_january_transfer_list']['sha256']
    if (receipt.get('url')!='https://www.premierleague.com/en/news/941295'
        or receipt.get('body_sha256')!=body_sha or receipt.get('final_url')!=receipt.get('url')
        or receipt.get('http_status')!=200
        or receipt.get('body_path')!=bindings['official_january_transfer_list']['path']):
        raise ValueError('official transfer-page receipt/body binding mismatch')
    text=official.text
    if ('January 2019 Premier League transfer news' not in text
        or 'Peter Crouch (Stoke City)' not in text or 'Sam Vokes (Stoke City)' not in text):
        raise ValueError('official January transfer list no longer proves reciprocal Burnley/Stoke entries')
    bi=text.find('Burnley In Peter Crouch (Stoke City)')
    next_club=text.find('Cardiff City In',bi+1)
    section=text[bi:next_club if next_club>=0 else bi+1200]
    if bi<0 or 'Sam Vokes (Stoke City)' not in section:
        raise ValueError('official reciprocal transfer entries are not both in Burnley section')
    return {'positive_opening_memberships':reports,
      'official_january_transfer':{'url':receipt['url'],'receipt_path':bindings['official_transfer_receipt']['path'],
       'receipt_sha256':bindings['official_transfer_receipt']['sha256'],'body_path':bindings['official_january_transfer_list']['path'],
       'body_sha256':body_sha,'textual_claims':['Burnley In Peter Crouch (Stoke City)','Burnley Out Sam Vokes (Stoke City)'],
       'scope':'Official 2018/19 January-window direction evidence; used to explain current end-season owners differ from positive August opener owners.'}}

def _rosters(eq,jug):
    # Parser-backed complete roster rows; only two exact directory records are read.
    parsed={}
    idx=IndexedFDIFile.from_bytes(eq)
    for entry in idx.entries:
        if entry.record_id not in (304,351): continue
        raw=eq[entry.payload_offset:entry.payload_offset+entry.payload_length]
        r=parse_eq_external_team_roster_payload(raw,{})
        if r is None: raise ValueError('target roster is not parseable mode-0 external linkage')
        parsed[entry.record_id]=(entry,r)
    if set(parsed)!={304,351}: raise ValueError('unique exact target EQ records required')
    return parsed

def _native_order(jug,cid):
    idx=IndexedFDIFile.from_bytes(jug); entries=[e for e in idx.entries if e.record_id==cid]
    if len(entries)!=1: raise ValueError('native player carrier must be unique')
    field=read_initial_order(entries[0].decode_payload(jug))
    return entries[0],field

def _source_request(path):
    p=Path(path)
    if not p.is_absolute(): p=registry.ROOT/p
    p=p.resolve(); registry.relative_workspace_path(p)
    if p.is_symlink() or not p.is_file(): raise ValueError('input must be retained regular file inside workspace')
    x=pipeline.read_json_file(p)
    if x.get('schema')!=INPUT_SCHEMA or x.get('mode')!=MODE: raise ValueError('unique Vokes/Crouch schema and mode required')
    return p,x

def prepare(base,input_path,*,_return_native=False):
    path,request=_source_request(input_path); parent=_parent(base,request)
    evidence=_source_membership(request)
    pkg=pipeline.read_json_file(base.package_path); jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if sha(jug)!=parent['jug_sha256'] or sha(eq)!=parent['eq_sha256']: raise ValueError('native full-file parent SHA changed')
    actors={x['carrier_id']:x for x in pkg['players']}; clubs={x['carrier_id']:x for x in pkg['clubs']}
    for person,info in (('vokes',V),('crouch',C)):
        submitted=request['actors'][person]; actor=actors.get(info['carrier'])
        if actor!=submitted['before'] or actor.get('id')!=f"english-player-{info['carrier']}" or actor.get('name')!=info['name'] or actor.get('source_name')!=info['name']:
            raise ValueError(f'{info["name"]}: exact full recipe identity preimage required')
        if actor.get('facts',{}).get('birth_date')!=info['dob'] or actor.get('club_id')!=f"english-club-{info['before_club']}":
            raise ValueError(f'{info["name"]}: exact DOB/current club recipe identity differs')
        if submitted.get('birth_date')!=info['dob'] or submitted.get('owners_before')!=[info['before_club']]:
            raise ValueError(f'{info["name"]}: source request identity/ownership assertion differs')
        facts=_native_order(jug,info['carrier'])[1]
        if facts.name!=info['native_name'] or facts.order!=info['order_before']:
            raise ValueError(f'{info["name"]}: native name or opening-order preimage differs')
        if native_facts(jug,info['carrier'])!=submitted['native_before']:
            raise ValueError(f'{info["name"]}: complete native identity/DOB/position/order preimage differs')
        shirt=request['shirt_targets'][person]
        if (actor['facts'].get('shirt_number')!=shirt['before_number']
            or shirt.get('native_name')!=info['native_name']
            or _native_shirt(jug,info['carrier'])[0]!=shirt['before_number']):
            raise ValueError(f'{info["name"]}: exact recipe/native shirt preimage differs')
    if native_owners(eq).get(7942)!={304} or native_owners(eq).get(10744)!={351}:
        raise ValueError('both carriers must have exact exclusive current owners')
    parsed=_rosters(eq,jug)
    target_rows={}
    for alias,cid,slot,pid,name in (('burnley',304,17,7942,'Peter CROUCH'),('stoke',351,13,10744,'Sam VOKES')):
        roster=parsed[cid][1]
        supplied=request['clubs'][alias]
        rows=[[r.player_record_id,r.flag] for r in roster.rows]
        if (roster.mode_byte!=0 or len(roster.rows)!=25 or supplied['mode']!=0 or supplied['row_count']!=25
            or supplied['native_rows_before']!=rows or supplied['recipe_before']!=clubs[cid]):
            raise ValueError(f'{alias}: exact complete 25-row mode-0 native/recipe preimage required')
        if any(r.flag!=0 for r in roster.rows) or len({r.player_record_id for r in roster.rows})!=25:
            raise ValueError(f'{alias}: all-zero flags and unique full roster required')
        row=roster.rows[slot-1]
        native_name=_native_order(jug,pid)[1].name
        if (row.player_record_id,row.flag)!=(pid,0) or native_name!=name:
            raise ValueError(f'{alias}: exact player/slot/flag/name target differs')
        target_rows[alias]={'eq_record_id':cid,'slot_number':slot,'player_record_id_before':pid,'flag':0,'player_name_before':name}
    for cid in (304,351):
        if not isinstance(clubs[cid].get('opening'),dict): raise ValueError('both clubs require explicit source opening structures')
    if ('english-player-7942' not in clubs[304]['opening'].get('substitute_player_ids',[])
        or 'english-player-10744' not in clubs[351]['opening'].get('substitute_player_ids',[])):
        raise ValueError('both affected actors must be existing opening substitutes; XI untouched')
    # Confirm the standard native editor writes only the two intended EQ links.
    # Every call above has just revalidated current request/source bytes and the
    # exact registered full-file preimages. Reuse only the deterministic native
    # postimage for byte-identical immutable JUG+EQ inputs; never cache admission.
    postjug,posteq=_native_apply_cached(jug,eq)
    eqdiff={i for i,(a,b) in enumerate(zip(eq,posteq)) if a!=b}
    jdiff={i for i,(a,b) in enumerate(zip(jug,postjug)) if a!=b}
    order_offsets={}; shirt_offsets={}
    for pid in (7942,10744):
        entry,field=_native_order(jug,pid); order_offsets[str(pid)]=entry.payload_offset+field.offset
        shirt_offsets[str(pid)]=_native_shirt(jug,pid)[1]
    expected_eq_offsets=set()
    for cid,slot,before,after in ((304,17,7942,10744),(351,13,10744,7942)):
        row=parsed[cid][1].rows[slot-1]
        before_bytes=before.to_bytes(4,'little'); after_bytes=after.to_bytes(4,'little')
        expected_eq_offsets.update(parsed[cid][0].payload_offset+row.raw_row_offset+1+i
                                   for i,(a,b) in enumerate(zip(before_bytes,after_bytes)) if a!=b)
    if eqdiff!=expected_eq_offsets:
        raise ValueError('native EQ writer escaped the differing bytes of the two player-ID fields')
    expected_jug_offsets=set(order_offsets.values())|set(shirt_offsets.values())
    if jdiff!=expected_jug_offsets: raise ValueError('native writer must change exactly two order and two shirt bytes')
    native_target_preimages={}
    jug_index=IndexedFDIFile.from_bytes(jug)
    for pid in (7942,10744):
        entry=next(e for e in jug_index.entries if e.record_id==pid)
        native_target_preimages[str(pid)]={'decoded_record_sha256':sha(entry.decode_payload(jug)),
          'native_facts':native_facts(jug,pid),'shirt_number':_native_shirt(jug,pid)[0]}
    plan={'schema':SCHEMA,'kind':KIND,'mode':MODE,'season':SEASON,'release_id':RELEASE,'parent':parent,
      'source_input':_binding(path),'evidence':evidence,'targets':target_rows,'native_order_offsets':order_offsets,
      'native_shirt_offsets':shirt_offsets,
      'native_target_preimages':native_target_preimages,
      'eq_changed_byte_offsets':sorted(expected_eq_offsets),
      'native_order_changes':[{'carrier_id':7942,'name':'Peter CROUCH','before':17,'after':13},
                              {'carrier_id':10744,'name':'Sam VOKES','before':13,'after':17}],
      'native_shirt_changes':[{'carrier_id':10744,'name':'Sam VOKES','before':10,'after':9},
                              {'carrier_id':7942,'name':'Peter CROUCH','before':15,'after':25}],
      'source_rows_before':{str(cid):[[r.player_record_id,r.flag] for r in parsed[cid][1].rows] for cid in (304,351)},
      'source_rows_after':{str(cid):[[r.player_record_id,r.flag] for r in parsed[cid][1].rows] for cid in (304,351)},
      'eq_preimage_sha256':sha(eq),'eq_postimage_sha256':sha(posteq),'jug_preimage_sha256':sha(jug),'jug_postimage_sha256':sha(postjug),
      'scope':'Only the two EQ player IDs, two native initial-order bytes, and two native shirt-number bytes, plus matching recipe club/roster/substitute references and those two shirt facts/proofs. Existing native player identities, DOBs, skills/ratings, photos, starting XIs, tactics, managers and all unrelated bytes preserved.',
      'caveat':'Date-scoped opening ownership correction; official January transfer list shows the later reciprocal transfer. Does not assert a season-long/final-date ownership fix.'}
    plan['source_rows_after']['304'][16]=[10744,0]; plan['source_rows_after']['351'][12]=[7942,0]
    plan['transaction_id']=sha(packages.canonical_json_bytes(plan))[:24]
    if _return_native: return plan,postjug,posteq
    return plan

@lru_cache(maxsize=1)
def _native_apply_cached(jug: bytes,eq: bytes):
    parsed=_rosters(eq,jug)
    with tempfile.TemporaryDirectory(prefix='vokes-crouch-exchange-') as td:
        eqp=Path(td)/'EQ98030.FDI'; jp=Path(td)/'JUG98030.FDI'; eqp.write_bytes(eq); jp.write_bytes(jug)
        edit_team_roster_eq_jug_linked(team_file=str(eqp),player_file=str(jp),eq_record_id=351,slot_number=13,player_record_id=7942,write_changes=True)
        edit_team_roster_eq_jug_linked(team_file=str(eqp),player_file=str(jp),eq_record_id=304,slot_number=17,player_record_id=10744,write_changes=True)
        out_eq=eqp.read_bytes()
    shirt_updates={10744:{'native_name':'Sam VOKES','before_number':10,'number':9},
                   7942:{'native_name':'Peter CROUCH','before_number':15,'number':25}}
    out_jug,shirt_changes=rewrite_indexed_native_shirt_numbers(jug,shirt_updates)
    if [(r['carrier_id'],r['before'],r['after']) for r in shirt_changes]!=[(7942,15,25),(10744,10,9)]:
        raise ValueError('native shirt API did not change the exact two published source numbers')
    replacements=[OrderReplacement(7942,'Peter CROUCH',17,13),OrderReplacement(10744,'Sam VOKES',13,17)]
    out_jug=patch_initial_orders(out_jug,replacements,allow_compact=True)
    reread=_rosters(out_eq,out_jug)
    if (reread[304][1].mode_byte!=0 or reread[351][1].mode_byte!=0
        or [[r.player_record_id,r.flag] for r in reread[304][1].rows][16]!=[10744,0]
        or [[r.player_record_id,r.flag] for r in reread[351][1].rows][12]!=[7942,0]
        or native_owners(out_eq).get(10744)!={304} or native_owners(out_eq).get(7942)!={351}):
        raise ValueError('EQ writer postimage does not establish the two exclusive destination owners')
    for pid,expected in ((7942,13),(10744,17)):
        if _native_order(out_jug,pid)[1].order!=expected:
            raise ValueError('native startup order does not match destination slot')
    for pid,expected in ((7942,25),(10744,9)):
        if _native_shirt(out_jug,pid)[0]!=expected:
            raise ValueError('native shirt byte does not match positive opening source row')
    return out_jug,out_eq

def _native_shirt(jug,cid):
    entry,field=_native_order(jug,cid); payload=entry.decode_payload(jug)
    if payload[2:5]!=bytes.fromhex('dd6361') or len(payload)<=7:
        raise ValueError('target shirt write requires full-layout dd6361 native header')
    if int.from_bytes(bytes(v^0x61 for v in payload[5:7]),'little')!=cid:
        raise ValueError('shirt header carrier ID does not match indexed carrier')
    return payload[7]^0x61,entry.payload_offset+7

def verify(base,plan):
    if plan.get('schema')!=SCHEMA or plan.get('kind')!=KIND or plan.get('mode')!=MODE: raise ValueError('unique schema/kind/mode required')
    path=registry.ROOT/plan['source_input']['path']
    if path.is_symlink() or registry.sha256_file(path)!=plan['source_input']['sha256']:
        raise ValueError('Vokes/Crouch source input bytes changed')
    rebuilt,postjug,posteq=prepare(base,path,_return_native=True)
    if rebuilt!=plan:
        raise ValueError('Vokes/Crouch source plan does not reproduce from exact parent and source inputs')
    return postjug,posteq

def bind(package,plan):
    validate_plan(plan)
    base=registry.load_registered_release(plan['season'],plan['release_id']); verify(base,plan)
    original=pipeline.read_json_file(base.package_path)
    if packages.canonical_json_bytes(package)!=packages.canonical_json_bytes(original): raise ValueError('bind requires exact complete registered package preimage')
    result=copy.deepcopy(package); actors={x['carrier_id']:x for x in result['players']}; clubs={x['carrier_id']:x for x in result['clubs']}
    actors[10744]['club_id']='english-club-304'; actors[7942]['club_id']='english-club-351'
    for pid,number in ((10744,9),(7942,25)):
        actors[pid]['facts']['shirt_number']=number
        actors[pid]['proof']={'artifact_id':artifact_id(plan),'grade':'source-receipt'}
        actors[pid]['fact_fallbacks']=[f for f in actors[pid].get('fact_fallbacks',[]) if f.get('field')!='shirt_number']
    _replace_one(clubs[304]['roster_player_ids'],'english-player-7942','english-player-10744')
    _replace_one(clubs[351]['roster_player_ids'],'english-player-10744','english-player-7942')
    _replace_one(clubs[304]['opening']['substitute_player_ids'],'english-player-7942','english-player-10744')
    _replace_one(clubs[351]['opening']['substitute_player_ids'],'english-player-10744','english-player-7942')
    aid=artifact_id(plan); artifacts=[a for a in result.get('artifacts',[]) if a.get('id')!=aid]
    artifacts.append({'id':aid,'kind':'season-input','relative_path':filename(plan),
      'sha256':sha(packages.canonical_json_bytes(plan)),'media_type':'application/json'})
    result['artifacts']=sorted(artifacts,key=lambda a:a['id'])
    for source_key,suffix,title in (
        ('vokes','burnley-source','Burnley opening substitute shirt row: Sam Vokes'),
        ('crouch','stoke-source','Stoke opening substitute shirt row: Peter Crouch')):
        sid=aid+'-'+suffix
        if any(x.get('id')==sid for x in result['sources']): raise ValueError('shirt evidence source ID already exists')
        report=plan['evidence']['positive_opening_memberships'][source_key]
        result['sources'].append({'id':sid,'title':title,'uri':report['report_url'],
          'proof_grade':'source-receipt','evidence_artifact_id':aid})
    proof_id='proof-'+aid
    if any(x.get('id')==proof_id for x in result['proofs']): raise ValueError('shirt proof ID already exists')
    result['proofs'].append({'id':proof_id,'artifact_id':aid,'grade':'source-receipt',
      'covers':['two-source-bound-opening-shirt-numbers-only; other player facts, skills, ratings and identities preserved']})
    for key in ('artifacts','sources','proofs'): result[key].sort(key=lambda a:a['id'])
    packages.validate_package(result)
    return result

def _replace_one(rows,old,new):
    if rows.count(old)!=1 or rows.count(new)!=0: raise ValueError('exact single recipe membership preimage required')
    rows[rows.index(old)]=new

def validate_plan(plan):
    if plan.get('schema')!=SCHEMA or plan.get('kind')!=KIND or plan.get('mode')!=MODE: raise ValueError('unique Vokes/Crouch transaction schema/mode required')
    if plan.get('native_order_changes')!=[{'carrier_id':7942,'name':'Peter CROUCH','before':17,'after':13},{'carrier_id':10744,'name':'Sam VOKES','before':13,'after':17}]: raise ValueError('exact reciprocal native order changes required')
    if plan.get('native_shirt_changes')!=[{'carrier_id':10744,'name':'Sam VOKES','before':10,'after':9},{'carrier_id':7942,'name':'Peter CROUCH','before':15,'after':25}]: raise ValueError('exact source-bound shirt changes required')
    if plan.get('targets',{}).get('burnley')!={'eq_record_id':304,'slot_number':17,'player_record_id_before':7942,'flag':0,'player_name_before':'Peter CROUCH'} or plan.get('targets',{}).get('stoke')!={'eq_record_id':351,'slot_number':13,'player_record_id_before':10744,'flag':0,'player_name_before':'Sam VOKES'}: raise ValueError('exact two EQ target rows required')
    if len(plan.get('source_rows_before',{}).get('304',[]))!=25 or len(plan.get('source_rows_before',{}).get('351',[]))!=25: raise ValueError('complete two-roster preimages required')
    for cid,slot,pid in ((304,17,10744),(351,13,7942)):
        before=plan['source_rows_before'][str(cid)]; after=plan['source_rows_after'][str(cid)]
        wanted=copy.deepcopy(before); wanted[slot-1]=[pid,0]
        if after!=wanted or any(flag!=0 for _,flag in after) or len({row[0] for row in after})!=25:
            raise ValueError('full roster postimage must contain exactly the reciprocal target substitution')
    if plan['source_rows_after']['304'][16]!=[10744,0] or plan['source_rows_after']['351'][12]!=[7942,0]: raise ValueError('post-roster references differ')

def apply(jug,eq,plan):
    validate_plan(plan); base=registry.load_registered_release(plan['season'],plan['release_id'])
    base_jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes(); base_eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if sha(base_jug)!=plan['jug_preimage_sha256'] or sha(base_eq)!=plan['eq_preimage_sha256']:
        raise ValueError('registered whole-file native preimage changed')
    expected_jug,expected_eq=verify(base,plan)
    if sha(expected_jug)!=plan['jug_postimage_sha256'] or sha(expected_eq)!=plan['eq_postimage_sha256']:
        raise ValueError('native editor/order APIs no longer reproduce prepared postimages')
    if (jug,eq) not in ((base_jug,base_eq),(expected_jug,expected_eq)):
        raise ValueError('accept complete paired native preimage or complete paired postimage only')
    return expected_jug,expected_eq

def reject_factory_recipe(package):
    if any(str(a.get('id','')).startswith(PREFIX) for a in package.get('artifacts',[])):
        raise ValueError('Vokes/Crouch dated ownership exchange requires source-bound reconstruction')

def reconstruction(previous,release_id):
    # Fail closed on SOURCE mode before resolving inherited locator paths.
    receipt_path=getattr(previous,'compiler_receipt_path',None)
    if receipt_path is None: return None
    receipt=pipeline.read_json_file(receipt_path)
    if receipt.get('compilation_mode')!=MODE: return None
    loc=getattr(previous,'locator',{})
    rel=loc.get('sourced_profile_assignment_plan_path')
    if not rel: raise ValueError('Vokes/Crouch SOURCE receipt lacks assignment-plan path')
    plan_path=(registry.ROOT/rel).resolve(); plan=pipeline.read_json_file(plan_path)
    if plan.get('schema')!=SCHEMA or plan.get('mode')!=MODE: raise ValueError('SOURCE artifact points to wrong unique schema/mode')
    base=registry.load_registered_release(plan['season'],plan['release_id']); verify(base,plan)
    if plan_path!=(previous.package_path.parent/filename(plan)).resolve() or registry.sha256_file(plan_path)!=receipt.get('original_profile_assignment_plan_sha256'):
        raise ValueError('SOURCE receipt assignment artifact path/SHA mismatch')
    package=pipeline.read_json_file(base.package_path)
    expected_package=bind(package,plan)
    if pipeline.read_json_file(previous.package_path)!=expected_package:
        raise ValueError('prior SOURCE package does not equal the source-bound ownership exchange')
    descriptor=previous.package_path.parent/'role-delta-input.json'
    expected_descriptor={'season':base.season,'release_id':base.release_id,
       'package_sha256':plan['parent']['package_sha256'],'jug_sha256':plan['parent']['jug_sha256'],
       'updates':[],'unresolved':[]}
    if pipeline.read_json_file(descriptor)!=expected_descriptor:
        raise ValueError('SOURCE role descriptor is not the exact inert descriptor')
    from scripts import publish_historical_role_delta_v1 as publisher
    publisher.publish(previous.season,descriptor,release_id=release_id,
      source_release_id=base.release_id,profile_assignment_plan_path=plan_path)
    rebuilt=registry.load_registered_release(previous.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path)!=expected_package:
        raise ValueError('SOURCE recipe replay differs from exact ownership exchange')
    return {'season':previous.season,'release_id':release_id,'complete_game_inventory_identical':True,
       'complete_recipe_identical':True,'compilation_mode':MODE}
