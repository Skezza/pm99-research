"""Three bounded original timelines for stale same-name native coach owners.

These exact first-team provider identities were independently checked by ROOT:
Basel26/Switzerland, SportingCristal1450/Peru, Aalesund5619/Norway. Country-
scoped native club aliases and every historical tenure still need admission.
"""
from datetime import UTC, datetime
from urllib.request import Request, urlopen
import time
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import audit_deferred_manager_tenures_20261016 as history
from scripts.capture_transfermarkt_opening_lineups_v1 import _validate_snapshot_payload
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/remaining-manager-originals-v1/coupled-clubs'
TARGETS = (
    ('Basel', 'switzerland', 26, 'fc-basel-1893'),
    ('Sporting Cristal Lima', 'peru', 1450, 'club-sporting-cristal'),
    ('Aalesund', 'norway', 5619, 'aalesunds-fk'),
)


def main(*, root=ROOT, targets=TARGETS):
    ROOT, TARGETS = root, targets
    if (ROOT / 'capture-summary.json').exists():
        raise ValueError('completed coupled-club captures must not repeat')
    ROOT.mkdir(parents=True, exist_ok=True); rows = []
    for name, country, club_id, slug in TARGETS:
        url = f'https://www.transfermarkt.co.uk/{slug}/mitarbeiterhistorie/verein/{club_id}'
        path = ROOT / (str(club_id) + '.html'); receipt = ROOT / (str(club_id) + '.json')
        if receipt.exists():
            row = pipeline.read_json_file(receipt)
            if row['url'] != url or (row['status'] == 'original-club-history-captured' and registry.sha256_file(path) != row['sha256']):
                raise ValueError('retained coupled-club source changed')
        else:
            if path.exists():
                raise ValueError('partial coupled-club download; inspect before retry')
            try:
                request = Request(url, headers={'User-Agent': 'PM99HistoricalResearch/1.0', 'Accept-Language': 'en-GB,en;q=0.9'})
                try:
                    with urlopen(request, timeout=30) as response:
                        raw = response.read(2 * 1024 * 1024 + 1); final_url = response.url
                finally:
                    time.sleep(1)
                if not 1000 <= len(raw) <= 2 * 1024 * 1024:
                    raise ValueError('original source outside bounded page limits')
                _validate_snapshot_payload(raw, url)
                page = BeautifulSoup(raw, 'html.parser')
                urls = {str(a.get('href', '')) for a in page.select('link[rel="canonical"]')}
                if len(urls) != 1 or (match := history.URL.fullmatch(next(iter(urls)))) is None or int(match[1]) != club_id:
                    raise ValueError('canonical original numerical club differs')
                path.write_bytes(raw)
                row = dict(status='original-club-history-captured', club=name, country=country,
                    source_club_id=club_id, url=url, final_url=final_url,
                    path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path),
                    retrieved_utc=datetime.now(UTC).isoformat(), bytes=len(raw),
                    title=page.title.get_text(' ', strip=True) if page.title else None,
                    period_coach_approved=False)
            except Exception as exc:
                row = dict(status='source-capture-failed-no-fallback', club=name, country=country,
                    source_club_id=club_id, url=url, error=type(exc).__name__ + ': ' + str(exc), retry_automatically=False)
            retained(receipt, row)
        rows.append(dict(row, receipt_path=registry.relative_workspace_path(receipt), receipt_sha256=registry.sha256_file(receipt)))
        print(dict(club=name, status=row['status'], bytes=row.get('bytes'), error=row.get('error')), flush=True)
    retained(ROOT / 'capture-summary.json', dict(utc=datetime.now(UTC).isoformat(), rows=rows,
        machine='joe-Vostro-3350', source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        native_writes=0, manager_cases_closed=0))


if __name__ == '__main__':
    main()
