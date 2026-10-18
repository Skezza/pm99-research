"""Missing-only acquisition of three original Morecambe biography leads.

Separate browser-identifying request from previous failed research-agent
requests; preserve every old failure receipt. Download is not identity approval.
"""
from datetime import UTC, datetime, date
import json
import subprocess
import time

from bs4 import BeautifulSoup
from scripts import capture_stock_replacement_sources_20261010 as old
from scripts.season_art_transaction_v1 import atomic_bytes
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def validate_source(payload, url):
    if url != 'https://www.southportcentral.co.uk/players/player-details/?id=696':
        old._validate_snapshot_payload(payload, url)
        return
    # This real profile includes a passive Cloudflare JS footer. The generic
    # Transfermarkt interstitial detector falsely rejects its marker even
    # though full biography and structured data are already in the response.
    # Do not disable that general guard or execute a challenge: instead require
    # this publisher's complete exact profile in two independent DOM locations.
    page = BeautifulSoup(payload, 'lxml')
    if len(payload) < 1000 or [h.get_text(' ', strip=True) for h in page.select('h1')] != ['Kenny Takano']:
        raise ValueError('original Southport numerical profile body absent')
    people = []
    for script in page.select('script[type="application/ld+json"]'):
        value = json.loads(script.get_text())
        if isinstance(value, dict) and value.get('@type') == 'Person':
            people.append(value)
    if (len(people) != 1 or people[0].get('@id') != url or people[0].get('url') != url
            or people[0].get('name') != 'Kenny Takano' or people[0].get('jobTitle') != 'Footballer'):
        raise ValueError('original Southport full Person identity missing')
    birthday = date.fromisoformat(people[0]['birthDate'])
    facts = {}
    for term in page.select('dl.mcr-player-facts dt'):
        definition = term.find_next_sibling('dd')
        if definition is not None:
            facts[term.get_text(' ', strip=True)] = definition.get_text(' ', strip=True)
    if (facts.get('Real name') != people[0].get('alternateName')
            or not facts.get('Born', '').startswith(birthday.strftime('%d/%m/%Y') + ' ')):
        raise ValueError('Southport displayed and structured biography disagree')


def main():
    requests = [
        ('morecambe2000-kenny-official-club-archive-literal-body-v2',
         'https://www.southportcentral.co.uk/players/player-details/?id=696'),
        ('morecambe2000-andy-official-club-biography',
         'https://www.afcsudbury.co.uk/a/a-to-z-the-men-of-afc-sudbury-39173.html?page=10'),
        ('morecambe2000-john-original-11v11-browser-request',
         'https://www.11v11.com/players/john-norman-9941/'),
    ]
    for key, url in requests:
        path, receipt = old.ROOT / (key + '.html'), old.ROOT / (key + '.source.json')
        if receipt.exists():
            prior = old.pipeline.read_json_file(receipt)
            if prior['url'] != url or prior.get('sha256') and old.registry.sha256_file(path) != prior['sha256']:
                raise ValueError('existing original biography capture changed')
            continue
        row = dict(url=url, utc=datetime.now(UTC).isoformat(), native_writes=0,
            transport='curl-browser-identifying-user-agent', target_identity_approved=False)
        try:
            result = subprocess.run(['curl', '--fail', '--silent', '--show-error', '--location',
                '--user-agent', 'Mozilla/5.0', '--max-time', '30', '--max-filesize',
                str(2 * 1024**2), url], capture_output=True, check=True, timeout=35)
            validate_source(result.stdout, url)
            atomic_bytes(path, result.stdout)
            page = BeautifulSoup(result.stdout, 'lxml')
            row.update(status='original-captured', sha256=old.registry.sha256_file(path),
                bytes=len(result.stdout), original_title=page.title.get_text(' ', strip=True) if page.title else '')
        except Exception as exc:
            row.update(status='source-acquisition-gap', reason=str(exc))
        retained(receipt, row)
        print(dict(key=key, status=row['status']), flush=True)
        time.sleep(2)


if __name__ == '__main__':
    main()
