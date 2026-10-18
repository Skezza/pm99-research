"""Apply the reusable complete-proof gate to the one remaining Aldred group."""
from scripts.checkpoint_frozen_fixture_reserve_v1 import run
from scripts.build_aldred_frozen_fixture_20261017 import ROOT,SEASON,RELEASE,REPLAY
from scripts.capture_aldred_frozen_fixture_20261017 import TAG,PROFILES


if __name__=='__main__':
    run(ROOT,SEASON,RELEASE,REPLAY,ROOT.parent/'release-delivery-checklist-v57.json',
        ROOT.parent/'release-delivery-checklist-v58.json',TAG,PROFILES)
