"""Capture only missing Morecambe opening identity/role originals; no DB writes."""
from scripts.capture_stock_replacement_sources_20261010 import main

SOURCES=(
    ('morecambe2000-mark-smith-original-birthday','https://en.wikipedia.org/wiki/Mark_Smith_(footballer,_born_1973)'),
    ('morecambe2000-kenny-takano-original-club-archive','https://www.southportcentral.co.uk/players/player-details/?id=696'),
    ('morecambe2000-john-norman-original-birthday','https://www.11v11.com/players/john-norman-9941/'),
    ('morecambe2000-andy-heald-original-birthday','https://www.11v11.com/players/andy-heald-9950/'),
    ('morecambe2000-chris-price-official-club-role','https://www.stalybridgeceltic.co.uk/play.php?code=PRICC'),
    ('morecambe2000-original-manager-history','https://www.soccerbase.com/teams/team.sd?team_id=1732&teamTabs=managers'),
)


if __name__=='__main__':main(extra_sources=SOURCES,only_extra=True,transport='curl')
