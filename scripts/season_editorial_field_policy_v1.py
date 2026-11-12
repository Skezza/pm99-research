"""Which workbook cells the generic amendment build can carry into a game.

Pure (no heavy imports) so the local workbook and the build route share one
answer. Anything not listed is refused with an actionable reason instead of
being saved as if it reached the game.
"""
import re

RATING_KEYS = ('speed', 'stamina', 'aggression', 'quality', 'heading', 'dribbling',
               'passing', 'shooting', 'tackling', 'handling')
PLAYER_FACT_FIELDS = ('primary_position', 'nationality', 'birth_date', 'shirt_number', 'height_cm', 'weight_kg')

_PLAYER_RATING = re.compile(r'^/players/([0-9]+)/ratings/values/([a-z_]+)$')
_PLAYER_FACT = re.compile(r'^/players/([0-9]+)/facts/([a-z_]+)$')
_MANAGER_NAME = re.compile(r'^/managers/([0-9]+)/name$')

UNSUPPORTED_REASONS = (
    (re.compile(r'^/players/[0-9]+/name$'),
     'player name edits are not carried into the game yet: the generic route has no proven native name-capacity writer'),
    (re.compile(r'^/clubs/[0-9]+/manager_id$'),
     'manager-to-club links are relational (EQ links, lineups, rosters) and are not supported by the generic route'),
    (re.compile(r'^/clubs/[0-9]+/'),
     'club label edits (name, full name, division, ground) are not carried into the game by the generic route'),
    (re.compile(r'^/managers/[0-9]+/'),
     'only the manager name is carried into the game'),
)


def classify(pointer):
    """Return (kind, index, field) for a supported pointer, else raise ValueError."""
    if not isinstance(pointer, str):
        raise ValueError('amendment pointer must be a string')
    match = _PLAYER_RATING.match(pointer)
    if match:
        if match.group(2) not in RATING_KEYS:
            raise ValueError(f'unsupported rating key {match.group(2)!r}; supported: {", ".join(RATING_KEYS)}')
        return 'player-rating', int(match.group(1)), match.group(2)
    match = _PLAYER_FACT.match(pointer)
    if match:
        if match.group(2) not in PLAYER_FACT_FIELDS:
            raise ValueError(f'unsupported player fact {match.group(2)!r}; supported: {", ".join(PLAYER_FACT_FIELDS)}')
        return 'player-fact', int(match.group(1)), match.group(2)
    match = _MANAGER_NAME.match(pointer)
    if match:
        return 'manager-name', int(match.group(1)), 'name'
    for pattern, reason in UNSUPPORTED_REASONS:
        if pattern.match(pointer):
            raise ValueError(f'{reason} ({pointer})')
    raise ValueError(f'this field cannot be carried into the game by the generic amendment build ({pointer})')


def supported(pointer):
    try:
        classify(pointer)
    except ValueError:
        return False
    return True


def reason_unsupported(pointer):
    try:
        classify(pointer)
    except ValueError as exc:
        return str(exc)
    return None


# --- record-specific capability (recipe-level; native agreement is still proven at build time) ------------

def _is_policy(value):
    return isinstance(value, dict)


def record_reason(kind, row, field, new_value=None):
    """Why *this* edit on *this* recipe record cannot reach the game, or None.

    Only the edited field (and fields it depends on) are gated: untouched unknown/preserved facts of the same
    person do not block an edit of a different field. ``new_value`` is optional (cell capability checks omit it).
    """
    if not isinstance(row, dict):
        return 'record not found in the recipe'
    if kind == 'manager-name':
        if row.get('policy') != 'write' or not isinstance(row.get('native_names'), dict):
            return 'this manager is a preserved/foreign native record; only written managers can be renamed'
        return None
    if row.get('policy') == 'preserve-existing-mode1':
        return 'this whole player record is preserved (mode-1); none of its fields are written'
    facts = row.get('facts') if isinstance(row.get('facts'), dict) else {}
    if kind == 'player-rating':
        values = (row.get('ratings') or {}).get('values')
        if not isinstance(values, dict) or isinstance(values.get(field), (dict, bool)) or not isinstance(values.get(field), int):
            return f'{field} is not a stored whole-number rating for this player'
        return None
    if kind != 'player-fact':
        return 'unsupported field kind'
    if _is_policy(facts.get(field)) or facts.get(field) is None:
        return f'{field} is an unknown/preserved value for this player; nothing to edit safely'
    if field == 'primary_position':
        if row.get('carrier_family') != 'dd6361':
            return 'broad position is writable only for full (dd6361) player records'
        if facts.get('primary_position') not in ('D', 'M', 'F'):
            return 'goalkeeper conversions are not supported; only outfield D/M/F positions can change'
        if not isinstance(facts.get('fine_roles'), list) or not facts['fine_roles']:
            return 'this player\'s fine roles are preserved/unknown, so a position change cannot be kept coherent'
        if new_value is not None and new_value not in ('D', 'M', 'F'):
            return 'goalkeeper conversions are not supported; choose D, M or F'
    elif field == 'shirt_number':
        if row.get('carrier_family') != 'dd6361':
            return 'shirt numbers are writable only for full (dd6361) player records'
    return None
