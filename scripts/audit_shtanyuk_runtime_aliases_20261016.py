"""Trace an observed Stoke surname-alias candidate across all26 actual games.

Read-only discovery. Different recipe dates/person IDs do not prove two people;
the original published identity and a sourced replacement still need admission.
This does not alter the frozen82 within-club or2797 cross-club denominators.
"""
from collections import defaultdict
import hashlib
from datetime import UTC, datetime, date
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/Shtanyuk-runtime-alias-v1'
ALIASES = {roster.normalise(n) for n in ('Sergey Shtanyuk','Sergei Shtanyuk',
    'Siarhei Shtaniuk','Syarhey Shtanyuk','Sergei Shtaniuk')}


def main():
    if (ROOT/'current-native-alias-candidates.json').exists():
        raise ValueError('completed read-only discovery must not repeat')
    ROOT.mkdir(parents=True,exist_ok=True); rows=[]; groups=[]
    for season in registry.supported_seasons():
        base=registry.load_preferred_release(season)
        package=pipeline.read_json_file(base.package_path)
        found=[p for p in package['players'] if ALIASES.intersection(
            roster.normalise(p.get(key,'')) for key in ('name','source_name'))]
        if not found:
            continue
        clubs={c['id']:c for c in package['clubs']}
        jug=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        entries={e.record_id:e for e in roster.IndexedFDIFile.from_bytes(jug).entries}
        by_club=defaultdict(list)
        for player in found:
            carrier=player['carrier_id']; payload=entries[carrier].decode_payload(jug)
            native=roster.native_player(payload,carrier);end=native['name_end']
            day,month=payload[end+12]^0x61,payload[end+13]^0x61
            year=int.from_bytes(bytes(v^0x61 for v in payload[end+14:end+16]),'little')
            row=dict(season=season,club_id=player['club_id'],club=clubs[player['club_id']]['name'],
                player_id=player['id'],carrier_id=carrier,name=player['name'],source_name=player.get('source_name'),
                person_id=player.get('person_id'),facts=player['facts'],native_name=native['name'],
                native_birth_date=date(year,month,day).isoformat(),release_id=base.release_id,
                manifest_sha256=base.manifest_sha256,package_sha256=registry.sha256_file(base.package_path),
                native_record_sha256=hashlib.sha256(payload).hexdigest())
            rows.append(row);by_club[player['club_id']].append(row)
        for cid,members in by_club.items():
            if len(members)>1:
                groups.append(dict(season=season,club_id=cid,club=clubs[cid]['name'],
                    carriers=[r['carrier_id'] for r in members],state='additional-runtime-alias-candidate-not-original82-closure',
                    independently_sourced_replacement_and_native_fix_delivered=False))
    retained(ROOT/'current-native-alias-candidates.json',dict(utc=datetime.now(UTC).isoformat(),
        machine='joe-Vostro-3350',source_session='01a0592d-fcd5-7262-a637-743a8253d9b4',
        rows=rows,groups=groups,native_writes=0,cases_closed=0,original82_unchanged=True,frozen2797_unchanged=True,
        original_source_leads=[
            'https://www.11v11.com/players/sergei-shtaniuk-12011/',
            'https://www.rfs.ru/cup/players/shtaniuk-siarhei',
            'https://www.national-football-teams.com/player/665/Syarhey_Shtanyuk.html'],
        note='2001/2002 runner frames visibly contain Shtanyuk and Shtaniuk. Primary-source replay, original August squad and correct replacement admission remain required. Different false DOBs can evade exact-name/DOB duplicate detection. Manager batch preserves these player bytes, does not introduce or close the issue.'))
    print(dict(native_records=len(rows),additional_alias_groups=len(groups),native_writes=0,cases_closed=0),flush=True)


if __name__=='__main__':
    main()
