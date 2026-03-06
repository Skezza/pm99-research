"""
League and competition definitions for Premier Manager 99.

Leagues are organized by nation, with England having 4 divisions
and other nations typically having a single top division.
"""

from typing import Dict, List, Tuple, Optional

# League structure based on game UI
# Each league has: name, team_id_start, team_id_end, team_count
LEAGUE_STRUCTURE = {
    "England": [
        {
            "name": "Premier League",
            "division": 1,
            "team_count": 20,
            "id_start": 3712,
            "id_end": 3731
        },
        {
            "name": "First Division",
            "division": 2,
            "team_count": 20,
            "id_start": 3732,
            "id_end": 3751
        },
        {
            "name": "Second Division",
            "division": 3,
            "team_count": 20,
            "id_start": 3752,
            "id_end": 3771
        },
        {
            "name": "Third Division",
            "division": 4,
            "team_count": 20,
            "id_start": 3772,
            "id_end": 3791
        }
    ],
    "Spain": [
        {
            "name": "La Liga",
            "division": 1,
            "team_count": 20,
            "id_start": 3792,
            "id_end": 3811
        }
    ],
    "Italy": [
        {
            "name": "Serie A",
            "division": 1,
            "team_count": 18,
            "id_start": 3812,
            "id_end": 3829
        }
    ],
    "Germany": [
        {
            "name": "Bundesliga",
            "division": 1,
            "team_count": 18,
            "id_start": 3830,
            "id_end": 3847
        }
    ],
    "France": [
        {
            "name": "Ligue 1",
            "division": 1,
            "team_count": 18,
            "id_start": 3848,
            "id_end": 3865
        }
    ],
    "Portugal": [
        {
            "name": "Primeira Liga",
            "division": 1,
            "team_count": 18,
            "id_start": 3866,
            "id_end": 3883
        }
    ],
    "Netherlands": [
        {
            "name": "Eredivisie",
            "division": 1,
            "team_count": 18,
            "id_start": 3884,
            "id_end": 3901
        }
    ],
    "Scotland": [
        {
            "name": "Scottish Premier League",
            "division": 1,
            "team_count": 10,
            "id_start": 3902,
            "id_end": 3911
        }
    ]
}

