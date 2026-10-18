"""Verify ROOT-inspected actual Woking/Oxford profiles against native inputs."""
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.build_woking_owned_opening_20261011 import ROOT,SEASON,RELEASE
from scripts.capture_woking_owned_opening_20261011 import PROFILES

if __name__=='__main__':verify_profiles(ROOT,SEASON,RELEASE,PROFILES)
