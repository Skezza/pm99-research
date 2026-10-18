"""Require every dated coach witness to be in the actual game start year.

The v1 source helper and private evidence remain immutable. NTF's partial
calendar-country set is not a general manager-date policy. Also check the
whole proposed manager graph, not merely duplicates inside the update list.
"""
import copy
import hashlib
from collections import defaultdict
from pathlib import Path
from scripts import season_cached_manager_repairs_20261016 as prior
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry

POLICY='all-coach-fixture-years-match-actual-game-start-year-and-no-new-canonical-owner-collision-v2'


def filtered(package,raw_plan):
    plan=copy.deepcopy(raw_plan);year=plan['season'][:4]
    selected=[];deferred=[]
    for row in plan['updates']:
        if row['first_fixture_date'][:4]!=year:
            deferred.append(dict(row=row,reason='dated witness is outside actual game start year; not proof that coach value itself is wrong'))
        else:selected.append(row)
    managers={m['id']:m for m in package['managers']}
    while selected:
        updates={row['manager_id']:row for row in selected}
        by_name=defaultdict(list);by_person=defaultdict(list)
        for id,manager in managers.items():
            if id in updates:
                name=updates[id]['after']
                person='manager-historical-'+hashlib.sha256(name.encode()).hexdigest()[:24]
            else:
                name=manager['name'];person=manager.get('person_id')
            by_name[prior.opening._normalise(name)].append(id)
            if person is not None:by_person[person].append(id)
        blocked=set()
        for group in (*by_name.values(),*by_person.values()):
            if len(group)>1:blocked.update(set(group)&set(updates))
        if not blocked:break
        deferred.extend(dict(row=row,reason='proposed coach identity already assigned elsewhere; dated owner/identity reconciliation required')
            for row in selected if row['manager_id'] in blocked)
        selected=[row for row in selected if row['manager_id'] not in blocked]
    if not deferred:
        return raw_plan,[]  # preserve exact existing safe private build/recipe
    plan['updates']=selected
    plan['unresolved'].extend(dict(club_id=d['row']['club_id'],club=d['row']['club'],
        before=d['row']['before'],proposed=d['row']['after'],reason=d['reason'],
        rejected_witness_date=d['row']['first_fixture_date']) for d in deferred)
    plan['summary']=dict(plan['summary'],corrections=len(selected),
        mismatches_requiring_further_review=len(plan['unresolved']))
    plan['year_and_global_owner_review_policy']=POLICY
    plan['implementation_inputs'].append(dict(path=registry.relative_workspace_path(Path(__file__)),
        sha256=registry.sha256_file(Path(__file__))))
    return plan,deferred


def decision(base):
    raw=prior.prepare(base)
    selected,deferred=filtered(pipeline.read_json_file(base.package_path),raw)
    return dict(season=base.season,release_id=base.release_id,policy=POLICY,
        original_proposals=len(raw['updates']),accepted_proposals=len(selected['updates']),
        original_plan_sha256=pipeline.canonical_json_sha256(raw),
        selected_plan_sha256=pipeline.canonical_json_sha256(selected),
        reuse_exact_existing_private_plan=not deferred,deferred=deferred,selected_plan=selected)


def prepare(base):return decision(base)['selected_plan']
