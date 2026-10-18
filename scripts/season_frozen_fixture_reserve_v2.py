"""Versioned fixture dispositions with original cached public person identities.

Numeric original identities, same-day positive retained XI, positive replacement
bench and period birthdays are mandatory. A published shirt-heading decoration
is retained in the recipe; it is not part of the person's identity key. No fuzzy
name matching, arbitrary reserve, starter replacement or ownership inference
from a current biography is permitted.
"""
import copy
from datetime import date
from pathlib import Path
import re
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_historical_transfer_review_v1 as people
from scripts import season_historical_opening_review_v1 as opening
from scripts import season_opening_order_repair_v1 as ownership
from scripts import season_within_club_reserve_repair_v1 as native
from scripts import season_duplicate_source_context_v1 as context
from scripts.backfill_exact_opening_club_aliases_v1 import unique_capture
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_published_person_identity_v1 as published_people

SCHEMA='pm99-original-fixture-frozen-pair-reserve-dispositions-v2'
INPUT_SCHEMA='pm99-explicit-frozen-pair-original-fixture-reserve-input-v2'


def heading_name(value):
    # Explicit source heading only: no initials expansion or surname guessing.
    return re.sub(r'^#(?:[1-9]|[1-9][0-9])\s+','',value)


def identity(player):
    return roster.normalise(heading_name(player.get('source_name') or player['name'])),player['facts'].get('birth_date')


def guard_pair(before,keep,first,second,owners,club,retained,expected_name,birthday):
    if before['club_id']==keep['club_id'] or before['carrier_id']==keep['carrier_id']:
        raise ValueError('frozen pair requires distinct current owners and carriers')
    wanted=(roster.normalise(expected_name),birthday)
    if identity(before)!=wanted or identity(keep)!=wanted or any(n['birth_date']!=birthday for n in (first,second)):
        raise ValueError('frozen pair full original identity or literal native birthday differs')
    for actor,fact,owner in ((before,first,club),(keep,second,retained)):
        if (actor['club_id']!=owner['id'] or owners.get(actor['carrier_id'])!={owner['carrier_id']}
                or owner['roster_player_ids'].count(actor['id'])!=1
                or roster.normalise(fact['name'])!=roster.normalise(actor['name'])):
            raise ValueError('frozen pair native name/owner differs from its exact declared actor')
    if first['startup_order']<=11 or first['position']=='G':
        raise ValueError('original-fixture reserve route cannot replace a native starter or keeper')


def binding(path):
    return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))


