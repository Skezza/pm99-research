"""Factory-style blue/white hoops from original club artwork and May2001 photo."""
from bs4 import BeautifulSoup
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry


def catalogue():
    _, raw, binding = source_rows('italchacao-2001-original-official-club-facts')
    page = BeautifulSoup(raw,'html.parser')
    if not page.select_one('img[src="ItalChacaoADIDAS.gif"]') or not page.select_one('img[src="EQUIPO2001.jpg"]'):
        raise ValueError('original kit artwork/photo links missing')
    evidence = [binding]
    for key, name in [('italchacao-2001-original-official-kit-gif','ItalChacaoADIDAS.gif'),
            ('italchacao-2001-original-official-may-team-photo','EQUIPO2001.jpg')]:
        path, _, item = source_rows(key)
        receipt = pipeline.read_json_file(path.with_suffix('.source.json'))
        if receipt['url'] != 'https://www.geocities.ws/mchataing/'+name:
            raise ValueError('original linked kit/photo URL differs')
        evidence.append(dict(item,url=receipt['url']))
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2001,end_year=2002,label='2001/02'),
        rows=[dict(carrier_id=2953,club_name='Deportivo Italchacao',status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style',style=dict(pattern='hoops',
                colors=[[24,40,152],'white'],shorts=[24,40,152],sleeves=[24,40,152],trim='white',stripe_count=3)),
            source=dict(provider='original-period-club-artwork-and-May2001-team-photograph',reviewed=True,
                evidence=evidence,exact_artwork=False,
                review='ROOT inspected original Adidas strip GIF and captioned May2001 team photo: blue shirt with broad white horizontal hoops, blue shorts, white sleeve trim. Simplified factory renderer; sponsors, stars, fine Adidas stripes and exact RGB not certified.',
                limitation='May2001 adjoining-period strip, not proof that identical artwork was worn in the August cup. Explicit V1 colour/pattern fallback.',
                attribution='Deportivo ItalChacao official2000/2001 site / Manuel De Oliveira. Original images are local design evidence, not redistributed artwork.'))])
