"""Pin the exact original-native accent split; do not fold runtime searches."""
import pytest
from scripts.capture_kiraly_period_profiles_20261017 import profile


@pytest.mark.parametrize('season,carrier,search',[
    ('2000-01',2211,'Kiraly'),('2001-02',2211,'Kiraly'),
    ('2002-03',2211,'Kiraly'),('2003-04',2211,'Kiraly'),
    ('2004-05',8492,'KIRÁLY'),('2005-06',9683,'KIRÁLY'),
    ('2006-07',9709,'KIRÁLY'),('2007-08',9475,'KIRÁLY'),
])
def test_exact_native_search_and_independent_identity_token(season,carrier,search):
    assert profile(season)==(carrier,'kiraly_hungary_keeper',search,'Kiraly')
