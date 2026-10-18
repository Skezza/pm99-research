"""Broad period colours from an inspected original July2003 website capture.

The preview's illustrative photograph is not certified as the July31 fixture
or an exact home-kit panel reference. A simplified factory strip is explicit.
"""
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_pipeline_v2 as pipeline

URL = 'https://virtual.urbe.edu/tesispub/0075242/conclu.pdf'


def catalogue():
    path, raw, binding = source_rows('monagas-2003-original-period-newspaper-thesis-annex')
    receipt = pipeline.read_json_file(path.with_suffix('.source.json'))
    if receipt['url'] != URL or not raw.startswith(b'%PDF-'):
        raise ValueError('original period website-annex PDF differs')
    return dict(schema_version='pm99-season-kit-catalogue-v1',
        season=dict(start_year=2003, end_year=2004, label='2003/04'),
        rows=[dict(carrier_id=2953, club_name='Monagas SC', status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style', style=dict(pattern='vertical_stripes',
                colors=[[32,64,168],[128,24,48]], shorts=[32,64,168], sleeves=[32,64,168],
                trim=[128,24,48], stripe_count=3)),
            source=dict(provider='original-period-website-screen-preserved-in-university-thesis-annex', reviewed=True,
                evidence=[dict(binding, url=URL, pdf_page_one_based=21, printed_page=154)], exact_artwork=False,
                review='ROOT inspected original PDF page21/printed154: LaVinotinto July2003 Monagas-Italchacao preview with blue/maroon shirt and dark-blue shorts, versus blue/white-hooped opponent. Three-stripe factory pattern is a declared simplified editorial default, not an exact panel trace.',
                limitation='Illustrative period-published photo; capture date corroborated by adjacent July31,2003 news-index page22. Photo match date, home/away classification, stripe count, sponsor and exact RGB NOT certified. Monochrome newspaper2-1 clipping is not colour evidence.',
                attribution='LaVinotinto.com original July2003 screen, preserved by Universidad Rafael Belloso Chacin thesis0075242 annex. Local colour/design research only; original image not redistributed.'))])
