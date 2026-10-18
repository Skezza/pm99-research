"""Retain bounded public primary reports for four conflicting coach histories.

Capturing a page is not approving a coach: ROOT must inspect each article and
admission must retain the explicit conflict, dated role and engine limitation.
"""
from datetime import UTC, datetime
from urllib.request import Request, urlopen
import time
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/remaining-manager-originals-v1/conflict-articles'
SOURCES = (
    ('bray-january-former-coach', 'https://www.irishtimes.com/sport/soccer/pat-devlin-airs-grievances-with-bray-wanderers-and-alan-mathews-decision-to-take-over-1.1655215'),
    ('bray-first-signings', 'https://extratime.com/articles/11587/bray-sign-six-as-the-new-reign-begins/'),
    ('bray-resignation', 'https://www.rte.ie/sport/soccer/2015/0410/693369-bray-settle-issues-with-alan-matthews/'),
    ('elfsborg-manager-2014', 'https://elfsborg.se/2014/10/16/klas-ingesson-slutar-som-manager-efter-sasongen/'),
    ('elfsborg-history', 'https://elfsborg.se/om-if-elfsborg/historik/'),
    ('sundsvall-shared-coaches', 'https://gifsundsvall.se/roger-franzen-lamnar-gif-sundsvall/'),
    ('sundsvall-coach-history', 'https://gifsundsvall.se/historia/gif-sundsvalls-tranare-genom-tiderna/'),
    ('sport-dorival-departure', 'https://meusport.com/noticias-do-sport-recife/dorival_junior_nao_e_mais_tecnico_do_sport/'),
)
MAX_BYTES = 2 * 1024 * 1024


def main():
    ROOT.mkdir(parents=True, exist_ok=True); rows = []
    if (ROOT / 'capture-summary.json').exists():
        raise ValueError('completed conflict article capture must not repeat')
    for key, url in SOURCES:
        path = ROOT / (key + '.html'); outcome = ROOT / (key + '.json')
        if outcome.exists():
            row = pipeline.read_json_file(outcome)
            if row['url'] != url:
                raise ValueError('retained source URL changed')
            if row['status'] == 'public-original-captured' and registry.sha256_file(path) != row['raw_sha256']:
                raise ValueError('retained original article bytes changed')
        else:
            if path.exists():
                raise ValueError('unreceipted original article; inspect before retry')
            try:
                request = Request(url, headers={'User-Agent': 'PM99HistoricalResearch/1.0', 'Accept-Language': 'en-GB,en;q=0.9'})
                try:
                    with urlopen(request, timeout=30) as response:
                        raw = response.read(MAX_BYTES + 1); final_url = response.url
                finally:
                    time.sleep(1)
                if len(raw) < 1000 or len(raw) > MAX_BYTES:
                    raise ValueError('original article outside bounded size limits')
                from scripts.capture_transfermarkt_opening_lineups_v1 import _validate_snapshot_payload
                _validate_snapshot_payload(raw, url)
                page = BeautifulSoup(raw, 'html.parser')
                title = page.title.get_text(' ', strip=True) if page.title else None
                if not title:
                    raise ValueError('source lacks original document title')
                path.write_bytes(raw)
                row = dict(status='public-original-captured', url=url, final_url=final_url,
                    raw_path=registry.relative_workspace_path(path), raw_sha256=registry.sha256_file(path),
                    bytes=len(raw), title=title, retrieved_utc=datetime.now(UTC).isoformat(),
                    historical_claim_approved=False)
            except Exception as exc:
                row = dict(status='capture-failed-no-fallback-claim', url=url,
                    error=type(exc).__name__ + ': ' + str(exc), retry_automatically=False)
            retained(outcome, row)
        rows.append(dict(key=key, **row))
        print(dict(key=key, status=row['status'], title=row.get('title'), error=row.get('error')), flush=True)
    retained(ROOT / 'capture-summary.json', dict(utc=datetime.now(UTC).isoformat(), rows=rows,
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', machine='joe-Vostro-3350',
        native_writes=0, recipe_writes=0, manager_cases_closed=0,
        scope='Primary public article captures only. Explicit ROOT source/conflict/period review and bounded admission remain required.'))


if __name__ == '__main__':
    main()
