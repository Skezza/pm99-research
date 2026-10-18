"""Find original biography witnesses across periods without changing games.

Birthdays are immutable biographies, not proof of target-season ownership.
Exact full-name joins only; multiple DOBs remain ambiguous. The existing
recipe is never treated as an external authority for selecting a person.
"""
from collections import defaultdict

from scripts import season_historical_roster_audit_v1 as sources
from scripts import season_number_label_names_v2 as names
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/original-number-labels-v3'


def main():
    output = ROOT / 'remaining-cross-period-biography-review-v1.json'
    if output.exists():
        raise ValueError('completed original biography review must not be overwritten')
    pending = pipeline.read_json_file(ROOT / 'private-remaining-literal-birthdays-v1.json')
    wanted = {names.literal_name(names.undecorated(f['name']))
        for s in pending['seasons'] for f in s['failures']}
    candidates = defaultdict(list)
    bound = []
    for season in registry.supported_seasons():
        captures, bindings = sources.load_sources(season)
        checker = sources.SourceVerifier(season, source_bindings=bindings)
        bound.append(dict(season=season, bindings=bindings))
        for capture in captures:
            matched = [p for p in capture['players'] if names.literal_name(
                names.undecorated(p['name'])) in wanted and isinstance(p.get('birth_date'), str)]
            if not matched:
                continue
            proof = checker.verify(capture)
            if proof['status'] != 'raw-source-reparsed':
                continue
            for person in matched:
                key = names.literal_name(names.undecorated(person['name']))
                # A duplicate exact name inside one source is not resolved by
                # choosing whichever DOB happens to agree with our recipe.
                same = [p for p in capture['players'] if names.literal_name(
                    names.undecorated(p['name'])) == key]
                candidates[key].append(dict(source_season=season, source_player=person,
                    source_club=capture['club_name'], original_proof=proof,
                    exact_name_rows_in_capture=len(same), approves_target_roster=False))
        print(dict(source_season=season, biography_only=True), flush=True)
    rows = []
    for season in pending['seasons']:
        for failure in season['failures']:
            witnesses = candidates[names.literal_name(names.undecorated(failure['name']))]
            dates = sorted({p['source_player']['birth_date'] for p in witnesses})
            unanimous = len(dates) == 1 and all(p['exact_name_rows_in_capture'] == 1 for p in witnesses)
            native = failure['native_birth_components']
            rows.append(dict(season=season['season'], failure=failure, source_dates=dates,
                exact_full_name_unanimous_DOB=unanimous,
                original_biography_agrees_with_recipe=unanimous and dates[0] == failure['recipe_birth_date'],
                original_biography_requires_recipe_correction=unanimous and dates[0] != failure['recipe_birth_date'],
                native_day_month_matches_unanimous_biography=unanimous and
                    (native['month'], native['day']) == tuple(map(int, dates[0].split('-')[1:])),
                original_witnesses=witnesses, native_writes=0, historically_approved=False))
    for source in bound:
        if sources.load_sources(source['season'])[1] != source['bindings']:
            raise ValueError('original biography capture set changed during review')
    for row in rows:
        for witness in row['original_witnesses']:
            proof = witness['original_proof']
            if registry.sha256_file(registry.ROOT / proof['local_path']) != proof['source_sha256']:
                raise ValueError('original biography bytes changed during review')
    pipeline.write_canonical_json(output, dict(schema='pm99-original-cross-period-biography-review-v1',
        source_bindings=bound, rows=rows, native_writes=0,
        exact_unanimous_biographies=sum(r['exact_full_name_unanimous_DOB'] for r in rows),
        source_backed_recipe_date_disagreements=sum(r['original_biography_requires_recipe_correction'] for r in rows),
        scope='Original full-name biographies only; no source-period ownership, person alias or release approval'))
    print(dict(review=registry.relative_workspace_path(output),
        unanimous=sum(r['exact_full_name_unanimous_DOB'] for r in rows),
        wrong_recipe=sum(r['original_biography_requires_recipe_correction'] for r in rows)), flush=True)


if __name__ == '__main__':
    main()
