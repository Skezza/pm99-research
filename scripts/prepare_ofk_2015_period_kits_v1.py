"""The reviewed19July2015 original photograph, not a2004 or modern kit."""
from bs4 import BeautifulSoup
from scripts import prepare_ofk_2004_source_allocation_v1 as source
from scripts import prepare_ofk_2004_private_kits_v1 as kits
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry


def catalogue():
    raw,binding=source.original('ofk-2015-original-first-match-photographs')
    page=BeautifulSoup(raw,'html.parser')
    photo=source.AUDIT/'ofk-2015-kit-originals/ofk-2015-original-first-match-photographs-1.jpg'
    receipt=pipeline.read_json_file(photo.with_name(photo.name+'.source.json'))
    expected='https://hotsport.rs/wp-content/uploads/2015/07/OFK-ZVEZDA_23-1024x783.jpg'
    if (receipt!=dict(url=expected,sha256=registry.sha256_file(photo))
            or page.select_one('meta[property="og:image"]').get('content')!=expected
            or not page.select_one('meta[property="og:updated_time"]')['content'].startswith('2015-07-19')):
        raise ValueError('OFK2015 reviewed photograph is not the original dated first fixture')
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2015,end_year=2016,label='2015/16'),rows=[dict(carrier_id=706,
            club_name='OFK Beograd',status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style',style=dict(pattern='vertical_stripes',
                colors=['white',[40,120,184]],shorts=[40,120,184],sleeves=[40,120,184],trim='white',stripe_count=5)),
            source=dict(provider='original-period-first-league-match-photograph',reviewed=True,
                evidence=[dict(path=registry.relative_workspace_path(photo),**receipt),binding],
                exact_artwork=False,review='ROOT inspected original19July2015 OFK/RedStar photograph: OFK players at back left in blue/white vertical-striped shirts, blue sleeves and blue shorts with white side detailing. Foreground red/white players are RedStar, not the template. Blue tone and stripe layout editorial approximation; logos/sponsors/piping simplified.',
                attribution='HotSport19July2015 match photograph (original linked JPEG), retained as local research/design evidence, not inserted into game.'))])


if __name__=='__main__':
    p=pipeline.read_json_file(source.AUDIT/'ofk-2015-celta-verified-source-inputs-v1.json')
    x=kits.prepare(source.AUDIT/'ofk-2015-private-kits-v1',source_catalogue=catalogue(),
        season='2015-16',baseline_release_id=p['baseline_release_id'])
    print(dict(sizes=len(x['changes']),period='2015-16',registered=False),flush=True)
