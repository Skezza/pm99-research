"""Produce Arsenal's capacity-fitting August25 from bound original sources.

Source preparation only, not native delivery. Correct first20 matchday IDs,
five positively dated August reserves, and exact original person identities.
Never silently copy the annual's two independently contradicted birth dates.
"""
import copy
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as person_source
from scripts import repair_prefix_selected_opening_sources_v1 as side_source
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_within_club_reserve_repair_v1 as facts
from scripts.capture_tachira_2014_original_people_v1 import source_rows
from scripts import capture_arsenal_coupled_primary_sources_20261016 as primary
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/arsenal-opening-2021-v1'
PUBLIC=registry.ROOT/'.local/duplicate-ownership-v3/published-person-identities-r2.json'
REPAIR=registry.ROOT/'.local/duplicate-ownership-v3/exact-side-opening-source-repairs-r4/capture-repairs/2021-22/club-309.json'
RESERVES=(230784,435338,93720,58864,340324)
REVIEWED_DATES={335721:('1997-11-08','1997-10-08'),253341:('1994-11-09','1995-09-20')}


def person_facts(id,person,aliases,annual):
    matching=[r for r in annual if roster.normalise(r['name']) in aliases]
    if len(matching)!=1:raise ValueError('one original annual identity required for published Arsenal person '+str(id))
    raw=matching[0];correction=None
    if raw['birth_date']!=person['birth_date']:
        if REVIEWED_DATES.get(id)!=(raw['birth_date'],person['birth_date']):
            raise ValueError('unreviewed annual/published-person birthday disagreement')
        correction=dict(annual=raw['birth_date'],original_person=person['birth_date'],
            policy='explicit-source-conflict-person-ID-and-full-name-not-a-forced-bad-DOB-join')
    if raw['position'] not in ('G','D','M','F'):raise ValueError('opening25 broad role source missing')
    result=copy.deepcopy(raw);result['birth_date']=person['birth_date']
    return result,correction


def other_period_facts(person,aliases,captures,verifier):
    """Other-club annuals can establish facts, never Arsenal membership.

    Departed January players are absent from Arsenal's end-season annual.
    Membership instead comes from the independent August matchday/press proof.
    Do not transfer another club's shirt number or majority-vote conflicting
    secondary values into the opening Arsenal squad.
    """
    matches=[]
    for capture in captures:
        rows=[r for r in capture['players'] if roster.normalise(r['name']) in aliases
            and r.get('birth_date')==person['birth_date']]
        if not rows:continue
        proof=verifier.verify(capture)
        if proof['status']!='raw-source-reparsed':continue
        for row in rows:
            matches.append((row,dict(club=capture['club_name'],source_path=capture['source_path'],
                source_sha256=capture['source_sha256'],raw_evidence=proof)))
    roles={r['position'] for r,_ in matches}
    if not matches or len(roles)!=1 or not roles<={'G','D','M','F'}:
        raise ValueError('missing or contradictory target-period broad role for '+person['name'])
    row=dict(name=person['name'],birth_date=person['birth_date'],position=next(iter(roles)),shirt_number=None)
    disagreements={}
    for field in ('nationality','height_cm','weight_kg'):
        values={r.get(field) for r,_ in matches}
        row[field]=next(iter(values)) if len(values)==1 else None
        if len(values)>1:disagreements[field]=sorted(values,key=str)
    return row,dict(policy='same-period-original-secondary-facts-only-not-owner-or-shirt-number',
        original_sources=[p for _,p in matches],secondary_disagreements=disagreements,
        shirt_number_gap='Different-club shirt numbers are not Arsenal shirt-number evidence')


