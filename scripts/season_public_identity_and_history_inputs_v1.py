"""Independently replay optional immutable public identity/history inputs."""
import json
from scripts import season_release_registry_v1 as registry


def binding(path, policy):
    return {'path': registry.relative_workspace_path(path),
            'sha256': registry.sha256_file(path), 'policy': policy}


def merge_bound(people, events, bindings):
    report = {}
    for key in ('published_person_supplement', 'published_transfer_supplement'):
        item = bindings.get(key)
        if item is None:
            continue
        path = registry.ROOT / item['path']
        if registry.sha256_file(path) != item['sha256']:
            raise ValueError('immutable public source supplement changed: ' + key)
        document = json.loads(path.read_text())
        if key == 'published_person_supplement':
            from scripts import season_published_person_identity_v1 as source
            if item['policy'] != source.POLICY:
                raise ValueError('unsupported original person input policy')
            people, result = source.merge(people, document)
        else:
            from scripts import season_published_transfer_history_v1 as source
            if item['policy'] != source.POLICY:
                raise ValueError('unsupported original transfer input policy')
            events, result = source.merge(events, document)
        report[key] = {'accepted_player_count': len(result['accepted_player_ids']),
                       'refused': result['refused']}
    return people, events, report
