"""Period home colours from the original May2015 photo republished18July.

Not the green away kit worn at the first fixture. Original photography remains
research evidence only; all three game bitmap sizes use the factory renderer.
"""
from bs4 import BeautifulSoup

from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry


def catalogue():
    _,raw,binding=source_rows('tachira-2015-first-second-week-club-press')
    page=BeautifulSoup(raw,'html.parser')
    text=page.get_text(' ',strip=True)
    if 'Fecha: Domingo 19/07/2015.' not in text or 'Prensa Deportivo Táchira' not in text:
        raise ValueError('original opening-period club-press date/attribution missing')
    photos=page.select('.post-body img')
    if len(photos)!=2 or '170515' not in photos[0].get('src',''):
        raise ValueError('original labelled May2015 home photograph missing')
    photo=ROOT.parent/'tachira-2015-kit-originals/tachira-2015-first-second-week-club-press-1.jpg'
    receipt=pipeline.read_json_file(photo.with_name(photo.name+'.source.json'))
    if receipt!=dict(url=photos[0]['src'],sha256=registry.sha256_file(photo)):
        raise ValueError('retained original home-kit photograph URL/hash changed')
    return dict(schema_version='pm99-season-kit-catalogue-v1',season=dict(start_year=2015,end_year=2016,label='2015/16'),
        rows=[dict(carrier_id=2953,club_name='Deportivo Tachira',status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style',style=dict(pattern='vertical_stripes',
                colors=[[232,212,0],'black'],shorts='black',sleeves='black',trim=[232,212,0],stripe_count=3)),
            source=dict(provider='original-May2015-home-photo-republished-opening-week',reviewed=True,
                evidence=[dict(path=registry.relative_workspace_path(photo),**receipt),binding],exact_artwork=False,
                review='ROOT inspected original17May2015-labelled photograph republished by club press18July2015: outfield Táchira in yellow/black vertical-striped shirts, black sleeves with yellow shoulder stripes, black shorts with yellow trim. The second image is a green goalkeeper, not the outfield template. Home default uses this positively period-labelled design, not green away11July. Specific stripe panels, Adidas marks, sponsor and sleeve detailing simplified; no claim every later match wore this exact shirt.',
                attribution='Prensa Deportivo Táchira / Café Deportivo18July2015, original linked May2015 JPEG retained as local design evidence, not game photography.'))])
