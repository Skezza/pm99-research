"""Resolve duplicate capture catalogues only when original replays are identical.

An empty old parsed catalogue and its later populated version are not two
different fixtures. Reparse every candidate's actual original schedule, match
and numerical biographies; never choose between contradictory originals.
"""
import copy


def select(captures, replay_one):
    if not captures:
        raise ValueError('no original opening capture')
    identity_keys = ('source_path', 'country_catalog', 'competition_catalog',
                     'competition_name', 'club_name')
    identity = tuple(captures[0][key] for key in identity_keys)
    if any(tuple(c[key] for key in identity_keys) != identity for c in captures):
        raise ValueError('capture catalogues do not identify the same exact team and competition')
    replays = []
    for capture in captures:
        actual = replay_one(capture)
        if (actual.get('status') != 'original-first-fixture-reparsed'
                or len(actual.get('identity_bridges', {}).get('starting_xi', [])) != 11):
            raise ValueError('capture lacks a complete independently replayed original XI')
        core = copy.deepcopy(actual)
        core.pop('source_capture', None)
        replays.append((capture, actual, core))
    if any(row[2] != replays[0][2] for row in replays[1:]):
        raise ValueError('original fixture/player/biography/raw-source replays conflict')
    chosen = min(replays, key=lambda row: (-len(row[0]['players']), row[0]['source_sha256']))
    proof = dict(schema='pm99-equivalent-replayed-original-opening-captures-v1',
        original_replays_identical_except_catalogue_binding=True,
        selected_capture_sha256=chosen[0]['source_sha256'],
        catalogue_versions=[dict(source_sha256=c['source_sha256'], players=len(c['players']))
                            for c in sorted(captures, key=lambda c: c['source_sha256'])],
        native_writes=0, identity_DOB_gaps_not_waived=True,
        historical_roster_or_native_allocation_approved=False)
    return chosen[0], chosen[1], proof