def main():
    repair=pipeline.read_json_file(REPAIR);capture_path=registry.ROOT/repair['original_capture_path']
    if registry.sha256_file(capture_path)!=repair['original_capture_sha256']:
        raise ValueError('original Arsenal fixture capture changed')
    capture=pipeline.read_json_file(capture_path)
    corrected,evidence,_=side_source.replay(repair['before'],capture,capture_path.parent/'cache')
    if corrected!=repair['after'] or corrected['first_league_fixture_date']!='2021-08-13':
        raise ValueError('exact Arsenal first-league side no longer reproduces')
    people,_=person_source.merge({},pipeline.read_json_file(PUBLIC))
    by={id:person for rows in people.values() for id,person in rows.items()}
    aliases={id:set() for id in by}
    for (name,_),rows in people.items():
        for id in rows:aliases[id].add(name)
    release=registry.load_preferred_release('2021-22')
    club=next(c for c in pipeline.read_json_file(release.package_path)['clubs'] if c['carrier_id']==309)
    if club['name']!='Arsenal':raise ValueError('target Arsenal identity changed')
    annual,annual_proof=facts.annual_capture('2021-22',club)
    proofs=[]
    for key,url in primary.SOURCES.items():
        _,raw,binding=source_rows(key);primary.validate(raw,url)
        proofs.append(dict(binding,url=url))
    _,raw,binding=source_rows('arsenal-2021-primary-opening-brentford-20261016')
    from bs4 import BeautifulSoup
    text=' '.join(BeautifulSoup(raw,'html.parser').get_text(' ',strip=True).split())
    if 'Arsenal: Leno; Chambers, White, Mari, Tierney; Xhaka (c), Lokonga; Pepe, Smith-Rowe, Martinelli; Balogun' not in text:
        raise ValueError('independent primary first XI disagrees')
    proofs.append(binding)
    selected=[]
    for field,kind in (('starting_xi','starting_xi'),('substitutes','published_first_league_bench')):
        selected.extend((int(r['source_player_id']),kind) for r in corrected[field])
    selected.extend((id,'positive-August-friendly-or-opening-injury-list-reserve') for id in RESERVES)
    if len(selected)!=25 or len({id for id,_ in selected})!=25:
        raise ValueError('Arsenal target must be exact unique twenty matchday plus five August reserves')
    desired=[];captures,_=roster.load_sources('2021-22');verifier=roster.SourceVerifier('2021-22')
    for id,kind in selected:
        if id not in by:raise ValueError('published original person missing: '+str(id))
        if any(roster.normalise(r['name']) in aliases[id] for r in annual['players']):
            row,conflict=person_facts(id,by[id],aliases[id],annual['players'])
            fact_origin=dict(policy='original-Arsenal-period-annual',raw_evidence=annual_proof)
        else:
            row,fact_origin=other_period_facts(by[id],aliases[id],captures,verifier);conflict=None
        desired.append(dict(source_person=by[id],source_player=row,membership=kind,
            annual_date_conflict=conflict,secondary_fact_origin=fact_origin,source_identity_policy=person_source.POLICY))
    ROOT.mkdir(parents=True,exist_ok=True)
    retained(ROOT/'source-package.json',dict(season='2021-22',club='Arsenal',club_carrier_id=309,
        first_league_fixture_date='2021-08-13',formation='4-2-3-1',manager='Mikel Arteta',
        matchday_and_reserve_primary_proofs=proofs,original_exact_club_opening=evidence,
        annual_source=annual_proof,source_repair=dict(path=registry.relative_workspace_path(REPAIR),sha256=registry.sha256_file(REPAIR)),
        published_people=dict(path=registry.relative_workspace_path(PUBLIC),sha256=registry.sha256_file(PUBLIC)),
        desired_people=desired,native_writes=0,recipe_writes=0,publication_authorised=False,
        next_required='Fit latest native25, pair four existing outside owners with independently sourced replacements, remove late signings without new duplicates, then SOURCE/native/runner delivery.'))
    print(dict(sourced_players=25,starting_XI=11,bench=9,positive_August_reserves=5,
        explicit_annual_date_corrections=sum(r['annual_date_conflict'] is not None for r in desired),native_writes=0),flush=True)


if __name__=='__main__':main()
