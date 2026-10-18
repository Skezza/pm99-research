"""Independent exact-edition country contradiction check; no native writes.

A disagreement is a review requirement, not automatic proof that either
publisher is right. No present-day nationality, other edition, bare surname or
different birthday may be substituted for a historical FIFA witness.
"""
import csv
from functools import lru_cache
from scripts import season_exact_fifa_role_delta_v1 as fifa
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_player_facts_audit_v1 as facts
from scripts import season_release_registry_v1 as registry

LABELS={'Republic of Ireland':'IRL','Congo DR':'COD','Congo':'CGO','China PR':'CHN',
    'Korea Republic':'KOR','Korea DPR':'PRK','FYR Macedonia':'MKD'}


def code(label):
    return LABELS.get(label) or facts.country(label)


@lru_cache(maxsize=1)
def load(file_sha):
    result={}
    with fifa.identity.old.FIFA.open(newline='') as stream:
        for row in csv.DictReader(stream):
            key=(int(row['fifa_version']),row['dob'])
            result.setdefault(key,[]).append({k:row[k] for k in
                ('player_id','long_name','short_name','dob','nationality_name','fifa_version','fifa_update_date')})
    return result


def match(player,season,index):
    edition=int(season[:4])-1999;birth=player['facts'].get('birth_date')
    if not 15<=edition<=23 or not isinstance(birth,str):return None
    alternatives=fifa.names(player);hits={}
    for row in index.get((edition,birth),[]):
        if any(roster.normalise(name) in (roster.normalise(row['long_name']),roster.normalise(row['short_name']))
                or fifa.identity.subsequence(fifa.identity.tokens(name),fifa.identity.tokens(row['long_name'])) for name in alternatives):
            hits.setdefault(row['player_id'],[]).append(row)
    if len(hits)!=1:return None
    rows=next(iter(hits.values()))
    if len({r['nationality_name'] for r in rows})!=1:return None
    return min(rows,key=lambda row:row['fifa_update_date'])


def check(row,season,*,index=None,file_sha=None):
    if not 15<=int(season[:4])-1999<=23:
        return dict(status='no-exact-target-edition',country_truth_approved=False)
    if index is None:
        file_sha=registry.sha256_file(fifa.identity.old.FIFA);index=load(file_sha)
    witness=match(row['before_player'],season,index)
    if witness is None:return dict(status='no-unambiguous-exact-name-DOB-FIFA-witness',country_truth_approved=False)
    nationality=code(witness['nationality_name'])
    if nationality is None:return dict(status='unmapped-exact-FIFA-country',source=witness,country_truth_approved=False)
    return dict(status='corroborated' if nationality==row['nationality'] else 'contradiction-requires-resolution',
        proposed_country=row['nationality'],FIFA_country=nationality,source=witness,
        source_file=dict(path=registry.relative_workspace_path(fifa.identity.old.FIFA),sha256=file_sha),
        country_truth_approved=False,source_disagreement_is_not_automatic_country_override=True)
