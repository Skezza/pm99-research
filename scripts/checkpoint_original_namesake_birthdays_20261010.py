"""Deliver the two independently corroborated placeholder-date corrections."""
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import run
from scripts.build_original_namesake_birthdays_20261010 import ROOT, CASES


if __name__ == '__main__':
    run(root=ROOT, cases=CASES, profiles={
        '2025-26': ('lawlor', 10666, 'Dylan Lawlor', 'Cardiff City', 19, None),
    }, prior_version=26, next_version=27, expected_delivered=239, expected_remaining=8,
        expected_new_dates=2, native_readback_version=9, proof_suffix='-independent-proof.json',
        close_ferran_finding=False)
