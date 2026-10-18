import pytest
from scripts import season_cgo_redirect_country_witness_v1 as subject


@pytest.mark.parametrize('season,carrier',[('2011-12',12506),('2012-13',8023)])
def test_retained_original_mfuyi_country_link_is_dr_congo_not_missing_source(season,carrier):
    path=subject.old.CATALOG.parent.parent/('country-policy-v2-cohort-20261017/'+season+'/country-plan.json')
    if not path.exists() or not (subject.CACHE/(subject.KEY+'.html')).exists():
        pytest.skip('local original country redirect corpus unavailable')
    row=next(r for r in subject.old.pipeline.read_json_file(path)['updates'] if r['carrier_id']==carrier)
    assert subject.verify(row,season)['country']=='COD'
    with pytest.raises(ValueError,match='future'):
        subject.verify(row,'2009-10')


def test_unrelated_country_cannot_be_admitted_to_cgo_alias_route():
    with pytest.raises(ValueError,match='only ambiguous original CGO'):
        subject.verify(dict(nationality='ENG'),'2011-12')
