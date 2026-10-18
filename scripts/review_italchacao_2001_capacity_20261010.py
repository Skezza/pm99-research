"""Reparse the preserved August squad and correct an unsupported capacity gate.

This review grants no permission to substitute a cup XI for the league opener.
The previous immutable review is retained; neither a keeper nor a DOB is invented.
"""
from scripts import italchacao_2001_original_august_v1 as opening
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_published_person_identity_v1 as people
from scripts.capture_tachira_2014_original_people_v1 import source_rows

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1'


def prepare():
    keys = ['italchacao-2001-original-official-august-match',
        'italchacao-2001-original-official-opening-friendly',
        'italchacao-2001-original-official-calendar',
        'italchacao-2001-original-first-league-result']
    sources = [source_rows(key) for key in keys]
    parsed = opening.parse(*(row[1] for row in sources))
    person_path = ROOT / 'italchacao-2001-original-person-candidates-v1.json'
    document = pipeline.read_json_file(person_path)
    people.merge({}, document)  # Independently reparse original API bytes/receipts.
    joined = opening.join_people(parsed, document)
    if len(joined) != 16 or len({p['source_player_id'] for p in joined}) != 16:
        raise ValueError('fixed16 opening-person union changed')
    previous = ROOT / 'italchacao-2001-original-august-source-review-v1.json'
    return dict(schema_version='pm99-original-august-capacity-review-v2',
        previous_review=dict(path=registry.relative_workspace_path(previous), sha256=registry.sha256_file(previous)),
        parser=dict(path='scripts/italchacao_2001_original_august_v1.py',
            sha256=registry.sha256_file(registry.ROOT / 'scripts/italchacao_2001_original_august_v1.py')),
        original_bindings=[row[2] for row in sources] + [dict(
            path=registry.relative_workspace_path(person_path), sha256=registry.sha256_file(person_path))],
        parsed_original=parsed, matched_original_people=joined,
        sourced_distinct_people=16, required_native_slots=16,
        capacity_issue=None,
        correction='A second goalkeeper is not required by the fixed16 carrier capacity. No extra goalkeeper manufactured.',
        remaining_publication_gaps=['First league starting XI unavailable; August cup/friendly alternative requires explicit source-policy approval.',
            'Bidoglio conflicting February5/February15 birthday remains unresolved.',
            'Native exclusive ownership, dated manager/kit, complete source replay and actual runner validation not yet delivered.'],
        native_writes=0, closed_duplicate_cases=0, publication_authorised=False)


if __name__ == '__main__':
    output = ROOT / 'italchacao-2001-original-capacity-review-v2.json'
    result = prepare()
    if output.exists():
        if pipeline.read_json_file(output) != result:
            raise ValueError('immutable corrected capacity review differs')
    else:
        pipeline.write_canonical_json(output, result)
    print(dict(source_people=result['sourced_distinct_people'], native_slots=result['required_native_slots'],
        capacity_issue=result['capacity_issue'], publication_authorised=False, duplicates_closed=0), flush=True)
