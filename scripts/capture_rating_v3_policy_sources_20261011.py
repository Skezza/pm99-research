"""Pin original small biography/dated achievement pages, never image downloads."""
import requests
from scripts import season_rating_calibration_v3 as policy
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

SOURCES=(('messi','https://en.wikipedia.org/wiki/Lionel_Messi','Lionel'),
    ('wilson','https://en.wikipedia.org/wiki/Josh_Wilson-Esbrand','Joshua'),
    ('yamal2024','https://www.uefa.com/uefaeuro/history/news/028f-1b5e5e91b6e6-b9784b9e13fb-1000--lamine-yamal-named-euro-2024-young-player-of-the-tournament/','2024'),
    ('yamal2025','https://penyes.fcbarcelona.com/en/news/4308882/lamine-yamal-reaches-18-years-of-age-as-a-record-breaker','2025'))

def main():
    root=policy.ROOT/'sources';root.mkdir(parents=True,exist_ok=True);rows=[]
    for label,url,token in SOURCES:
        path=root/(label+'.html')
        if not path.exists():
            response=requests.get(url,headers={'User-Agent':'PM99 historical recipe research source receipt/1.0'},timeout=45)
            response.raise_for_status()
            if token not in response.text:raise ValueError('wrong/blocked policy source page')
            path.write_bytes(response.content)
        rows.append(dict(label=label,url=url,path=policy.registry.relative_workspace_path(path),sha256=policy.registry.sha256_file(path),
            purpose='identity/dated achievements; NOT numerical rating authority'))
    retained(policy.ROOT/'dated-policy-sources.json',dict(sources=rows))

if __name__=='__main__':main()
