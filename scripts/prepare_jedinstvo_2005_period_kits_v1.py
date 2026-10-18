"""Observed opening-match blue/white strip, not a certified home-kit claim.

The retained original8August2005 colour newspaper shows Trifunovic against
Partizan. Use the observed strip as an explicit V1 default; its home/away
classification and exact sponsor/panel artwork remain an editorial limitation.
"""
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.capture_original_borba_page_v1 import original_download_url
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry


def catalogue():
    key='jedinstvo-borba-2005-08-08-page10'
    _,raw,binding=source_rows(key)
    photo=ROOT.parent/'borba-original-scans'/f'{key}.jpg'
    receipt=pipeline.read_json_file(photo.with_name(photo.name+'.source.json'))
    if (receipt['url']!=original_download_url(raw) or receipt['source_binding']!=binding
            or receipt['sha256']!=registry.sha256_file(photo)):
        raise ValueError('observed original opening strip photograph URL/hash changed')
    return dict(schema_version='pm99-season-kit-catalogue-v1',season=dict(start_year=2005,end_year=2006,label='2005/06'),
        rows=[dict(carrier_id=706,club_name='Jedinstvo Bijelo Polje',status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style',style=dict(pattern='solid',colors=[[40,45,125],'white'],
                shorts='white',sleeves=[40,45,125],trim='white')),
            source=dict(provider='original-opening-match-colour-newspaper-photograph',reviewed=True,
                evidence=[dict(path=registry.relative_workspace_path(photo),url=receipt['url'],sha256=receipt['sha256']),binding],
                exact_artwork=False,default_strip_policy='Observed first-match strip as explicit V1 default, not certified home classification.',
                review='ROOT inspected original8August2005 colour page10. Caption identifies Milos Trifunovic of Jedinstvo in a duel with Nenad Brnovic of Partizan. Visible Jedinstvo outfield shirt blue/purple with white accents, white shorts and blue socks. Partizan black/white foreground shirt is NOT the target template. Blue chosen editorially from printed scan, not a measured fabric RGB; shirt panels/marks/sponsors simplified. Home/away classification unconfirmed and remains logged, not represented as a verified home design.',
                attribution='Borba8August2005 p10 / Pretraziva digital newspaper archive. Original scan retained as design evidence only.'))])
