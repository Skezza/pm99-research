"""Attach the original 2012 Wrexham kit and first-match ground, privately.

The cached Soccerbase match supplies the ground; its exact original schedule
and first-fixture replay supply the date. No new archive scrape is necessary.
"""
import json
import os
from pathlib import Path

from bs4 import BeautifulSoup
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_kit_render_bindings_v1 as render
from scripts import prepare_paired_club_assets_v1 as assets

BASE = registry.ROOT / '.local/consolidated-audit-20261009'
CACHE = BASE / 'barrow-2012-retirement-assets-v1/source-cache'
OUTPUT = BASE / 'barrow-2012-retirement-assets-v1'
SPECS = {3312: ('Wrexham', 'Racecourse Ground', 'wrexham-2012-opener.html',
    'https://www.soccerbase.com/matches/additional_information.sd?id_game=658094',
    ('Wrexham 3 - 1 Woking', 'STADIUM: Racecourse Ground'))}


def link_original(source, target):
    if target.exists():
        if registry.sha256_file(source) != registry.sha256_file(target):
            raise ValueError('original hardlink preimage differs')
    else:
        os.link(source, target)


def catalogue():
    from scripts import replay_original_soccerbase_openings_v1 as original
    proposal = pipeline.read_json_file(BASE / 'barrow-2012-retirement-source-v1/3312-wrexham-source.json')
    actual = original.replay_club('2012-13', proposal['opening_capture'], {}, True,
        allow_missing_birth_date=True)
    fields = ('fixture', 'original_match', 'raw_sources', 'source_capture')
    if (any(actual[k] != proposal['original_opening'][k] for k in fields)
            or actual['fixture']['date'] != '2012-08-11'):
        raise ValueError('dated original first fixture changed')
    history = BASE / 'boreham-retirement-pair-assets-v1/source-cache'
    for name in ('wrexham-kit-history.html', 'wrexham-kit-history.html.source.json'):
        link_original(history / name, CACHE / name)
    match = next(r for r in actual['raw_sources'] if r['url'] == SPECS[3312][3])
    path = registry.ROOT / match['path']
    link_original(path, CACHE / SPECS[3312][2])
    link_original(path.with_name(path.name + '.source.json'), CACHE / (SPECS[3312][2] + '.source.json'))
    soup = BeautifulSoup((CACHE / 'wrexham-kit-history.html').read_bytes(), 'html.parser')
    image = soup.find('img', src='/Wrexham/images/wrexham_2012-2013.gif')
    if image is None or '2012-2013' not in image.parent.get_text(' ', strip=True):
        raise ValueError('original HFK image is not explicitly labelled 2012/13')
    evidence = []
    for name in ('wrexham-kit-history.html', 'wrexham-2012-home.gif'):
        path = CACHE / name
        receipt = pipeline.read_json_file(path.with_name(name + '.source.json'))
        if receipt['sha256'] != registry.sha256_file(path):
            raise ValueError('original period kit evidence changed')
        evidence.append(dict(path=registry.relative_workspace_path(path), **receipt))
    assets.ground_source(CACHE, 3312, SPECS)
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2012, end_year=2013, label='2012/13'),
        rows=[dict(carrier_id=3312, club_name='Wrexham', status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style',
                style=dict(pattern='solid', colors=['red'], shorts='white', sleeves='red', trim='white')),
            source=dict(provider='reviewed-original-period-image',
                attribution='Historical Football Kits / Dave Moor', evidence=evidence,
                review='Original target-year drawing visually reviewed: red shirt, white collar/shorts; red shorts-side stripes and sponsors simplified.',
                exact_artwork=False))],
        policy=dict(period_colours_reviewed=True, exact_sponsors_and_fine_patterns=False,
            ground_original_first_fixture=dict(date=actual['fixture']['date'],
                game_id=actual['fixture']['game_id'], raw_sources=actual['raw_sources'][:2])))


def prepare():
    if (OUTPUT / 'kit-catalogue.json').exists():
        raise ValueError('asset rendering workspace is immutable')
    doc = catalogue()
    pipeline.write_canonical_json(OUTPUT / 'kit-catalogue.json', doc)
    pipeline.write_canonical_json(OUTPUT / 'ground-specs.json', SPECS)
    bindings, receipt = render.render_catalogue(doc,
        dbdat=BASE / 'barrow-2012-retirement-native-v1/game/DBDAT',
        output_dir=OUTPUT / 'renders', pattern_cache_dir=OUTPUT / 'pattern-cache', allow_network=False)
    if receipt['coverage']['bound_club_count'] != 1 or receipt['coverage']['artifact_count'] != 3:
        raise ValueError('replacement kit render has gaps')
    pipeline.write_canonical_json(OUTPUT / 'render-bindings.json', bindings)
    pipeline.write_canonical_json(OUTPUT / 'render-receipt.json', receipt)
    result = assets.prepare(BASE / 'barrow-2012-retirement-native-v1', OUTPUT,
        BASE / 'barrow-2012-retirement-complete-v1', ground_specs=SPECS)
    print(dict(clubs=result['new_clubs'], assets_built=True, installed=False), flush=True)


if __name__ == '__main__':
    prepare()
