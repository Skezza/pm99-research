"""Source/native adjudication of the pinned within-club queue; no game writes.

Different dates alone do not prove namesakes. Clear a duplicate suspicion only
when both identities have distinct literal dates, original squad witnesses,
matching native dates and distinct records. Opening-date membership remains a
separate question. Equal native dates are evidence, not deletion permission.
"""
import argparse
from collections import Counter
from datetime import date
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import consolidated_season_discovery_v1 as discovery


def classify(rows):
    dates=[r.get('recipe_date') for r in rows]
    if (len(rows)>=2 and all(isinstance(d,str) for d in dates) and
            len(set(dates))==len(dates) and all(r.get('native_date')==r.get('recipe_date')
              and r.get('original_squad_identity_verified') for r in rows)):
        return 'distinct-source-and-native-identities-not-a-duplicate'
    native_dates=[r.get('native_date') for r in rows]
    if all(native_dates) and len(set(native_dates))==1:
        return 'same-name-and-native-birthday-needs-ownership-or-reserve-repair'
    return 'unresolved-source-or-native-identity'


def run(root,roster_store):
    input_path=root/'within-club-and-date-triage.json'
    pinned=json.loads((root/'snapshot.json').read_text())
    assert discovery.bindings()==pinned['rows']
    document=json.loads(input_path.read_text())
    dispositions=[]; bindings=[]
    for section in document['seasons']:
        season=section['season'];release=registry.load_preferred_release(season)
        assert section['release_id']==release.release_id
        assert section['package_sha256']==registry.sha256_file(release.package_path)
        jug=release.game_path/'DBDAT/JUG98030.FDI';raw=jug.read_bytes()
        entries={e.record_id:e for e in IndexedFDIFile.from_bytes(raw).entries}
        report_path=roster_store/'rosters'/season/'report.json.gz'
        with gzip.open(report_path,'rt') as stream:
            report=json.load(stream)
        assert report['bindings']['jug_sha256']==hashlib.sha256(raw).hexdigest()
        sources={(p['club_id'],p['carrier_id']):p for p in report['players']}
        bindings.append({'season':season,'JUG_sha256':hashlib.sha256(raw).hexdigest(),
                         'roster_report_sha256':registry.sha256_file(report_path)})
        for group in section['within_club_name_candidates']:
            people=[]
            for p in group['players']:
                carrier=p['carrier_id'];payload=entries[carrier].decode_payload(raw)
                native=roster.native_player(payload,carrier);end=native['name_end']
                day,month=payload[end+12]^0x61,payload[end+13]^0x61
                year=int.from_bytes(bytes(v^0x61 for v in payload[end+14:end+16]),'little')
                try:native_date=date(year,month,day).isoformat()
                except ValueError:native_date=None
                source=sources[(group['club_id'],carrier)]
                verified=(source['membership_status']=='captured-squad-match' and
                          source['source_raw_verified'] and source['match_basis']=='name-and-birth-date')
                people.append({'carrier_id':carrier,'name':p['name'],'native_name':native['name'],
                    'recipe_date':p['birth_date'],'native_date':native_date,
                    'original_squad_identity_verified':verified,
                    'membership_status':source['membership_status'], 'source_evidence':source['evidence']})
            status=classify(people)
            stable=json.dumps([season,group['club_id'],sorted(p['carrier_id'] for p in people)],separators=(',',':'))
            dispositions.append({'id':hashlib.sha256(stable.encode()).hexdigest(),
                 'season':season,'club':group['club'],'club_id':group['club_id'],
                 'candidate_name':group['full_name_key'],'classification':status,'players':people,
                 'game_changed':False,'august_membership_cleared':False,
                 'duplicate_suspicion_cleared':status=='distinct-source-and-native-identities-not-a-duplicate'})
    assert discovery.bindings()==pinned['rows']
    result={'schema':'pm99-within-club-independent-native-source-dispositions-v1',
            'candidate_input_sha256':registry.sha256_file(input_path),'bindings':bindings,
            'summary':dict(Counter(r['classification'] for r in dispositions)),
            'rows':dispositions,'native_writes':0,
            'scope':'Adjudication of duplicate suspicion only; no opening-date ownership, skill or portrait clearance.'}
    discovery.write_new(root/'within-club-adjudication.json',result)
    print(json.dumps(result['summary']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--roster-store',type=Path,required=True)
    a=p.parse_args();run(a.root,a.roster_store)
