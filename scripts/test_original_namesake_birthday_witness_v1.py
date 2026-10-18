import pytest
from scripts import original_namesake_birthday_witness_v1 as witness


def john():
    return b'<html><h1>John Clarke (footballer, born 2004)</h1><table class="infobox"><tr><td class="fn">John Clarke</td></tr><tr><td class="bday">2004-04-24</td></tr><tr><td>2022\xe2\x80\x932026</td><td><a href="/wiki/Reading_F.C.">Reading</a></td><td>3 (0)</td></tr></table></html>'


def dylan():
    return b'<html><title>D. Lawlor | Cardiff</title><div class="field--name-field-cc-first-name">Dylan</div><div class="field--name-field-cc-last-name">Lawlor</div><div class="field--name-field-cc-date-of-birth"><time datetime="2006-01-01T12:00:00Z">01/01/2006</time></div></html>'


def test_independent_biography_full_name_date_and_historical_club():
    p = witness.parse('namesake-birthday-original-john-wikipedia', john())
    assert (p['name'], p['birth_date'], p['historical_club']) == ('John Clarke', '2004-04-24', 'Reading')
    p = witness.parse('namesake-birthday-primary-dylan-cardiff', dylan())
    assert (p['name'], p['birth_date'], p['historical_club']) == ('Dylan Lawlor', '2006-01-01', 'Cardiff City')
    assert not p['approves_current_club_ownership']


def test_original_absolute_wikipedia_career_link_is_equivalent():
    raw = john().replace(b'/wiki/Reading_F.C.', b'https://en.wikipedia.org/wiki/Reading_F.C.')
    assert witness.parse('namesake-birthday-original-john-wikipedia', raw)['historical_club'] == 'Reading'


@pytest.mark.parametrize('fault', ['another-name', 'another-era', 'another-club', 'duplicate-date', 'invalid-date'])
def test_ambiguous_or_unrelated_wikipedia_biography_refused(fault):
    raw = john()
    if fault == 'another-name': raw = raw.replace(b'John Clarke</td>', b'James Clarke</td>')
    if fault == 'another-era': raw = raw.replace(b'2022', b'1992')
    if fault == 'another-club': raw = raw.replace(b'Reading_F.C.', b'Other_F.C.')
    if fault == 'duplicate-date': raw = raw.replace(b'</table>', b'<tr><td class="bday">1999-04-24</td></tr></table>')
    if fault == 'invalid-date': raw = raw.replace(b'2004-04-24', b'2004-02-30')
    with pytest.raises(ValueError): witness.parse('namesake-birthday-original-john-wikipedia', raw)


@pytest.mark.parametrize('fault', ['name', 'date', 'duplicate'])
def test_ambiguous_or_changed_club_biography_refused(fault):
    raw = dylan()
    if fault == 'name': raw = raw.replace(b'>Dylan<', b'>David<')
    if fault == 'date': raw = raw.replace(b'2006-01-01', b'2006-02-30')
    if fault == 'duplicate': raw = raw.replace(b'</html>', b'<div class="field--name-field-cc-date-of-birth"><time datetime="2010-01-01T12:00:00Z">2010</time></div></html>')
    with pytest.raises(ValueError): witness.parse('namesake-birthday-primary-dylan-cardiff', raw)


def period_squad():
    key = 'namesake-birthday-original-gillingham-2025-squad'
    cells = '<td>-</td><td><a href="/harry-webster/profil/spieler/1313578">Harry Webster</a></td><td>08/09/2006 (19)</td>' + '<td>-</td>' * 7
    return ('<html><meta property="og:title" content="Gillingham FC - Detailed squad 25/26 (Detailed view)"><meta property="og:url" content="' + witness.KEYS[key] + '"><table class="items"><tbody><tr>' + cells + '</tr></tbody></table></html>').encode()


def test_original_period_stable_id_disambiguates_without_current_club_guess():
    value = witness.parse('namesake-birthday-original-gillingham-2025-squad', period_squad())
    assert value == dict(name='Harry Webster', birth_date='2006-09-08',
        historical_club='Gillingham', approves_current_club_ownership=False)


@pytest.mark.parametrize('fault', ['season', 'url', 'name', 'id', 'duplicate', 'date', 'missing-date'])
def test_period_person_row_must_bind_club_season_stable_id_and_birthday(fault):
    raw = period_squad()
    if fault == 'season': raw = raw.replace(b'25/26', b'24/25')
    if fault == 'url': raw = raw.replace(b'saison_id/2025', b'saison_id/2024')
    if fault == 'name': raw = raw.replace(b'Harry Webster</a>', b'Another Webster</a>')
    if fault == 'id': raw = raw.replace(b'/1313578', b'/99999')
    if fault == 'duplicate': raw = raw.replace(b'</tbody>', raw[raw.index(b'<tr>'):raw.index(b'</tr>') + 5] + b'</tbody>')
    if fault == 'date': raw = raw.replace(b'08/09/2006', b'31/02/2006')
    if fault == 'missing-date': raw = raw.replace(b'08/09/2006 (19)', b'-')
    with pytest.raises(ValueError): witness.parse('namesake-birthday-original-gillingham-2025-squad', raw)


