"""Render three reviewed period kits; preserve originals and record limitations."""
import json
from pathlib import Path
import re
import sys
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_kit_render_bindings_v1 as render
from scripts import prepare_paired_club_assets_v1 as assets

BASE = ROOT / '.local/consolidated-audit-20261009'
CACHE = BASE / 'boreham-retirement-pair-assets-v1/source-cache'
OUTPUT = BASE / 'boreham-retirement-triple-assets-v2'
SPECS = {
    3329: ('Wrexham', 'Racecourse Ground', 'wrexham-2017-opener.html',
        'https://www.wrexhamafcarchive.co.uk/matchdetails.php?id=150',
        ('Saturday, August 5th, 2017', 'Macclesfield Town')),
    3325: ('Chester', 'Deva Stadium', 'chester-2017-home-match.html',
        'https://www.wrexhamafcarchive.co.uk/matchdetails.php?id=169',
        ('Wednesday, November 8th, 2017', 'Chester', 'Wrexham')),
    3316: ('Guiseley', 'Nethermoor', 'guiseley-2017-opener.html',
        'https://chadwickmedia.wordpress.com/2017/08/07/guiseley-afc-v-ebbsfleet-united/',
        ('August 7, 2017', 'Guiseley AFC 2 v 2 Ebbsfleet United')),
}


def original(filename):
    path = CACHE / filename
    receipt = json.loads(path.with_name(filename + '.source.json').read_text())
    if receipt['sha256'] != registry.sha256_file(path):
        raise ValueError('original kit evidence changed: ' + filename)
    return dict(path=registry.relative_workspace_path(path), **receipt)


def catalogue():
    history = BeautifulSoup((CACHE / 'wrexham-kit-history.html').read_bytes(), 'html.parser')
    image = history.find('img', src='/Wrexham/images/wrexham_2017-2018-1st.gif')
    if image is None or '2017-2018' not in image.parent.get_text(' ', strip=True):
        raise ValueError('Wrexham period image is not bound to 2017/18')
    raw = (CACHE / 'chester-2017-official-trophy-highlight.html').read_text()
    if not ('Chester FC TV' in raw and 'CFC TV: Chester 2-2 AFC Fylde' in raw
            and re.search(r'datePublished" content="2017-12-17T', raw)):
        raise ValueError('Chester original video lacks its publisher and target-season date')
    styles = {
        3329: dict(pattern='solid', colors=['red'], shorts='white', sleeves='red', trim='white'),
        3325: dict(pattern='vertical_stripes', colors=['blue', 'white'], shorts='white',
                   sleeves='blue', trim='blue', stripe_count=6),
        3316: dict(pattern='solid', colors=['white'], shorts='navy', sleeves='white', trim='navy'),
    }
    evidence = {
        3329: ['wrexham-kit-history.html', 'wrexham-2017-home.gif'],
        3325: ['chester-2017-home-shirt.html', 'chester-2017-home-shirt.jpg',
               'chester-2017-official-trophy-highlight.html',
               'chester-2017-official-video-storyboard-0.jpg',
               'chester-2017-official-video-storyboard-1.jpg'],
        3316: ['guiseley-2017-opener.html', 'guiseley-2017-opener-95.jpg'],
    }
    reviews = {
        3329: 'Original HFK target-year drawing: red shirt, white shorts, white trim. Fine diagonal striping and sponsors simplified.',
        3325: 'Original collector target-year shirt and Chester FC TV December 2017 home-match frames: blue/white stripes, blue sleeves, white shorts. Period home-match variant; not proof of the August default shorts. No modern black-shorts assumption. Sponsors simplified.',
        3316: 'Original photographer August 2017 first-match photograph: white shirt, navy shorts and navy sleeve trim. Sponsors simplified.',
    }
    rows = []
    for carrier in sorted(styles):
        rows.append(dict(carrier_id=carrier, club_name=SPECS[carrier][0], status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style', style=styles[carrier]),
            source=dict(provider='reviewed-original-period-image',
                attribution={'3329': 'Historical Football Kits / Dave Moor',
                             '3325': 'Old Football Shirts contributor; Chester FC TV / Jamie Stubbs',
                             '3316': 'Chadwick Media'}[str(carrier)],
                evidence=[original(name) for name in evidence[carrier]],
                review=reviews[carrier], exact_artwork=False)))
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2017, end_year=2018, label='2017/18'), rows=rows,
        policy=dict(period_colours_reviewed=True, exact_sponsors_and_fine_patterns=False,
                    opening_default_shorts_proved_for_every_club=False))


def prepare():
    if OUTPUT.exists():
        raise ValueError('asset source/render workspace is immutable')
    doc = catalogue()
    for carrier in SPECS:
        assets.ground_source(CACHE, carrier, SPECS)
    OUTPUT.mkdir()
    # Ground files stay original, URL/SHA bound. Hardlinks are read-only inputs.
    import os
    (OUTPUT / 'source-cache').mkdir()
    for value in SPECS.values():
        for name in (value[2], value[2] + '.source.json'):
            os.link(CACHE / name, OUTPUT / 'source-cache' / name)
    pipeline.write_canonical_json(OUTPUT / 'kit-catalogue.json', doc)
    pipeline.write_canonical_json(OUTPUT / 'ground-specs.json', SPECS)
    bindings, receipt = render.render_catalogue(doc,
        dbdat=BASE / 'boreham-retirement-triple-native-v2/game/DBDAT',
        output_dir=OUTPUT / 'renders', pattern_cache_dir=OUTPUT / 'pattern-cache', allow_network=False)
    if receipt['coverage']['bound_club_count'] != 3 or receipt['coverage']['artifact_count'] != 9:
        raise ValueError('replacement kit render has gaps')
    pipeline.write_canonical_json(OUTPUT / 'render-bindings.json', bindings)
    pipeline.write_canonical_json(OUTPUT / 'render-receipt.json', receipt)
    result = assets.prepare(BASE / 'boreham-retirement-triple-native-v2', OUTPUT,
        BASE / 'boreham-retirement-triple-complete-v2', ground_specs=SPECS)
    print(dict(clubs=result['new_clubs'], assets_built=True, installed=False), flush=True)


if __name__ == '__main__':
    prepare()
