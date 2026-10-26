"""Synthetic parser guards plus a retained original report when locally available."""
from pathlib import Path
import pytest
from bs4 import BeautifulSoup
from scripts import season_source_bound_fixture_membership_v1 as source


def grid(ids=range(1,12)):
    # Synthetic fixture, not historical evidence.
    return BeautifulSoup('<div class="aufstellung-box"><div class="formation-subtitle">Starting Line-up: 4-3-3</div>'+''.join(f'<div class="formation-player-container"><a href="/sample/profil/spieler/{i}">Surname{i}</a></div>' for i in ids)+'</div>','html.parser').div


def test_grid_retains_literal_surnames_and_exact_provider_ids():
    rows,formation=source._parse_grid_team(grid())
    assert formation=='4-3-3'
    assert rows==[(str(i),f'Surname{i}',None) for i in range(1,12)]


@pytest.mark.parametrize('ids',[range(1,11),[1]*11,[0]+list(range(1,11))])
def test_grid_rejects_missing_repeated_and_nonpositive_identities(ids):
    with pytest.raises(source.OpeningXICompositionError):source._parse_grid_team(grid(ids))


def test_grid_requires_original_published_formation():
    team=grid();team.select_one('.formation-subtitle').decompose()
    with pytest.raises(source.OpeningXICompositionError):source._parse_grid_team(team)


def test_retained_wycombe_report_exact_surnames_and_ids():
    path=source.registry.ROOT/'.local/transfermarkt-opening-plans-current-v1/2016-17/cache/report/2701270.html'
    if not path.exists():pytest.skip('local retained historical report unavailable')
    page=BeautifulSoup(path.read_bytes(),'html.parser')
    teams=[t for t in page.select('.large-6') if t.select_one('a[href*="/startseite/verein/2805/"]') and t.select_one('.formation-subtitle')]
    assert len(teams)==1
    rows,formation=source._parse_grid_team(teams[0])
    assert formation=='4-3-3'
    assert rows[0]==('21703','Brown',None)
    assert len(rows)==11 and '191620' not in [r[0] for r in rows]
