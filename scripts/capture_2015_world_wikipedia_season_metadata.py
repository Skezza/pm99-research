#!/usr/bin/env python3
"""Capture exact 2015/16 club-season infobox facts from MediaWiki revisions.

Only deterministic title forms are requested. A response is accepted only if
its infobox season is 2015/16 and its club label has either the existing
strict FootballSquads club key or a declared presentation-only title form
(for example, ``Barcelona`` -> ``FC Barcelona``). Search merely discovers
pages to test against that predicate; rank, aliases and near-name guesses are
never used as an identity decision.
"""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__('sys').path: __import__('sys').path.insert(0,str(ROOT))
from scripts.audit_world_2015_source_coverage import strict_club_key

SCHEMA='pm99-world-2015-wikipedia-season-metadata-v1'; DRAFT_SCHEMA='pm99-world-2015-source-carrier-drafts-v1'; API='https://en.wikipedia.org/w/api.php'; USER_AGENT='PM99RE-source-research/1.0 (https://github.com/openai/codex; source-research@example.invalid)'
class CaptureError(ValueError): pass
def canonical_json_bytes(v: Any)->bytes: return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def _clean(v:str)->str:
 v=re.sub(r'<!--.*?-->','',v,flags=re.S); v=re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]',r'\2',v); v=re.sub(r'\[\[([^\]]+)\]\]',r'\1',v); v=re.sub(r'{{[^{}]*}}','',v); return re.sub(r'<[^>]+>','',v).strip()
def _infobox(content:str)->dict[str,str]:
 m=re.search(r'{{\s*Infobox football club season\b(.*?)(?:\n}})',content,re.I|re.S)
 if not m:return {}
 return {key.casefold().strip():_clean(value) for key,value in re.findall(r'^\s*\|\s*([^=\n]+?)\s*=\s*(.*?)\s*$',m.group(1),re.M)}
def _fetch(title:str)->dict[str,Any]|None:
 q=urlencode({'action':'query','format':'json','formatversion':'2','prop':'revisions','rvprop':'ids|timestamp|content','rvslots':'main','titles':title,'redirects':'1'})
 try:
  raw=urlopen(Request(API+'?'+q,headers={'User-Agent':USER_AGENT}),timeout=25).read(); data=json.loads(raw)
 except Exception:return None
 pages=(data.get('query') or {}).get('pages') or []
 if len(pages)!=1 or pages[0].get('missing') or not (pages[0].get('revisions') or []):return None
 revision=pages[0]['revisions'][0]; content=((revision.get('slots') or {}).get('main') or {}).get('content','')
 return {'title':pages[0].get('title'),'pageid':pages[0].get('pageid'),'revid':revision.get('revid'),'timestamp':revision.get('timestamp'),'content_sha256':hashlib.sha256(content.encode()).hexdigest(),'infobox':_infobox(content)}
def _search_titles(name:str)->list[str]:
 q=urlencode({'action':'query','format':'json','formatversion':'2','list':'search','srnamespace':'0','srlimit':'8','srsearch':f'"{name}" "2015" season'})
 try:data=json.loads(urlopen(Request(API+'?'+q,headers={'User-Agent':USER_AGENT}),timeout=25).read())
 except Exception:return []
 return sorted({str(row.get('title') or '') for row in (data.get('query') or {}).get('search') or [] if row.get('title')})

def _declared_title_labels(name: str) -> list[str]:
 """Return exact, presentation-only title variants; this is not fuzzy match."""
 # These are conventional decoration forms found in English Wikipedia season
 # titles.  The source label itself remains the primary identity.  A page can
 # only be accepted when its infobox club equals one of these explicit labels.
 bare = name.strip()
 # Keep the request set bounded: the API search is the fallback discovery
 # mechanism and validation below remains exact against these labels.
 return list(dict.fromkeys([bare, f"FC {bare}", f"F.C. {bare}", f"{bare} FC", f"{bare} F.C.", f"{bare} C.F."]))

def _season_title_candidates(name: str) -> list[str]:
 labels = _declared_title_labels(name)
 # English Wikipedia's established season-title convention is prefix-first.
 # The ASCII fallback handles redirects without multiplying network requests.
 return [candidate for label in labels for candidate in (f"2015–16 {label} season", f"2015-16 {label} season")]
