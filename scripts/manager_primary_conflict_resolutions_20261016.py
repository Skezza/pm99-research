"""Replay ROOT-reviewed original reports resolving four coach-history conflicts.

These are explicit dated source decisions, not a generic 'take first result'
fallback. Keep the rejected/overlapping original history alongside the primary
club/report evidence. Sundsvall genuinely had two co-heads; one native coach
slot represents Cedergren without claiming he was the sole head coach.
"""
from datetime import date
import json
import re
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import capture_deferred_manager_originals_20261016 as captures
from scripts import capture_manager_conflict_articles_20261016 as articles
from scripts.season_historical_opening_review_v1 import _normalise

SCHEMA = 'pm99-original-primary-manager-conflict-resolutions-v1'
TARGETS = (
    ('2006-07', 8718, 'Dorival Júnior', '4724', 'contemporary-dismissal-report-rejects-premature-successor-date'),
    ('2014-15', 3930, 'Alan Mathews', '7546', 'contemporary-former-manager-report-rejects-overlapping-former-coach-tenure'),
    ('2014-15', 1101, 'Klas Ingesson', '23686', 'official-club-manager-role-and-continuous-2013-2014-period-override-truncated-provider-tenure'),
    ('2016-17', 2843, 'Joel Cedergren', '49203', 'one-native-coach-slot-selects-confirmed-co-head-not-sole-head-claim'),
)


def published_dates(page):
    values = [m.get('content', '') for m in page.select('meta[property="article:published_time"],meta[property="og:published_time"]')]
    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get('datePublished'), str):
                values.append(value['datePublished'])
            for item in value.values():
                if isinstance(item, (dict, list)):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    for script in page.select('script[type="application/ld+json"]'):
        try:
            walk(json.loads(script.string or script.get_text()))
        except ValueError:
            continue
    return {date.fromisoformat(v[:10]).isoformat() for v in values if re.match(r'^\d{4}-\d{2}-\d{2}', v)}


def original_article(key, *, published=None, anchors=()):
    receipt_path = articles.ROOT / (key + '.json')
    receipt = pipeline.read_json_file(receipt_path)
    expected = dict(articles.SOURCES)[key]
    if receipt['status'] != 'public-original-captured' or receipt['url'] != expected:
        raise ValueError('primary manager article was not captured from its original URL')
    raw_path = registry.ROOT / receipt['raw_path']
    if registry.sha256_file(raw_path) != receipt['raw_sha256']:
        raise ValueError('primary manager article original bytes changed')
    page = BeautifulSoup(raw_path.read_bytes(), 'html.parser')
    # Read structured publication dates before removing scripts from body text.
    dates = published_dates(page)
    for tag in page.select('script,style'):
        tag.decompose()
    text = _normalise(page.get_text(' ', strip=True))
    if published is not None and dates != {published}:
        raise ValueError('primary report publication date differs or is ambiguous')
    if any(_normalise(anchor) not in text for anchor in anchors):
        raise ValueError('reviewed primary source facts no longer independently reparse')
    return dict(path=receipt['raw_path'], sha256=receipt['raw_sha256'], url=expected,
        receipt_path=registry.relative_workspace_path(receipt_path), receipt_sha256=registry.sha256_file(receipt_path),
        published_dates=sorted(dates), reviewed_fact_anchors=list(anchors))


