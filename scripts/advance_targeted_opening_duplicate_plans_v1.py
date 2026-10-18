#!/usr/bin/env python3
"""Reconsider only seasons receiving stronger first-fixture source evidence.

Preserve completed games and fixes. Unchanged seasons get current-release,
zero-update plans; this is never approval of their unresolved roster queues.
"""
import argparse
import collections
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import season_duplicate_source_context_v1 as context
from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_public_identity_and_history_inputs_v1 as public
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase


def advanced_seasons(review, prior_root=None):
    """Do not redo decisions for identical replays of incomplete biographies."""
    extension=review['targeted_original_extension'];previous=extension['previous_review']
    path=ROOT/previous['path']
    if registry.sha256_file(path)!=previous['sha256']:
        raise ValueError('targeted previous review changed')
    old=json.loads(path.read_text())
    old_rows={(s['season'],r['club']):r for s in old['seasons'] for r in s['clubs']}
    new_rows={(s['season'],r['club']):r for s in review['seasons'] for r in s['clubs']}
    selected={r['season'] for r in extension['added']
        if new_rows.get((r['season'],r['club']))!=old_rows.get((r['season'],r['club']))}
    if prior_root is None:return selected
    # Unchanged seasons may retain an older review binding than the season
    # used to extend this batch. Compare each plan's own actual prior evidence,
    # not just the extension's global parent (which can repeat another review).
    result=set();cache={}
    for season in selected:
        plan=json.loads((prior_root/season/'ownership-plan.json').read_text())
        bound=plan['bindings']['soccerbase_opening_sources']['review']
        key=bound['path'],bound['sha256']
        if key not in cache:
            p=ROOT/bound['path']
            if registry.sha256_file(p)!=bound['sha256']:raise ValueError('prior season review changed')
            cache[key]=json.loads(p.read_text())
        previous_sections=[s for s in cache[key]['seasons'] if s['season']==season]
        current_sections=[s for s in review['seasons'] if s['season']==season]
        if len(previous_sections)!=1 or len(current_sections)!=1:
            raise ValueError('forward source comparison lacks one exact season')
        before={r['club']:r for r in previous_sections[0]['clubs']}
        after={r['club']:r for r in current_sections[0]['clubs']}
        if before!=after:result.add(season)
    return result


def advance(prior_root, review_path, output, *, seasons=None):
    review = json.loads(review_path.read_text())
    selected = advanced_seasons(review,prior_root)
    if seasons is not None: selected &= set(seasons)
    original = json.loads((prior_root/'2000-01/ownership-plan.json').read_text())
    pin = original['bindings']['snapshot']
    people=events=None
    if any(not (output/s/'ownership-plan.json').exists() for s in selected):
        people, events, actual_pin = context.load_snapshot(ROOT/pin['path'], ROOT/pin['pinned_receipt_path'])
        if pin != actual_pin: raise ValueError('targeted plan snapshot pin changed')
    current_queue = json.loads((prior_root.parent/'closeout-r39-final/unresolved.json').read_text())
    by_season = collections.defaultdict(list)
    for row in current_queue:
        copied = dict(row); copied.pop('season', None); by_season[row['season']].append(copied)
    for season in registry.supported_seasons():
        target = output/season/'ownership-plan.json'
        if target.exists():
            existing = json.loads(target.read_text()); release = registry.load_preferred_release(season)
            if (existing['release_id'], existing['package_sha256'], existing['jug_sha256']) != (
                    release.release_id, registry.sha256_file(release.package_path),
                    registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI')):
                raise ValueError('completed targeted plan baseline changed')
            print(json.dumps({'season': season, 'reused_completed_plan': True}), flush=True); continue
        old_path = prior_root/season/'ownership-plan.json'; old = json.loads(old_path.read_text())
        if season in selected:
            bindings = old['bindings']; extra = bindings.get('supplemental_opening')
            source_root = (ROOT/bindings['opening_path']).parents[2]
            result = planner.plan(season, people, events, pin, source_root, output,
                supplemental_opening_path=ROOT/extra['path'] if extra else None,
                with_opening_person_supplement=True,
                published_person_path=ROOT/bindings['published_person_supplement']['path'],
                published_transfer_path=ROOT/bindings['published_transfer_supplement']['path'],
                allow_sourced_outfield_reserve_role_changes=True, allow_published_display_aliases=True,
                allow_dated_reserve_owners=True, soccerbase_review_path=review_path,
                soccerbase_club_entities_path=ROOT/bindings['soccerbase_opening_sources']['club_entities']['path'],
                allow_dated_outfield_reserve_role_changes=True)
            print(json.dumps(result), flush=True)
        else:
            release = registry.load_preferred_release(season)
            saved = copy.deepcopy(old); saved.update(release_id=release.release_id,
                package_sha256=registry.sha256_file(release.package_path),
                jug_sha256=registry.sha256_file(release.game_path/'DBDAT/JUG98030.FDI'), updates=[],
                unresolved=by_season[season])
            saved['summary'].update(replacement_slots=0, unresolved_entries=len(saved['unresolved']),
                unresolved_reasons=dict(collections.Counter(r['reason'] for r in saved['unresolved'])))
            saved.pop('allow_same_carrier_name_capacity', None)
            saved['bindings'].pop('same_carrier_name_capacity', None)
            saved['continued_targeted_source_queue'] = {'prior_plan_path': str(old_path.relative_to(ROOT)),
                'prior_plan_sha256': registry.sha256_file(old_path), 'source_evidence_not_advanced': True,
                'native_writes': 0, 'completed_game_preserved': True}
            target.parent.mkdir(parents=True,exist_ok=True)
            pipeline.write_canonical_json(target, saved)
            print(json.dumps({'season': season, 'unchanged': True}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prior-root', type=Path, required=True); p.add_argument('--review', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--seasons', nargs='+')
    a = p.parse_args(); advance(a.prior_root.resolve(), a.review.resolve(), a.output.resolve(), seasons=a.seasons)
