"""Observed first-match red strip; exact artwork and home classification unknown."""
from scripts.capture_stock_replacement_sources_20261010 import ROOT
from scripts.capture_borac_2003_period_photographs_v1 import SOURCES
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry


def catalogue():
    key = 'borac-2003-original-opening-photographs-retrospective'
    _, _, binding = source_rows(key)
    photo = ROOT.parent / 'borac-2003-period-originals' / (key + '.jpg')
    receipt = pipeline.read_json_file(photo.with_name(photo.name + '.source.json'))
    if receipt != dict(url=SOURCES[key], sha256=registry.sha256_file(photo), source_binding=binding):
        raise ValueError('original opening photograph or source binding changed')
    return dict(schema_version='pm99-season-kit-catalogue-v1', season=dict(start_year=2003, end_year=2004, label='2003/04'),
        rows=[dict(carrier_id=706, club_name='Borac Cacak', status='source-ready',
            render_contract=dict(kind='reviewed-pm99-style', style=dict(pattern='solid', colors=['red', 'white'],
                shorts='red', sleeves='red', trim='white')),
            source=dict(provider='original-opening-match-colour-photograph-republished-with-report', reviewed=True,
                evidence=[dict(path=registry.relative_workspace_path(photo), url=receipt['url'], sha256=receipt['sha256']), binding],
                exact_artwork=False, default_strip_policy='Observed first-match strip as explicit V1 default; home/away classification unconfirmed.',
                review='ROOT inspected retained colour photograph within the Partizan-Borac6-1 original match report. Borac outfielder behind black-white Partizan player has red shirt with white upper-body accents, red shorts and red socks. Grey diving goalkeeper is NOT the outfield kit. Simplified factory solid-red template with white trim; no exact sponsors, panels or fabric RGB claim.',
                attribution='Original2003 Partizan-Borac report/photo, republished by Crno-bela Nostalgija in Prvenstvo2003/04. Retained scan is research design evidence, not redistributed kit artwork.'))])