def resolve():
    report_path = captures.ROOT / 'capture-summary.json'
    report = pipeline.read_json_file(report_path); results = []
    for season, club_id, name, person_id, policy in TARGETS:
        matches = [r for r in report['rows'] if r['season'] == season and r['source_club_id'] == club_id]
        if len(matches) != 1 or matches[0]['status'] != 'source-case-remains-unresolved':
            raise ValueError('original four unresolved source cases changed')
        case = matches[0]; download = case['download']
        raw = registry.ROOT / download['raw_path']; receipt = registry.ROOT / download['receipt_path']
        if registry.sha256_file(raw) != download['raw_sha256'] or registry.sha256_file(receipt) != download['receipt_sha256']:
            raise ValueError('conflicting original provider page/receipt changed')
        page = BeautifulSoup(raw.read_bytes(), 'html.parser')
        canonicals = {str(a.get('href', '')) for a in page.select('link[rel="canonical"]')}
        if len(canonicals) != 1 or (match := captures.old.URL.fullmatch(next(iter(canonicals)))) is None or int(match[1]) != club_id:
            raise ValueError('original conflicting history numeric club identity differs')
        names = {str(a.get('title') or a.get_text(' ', strip=True)).strip()
            for a in page.select('a[href*="/profil/trainer/"]')
            if re.search(r'/profil/trainer/' + re.escape(person_id) + r'(?:/|$)', str(a.get('href', '')))} - {''}
        if name not in names:
            raise ValueError('accepted coach original numerical person/name is absent from history')
        if club_id == 8718:
            authorities = [original_article('sport-dorival-departure', published='2006-08-16', anchors=(
                'Dorival Júnior passou quase oito meses no comando técnico do Sport',
                'Givanildo Oliveira (sem clube)', 'confirmando a demissão do treinador'))]
            explanation = 'Contemporary16August2006 dismissal report describes Dorival as incumbent for almost eight months and Givanildo as unattached. Therefore reject the provider August1 successor start; Dorival covers actual August1.'
            coheads = None
        elif club_id == 3930:
            authorities = [original_article('bray-january-former-coach', published='2014-01-15', anchors=(
                'Former Bray Wanderers manager Pat Devlin', 'Alan Mathews', 'opportunity to replace him')),
                original_article('bray-resignation', published='2015-04-10', anchors=(
                    'Alan Mathews', 'maintain the club’s Premiership status last season'))]
            explanation = 'January2014 contemporary former-manager interview explicitly describes Mathews replacing Devlin; April2015 club statement credits his management of the previous season. Reject the stale overlapping Devlin employment/tenure as August2014 first-team management.'
            coheads = None
        elif club_id == 1101:
            authorities = [original_article('elfsborg-manager-2014', published='2014-10-16', anchors=(
                'Klas Ingesson har i dagarna meddelat att han kliver av managerrollen efter säsongen',
                'Vi har haft ett fantastiskt år med Klas som manager')),
                original_article('elfsborg-history', anchors=(
                    '2013. Är en på många sätt händelserik säsong',
                    '2014. Detta år präglades av Klas Ingessons bortgång den 29 oktober',
                    'Klas hann på sitt dryga år som huvudansvarig tränare för Elfsborg'))]
            explanation = 'Club-designated manager Ingesson continued from the2013 appointment through2014; the club’s contemporary October2014 announcement and history contradict the provider December2013 end. Jan Mian’s training/head-coach role is not silently merged into Ingesson.'
            coheads = None
        else:
            authorities = [original_article('sundsvall-shared-coaches', anchors=(
                'blev sedan huvudtränare 2013 tillsammans med Joel Cedergren',
                'Joel Cedergren tar rollen som huvudtränare från och med idag och för resterande del av säsongen 2016')),
                original_article('sundsvall-coach-history', anchors=(
                    '2013–2016 Joel Cedergren, Roger Franzén', 'Franzén fick lämna hösten 2016'))]
            explanation = 'The overlap is legitimate joint head coaching through autumn2016. Native one-manager capacity represents confirmed co-head Cedergren; it does not claim he was sole coach or merge Franzén’s identity.'
            coheads = [dict(name='Joel Cedergren', source_manager_id='49203'), dict(name='Roger Franzén', source_manager_id='4389')]
        results.append(dict(season=season, club=case['club'], club_id=case['club_id'],
            source_club_id=club_id, date=season[:4] + '-08-01', manager=name, source_manager_id=person_id,
            policy=policy, explanation=explanation, co_head_coaches=coheads,
            original_unresolved_case=case, primary_authorities=authorities,
            raw_history=dict(path=download['raw_path'], sha256=download['raw_sha256'], url=next(iter(canonicals))),
            reviewer='ROOT', original_primary_article_text_inspected=True,
            native_writes=0, recipe_writes=0, manager_cases_closed=0))
    return dict(schema=SCHEMA, resolutions=results, source_report=dict(
        path=registry.relative_workspace_path(report_path), sha256=registry.sha256_file(report_path)),
        original_source_conflicts_retained=True, native_writes=0, manager_cases_closed=0)


if __name__ == '__main__':
    from scripts.build_savio_bobb_alias_reserve_20261011 import retained
    result = resolve()
    retained(captures.ROOT.parent / 'primary-four-manager-resolutions.json', result)
    print(dict(primary_source_resolutions=len(result['resolutions']), native_writes=0, manager_cases_closed=0), flush=True)