# Best-effort fallback for the observed EQ98030.FDI team stream order.
# The team parser can recover valid names even when the parsed `team_id` is noisy
# or zero, but the decoded team list itself is still strongly grouped by
# competition. These blocks are used only when the primary `team_id` mapping
# fails, so the parser-backed range mapping stays authoritative where it works.
TEAM_SEQUENCE_FALLBACKS: List[Dict[str, object]] = [
    {"index_start": 0, "index_end": 19, "country": "Spain", "league": "La Liga"},
    {"index_start": 20, "index_end": 37, "country": "Italy", "league": "Serie A"},
    {"index_start": 38, "index_end": 59, "country": "England", "league": "Premier League"},
    {"index_start": 60, "index_end": 83, "country": "England", "league": "First Division"},
    {"index_start": 84, "index_end": 107, "country": "England", "league": "Second Division"},
    {"index_start": 108, "index_end": 131, "country": "England", "league": "Third Division"},
    {"index_start": 132, "index_end": 149, "country": "Germany", "league": "Bundesliga"},
    {"index_start": 150, "index_end": 167, "country": "France", "league": "Division 1"},
    {"index_start": 168, "index_end": 182, "country": "Portugal", "league": "Primeira Liga"},
    {"index_start": 183, "index_end": 187, "country": "Yugoslavia", "league": "First League"},
    {"index_start": 188, "index_end": 194, "country": "Russia", "league": "Top Division"},
    {"index_start": 195, "index_end": 211, "country": "Netherlands", "league": "Eredivisie"},
    {"index_start": 212, "index_end": 229, "country": "Belgium", "league": "First Division"},
    {"index_start": 230, "index_end": 233, "country": "Croatia", "league": "First League"},
    {"index_start": 234, "index_end": 243, "country": "Sweden", "league": "Allsvenskan"},
    {"index_start": 244, "index_end": 252, "country": "Turkey", "league": "First League"},
    {"index_start": 253, "index_end": 263, "country": "Poland", "league": "First Division"},
    {"index_start": 264, "index_end": 275, "country": "Switzerland", "league": "Nationalliga A"},
    {"index_start": 276, "index_end": 285, "country": "Austria", "league": "Bundesliga"},
    {"index_start": 286, "index_end": 296, "country": "Denmark", "league": "Superliga"},
    {"index_start": 297, "index_end": 307, "country": "Scotland", "league": "Premier Division"},
    {"index_start": 308, "index_end": 318, "country": "Greece", "league": "Alpha Ethniki"},
    {"index_start": 319, "index_end": 327, "country": "Norway", "league": "Tippeligaen"},
    {"index_start": 328, "index_end": 335, "country": "Romania", "league": "Divizia A"},
    {"index_start": 336, "index_end": 343, "country": "Czech Republic", "league": "First League"},
    {"index_start": 344, "index_end": 349, "country": "Bulgaria", "league": "A Group"},
    {"index_start": 350, "index_end": 358, "country": "Slovakia", "league": "First League"},
    {"index_start": 359, "index_end": 363, "country": "Slovenia", "league": "First League"},
    {"index_start": 364, "index_end": 368, "country": "Cyprus", "league": "First Division"},
    {"index_start": 369, "index_end": 377, "country": "Hungary", "league": "NB I"},
    {"index_start": 378, "index_end": 381, "country": "Ukraine", "league": "Top League"},
    {"index_start": 382, "index_end": 385, "country": "Luxembourg", "league": "National Division"},
    {"index_start": 386, "index_end": 397, "country": "Republic of Ireland", "league": "Premier Division"},
    {"index_start": 398, "index_end": 404, "country": "Northern Ireland", "league": "Premier Division"},
    {"index_start": 405, "index_end": 406, "country": "Iceland", "league": "Urvalsdeild"},
    {"index_start": 407, "index_end": 411, "country": "Finland", "league": "Veikkausliiga"},
    {"index_start": 412, "index_end": 424, "country": "Wales", "league": "League of Wales"},
    {"index_start": 425, "index_end": 429, "country": "Israel", "league": "Premier League"},
    {"index_start": 430, "index_end": 432, "country": "Malta", "league": "Premier League"},
    {"index_start": 433, "index_end": 434, "country": "Faroe Islands", "league": "Premier Division"},
    {"index_start": 435, "index_end": 437, "country": "Lithuania", "league": "A Lyga"},
    {"index_start": 438, "index_end": 439, "country": "Albania", "league": "Kategoria Superiore"},
    {"index_start": 440, "index_end": 441, "country": "Georgia", "league": "Umaglesi Liga"},
    {"index_start": 442, "index_end": 442, "country": "Moldova", "league": "National Division"},
    {"index_start": 443, "index_end": 444, "country": "Bolivia", "league": "Liga Profesional"},
    {"index_start": 445, "index_end": 447, "country": "Ecuador", "league": "Serie A"},
    {"index_start": 448, "index_end": 448, "country": "Belarus", "league": "Premier League"},
    {"index_start": 449, "index_end": 451, "country": "Peru", "league": "Primera Division"},
    {"index_start": 452, "index_end": 460, "country": "Brazil", "league": "Campeonato Brasileiro"},
    {"index_start": 461, "index_end": 462, "country": "Uruguay", "league": "Primera Division"},
    {"index_start": 463, "index_end": 464, "country": "Venezuela", "league": "Primera Division"},
    {"index_start": 465, "index_end": 467, "country": "Chile", "league": "Primera Division"},
    {"index_start": 468, "index_end": 470, "country": "Colombia", "league": "Primera A"},
    {"index_start": 471, "index_end": 473, "country": "Paraguay", "league": "Primera Division"},
    {"index_start": 474, "index_end": 495, "country": "England", "league": "Conference"},
    {"index_start": 496, "index_end": 505, "country": "England", "league": "Non-League"},
    {"index_start": 506, "index_end": 507, "country": "Latvia", "league": "Virsliga"},
    {"index_start": 508, "index_end": 508, "country": "Armenia", "league": "Premier League"},
    {"index_start": 509, "index_end": 509, "country": "North Macedonia", "league": "First League"},
    {"index_start": 510, "index_end": 510, "country": "Belarus", "league": "Premier League"},
    {"index_start": 511, "index_end": 511, "country": "Estonia", "league": "Meistriliiga"},
    {"index_start": 512, "index_end": 512, "country": "Azerbaijan", "league": "Top Division"},
    {"index_start": 513, "index_end": 514, "country": "Special", "league": "Selection"},
    {"index_start": 515, "index_end": 530, "country": "Argentina", "league": "Primera Division"},
    {"index_start": 531, "index_end": 531, "country": "Special", "league": "All-Stars"},
    {"index_start": 532, "index_end": 532, "country": "Special", "league": "Free Agents"},
    {"index_start": 533, "index_end": 533, "country": "Special", "league": "Youth Pool"},
]


