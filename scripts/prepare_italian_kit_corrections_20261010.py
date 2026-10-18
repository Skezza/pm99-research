"""Prepare two visually reviewed period designs, without publishing games."""
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts.prepare_reviewed_kit_delta_v1 import prepare

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/italian-kit-corrections-v1'
SPECS = {
    '2005-06': ('Palermo', 'palermo-2005', 2,
        dict(pattern='solid', colors=[[230, 167, 201]], shorts='black',
             sleeves=[230, 167, 201], trim='black'),
        'Original Corini shirt and accompanying Juventus match photograph: pale pink shirt, black neck trim and black shorts. Fine black piping, sponsors and logos simplified.'),
    '2006-07': ('Atalanta', 'atalanta-2006', 1,
        dict(pattern='vertical_stripes', colors=[[0, 104, 205], 'black'],
             shorts='black', sleeves=[0, 104, 205], trim='black', stripe_count=5),
        'Original labelled 2006/07 Asics home shirt: blue/black vertical stripes, blue sleeves, black neck/shoulder panels. Fine panels, logos and sponsors simplified; black shorts follow captured target-season catalogue, not this shirt-only photograph.'),
}


def catalogue(season):
    club, prefix, count, style, review = SPECS[season]
    evidence = []
    for name in [prefix + '.html'] + [f'{prefix}-{i}.jpg' for i in range(1, count + 1)]:
        path = ROOT / 'source-cache' / name
        receipt = pipeline.read_json_file(path.with_name(name + '.source.json'))
        evidence.append(dict(path=registry.relative_workspace_path(path), **receipt))
    if season == '2006-07':
        original = registry.ROOT / '.local/season-kit-sources-historical-backfill-v1/2006-07/kit-catalogue-v1.json'
        row = next(r for r in pipeline.read_json_file(original)['rows'] if r['carrier_id'] == 223)
        if row['club_name'] != club or row['render_contract']['fields']['shorts1'] != '000000':
            raise ValueError('original target-season shorts evidence differs')
        # This catalogue is retained as secondary source provenance, not the
        # impossible composite pattern token used as the new rendering input.
        review += ' Original shorts catalogue SHA256=' + registry.sha256_file(original)
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=int(season[:4]), end_year=int(season[:4]) + 1, label=season.replace('-', '/')),
        rows=[dict(carrier_id=223, club_name=club, status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style', style=style),
            source=dict(provider='reviewed-original-period-shirt-photographs',
                reviewed=True, evidence=evidence, review=review, exact_artwork=False,
                attribution='Mondorosanero (Palermo); Le 7 Sorelle (Atalanta). Source photographs used for historical colour/design review, not copied into game.'))])


def main():
    for season in SPECS:
        output = ROOT / (season + '-v2')
        path = ROOT / (season + '-kit-catalogue.json')
        doc = catalogue(season)
        if path.exists() and pipeline.read_json_file(path) != doc:
            raise ValueError('authored source contract changed')
        if not path.exists():
            pipeline.write_canonical_json(path, doc)
        print(dict(season=season, result=prepare(season, path, output), installed=False), flush=True)


if __name__ == '__main__':
    main()
