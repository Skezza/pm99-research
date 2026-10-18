"""Bind dated Barnet ground and season-specific illustrated home-kit colours."""
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_kit_render_bindings_v1 as render
from scripts import prepare_paired_club_assets_v1 as assets
from scripts import verify_paired_whole_club_native_v1 as readback
from scripts import verify_paired_club_identity_v1 as identity
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

BASE = registry.ROOT / '.local/consolidated-audit-20261009'
ROOT = BASE / 'Barnet2018-assets-v1'
NATIVE = BASE / 'Barnet2018-native-delivery-v1/native'
COMPLETE = BASE / 'Barnet2018-complete-v1'
SPECS = {3317: ('Barnet', 'The Hive London', 'ground-original-3317.html',
    'https://barnetfc.com/news-2018-19-vanarama-national-league-fixtures-released',
    ('2018/19', 'Braintree Town', 'August 7th'))}


def main():
    if COMPLETE.exists():
        raise ValueError('completed asset candidate must not be repeated')
    evidence = []
    for name in ('kit-history-original.html', 'home-2018-19.gif'):
        path = ROOT / 'source-cache' / name
        source = pipeline.read_json_file(path.with_name(path.name + '.source.json'))
        if registry.sha256_file(path) != source['sha256']:
            raise ValueError('original illustrated kit source changed')
        evidence.append(dict(path=registry.relative_workspace_path(path), **source))
    assets.ground_source(ROOT / 'source-cache', 3317, SPECS)
    doc = dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2018, end_year=2019, label='2018/19'),
        rows=[dict(carrier_id=3317, club_name='Barnet', status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style', style=dict(
                pattern='solid', colors=['orange'], shorts='black', sleeves='orange', trim='black')),
            source=dict(provider='reviewed-season-labelled-kit-illustration',
                attribution='Historical Football Kits, Barnet club history and 2018-2019 home illustration',
                evidence=evidence, exact_artwork=False,
                review='ROOT viewed original season-labelled 150x263 illustration: amber/orange shirt and sleeves, black shorts, amber socks. Factory-tone approximation preserves these colour families; the asymmetric honeycomb graphic, sponsors, badge and manufacturer panels are deliberately not reproduced. This is an illustrated historical secondary source, not a primary club launch photograph.',
                shorts_source_verified=True))],
        limitations=['Illustration-based palette and shorts; exact pigment shades not certified.',
            'Asymmetric honeycomb graphic, sponsors and badges simplified; no exact-artwork claim.'])
    retained(ROOT / 'kit-catalogue.json', doc)
    retained(ROOT / 'ground-specs.json', SPECS)
    bindings, receipt = render.render_catalogue(doc, dbdat=NATIVE / 'game/DBDAT',
        output_dir=ROOT / 'renders', pattern_cache_dir=ROOT / 'pattern-cache', allow_network=False)
    if receipt['coverage']['bound_club_count'] != 1 or receipt['coverage']['artifact_count'] != 3:
        raise ValueError('all three Barnet kit sizes required')
    retained(ROOT / 'render-bindings.json', bindings)
    retained(ROOT / 'render-receipt.json', receipt)
    assets.prepare(NATIVE, ROOT, COMPLETE, ground_specs=SPECS)
    native = readback.verify(COMPLETE, BASE / 'Barnet2018-native-readback.json')
    duplicates = identity.verify(COMPLETE,
        registry.ROOT / '.local/duplicate-ownership-v3/published-person-identities-r2.json',
        BASE / 'Barnet2018-identity-readback.json')
    print(dict(native_actors_verified=len(native['players']),
        new_duplicates=duplicates['introduced_candidate_groups'],
        stale_portraits_cleared=duplicates['stale_portraits_cleared'],
        preferred_changed=False), flush=True)


if __name__ == '__main__':
    main()
