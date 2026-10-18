"""Capture original identity/career evidence for the observed surname aliases."""
from scripts import capture_manager_conflict_articles_20261016 as capture
from scripts.audit_shtanyuk_runtime_aliases_20261016 import ROOT


if __name__=='__main__':
    capture.ROOT=ROOT/'originals'
    capture.SOURCES=(
        ('identity-career-11v11','https://www.11v11.com/players/sergei-shtaniuk-12011/'),
        ('official-rfs','https://www.rfs.ru/cup/players/shtaniuk-siarhei'),
        ('national-football-teams','https://www.national-football-teams.com/player/665/Syarhey_Shtanyuk.html'),
    )
    capture.main()
