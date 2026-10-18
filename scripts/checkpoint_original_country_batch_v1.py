"""Publish a bounded country batch only after full native/SOURCE/runtime proof."""
import copy
from datetime import UTC, datetime

from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_original_secondary_facts_v1 as original_source
from scripts import publish_historical_role_delta_v1 as publisher, attest_registered_season_runtime_v1 as runtime
from scripts.build_2015_english92_release import NATIONALITY, UNREPRESENTABLE_NATIONALITY
from scripts.consolidated_season_discovery_v1 import bindings
from scripts.checkpoint_original_secondary_fact_delivery_20261010 import check_visual
from scripts.checkpoint_remaining_manager_tenures_20261016 import verify_original2015
from scripts.verify_profile_skill_digits_v1 import verify_profiles as verify_digits
from scripts.verify_city_opening_runtime_20261011 import verify_profiles
from scripts.review_rating_frames_20261011 import lineup_frame
from scripts.build_savio_bobb_alias_reserve_20261011 import retained


def binding(path):
    return dict(path=registry.relative_workspace_path(path),sha256=registry.sha256_file(path))


def country_label(code):
    if code == 'CGO':
        return 'CONGO'  # Not COD/ZAIRE; actual TEXTOS has two distinct entries.
    if code in UNREPRESENTABLE_NATIONALITY:
        return 'XXX'
    if code not in NATIONALITY:
        raise ValueError('unreviewed native country label mapping')
    return NATIONALITY[code]


def check_country_code(row, codes):
    label=country_label(row['nationality'])
    if label not in codes or row['native_country_code'] != codes[label]:
        raise ValueError('source country would display the wrong native country: '+row['nationality'])
    return label


def check_literal_role(review,native_position):
    # This checks the review transcription, not historical role correctness.
    labels={'G':'GOALKEEPER','D':'DEFENDER','M':'MIDFIELDER','F':'FORWARD'}
    if native_position not in labels or review.get('observed_role')!=labels[native_position]:
        raise ValueError('reviewed literal role heading differs from actual native profile')


def real_country_change_counts(rows):
    return dict(countries_source_verified=len(rows),
        countries_corrected=sum(r['native_country_changed'] or r['recipe_country_changed'] for r in rows),
        native_country_values_changed=sum(r['native_country_changed'] for r in rows),
        recipe_country_values_changed=sum(r['recipe_country_changed'] for r in rows))


def registration_ancestry(proof,current_release_id,final_release_id):
    if (proof.get('schema')!='pm99-verified-country-only-ancestry-v1'
            or proof.get('base_release_id')!=current_release_id
            or proof.get('final_release_id')!=final_release_id
            or not 1<=len(proof.get('edges',[]))<=8):
        raise ValueError('country registration requires the exact verified bounded ancestry')
    chain=[current_release_id]
    for edge in proof['edges']:
        if edge['parent_release_id']!=chain[-1] or edge['release_id'] in chain:
            raise ValueError('country registration ancestry skips a parent or cycles')
        chain.append(edge['release_id'])
    if chain[-1]!=final_release_id:
        raise ValueError('country registration ancestry does not reach the final game')
    return chain


def independent_country_checks(row,season,*,index=None,file_sha=None):
    from scripts import season_country_fifa_crosscheck_v1 as fifa_check
    if 'country_resolution_input' in row:
        from scripts import season_resolved_period_country_v3 as resolved
        proof=resolved.verify_row_resolution(row,season,index=index,file_sha=file_sha)
        return dict(status='resolved-by-rederived-original-country-source-choice',
            country_resolution=proof,country_truth_approved=False),proof['independent_biography']
    result=fifa_check.check(row,season,index=index,file_sha=file_sha)
    country_proof=None
    if row['nationality']=='CGO':
        from scripts import season_cgo_disambiguation_v2 as independent_country
        country_proof=independent_country.verify(row,season)
    if result['status']=='contradiction-requires-resolution':
        # FIFA has its own Congo miscoding. A reparsed exact-person original
        # biography with a prior dated Republic national-team association,
        # agreeing with the dated squad, resolves that geography disagreement.
        # This is not a waiver for other countries, future debuts or aliases.
        if country_proof is None or country_proof['country']!=row['nationality']:
            raise ValueError('period country source contradicts exact historical FIFA; resolve before publication: '+str(row['carrier_id']))
        result=dict(result,status='resolved-country-geography-by-independent-prior-dated-association',
            raw_FIFA_disagreement_retained=True,
            resolution_rule='dated-squad-plus-exact-biography-country-link-over-FIFA-Congo-geography',
            independent_country_proof=country_proof)
    return result,country_proof


