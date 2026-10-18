"""Private two-byte Stoke flag control; no release or historical policy change."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import season_package_compiler_v2
from scripts import season_release_registry_v1 as registry
from scripts import season_pipeline_v2 as pipeline
from app.fdi_indexed import IndexedFDIFile
from app.eq_jug_linked import parse_eq_external_team_roster_payload


def patch_flags(original,carrier,players):
    if not players or len(players)!=len(set(players)):raise ValueError('need distinct explicit player IDs')
    entries=[e for e in IndexedFDIFile.from_bytes(original).entries if e.record_id==carrier]
    if len(entries)!=1:raise ValueError('team carrier is not unique')
    entry=entries[0];raw=original[entry.payload_offset:entry.payload_offset+entry.payload_length]
    roster=parse_eq_external_team_roster_payload(raw,{})
    if roster is None or roster.mode_byte!=0:raise ValueError('pilot supports parsed mode-0 roster only')
    rows=[r for r in roster.rows if r.player_record_id in players]
    if len(rows)!=len(players) or any(r.flag!=1 for r in rows):raise ValueError('pilot requires exact flag-one rows')
    result=bytearray(original);offsets=[]
    for row in rows:
        offset=entry.payload_offset+row.raw_row_offset
        if result[offset]!=1:raise ValueError('flag byte disagrees with parser')
        result[offset]=0;offsets.append(offset)
    if [i for i,(a,b) in enumerate(zip(original,result)) if a!=b]!=sorted(offsets):
        raise ValueError('pilot changed bytes outside the selected flags')
    changed=parse_eq_external_team_roster_payload(bytes(result[entry.payload_offset:entry.payload_offset+entry.payload_length]),{})
    if [(r.player_record_id,r.flag) for r in changed.rows]!=[
            (r.player_record_id,0 if r.player_record_id in players else r.flag) for r in roster.rows]:
        raise ValueError('pilot changed roster membership, order or unselected flags')
    return bytes(result),{'carrier_id':carrier,'player_ids':players,'changed_offsets':sorted(offsets),
        'changed_bytes':len(offsets),'membership_and_order_unchanged':True}


def prepare(output):
    if output.exists():raise ValueError('private roster control is immutable')
    release=registry.load_preferred_release('2007-08')
    original=(release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    changed,proof=patch_flags(original,351,[10734,10886])
    dbdat=output/'DBDAT';dbdat.mkdir(parents=True);(dbdat/'EQ98030.FDI').write_bytes(changed)
    for name in ('JUG98030.FDI','ENT98030.FDI','MINIFOTO.PKF','BIGCAMP.PKF','BIGESC.PKF',
                 'MINIESC.PKF','NANOESC.PKF','RIDIESC.PKF'):
        os.link(release.game_path/'DBDAT'/name,dbdat/name)
    os.link(release.game_path/'MANAGPRE.EXE',output/'MANAGPRE.EXE')
    receipt={'schema_version':'pm99-private-roster-flag-runtime-control-v1','historical_release':False,
        'publication_authorised':False,'season':'2007-08','release_id':release.release_id,'proof':proof,
        'baseline_eq_sha256':hashlib.sha256(original).hexdigest(),
        'pilot_eq_sha256':hashlib.sha256(changed).hexdigest(),
        'jug_sha256':registry.sha256_file(dbdat/'JUG98030.FDI'),
        'scope':'causal control only; no assertion that flag one means loan, injury or historical absence'}
    pipeline.write_canonical_json(output/'private-pilot.json',receipt);return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.output)),flush=True)
