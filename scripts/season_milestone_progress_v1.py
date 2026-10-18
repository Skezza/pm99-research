#!/usr/bin/env python3
"""Frozen, deterministic duplicate-review measurements; never game mutations.

An absent audit candidate is NOT a verified repair. This initial adapter tracks
queue movement and recurrence, not historical completion or live game validity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SEASONS = tuple(f'{y}-{str(y + 1)[-2:]}' for y in range(2000, 2026))
AUDIT_SCHEMA = 'pm99-published-person-and-full-source-name-dob-audit-v1'
BASELINE_SCHEMA = 'pm99-frozen-duplicate-review-baseline-v1'
REPORT_SCHEMA = 'pm99-frozen-duplicate-review-progress-v1'


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pairs(rows):
    result = {}
    for key, value in rows:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def read(path, expected_sha=None):
    raw = path.read_bytes()
    if expected_sha is not None and hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('bound evidence hash changed while reading')
    return json.loads(raw, object_pairs_hook=pairs)


def binding(path):
    path = path.resolve()
    try:
        name = path.relative_to(ROOT).as_posix()
    except ValueError:
        name = str(path)
    return {'path': name, 'sha256': digest(path)}


def bound(reference):
    if set(reference) != {'path', 'sha256'}:
        raise ValueError('invalid evidence binding')
    path = Path(reference['path'])
    path = path if path.is_absolute() else ROOT / path
    if digest(path) != reference['sha256']:
        raise ValueError('bound evidence hash changed')
    return path


def count(value):
    if type(value) is not int or value < 0:
        raise ValueError('invalid audit count')
    return value


def audit(path, expected_sha=None):
    document = read(path, expected_sha)
    if document.get('schema_version') != AUDIT_SCHEMA:
        raise ValueError('unsupported audit schema')
    contract = {key: document[key] for key in
                ('schema_version', 'policy', 'snapshot', 'public_person_supplement')}
    if (not isinstance(contract['policy'], str) or not contract['policy']
            or not isinstance(contract['snapshot'], dict)
            or not isinstance(contract['public_person_supplement'], dict)):
        raise ValueError('invalid audit contract')
    for key in ('path', 'pinned_receipt_path', 'project_url', 'version'):
        if not isinstance(contract['snapshot'].get(key), str) or not contract['snapshot'][key]:
            raise ValueError('incomplete snapshot binding')
    for key in ('sha256', 'pinned_receipt_sha256'):
        if not re.fullmatch('[0-9a-f]{64}', contract['snapshot'].get(key, '')):
            raise ValueError('invalid snapshot hash')
    supplement = contract['public_person_supplement']
    if (not all(isinstance(supplement.get(k), str) and supplement[k] for k in ('path', 'policy'))
            or not re.fullmatch('[0-9a-f]{64}', supplement.get('sha256', ''))
            or not isinstance(supplement.get('merge_refusals'), list)):
        raise ValueError('incomplete supplement binding')
    items, season_ids = {}, set()
    for section in document['seasons']:
        season = section['season']
        if season not in SEASONS or season in season_ids:
            raise ValueError('unexpected or repeated season')
        season_ids.add(season)
        if (not isinstance(section['release_id'], str) or not section['release_id']
                or not re.fullmatch('[0-9a-f]{64}', section['package_sha256'])):
            raise ValueError('missing release/package binding')
        layers = section['layers']
        if not isinstance(layers, list) or not layers:
            raise ValueError('missing recipe layer bindings')
        labels, paths = set(), set()
        for layer in layers:
            label, name = layer['layer'], layer['path']
            if (not isinstance(label, str) or not label or label in labels
                    or not isinstance(name, str) or not name or name in paths
                    or not re.fullmatch('[0-9a-f]{64}', layer['sha256'])):
                raise ValueError('invalid or repeated layer binding')
            labels.add(label); paths.add(name)
        main = [layer for layer in layers if layer['layer'] == 'main']
        if len(main) != 1 or main[0]['sha256'] != section['package_sha256']:
            raise ValueError('main layer differs from recipe hash')
        carriers = set()
        candidates = section['candidates']
        if count(section['cross_club_candidate_groups']) != len(candidates):
            raise ValueError('season count differs from candidates')
        for candidate in candidates:
            identity = candidate['identity']
            if (not isinstance(identity, list) or not identity
                    or identity[0] not in ('published-person', 'full-source-name-dob-candidate')):
                raise ValueError('unsupported identity namespace')
            if identity[0] == 'published-person':
                if len(identity) != 2 or not isinstance(identity[1], (str, int)) or type(identity[1]) is bool:
                    raise ValueError('invalid published identity')
                if ((type(identity[1]) is int and identity[1] <= 0)
                        or (isinstance(identity[1], str) and
                            (not identity[1] or identity[1].strip() != identity[1]))):
                    raise ValueError('empty or invalid published identity')
            elif len(identity) != 3 or not all(isinstance(v, str) and v for v in identity):
                raise ValueError('invalid name/DOB candidate identity')
            item_id = hashlib.sha256(canonical([season, identity])).hexdigest()
            if item_id in items:
                raise ValueError('duplicate candidate identity')
            members = candidate['players']
            clubs = set()
            for member in members:
                carrier = member['carrier_id']
                if type(carrier) is not int or carrier <= 0 or carrier in carriers:
                    raise ValueError('repeated or invalid native carrier')
                carriers.add(carrier)
                if not all(isinstance(member[k], str) and member[k] for k in
                           ('club_id', 'player_id', 'source_name')):
                    raise ValueError('invalid candidate member')
                clubs.add(member['club_id'])
            if len(clubs) < 2:
                raise ValueError('candidate does not span distinct club IDs')
            items[item_id] = {'season': season, 'identity': identity,
                             'members': sorted(members, key=canonical)}
    if season_ids != set(SEASONS):
        raise ValueError('audit must cover exactly all 26 seasons')
    if count(document['cross_club_candidate_groups']) != len(items):
        raise ValueError('total count differs from candidates')
    return contract, items


def exclusive_write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(canonical(document))


def freeze(audit_path, output):
    reference = binding(audit_path)
    contract, items = audit(audit_path, reference['sha256'])
    result = {'schema_version': BASELINE_SCHEMA, 'audit': reference,
              'measurement_code_sha256': digest(Path(__file__)),
              'contract': contract, 'items': items, 'denominator': len(items),
              'scope': 'cross-club audit candidate groups, not confirmed errors'}
    exclusive_write(output, result)
    return result


def baseline(path, expected_sha):
    if digest(path) != expected_sha:
        raise ValueError('baseline hash differs from external pin')
    result = read(path, expected_sha)
    if (result['schema_version'] != BASELINE_SCHEMA
            or result['measurement_code_sha256'] != digest(Path(__file__))):
        raise ValueError('measurement implementation changed; explicit new baseline required')
    contract, items = audit(bound(result['audit']), result['audit']['sha256'])
    if (contract != result['contract'] or items != result['items']
            or len(items) != result['denominator']):
        raise ValueError('baseline differs from its bound audit')
    return result


def measurement(base, base_ref, audit_path, previous_ref=None, ancestry=()):
    current_ref = binding(audit_path)
    contract, current = audit(audit_path, current_ref['sha256'])
    if contract != base['contract']:
        raise ValueError('audit rules or source snapshot/supplement changed')
    previous = None
    if previous_ref is not None:
        if len(ancestry) >= 256 or previous_ref['sha256'] in ancestry:
            raise ValueError('cyclic or excessively long report history')
        previous_path = bound(previous_ref)
        previous = read(previous_path, previous_ref['sha256'])
        if previous['schema_version'] != REPORT_SCHEMA or previous['baseline'] != base_ref:
            raise ValueError('previous report belongs to another baseline')
        reproduced = measurement(base, base_ref, bound(previous['audit']),
                                 previous['previous_report'], ancestry + (previous_ref['sha256'],))
        if previous != reproduced:
            raise ValueError('previous report does not independently reproduce')
    known = dict(base['items'])
    if previous:
        known.update(previous['discovered_items'])
    introduced = sorted(set(current) - set(known))
    discovered = dict(previous['discovered_items']) if previous else {}
    discovered.update({key: current[key] for key in introduced})
    known.update(discovered)
    previous_absent = set(previous['absent_item_ids']) if previous else set()
    present, absent = set(current), set(known) - set(current)
    reappeared = sorted(previous_absent & present)
    member_changes = []
    # Compare consecutive audits, not a mutable hand-authored status list.
    earlier = audit(bound(previous['audit']), previous['audit']['sha256'])[1] if previous else base['items']
    for key in sorted(set(earlier) & present):
        old = {canonical(m) for m in earlier[key]['members']}
        new = {canonical(m) for m in current[key]['members']}
        if old != new:
            member_changes.append({'item_id': key, 'members_added': len(new-old),
                                   'members_removed': len(old-new)})
    base_ids = set(base['items'])
    base_absent = sorted(base_ids - present)
    bound(current_ref)  # refuse an audit modified while the history was checked
    return {
        'schema_version': REPORT_SCHEMA, 'baseline': base_ref, 'audit': current_ref,
        'previous_report': previous_ref, 'scope': base['scope'],
        'evidence_mode': 'frozen-audit-comparison; NOT live-game or source-truth verification',
        'history_mode': ('verified-supplied-checkpoint-chain' if previous else
                         'initial-comparison-no-previous-report; recurrence not assessed'),
        'baseline_total': base['denominator'], 'baseline_present': len(base_ids & present),
        'baseline_absent_awaiting_verification': len(base_absent),
        'baseline_absent_item_ids': base_absent, 'absent_item_ids': sorted(absent),
        'current_candidate_count': len(current),
        'candidate_reappeared_count': len(reappeared) if previous else None,
        'candidate_reappeared_item_ids': reappeared,
        'new_discovery_count': len(introduced), 'new_discovery_item_ids': introduced,
        'discovered_total': len(discovered), 'discovered_items': discovered,
        'discovered_still_present': len(set(discovered) & present),
        'membership_changes': member_changes,
        'verified_completed_count': 0, 'verified_completion_percent': None,
        'confirmed_error_fix_percent': None, 'proven_fix_regression_count': None,
        'completion_limit': 'No verified-disposition adapter: disappearance never means repaired.',
        'queue_net_reduction_percent': (round(100 * (base['denominator']-len(current)) /
                                            base['denominator'], 3) if base['denominator'] else None),
    }


def report(baseline_path, expected_sha, audit_path, output, previous_path=None, previous_sha=None):
    if (previous_path is None) != (previous_sha is None):
        raise ValueError('previous report needs both path and external SHA256 pin')
    previous_ref = binding(previous_path) if previous_path else None
    if previous_ref and previous_ref['sha256'] != previous_sha:
        raise ValueError('previous report hash differs from external pin')
    base = baseline(baseline_path, expected_sha)
    base_ref = binding(baseline_path)
    if base_ref['sha256'] != expected_sha:
        raise ValueError('baseline changed during validation')
    result = measurement(base, base_ref, audit_path, previous_ref)
    bound(base_ref)
    bound(base['audit'])
    if base['measurement_code_sha256'] != digest(Path(__file__)):
        raise ValueError('measurement implementation changed during validation')
    exclusive_write(output, result)
    return result


def summary(result):
    return {key: result[key] for key in ('baseline_total', 'baseline_present',
        'baseline_absent_awaiting_verification', 'current_candidate_count',
        'new_discovery_count', 'discovered_total', 'candidate_reappeared_count',
        'verified_completion_percent', 'queue_net_reduction_percent')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('freeze')
    init.add_argument('--audit', type=Path, required=True)
    init.add_argument('--output', type=Path, required=True)
    run = commands.add_parser('report')
    run.add_argument('--baseline', type=Path, required=True)
    run.add_argument('--baseline-sha256', required=True)
    run.add_argument('--audit', type=Path, required=True)
    run.add_argument('--previous', type=Path)
    run.add_argument('--previous-sha256')
    run.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'freeze':
            value = freeze(args.audit, args.output)
            print(json.dumps({'baseline_total': value['denominator'], 'baseline': binding(args.output)}))
        else:
            print(json.dumps(summary(report(args.baseline, args.baseline_sha256, args.audit,
                                            args.output, args.previous, args.previous_sha256))))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f'Progress measurement refused: {exc}\n')
