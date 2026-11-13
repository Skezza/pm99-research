"""Validate completed games while the build and runner advance; fixed scope26."""
import time
from datetime import UTC,datetime
from scripts import json_storage_io_v1 as storage_io
from scripts import season_release_registry_v1 as registry
from scripts.attest_registered_season_runtime_v1 import _atomic_replace_json
from scripts.audit_delivered_rating_calibrations_v1 import audit
from scripts.build_all_rating_calibrations_20261011 import ROOT,release_id
from scripts.capture_rating_profiles_20261011 import PROFILES

STEPS=('quality-plan.json','native-byte-proof.json','complete-SOURCE-replay.json',
    'all-updated-players-native-readback.json','startup-transport.json','startup-visual-review.json','final-attestation.json')
def status():
    rows=[]
    for season in registry.supported_seasons():
        root=ROOT/season
        # The single auditor owns these outputs; no concurrent regeneration.
        if storage_io.exists(root / 'complete-SOURCE-replay.json') and not storage_io.exists(root / 'all-updated-players-native-readback.json'):
            print(audit(season),flush=True)
        rows.append(dict(season=season,release_id=release_id(season),steps={name:storage_io.exists(root / name) for name in STEPS}))
    profiles=[dict(season=s,carrier=carrier,label=label,
        transport=storage_io.exists(ROOT / s / (label + '-profile-transport.json')),
        visual_review=storage_io.exists(ROOT / s / (label + '-profile-visual-review.json')),
        native_runtime_proof=storage_io.exists(ROOT / s / (label + '-native-runtime-proof.json'))) for s,carrier,label,_ in PROFILES]
    _atomic_replace_json(ROOT/'live-status.json',dict(utc=datetime.now(UTC).isoformat(),scope='Only this fixed26-season rating delivery; not global historical completeness',
        season_count=26,required_per_season=list(STEPS),seasons=rows,profiles=profiles,
        note='File presence is a progress indicator, not a substitute for final hash/semantic/visual verification. No changing original duplicate denominator.'))
    return sum(r['steps'][STEPS[3]] for r in rows)==26

if __name__=='__main__':
    deadline=time.monotonic()+7200
    while True:
        if status():break
        if time.monotonic()>deadline:raise ValueError('bounded validation watch expired')
        time.sleep(20)
