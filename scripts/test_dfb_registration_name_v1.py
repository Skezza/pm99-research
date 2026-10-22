import pytest

from scripts import season_opening_identity_exchange_v1 as subject


@pytest.mark.parametrize('bad', [None, 'substring', 'given', 'different-person'])
def test_family_display_keeps_exact_source_identity_and_native_encoding(tmp_path, monkeypatch, bad):
    path = tmp_path / 'profile.html'
    path.write_text('<h1 class="data-header__headline-wrapper"><span class="data-header__shirt-number">'
        '#10</span>Özkan <strong>Yıldırım</strong></h1>')
    monkeypatch.setattr(subject, 'original', lambda value: path)
    monkeypatch.setattr(subject, 'read_transfermarkt_profile', lambda *args:
        dict(published_full_name='Özkan Yıldırım', published_birth_date='1993-04-10'))
    selection = dict(name='Özkan Yıldırım', birth_date='1993-04-10', provider_player_id=83256,
        native_display_name='Yıldırım', profile='profile')
    if bad == 'substring': selection['native_display_name'] = 'dırım'
    if bad == 'given': selection['native_display_name'] = 'Özkan'
    if bad == 'different-person': selection['birth_date'] = '1993-04-11'
    if bad is None:
        assert subject.published_profile_family_display(selection, {'profile':{}}) == 'Yildirim'
    else:
        with pytest.raises(ValueError, match='exact published'):
            subject.published_profile_family_display(selection, {'profile':{}})


@pytest.mark.parametrize('variant', ['direct', 'linked', 'foreign', 'multiple',
    'mixed', 'wrong-name', 'wrong-dob', 'wrong-date', 'wrong-path'])
def test_registration_is_exact_person_and_row_bound(tmp_path, monkeypatch, variant):
    name = 'Santiago García'
    href = 'https://datencenter.dfb.de/profil/223663?historize_title=Werder'
    if variant == 'foreign': href = href.replace('datencenter.dfb.de', 'example.org')
    if variant == 'wrong-path': href = href.replace('/profil/', '/teams/')
    cell = name if variant == 'direct' else f'<a href="{href}">{name}</a>'
    if variant == 'multiple': cell += f'<a href="{href}">{name}</a>'
    if variant == 'mixed': cell = 'Someone Else ' + cell
    if variant == 'wrong-name': cell = cell.replace(name, 'Someone Else')
    dob = '08.07.1988' if variant != 'wrong-dob' else '08.07.1989'
    date = '01.09.2013' if variant != 'wrong-date' else '02.09.2013'
    path = tmp_path / 'dfb.html'
    path.write_text(f'<h2>Werder Bremen</h2><h3>Kader Bundesliga 2013/2014</h3>'
        f'<p>Reference 01.09.2013 Santiago García</p><table><tr class="c-Table-body-row">'
        f'<td>3</td><td>{cell}<small>(ab {date})</small></td><td>{dob}</td></tr></table>')
    monkeypatch.setattr(subject, 'original', lambda value: path)
    source = dict(url='https://datencenter.dfb.de/competitions/bundesliga/seasons/2013-2014/teams/werder-bremen',
        anchors=['Santiago García', '01.09.2013'], date_anchor='01.09.2013', event_date='2013-09-01',
        dfb_registration_row=dict(season_start_year=2013, club_heading='Werder Bremen',
            roster_heading='Kader Bundesliga 2013/2014', full_name=name, birthday_literal='08.07.1988'))
    if variant in ('direct', 'linked'):
        subject.dated_source(source)
    else:
        with pytest.raises(ValueError, match='exact person'):
            subject.dated_source(source)
