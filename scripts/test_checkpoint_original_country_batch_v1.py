import pytest
from scripts import checkpoint_original_country_batch_v1 as subject


def test_congo_is_not_zaire_even_if_legacy_mapper_says_so():
    with pytest.raises(ValueError,match='wrong native country'):
        subject.check_country_code(dict(nationality='CGO',native_country_code=80),dict(CONGO=111,ZAIRE=80))
    assert subject.check_country_code(dict(nationality='CGO',native_country_code=111),dict(CONGO=111,ZAIRE=80))=='CONGO'


def test_supported_country_cannot_silently_become_england():
    with pytest.raises(ValueError,match='wrong native country'):
        subject.check_country_code(dict(nationality='SCO',native_country_code=30),dict(ENGLAND=30,SCOTLAND=49))


def test_proven_unsupported_country_must_display_xxx_not_england():
    with pytest.raises(ValueError,match='wrong native country'):
        subject.check_country_code(dict(nationality='ANT',native_country_code=30),dict(ENGLAND=30,XXX=0))
    assert subject.check_country_code(dict(nationality='ANT',native_country_code=0),dict(ENGLAND=30,XXX=0))=='XXX'


def test_other_defaults_must_match_before_any_publication(monkeypatch,tmp_path):
    monkeypatch.setattr(subject.pipeline,'read_json_file',lambda path:dict(current_release_bindings=['old']))
    monkeypatch.setattr(subject,'bindings',lambda:['changed'])
    with pytest.raises(ValueError,match='bindings differ'):
        subject.run(tmp_path,'2008-09','actual','replay',tmp_path/'prior',tmp_path/'output','tag',[])


def test_literal_review_cannot_replace_a_visible_defender_with_inferred_midfielder():
    with pytest.raises(ValueError,match='literal role heading'):
        subject.check_literal_role(dict(observed_role='MIDFIELDER'),'D')
    subject.check_literal_role(dict(observed_role='DEFENDER'),'D')


def test_source_verification_and_private_regression_prevention_are_not_new_public_fixes():
    rows=[dict(native_country_changed=False,recipe_country_changed=False),
          dict(native_country_changed=True,recipe_country_changed=False),
          dict(native_country_changed=False,recipe_country_changed=True),
          dict(native_country_changed=True,recipe_country_changed=True)]
    assert subject.real_country_change_counts(rows)==dict(countries_source_verified=4,
        countries_corrected=3,native_country_values_changed=2,recipe_country_values_changed=2)


def test_country_registration_passes_every_proved_private_parent_without_promoting_it():
    proof=dict(schema='pm99-verified-country-only-ancestry-v1',base_release_id='public',final_release_id='final',
        edges=[dict(parent_release_id='public',release_id='private'),dict(parent_release_id='private',release_id='final')])
    assert subject.registration_ancestry(proof,'public','final')==['public','private','final']
    proof['edges'][1]['parent_release_id']='public'
    with pytest.raises(ValueError,match='skips a parent'):
        subject.registration_ancestry(proof,'public','final')


def test_country_registration_rejects_an_unproved_different_or_incomplete_chain():
    with pytest.raises(ValueError,match='exact verified bounded'):
        subject.registration_ancestry(dict(schema='unverified',edges=[]),'public','final')
    proof=dict(schema='pm99-verified-country-only-ancestry-v1',base_release_id='public',final_release_id='final',
        edges=[dict(parent_release_id='public',release_id='private')])
    with pytest.raises(ValueError,match='does not reach'):
        subject.registration_ancestry(proof,'public','final')


def test_non_congo_source_disagreement_is_not_waived(monkeypatch):
    from scripts import season_country_fifa_crosscheck_v1 as fifa
    monkeypatch.setattr(fifa,'check',lambda *a,**kw:dict(status='contradiction-requires-resolution'))
    with pytest.raises(ValueError,match='contradicts exact historical FIFA'):
        subject.independent_country_checks(dict(carrier_id=1,nationality='ESP'),'2017-18')


def test_congo_disagreement_requires_actual_independent_proof(monkeypatch):
    from scripts import season_country_fifa_crosscheck_v1 as fifa,season_cgo_disambiguation_v2 as cgo
    monkeypatch.setattr(fifa,'check',lambda *a,**kw:dict(status='contradiction-requires-resolution'))
    def refuse(*a,**kw):
        raise ValueError('future country is not established by target season')
    monkeypatch.setattr(cgo,'verify',refuse)
    with pytest.raises(ValueError,match='future country'):
        subject.independent_country_checks(dict(carrier_id=1,nationality='CGO'),'2017-18')


def test_original_linganzi_republic_evidence_resolves_fifa_democratic_miscoding():
    from scripts import season_cgo_disambiguation_v2 as cgo
    path=cgo.CATALOG.parent.parent/'country-policy-v2-cohort-20261017/2016-17/country-plan.json'
    if not cgo.CATALOG.exists() or not path.exists():pytest.skip('local original corpus unavailable')
    row=next(r for r in cgo.pipeline.read_json_file(path)['updates'] if r['carrier_id']==33239)
    result,proof=subject.independent_country_checks(row,'2016-17')
    assert result['status']=='resolved-country-geography-by-independent-prior-dated-association'
    assert result['FIFA_country']=='COD' and proof['country']=='CGO'
    assert result['raw_FIFA_disagreement_retained']
