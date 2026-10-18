"""Narrow, explicit user-approved August lineups and surname-only identities.

These declarations preserve gaps. They never certify a missing league XI,
guess a first name, assign a different provider's person ID, or approve a build.
"""
from datetime import date
import re

SCHEMA = 'pm99-approved-august-source-fallback-v1'
SESSION = '01a0592d-fcd5-7262-a637-743a8253d9b4'
APPROVAL = ('Yes, use the August cup or friendly lineups and keep the published '
            'surnames where needed. Log the gaps clearly. Keep going and close '
            'out the remaining seven cases, then work through the rest of the checklist.')


def lineup(*, season, fixture_date, competition, source_binding, missing_league_xi):
    year = int(season[:4])
    if season != f'{year:04d}-{(year + 1) % 100:02d}':
        raise ValueError('invalid season label')
    fixture = date.fromisoformat(fixture_date)
    if fixture.year != year or fixture.month != 8 or competition not in ('cup', 'friendly'):
        raise ValueError('approval applies only to target-season August cup/friendly lineups')
    if missing_league_xi is not True:
        raise ValueError('fallback must retain the missing league XI explicitly')
    if (not source_binding.get('path') or
            not re.fullmatch(r'[0-9a-f]{64}', source_binding.get('sha256', ''))):
        raise ValueError('fallback requires a bound original source')
    return dict(schema_version=SCHEMA, source_session=SESSION, user_approval=APPROVAL,
        season=season, date=fixture_date, competition=competition,
        original_source=dict(source_binding), league_starting_xi_missing=True,
        substituted_first_league_xi=False, historically_perfect=False,
        gap='First league starting XI unavailable; using a published August '+competition+' XI.')


def surname(*, published_surname, provider, club, fixture_date, source_binding):
    date.fromisoformat(fixture_date)
    if (not published_surname or published_surname != published_surname.strip()
            or not provider or not club or not source_binding.get('path')
            or not re.fullmatch(r'[0-9a-f]{64}', source_binding.get('sha256', ''))):
        raise ValueError('surname-only identity requires literal published label and original fixture binding')
    return dict(schema_version=SCHEMA, source_session=SESSION, user_approval=APPROVAL,
        published_surname=published_surname, given_name=None, full_name_missing=True,
        provider=provider, club=club, fixture_date=fixture_date,
        original_source=dict(source_binding), cross_provider_person_id=None,
        gap='First name unavailable; retaining published surname without expansion.')
