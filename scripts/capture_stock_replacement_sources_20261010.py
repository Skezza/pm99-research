"""Acquire bounded candidate club sources; never approves or writes a game."""
from datetime import UTC, datetime
from urllib.request import Request, urlopen
import time
import subprocess

from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts.capture_transfermarkt_opening_lineups_v1 import _validate_snapshot_payload
from scripts.capture_transfermarkt_historical_squads_v1 import parse_squad_with_dom_fallback

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/stock-club-history-v1/replacement-candidates'


def main(extra_sources=None, only_extra=False, transport='urllib', validator=_validate_snapshot_payload):
    if transport not in ('urllib', 'curl'):
        raise ValueError('unsupported public HTTP transport')
    ROOT.mkdir(exist_ok=True)
    urls = [('rodallega-profile', 'https://www.transfermarkt.co.uk/robert-rodallega/profil/spieler/351663'),
        ('radisic-profile', 'https://www.transfermarkt.co.uk/sinisa-radisic/profil/spieler/711047'),
        ('camacho-teammates', 'https://www.transfermarkt.co.uk/esmareley-camacho/gemeinsameSpiele/spieler/710556/gegner/350367/kriterium/2/wettbewerb//liga/0/verein/0')]
    urls += [(f'ofk-beograd-{year}', f'https://www.transfermarkt.co.uk/ofk-belgrad/kader/verein/53/saison_id/{year}/plus/1')
        for year in (2000, 2001, 2002, 2003, 2004, 2005, 2015)]
    urls += [(f'tachira-{year}', f'https://www.transfermarkt.co.uk/deportivo-tachira/kader/verein/13297/saison_id/{year}/plus/1')
        for year in (2000, 2001, 2002, 2003, 2014, 2015)]
    urls += [(f'ofk-beograd-{year}-schedule', f'https://www.transfermarkt.co.uk/ofk-belgrad/spielplan/verein/53/saison_id/{year}')
        for year in (2003, 2004, 2005, 2015)]
    urls += [(f'tachira-{year}-schedule', f'https://www.transfermarkt.co.uk/deportivo-tachira/spielplan/verein/13297/saison_id/{year}')
        for year in (2000, 2001, 2003, 2014, 2015)]
    urls += [(f'ofk-first-fixture-{year}-{match}', f'https://www.transfermarkt.co.uk/spielbericht/index/spielbericht/{match}')
        for year, match in ((2004, 3142214), (2005, 2927744), (2015, 2598829))]
    urls += [('becej-2015-preseason-report', 'https://becejski-mozaik.co.rs/vojvodanska-fudbalska-liga-grupa-backa-start-prvenstva-15-avgusta/'),
        ('becej-2015-opening-roster', 'https://becejski-mozaik.co.rs/vojvodanska-fudbalska-liga-grupa-backa-backa-liga-velika-nepoznanica/'),
        ('becej-2015-first-fixture', 'https://becejski-mozaik.co.rs/fudbal-backa-zona-1-kolo-becejska-goleada-u-somboru/'),
        ('becej-2015-second-fixture', 'https://becejski-mozaik.co.rs/fudbal-backa-zona-sestica-i-za-suboticane/'),
        ('becej-2015-fixture-article-index', 'https://becejski-mozaik.co.rs/wp-json/wp/v2/posts?after=2015-08-14T00:00:00&before=2015-08-25T23:59:59&per_page=100&_fields=id,date,link,title')]
    urls += [('ofk-2004-intertoto-official-retrospective', 'https://ofkbeograd.com/2024/07/27/secanje-na-polufinale-intertoto-kupa-2004-godine/'),
        ('ofk-2004-intertoto-mondo-retrospective', 'https://mondo.rs/Sport/Fudbal/a1957841/ofk-beograd-atletiko-madrid-u-intertoto-kupu-mondo-intervju.html'),
        ('ofk-2004-home-kit-catalogue', 'https://www.footballkitarchive.com/es/ofk-beograd-2004-05-home-kit/'),
        ('ofk-2004-ntf-annual', 'https://www.national-football-teams.com/club/2155/2004_1/Ofk_Beograd.html'),
        ('tachira-2014-footballnation-opening', 'https://footballnation.eu/match/primera-division-venezolana/2014/510598/')]
    urls += [('ofk-2015-official-first-report', 'https://ofkbeograd.co.rs/index.php?show=1379&tip=report'),
        ('ofk-2015-original-first-match-photographs', 'https://hotsport.rs/2015/07/19/superliga-srbije-preokret-zvezde-za-istoriju-sestica-u-drugom-poluvremenu-video-foto/')]
    urls += [('celta-2015-original-drazic-announcement', 'https://rccelta.es/equipo/actualidad/dejan-drazic-nuevo-jugador-del-celta-a-falta-del-reconocimiento-medico/'),
        ('celta-2015-original-annual', 'https://www.transfermarkt.co.uk/celta-vigo/kader/verein/940/saison_id/2015/plus/1')]
    urls += [('celta-2015-madinda-preseason-original', 'https://rccelta.es/equipo/actualidad/nolito-y-madinda-se-incorporan-a-la-pretemporada-celeste-el-14-de-julio/'),
        ('celta-2014-madinda-national-team-original', 'https://rccelta.es/equipo/actualidad/el-primer-equipo-recupera-a-sus-internacionales/')]
    urls += [('cancarevic-original-nationality-chronology', 'https://en.wikipedia.org/wiki/Ognjen_%C4%8Can%C4%8Darevi%C4%87')]
    if extra_sources is not None:
        urls = list(extra_sources) if only_extra else urls + list(extra_sources)
    for key, url in urls:
        path, receipt = ROOT / (key + '.html'), ROOT / (key + '.source.json')
        if receipt.exists():
            prior = pipeline.read_json_file(receipt)
            if prior['url'] != url or prior.get('sha256') and registry.sha256_file(path) != prior['sha256']:
                raise ValueError('retained source candidate changed')
            continue
        try:
            request = Request(url, headers={'User-Agent': 'PM99 historical database research (local source capture)',
                'Accept-Language': 'en-GB,en;q=0.9'})
            if transport == 'curl':
                payload = subprocess.run(['curl', '--fail', '--silent', '--show-error',
                    '--location', '--max-time', '30', '--max-filesize', str(2 * 1024 ** 2), url],
                    capture_output=True, check=True, timeout=35).stdout
            else:
                with urlopen(request, timeout=30) as response:
                    payload = response.read(2 * 1024 ** 2 + 1)
            if len(payload) > 2 * 1024 ** 2:
                raise ValueError('candidate original exceeds 2MiB bound')
            validator(payload, url)
            path.write_bytes(payload)
            page = BeautifulSoup(payload, 'html.parser')
            row = dict(url=url, utc=datetime.now(UTC).isoformat(), status='original-captured',
                transport=transport,
                sha256=registry.sha256_file(path), bytes=len(payload),
                original_title=page.title.get_text(' ', strip=True) if page.title else '',
                parsed_squad_players=parse_squad_with_dom_fallback(payload) if '/kader/' in url else [],
                target_squad_approved=False, native_writes=0)
        except Exception as exc:
            row = dict(url=url, utc=datetime.now(UTC).isoformat(), status='source-acquisition-gap',
                transport=transport,
                reason=str(exc), target_squad_approved=False, native_writes=0)
        pipeline.write_canonical_json(receipt, row)
        print(dict(key=key, status=row['status'], players=len(row.get('parsed_squad_players', []))), flush=True)
        time.sleep(2)


if __name__ == '__main__':
    main()
