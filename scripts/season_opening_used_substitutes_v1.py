"""Recover used substitutes from original, club-attributed match events.

Older reports often publish substitutions but no separate bench box. Only the
incoming player, explicit club crest ID and own outgoing player establish a
positive match appearance. Opponent events and outgoing players are not reserves.
"""
from __future__ import annotations
import re
from bs4 import BeautifulSoup, SoupStrainer


def parse(payload, source_club_id, starting_xi):
    soup = BeautifulSoup(payload, 'html.parser', parse_only=SoupStrainer('li'))
    used, unresolved = {}, []
    own_players = {str(id) for id in starting_xi}
    def players(container):
        result = {}
        for a in container.select('a[href]') if container else []:
            m = re.search(r'/spieler/(\d+)(?:/|$)', a['href'])
            name = (a.get('title') or a.get_text(' ', strip=True)).strip()
            if m and name:
                result[m.group(1)] = name
        return result
    for event in soup.select('li'):
        incoming = event.select_one('.sb-aktion-wechsel-ein')
        if incoming is None:
            continue
        clubs = {int(m.group(1)) for a in event.select('.sb-aktion-wappen a[href]')
                 if (m := re.search(r'/verein/(\d+)(?:/|$)', a['href']))}
        if source_club_id not in clubs:
            continue
        entrants = players(incoming)
        outgoing = players(event.select_one('.sb-aktion-wechsel-aus'))
        def issue(reason):
            unresolved.append({'reason': reason, 'incoming_player_ids': entrants,
                               'outgoing_player_ids': outgoing, 'club_ids': sorted(clubs)})
        if clubs != {source_club_id}:
            issue('ambiguous-substitution-club-crest')
            continue
        if len(outgoing) != 1 or len(entrants) != 1 or not set(outgoing) <= own_players:
            issue('substitution-pair-does-not-match-own-published-XI-or-earlier-substitute')
            continue
        id, name = next(iter(entrants.items()))
        if id in own_players:
            issue('incoming-substitute-already-in-own-starting-or-used-lineup')
            continue
        used[id] = name
        own_players.add(id)
    return {'used_substitutes': used, 'unresolved_events': unresolved}
