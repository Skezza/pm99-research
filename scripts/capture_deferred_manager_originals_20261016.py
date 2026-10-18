"""Capture remaining32 coach-history sources once per original numeric club.

Historical tenure dates, not today's coach, determine each claim. Two-manager
overlaps and missing tenures remain explicit; no person/club fallback is used.
Downloads are size bounded, rate limited, URL/SHA receipted and never retried
automatically. An HTTP access-control response pauses further host requests.
"""
from collections import Counter
from datetime import UTC, date, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import time

from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import audit_deferred_manager_tenures_20261016 as old
from scripts.capture_transfermarkt_opening_lineups_v1 import _validate_snapshot_payload
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/remaining-manager-originals-v1/deferred32'
AUDIT = old.ROOT / 'deferred-tenure-source-audit-v2.json'
MAX_BYTES = 2 * 1024 * 1024


def history_url(case):
    path = registry.ROOT / case['decision_path']
    if registry.sha256_file(path) != case['decision_sha256']:
        raise ValueError('original deferred decision changed')
    decision = pipeline.read_json_file(path)
    rows = [d['row'] for d in decision['deferred'] if d['row']['club_id'] == case['club_id']]
    if len(rows) != 1 or rows[0]['evidence']['source_club_id'] != case['source_club_id']:
        raise ValueError('original deferred club identity does not join once')
    schedule = rows[0]['evidence']['schedule_url']
    prefix, separator, suffix = schedule.partition('/spielplan/verein/')
    if not separator or suffix.split('/')[0] != str(case['source_club_id']) or not prefix.startswith('https://www.transfermarkt.co.uk/'):
        raise ValueError('original numeric-club schedule URL differs')
    return prefix + '/mitarbeiterhistorie/verein/' + str(case['source_club_id'])


def original_page(url, club_id):
    path = ROOT / 'raw' / (str(club_id) + '.html')
    receipt = path.with_suffix('.html.source.json')
    if path.exists():
        saved = pipeline.read_json_file(receipt)
        if saved['url'] != url or saved['sha256'] != registry.sha256_file(path):
            raise ValueError('retained new original source URL/SHA changed')
        return path, receipt
    if receipt.exists():
        raise ValueError('partial original download; inspect before retry')
    request = Request(url, headers={'User-Agent': 'PM99HistoricalResearch/1.0', 'Accept-Language': 'en-GB,en;q=0.9'})
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read(MAX_BYTES + 1); final_url = response.url
    finally:
        time.sleep(1)
    if len(raw) > MAX_BYTES or len(raw) < 1000:
        raise ValueError('original history page exceeds bounded size or is implausibly small')
    _validate_snapshot_payload(raw, url)
    urls = {str(a.get('href', '')) for a in BeautifulSoup(raw, 'html.parser').select('link[rel="canonical"]')}
    if len(urls) != 1:
        raise ValueError('original history needs one canonical numeric club URL')
    match = old.URL.fullmatch(next(iter(urls)))
    if match is None or int(match[1]) != club_id:
        raise ValueError('original canonical club ID differs')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    retained(receipt, dict(url=url, final_url=final_url, sha256=registry.sha256_file(path),
        bytes=len(raw), retrieved_utc=datetime.now(UTC).isoformat()))
    return path, receipt


def main():
    output = ROOT / 'capture-summary.json'
    if output.exists():
        raise ValueError('completed remaining32 capture must not repeat')
    audit = pipeline.read_json_file(AUDIT)
    cases = [r for r in audit['rows'] if r['status'] != 'unanimous-reparsed-August1-tenure-candidate'
        or not any(c['original_download_receipt_verified'] for c in r['claims'])]
    if len(cases) != 32:
        raise ValueError('frozen remaining32 source cases changed')
    ROOT.mkdir(parents=True, exist_ok=True)
    captures = {}; rows = []; paused = None
    for case in cases:
        club_id = case['source_club_id']; url = history_url(case)
        if club_id not in captures:
            saved = ROOT / (str(club_id) + '-download.json')
            if saved.exists():
                captures[club_id] = pipeline.read_json_file(saved)
            else:
                try:
                    if paused is not None:
                        raise ValueError('host paused after prior access-control response: ' + paused)
                    path, receipt = original_page(url, club_id)
                    downloaded = dict(status='original-history-captured', source_club_id=club_id, url=url,
                        raw_path=registry.relative_workspace_path(path), raw_sha256=registry.sha256_file(path),
                        receipt_path=registry.relative_workspace_path(receipt), receipt_sha256=registry.sha256_file(receipt))
                except Exception as exc:
                    if isinstance(exc, HTTPError) and exc.code in (401, 403, 405, 429, 503):
                        paused = str(exc.code)
                    downloaded = dict(status='original-history-capture-failed', source_club_id=club_id, url=url,
                        error=type(exc).__name__ + ': ' + str(exc), retry_automatically=False)
                retained(saved, downloaded); captures[club_id] = downloaded
        downloaded = captures[club_id]
        result = dict(season=case['season'], club=case['club'], club_id=case['club_id'],
            source_club_id=club_id, original_case=case, download=downloaded)
        try:
            if downloaded['status'] != 'original-history-captured':
                raise ValueError(downloaded['error'])
            path = registry.ROOT / downloaded['raw_path']; receipt = registry.ROOT / downloaded['receipt_path']
            if registry.sha256_file(path) != downloaded['raw_sha256'] or registry.sha256_file(receipt) != downloaded['receipt_sha256']:
                raise ValueError('captured original source/receipt SHA changed')
            result.update(status='fresh-original-August1-tenure-reparsed',
                claim=old.tenure(path.read_bytes(), club_id, date(int(case['season'][:4]), 8, 1)))
        except (ValueError, old.history.ManagerHistoryError) as exc:
            result.update(status='source-case-remains-unresolved', reason=str(exc))
        rows.append(result)
        print(dict(season=case['season'], club=case['club'], status=result['status'],
            manager=result.get('claim', {}).get('manager'), reason=result.get('reason')), flush=True)
    retained(output, dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        original_audit=dict(path=registry.relative_workspace_path(AUDIT), sha256=registry.sha256_file(AUDIT)),
        original_cases=32, unique_source_clubs=len(captures), rows=rows,
        statuses=dict(Counter(r['status'] for r in rows)), native_writes=0, recipe_writes=0,
        manager_cases_closed=0, access_control_pause=paused,
        scope='New source capture/tenure claims only, not canonical owner admission, native delivery or a global manager clearance.'))


if __name__ == '__main__':
    main()
