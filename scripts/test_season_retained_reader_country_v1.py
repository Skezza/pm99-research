import pytest
from scripts import season_retained_reader_country_v1 as source

ORIGIN = 'https://www.11v11.com/players/example-person-123/'
BINDING = dict(provider=source.PROVIDER, provider_player_id=123,
               original_url=ORIGIN, url='https://r.jina.ai/' + ORIGIN)
BODY = (f'Title: Example Person\n\nURL Source: {ORIGIN}\n\nMarkdown Content:\n'
        '**Date of birth**03 December 1971\n**Place of birth**Elsewhere\n'
        '**Nationality**Dutch\n').encode()


def parse(raw=BODY, binding=None):
    return source.parse_country(raw, binding or BINDING,
                                actor_name='Example Person', birth_date='1971-12-03')


def test_explicit_same_person_country_without_other_fact_claims():
    result = parse()
    assert result['nationality'] == 'NED'
    assert result['source_format'].endswith('not-original-HTML')
    assert not result['target_season_ownership_claimed']
    assert not result['exclusive_citizenship_at_target_date_claimed']


def test_existing_known_wrong_country_dispatch_uses_same_parser():
    from scripts.season_known_wrong_profile_nationality_v1 import parse_profile_country
    result = parse_profile_country(BODY, BINDING,
                                   actor_name='Example Person', birth_date='1971-12-03')
    assert result == parse()


@pytest.mark.parametrize('old,new', [
    (b'Title: Example Person', b'Title: Another Person'),
    (b'1971', b'1972'),
    (b'URL Source: https://www.11v11.com/', b'URL Source: https://other.invalid/'),
    (b'**Nationality**Dutch', b'**Country of birth**Dutch'),
    (b'**Nationality**Dutch', b'**Nationality**Unknown'),
    (b'**Nationality**Dutch', b'**Nationality**Dutch\n**Nationality**German'),
])
def test_conflicting_or_absent_identity_country_refused(old, new):
    with pytest.raises(ValueError):
        parse(BODY.replace(old, new))


@pytest.mark.parametrize('key,value', [
    ('provider_player_id', 124), ('original_url', ORIGIN + '?other=1'),
    ('url', 'https://other.invalid/' + ORIGIN),
])
def test_origin_or_proxy_spoof_refused(key, value):
    with pytest.raises(ValueError):
        parse(binding={**BINDING, key: value})
