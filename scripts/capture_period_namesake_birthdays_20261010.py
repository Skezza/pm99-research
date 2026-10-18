"""Capture the exact original-period namesake repair, serially on the runner."""
from scripts.capture_original_secondary_facts_20261010 import main
from scripts.build_period_namesake_birthdays_20261010 import ROOT, CASES


if __name__ == '__main__':
    main(root=ROOT, cases=CASES, profiles={'2025-26': ('Harry Webster', 'webster', 27048)},
        preceding=ROOT.parent / 'original-namesake-birthdays-v1/lawlor-profile-transport.json',
        proof_suffix='-independent-proof.json')
