"""Choose a reproducible single historical game flag, retaining disagreements.

This is source adjudication, not a native-writing policy or a claim of sole
citizenship. Exact-period FIFA supplies the game flag where annuals disagree,
except independently dated biography evidence disambiguating the two Congos.
Missing evidence is held, never filled from present-day citizenship.
"""
import copy

from scripts import season_country_fifa_crosscheck_v1 as fifa
from scripts import season_cgo_disambiguation_v2 as cgo
from scripts import season_original_passport_alias_v1 as passport


def resolve(row, season, *, index, file_sha):
    biography, biography_gap, alias, witness = None, None, None, None
    if row['nationality'] == 'CGO':
        try:
            biography = cgo.resolve(row, season)
        except ValueError as exc:
            biography_gap = str(exc)
    check = fifa.check(row, season, index=index, file_sha=file_sha)
    if check.get('source') is not None and check.get('FIFA_country'):
        witness = check['source']
    elif row['nationality'] == 'CGO' and biography is None and 15 <= int(season[:4]) - 1999 <= 23:
        alias = passport.original_alias(row['source_person'])
        if alias is not None:
            player = copy.deepcopy(row['before_player'])
            player['name'] = player['source_name'] = alias['name']
            witness = fifa.match(player, season, index)
    fifa_country = fifa.code(witness['nationality_name']) if witness else None
    if biography is not None:
        country, rule = biography['country'], 'independent-prior-dated-Congo-geography'
    elif fifa_country is not None:
        country, rule = fifa_country, 'exact-target-FIFA-single-game-flag-not-exclusive-citizenship'
    elif row['nationality'] != 'CGO' and check['status'] != 'contradiction-requires-resolution':
        country, rule = row['nationality'], 'original-unambiguous-period-squad-country'
    else:
        raise ValueError('ambiguous historical country has no dated biography or exact FIFA witness: '
            + str(row['carrier_id']))
    return dict(nationality=country, original_annual_nationality=row['nationality'], resolution_rule=rule,
        independent_biography=biography, independent_biography_gap=biography_gap,
        exact_FIFA_witness=witness, original_passport_name_alias=alias,
        FIFA_source_file=dict(path=fifa.registry.relative_workspace_path(fifa.fifa.identity.old.FIFA), sha256=file_sha),
        FIFA_country=fifa_country, source_disagreement_retained=True,
        exclusive_citizenship_or_target_season_caps_claimed=False)