def run(root,season,release_id,replay_id,previous_path,output,tag,profiles,*,source=original_source,ancestors=()):
    if output.exists():
        raise ValueError('completed country publication must not repeat')
    previous=pipeline.read_json_file(previous_path);old=previous['current_release_bindings']
    if bindings()!=old:
        raise ValueError('current country default bindings differ from explicit previous checkpoint')
    actual=registry.load_registered_release(season,release_id)
    plan_path=root/'country-plan.json';plan=pipeline.read_json_file(plan_path)
    base=registry.load_registered_release(season,plan['release_id'])
    preferred=registry.load_preferred_release(season)
    chain_proof=None;country_origins={};updates=plan['updates']
    if ancestors:
        from scripts import verify_country_only_ancestry_v1 as ancestry
        updates,country_origins,chain_proof=ancestry.verify(actual,preferred,
            [ancestry.Edge(release_id,replay_id,root),*ancestors])
        base=preferred
    elif preferred.manifest_sha256!=base.manifest_sha256:
        raise ValueError('country parent changed or is not yet delivered')
    if not ancestors:
        source.verify(base,plan)
    if (not plan['updates'] or plan['unresolved']
            or any(r['fields']!=['nationality'] for r in plan['updates'])
            or len({r['carrier_id'] for r in plan['updates']})!=len(plan['updates'])
            or plan['targets']!={str(r['carrier_id']):['nationality'] for r in plan['updates']}):
        raise ValueError('exact unique nationality-only source scope required')
    before=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    after=(actual.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    before_countries={p['carrier_id']:p['facts'].get('nationality')
        for p in pipeline.read_json_file(base.package_path)['players']}
    after_countries={p['carrier_id']:p['facts'].get('nationality')
        for p in pipeline.read_json_file(actual.package_path)['players']}
    eq=(base.game_path/'DBDAT/EQ98030.FDI').read_bytes()
    if not ancestors and (source.apply(before,eq,plan)!=(after,eq) or source.apply(after,eq,plan)!=(after,eq)):
        raise ValueError('whole country native reconstruction or idempotence differs')
    codes=source.compiler._extract_country_codes_from_textos(actual.game_path/'DBDAT/TEXTOS.PKF')
    entries={e.record_id:e for e in IndexedFDIFile.from_bytes(before).entries}
    allowed=set();observed=[];labels={};native_positions={};position_followups=[];country_disambiguation=[]
    fifa_countries=None;fifa_countries_sha=None;country_crosschecks=[]
    for row in updates:
        label=check_country_code(row,codes);labels[row['carrier_id']]=label
        from scripts import season_country_fifa_crosscheck_v1 as country_crosscheck
        if (15<=int(season[:4])-1999<=23 or 'country_resolution_input' in row) and fifa_countries is None:
            fifa_countries_sha=registry.sha256_file(country_crosscheck.fifa.identity.old.FIFA)
            fifa_countries=country_crosscheck.load(fifa_countries_sha)
        independent,country_proof=independent_country_checks(row,season,index=fifa_countries,file_sha=fifa_countries_sha)
        country_crosschecks.append(dict(carrier_id=row['carrier_id'],**independent))
        if country_proof is not None:
            country_disambiguation.append(country_proof)
        entry=entries[row['carrier_id']];payload=entry.decode_payload(after)
        native=original_source.original.audit.native_player(payload,row['carrier_id'])
        end=native['name_end'];native_positions[row['carrier_id']]=native['position']
        native_code=payload[end+8]^0x61
        before_code=entry.decode_payload(before)[end+8]^0x61
        if native_code!=row['native_country_code']:
            raise ValueError('independent actual stored country differs from original source mapping')
        allowed.add(entry.payload_offset+end+8)
        observed.append(dict(carrier_id=row['carrier_id'],source_country=row['nationality'],
            native_country_code=native_code,native_label=label,before_native_country_code=before_code,
            before_recipe_country=before_countries[row['carrier_id']],after_recipe_country=after_countries[row['carrier_id']],
            native_country_changed=before_code!=native_code,
            recipe_country_changed=before_countries[row['carrier_id']]!=after_countries[row['carrier_id']]))
        positions={w['original_player'].get('position') for w in row['nationality_evidence']}
        if len(positions)==1 and positions<={'G','D','M','F'} and native['position'] not in positions:
            position_followups.append(dict(id=f'country-source-position-{season}-{row["carrier_id"]}',
                season=season,carrier_id=row['carrier_id'],name=row['before_player']['name'],
                state='open-dated-annual-broad-position-conflict',native_position=native['position'],
                original_annual_position=next(iter(positions)),
                source_plan=country_origins.get(row['carrier_id'],binding(plan_path)),
                nationality_repair_does_not_approve_role_or_August_deployment=True))
    changed={i for i,(a,b) in enumerate(zip(before,after)) if a!=b}
    counts=real_country_change_counts(observed)
    if counts['native_country_values_changed']!=len(changed):
        raise ValueError('country value changes do not match distinct actual nationality bytes')
    if len(before)!=len(after) or not changed<=allowed:
        raise ValueError('country patch changed another native field')
    left={r['path']:r['sha256'] for r in pipeline.read_json_file(base.inventory_path)['files']}
    right={r['path']:r['sha256'] for r in pipeline.read_json_file(actual.inventory_path)['files']}
    if set(left)!=set(right) or any(left[k]!=right[k] for k in left if k!='DBDAT/JUG98030.FDI'):
        raise ValueError('country patch changed another game file')
    if not ancestors and source.bind(pipeline.read_json_file(base.package_path),plan)!=pipeline.read_json_file(actual.package_path):
        raise ValueError('country patch changed unrelated recipe facts')
    replay=pipeline.read_json_file(root/'complete-SOURCE-replay.json')
    rebuilt=registry.load_registered_release(season,replay_id)
    if not replay['complete_game_inventory_identical'] or not replay['complete_recipe_identical']:
        raise ValueError('whole country SOURCE proof incomplete')
    for release in (actual,rebuilt):
        pipeline.assert_tree_matches_inventory(release.game_path,pipeline.read_json_file(actual.inventory_path))
    if actual.package_path.read_bytes()!=rebuilt.package_path.read_bytes():
        raise ValueError('country whole SOURCE recipe differs')
    if not profiles or not {r[0] for r in profiles}<={r['carrier_id'] for r in updates}:
        raise ValueError('at least one actually changed-country original profile required')
    evidence=registry.ROOT/'.local/runlogs/pm99_runner'/tag
    transport=pipeline.read_json_file(root/'startup-transport.json')
    summary=pipeline.read_json_file(evidence/'summary.json')
    visual=pipeline.read_json_file(root/'startup-visual-review.json');check_visual(visual)
    if (transport['exit_code']!=0 or transport['release_manifest_sha256']!=actual.manifest_sha256
            or transport['evidence']!=registry.relative_workspace_path(evidence)
            or visual['observed_team']!='Stoke City' or visual['observed_date']!=season[:4]+'-08-01'
            or visual['release_manifest_sha256']!=actual.manifest_sha256
            or visual['screenshot_sha256']!=registry.sha256_file(lineup_frame(evidence))
            or not summary.get('success') or summary.get('crash_detected') or summary.get('wine_debugger_detected')
            or summary['release_manifest_sha256']!=actual.manifest_sha256
            or summary['output_inventory_fingerprint']!=actual.locator['game_inventory_fingerprint']):
        raise ValueError('original country startup not bound to corrected game')
    verify_digits(root,season,release_id,profiles);verify_profiles(root,season,release_id,profiles)
    for carrier,label,_,_ in profiles:
        visual=pipeline.read_json_file(root/(label+'-profile-visual-review.json'))
        check_literal_role(visual,native_positions[carrier])
        if original_source.original.audit.normalise(visual['observed_nationality'])!=original_source.original.audit.normalise(labels[carrier]):
            raise ValueError('actual corrected country text not independently reviewed')
    backup=verify_original2015()
    retained(root/'independent-country-crosschecks.json',dict(season=season,rows=country_crosschecks,
        contradictions_not_automatically_waived=True,missing_coverage_not_claimed_as_corroboration=True))
    if country_disambiguation:
        retained(root/'country-code-disambiguation-proof.json',dict(season=season,rows=country_disambiguation,
            provider_CGO_not_assumed_unambiguous=True,current_country_or_future_caps_not_used=True))
    if chain_proof is not None:
        retained(root/'country-chain-proof.json',chain_proof)
    if bindings()!=old:
        raise ValueError('another default changed during country preflight')
    retained(root/'prepublication-proof.json',dict(source_countries=observed,
        **counts,
        native_country_bytes_changed=len(changed),
        all_changed_country_bytes_verified=True,other_native_game_recipe_facts_preserved=True,
        whole_SOURCE=True,original_startup_and_representative_profiles_verified=len(profiles),
        duplicate_and_birthday_counters_unchanged=True))
    if chain_proof is not None:
        publisher.register_completed_delta(season,release_id,
            verified_ancestor_chain=registration_ancestry(chain_proof,base.release_id,release_id))
    else:
        publisher.register_completed_delta(season,release_id)
    retained(root/'final-attestation.json',runtime.attest(season=season,evidence_dir=evidence))
    validation=registry.validate_preferred_release(season,level='playable')
    if not validation['valid']:
        raise ValueError('country default fails playable validation')
    retained(root/'preferred-playable-validation.json',validation)
    current=bindings()
    if [r for r in current if r['season']!=season]!=[r for r in old if r['season']!=season]:
        raise ValueError('country publication changed another preferred season')
    result=copy.deepcopy(previous)
    result['additional_confirmed_findings'].append(dict(id='period-country-batch-'+release_id,season=season,
        state='delivered-source-native-SOURCE-and-runner-verified',**counts,
        native_country_bytes_changed=len(changed),
        source_plan=binding(plan_path),cross_club_cases_closed=0,
        identity_role_ownership_skill_asset_approval=False))
    existing={r['id'] for r in result['additional_confirmed_findings']}
    result['additional_confirmed_findings'] += [r for r in position_followups if r['id'] not in existing]
    names=['country-plan.json','native-byte-proof.json','complete-SOURCE-replay.json','startup-transport.json',
        'startup-visual-review.json','prepublication-proof.json','final-attestation.json','preferred-playable-validation.json',
        'independent-country-crosschecks.json']
    names += [label+suffix for _,label,_,_ in profiles for suffix in ('-profile-transport.json',
        '-profile-visual-review.json','-native-runtime-proof.json','-original-digit-proof.json','-original-age-proof.json')]
    if chain_proof is not None:
        names.append('country-chain-proof.json')
    if country_disambiguation:
        names.append('country-code-disambiguation-proof.json')
    result['delivered_evidence'] += [backup]+[binding(root/name) for name in names]
    result.update(utc=datetime.now(UTC).isoformat(),previous_checklist=binding(previous_path),
        current_release_bindings=current,fresh_runtime_runs_this_checklist=[season],all_required_work_complete=False)
    pipeline.write_canonical_json(output,result)
    retained(root/'final-delivery-summary.json',dict(checklist=binding(output),countries_delivered=counts['countries_corrected'],
        **counts,
        native_country_bytes_changed=len(changed),new_dated_position_followups=len(position_followups),
        all_other25_preferred_bindings_unchanged=True,original2015_backup_verified=True,
        duplicate_and_birthday_counters_unchanged=True,global_historical_RC=False))
    print(dict(country_corrections_delivered=counts['countries_corrected'],countries_source_verified=len(observed),
        season=season,cross_club_cases_closed=0),flush=True)
