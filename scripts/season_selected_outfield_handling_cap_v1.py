"""Selected, source-established outfield actors: cap Handling, retain nine skills.

This is an editorial game-balance rule, not a historical ability claim. Selection
is explicit and bound to the current immutable actor, owner and native preimage.
"""
import copy
from pathlib import Path
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_opening_identity_exchange_v1 as identity
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_historical_roster_audit_v1 as roster
from scripts.season_within_club_reserve_repair_v1 import native_facts

KIND='selected-outfield-handling-cap-v1'
SOURCE_ID='selected-outfield-handling-cap-v1'
POLICY='explicit-outfield-selection-cap-20-preserve-other-nine-native-skills-v1'
INPUT_SCHEMA='pm99-selected-outfield-handling-cap-input-v1'


def rows(base, request_path):
    path=Path(request_path)
    if not path.is_absolute():path=registry.ROOT/path
    relative=registry.relative_workspace_path(path)
    cursor=registry.ROOT
    for part in Path(relative).parts:
        cursor=cursor/part
        if cursor.is_symlink():raise ValueError('handling request may not traverse a symlink')
    request=pipeline.read_json_file(path)
    input_sha256=registry.sha256_file(path)
    source_id=SOURCE_ID+'-'+input_sha256[:12]
    if (request.get('schema')!=INPUT_SCHEMA or request.get('policy')!=POLICY
            or request.get('season')!=base.season or request.get('release_id')!=base.release_id
            or request.get('parent_manifest_sha256')!=base.manifest_sha256):
        raise ValueError('handling request schema/policy/immutable parent differs')
    selections=request.get('changes')
    if (not isinstance(selections,list) or not selections
            or len({row.get('carrier_id') for row in selections})!=len(selections)):
        raise ValueError('handling changes require explicit unique selected actors')
    package=pipeline.read_json_file(base.package_path)
    players={row['carrier_id']:row for row in package['players']}
    clubs={row['id']:row for row in package['clubs']}
    jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    owners=ownership.native_owners(eq)
    result=[]
    for selection in selections:
        if (set(selection)!={'carrier_id','name','birth_date','club_carrier_id','before_handling'}
                or type(selection['carrier_id']) is not int):
            raise ValueError('handling selection must pin exact actor, birthday, owner and old value')
        actor=players.get(selection['carrier_id'])
        if actor is None:raise ValueError('handling actor is absent')
        facts=native_facts(jug,actor['carrier_id'])
        if ((actor.get('source_name') or actor['name'])!=selection['name']
                or actor['facts']['birth_date']!=selection['birth_date']
                or facts['birth_date']!=selection['birth_date']
                or roster.normalise(facts['name'])!=roster.normalise(actor['name'])
                or actor['facts']['primary_position'] not in {'D','M','F'}
                or facts['position']!=actor['facts']['primary_position']
                or owners.get(actor['carrier_id'])!={selection['club_carrier_id']}
                or clubs[actor['club_id']]['carrier_id']!=selection['club_carrier_id']):
            raise ValueError('handling source actor is not the exact exclusively owned native outfield player')
        before=actor['ratings']['values'];native=identity.skills(jug,actor['carrier_id'])
        if (native!=before or before['handling']!=selection['before_handling']
                or type(before['handling']) is not int or not 20<before['handling']<=99):
            raise ValueError('handling native/preimage mismatch or no over-cap outfield value')
        ratings=copy.deepcopy(actor['ratings']);ratings['values']['handling']=20
        old_ids=ratings.get('provenance',{}).get('source_ids',[])
        ratings['provenance']={'method':POLICY,'proof_grade':'reviewed-editorial',
                               'source_ids':list(dict.fromkeys([*old_ids,source_id]))}
        assert all(ratings['values'][key]==value for key,value in before.items() if key!='handling')
        result.append({'carrier_id':actor['carrier_id'],'before':copy.deepcopy(actor),'ratings':ratings})
    model=registry.ROOT/'scripts/season_editorial_ratings_v1.py'
    return result,{'policy':POLICY,'source_input':{'path':relative,'sha256':input_sha256},'source_id':source_id,
                   'existing_outfield_model':{'path':registry.relative_workspace_path(model),'sha256':registry.sha256_file(model)},
                   'handling_only':True,'historical_ability_claim':False}
