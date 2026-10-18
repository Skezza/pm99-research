"""Verify the final first-season ownership, role and nationality correction."""
from scripts import capture_cross_club_reserve_20261016 as capture
from scripts.build_donor_role_safety_20261016 import ROOT, RELEASE

TAG='donor_role_safety_2000_01_r108a_20261016'


if __name__=='__main__':
    capture.main(root=ROOT/'2000-01',release_id=RELEASE,tag=TAG)
