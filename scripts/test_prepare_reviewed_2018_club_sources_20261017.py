import pytest
from scripts.prepare_reviewed_2018_club_sources_20261017 import wiki_identity

@pytest.mark.parametrize('template',[
    '{{birth date and age|1995|2|13|df=y}}',
    '{{Birth date and age|df=y|1995|02|13}}',
])
def test_original_infobox_date_order_is_explicit(template):
    raw='| name = Bradley Barry\n| fullname = Bradley Oliver Barry<ref>source</ref>\n| birth_date = '+template+'\n'
    assert wiki_identity(raw)==('Bradley Barry','Bradley Oliver Barry','1995-02-13')

@pytest.mark.parametrize('fault',[
    'duplicate-name','missing-fullname','unparsed-date','extra-numeric-argument','invalid-date','unexpected-argument',
])
def test_ambiguous_or_unparsed_infobox_never_resolves_a_conflicting_date(fault):
    raw='| name = Bradley Barry\n| fullname = Bradley Oliver Barry\n| birth_date = {{birth date and age|1995|2|13|df=y}}\n'
    if fault=='duplicate-name':raw+='|name = Another Person\n'
    elif fault=='missing-fullname':raw=raw.replace('| fullname = Bradley Oliver Barry\n','')
    elif fault=='unparsed-date':raw=raw.replace('{{birth date and age|1995|2|13|df=y}}','13/02/1995')
    elif fault=='extra-numeric-argument':raw=raw.replace('|df=y','|9|df=y')
    elif fault=='invalid-date':raw=raw.replace('|2|13','|2|31')
    elif fault=='unexpected-argument':raw=raw.replace('|df=y','|alternate=1')
    with pytest.raises(ValueError):wiki_identity(raw)
