#!/usr/bin/env python3
"""Verify every newly installed photo against its source, recipe and native BMP."""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import season_release_registry_v1 as registry
from scripts import season_portrait_pipeline_v1 as portraits
from scripts import season_visual_patch_v1 as art


def committed_photo_receipts(release):
    """Read only receipts bound to committed stages of this release's chain."""
    if release.build_chain_path is None:
        return []
    chain = json.loads(release.build_chain_path.read_text())
    stages = {stage['id']: (index, stage) for index, stage in enumerate(chain['stages'])}
    found = []
    for journal_path in (ROOT / '.local/season-art-transactions-v1').glob('*/' + release.season + '/journal.json'):
        journal = json.loads(journal_path.read_text())
        key = 'portrait-' + journal.get('release_id', '')
        if journal.get('state') != 'committed' or key not in stages:
            continue
        application_path = journal_path.parent / 'visual-patch-application.json'
        application = json.loads(application_path.read_text())
        path = Path(application['materialisation_path'])
        path.resolve().relative_to(ROOT.resolve())
        index, stage = stages[key]
        if art.sha(application_path) != stage['receipt_sha256'] or art.sha(path) != application['materialisation_sha256']:
            raise ValueError('committed photo receipt no longer matches the release chain')
        found.append((index, journal['release_id'], json.loads(path.read_text())))
    return [(lane, receipt) for _, lane, receipt in sorted(found)]


def foreign_roster_ids(package):
    # Capacity policy alone is not a country boundary: the 92 English clubs
    # also preserve fixed carriers. Foreign membership is explicitly declared.
    return {pid for club in package['clubs']
            if club.get('division') == 'preserve-existing-mode1-membership'
            for pid in club['roster_player_ids']}


def verify(output):
    rows, failures = [], []
    for season in registry.supported_seasons():
        release=registry.load_preferred_release(season)
        active_archive = {}
        for record in portraits.iter_minifoto_records(release.game_path / 'DBDAT/MINIFOTO.PKF'):
            active_archive.setdefault(record.player_record_id, []).append(
                hashlib.sha256(record.raw_bitmap).hexdigest())
        players={int(p['carrier_id']):p for p in json.loads(release.package_path.read_text())['players']}
        expected={}
        for root in ('foreign-portrait-rollout-r8','reviewed-real-photo-rollout-r9'):
            path=ROOT/'.local'/root/season/'patch/receipt.json'
            if path.exists():
                for row in json.loads(path.read_text())['replacements']:expected[int(row['carrier_id'])]=(root,row)
        for lane, receipt in committed_photo_receipts(release):
            for row in receipt.get('replacements', []):
                if 'source_sha256' in row and 'bitmap_sha256' in row:
                    expected[int(row['carrier_id'])] = (lane, row)
        checked=[]
        for carrier,(root,row) in expected.items():
            issues=[];player=players.get(carrier)
            if not player or player['name']!=row['name'] or player.get('facts',{}).get('birth_date')!=row['birth_date']:
                issues.append('recipe-identity-changed')
            bitmap=release.game_path/'DBDAT/MINIFOTO'/f'J96{carrier:05d}.BMP'
            if not bitmap.exists() or art.sha(bitmap)!=row['bitmap_sha256']:issues.append('installed-bitmap-changed')
            else:portraits.validate_minifoto_bitmap(bitmap.read_bytes())
            if any(digest != row['bitmap_sha256'] for digest in active_archive.get(carrier, [])):
                issues.append('conflicting-active-archive-portrait')
            if 'source_image_url' in row:
                _,source=portraits._cache_paths(portraits.DEFAULT_CACHE,row['source_image_url'])
            else:
                url=row['source']['image_url'];key=hashlib.sha256(url.encode()).hexdigest()
                cache = Path(row.get('source_cache_root', ROOT/'.local/foreign-photo-expansion-v1/source-cache'))
                cache.resolve().relative_to(ROOT.resolve())
                source=cache/key[:2]/(key+'.bin')
            if not source.exists() or art.sha(source)!=row['source_sha256']:issues.append('source-bytes-changed')
            checked.append({'carrier_id':carrier,'name':row['name'],'lane':root,'issues':issues,
                            'source_kind': 'real-photo' if 'source' in row else 'fifa-photo',
                            'active_archive_entry_count':len(active_archive.get(carrier, []))})
            if issues:failures.append({'season':season,**checked[-1]})
        package = json.loads(release.package_path.read_text())
        foreign_ids = foreign_roster_ids(package)
        verified = {p['carrier_id']: p for p in checked if not p['issues']}
        counts = {}
        coverage_path = output.parent / 'coverage' / (season + '.csv')
        coverage_path.parent.mkdir(parents=True, exist_ok=True)
        with coverage_path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=['season', 'carrier_id', 'name', 'birth_date', 'club_id', 'status'])
            writer.writeheader()
            for p in package['players']:
                if p['id'] not in foreign_ids: continue
                carrier = int(p['carrier_id'])
                bmp = release.game_path/'DBDAT/MINIFOTO'/f'J96{carrier:05d}.BMP'
                status = ('verified-' + verified[carrier]['source_kind']) if carrier in verified else (
                    'inherited-unverified' if bmp.is_file() or carrier in active_archive else 'missing')
                counts[status] = counts.get(status, 0) + 1
                writer.writerow({'season': season, 'carrier_id': carrier, 'name': p['name'],
                                 'birth_date': p.get('facts', {}).get('birth_date'), 'club_id': p['club_id'], 'status': status})
        rows.append({'season':season,'release_id':release.release_id,'new_photo_carriers_checked':len(checked),
                     'recipe_sha256':art.sha(release.package_path),'players':checked,
                     'foreign_roster_coverage': counts, 'foreign_coverage_csv': str(coverage_path)})
    result={'schema_version':'pm99-foreign-photo-rollout-verification-v1','seasons_checked':len(rows),
            'new_photo_carriers_checked':sum(r['new_photo_carriers_checked'] for r in rows),
            'failure_count':len(failures),'failures':failures,'seasons':rows,
            'foreign_roster_coverage': {key: sum(r['foreign_roster_coverage'].get(key, 0) for r in rows)
                                      for key in ('verified-real-photo', 'verified-fifa-photo', 'inherited-unverified', 'missing')},
            'scope':'new photo recipe identities/source/BMP bytes and absence of conflicting active archive portraits; not certification of unmodified inherited assets'}
    art.save(output,result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('seasons','failures')}))
    return bool(failures)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    raise SystemExit(verify(parser.parse_args().output))
