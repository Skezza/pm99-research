"""Retain original stock-club history evidence, without approving any squad."""
from datetime import UTC, datetime
import requests

from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1'
SOURCES = {
    'delirio-vinotinto.pdf': 'https://banesco-prod-2020.s3.amazonaws.com/wp-content/uploads/delirio-vinotinto.pdf',
    'becej-all-transfers.html': 'https://www.transfermarkt.co.uk/fk-becej/alletransfers/verein/777',
}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    for filename, url in SOURCES.items():
        path = ROOT / filename
        receipt = ROOT / (filename + '.source.json')
        if path.exists():
            old = pipeline.read_json_file(receipt)
            if old['url'] != url or old['sha256'] != registry.sha256_file(path):
                raise ValueError('retained original history evidence changed')
            continue
        response = requests.get(url, timeout=45)
        response.raise_for_status()
        if len(response.content) > 20 * 1024 ** 2:
            raise ValueError('history source exceeds bounded download')
        path.write_bytes(response.content)
        pipeline.write_canonical_json(receipt, dict(url=url, utc=datetime.now(UTC).isoformat(),
            sha256=registry.sha256_file(path), bytes=len(response.content),
            approves_target_season_squad=False))
        print(dict(source=filename, captured=True, squad_approved=False), flush=True)


if __name__ == '__main__':
    main()
