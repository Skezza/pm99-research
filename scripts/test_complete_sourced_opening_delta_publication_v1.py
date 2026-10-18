import pytest
from scripts import complete_sourced_opening_delta_publication_v1 as m


@pytest.mark.parametrize('season,release',[('2008-09','safe'),('2009-10','../other'),
    ('2009-10','/absolute'),('2009-10','MixedCase'),('2009-10','')])
def test_recovery_refuses_other_seasons_or_unsafe_paths(season,release):
    with pytest.raises(ValueError,match='unsafe|unsupported'):m.complete(season,release)


def test_existing_locator_is_never_overwritten(tmp_path,monkeypatch):
    path=tmp_path/'locator.json';path.write_text('existing release')
    monkeypatch.setattr(m.registry,'locator_path',lambda season,release:path)
    with pytest.raises(ValueError,match='immutable'):m.complete('2009-10','safe')
    assert path.read_text()=='existing release'
