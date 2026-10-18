#!/usr/bin/env python3
"""Capture only queued English first-fixture gaps, without changing recipes.

Use stable provider IDs already recorded in source selections. Discover the
provider's actual season ID from its published dropdown, never year minus a
constant. Store originals/receipts outside existing source publications.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import parse_qs,urlparse,quote_plus

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from bs4 import BeautifulSoup
from scripts import prepare_duplicate_club_disposition_v1 as whole
from scripts import season_soccerbase_original_opening_v1 as original
from scripts import capture_ntf_historical_carrier_squads_v1 as acquisition
from scripts import capture_soccerbase_august_squads_v1 as facts
from scripts import season_pipeline_v2 as pipeline

LEAGUES={'Premier League','Football League Div 1','Football League Div 2','Football League Div 3',
    'Championship','Football League One','Football League Two','League One','League Two',
    'Conference','Football Conference','Conference National','National League','Blue Square Premier',
    'Blue Sq Premier','Nationwide Conference'}

# Exact historical provider labels, confirmed on the saved original club pages.
# Do not strip City/United/Rovers generically: that can join different clubs.
PROVIDER_ALIASES = {
    'Norwich City': ('Norwich',), 'Oxford United': ('Oxford',),
    'Southend United': ('Southend',), 'Tranmere Rovers': ('Tranmere',),
    'Mansfield Town': ('Mansfield',), 'Peterborough United': ('Peterborough',),
    'West Ham United': ('West Ham',), 'Brighton & Hove Albion': ('Brighton',),
    'Queens Park Rangers': ('QPR',), 'Bristol Rovers': ('Bristol R',),
    'Cambridge United': ('Cambridge U',), 'Doncaster Rovers': ('Doncaster',),
    'Rushden & Diamonds': ('Rushden',), 'Luton Town': ('Luton',),
    'Shrewsbury Town': ('Shrewsbury',), 'West Bromwich Albion': ('West Brom',),
    'Wigan Athletic': ('Wigan',), 'Bristol City': ('Bristol C',),
    'Nottingham Forest': ('Nottm Forest',), 'Wolverhampton Wanderers': ('Wolves',),
    # Exact labels in the saved original numeric provider catalogue. Historic
    # season, club-side and first-fixture checks remain mandatory after lookup.
    'Accrington Stanley': ('Accrington',), 'Rotherham United': ('Rotherham',),
    'Boreham Wood': ('Boreham W',), 'Harrogate Town': ('Harrogate',),
    'Maidenhead United': ('Maidenhead',), 'Solihull Moors': ('Solihull M',),
    'Welling United': ('Welling',), 'Yeovil Town': ('Yeovil',),
}


def provider_matches(published, target):
    return any(whole.club_keys(published)&whole.club_keys(name)
        for name in (target,*PROVIDER_ALIASES.get(target,())))


def reuse_original_profile(cache,id,url):
    target=cache.root/f'players/{id}.html'
    if target.exists():return
    for year in range(2000,2026):
        source=ROOT/'.local'/f'season-{year}-{str(year+1)[-2:]}'/'soccerbase-august-cache-v1'/'player'/f'{id}.html'
        receipt=source.with_suffix(source.suffix+'.source.json')
        if not source.is_file() or not receipt.is_file():continue
        metadata=json.loads(receipt.read_text())
        if metadata!={'url':url,'sha256':whole.registry.sha256_file(source)}:continue
        target.parent.mkdir(parents=True,exist_ok=True)
        os.link(source,target);os.link(receipt,target.with_suffix(target.suffix+'.source.json'))
        return


def resolve_provider(target,cache):
    if target['provider_team_id'] is not None:return target['provider_team_id'],None
    if target['provider_identity_candidates']:raise ValueError('previous stable provider identities conflict')
    url='https://www.soccerbase.com/teams/search_results.sd?type=team&search='+quote_plus(target['club'])
    raw=cache.get(url,'club-search.html');soup=BeautifulSoup(raw,'lxml')
    canonical=soup.select_one('link[rel="canonical"][href*="team_id="]');heading=soup.select_one('h1')
    label=re.sub(r'\s+Club details$','',heading.get_text(' ',strip=True) if heading else '')
    matches=set()
    links=[canonical] if canonical is not None else soup.select('a[href*="/teams/team.sd?team_id="]')
    for link in links:
        u=urlparse(link['href']);query=parse_qs(u.query);id=query.get('team_id',[])
        name=label if canonical is not None else link.get_text(' ',strip=True)
        if (u.netloc in ('','www.soccerbase.com') and u.path=='/teams/team.sd'
                and len(id)==1 and id[0].isdigit() and provider_matches(name,target['club'])):
            matches.add(int(id[0]))
    if not matches:
        # The site's full-name search often returns no results for its own
        # abbreviated labels. Use its original numeric autocomplete catalogue,
        # exact explicit aliases only. This remains identity discovery, never
        # historical squad membership or lifecycle approval.
        catalogue_url='https://www.soccerbase.com/js/autocomplete-teams.js.sd?1.1.38'
        source=ROOT/'.local/duplicate-ownership-v3/Soccerbase-primary-club-discovery-r1/autocomplete-teams.js'
        target_path=cache.root/'autocomplete-teams.js';receipt=source.with_suffix(source.suffix+'.source.json')
        if source.is_file() and receipt.is_file() and not target_path.exists():
            metadata=json.loads(receipt.read_text())
            if metadata!={'url':catalogue_url,'sha256':whole.registry.sha256_file(source)}:
                raise ValueError('original numeric club catalogue receipt changed')
            target_path.parent.mkdir(parents=True,exist_ok=True)
            os.link(source,target_path);os.link(receipt,target_path.with_suffix(target_path.suffix+'.source.json'))
        raw=cache.get(catalogue_url,'autocomplete-teams.js')
        text=raw.decode() if isinstance(raw,bytes) else raw
        data=re.search(r'teamsData\s*=\s*(\[\[.*?\]\])\s*;',text)
        if data is None:raise ValueError('original club catalogue lacks exact numeric array')
        wanted=set().union(*(whole.club_keys(name) for name in
            (target['club'],*PROVIDER_ALIASES.get(target['club'],()))))
        selected=[(name,id) for name,id in json.loads(data.group(1))
            if type(id) is int and id>0 and whole.roster.normalise(name) in wanted]
        matches={id for _,id in selected}
        if len(matches)==1:
            return next(iter(matches)),{'url':catalogue_url,'published_names':[n for n,_ in selected],
                'method':'original-exact-alias-numeric-catalogue-followed-by-dated-season-and-fixture-checks'}
    if len(matches)!=1:raise ValueError('exact country-scoped provider search did not identify one club')
    return next(iter(matches)),{'url':url,'published_name':label,'method':'original-exact-name-search-followed-by-dated-season-and-numeric-fixture-checks'}


def selectors(value):
    if isinstance(value,dict):
        if value.get('soccerbase_team_id') and value.get('club_name'):yield value
        for child in value.values():yield from selectors(child)
    elif isinstance(value,list):
        for child in value:yield from selectors(child)


def discover_targets(queue):
    wanted=collections.defaultdict(dict)
    for row in queue:
        if row['reason']!='an-affected-club-lacks-a-verified-opening-source':continue
        for c in row['candidates']:
            id=c['club_id'];carrier=int(id.rsplit('-',1)[1])
            if id.startswith('english-club-') or 3300<=carrier<=3331:
                wanted[row['season']].setdefault(c['club'],set()).add(c['club_id'])
    result=[]
    for season,clubs in sorted(wanted.items()):
        published=[]
        for path in sorted((ROOT/'.local'/('season-'+season)).glob('*opening*json')):
            doc=json.loads(path.read_text());published.extend(selectors(doc))
            for c in doc.get('clubs',[]):
                source=c.get('source_path','');m=re.fullmatch(r'soccerbase/team/(\d+)/august',source)
                if m:published.append({'club_name':c['club_name'],'soccerbase_team_id':int(m.group(1))})
        nonleague=ROOT/'.local'/('season-'+season)/'soccerbase-august-english-nonleague-v1.json'
        if nonleague.is_file():
            for c in json.loads(nonleague.read_text())['clubs']:
                m=re.fullmatch(r'soccerbase/team/(\d+)/august',c['source_path'])
                if m:published.append({'club_name':c['club_name'],'soccerbase_team_id':int(m.group(1))})
        by_name=collections.defaultdict(set)
        unique={(str(p['club_name']),int(p['soccerbase_team_id'])) for p in published}
        for published_name,team in sorted(unique):
            for key in whole.club_keys(published_name):by_name[key].add(team)
        for name,ids in sorted(clubs.items()):
            matches=set().union(*(by_name[key] for key in whole.club_keys(name)))
            result.append({'season':season,'club':name,'native_club_ids':sorted(ids),
                'provider_team_id':next(iter(matches)) if len(matches)==1 else None,
                'provider_identity_candidates':sorted(matches)})
    return result


def capture(target,root,offline,prior_roots=()):
    season=target['season'];year=int(season[:4])
    directory=root/season/whole.roster.normalise(target['club'])
    output=directory/'capture.json'
    if not directory.exists():
        for prior in prior_roots:
            previous=prior/season/whole.roster.normalise(target['club'])
            prior_capture=previous/'capture.json'
            if not prior_capture.is_file():continue
            saved=json.loads(prior_capture.read_text())
            if saved['target']!=target:raise ValueError('previous target capture differs from exact new scope')
            for proof in saved['raw_sources']:
                if whole.registry.sha256_file(ROOT/proof['path'])!=proof['sha256']:raise ValueError('previous original changed')
                if whole.registry.sha256_file(ROOT/proof['receipt_path'])!=proof['receipt_sha256']:raise ValueError('previous receipt changed')
            directory.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(previous,directory,copy_function=os.link)
            break
    if output.exists():
        saved=json.loads(output.read_text())
        if saved['target']!=target:raise ValueError('immutable target capture changed')
        for proof in saved['raw_sources']:
            if whole.registry.sha256_file(ROOT/proof['path'])!=proof['sha256']:raise ValueError('saved source changed')
            if whole.registry.sha256_file(ROOT/proof['receipt_path'])!=proof['receipt_sha256']:raise ValueError('saved receipt changed')
        return saved
    cache=acquisition.Cache(directory/'originals',offline=offline,delay=.3,stop_on_http_block=True)
    team,discovery=resolve_provider(target,cache)
    url=f'https://www.soccerbase.com/teams/team.sd?team_id={team}&season_id=0&teamTabs=results'
    raw=cache.get(url,'discovery.html');soup=BeautifulSoup(raw,'lxml')
    heading=soup.select_one('h1')
    name=re.sub(r'\s+Results$','',heading.get_text(' ',strip=True) if heading else '')
    if not provider_matches(name,target['club']):raise ValueError('published club name does not match scoped aliases')
    options=[o for o in soup.select('select#seasonSelect option') if o.get_text(' ',strip=True)==f'{year}/{year+1}']
    if len(options)!=1 or not str(options[0].get('value','')).isdigit():raise ValueError('historical season lacks exact published provider ID')
    provider_season=int(options[0]['value'])
    url=f'https://www.soccerbase.com/teams/team.sd?team_id={team}&season_id={provider_season}&teamTabs=results'
    raw=cache.get(url,'team.html');soup=BeautifulSoup(raw,'lxml')
    leagues={x.get_text(' ',strip=True) for x in soup.select('td.tournament a')}&LEAGUES
    if len(leagues)!=1:raise ValueError('historical club requires one recognised league competition: '+str(sorted(leagues)))
    competition=next(iter(leagues));fixture=original.first_fixture(raw,team,season,competition,name,url,
        allow_later_unscored=True)
    match_url=f"https://www.soccerbase.com/matches/additional_information.sd?id_game={fixture['game_id']}"
    match_raw=cache.get(match_url,'match.html');sheet=original.match(match_raw,fixture,team,match_url,True)
    people=[];biographies=[]
    for field in ('starting_xi','published_bench'):
        for row in sheet[field]:
            id=row['provider_player_id'];profile_url=f'https://www.soccerbase.com/players/player.sd?player_id={id}'
            reuse_original_profile(cache,id,profile_url)
            raw=cache.get(profile_url,f'players/{id}.html');bio=original.profile(raw,row,profile_url)
            player=facts.player_profile(raw,fallback_name=bio['name'],fallback_position=row['position'])
            player.update(name=bio['name'],birth_date=bio['birth_date'],position=row['position'])
            people.append(player);biographies.append({'membership':field,'original_match_row':row,'original_biography':bio})
    proofs=[]
    for item in cache.used:
        path=cache.root/item['cache_path'];receipt=path.with_suffix(path.suffix+'.source.json')
        # Acquisition Cache snapshots already carry its key, not a workspace path.
        proofs.append({'path':whole.registry.relative_workspace_path(path),'sha256':whole.registry.sha256_file(path),
            'receipt_path':whole.registry.relative_workspace_path(receipt),'receipt_sha256':whole.registry.sha256_file(receipt),'url':item['url']})
    return {'schema_version':'pm99-targeted-original-Soccerbase-first-fixture-capture-v1',
        'target':target,'fixture':fixture,'competition':competition,'provider_season_id':provider_season,
        'first_fixture_policy':original.LATER_SCORE_POLICY,
        'published_club_name':name,'provider_team_id':team,'provider_identity_discovery':discovery,
        'original_match':sheet,'people':people,'biographies':biographies,
        'raw_sources':proofs,'cache_root':whole.registry.relative_workspace_path(cache.root),
        'native_writes':0,'recipes_modified':0,'historical_ownership_approved':False}


def run(queue_path,root,offline=False,limit=None,prior_roots=(),summary_output=None):
    if summary_output is not None and summary_output.exists():
        raise ValueError('revised source collection summary is immutable')
    root.mkdir(parents=True,exist_ok=True)
    targets=discover_targets(json.loads(queue_path.read_text()))
    if limit is not None:targets=targets[:limit]
    scope={'queue_path':whole.registry.relative_workspace_path(queue_path),'queue_sha256':whole.registry.sha256_file(queue_path),
        'targets':targets,'native_writes':0,'recipes_modified':0}
    scope_path=root/'scope.json'
    if scope_path.exists():
        if json.loads(scope_path.read_text())!=scope:raise ValueError('target scope changed')
    else:pipeline.write_canonical_json(scope_path,scope)
    outcomes=[]
    for target in targets:
        if shutil.disk_usage(root).free<8*1024**3+64*1024**2:raise ValueError('source capture would breach disk reserve')
        try:
            result=capture(target,root,offline,prior_roots)
            output=root/target['season']/whole.roster.normalise(target['club'])/'capture.json'
            if not output.exists():pipeline.write_canonical_json(output,result)
            result={'target':target,'status':'original-first-fixture-and-biographies-reparsed',
                'capture_path':whole.registry.relative_workspace_path(output),'capture_sha256':whole.registry.sha256_file(output)}
        except (ValueError,OSError) as exc:
            result={'target':target,'status':'source-gap','reason':str(exc)}
        outcomes.append(result);print(json.dumps(result),flush=True)
    summary=summary_output or root/'summary.json'
    if not summary.exists():pipeline.write_canonical_json(summary,{'scope':scope,'outcomes':outcomes,
        'status_counts':dict(collections.Counter(r['status'] for r in outcomes)),'native_writes':0,'recipes_modified':0})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--queue',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--offline',action='store_true');p.add_argument('--limit',type=int)
    p.add_argument('--reuse-root',type=Path,action='append',default=[])
    p.add_argument('--summary-output',type=Path,
        help='New immutable outcome receipt for a gap-only continuation reusing the same raw cache')
    a=p.parse_args();run(a.queue,a.root,a.offline,a.limit,a.reuse_root,a.summary_output)
