"""Capture missing sources and bind an existing complete Hyde proposal.

No game writes, source recrawl or publication. Completed raw responses are reused.
"""
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import prepare_paired_whole_club_dispositions_v1 as paired
from scripts.prepare_paired_whole_club_native_v1 import dated_manager_identity
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/Hyde2013-native-delivery-v1'
SOURCE=ROOT.parent/'whole-club-matchday-career-scan-20261017-r2/2013-14/3319-hyde.json'
SOURCES={
    'manager-1332.html':'https://www.soccerbase.com/teams/team.sd?team_id=1332&teamTabs=managers',
    'ground-2013-conference.html':'https://en.wikipedia.org/wiki/2013%E2%80%9314_Football_Conference',
    'programme-2013-hyde-luton.pdf':'https://cdn.hattersheritage.co.uk/2013-14%2BSeason%2BDONE%2FMatches%2FM5210%2BHyde%2Bv%2BLuton%2BTown%2FProgramme%2FProgramme.pdf',
}

def run():
    cache=ROOT/'source-cache';cache.mkdir(parents=True,exist_ok=True)
    for filename,url in SOURCES.items():
        path=cache/filename;receipt=path.with_name(filename+'.source.json')
        if path.exists():
            if not receipt.exists() or pipeline.read_json_file(receipt)!=dict(url=url,sha256=registry.sha256_file(path)):
                raise ValueError('existing original source lacks matching URL/body receipt')
            continue
        response=requests.get(url,timeout=45,headers={'User-Agent':'PM99 historical season research/1.0'})
        response.raise_for_status();body=response.content
        # Original archive HEAD declares 36,311,772 bytes for this programme;
        # keep a bounded 40MiB allowance, not an unlimited asset download.
        limit=(40 if filename.endswith('.pdf') else 3)*1024*1024
        if not body or len(body)>limit:raise ValueError('unexpected source size')
        if filename.endswith('.pdf') and not body.startswith(b'%PDF-'):raise ValueError('programme is not PDF')
        path.write_bytes(body);retained(receipt,dict(url=url,sha256=registry.sha256_file(path)))
        print(dict(original_source_captured=filename,bytes=len(body)),flush=True)
    manager,person=dated_manager_identity((cache/'manager-1332.html').read_bytes(),'2013-08-10')
    if manager!='Scott McNiven':raise ValueError('original dated manager differs')
    page=BeautifulSoup((cache/'ground-2013-conference.html').read_bytes(),'html.parser')
    rows=[r.get_text(' ',strip=True) for r in page.select('tr') if r.select_one('a[title="Hyde F.C."]') or
        r.select_one('a[title="Hyde United F.C."]')]
    if not any('Ewen Fields' in row for row in rows):raise ValueError('season stadium table does not bind Hyde to Ewen Fields')
    proposal=pipeline.read_json_file(SOURCE)
    current=registry.load_preferred_release('2013-14')
    if proposal['release_id']!=current.release_id:raise ValueError('current baseline advanced')
    pair=dict(schema_version=paired.SINGLETON_SCHEMA,season='2013-14',release_id=current.release_id,
        proposals=[dict(path=registry.relative_workspace_path(SOURCE),sha256=registry.sha256_file(SOURCE))],
        native_writes=0,registered=False,publication_authorised=False)
    pair['source_guard']=paired.source_guard(pair,[proposal]);retained(ROOT/'complete-singleton-source.json',pair)
    retained(ROOT/'manager-ground-source-proof.json',dict(manager=manager,numeric_manager_id=person,date='2013-08-10',
        ground='Ewen Fields',source_rows=rows,proposal_sha256=registry.sha256_file(SOURCE),
        kit_programme_visual_review_pending=True,native_writes=0))
    print(dict(source_group_ready=True,manager=manager,numeric_manager_id=person,native_writes=0),flush=True)

if __name__=='__main__':run()