def new_period_squad(key):
    club,_,name,id=witness.PERIOD_SQUADS[key]
    year='23/24' if '2023-squad' in key else '24/25'
    birthday='26/08/2007' if 'crewe-U18' in key else ('04/10/2000' if 'crawley' in key else ('10/04/2004' if 'man-city' in key else '02/11/2003'))
    cells=f'<td>-</td><td><a href="/person/profil/spieler/{id}">{name}</a></td><td>{birthday} (20)</td>'+'<td>-</td>'*7
    return (f'<html><meta property="og:title" content="{club} - Plantilla detallada {year} (Vista en detalle)">'
        f'<meta property="og:url" content="{witness.KEYS[key]}"><table class="items"><tbody><tr>{cells}</tr></tbody></table></html>').encode()


@pytest.mark.parametrize('key',[k for k in witness.PERIOD_SQUADS if k.startswith('six-dates-original-') and 'man-city' not in k])
def test_new_year_witness_binds_exact_period_person_and_logs_day_conflict(key):
    result=witness.parse(key,new_period_squad(key))
    assert result['period_person_source_id']==witness.PERIOD_SQUADS[key][3]
    assert result['source_period']==('2023-24' if '2023-squad' in key else '2024-25')
    if 'morecambe' in key or 'shrewsbury' in key:assert 'November1' in result['date_disagreement_note']


def test_crewe_youth_witness_does_not_claim_next_season_opening_ownership():
    key='six-dates-original-crewe-U18-2024-squad'
    result=witness.parse(key,new_period_squad(key))
    assert result['birth_date']=='2007-08-26'
    assert result['historical_club']=='Crewe Alexandra'
    assert result['source_period']=='2024-25'
    assert not result['approves_current_club_ownership']
    assert 'youth biography only' in result['identity_scope']
    with pytest.raises(ValueError):
        witness.parse(key,new_period_squad(key).replace(b'/1353755',b'/550679'))


@pytest.mark.parametrize('fault',[None,'flag','country','duplicate','id'])
def test_savio_nationality_requires_exact_country_cell_and_primary_alias(monkeypatch,fault):
    from pathlib import Path
    key='savio-nationality-original-man-city-2024-squad'
    raw=new_period_squad(key).replace(b'<td>-</td><td>-</td>',
        b'<td><img class="flaggenrahmen" alt="Brasil" title="Brasil" src="https://img.a.transfermarkt.technology/flagge/verysmall/26.png"/></td><td>-</td>',1)
    if fault=='flag':raw=raw.replace(b'/26.png',b'/189.png')
    if fault=='country':raw=raw.replace(b'Brasil',b'England')
    if fault=='duplicate':raw=raw.replace(b'</td><td>-</td>',b'<img class="flaggenrahmen" alt="Brasil" title="Brasil" src="https://img.a.transfermarkt.technology/flagge/verysmall/26.png"/></td><td>-</td>',1)
    if fault=='id':raw=raw.replace(b'/743591',b'/99999')
    primary=b'<html><h1>Who is new Man City signing Savinho?</h1><p>Also known as "Savio", he was born in Sao Mateus, Brazil, on 10 April 2004.</p></html>'
    monkeypatch.setattr(witness,'source_rows',lambda key:(Path('primary.html'),primary,{'path':'primary.html','sha256':'a'*64}))
    monkeypatch.setattr(witness.pipeline,'read_json_file',lambda path:{'url':'https://www.premierleague.com/en/news/4051917'})
    if fault is None:assert witness.parse(key,raw)['exact_period_nationality']=='BRA'
    else:
        with pytest.raises(ValueError):witness.parse(key,raw)


@pytest.mark.parametrize('fault',['club','season','id','name','duplicate'])
def test_new_bloxham_witness_rejects_other_club_period_or_namesake(fault):
    key='six-dates-original-morecambe-3697-2023-squad';raw=new_period_squad(key)
    if fault=='club':raw=raw.replace(b'FC Morecambe',b'Blackburn Rovers')
    if fault=='season':raw=raw.replace(b'23/24',b'24/25')
    if fault=='id':raw=raw.replace(b'/816515',b'/907216')
    if fault=='name':raw=raw.replace(b'Tom Bloxham',b'Another Bloxham')
    if fault=='duplicate':raw=raw.replace(b'</tbody>',raw[raw.index(b'<tr>'):raw.index(b'</tr>')+5]+b'</tbody>')
    with pytest.raises(ValueError):witness.parse(key,raw)


@pytest.mark.parametrize('fault',[None,'title','alias','date','url'])
def test_savio_single_name_needs_original_primary_alias_not_guess(monkeypatch,fault):
    from pathlib import Path
    raw=b'<html><h1>Who is new Man City signing Savinho?</h1><p>Also known as "Savio", he was born in Sao Mateus, Brazil, on 10 April 2004.</p></html>'
    if fault=='title':raw=raw.replace(b'Savinho?',b'Another?')
    if fault=='alias':raw=raw.replace(b'"Savio"',b'"Another"')
    if fault=='date':raw=raw.replace(b'10 April',b'11 April')
    url='https://www.premierleague.com/en/news/4051917' if fault!='url' else 'https://example.com/'
    monkeypatch.setattr(witness,'source_rows',lambda key:(Path('primary.html'),raw,{'path':'primary.html','sha256':'a'*64}))
    monkeypatch.setattr(witness.pipeline,'read_json_file',lambda path:{'url':url})
    key='six-dates-original-man-city-2024-squad'
    if fault is None:assert witness.parse(key,new_period_squad(key))['single_name_alias_verified']
    else:
        with pytest.raises(ValueError):witness.parse(key,new_period_squad(key))
