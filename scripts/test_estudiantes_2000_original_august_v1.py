"""No unsupported modern identity or manager can replace the period report."""
import copy
from unittest.mock import patch

import pytest
from scripts import estudiantes_2000_original_august_v1 as source


def review():
    return dict(schema_version=source.SCHEMA,method='assistant-original-PDF-page-visual-review',
        original_url=source.URL,pdf_sha256=source.PDF_SHA,page_image_sha256=source.PAGE_SHA,
        pdf_page_number=60,printed_page_number=52,original_page_visually_inspected=True,
        fixture=source.expected())


def verify(r):
    # Unit fixture bytes do not pretend to be the original24MiB PDF. The hash
    # adapter isolates review semantics; real replay checks the retained bytes.
    pdf=b'%PDF-original';page=b'original-page'
    class Digest:
        def __init__(self,data):self.data=data
        def hexdigest(self):return source.PDF_SHA if self.data==pdf else source.PAGE_SHA
    with patch.object(source.hashlib,'sha256',side_effect=Digest):
        return source.verify_review(pdf,page,r)


def test_original_cup_scope_and_exact_sixteen():
    result=verify(review())
    assert result['manager']=="Antonio D’Accorso"
    assert len(result['starting_xi'])+len(result['used_substitutes'])+len(result['unused_substitutes'])==16
    assert result['approved_lineup_fallback']['league_starting_xi_missing'] is True
    assert result['native_writes']==result['closed_duplicate_cases']==0
    assert '103260' in result['source_disagreements'][1]['disposition']


@pytest.mark.parametrize('field,value',[
    ('fixture_date','2000-08-22'),('manager','Richard Páez'),('first_league_xi',True),
    ('ground','Metropolitano'),('formation','4-4-2'),('club','Caracas'),
    ('starting_xi',[]),('used_substitutes',[]),('unused_substitutes',[]),
    ('cautions',[])])
def test_altered_fixture_refused(field,value):
    r=review();r['fixture'][field]=value
    with pytest.raises(ValueError):verify(r)


@pytest.mark.parametrize('field,value',[
    ('original_url','https://example.com/mirror'),('pdf_page_number',61),
    ('printed_page_number',53),('original_page_visually_inspected',False),
    ('method','automatic-ocr'),('pdf_sha256','0'*64),('page_image_sha256','0'*64)])
def test_unbound_review_refused(field,value):
    r=review();r[field]=value
    with pytest.raises(ValueError):verify(r)


def test_wrong_gomez_identity_not_silently_joined():
    r=review();r['fixture']['starting_xi'][6]['source_player_id']=103260
    with pytest.raises(ValueError):verify(r)


def test_changed_original_bytes_refused():
    with pytest.raises(ValueError):source.verify_review(b'%PDF-changed',b'changed',review())


@pytest.mark.parametrize('field,value',[
    ('name','Jesús Gómez'),('birth_date','1984-08-06'),('source_player_id',103260),
    ('given_name',None),('family_name','Mercado'),('identity_policy','unverified'),
    ('source_provider','transfermarkt')])
def test_unresolved_actor_cannot_become_modern_namesake(monkeypatch,field,value):
    expected=dict(source_player_id='fixture-actor:original',source_provider='original-fixture',
        name='Javier Gómez',given_name='Javier',family_name='Gómez',birth_date=None,
        identity_policy='explicit-original-policy')
    monkeypatch.setattr(source,'unresolved_gomez',lambda:copy.deepcopy(expected))
    changed=copy.deepcopy(expected);changed[field]=value
    with pytest.raises(ValueError):source.verify_actor(changed)


def test_second_club_kit_artifact_does_not_replace_sartid():
    from scripts import season_foreign_fixed_roster_delta_v1 as foreign
    first=foreign.kit_source_artifact('2000-01',{})
    second=foreign.kit_source_artifact('2000-01',{},carrier=2953)
    assert first['id']!=second['id']
    assert first['relative_path']!=second['relative_path']


def test_pdf_manager_source_is_not_mislabelled_html():
    from scripts import prepare_estudiantes_2000_verified_inputs_v1 as inputs
    dated=inputs.native_dated({'dated_manager_ground':{},'original_bindings':[{}]})
    assert dated['relative_path'].endswith('.pdf')
    assert dated['media_type']=='application/pdf'
