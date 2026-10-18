"""Resolve weak coach witnesses against cached dated tenures, without game writes.

A filename is not club identity: require the original canonical numeric club
URL. All readable cached tenure claims must agree on coach ID and full name.
No tenure coverage, overlapping appointments or disagreeing captures stay open.
"""
from collections import defaultdict,Counter
from datetime import date
from pathlib import Path
import re
from bs4 import BeautifulSoup
from scripts import season_pipeline_v2 as pipeline,season_release_registry_v1 as registry
from scripts import capture_opening_manager_history_supplements_v1 as history
from scripts.build_year_bound_manager_repairs_20261016 import ROOT
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

URL=re.compile(r'https://www\.transfermarkt\.(?:co\.uk|com)/[^/]+/mitarbeiterhistorie/verein/([1-9][0-9]*)/?$')


def tenure(raw,club_id,at):
    page=BeautifulSoup(raw,'html.parser')
    urls={str(link.get('href','')) for link in page.select('link[rel="canonical"]')}
    if len(urls)!=1:raise ValueError('original history needs one canonical club URL')
    url=next(iter(urls));match=URL.fullmatch(url)
    if match is None or int(match[1])!=club_id:
        raise ValueError('original history canonical numeric club identity differs')
    name,person=history.manager_at_date(raw,at)
    return dict(manager=name,source_manager_id=person,source_url=url,date=at.isoformat())


def index():
    roots=[registry.ROOT/'.local/external-sources/cache.transfermarkt-opening/manager-history',
        registry.ROOT/'.local/external-sources/cache.transfermarkt-2015-manager-snapshot-v5/manager-history/2015-snapshot',
        registry.ROOT/'.local/external-sources/cache.transfermarkt-2015-manager-exact-search-v6/manager-history/manager-history/2015-exact-search']
    roots.extend((registry.ROOT/'.local/transfermarkt-opening-plans-current-v1').glob('*/cache/manager-history'))
    result=defaultdict(list)
    for root in roots:
        for path in sorted(root.glob('*.html')):
            if path.stem.isdigit():result[int(path.stem)].append(path)
    return result


def receipt_index():
    """Join captured download hashes, not just self-declared page canonicals."""
    documents=list((registry.ROOT/'.local/transfermarkt-opening-plans-current-v1').glob(
        '*/opening-manager-supplement-transfermarkt.json'))
    documents.extend(registry.ROOT/'.local/operations/2015-16'/name for name in (
        'world-manager-history-transfermarkt-snapshot-v5-r2-20260912.json',
        'world-manager-history-transfermarkt-exact-search-v6-r3-20260912.json'))
    result=defaultdict(list)
    for path in documents:
        if not path.exists():continue
        document=pipeline.read_json_file(path)
        provenance=dict(receipt_path=registry.relative_workspace_path(path),
            receipt_sha256=registry.sha256_file(path))
        for key in ('cache_files','manager_history_cache_files'):
            for row in document.get('sources',{}).get(key,[]):
                match=URL.fullmatch(row.get('url',''))
                if match:
                    result[(int(match[1]),row['sha256'])].append(dict(provenance,
                        original_download_url=row['url'],original_cache_path=row['cache_path']))
    return result


def inspect(paths,club_id,at,receipts=None):
    claims=[];unusable=[]
    for path in paths:
        binding=dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))
        try:
            witnesses=(receipts or {}).get((club_id,binding['sha256']),[])
            claims.append(dict(tenure(path.read_bytes(),club_id,at),**binding,
                original_download_receipt_verified=bool(witnesses),download_receipts=witnesses))
        except (ValueError,history.ManagerHistoryError) as exc:
            unusable.append(dict(binding,reason=str(exc)))
    identities={(c['manager'],c['source_manager_id']) for c in claims}
    # An overlapping appointment is a real contradiction, not simply an old
    # capture without the requested tenure. Do not hide it behind a good copy.
    overlaps=any((match:=re.search(r'has ([0-9]+) managers covering',u['reason']))
        is not None and int(match[1])>1 for u in unusable)
    if overlaps or len(identities)>1:status='conflicting-original-tenure-claims'
    elif len(identities)==1:status='unanimous-reparsed-August1-tenure-candidate'
    else:status='no-readable-cached-tenure-at-target-date'
    return dict(status=status,claims=claims,unusable=unusable)


def main():
    files=index();receipts=receipt_index();rows=[]
    for path in sorted(ROOT.glob('20*-*/source-acceptance-decision.json')):
        decision=pipeline.read_json_file(path);season=decision['season']
        for item in decision['deferred']:
            row=item['row'];club_id=row['evidence']['source_club_id']
            evidence=inspect(files.get(club_id,[]),club_id,date(int(season[:4]),8,1),receipts)
            result=dict(season=season,club=row['club'],club_id=row['club_id'],
                source_club_id=club_id,old_proposed_coach=row['after'],original_deferral=item['reason'],
                decision_path=registry.relative_workspace_path(path),decision_sha256=registry.sha256_file(path),**evidence)
            rows.append(result)
            print(dict(season=season,club=row['club'],status=evidence['status'],
                managers=sorted({c['manager'] for c in evidence['claims']})),flush=True)
    if len(rows)!=85:raise ValueError('all85 deferred proposals must remain accounted for')
    retained(ROOT/'deferred-tenure-source-audit-v2.json',dict(original_deferred=85,
        source_date_policy='literal-August1-tenure-not-current-manager-or-following-year-fixture',
        native_writes=0,recipe_writes=0,global_manager_approval=False,
        statuses=dict(Counter(r['status'] for r in rows)),
        unanimous_candidates_with_download_provenance=sum(r['status']=='unanimous-reparsed-August1-tenure-candidate'
            and any(c['original_download_receipt_verified'] for c in r['claims']) for r in rows),rows=rows))


if __name__=='__main__':main()
