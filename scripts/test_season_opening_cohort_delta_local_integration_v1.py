from __future__ import annotations
import copy, json, sys, unittest
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; BASE=ROOT/'.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/molde-irish-opening-cohort-adapter-proposal-v1'; CAND=BASE/'canonical-provider-candidate-v4'
sys.path[:0]=[str(ROOT),str(ROOT/'upstream/pm99-skezmod-db-editor'),str(CAND),str(BASE)]
from scripts import season_opening_cohort_delta_v1 as provider
from scripts import season_package_compiler_v2 as compiler
from scripts import season_release_registry_v1 as registry
from app.fdi_indexed import IndexedFDIFile

class OpeningCohortProviderCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (CAND/"opening-cohort-source-plan-v4-bound.json").is_file():
            raise unittest.SkipTest("Local source/native integration corpus is not installed")
        cls.profile=json.loads((CAND/'opening-cohort-delta-f71d4725acbe78b13c84dd20.json').read_text())
        cls.release=registry.load_registered_release('2017-18',cls.profile['parent']['release_id'])
        cls.package=json.loads((CAND/'molde-termalica-five-actor-child-recipe-v4.json').read_text())
        cls.plan=json.loads((CAND/'opening-cohort-source-plan-v4-bound.json').read_text())
        cls.preview=(BASE/'five-actor-child-native-preview-v1/in-memory-native-postimage/JUG98030.FDI').read_bytes()

    def test_full_persisted_native_bindings_and_exact_immutable_parent_source_replay(self):
        core, path, digest=provider.embedded_plan(self.package)
        self.assertEqual(core,self.plan)
        self.assertEqual(digest,self.profile['typed_plan']['sha256'])
        self.assertTrue(all('native_transfer_binding' in row for row in core['actors']
                            if row['identity_policy']=='same-person-preserve'))
        receipt=provider.verify(self.release,self.profile)
        self.assertEqual(receipt['source_reconstruction']['reconstruction']['post_jug_sha256'],
                         self.profile['expected_post_jug_sha256'])
        self.assertEqual(provider.bind(json.loads(self.release.package_path.read_text()),self.profile),self.package)
        parent_jug=(self.release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        parent_eq=(self.release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
        replay,eq=provider.apply(parent_jug,parent_eq,self.profile)
        self.assertEqual(replay,self.preview)
        self.assertEqual(eq,parent_eq)
        self.assertEqual(provider.apply(replay,eq,self.profile),(replay,eq))
        drift=bytearray(replay);drift[-1]^=1
        with self.assertRaisesRegex(ValueError,'native preimage differs'):
            provider.apply(bytes(drift),eq,self.profile)
        self.assertEqual(replay,provider.reconstruct_from_parent(
            self.release,self.package,expected_package_sha256=self.profile['child_recipe']['sha256'])[0])

    def test_edits_to_recipe_or_serialized_transfer_pin_fail_closed(self):
        changed=copy.deepcopy(self.package)
        changed['package_id']+='-edited'
        with self.assertRaisesRegex(ValueError,'child recipe differs from stored compiler/locator SHA'):
            provider.verify_recipe(self.release,changed,
                expected_package_sha256=self.profile['child_recipe']['sha256'])
        changed=copy.deepcopy(self.plan)
        actor=next(row for row in changed['actors'] if row['identity_policy']=='same-person-preserve')
        actor['native_transfer_binding']['source_payload_sha256']='0'*64
        parent_package=json.loads(self.release.package_path.read_text())
        parent_jug=(self.release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        parent_eq=(self.release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
        codes=compiler._extract_country_codes_from_textos(self.release.game_path/'DBDAT/TEXTOS.PKF')
        rebound=provider.core.bind_same_person_preimages(parent_package,parent_jug,parent_eq,changed,codes)
        self.assertNotEqual(rebound,changed)

    def test_no_photo_quality_dispatcher_uses_existing_writer_on_selected_carriers(self):
        archive=(self.release.game_path/'DBDAT/MINIFOTO.PKF').read_bytes()
        post,offsets=provider.apply_profile_minifoto(archive,self.profile)
        self.assertEqual(set(offsets),{int(row['post_carrier_id']) for row in self.plan['actors']})
        self.assertEqual({carrier:rows for carrier,rows in offsets.items() if rows},{})
        self.assertEqual(post,archive)

    def test_source_release_gate_reads_stored_child_and_profile_pins(self):
        with TemporaryDirectory(prefix='cohort-source-gate-') as tmp:
            game=Path(tmp)/'game'; (game/'DBDAT').mkdir(parents=True)
            (game/'DBDAT/JUG98030.FDI').write_bytes(self.preview)
            parent_eq=(self.release.game_path/'DBDAT/EQ98030.FDI').read_bytes()
            (game/'DBDAT/EQ98030.FDI').write_bytes(parent_eq)
            stored_plan=CAND/provider.filename(self.profile)
            child=SimpleNamespace(season=self.release.season,release_id='private-child',
                locator={'sourced_profile_assignment_plan_path':str(stored_plan.relative_to(ROOT))},
                package_path=CAND/'molde-termalica-five-actor-child-recipe-v4.json',game_path=game)
            receipt=provider.verify_source(self.release,child,self.profile)
            self.assertEqual(receipt['source_child_jug_sha256'],self.profile['expected_post_jug_sha256'])
            edited=Path(tmp)/'edited-recipe.json'
            edited.write_text(child.package_path.read_text().replace(
                'molde-termalica-opening-cohort-20261025-v4-candidate',
                'molde-termalica-opening-cohort-edited',1))
            child.package_path=edited
            with self.assertRaisesRegex(ValueError,'SOURCE child recipe bytes differ'):
                provider.verify_source(self.release,child,self.profile)

    def test_compiler_factory_guard_accepts_bound_recipe_and_rejects_drift(self):
        provider.reject_factory_recipe(self.package)
        changed=copy.deepcopy(self.package)
        row=next(row for row in changed['artifacts'] if row['id'].startswith('opening-cohort-plan-'))
        row['sha256']='0'*64
        with self.assertRaises(ValueError):
            provider.reject_factory_recipe(changed)

    def test_source_body_membership_all_xi_and_position_rows_reject_tampering(self):
        provider._verify_fixture_source_membership(self.plan)
        changed=copy.deepcopy(self.plan)
        molde=next(row for row in changed['clubs'] if row['club_carrier_id']==1352)
        molde['source_slot_rows'][0]['fiks_person_id']='9999999'
        with self.assertRaisesRegex(ValueError,'fixture assertion|starting XI IDs/names'):
            provider._verify_fixture_source_membership(changed)
        changed=copy.deepcopy(self.plan)
        molde=next(row for row in changed['clubs'] if row['club_carrier_id']==1352)
        slot=next(row for row in molde['source_slot_rows']
                  if 'molde_2017_footballsquads' in row.get('published_position_row_bindings',{}))
        source_id='molde_2017_footballsquads'
        slot['published_position_row_bindings'][source_id]['row_text']='not a published row'
        with self.assertRaisesRegex(ValueError,'CSV row text/hash'):
            provider._verify_fixture_source_membership(changed)
        changed=copy.deepcopy(self.plan)
        molde=next(row for row in changed['clubs'] if row['club_carrier_id']==1352)
        slot=next(row for row in molde['source_slot_rows']
                  if 'molde_annual' in row.get('published_position_row_bindings',{}))
        option=next(row for row in slot['published_position_options'] if row['source_id']=='molde_annual')
        option['position']='F'
        with self.assertRaisesRegex(ValueError,'position option differs'):
            provider._verify_fixture_source_membership(changed)

    def test_root_approved_utility_exception_is_bound_and_role_compatible(self):
        receipt=provider.verify_native_slot_compatibility(self.preview,self.plan)
        self.assertEqual(receipt['slot_count'],22)
        self.assertEqual(receipt['utility_exception_count'],1)
        kupczak=next(row for row in receipt['rows'] if row['carrier_id']==13843)
        self.assertEqual((kupczak['typed_slot_position'],kupczak['native_broad_position']),('D','M'))
        self.assertIn(4,kupczak['native_fine_roles'])
        changed=copy.deepcopy(self.plan)
        slot=next(row for club in changed['clubs'] for row in club['source_slot_rows']
                  if row['carrier_id']==13843)
        del slot['utility_exception']
        with self.assertRaisesRegex(ValueError,'lacks a bound utility exception'):
            provider.verify_native_slot_compatibility(self.preview,changed)
        changed=copy.deepcopy(self.plan)
        slot=next(row for club in changed['clubs'] for row in club['source_slot_rows']
                  if row['carrier_id']==13843)
        slot['utility_exception']['native_eligible_fine_role']=9
        with self.assertRaisesRegex(ValueError,'unsupported by its broad/fine role'):
            provider.verify_native_slot_compatibility(self.preview,changed)
        changed=copy.deepcopy(self.plan)
        slot=next(row for club in changed['clubs'] for row in club['source_slot_rows']
                  if row['carrier_id']==13843)
        slot['slot_position']='M'
        with self.assertRaisesRegex(ValueError,'exception is attached to a natively compatible slot'):
            provider.verify_native_slot_compatibility(self.preview,changed)

    def test_closed_recipe_mask_rejects_unselected_actor_fact_and_manager_edits(self):
        from scripts import season_package_v2 as packages
        parent_package=json.loads(self.release.package_path.read_text())
        jug=(self.release.game_path/'DBDAT/JUG98030.FDI').read_bytes()
        codes=compiler._extract_country_codes_from_textos(self.release.game_path/'DBDAT/TEXTOS.PKF')
        changed=copy.deepcopy(self.package)
        selected={row['recipe_player_id'] for row in self.plan['actors']}
        unselected=next(row for row in changed['players'] if row['id'] not in selected)
        unselected['name']+=' edited'
        with self.assertRaisesRegex(ValueError,'unselected player row'):
            provider._verify_recipe_field_mask(parent_package,changed,jug,self.plan,codes)
        changed=copy.deepcopy(self.package)
        ranmark=next(row for row in changed['players'] if row['id']=='player-20019')
        ranmark['facts']['weight_kg']=85
        with self.assertRaisesRegex(ValueError,'new actor fact differs'):
            provider._verify_recipe_field_mask(parent_package,changed,jug,self.plan,codes)
        changed=copy.deepcopy(self.package)
        changed['managers'][0]['name']+=' edited'
        with self.assertRaisesRegex(ValueError,'closed top-level field: managers'):
            provider._verify_recipe_field_mask(parent_package,changed,jug,self.plan,codes)

    def test_source_reconstruction_creates_new_child_via_mock_publisher(self):
        from scripts import publish_historical_role_delta_v1 as publisher
        with TemporaryDirectory(prefix='opening-cohort-source-create-') as tmp:
            temp=Path(tmp)
            profile_path=CAND/provider.filename(self.profile)
            receipt_path=temp/'compiler.json'
            receipt_path.write_text(json.dumps({'compilation_mode':provider.MODE,
                'original_profile_assignment_plan_sha256':registry.sha256_file(profile_path)}))
            inventory_path=temp/'inventory.json'; inventory_path.write_text('{"files":[]}')
            descriptor_path=CAND/'role-delta-input.json'
            descriptor={"season":self.release.season,"release_id":self.release.release_id,
                "package_sha256":self.profile['parent']['package_sha256'],
                "jug_sha256":self.profile['parent']['native_sha256']['JUG98030.FDI'],
                "updates":[],"unresolved":[]}
            descriptor_path.write_text(json.dumps(descriptor))
            relative=str(profile_path.relative_to(ROOT))
            previous=SimpleNamespace(season=self.release.season,release_id='candidate-A',
                compiler_receipt_path=receipt_path,
                locator={'sourced_profile_assignment_plan_path':relative},
                package_path=CAND/'molde-termalica-five-actor-child-recipe-v4.json',
                inventory_path=inventory_path,game_path=self.release.game_path)
            target_id='private-opening-cohort-source-b-test-001'
            target_locator=temp/'registry'/target_id/'locator.json'
            made={}
            def load(season,release_id):
                return made[release_id] if release_id in made else self.release
            def fake_publish(season, plan_path, **kwargs):
                self.assertEqual(season,self.release.season)
                self.assertEqual(Path(plan_path),descriptor_path)
                self.assertEqual(kwargs['release_id'],target_id)
                self.assertEqual(kwargs['source_release_id'],self.release.release_id)
                self.assertEqual(kwargs['minimum_free_bytes'],8*1024**3)
                made[target_id]=SimpleNamespace(season=season,release_id=target_id,
                    package_path=previous.package_path,game_path=self.release.game_path,
                    locator={'sourced_profile_assignment_plan_path':relative})
            try:
                with patch.object(registry,'load_registered_release',side_effect=load), \
                     patch.object(registry,'locator_path',return_value=target_locator), \
                     patch.object(publisher,'publish',side_effect=fake_publish), \
                     patch.object(provider,'verify_source',return_value={'mock':'source-verified'}), \
                     patch('scripts.season_pipeline_v2.assert_tree_matches_inventory') as assert_inventory:
                    result=provider.reconstruction(previous,target_id)
                self.assertEqual(result['release_id'],target_id)
                self.assertTrue(result['complete_game_inventory_identical'])
                self.assertTrue(result['complete_recipe_identical'])
                assert_inventory.assert_called_once()
            finally:
                descriptor_path.unlink(missing_ok=True)

    def test_patched_quality_build_dispatches_ordinary_recipe_without_new_args(self):
        quality_path=CAND/'overlay/scripts/build_registered_quality_release_v1.py'
        spec=importlib.util.spec_from_file_location('private_candidate_quality_builder',quality_path)
        quality=importlib.util.module_from_spec(spec); spec.loader.exec_module(quality)
        from scripts import season_owned_club_composition_v1 as composition
        from scripts import season_visual_patch_reconstruction_v1 as artwork
        class ReachedNextSourceGate(Exception): pass
        previous=SimpleNamespace()
        with patch.dict(sys.modules,{'scripts.season_opening_cohort_delta_v1':provider}), \
             patch.object(quality.pipeline,'normalise_season_id',return_value='2017-18'), \
             patch.object(quality.registry,'load_preferred_release',return_value=previous), \
             patch.object(composition,'reconstruction',return_value=None), \
             patch.object(provider,'reconstruction',return_value=None) as opening_dispatch, \
             patch.object(artwork,'reconstruction',side_effect=ReachedNextSourceGate):
            with self.assertRaises(ReachedNextSourceGate):
                quality.build('2017-18',release_id='ordinary-recipe-test')
        opening_dispatch.assert_called_once_with(previous,'ordinary-recipe-test')

if __name__=='__main__': unittest.main(verbosity=2)
