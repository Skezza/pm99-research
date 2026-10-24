#!/usr/bin/env python3
"""Bounded duplicate-person replacements through the established native API.

Unrelated people/records and all club/manager/tactics declarations stay exact.
Missing secondary facts are explicit; an old person's face is never inherited.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

from scripts import season_duplicate_ownership_plan_v1 as planner
from scripts import season_editorial_ratings_v1 as ratings
from scripts import season_editorial_rating_input_builder_v1 as rating_input
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_package_compiler_v2 as compiler
from scripts import season_package_v2 as package_v2
from scripts import season_release_registry_v1 as registry
from scripts.materialise_native_no_photo_v2 import _active_offsets_for_players
from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import rewrite_indexed_native_roles


def plan_filename(plan):
    digest = hashlib.sha256(package_v2.canonical_json_bytes(plan)).hexdigest()
    return 'ownership-plan-' + digest[:12] + '.json'


def verify_plan(release, plan):
    from scripts import season_frozen_fixture_reserve_v2 as public_fixture
    if plan.get('schema_version') == public_fixture.SCHEMA:
        public_fixture.verify_plan(release, plan)
        return
    from scripts import season_frozen_fixture_reserve_v1 as frozen_fixture
    if plan.get('schema_version') == frozen_fixture.SCHEMA:
        frozen_fixture.verify_plan(release, plan)
        return
    from scripts import season_shtanyuk_2002_coupled_alias_v1 as coupled_alias
    if plan.get('schema_version') == coupled_alias.SCHEMA:
        coupled_alias.verify_plan(release, plan)
        return
    from scripts import season_stoke_original_alias_reserve_v1 as original_alias
    if plan.get('schema_version') == original_alias.SCHEMA:
        original_alias.verify_plan(release, plan)
        return
    from scripts import season_cross_club_reserve_repair_v1 as cross_club
    if plan.get('schema_version') == cross_club.SCHEMA:
        cross_club.verify_plan(release, plan)
        return
    from scripts import season_within_club_reserve_repair_v1 as within_club
    if plan.get('schema_version') == within_club.SCHEMA:
        within_club.verify_plan(release, plan)
        return
    if (plan['schema_version'], plan['season'], plan['release_id'], plan['package_sha256'], plan['jug_sha256']) != (
            planner.SCHEMA, release.season, release.release_id, registry.sha256_file(release.package_path),
            registry.sha256_file(release.game_path / 'DBDAT/JUG98030.FDI')):
        raise ValueError('ownership plan is stale')
    bindings = plan['bindings']
    from scripts import season_published_display_names_v1 as display_names
    display_names.verify_plan(plan)
    from scripts import season_published_family_component_v1 as family_components
    family_components.verify_plan(plan)
    from scripts import season_same_carrier_name_capacity_v1 as name_capacity
    name_capacity.validate_binding(plan)
    from scripts import season_duplicate_english_overlay_v1 as english_overlay
    english_overlay.validate_binding(release, plan)
    from scripts import season_dated_reserve_owner_v1 as annual_owners
    annual_owners.validate_binding(plan)
    from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
    soccerbase.validate_binding(plan)
    for path_key, hash_key in [('opening_path', 'opening_sha256'), ('review_path', 'review_sha256')]:
        if registry.sha256_file(registry.ROOT / bindings[path_key]) != bindings[hash_key]:
            raise ValueError('ownership review input changed')
    for capture in bindings['captures']:
        if registry.sha256_file(registry.ROOT / capture['path']) != capture['sha256']:
            raise ValueError('ownership original capture changed')
    if registry.sha256_file(registry.ROOT / bindings['snapshot']['path']) != bindings['snapshot']['sha256']:
        raise ValueError('ownership transfer snapshot changed')
    if bindings.get('supplemental_opening'):
        extra = bindings['supplemental_opening']
        if registry.sha256_file(registry.ROOT / extra['path']) != extra['sha256']:
            raise ValueError('supplemental opening evidence changed')
    from scripts import season_common_date_ownership_v1 as common_date
    common_date.verify_plan_claims(release, plan)
    checked = {}
    clubs_for_roles = None
    for row in plan['updates']:
        if row['before']['facts'].get('primary_position') != row['replacement']['source_player']['position']:
            from scripts import season_sourced_reserve_role_policy_v1 as reserve_roles
            if clubs_for_roles is None:
                clubs_for_roles = {c['id']: c for _, package, _ in planner.package_layers(release) for c in package['clubs']}
            reserve_roles.validate(plan, row, clubs_for_roles[row['club_id']])
        eligibility = row['replacement'].get('opening_eligibility')
        if eligibility is not None:
            opening = row['replacement_opening_evidence']
            if (eligibility['date'], eligibility['source_club_id']) != (opening['date'], opening['source_club_id']):
                raise ValueError('replacement eligibility belongs to another opening date or club')
            if eligibility['method'] == 'positive-first-fixture-substitute-id':
                if str(row['replacement']['source_person']['source_player_id']) not in opening['substitutes']:
                    raise ValueError('replacement lacks its declared first-fixture substitute evidence')
            elif eligibility['method'] == 'dated-opening-reserve-entry-exit-bracket':
                interval = eligibility['interval']
                if (interval['status'] != 'recorded-entry-and-exit-bracket-fixture' or
                        interval['source_owner_club_id'] != opening['source_club_id'] or
                        not interval['entry']['date'] < opening['date'] < interval['departure']['date'] or
                        interval['entry']['to_club_id'] != interval['departure']['from_club_id']):
                    raise ValueError('replacement lacks consistent dated opening ownership')
            else:
                raise ValueError('unsupported replacement opening eligibility')
        proof = row['replacement']['raw_evidence']
        sources = [{'path': proof['local_path'], 'sha256': proof['source_sha256']}]
        sources += row['owner_evidence']['raw_sources'] + row['replacement_opening_evidence']['raw_sources']
        if row.get('retained_owner_squad_membership') is not None:
            annual = row['retained_owner_squad_membership']['raw_evidence']
            sources.append({'path': annual['local_path'], 'sha256': annual['source_sha256']})
        for source in sources:
            path = registry.ROOT / source['path']
            if path not in checked:
                checked[path] = registry.sha256_file(path)
            if checked[path] != source['sha256']:
                raise ValueError('ownership raw evidence changed')


def updated_package(package, plan, *, selected_layer='main'):
    if selected_layer not in ('main', 'english'):
        raise ValueError('unsupported ownership recipe layer')
    if (selected_layer == 'english' or any(r['layer'] == 'english' for r in plan['updates'])) and not plan.get('allow_english_overlay_replacements'):
        raise ValueError('English ownership overlays require the explicitly bound layer transaction')
    if any(r['layer'] not in ('main', 'english') for r in plan['updates']):
        raise ValueError('unsupported ownership recipe layer')
    result = copy.deepcopy(package)
    # Keep earlier repairs bound to their own evidence, not this new plan.
    plan_digest = hashlib.sha256(package_v2.canonical_json_bytes(plan)).hexdigest()
    artifact_id = 'duplicate-ownership-plan-' + plan['season'] + '-' + plan_digest[:12]
    source_id = 'duplicate-ownership-source-' + plan['season'] + '-' + plan_digest[:12]
    proof = {'artifact_id': artifact_id, 'grade': 'source-receipt'}
    clubs = {c['id']: c for c in package['clubs']}
    by_id = {p['id']: p for p in result['players']}
    for row in plan['updates']:
        if row['layer'] != selected_layer:
            continue
        player = by_id.get(row['player_id'])
        if player != row['before'] or player['carrier_id'] != row['carrier_id']:
            raise ValueError('ownership plan player is not the exact prior recipe row')
        source = row['replacement']['source_player']
        person = row['replacement']['source_person']
        if source['birth_date'] != person['birth_date']:
            raise ValueError('replacement DOB does not match published person')
        from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
        person_id = soccerbase.person_id(person)
        date = row['replacement_opening_evidence']['date']
        strength = rating_input.COUNTRY_STRENGTH.get(roster.club_group(clubs[player['club_id']]), 60)
        hierarchy = {'schema_version': ratings.HIERARCHY_SCHEMA, 'snapshot_date': date,
            'clubs': [{'club_id': player['club_id'], 'strength': strength, 'source_ids': [source_id]}]}
        rating_doc = ratings.build_rating_output({'schema_version': ratings.INPUT_SCHEMA, 'snapshot_date': date,
            'hierarchy': hierarchy, 'players': [{'player_id': player['id'], 'person_id': person_id,
                'club_id': player['club_id'], 'position': source['position'], 'birth_date': source['birth_date'],
                'height_cm': source.get('height_cm'), 'squad_status': 'substitute'}]})
        # A conservative central role is editorial, not an independently
        # verified flank/specialism. Never inherit the displaced person's role.
        facts = {'birth_date': source['birth_date'], 'nationality': source.get('nationality') or 'XXX',
                 'primary_position': source['position'], 'fine_roles': [{'G': 0, 'D': 4, 'M': 9, 'F': 12}[source['position']]],
                 'shirt_number': {'policy': 'preserve-existing-mode1'}}
        fallback = []
        if source['birth_date'] is None:
            # Explicit missing-date policy, never an untyped null or namesake.
            if person.get('identity_policy') in ('original-Monagas2003-person-ID-and-explicit-unpublished-DOB-v1', 'original-Monagas2002-person-ID-and-explicit-unpublished-DOB-v1'):
                from scripts import season_monagas_2003_missing_birthday_v1 as missing
                missing.verify(person)
                reason = 'Original dated opening member and publisher ID confirmed; original birthday explicitly unpublished. Native carrier date retained only as an unsourced fallback, not the player birthday.'
            else:
                from scripts import season_original_fixture_display_v1 as fixture_display
                fixture_display.verify_actor(person)
                reason = 'Original published fixture surname has no known birthday. Native carrier date retained only as an explicit unsourced fallback, not the player birthday.'
            facts['birth_date'] = {'policy': 'preserve-existing-mode1'}
            fallback.append(dict(field='birth_date',method='preserve-existing-mode1',
                proof=proof,value=copy.deepcopy(facts['birth_date']),
                reason=reason))
        for field in ('height_cm', 'weight_kg'):
            value = source.get(field)
            facts[field] = value if isinstance(value, int) else {'policy': 'preserve-existing-mode1'}
        for field in ('nationality', 'shirt_number', 'height_cm', 'weight_kg'):
            if field == 'shirt_number' or isinstance(facts[field], dict) or (field == 'nationality' and not source.get(field)):
                fallback.append({'field': field, 'method': (
                    'deterministic-default' if field == 'nationality' else 'preserve-existing-mode1'),
                    'proof': proof, 'value': facts[field],
                    'reason': 'Opening substitute source lacks a proven writable secondary fact.'})
        generated_ratings = rating_doc['player_ratings'][0]['ratings']
        generated_ratings['provenance'] = {k: generated_ratings['provenance'][k]
            for k in ('method', 'proof_grade', 'source_ids')}
        replacement = {'id': player['id'], 'carrier_id': player['carrier_id'], 'carrier_family': player['carrier_family'],
            'club_id': player['club_id'], 'person_id': person_id, 'name': compiler._pm99_text(source['name'], label='replacement name'),
            'source_name': source['name'], 'facts': facts, 'proof': proof,
            'ratings': generated_ratings, 'fact_fallbacks': sorted(fallback, key=lambda r: r['field'])}
        if row.get('source_bound_replacement_output') is not None:
            from scripts import season_cross_club_reserve_repair_v1 as cross_club
            from scripts import cross_club_replacement_output_v1 as replacement_output
            if plan.get('schema_version') != cross_club.SCHEMA:
                raise ValueError('replacement-specific output requires its independently replayed cross-club source policy')
            replacement = replacement_output.apply_output(replacement, row)
        player.clear()
        player.update(replacement)
        portraits = result['assets']['portraits']
        portraits[:] = [p for p in portraits if p['player_id'] != player['id']]
        portraits.append({'player_id': player['id'], 'status': 'native-no-photo', 'proof': proof,
            'review_reason': 'Displaced identity portrait removed; replacement photograph not sourced.'})
        portraits.sort(key=lambda p: p['player_id'])
    result['artifacts'] = sorted(result['artifacts'] + [{'id': artifact_id, 'kind': 'season-input',
        'sha256': hashlib.sha256(package_v2.canonical_json_bytes(plan)).hexdigest(),
        'media_type': 'application/json', 'relative_path': plan_filename(plan)}], key=lambda a: a['id'])
    result['sources'] = sorted(result['sources'] + [{'id': source_id,
        'title': plan.get('source_title', 'Independently reparsed opening substitutes and dated transfer ownership'),
        'uri': plan['bindings']['snapshot']['project_url'], 'proof_grade': 'source-receipt',
        'evidence_artifact_id': artifact_id}], key=lambda a: a['id'])
    result['proofs'] = sorted(result['proofs'] + [{'id': 'proof-' + artifact_id, 'artifact_id': artifact_id,
        'grade': 'source-receipt', 'covers': plan.get('proof_covers', ['dated-ownership-and-genuine-opening-substitute-replacement'])}], key=lambda a: a['id'])
    package_v2.validate_package(result, strict=False)
    return result


def _compiler_subset(package, changed_ids):
    """Copy only the compiler's two inputs, never the full season evidence.

    This private view is not a publishable recipe. All selected player and
    club objects remain independent of the caller, including nested facts.
    """
    subset = {
        'players': [copy.deepcopy(p) for p in package['players'] if p['id'] in changed_ids],
        'clubs': copy.deepcopy(package['clubs']),
    }
    # Mode-1 does not write startup orders. Restrict this temporary compiler
    # view consistently; the published full roster and EQ remain untouched.
    for club in subset['clubs']:
        club['roster_player_ids'] = [id for id in club['roster_player_ids'] if id in changed_ids]
        for key in ('starting_xi_player_ids', 'substitute_player_ids'):
            if key in club.get('opening', {}):
                club['opening'][key] = [id for id in club['opening'][key] if id in changed_ids]
    return subset


def compile_planned_players(original, package, changed_ids, country_codes, plan):
    """Recover only explicitly bound selected slots before the unchanged writer."""
    from scripts import season_same_carrier_name_capacity_v1 as capacity
    return compile_players(capacity.prepare_source(original,plan),package,changed_ids,country_codes)


def compile_players(original, package, changed_ids, country_codes):
    subset = _compiler_subset(package, changed_ids)
    # dd6361's isolated core compiler leaves fine roles to the separately
    # proven native role writer. This is explicit, not a compiler bypass.
    roles = {p['carrier_id']: p['facts']['fine_roles'] for p in subset['players']}
    for player in subset['players']:
        player['facts']['fine_roles'] = {'policy': 'preserve-existing-mode1'}
    # Full mode-0 compilation would recompute startup order from this filtered
    # roster. Use the isolated parser-backed core lane for both layouts instead;
    # preserve the native team link, shirt byte and startup controls verbatim.
    modes = {c['id']: 1 for c in package['clubs']}
    replacements, handling, *_ = compiler._player_replacements(
        package=subset, jug_data=original, country_codes=country_codes, club_modes=modes)
    patched = compiler._rebuild_indexed(original, IndexedFDIFile.from_bytes(original), replacements)
    # The handling writer's tail assertion is reproduced in memory: no file
    # write can touch an immutable baseline hardlink.
    index = IndexedFDIFile.from_bytes(patched)
    entries = {e.record_id: e for e in index.entries}
    tails = {}
    for row in handling:
        payload = bytearray(entries[row['record_id']].decode_payload(patched))
        values = row['visible_skills']
        if [payload[-16 + i] ^ 0x61 for i in range(len(compiler.SKILLS))] != [values[k] for k in compiler.SKILLS]:
            raise ValueError('replacement Handling tail anchor disagrees')
        payload[-7] = values['handling'] ^ 0x61
        tails[row['record_id']] = bytes(payload)
    if tails:
        patched = compiler._rebuild_indexed(patched, index, tails)
    patched, _ = rewrite_indexed_native_roles(patched, roles)
    old_index, new_index = IndexedFDIFile.from_bytes(original), IndexedFDIFile.from_bytes(patched)
    old_entries = {e.record_id: e for e in old_index.entries}
    new_entries = {e.record_id: e for e in new_index.entries}
    if old_entries.keys() != new_entries.keys():
        raise ValueError('ownership delta changed native fixed carriers')
    for carrier, old_entry in old_entries.items():
        if carrier not in roles and old_entry.decode_payload(original) != new_entries[carrier].decode_payload(patched):
            raise ValueError('ownership delta changed an unrelated player record')
    for player in package['players']:
        if player['id'] not in changed_ids:
            continue
        payload = new_entries[player['carrier_id']].decode_payload(patched)
        old_payload = old_entries[player['carrier_id']].decode_payload(original)
        old_end = roster.native_player(old_payload, player['carrier_id'])['name_end']
        actual = roster.native_player(payload, player['carrier_id'])
        if actual['name'].casefold() != player['name'].casefold() or actual['roles'][0] != player['facts']['fine_roles'][0]:
            raise ValueError('replacement name/fine-role native readback failed')
        end = actual['name_end']
        if (payload[:8] != old_payload[:8] or payload[end:end + 2] != old_payload[old_end:old_end + 2] or
                payload[end + 9:end + 10] != old_payload[old_end + 9:old_end + 10]):
            raise ValueError('replacement changed native club/shirt/startup controls')
        # +10/+11 are the independently established broad-position field
        # pair, not startup controls. The core compiler already audits this
        # two-byte writable range. +9 and the startup/opaque +0/+1 remain
        # exact, along with the self-ID/shirt prefix above. A genuine sourced
        # outfield replacement can legitimately change the position pair.
        birthday = player['facts']['birth_date']
        if birthday == {'policy':'preserve-existing-mode1'}:
            if payload[end+12:end+16] != old_payload[old_end+12:old_end+16]:
                raise ValueError('declared unpublished replacement DOB changed native fallback bytes')
        else:
            born = dt.date.fromisoformat(birthday)
            observed = tuple(payload[end + offset] ^ 0x61 for offset in (12, 13))
            year = int.from_bytes(bytes(b ^ 0x61 for b in payload[end + 14:end + 16]), 'little')
            if observed != (born.day, born.month) or year != born.year:
                raise ValueError('replacement native DOB readback failed')
        facts = player['facts']
        if actual['position'] != facts['primary_position']:
            raise ValueError('replacement native broad position readback failed')
        if facts['nationality'] == {'policy': 'preserve-existing-mode1'}:
            if payload[end + 8] != old_payload[old_end + 8]:
                raise ValueError('declared unpublished replacement nationality changed native fallback byte')
        elif payload[end + 8] ^ 0x61 != compiler._country_code(facts['nationality'], dict(country_codes)):
            raise ValueError('replacement native nationality readback failed')
        for field, offset in [('height_cm', 16), ('weight_kg', 17)]:
            if isinstance(facts[field], int) and payload[end + offset] ^ 0x61 != facts[field]:
                raise ValueError('replacement native physical fact readback failed')
        if player['carrier_family'] == 'dd6360':
            native = compiler._read_native_dd6360_fields(payload, end)
            skills, handling = native['skills'], native['handling']
        else:
            skills, handling = [b ^ 0x61 for b in payload[-16:-7]], payload[-7] ^ 0x61
        ratings_expected = player['ratings']['values']
        if skills != [ratings_expected[field] for field in compiler.SKILLS] or handling != ratings_expected['handling']:
            raise ValueError('replacement native ten-rating readback failed')
    return patched


def fit_display_names(original, package, plan):
    """Prefer a full name, then a published surname alias; never old identity."""
    if plan.get('allow_same_carrier_name_capacity'):
        from scripts import season_same_carrier_name_capacity_v1 as capacity
        original=capacity.prepare_source(original,plan)
    index = IndexedFDIFile.from_bytes(original)
    entries = {e.record_id: e for e in index.entries}
    players = {p['id']: p for p in package['players']}
    aliases = []
    for row in plan['updates']:
        player = players[row['player_id']]
        raw = entries[row['carrier_id']].decode_payload(original)
        current = compiler._player_name(raw, record_id=row['carrier_id'])
        person = row['replacement']['source_person']
        given = person.get('given_name') or ''
        family = person.get('family_name') or ''
        candidates = [(player['name'], 'full-sourced-name')]
        if family:
            surname = compiler._pm99_text(family, label='published surname')
            if given:
                candidates.append((compiler._pm99_text(given[0], label='published initial') + '. ' + surname,
                                   'published-given-initial-and-full-surname'))
            candidates.append((surname, 'published-full-surname'))
        if row.get('published_display_names') is not None:
            from scripts import season_published_display_names_v1 as display_names
            for alias in display_names.verify(row['published_display_names'], person):
                candidates.append((compiler._pm99_text(alias['name'], label='explicit published display name'),
                                   'original-explicit-' + alias['field']))
        if row.get('published_family_component') is not None:
            from scripts import season_published_family_component_v1 as family_components
            for alias in family_components.native_candidates(row['published_family_component'], person):
                candidates.append((compiler._pm99_text(alias['name'], label='entire published family component'),
                                   'original-' + alias['field']))
        from scripts import season_soccerbase_duplicate_source_policy_v1 as soccerbase
        for alias in soccerbase.explicit_display_names(row['replacement']):
            candidates.append((compiler._pm99_text(alias['name'], label='original Soccerbase match display name'),
                               'original-Soccerbase-' + alias['field']))
        for name, method in candidates:
            try:
                if name.casefold() != current.casefold():
                    compiler._patch_indexed_player_variable_name_payload(raw, current, name)
            except (ValueError, RuntimeError):
                continue
            player['name'] = name
            aliases.append({'carrier_id': row['carrier_id'], 'source_name': player['source_name'],
                            'display_name': name, 'method': method})
            break
        else:
            raise ValueError(f"replacement {player['source_name']} cannot fit carrier {row['carrier_id']} without losing its surname")
    return aliases


def no_photo_archive(original, carriers):
    result = bytearray(original)
    places = _active_offsets_for_players(result, carriers)
    for offsets in places.values():
        for offset in offsets:
            result[offset] = 0
    if any(_active_offsets_for_players(result, carriers).values()):
        raise ValueError('displaced portrait remains active')
    # Directory offsets are unchanged, all image pixels preserved; only
    # displaced persons' exact active directory flags may change.
    return bytes(result), places
