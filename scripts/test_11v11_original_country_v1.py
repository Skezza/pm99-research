import pytest

from scripts import season_retained_reader_country_v1 as source

URL = 'https://www.11v11.com/players/example-person-123/'
BINDING = dict(provider=source.ORIGINAL_PROVIDER, provider_player_id=123, url=URL)
BODY = (f'<html><head><title>Example Person Football Player Statistics | 11v11.com</title>'
        f'<meta property="og:url" content="{URL}"></head><body><h1>Example Person</h1>'
        '<div class="basicData"><table>'
        '<tr><td>Date of birth</td><td>03 December 1971</td></tr>'
        '<tr><td>Place of birth</td><td>Elsewhere</td></tr>'
        '<tr><td>Nationality</td><td>English</td></tr>'
        '</table></div></body></html>').encode()


def parse(raw=BODY, binding=None):
    return source.parse_original_country(raw, BINDING if binding is None else binding,
                                         actor_name='Example Person', birth_date='1971-12-03')


def test_original_explicit_country_and_common_writer_dispatch():
    from scripts.season_known_wrong_profile_nationality_v1 import parse_profile_country
    result = parse()
    assert result['nationality'] == 'ENG'
    assert result['source_format'] == 'original-profile-HTML'
    assert not result['target_season_ownership_claimed']
    assert not result['exclusive_citizenship_at_target_date_claimed']
    assert parse_profile_country(BODY, BINDING, actor_name='Example Person',
                                 birth_date='1971-12-03') == result


@pytest.mark.parametrize('old,new', [
    (b'<h1>Example Person</h1>', b'<h1>Another Person</h1>'),
    (b'<title>Example Person', b'<title>Another Person'),
    (b'1971', b'1972'),
    (b'03 December', b'12 March'),
    (b'<td>Nationality</td>', b'<td>Country of birth</td>'),
    (b'<td>English</td>', b'<td>British</td>'),
    (b'<td>English</td>', b'<td>ZZZ</td>'),
    (b'<td>English</td>', b'<td>English, French</td>'),
    (b'<td>English</td>', b'<td></td>'),
    (b'</table>', b'<tr><td>Nationality</td><td>French</td></tr></table>'),
    (b'</table>', b'<tr><td>Date of birth</td><td>03 December 1971</td></tr></table>'),
    (b'class="basicData"', b'class="otherData"'),
    (b'property="og:url"', b'property="unrelated"'),
    (b'</head>', f'<meta property="og:url" content="{URL}"></head>'.encode()),
    (b'</body>', b'<h1>Example Person</h1></body>'),
    (b'</body>', b'<div class="basicData"></div></body>'),
    (URL.encode(), URL.replace('-123/', '-124/').encode()),
])
def test_conflicting_or_absent_original_identity_refused(old, new):
    with pytest.raises(ValueError):
        parse(BODY.replace(old, new))


@pytest.mark.parametrize('key,value', [
    ('provider_player_id', 124), ('provider_player_id', True),
    ('provider', source.PROVIDER), ('url', URL + '?other=1'),
    ('url', URL.replace('www.11v11.com', 'www.11v11.com.evil.invalid')),
])
def test_source_binding_spoof_refused(key, value):
    with pytest.raises(ValueError):
        parse(binding={**BINDING, key: value})


def test_reader_challenge_or_title_only_is_not_an_original_biography():
    with pytest.raises(ValueError):
        parse(b'Title: Example Person\nURL Source: ' + URL.encode())
