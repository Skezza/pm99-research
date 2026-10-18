"""Small original-source capture for the Eastleigh2014 complete-club repair."""
from datetime import UTC,datetime
from urllib.request import Request,urlopen
from bs4 import BeautifulSoup
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts.supplement_soccerbase_opening_lineups_v1 import Cache
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/Eastleigh2014-assets-v1'


def main():
    if (ROOT/'capture-summary.json').exists():raise ValueError('completed captures must not repeat')
    cache=Cache(ROOT/'source-cache',offline=False,delay=1)
    targets=(('kit-launch.html','https://eastleighfc.blogspot.com/2014/06/eastleigh-fc-and-joma-reveal-new-201415.html'),
        ('ground-original-3322.html','https://www.skysports.com/football/eastleigh-vs-aldershot-town/319716'))
    rows=[]
    for name,url in targets:
        raw=cache.get(url,name);path=ROOT/'source-cache'/name
        receipt=path.with_name(name+'.source.json')
        expected=dict(url=url,sha256=registry.sha256_file(path))
        if receipt.exists():
            if pipeline.read_json_file(receipt)!=expected:raise ValueError('retained original capture changed')
        else:retained(receipt,expected)
        page=BeautifulSoup(raw,'lxml');text=page.get_text(' ',strip=True)
        if name=='ground-original-3322.html' and any(a not in text for a in ('Eastleigh','Aldershot','14th August 2014','Silverlake Stadium')):
            raise ValueError('original ground source lacks dated target match')
        if name=='kit-launch.html' and any(a not in text for a in ('2014/15','royal blue and white','Joma')):
            raise ValueError('original launch lacks period/colour/manufacturer')
        images=[dict(src=i.get('src'),alt=i.get('alt')) for i in page.select('img[src]')]
        if name=='kit-launch.html':
            home=[i['src'] for i in images if i['src'].endswith('/Home+Kit+2014+2015.jpg')]
            if len(home)!=1:raise ValueError('original launch must identify one period home image')
            photo=ROOT/'source-cache/home-2014-15.jpg'
            if not photo.exists():
                with urlopen(Request(home[0],headers={'User-Agent':'PM99HistoricalResearch/1.0'}),timeout=30) as response:
                    data=response.read(2*1024*1024+1)
                if len(data)>2*1024*1024:raise ValueError('period kit image exceeds bounded size')
                photo.write_bytes(data)
            if not photo.with_name(photo.name+'.source.json').exists():
                retained(photo.with_name(photo.name+'.source.json'),dict(url=home[0],sha256=registry.sha256_file(photo)))
        row=dict(name=name,url=url,path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path),images=images)
        rows.append(row);print(dict(name=name,bytes=len(raw),images=images[:12]),flush=True)
    retained(ROOT/'capture-summary.json',dict(utc=datetime.now(UTC).isoformat(),rows=rows,
        native_writes=0,optional_reference_not_used='Football Kit Archive original download returned403; no bypass/retry needed because original dated launch and image are available.',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',machine='joe-Vostro-3350'))


if __name__=='__main__':main()
