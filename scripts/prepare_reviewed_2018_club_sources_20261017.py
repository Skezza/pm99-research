"""Re-use existing source rules after eight independently verified DOB reviews.

Only three bounded source proposals, no scan, native writes or publication.
"""
from datetime import date
from pathlib import Path
import re
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import prepare_duplicate_club_disposition_v1 as whole
from scripts import derive_provider_identity_resolutions_v1 as identities
from scripts import replay_original_soccerbase_openings_v1 as replay
from scripts.scan_duplicate_whole_club_sources_v1 import BoundSnapshotCache
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

AUDIT=registry.ROOT/'.local/consolidated-audit-20261009'
REPORT=AUDIT/'luna-closeout-20261017/2018-dob-independent-corroboration.json'
REPORT_SHA='6b071698450bd1604cb34f0712a1111d7a4f77e108d87f370a65193491faa5ae'
OUT=AUDIT/'reviewed-original-club-sources-2018-v1'

def wiki_identity(raw):
    field=lambda key:re.findall(r'^\|\s*'+key+r'\s*=\s*([^\n]*)',raw,re.M|re.I)
    name,full,born=field('name'),field('fullname'),field('birth_date')
    if any(len(values)!=1 for values in (name,full,born)):raise ValueError('one explicit infobox identity/date required')
    template=re.match(r'\{\{birth date and age\|([^}]+)\}\}',born[0],re.I)
    if template is None:raise ValueError('unsupported original DOB template; never guess')
    pieces=[part.strip() for part in template[1].split('|')]
    if any(not(part.isdigit() or part=='df=y') for part in pieces):raise ValueError('unexpected date argument')
    numbers=[int(part) for part in pieces if part.isdigit()]
    if len(numbers)!=3:raise ValueError('one original year/month/day required')
    return name[0].strip(),full[0].split('<ref',1)[0].strip(),date(*numbers).isoformat()

def run():
    if (OUT/'summary.json').exists():raise ValueError('completed source batch must not repeat')
    if registry.sha256_file(REPORT)!=REPORT_SHA:raise ValueError('review report changed')
    report=pipeline.read_json_file(REPORT);reviews=report['reviews']
    if len(reviews)!=8 or len({r['soccerbase_id'] for r in reviews})!=8:raise ValueError('exact eight people required')
    for row in reviews:
        source=row['independent_source'];path=registry.ROOT/source['cached_body']
        if registry.sha256_file(path)!=source['sha256']:raise ValueError('independent raw body changed')
        raw=path.read_text();name,full,born=wiki_identity(raw)
        if (name,full,born)!=(row['display_name'],row['full_name'],row['soccerbase_dob']):
            raise ValueError('independent raw identity/DOB differs from the proposed review')
        if row['club'] not in raw:raise ValueError('independent career context lacks the source club')
        for key in ('soccerbase_profile','numeric_match_link'):
            evidence=row[key]
            if registry.sha256_file(registry.ROOT/evidence['path'])!=evidence['sha256']:
                raise ValueError('original numeric match/biography changed')
    OUT.mkdir(parents=True,exist_ok=True)
    prior=pipeline.read_json_file(registry.ROOT/'.local/duplicate-ownership-v3/targeted-original-opening-proposals-r3/2018-19/ownership-plan.json')
    bindings=prior['bindings'];pin=bindings['snapshot'];cache=BoundSnapshotCache()
    people,events,actualpin=cache.load(registry.ROOT/pin['path'],registry.ROOT/pin['pinned_receipt_path'])
    if actualpin!=pin:raise ValueError('original snapshot differs')
    people,_,_=cache.merge_public(people,events,bindings)
    captures,_=whole.roster.load_sources('2018-19');base=registry.load_preferred_release('2018-19')
    cap=pipeline.read_json_file(registry.ROOT/'.local/duplicate-ownership-v3/capacity-window-proposals-r1/2018-19/ownership-plan.json')
    bundle=cap['bindings'].get('same_carrier_name_capacity')
    if bundle is None:raise ValueError('explicit existing capacity bundle required')
    decisions=[]
    for target,reported in (('Chesterfield','Chesterfield'),('Fylde','AFC Fylde'),('Leyton Orient','Leyton Orient')):
        path=OUT/(whole.roster.normalise(target)+'.json');decision=path.with_name(path.stem+'-decision.json')
        if path.exists() or decision.exists():raise ValueError('inspect existing partial source decision before continuing')
        matches=[c for c in captures if c['source_path'].startswith('soccerbase/team/') and whole.club_keys(target)&whole.club_keys(c['club_name'])]
        annuals=[c for c in captures if c['source_path'].endswith('.txt') and whole.club_keys(target)&whole.club_keys(c['club_name'])]
        if len(matches)!=1 or len(annuals)!=1:raise ValueError('one exact original capture and annual required')
        actual=replay.replay_club('2018-19',matches[0],people,True)
        expected=[r for r in reviews if r['club']==reported]
        for row in expected:
            players=[p['soccerbase_person'] for group in actual['identity_bridges'].values() for p in group
                if p['soccerbase_person']['provider_player_id']==row['soccerbase_id']]
            if len(players)!=1 or (players[0]['name'],players[0]['birth_date'])!=(row['display_name'],row['soccerbase_dob']):
                raise ValueError('independently replayed numeric first-fixture identity differs')
        review,gaps=identities.derive('2018-19',target,actual,annuals[0],people)
        if gaps:
            result=dict(target=target,status='source-gap',reason='existing source rule requires independent numeric publisher identity',
                identity_gaps=gaps,independent_Wikipedia_source_agreement_not_a_policy_waiver=True)
            retained(decision,result);decisions.append(result);print(result,flush=True);continue
        if {int(r['source_provider_person_id'].split(':')[1]) for r in review['resolutions']}!={r['soccerbase_id'] for r in expected}:
            raise ValueError('independent original identity resolutions differ from the reviewed eight')
        review['independent_wikipedia_evidence']=[dict(path=r['independent_source']['cached_body'],sha256=r['independent_source']['sha256'],
            url=r['independent_source']['raw_url']) for r in expected]
        review_path=OUT/(path.stem+'-identity-review.json');retained(review_path,review)
        try:
            whole.prepare('2018-19',3322,target,registry.ROOT/bindings['published_person_supplement']['path'],
                registry.ROOT/bindings['published_transfer_supplement']['path'],
                registry.ROOT/bindings['soccerbase_opening_sources']['club_entities']['path'],path,
                capacity_bundle=bundle,baseline_release_id=base.release_id,inspect_collisions=True,
                snapshot_binding=pin,snapshot_loader=cache.load,public_loader=cache.merge_public,
                allow_keeper_order_exchange=True,identity_review_path=review_path,
                allow_original_matchday_only_club_identity=True,allow_original_provider_career_reserves=True)
            proposal=pipeline.read_json_file(path)
            result=dict(target=target,status='complete-source-fit' if proposal['allocation_gap'] is None else 'allocation-gap',
                outside_collisions=proposal['outside_collisions'],proposal_path=registry.relative_workspace_path(path),
                proposal_sha256=registry.sha256_file(path),reason=proposal['allocation_gap'])
        except ValueError as exc:result=dict(target=target,status='source-gap',reason=str(exc))
        retained(decision,result);decisions.append(result);print(result,flush=True)
    cache.verify()
    retained(OUT/'summary.json',dict(decisions=decisions,native_writes=0,publication_authorised=False,
        original_review_sha256=REPORT_SHA,current_release_id=base.release_id))

if __name__=='__main__':run()
