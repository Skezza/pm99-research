"""Bounded single original history capture for the remaining coach identities.

Uses the already published club289 binding, not a guessed search ID. No
native/recipe writes, retries, access-control bypass or unaffected regeneration.
"""
from datetime import UTC, date, datetime
from urllib.request import Request, urlopen

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_cached_manager_repairs_20261016 as original
from scripts import audit_deferred_manager_tenures_20261016 as histories
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/remaining-manager-originals-v1/sunderland'
MAX_BYTES = 2 * 1024 * 1024


def main():
    report_path = original.REVIEWS / '2020-21/opening-review.json'
    report = pipeline.read_json_file(report_path)
    rows = [r for r in report['clubs'] if r['club'] == 'Sunderland'
        and r['status'] == 'original-first-fixture-reparsed']
    if len(rows) != 1 or rows[0]['evidence']['source_club_id'] != 289:
        raise ValueError('original exact Sunderland club identity missing or changed')
    row = rows[0]
    schedule = row['evidence']['schedule_url']
    suffix = '/spielplan/verein/289/saison_id/2020'
    if not schedule.endswith(suffix):
        raise ValueError('unexpected original source schedule URL')
    url = schedule[:-len(suffix)] + '/mitarbeiterhistorie/verein/289'
    ROOT.mkdir(parents=True, exist_ok=True)
    outcome = ROOT / 'capture-result.json'
    if outcome.exists():
        print(pipeline.read_json_file(outcome), flush=True)
        return
    path = ROOT / '289.html'; receipt_path = ROOT / '289.html.source.json'
    if path.exists() or receipt_path.exists():
        raise ValueError('partial original source capture; inspect before retry')
    binding = dict(original_report=registry.relative_workspace_path(report_path),
        original_report_sha256=registry.sha256_file(report_path), original_club_row=row)
    try:
        request = Request(url, headers={'User-Agent': 'PM99HistoricalResearch/1.0', 'Accept-Language': 'en-GB,en;q=0.9'})
        with urlopen(request, timeout=30) as response:
            raw = response.read(MAX_BYTES + 1)
            final_url = response.url
        if len(raw) > MAX_BYTES or len(raw) < 1000:
            raise ValueError('history source size outside bounded original-page limits')
        claims = [histories.tenure(raw, 289, date(year, 8, 1)) for year in (2020,)]
        # Save only an actual historical source, never an HTTP challenge page.
        # The canonical/numeric club and dated coach parser above must succeed.
        path.write_bytes(raw)
        retained(receipt_path, dict(url=url, final_url=final_url, sha256=registry.sha256_file(path),
            retrieved_utc=datetime.now(UTC).isoformat(), bytes=len(raw), **binding))
        result = dict(status='original-numeric-club-history-captured-and-reparsed', claims=claims,
            source=dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path), url=url),
            receipt=dict(path=registry.relative_workspace_path(receipt_path), sha256=registry.sha256_file(receipt_path)),
            native_writes=0, recipe_writes=0, manager_cases_closed=0)
    except Exception as exc:
        result = dict(status='original-source-capture-failed-no-fallback-claim', url=url,
            error=type(exc).__name__ + ': ' + str(exc), native_writes=0, recipe_writes=0,
            manager_cases_closed=0, retry_automatically=False, **binding)
    retained(outcome, result)
    print(result, flush=True)


if __name__ == '__main__':
    main()
