"""Require actual substitution sprites, not shared penalty-event CSS labels.

Transfermarkt uses wechsel-ein/aus spans for penalties too. Both explicit
entry/exit sprites distinguish substitutions before the V1 ownership checks.
Keep markerless ambiguous events unresolved; positively identified penalty
events are not substitutions and cannot supply or dispute reserve membership.
"""
import re
from bs4 import BeautifulSoup, SoupStrainer
from scripts import season_opening_used_substitutes_v1 as original

POLICY = 'explicit-entry-exit-sprites-not-penalty-labels-v2'


def parse(payload, source_club_id, starting_xi):
    soup = BeautifulSoup(payload, 'html.parser', parse_only=SoupStrainer('li'))
    accepted, ignored, ambiguous = [], [], []
    for event in soup.select('li'):
        incoming = event.select_one('.sb-aktion-wechsel-ein')
        if incoming is None:
            continue
        outgoing = event.select_one('.sb-aktion-wechsel-aus')
        if incoming.select_one('.sb-ein') and outgoing and outgoing.select_one('.sb-aus'):
            accepted.append(str(event))
            continue
        # A club badge in the score cell plus the opposing player portrait is
        # the published penalty-event layout. Mere free text is not authority.
        penalty_score = event.select_one('.sb-aktion-spielstand a[href*="/verein/"]')
        if penalty_score is not None and re.search(r'\bPenalty\b', incoming.get_text(' ', strip=True)):
            ignored.append(str(event))
        else:
            ambiguous.append(str(event))
    result = original.parse(''.join(accepted).encode(), source_club_id, starting_xi)
    # Markerless events never create positive appearances, including those
    # V1 would accept. Retain all their player IDs to protect absent claims.
    if ambiguous:
        for event in ambiguous:
            raw = original.parse(event.encode(), source_club_id, starting_xi)
            if raw['unresolved_events']:
                result['unresolved_events'].extend(raw['unresolved_events'])
            elif raw['used_substitutes']:
                node = BeautifulSoup(event, 'html.parser').select_one('.sb-aktion-wechsel-aus')
                outgoing_ids = {m.group(1): (a.get('title') or a.get_text(' ', strip=True)).strip()
                    for a in node.select('a[href]') if (m := re.search(r'/spieler/(\d+)(?:/|$)', a['href']))} if node else {}
                result['unresolved_events'].append({
                    'reason': 'entry-exit-substitution-sprites-missing',
                    'incoming_player_ids': raw['used_substitutes'],
                    'outgoing_player_ids': outgoing_ids, 'club_ids': [source_club_id]})
    result['ignored_penalty_events'] = len(ignored)
    return result
