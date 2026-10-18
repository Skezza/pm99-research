#!/usr/bin/env python3
"""Derive explicit birthday reviews from independently replayed provider inputs.

No date-format guessing: two agreeing original identity sources must identify
one stable person. Conflicting plausible namesakes remain unresolved. Membership
and roles still come from the historical fixture, never a current player page.
"""
from datetime import date
from scripts import prepare_duplicate_club_disposition_v1 as source

SCHEMA = 'pm99-explicit-provider-person-identity-resolution-v1'
POLICY = 'replayed-annual-and-independent-publisher-biography-consensus-v1'


def too_young(birthday, fixture_date):
    born, day = date.fromisoformat(birthday), date.fromisoformat(fixture_date)
    return day.year-born.year-((day.month,day.day)<(born.month,born.day)) < 12


def derive(season, club, actual, annual, people, *, exclude_unpublished_bench_birth_dates=False):
    """Caller independently replays and binds originals; native build does so again."""
    resolutions, gaps, exclusions = [], [], []
    for group in ('starting_xi','published_bench'):
        for row in actual['identity_bridges'][group]:
            bio = row['soccerbase_person']
            matches = [p for p in annual['players'] if
                source.roster.normalise(p['name']) == source.roster.normalise(bio['name'])
                and isinstance(p.get('birth_date'),str)]
            if not matches:
                if bio['birth_date'] is None:
                    if group == 'published_bench' and exclude_unpublished_bench_birth_dates:
                        exclusions.append({'source_provider_person_id':bio['source_player_id'],
                            'name':bio['name'],'published_birth_date':None,
                            'reason':'optional-published-bench-DOB-unpublished-and-no-target-annual-biography'})
                        continue
                    gaps.append({'provider_person_id':bio['source_player_id'],'name':bio['name'],
                        'reason':'missing-provider-DOB-and-no-unique-full-name-target-annual-biography'})
                continue
            if any(p['birth_date']==bio['birth_date'] for p in matches):
                continue
            if len(matches)!=1:
                gaps.append({'provider_person_id':bio['source_player_id'],'reason':'annual-same-name-identity-ambiguous'})
                continue
            annual_date = matches[0]['birth_date']
            own = (source.transfer.unique_person({'name':bio['name'],'facts':{'birth_date':bio['birth_date']}},people)
                   if bio['birth_date'] is not None else None)
            agreed = source.transfer.unique_person({'name':bio['name'],'facts':{'birth_date':annual_date}},people)
            if own is not None and type(own['source_player_id']) is not int: own=None
            if agreed is not None and type(agreed['source_player_id']) is not int: agreed=None
            if own is not None and agreed is not None and not too_young(bio['birth_date'],actual['fixture']['date']):
                gaps.append({'provider_person_id':bio['source_player_id'],
                    'reason':'both-birthdays-identify-plausible-independent-publisher-namesakes'})
                continue
            if agreed is not None and not too_young(annual_date,actual['fixture']['date']):
                person, canonical = agreed, annual_date
                reason = 'Replayed target-season annual biography and independently replayed publisher identity agree; original Soccerbase birthday conflicts. Preserve the original disagreement and use the agreed stable identity; retain dated fixture membership and role.'
                extra = {}
            elif own is not None and not too_young(bio['birth_date'],actual['fixture']['date']):
                if exclude_unpublished_bench_birth_dates:
                    # This new route must not let two potentially copied
                    # catalogue biographies override a conflicting period
                    # annual. A positive period-specific identity witness is
                    # required separately; source counts are not a vote.
                    gaps.append({'provider_person_id':bio['source_player_id'],
                        'reason':'period-annual-DOB-conflict-needs-positive-historical-identity-witness'})
                    continue
                person, canonical = own, bio['birth_date']
                reason = 'Replayed original Soccerbase biography and independent publisher agree; target-season annual birthday conflicts. Explicitly retain the agreed original identity, discard that annual biography and log missing secondary facts; retain dated fixture membership and role.'
                extra = {'annual_fact_policy':'discard-conflicting-annual-biography',
                    'rejected_annual_birth_date':annual_date}
            else:
                gaps.append({'provider_person_id':bio['source_player_id'],'reason':'no-two-source-confirmed-adult-historical-identity'})
                continue
            resolutions.append({'source_provider_person_id':bio['source_player_id'],
                'name':bio['name'],'published_birth_date':bio['birth_date'],
                'canonical_birth_date':canonical,'canonical_source_player_id':person['source_player_id'],
                'corroboration_url':person['source_profile_url'],'reason':reason,**extra})
    document = {'schema_version':SCHEMA,'season':season,'club':club,'resolutions':resolutions,
        'derivation_policy':POLICY}
    if exclude_unpublished_bench_birth_dates:
        document['optional_bench_exclusions'] = exclusions
    if any(row['published_birth_date'] is None for row in resolutions):
        document['allow_explicitly_reviewed_missing_provider_birth_date']=True
    return document, gaps