def _one(proposal:Mapping[str,Any])->dict[str,Any]:
 cid=int(proposal['carrier_id']); name=str(proposal['source_club_name']); key=strict_club_key(name)
 declared_labels = _declared_title_labels(name)
 allowed_keys={strict_club_key(label) for label in declared_labels}
 candidates=_season_title_candidates(name)
 matches=[]
 def consider(title: str) -> None:
  """Append only a season/page/declared-label exact result."""
  got=_fetch(title)
  if not got:return
  box=got['infobox']; season=str(box.get('season','')).replace('-','–')
  club=_clean(box.get('club',''))
  if season not in {'2015–16','2015–2016'} or strict_club_key(club) not in allowed_keys:return
  manager=box.get('manager') or box.get('head coach') or None; stadium=box.get('stadium') or box.get('ground') or None; capacity=box.get('capacity') or None
  matches.append((title,got,manager,stadium,capacity))
 for title in dict.fromkeys(candidates):
  consider(title)
  # The primary direct strict-key title is sufficient; other spelling forms
  # cannot improve its source identity and would only create API load.
  if matches and strict_club_key(_clean(matches[0][1]['infobox'].get('club','')))==key:break
 if not matches:
  # API search is discovery only and runs only after every direct deterministic
  # season title form failed. Search rank is never applied as an identity key.
  for title in _search_titles(name): consider(title)
 unique={int(item[1]['pageid']):item for item in matches}
 matches=list(unique.values())
 if len(matches)==1:
  title,got,manager,stadium,capacity=matches[0];return {'carrier_id':cid,'source_club_name':name,'strict_club_key':key,'status':'exact-season-infobox-match','requested_title':title,'accepted_infobox_club_label':_clean(got['infobox'].get('club','')),'identity_method':'strict-club-key' if strict_club_key(_clean(got['infobox'].get('club','')))==key else 'declared-presentation-only-title-form','page':got,'facts':{'manager':manager,'stadium':stadium,'capacity':capacity,'capacity_scope':'season-infobox' if capacity else 'unavailable'}}
 status='requires-review-ambiguous-exact-season-infobox-match' if len(matches)>1 else 'requires-review-no-exact-2015-16-season-infobox-match'
 return {'carrier_id':cid,'source_club_name':name,'strict_club_key':key,'status':status,'requested_titles':candidates}
def build(draft:Mapping[str,Any])->dict[str,Any]:
 if draft.get('schema_version')!=DRAFT_SCHEMA:raise CaptureError('source draft schema is unsupported')
 selected=sorted((p for p in draft.get('proposals',[]) if isinstance(p,dict) and p.get('status')=='source-squad-ready'),key=lambda p:int(p['carrier_id']))
 if not selected:raise CaptureError('source draft has no source-squad-ready carriers')
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool: rows=list(pool.map(_one,selected))
 matched=[r for r in rows if r['status']=='exact-season-infobox-match']
 return {'schema_version':SCHEMA,'policy':'deterministic-season-title-forms; strict-season-and-declared-club-label-validation; search-discovery-only; no-fuzzy-apply; source-facts-only','sources':{'source_draft_sha256':hashlib.sha256(canonical_json_bytes(draft)).hexdigest(),'mediawiki_api':API},'coverage':{'source_ready_carrier_count':len(rows),'exact_season_infobox_match_count':len(matched),'declared_presentation_title_form_match_count':sum(r.get('identity_method')=='declared-presentation-only-title-form' for r in matched),'manager_fact_count':sum(bool(r['facts']['manager']) for r in matched),'stadium_fact_count':sum(bool(r['facts']['stadium']) for r in matched),'season_scoped_capacity_fact_count':sum(bool(r['facts']['capacity']) for r in matched)},'rows':rows}
def main()->int:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-draft',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();raw=a.source_draft.read_bytes();draft=json.loads(raw.decode());
 if raw!=canonical_json_bytes(draft):p.error('source draft must be canonical JSON')
 try:r=build(draft)
 except CaptureError as e:p.error(str(e))
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_json_bytes(r));print(json.dumps(r['coverage'],sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
