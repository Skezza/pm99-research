"""Compare an unpublished pair to its exact baseline using the pinned reader."""
import argparse
import collections
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import audit_published_player_identities_v1 as identities
from scripts import prepare_duplicate_whole_club_native_v1 as native
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as public


def groups(package,people):
    result=collections.defaultdict(list)
    for player in package['players']:
        key=identities.key(player,people)
        if key is not None:
            result[key].append((player['carrier_id'],player['club_id']))
    return {key:rows for key,rows in result.items() if len({club for _,club in rows})>1}


def verify(candidate,person_input,output):
    if output.exists():raise ValueError('identity comparison is immutable')
    receipt=json.loads((candidate/'candidate-receipt.json').read_text())
    pair=json.loads(native.original(receipt['source_pair']).read_text())
    base=registry.load_registered_release(pair['season'],pair['release_id'])
    before=json.loads(base.package_path.read_text());after=json.loads((candidate/'season-package.json').read_text())
    supplement_sha=registry.sha256_file(person_input)
    people,snapshot=identities.load_identity_snapshot()
    people,merge=public.merge(people,json.loads(person_input.read_text()))
    old,new=groups(before,people),groups(after,people)
    if new.keys()-old.keys():raise ValueError('new cross-club person candidates introduced')
    proposals=[json.loads(native.original(b).read_text()) for b in pair['proposals']]
    corrected={r['carrier_id'] for p in proposals for r in p['allocation']}
    players={p['carrier_id']:p for p in after['players']}
    if any(players[p['carrier_id']]!=p for p in before['players'] if p['carrier_id'] not in corrected):
        raise ValueError('unselected recipe player changed')
    if any(any(id in corrected for id,_ in rows) for rows in new.values()):
        raise ValueError('replacement remains in an outside cross-club identity group')
    archive=(candidate/'game/DBDAT/MINIFOTO.PKF').read_bytes()
    cleared,offsets=native.delta.no_photo_archive(archive,corrected)
    if cleared!=archive or any((candidate/'game/DBDAT/MINIFOTO'/f'J96{id:05d}.BMP').exists() for id in corrected):
        raise ValueError('retired player portrait is still attached to a replacement')
    from scripts import season_whole_club_keeper_exchange_v1 as keeper
    jug=(candidate/'game/DBDAT/JUG98030.FDI').read_bytes();eq=(candidate/'game/DBDAT/EQ98030.FDI').read_bytes()
    replayed,changes=keeper.replay(jug,eq,after,candidate/'season-package.json')
    if replayed!=jug:raise ValueError('bound keeper-order replay is not idempotent')
    if registry.sha256_file(person_input)!=supplement_sha:raise ValueError('identity input changed during comparison')
    proof={'schema_version':'pm99-paired-club-independent-identity-difference-v1','season':pair['season'],
        'candidate_receipt_sha256':registry.sha256_file(candidate/'candidate-receipt.json'),
        'package_sha256':registry.sha256_file(candidate/'season-package.json'),
        'source_release_id':pair['release_id'],'identity_snapshot':snapshot,
        'person_input':{'path':registry.relative_workspace_path(person_input),'sha256':supplement_sha},
        'before_cross_club_candidate_groups':len(old),'after_cross_club_candidate_groups':len(new),
        'removed_candidate_groups':len(old.keys()-new.keys()),'introduced_candidate_groups':0,
        'corrected_slots':sorted(corrected),'replacement_cross_club_candidates':0,
        'unselected_recipe_players_identical':True,'stale_portraits_cleared':True,
        'keeper_recipe_replay_idempotent':True,'registered':False,'duplicate_cleanup_complete':False}
    pipeline.write_canonical_json(output,proof);return proof


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('candidate','person-input','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();r=verify(a.candidate,a.person_input,a.output)
    print(json.dumps({k:r[k] for k in ('corrected_slots','before_cross_club_candidate_groups','after_cross_club_candidate_groups','introduced_candidate_groups','registered')}),flush=True)
