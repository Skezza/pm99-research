"""Prove an authored duplicate club hidden by its wrong native display label.

No majority votes, inferred new clubs or native writes. The complete authored
XI must unanimously bind the exact original source selector and independently
reparsed first fixture. This only admits a source-only retirement proposal;
the retained club still needs a separate label/manager/roster correction.
"""
from scripts import season_release_registry_v1 as registry, season_pipeline_v2 as pipeline
from scripts import season_historical_club_label_review_v1 as source


def verified_retained(release, old, audit_path):
    registry.relative_workspace_path(audit_path)
    audit = pipeline.read_json_file(audit_path)
    binding = audit['bindings']
    if (audit.get('schema_version') != source.SCHEMA or audit.get('season') != release.season
            or tuple(binding.get(k) for k in ('release_id','package_sha256','eq_sha256','ent_sha256')) != (
                release.release_id,registry.sha256_file(release.package_path),
                registry.sha256_file(release.game_path/'DBDAT/EQ98030.FDI'),
                registry.sha256_file(release.game_path/'DBDAT/ENT98030.FDI'))):
        raise ValueError('retained duplicate source review has a different immutable baseline')
    package = pipeline.read_json_file(release.package_path)
    rows = [r for r in audit['clubs'] if r.get('status')=='source-supported-club-label-mismatch'
            and r.get('after')==old['name'] and r['carrier_id']!=old['carrier_id']]
    if len(rows)!=1:
        raise ValueError('one exact positively authored retained duplicate required')
    row = rows[0]
    clubs = [c for c in package['clubs'] if c['id']==row['club_id'] and c['carrier_id']==row['carrier_id']]
    if len(clubs)!=1 or clubs[0]['name']!=row['before']:
        raise ValueError('retained authored club preimage differs')
    retained=clubs[0]; aid='opening-squad-preallocation-'+release.season
    descriptors=[a for a in package['artifacts'] if a['id']==aid]
    pre_path=registry.ROOT/binding['source_row_path']
    capture_path=registry.ROOT/binding['original_capture_path']
    if (len(descriptors)!=1 or registry.sha256_file(pre_path)!=binding['source_row_sha256']
            or descriptors[0]['sha256']!=binding['source_row_sha256']
            or registry.sha256_file(capture_path)!=binding['original_capture_sha256']):
        raise ValueError('retained original authored source/capture changed')
    pre=pipeline.read_json_file(pre_path); index,sources=source.indexed_claims(pre)
    players=[p for p in package['players'] if p['club_id']==retained['id']]
    authored, reason=source.unanimous_claim(retained,players,aid,index,sources)
    if reason or not authored or authored['selector']!=row['source_selector'] or authored['selector']['club_name']!=old['name']:
        raise ValueError('complete retained authored cohort does not unanimously identify the original club')
    capture=pipeline.read_json_file(capture_path)
    matches=[c for c in capture['clubs'] if source.selector_key(c['source_selector'])[:3]==source.selector_key(authored['selector'])[:3]]
    if len(matches)!=1:
        raise ValueError('retained club lacks one exact original first fixture')
    original=source.opening.verify_opening(matches[0],capture,capture_path.parent/'cache')
    xi={str(p['opening_source_player_id']) for p in authored['players'] if isinstance(p.get('opening_xi_order'),int)}
    if (original!=row['evidence'] or set(original['starting_xi'])!=xi
            or original['date']!=authored['opening_fixture_date']):
        raise ValueError('retained authored first XI does not independently reproduce')
    return retained, dict(path=registry.relative_workspace_path(audit_path),
        sha256=registry.sha256_file(audit_path),schema=source.SCHEMA,
        approval_scope='source-only duplicate identity; retained native label/manager/roster remain pending')
