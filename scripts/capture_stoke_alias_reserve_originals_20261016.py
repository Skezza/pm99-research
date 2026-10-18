"""Retain positive reserve and explicit conflicting proposed-reserve evidence.

Commons is a2001 candidate. Wilson's published Stoke loan dates must be
checked before any2002 admission; a match-page bench label is not enough.
"""
from scripts import capture_manager_conflict_articles_20261016 as capture
from scripts.audit_shtanyuk_runtime_aliases_20261016 import ROOT


if __name__=='__main__':
    capture.ROOT=ROOT/'reserve-originals'
    capture.SOURCES=(
        ('commons-soccerbase','https://www.soccerbase.com/players/player.sd?player_id=28633'),
        ('wilson-conflicting-opening-soccerbase','https://www.soccerbase.com/players/player.sd?player_id=13854'),
        ('vandeurzen-biography','https://en.wikipedia.org/wiki/Jurgen_Vandeurzen'),
    )
    capture.main()
