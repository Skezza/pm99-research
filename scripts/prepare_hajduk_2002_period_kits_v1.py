"""Period-labelled original home artwork, inspected without copying logos."""
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_pipeline_v2 as pipeline

URL='https://www.colours-of-football.com/colours03/scg/hajduk/hajduk_1.html'
IMAGE='https://www.colours-of-football.com/colours03/scg/hajduk/srb_hajduk_1_0203.png'


def catalogue():
    path,raw,binding=source_rows('hajduk-2002-original-period-kit-catalogue')
    receipt=pipeline.read_json_file(path.with_suffix('.source.json'))
    page=BeautifulSoup(raw,'html.parser')
    picture=page.select_one('img[src="srb_hajduk_1_0203.png"]')
    if (receipt['url']!=URL or page.title.get_text(' ',strip=True)!='FK Hajduk Kula Football Shirt Images'
            or picture is None or 'home kit 2002-2003' not in page.get_text(' ',strip=True)):
        raise ValueError('kit catalogue club/season/linked artwork differs')
    image_path,_,image_binding=source_rows('hajduk-2002-original-period-home-kit-artwork')
    image_receipt=pipeline.read_json_file(image_path.with_suffix('.source.json'))
    if image_receipt['url']!=IMAGE or urljoin(URL,picture['src'])!=IMAGE:
        raise ValueError('original home artwork link/receipt differs')
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2002,end_year=2003,label='2002/03'),
        rows=[dict(carrier_id=706,club_name='Hajduk Kula',status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style',style=dict(pattern='solid',
                colors=['white',[0,152,232]],shorts='white',sleeves='white',trim=[0,152,232])),
            source=dict(provider='original-period-labelled-kit-artwork',reviewed=True,
                evidence=[binding,dict(image_binding,url=IMAGE)],exact_artwork=False,
                review='ROOT inspected original home2002/03 artwork: white shirt and shorts with fine light-blue side seams/shorts hem. Factory solid-white template with blue trim; sponsor, logos and exact piping geometry omitted.',
                limitation='Period-labelled retrospective kit illustration, not an August match photograph or exact RGB certification.',
                attribution='Colours of Football / Mikhail Sipovich, original Hajduk Kula home2002-2003 artwork. Local research design reference only; not redistributed original artwork.'))])