def get_country_leagues(country: str) -> List[Dict]:
    """Get all leagues for a country.
    
    Args:
        country: Country name (e.g., "England", "Spain")
        
    Returns:
        List of league dictionaries with name, division, team_count, id_start, id_end
    """
    return LEAGUE_STRUCTURE.get(country, [])


def get_all_countries() -> List[str]:
    """Get list of all countries with leagues.
    
    Returns:
        Sorted list of country names
    """
    return sorted(LEAGUE_STRUCTURE.keys())


def get_team_league(team_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Get the country and league name for a team ID.
    
    Args:
        team_id: Team identifier
        
    Returns:
        Tuple of (country_name, league_name) or (None, None) if not found
    """
    for country, leagues in LEAGUE_STRUCTURE.items():
        for league in leagues:
            if league["id_start"] <= team_id <= league["id_end"]:
                return country, league["name"]
    return None, None


def get_team_league_by_sequence(team_index: int) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort league lookup by the recovered team stream order.

    This is a fallback for cases where the parsed `team_id` is zero or clearly
    unreliable. It should not replace `get_team_league()` when a valid team-ID
    range match exists.
    """
    try:
        index_value = int(team_index)
    except Exception:
        return None, None

    for block in TEAM_SEQUENCE_FALLBACKS:
        start = int(block["index_start"])
        end = int(block["index_end"])
        if start <= index_value <= end:
            return str(block["country"]), str(block["league"])
    return None, None


def get_league_info(country: str, league_name: str) -> Optional[Dict]:
    """Get detailed information about a specific league.
    
    Args:
        country: Country name
        league_name: League name
        
    Returns:
        League dictionary or None if not found
    """
    leagues = get_country_leagues(country)
    for league in leagues:
        if league["name"] == league_name:
            return league
    return None


def get_league_teams_count(country: str, league_name: str) -> int:
    """Get the number of teams in a league.
    
    Args:
        country: Country name
        league_name: League name
        
    Returns:
        Number of teams, or 0 if league not found
    """
    info = get_league_info(country, league_name)
    return info["team_count"] if info else 0


def get_league_id_range(country: str, league_name: str) -> Optional[Tuple[int, int]]:
    """Get the team ID range for a league.
    
    Args:
        country: Country name
        league_name: League name
        
    Returns:
        Tuple of (id_start, id_end) or None if not found
    """
    info = get_league_info(country, league_name)
    return (info["id_start"], info["id_end"]) if info else None


def is_english_team(team_id: int) -> bool:
    """Check if a team ID belongs to an English team.
    
    Args:
        team_id: Team identifier
        
    Returns:
        True if team is from England
    """
    country, _ = get_team_league(team_id)
    return country == "England"


def get_division_name(country: str, division: int) -> Optional[str]:
    """Get the league name for a specific division in a country.
    
    Args:
        country: Country name
        division: Division number (1 = top tier)
        
    Returns:
        League name or None if not found
    """
    leagues = get_country_leagues(country)
    for league in leagues:
        if league.get("division") == division:
            return league["name"]
    return None


# English-specific helpers (since England has 4 divisions)
def get_english_division(team_id: int) -> Optional[int]:
    """Get the division number for an English team.
    
    Args:
        team_id: Team identifier
        
    Returns:
        Division number (1-4) or None if not an English team
    """
    if not is_english_team(team_id):
        return None
    
    country, league_name = get_team_league(team_id)
    if country != "England":
        return None
    
    info = get_league_info(country, league_name)
    return info.get("division") if info else None


# Validation helpers
def validate_team_id(team_id: int) -> bool:
    """Check if a team ID is within valid league ranges.
    
    Args:
        team_id: Team identifier
        
    Returns:
        True if team_id is in a valid league range
    """
    country, league = get_team_league(team_id)
    return country is not None and league is not None


def get_next_available_id(country: str, league_name: str) -> Optional[int]:
    """Get the next available team ID in a league (for adding teams).
    
    Args:
        country: Country name
        league_name: League name
        
    Returns:
        Next available ID or None if league is full or not found
    """
    info = get_league_info(country, league_name)
    if not info:
        return None
    
    # This would need actual team data to determine which IDs are in use
    # For now, return the start of the range
    return info["id_start"]
