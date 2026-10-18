"""Factory-style3-size kit from the inspected actual first-match photograph."""
from bs4 import BeautifulSoup
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts import tachira_2014_original_opening_v1 as opening
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import prepare_ofk_2004_private_kits_v1 as kits


def catalogue():
    _, raw, binding = source_rows('tachira-2014-original-club-press-opening-validated')
    opening.parse(raw)
    photo = ROOT.parent / 'tachira-2014-kit-originals/tachira-2014-original-club-press-opening-validated-1.jpg'
    receipt = pipeline.read_json_file(photo.with_name(photo.name + '.source.json'))
    expected = 'https://media.lavinotinto.com/cms/wp-content/uploads/2014/08/tach-atletico.jpg'
    page = BeautifulSoup(raw, 'html.parser')
    if (receipt != dict(url=expected, sha256=registry.sha256_file(photo))
            or page.select_one('meta[property="og:image"]').get('content') != expected):
        raise ValueError('period kit source differs from original first-match photograph')
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2014, end_year=2015, label='2014/15'),
        rows=[dict(carrier_id=2953, club_name='Deportivo Tachira', status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style', style=dict(pattern='vertical_stripes',
                colors=[[232,212,0], 'black'], shorts='black', sleeves=[232,212,0], trim='black', stripe_count=3)),
            source=dict(provider='original-period-first-league-match-photograph', reviewed=True,
                evidence=[dict(path=registry.relative_workspace_path(photo), **receipt), binding], exact_artwork=False,
                review='ROOT inspected original10August2014 first-match photograph. Táchira players wear yellow shirts with wide black vertical front stripes, yellow sleeves/black cuffs, black shoulder panels and black shorts. Upper yellow chest/precise black panels and sponsors simplified by factory pattern renderer; this is period colour/pattern evidence, not exact artwork.',
                attribution='Prensa Deportivo Táchira / LaVinotinto10August2014, original linked JPEG retained only as local research/design evidence.'))])


if __name__ == '__main__':
    proposal = pipeline.read_json_file(ROOT.parent / 'tachira-2014-verified-source-inputs-v1.json')
    proof = kits.prepare(ROOT.parent / 'tachira-2014-private-kits-v1', source_catalogue=catalogue(),
        season='2014-15', baseline_release_id=proposal['baseline_release_id'], carrier=2953, club_name='Deportivo Tachira')
    print(dict(sizes=len(proof['changes']), registered=False), flush=True)
