from types import SimpleNamespace
import pytest
from scripts import savio_bobb_2024_original_alias_v1 as source


def page(opening):
    if opening:
        title='Match report: Chelsea 0-2 Man City';day='2024-08-18'
        text='Man City : Ederson, Lewis, Akanji, Dias, Gvardiol, Kovacic, De Bruyne (C), Bernardo, Doku, Savinho (Foden 46), Haaland Unused substitutes : Ortega'
    else:
        title='Match Report: Manchester City 4-2 Chelsea';day='2024-08-03'
        text="Manchester City starting XI: Ortega, Lewis, Phillips, Gvardiol, Wilson-Esbrand, Kovacic, O'Reilly, Bobb, McAtee, Grealish, Haaland"
    return (f'<title>{title} | News | Official Site | Chelsea Football Club</title><script>{{"content_publish_date":"{day}T12:00:00"}}</script><p>{text}</p><p>there was a goal for Oscar Bobb</p>').encode()


@pytest.mark.parametrize('opening',[True,False])
def test_exact_primary_positive_August_roster_report(opening):
    assert source.report(page(opening),opening=opening)==('2024-08-18' if opening else '2024-08-03')


@pytest.mark.parametrize('opening',[True,False])
@pytest.mark.parametrize('fault',['date','title','person','duplicate'])
def test_primary_match_mutations_refuse(opening,fault):
    raw=page(opening)
    if fault=='date':raw=raw.replace(b'2024-08-',b'2025-08-')
    if fault=='title':raw=raw.replace(b'<title>Match',b'<title>Other')
    if fault=='person':raw=raw.replace(b'Savinho' if opening else b'Bobb',b'Another')
    if fault=='duplicate':raw+=raw
    with pytest.raises(ValueError):source.report(raw,opening=opening)


@pytest.mark.parametrize('fault',[None,'season','carrier','club','alias','birthday','replacement'])
def test_alias_exception_never_becomes_a_fuzzy_name_or_DOB_rule(fault):
    release=SimpleNamespace(season='2024-25');club=dict(carrier_id=313,name='Manchester City')
    displaced=9246;names=['Savinho','#17 Sávio'];birthdays=['2004-04-10']*2;replacement='Oscar_Bobb'
    if fault=='season':release.season='2025-26'
    if fault=='carrier':displaced=9247
    if fault=='club':club['name']='Manchester United'
    if fault=='alias':names[1]='Another Savio'
    if fault=='birthday':birthdays[1]='1974-01-09'
    if fault=='replacement':replacement='Jacob_Wright'
    args=(release,displaced,9232,names,birthdays,club,replacement,743591)
    if fault is None:source.validate_pair(*args)
    else:
        with pytest.raises(ValueError):source.validate_pair(*args)
