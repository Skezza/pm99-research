"""Verify a manually inspected period PDF fixture, not a modern inferred XI.

The magazine is scanned: this is explicitly a hash-bound visual transcription,
not an automatic PDF-text scrape. Changed original bytes require a new review.
No contemporary namesake ID or date may fill the unresolved Gomez identity.
"""
import copy
import hashlib

from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_august_source_fallback_v1 as fallback

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1'
URL = 'https://www.spfcpedia.com.br/ebooks/2021-05-08_revista-conmebol_066.pdf'
PDF_SHA = 'bf50ff34f9ecec6e65b7b130a5ed59b042d775aa2f4c215ccbaa5cece2499eff'
PAGE_SHA = 'f53cfeed69eb980e27cc97dfc22cae4cce0a1d47ae862f8d323f4b316b060d48'
SCHEMA = 'pm99-reviewed-original-estudiantes2000-august-cup-v1'
XI = ['Osnel García', 'Vielma', 'Villafraz', 'Manuel Rodríguez', 'Lenín Díaz',
      'Cristian Pérez', 'Javier Gómez', 'Pozzuto', 'Martín Brignani', 'Salazar', 'Panigutti']
USED = [dict(published_match_name='Buitriago', minute=46, replaces='Salazar')]
UNUSED = ['Rivas', 'Juan Lobo', 'Oswaldo Morán', 'Gregory Sánchez']


def expected():
    return dict(season='2000-01', fixture_date='2000-08-02', club='Estudiantes de Mérida',
        opponent='Guadalajara', result='2-3', competition='Copa Merconorte',
        ground='Guillermo Soto Rosa', manager="Antonio D’Accorso",
        starting_xi=[dict(published_match_name=n) for n in XI],
        used_substitutes=copy.deepcopy(USED), unused_substitutes=list(UNUSED),
        cautions=[dict(published_match_name='Manuel Rodríguez', minute=68,
            interpretation='Unexplained printed minute; NOT an invented replacement player.')],
        first_league_xi=False, formation=None)


def verify_review(pdf_raw, page_raw, review):
    if (not isinstance(pdf_raw, bytes) or not pdf_raw.startswith(b'%PDF-')
            or hashlib.sha256(pdf_raw).hexdigest()!=PDF_SHA):
        raise ValueError('original CONMEBOL magazine changed; new visual review required')
    if not isinstance(page_raw, bytes) or hashlib.sha256(page_raw).hexdigest()!=PAGE_SHA:
        raise ValueError('original reviewed page image changed')
    if (review.get('schema_version')!=SCHEMA
            or review.get('method')!='assistant-original-PDF-page-visual-review'
            or review.get('original_url')!=URL or review.get('pdf_sha256')!=PDF_SHA
            or review.get('page_image_sha256')!=PAGE_SHA
            or review.get('pdf_page_number')!=60 or review.get('printed_page_number')!=52
            or review.get('original_page_visually_inspected') is not True
            or review.get('fixture')!=expected()):
        raise ValueError('review changes original fixture, date, people, manager or source')
    result=copy.deepcopy(review['fixture'])
    binding=dict(path=registry.relative_workspace_path(ROOT/'estudiantes-2000-original-CONMEBOL-magazine66.pdf'),
        sha256=PDF_SHA)
    result['approved_lineup_fallback']=fallback.lineup(season='2000-01',
        fixture_date='2000-08-02', competition='cup', source_binding=binding,
        missing_league_xi=True)
    result['source_disagreements']=[
        dict(source='Transfermarkt original August2 match4662126',
            issue='Lists Richard Páez rather than the original period report Antonio D’Accorso.',
            disposition='Use the original dated magazine manager; do not import modern-page coach.'),
        dict(source='Transfermarkt linked squad/person103260',
            issue='Modern page links Jesús Gómez; period report publishes Javier Gómez.',
            disposition='Cross-provider identity/DOB not proved; do not import person103260 birthday.'),
        dict(source='Transfermarkt original August2 match4662126',
            issue='Bench differs from the original period report.',
            disposition='Use the four explicit period-report reserves, not the modern seven-player bench.')]
    result['native_writes']=0
    result['closed_duplicate_cases']=0
    result['publication_authorised']=False
    return result


def replay(review_path):
    pdf=ROOT/'estudiantes-2000-original-CONMEBOL-magazine66.pdf'
    page=ROOT/'estudiantes-2000-original-magazine66-page60.png'
    receipt=pipeline.read_json_file(pdf.with_suffix('.source.json'))
    if receipt.get('url')!=URL or receipt.get('sha256')!=PDF_SHA:
        raise ValueError('original magazine capture receipt differs')
    return verify_review(pdf.read_bytes(),page.read_bytes(),pipeline.read_json_file(review_path))


def unresolved_gomez():
    """Keep the period-published name; never attach a modern namesake DOB."""
    review_path=ROOT/'estudiantes-2000-original-magazine66-August2-visual-review-v1.json'
    actual=replay(review_path)
    bindings=[dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))
        for path in [ROOT/'estudiantes-2000-original-CONMEBOL-magazine66.pdf',review_path]]
    claim=dict(policy='original-Estudiantes2000-published-Javier-Gomez-unresolved-identity-v1',
        source_session=fallback.SESSION,user_approval=fallback.APPROVAL,
        provider='original-CONMEBOL-magazine66',club=actual['club'],fixture_date=actual['fixture_date'],
        published_match_name=actual['starting_xi'][6]['published_match_name'],
        cross_provider_person_id=None,full_provider_identity_unproved=True,
        birth_date_unpublished_in_original_fixture=True,original_bindings=bindings,
        gap='Javier Gómez is published; modern Jesús Gómez103260 identity/DOB unproved. Preserve native date as unsourced fallback.')
    actor_key='fixture-actor:'+hashlib.sha256(pipeline.canonical_json_bytes(claim)).hexdigest()[:24]
    return dict(source_player_id=actor_key,source_provider='original-fixture',
        name='Javier Gómez',given_name='Javier',family_name='Gómez',birth_date=None,
        identity_policy=fallback.SCHEMA,identity_evidence=claim,original_fixture_bindings=bindings)


def verify_actor(person):
    expected_person=unresolved_gomez()
    if person!=expected_person:
        raise ValueError('period Gomez actor changed name, original bindings, ID or unresolved birthday')
    return 'person-original-fixture-'+person['source_player_id'].split(':')[1]
