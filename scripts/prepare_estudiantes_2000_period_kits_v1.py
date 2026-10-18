"""Historical traditional colours, explicitly NOT exact target-year artwork."""
from bs4 import BeautifulSoup
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_pipeline_v2 as pipeline

URL='https://es.wikipedia.org/wiki/Estudiantes_de_M%C3%A9rida_F%C3%BAtbol_Club'


def catalogue():
    path,raw,binding=source_rows('estudiantes-original-historical-club-colours')
    if pipeline.read_json_file(path.with_suffix('.source.json'))['url']!=URL:
        raise ValueError('historical colour source belongs to another club')
    text=BeautifulSoup(raw,'html.parser').get_text(' ',strip=True)
    if 'camiseta a rayas rojas y blancas, pantalón color azul' not in text:
        raise ValueError('historical traditional colours changed')
    return dict(schema_version='pm99-season-kit-catalogue-v1',season=dict(start_year=2000,end_year=2001,label='2000/01'),
        rows=[dict(carrier_id=2953,club_name='Estudiantes de Mérida',status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style',style=dict(pattern='vertical_stripes',
                colors=[[184,24,32],[240,240,240]],shorts=[24,48,104],sleeves=[184,24,32],trim='white',stripe_count=3)),
            source=dict(provider='historical-traditional-club-colours-explicit-editorial-fallback',reviewed=True,
                evidence=[dict(binding,url=URL)],exact_artwork=False,target_season_artwork_verified=False,
                review='Original historical-club article explicitly describes red/white stripes and blue shorts. Factory shading template uses those traditional colours; stripe count, sleeves, sponsor and exact RGB are editorial.',
                limitation='Target2000 FKA acquisition unavailable; period photo links dead. NOT claimed a viewed target-season kit photo or exact2000 design.',
                attribution='Wikipedia contributors, Estudiantes de Merida historical club colours; text-derived editorial design only, no original artwork redistributed.'))])
