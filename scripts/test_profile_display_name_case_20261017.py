"""Display case only; never waive a different identity, accent or truncation."""
import pytest
from scripts.verify_city_opening_runtime_20261011 import same_native_display_name


@pytest.mark.parametrize('observed,expected,accepted',[
    ('Gabor KIRÁLY','Gabor Király',True),
    ('G. KIRALY','G. Kiraly',True),
    ('Gabor KIRALY','Gabor Király',False),
    ('G. KIRÁLY','Gabor Király',False),
    ('Gabor KIRÁLY extra','Gabor Király',False),
    ('GaborKIRÁLY','Gabor Király',False),
    ('Gabor KIRÁLY','Gabor Kiraly',False),
    (None,'Gabor Király',False),
])
def test_only_display_case_can_differ(observed,expected,accepted):
    assert same_native_display_name(observed,expected) is accepted