def retired_member_proof(base,decision,case,actors,jug):
    """Account for an original third copy already positively replaced.

    Disappearance alone is insufficient. Require a separately source-complete
    native club transaction, its actual old frozen actor and unchanged sourced
    replacement now. This never counts a partly repaired group as closed.
    """
    from app.fdi_indexed import IndexedFDIFile
    from scripts import season_paired_whole_club_reconstruction_v1 as whole
    from scripts import prepare_paired_whole_club_dispositions_v1 as paired
    result=[];seen=set()
    for witness in decision.get('previously_retired_frozen_members',[]):
        carrier=witness['carrier_id']
        if carrier in seen or carrier in (decision['displaced_carrier'],decision['retained_carrier']):
            raise ValueError('retired-member witness repeats or hides a current pair member')
        seen.add(carrier)
        original=[p for p in case['players'] if p['carrier_id']==carrier]
        if len(original)!=1:raise ValueError('retired-member witness is not an original frozen case member')
        prior=registry.load_registered_release(base.season,witness['release_id'])
        bound=whole.bound_receipt(prior)
        if bound is None:raise ValueError('retired member needs its independently sourced complete-club correction')
        receipt_path,receipt=bound
        pair_path=registry.ROOT/receipt['source_pair']['path']
        if registry.sha256_file(pair_path)!=receipt['source_pair']['sha256']:
            raise ValueError('retired-member complete source group changed')
        pair=pipeline.read_json_file(pair_path);proposals=[]
        for source in pair['proposals']:
            path=registry.ROOT/source['path']
            if registry.sha256_file(path)!=source['sha256']:raise ValueError('retired original source changed')
            proposals.append(pipeline.read_json_file(path))
        if paired.source_guard(pair,proposals)!=pair['source_guard']:raise ValueError('retired complete source guard differs')
        allocation=[r for p in proposals for r in p['allocation'] if r['carrier_id']==carrier]
        if len(allocation)!=1:raise ValueError('retired native slot not present once in full source allocation')
        before=allocation[0]['before_recipe'];frozen=original[0]
        if (before['club_id'],before.get('source_name') or before['name'],before['facts']['birth_date'])!=(
                frozen['club_id'],frozen['source_name'],frozen['birth_date']):
            raise ValueError('prior retired preimage is not the exact frozen actor')
        old_package=pipeline.read_json_file(prior.package_path)
        current=actors[carrier];proved=next(p for p in old_package['players'] if p['carrier_id']==carrier)
        if (current!=proved or current['source_name']!=allocation[0]['replacement']['source_player']['name']
                or current['facts']['birth_date']!=allocation[0]['replacement']['source_player']['birth_date']
                or identity(current)==identity(before)):
            raise ValueError('retired member lacks the unchanged positive sourced replacement')
        prior_jug=(prior.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        old_entry=next(e for e in IndexedFDIFile.from_bytes(prior_jug).entries if e.record_id==carrier)
        current_entry=next(e for e in IndexedFDIFile.from_bytes(jug).entries if e.record_id==carrier)
        if old_entry.decode_payload(prior_jug)!=current_entry.decode_payload(jug):
            raise ValueError('retired member native replacement changed')
        result.append(dict(carrier_id=carrier,release_id=prior.release_id,manifest_sha256=prior.manifest_sha256,
            candidate_receipt=binding(receipt_path),source_pair=binding(pair_path),
            exact_frozen_preimage=frozen,positive_source_replacement=allocation[0]['replacement'],
            current_replacement_recipe_and_native_identical=True))
    return result


def load_identity_index(database=None,pin=None):
    """Replay original responses, not saved aliases alone or current clubs."""
    if database is None:
        database=registry.ROOT/'.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb'
    if pin is None:
        pin=registry.ROOT/'.local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json'
    index,events,snapshot=context.load_snapshot(database,pin)
    supplement=registry.ROOT/'.local/duplicate-ownership-v3/published-person-identities-r2.json'
    bindings=dict(published_person_supplement=public.binding(supplement,published_people.POLICY))
    index,_,report=public.merge_bound(index,events,bindings)
    return index,snapshot,bindings,report


def prepare(base,review_path):
    review=pipeline.read_json_file(review_path)
    if review.get('schema')!=INPUT_SCHEMA or review.get('season')!=base.season or not review.get('cases'):
        raise ValueError('explicit season and frozen-case reserve input required')
    root=registry.ROOT/'.local/consolidated-audit-20261009'
    frozen_path=root/'cross-club-identities-enriched.json';frozen=pipeline.read_json_file(frozen_path)
    cases=next(r['candidates'] for r in frozen['seasons'] if r['season']==base.season)
    capture_path=registry.ROOT/f'.local/transfermarkt-opening-plans-current-v1/{base.season}/opening-lineups.json'
    capture=pipeline.read_json_file(capture_path)
    database=registry.ROOT/'.local/external-sources/transfermarkt-datasets/transfermarkt-datasets.duckdb'
    pin=registry.ROOT/'.local/season-pipeline-v2/world-2015-transfermarkt-opening-fixtures-20260831.json'
    index,snapshot,supplement_bindings,supplement_merge=load_identity_index(database,pin)
    main=next(p for label,p,_ in layers.package_layers(base) if label=='main')
    represented=[p for _,pkg,_ in layers.package_layers(base) for p in pkg['players']]
    actors={p['carrier_id']:p for p in main['players']};clubs={c['id']:c for c in main['clubs']}
    jug_path=base.game_path/'DBDAT/JUG98030.FDI';eq_path=base.game_path/'DBDAT/EQ98030.FDI'
    jug=jug_path.read_bytes();eq=eq_path.read_bytes();owners=ownership.native_owners(eq)
    updates=[];proofs=[];selected=set();new_names=set()
    for decision in review['cases']:
        source_id=decision['source_person_id'];displaced=decision['displaced_carrier'];retained=decision['retained_carrier']
        if type(source_id) is not int or displaced in selected:raise ValueError('invalid or repeated frozen source/target')
        selected.add(displaced)
        matches=[c for c in cases if c['identity']==['published-person',source_id]]
        retired={r['carrier_id'] for r in decision.get('previously_retired_frozen_members',[])}
        if len(matches)!=1 or {p['carrier_id'] for p in matches[0]['players']}!=({displaced,retained}|retired):
            raise ValueError('every exact frozen published-person owner must be accounted for')
        case=matches[0];before,keep=actors[displaced],actors[retained]
        club,retained_club=clubs[before['club_id']],clubs[keep['club_id']]
        birthday=keep['facts']['birth_date'];full_name=heading_name(keep.get('source_name') or keep['name'])
        published=people.unique_person(dict(name=full_name,facts=dict(birth_date=birthday)),index)
        if published is None or published['source_player_id']!=source_id:
            raise ValueError('original pinned full-name/DOB person does not identify the frozen numeric actor')
        first,second=native.native_facts(jug,displaced),native.native_facts(jug,retained)
        guard_pair(before,keep,first,second,owners,club,retained_club,full_name,birthday)
        retired_proofs=retired_member_proof(base,decision,case,actors,jug)
        copies=[p['carrier_id'] for p in represented if identity(p)==identity(keep)]
        if set(copies)!={displaced,retained}:raise ValueError('additional current full-identity copies require a coupled correction')
        source_rows=[]
        for target in (club,retained_club):
            captured=unique_capture(target,capture['clubs'])
            if captured is None:raise ValueError('one original numeric club first fixture required')
            source_rows.append(opening.verify_opening(captured,capture,capture_path.parent/'cache'))
        target_match,owner_match=source_rows
        if target_match['date']!=owner_match['date'] or not target_match['date'].startswith(base.season[:4]+'-08-'):
            raise ValueError('same-day original August ownership evidence required; no transfer-day inference')
        if (str(source_id) not in owner_match['starting_xi']
                or any(str(source_id) in target_match[f] for f in ('starting_xi','substitutes'))):
            raise ValueError('retained original XI ownership conflicts with the displaced club report')
        replacement_id=decision['replacement_source_person_id']
        replacement_name=decision['replacement_name']
        if type(replacement_id) is not int or target_match['substitutes'].get(str(replacement_id))!=replacement_name:
            raise ValueError('replacement lacks exact original numeric bench/full published name')
        key=roster.normalise(replacement_name)
        if key in new_names or any(identity(p)[0]==key for p in represented):
            raise ValueError('opening reserve already represented or repeated in this batch')
        new_names.add(key)
        annual,raw=native.annual_capture(base.season,club)
        members=[p for p in annual['players'] if roster.normalise(p['name'])==key]
        if len(members)!=1 or members[0].get('position') not in ('D','M','F') or not members[0].get('birth_date'):
            raise ValueError('replacement needs one period full-name/DOB/outfield-role biography')
        source=copy.deepcopy(members[0]);day=date.fromisoformat(target_match['date']);born=date.fromisoformat(source['birth_date'])
        age=day.year-born.year-((day.month,day.day)<(born.month,born.day))
        if not 12<=age<=50:raise ValueError('period reserve age is implausible')
        person=dict(source_player_id=replacement_id,source_provider='original-transfermarkt-fixture-and-period-annual',
            name=replacement_name,birth_date=source['birth_date'],
            source_profile_url=next(p['source_url'] for r in capture['clubs'] if r['lineup_source_url']==target_match['source_url']
                and r['source_selector']['transfermarkt_club_id']==target_match['source_club_id'] for p in r['substitutes']
                if str(p['source_player_id'])==str(replacement_id)))
        # Person identity/birthday is not inferred from a bare surname: exact
        # full-name annual + full published bench heading identify the reserve.
        owner_proof=dict(policy='original-same-day-numeric-retained-XI-and-replacement-bench-v1',
            retained_first_fixture=owner_match,replacement_first_fixture=target_match)
        updates.append(dict(layer='main',player_id=before['id'],carrier_id=displaced,club_id=club['id'],
            before=copy.deepcopy(before),retained_owner_player_id=keep['id'],retained_carrier_id=retained,
            retained_owner_club_id=retained_club['id'],duplicate_source_person=published,
            duplicate_owner_evidence=owner_proof,owner_evidence=owner_proof,
            replacement_opening_evidence=dict(date=target_match['date'],policy=owner_proof['policy'],
                actual_first_fixture_claimed=True,published_bench=True),
            replacement=dict(source_player=source,source_person=person,raw_evidence=raw),
            duplicate_native_before=[first,second]))
        proofs.append(dict(case_id=pipeline.canonical_json_sha256(dict(season=base.season,case=case)),
            frozen_case=case,source_person_id=source_id,retained_carrier=retained,displaced_carrier=displaced,
            previously_retired_frozen_members=retired_proofs,
            retained_published_person=published,original_openings=source_rows,annual_capture=annual,annual_proof=raw))
    return dict(schema_version=SCHEMA,season=base.season,release_id=base.release_id,
        package_sha256=registry.sha256_file(base.package_path),jug_sha256=registry.sha256_file(jug_path),
        eq_sha256=registry.sha256_file(eq_path),updates=updates,unresolved=[],starting_XI_change_authorised=False,
        bindings=dict(snapshot=snapshot,**supplement_bindings,supplement_merge=supplement_merge,
            review=binding(review_path),frozen_cases=binding(frozen_path),
            original_openings=binding(capture_path),positive_pairs=proofs,
            implementation_inputs=[binding(Path(__file__))]),
        source_title='Frozen exact cross-club numeric identities; original same-day retained starting XI and positive replacement bench',
        proof_covers=['original-positive-owner-and-published-bench','exact-native-reserve-only',
            'published-shirt-heading-preserved-not-fuzzy-person-name','all-unrelated-native-data-preserved'])


def verify_plan(base,plan):
    if plan.get('schema_version')!=SCHEMA or prepare(base,registry.ROOT/plan['bindings']['review']['path'])!=plan:
        raise ValueError('original frozen-pair fixture reserve proof did not independently reproduce')


def reconstruction(previous,release_id):
    path=getattr(previous,'locator',{}).get('ownership_plan_path')
    if not path:return None
    path=registry.ROOT/path;plan=pipeline.read_json_file(path)
    if plan.get('schema_version')!=SCHEMA:return None
    from scripts import season_duplicate_ownership_delta_v1 as delta,season_duplicate_layered_packages_v1 as layered
    from scripts import publish_historical_role_delta_v1 as publisher
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    base=registry.load_registered_release(plan['season'],plan['release_id']);verify_plan(base,plan)
    if path.resolve()!=(previous.package_path.parent/delta.plan_filename(plan)).resolve():
        raise ValueError('SOURCE input is not the exact release-local frozen-pair plan')
    expected,english,_,_=layered.prepare(base,plan,(base.game_path/'DBDAT/JUG98030.FDI').read_bytes())
    if english is not None or expected!=pipeline.read_json_file(previous.package_path):
        raise ValueError('edited frozen-pair recipe cannot discard changes during SOURCE replay')
    descriptor=path.with_name('frozen-fixture-source-replay-inert.json')
    retained(descriptor,dict(season=base.season,release_id=base.release_id,package_sha256=plan['package_sha256'],
        jug_sha256=plan['jug_sha256'],updates=[],unresolved=[]))
    publisher.publish(base.season,descriptor,release_id=release_id,source_release_id=base.release_id,ownership_plan_path=path)
    rebuilt=registry.load_registered_release(base.season,release_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path,pipeline.read_json_file(previous.inventory_path))
    if rebuilt.package_path.read_bytes()!=previous.package_path.read_bytes():raise ValueError('whole SOURCE recipe differs')
    return dict(season=base.season,release_id=release_id,complete_game_inventory_identical=True,complete_recipe_identical=True)
