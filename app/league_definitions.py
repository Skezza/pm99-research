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