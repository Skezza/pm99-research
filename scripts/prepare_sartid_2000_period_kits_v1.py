"""Explicit adjoining2002 artwork fallback, never target2000 certification."""
from bs4 import BeautifulSoup
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_pipeline_v2 as pipeline

URL='https://www.colours-of-football.com/colours03/scg/sartid/sartid_1.html'
IMAGE='https://www.colours-of-football.com/colours03/scg/sartid/srb_sartid_1_0203.png'


def catalogue():
    path,raw,binding=source_rows('sartid-original-period-kit-catalogue')
    receipt=pipeline.read_json_file(path.with_suffix('.source.json'))
    page=BeautifulSoup(raw,'html.parser')
    if (receipt['url']!=URL or page.select_one('img[src="srb_sartid_1_0203.png"]') is None
            or 'home kit 2002-2003' not in page.get_text(' ',strip=True)):
        raise ValueError('adjoining original Sartid kit source differs')
    image_path,raw,image_binding=source_rows('sartid-original-home-2002-artwork')
    if (pipeline.read_json_file(image_path.with_suffix('.source.json'))['url']!=IMAGE
            or not raw.startswith(b'\x89PNG\r\n\x1a\n')):
        raise ValueError('original linked Sartid artwork differs')
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2000,end_year=2001,label='2000/01'),
        rows=[dict(carrier_id=706,club_name='Sartid Smederevo',status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style',style=dict(pattern='solid',
                colors=[[0,48,104],[0,144,216]],shorts=[0,48,104],sleeves=[0,48,104],trim='white')),
            source=dict(provider='adjoining-season-colour-reference-explicit-editorial-fallback',reviewed=True,
                evidence=[binding,dict(image_binding,url=IMAGE)],exact_artwork=False,
                target_season_artwork_verified=False,reference_publication_year=2002,
                review='ROOT inspected original2002/03 illustration: dark-blue shirt/shorts, lighter-blue thin vertical panels with white edges. Simplified solid factory template with blue colour and white trim, not exact stripe/sponsor reconstruction.',
                limitation='Target2000/01 artwork unavailable; two-years-later illustration is an explicitly declared editorial colour fallback, not target-season evidence.',
                attribution='Colours of Football / Mikhail Sipovich, original Sartid home2002/03 illustration. Local design reference only; original artwork not redistributed.'))])
