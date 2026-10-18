import pytest
from scripts.bidoglio_original_birthday_resolution_v1 import parse


def sources():
    return (
        '<html><h1>Héctor Pablo Bidoglio, un rosarino con corazón Vinotinto</h1><time datetime="2020-04-15T07:00:38-04:00"></time><p>El texto del que es considerado himno menciona Héctor Pablo Bidoglio, mediocampista que nace un 5 de febrero de 1968.</p></html>'.encode(),
        '<html><h1>Héctor Bidoglio</h1><table class="infobox"><tr><td>Nacimiento Rosario 5 de febrero de 1968 (58 años)</td></tr></table></html>'.encode(),
        '<html><table><tr><td>Hï¿½ctor Pablo Bidoglio</td><td>15/02/1968</td></tr></table></html>'.encode('cp1252'))


def test_conflict_is_retained_and_only_static_birthday_approved():
    value = parse(*sources())
    assert value['birth_date'] == '1968-02-05'
    assert value['contrary_period_birth_date'] == '1968-02-15'
    assert value['birthday_approved']
    assert value['native_writes'] == 0
    assert not value['approves_opening_membership'] and not value['approves_current_roles']


@pytest.mark.parametrize('fault', ['another-person', 'another-date', 'another-year', 'duplicate-paragraph', 'contrary-date'])
def test_source_disagreement_or_ambiguous_identity_refused(fault):
    raw = list(sources())
    if fault == 'another-person': raw[0] = raw[0].replace(b'Pablo Bidoglio, mediocampista', b'Pablo Other, mediocampista')
    if fault == 'another-date': raw[1] = raw[1].replace(b'5 de febrero', b'15 de febrero')
    if fault == 'another-year': raw[0] = raw[0].replace(b'1968', b'1969')
    if fault == 'duplicate-paragraph': raw[0] = raw[0].replace(b'</html>', raw[0][raw[0].index(b'<p>'):raw[0].index(b'</p>') + 4] + b'</html>')
    if fault == 'contrary-date': raw[2] = raw[2].replace(b'15/02/1968', b'05/02/1968')
    with pytest.raises(ValueError): parse(*raw)
