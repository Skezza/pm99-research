"""Replay only explicit, complete mode-1 whole-club keeper exchanges.

The existing whole-club source artifact is the authority. No reserve-swap plan,
implicit name fit or recipe-only inferred starting XI can activate this lane.
"""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'upstream/pm99-skezmod-db-editor'))

from app.player_initial_order import OrderReplacement, patch_owned_mode1_keeper_exchange, read_initial_order
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry


def validate_scope(package, club, source):
    from scripts.prepare_duplicate_club_disposition_v1 import keeper_exchange, opening_edge
    if (source.get('schema_version') != 'pm99-whole-club-collision-diagnostic-only-v1'
            or source.get('collision_inspection_only') is not True
            or source.get('allow_keeper_order_exchange') is not True
            or source.get('native_opening_slot_policy') !=
            'complete-sourced-XI-with-bounded-owned-mode1-reciprocal-keeper-order-exchange-v1'):
        raise ValueError('unsupported whole-club keeper exchange policy')
    season=f"{package['season']['start_year']}-{str(package['season']['end_year'])[-2:]}"
    if (source['season'] != season or source['before_club']['id'] != club['id']
            or source['before_club']['carrier_id'] != club['carrier_id'] or source['new_club'] != club['name']):
        raise ValueError('whole-club keeper exchange targets another season or club')
    allocation=source['allocation']; players={p['id']:p for p in package['players']}
    ids=[r['player_id'] for r in allocation]
    if (not ids or len(ids)!=len(set(ids)) or set(ids)!=set(club['roster_player_ids'])
            or len(ids)!=len(source['desired_people'])
            or len({r['carrier_id'] for r in allocation})!=len(ids)):
        raise ValueError('whole-club keeper exchange does not cover every fixed roster slot')
    desired={p['source_person']['source_player_id']:p for p in source['desired_people']}
    if len(desired)!=len(ids) or {r['replacement']['source_person']['source_player_id'] for r in allocation}!=set(desired):
        raise ValueError('whole-club keeper exchange repeats or loses a sourced player')
    rows=keeper_exchange(allocation)
    if rows!=source.get('startup_order_exchange'):
        raise ValueError('whole-club keeper exchange differs from its sourced allocation')
    orders={r['carrier_id']:r['after'] for r in rows}
    for r in allocation:
        p=players.get(r['player_id']);wanted=r['replacement']['source_player']
        if (p is None or p['club_id']!=club['id'] or p['carrier_id']!=r['carrier_id']
                or p['name']!=r['display']['display_name'] or p.get('source_name')!=wanted['name']
                or p['facts']['birth_date']!=wanted['birth_date']
                or p['facts']['primary_position']!=wanted['position']
                or r['replacement']!=desired[r['replacement']['source_person']['source_player_id']]):
            raise ValueError('whole-club keeper exchange recipe no longer matches the complete sourced roster')
        if (r.get('native_startup_order_after')!=orders.get(r['carrier_id'],r['native_startup_order_before'])
                or not opening_edge(r['native_startup_order_after'],r['replacement'])):
            raise ValueError('whole-club keeper exchange moves a reserve or misplaces its goalkeeper')
    return rows


def bound_native_replacements(jug,rows):
    """The writer capitalises surnames; bind exact current native spelling."""
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(jug).entries};result=[]
    for r in rows:
        e=entries[r['carrier_id']];name=read_initial_order(e.decode_payload(jug)).name
        if name.casefold()!=r['expected_name'].casefold():
            raise ValueError('keeper exchange native name differs from its exact sourced display form: '
                f"{r['carrier_id']} expected {r['expected_name']!r}, found {name!r}")
        result.append(OrderReplacement(r['carrier_id'],name,r['before'],r['after']))
    return result


def replay(jug, eq, package, package_path):
    artifacts={a['id']:a for a in package['artifacts']}; cache={}; changes=[]
    for club in package['clubs']:
        identity=club.get('proof',{}).get('artifact_id','')
        if not identity.startswith('duplicate-ownership-plan-'):
            continue
        artifact=artifacts.get(identity)
        if artifact is None:raise ValueError('whole-club source artifact is absent')
        if identity not in cache:
            rel=Path(artifact.get('relative_path',''))
            if not rel.parts or rel.is_absolute() or '..' in rel.parts:
                raise ValueError('unsafe whole-club source artifact path')
            path=package_path.parent/rel
            if registry.sha256_file(path)!=artifact['sha256']:
                raise ValueError('whole-club source artifact changed')
            cache[identity]=json.loads(path.read_text())
        source=cache[identity].get('whole_club_original_source')
        if source is None or not source.get('allow_keeper_order_exchange'):
            continue
        rows=validate_scope(package,club,source)
        if rows:
            jug=patch_owned_mode1_keeper_exchange(jug,eq,
                bound_native_replacements(jug,rows))
            changes.append({'club_carrier_id':club['carrier_id'],'rows':rows})
    return jug,changes
