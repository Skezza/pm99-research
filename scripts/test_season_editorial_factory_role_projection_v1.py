"""Read-only adversarial tests through the canonical common dispatcher."""
from __future__ import annotations
import copy
import json
import tempfile
import unittest
from pathlib import Path

from app.fdi_indexed import IndexedFDIFile
from app.indexed_jug_roles import read_indexed_native_roles
from scripts import season_pipeline_v2 as pipeline
from scripts import season_release_registry_v1 as registry
from scripts import season_source_verified_player_changes_v1 as common

ROOT = registry.ROOT
QA = ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/seedorf-editorial-finerole-pilot-v1/common-dispatch-qa-v1"
REQUEST_PATH = ROOT / ".local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/seedorf-editorial-finerole-pilot-v1/request.json"
EXPECTED_RELEASE = "sourced-seedorf-dutch-country-20261024-r241a"


class EditorialIdentityGuardUnitTests(unittest.TestCase):
    """Always-runnable pure alias guards; no local game corpus required."""
    def test_same_person_initial_surname_alias_is_not_distinct_even_if_dob_disagrees(self):
        from scripts.season_editorial_factory_role_projection_v1 import distinct_factory_identity
        # The DOB preimage is deliberately different in this scenario, but name
        # aliasing must still hold rather than certify a second person.
        self.assertFalse(distinct_factory_identity("CSeedorf", "Clarence Seedorf"))
        self.assertFalse(distinct_factory_identity("C. Seedorf", "Clarence Seedorf"))
        self.assertFalse(distinct_factory_identity("Clarence Seedorf", "CSeedorf"))

    def test_shared_first_or_surname_is_conservatively_held(self):
        from scripts.season_editorial_factory_role_projection_v1 import distinct_factory_identity
        self.assertFalse(distinct_factory_identity("Clarence Seedorf", "Clarence Smith"))
        self.assertFalse(distinct_factory_identity("C. Seedorf", "Clarence Seedorf"))

    def test_distinct_name_tokens_can_pass(self):
        from scripts.season_editorial_factory_role_projection_v1 import distinct_factory_identity
        self.assertTrue(distinct_factory_identity("Christian Ziege", "Clarence Seedorf"))


class CommonRoleProjectionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not REQUEST_PATH.is_file():
            raise unittest.SkipTest("retained editorial-role request is absent in this clean checkout")
        cls.request = json.loads(REQUEST_PATH.read_text())
        try:
            cls.base = registry.load_registered_release(cls.request["season"], cls.request["release_id"])
        except (FileNotFoundError, KeyError, ValueError):
            raise unittest.SkipTest("registered source fixture parent is not available")
        cls.package = pipeline.read_json_file(cls.base.package_path)
        cls.jug_path = cls.base.game_path / "DBDAT/JUG98030.FDI"
        cls.eq_path = cls.base.game_path / "DBDAT/EQ98030.FDI"
        cls.jug = cls.jug_path.read_bytes()
        cls.eq = cls.eq_path.read_bytes()
        cls.plan = common.prepare(cls.base, REQUEST_PATH)
        cls.carrier = cls.request["carrier_id"]

    def test_01_dispatch_and_exact_parent(self):
        self.assertEqual(self.base.release_id, EXPECTED_RELEASE)
        self.assertEqual(self.plan["kind"], common.EDITORIAL_FACTORY_ROLE_KIND)
        self.assertEqual(self.plan["release_id"], EXPECTED_RELEASE)
        self.assertEqual([r["carrier_id"] for r in self.plan["updates"]], [self.carrier])
        common.validate_mask(self.plan)

    def test_02_bind_changes_only_fine_role_recipe_field(self):
        updated = common.bind(self.package, self.plan)
        before = {row["carrier_id"]: row for row in self.package["players"]}
        after = {row["carrier_id"]: row for row in updated["players"]}
        changed = {cid for cid in before if before[cid] != after[cid]}
        self.assertEqual(changed, {self.carrier})
        old_actor, new_actor = before[self.carrier], after[self.carrier]
        self.assertEqual(old_actor["facts"]["primary_position"], new_actor["facts"]["primary_position"])
        for key in ("name", "source_name", "person_id", "club_id", "ratings"):
            self.assertEqual(old_actor[key], new_actor[key])
        for field in ("birth_date", "nationality", "height_cm", "weight_kg", "shirt_number"):
            self.assertEqual(old_actor["facts"].get(field), new_actor["facts"].get(field))
        self.assertEqual(new_actor["facts"]["fine_roles"], self.plan["updates"][0]["values"]["fine_roles"])
        self.assertEqual(updated["clubs"], self.package["clubs"])
        self.assertEqual(updated["managers"], self.package["managers"])
        self.assertEqual(updated["assets"], self.package["assets"])
        self.assertEqual(len(updated["artifacts"]), len(self.package["artifacts"]) + 1)

    def test_03_apply_checks_all_six_role_slots_and_is_idempotent(self):
        masks = self.plan["updates"][0]["native_masks"]
        self.assertEqual(len(masks), 6)
        after, after_eq = common.apply(self.jug, self.eq, self.plan)
        changed_offsets = {i for i, (a, b) in enumerate(zip(self.jug, after)) if a != b}
        expected_changed = {m["file_offset"] for m in masks if m["before"] != m["after"]}
        self.assertEqual(changed_offsets, expected_changed)
        self.assertEqual(after_eq, self.eq)
        self.assertEqual(sum(m["before"] == m["after"] for m in masks), 3)
        entry = next(e for e in IndexedFDIFile.from_bytes(after).entries if e.record_id == self.carrier)
        self.assertEqual(read_indexed_native_roles(entry.decode_payload(after), self.carrier)[1], [9, 98, 98, 98, 98, 98])
        again, again_eq = common.apply(after, after_eq, self.plan)
        self.assertEqual(again, after)
        self.assertEqual(again_eq, after_eq)

    def test_04_tampered_request_and_source_binding_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="role-request-", dir=QA) as temp:
            path = Path(temp) / "tampered-request.json"
            for mutate in (
                lambda d: d["historical_identity_witness"].update(full_name="Different Person"),
                lambda d: d["source_bindings"]["fixture"].update(sha256="0" * 64),
                lambda d: d["historical_identity_witness"]["historical_identity"]["match"].update(date="2005-09-11"),
            ):
                changed = copy.deepcopy(self.request)
                mutate(changed)
                path.write_bytes(pipeline.canonical_json_bytes(changed))
                with self.assertRaises((ValueError, KeyError)):
                    common.prepare(self.base, path)

    def test_05_tampered_native_mask_is_rejected(self):
        changed = copy.deepcopy(self.plan)
        changed["updates"][0]["native_masks"][3]["after"] ^= 1
        with self.assertRaises(ValueError):
            common.apply(self.jug, self.eq, changed)

    def test_06_eq_nonpreimage_is_rejected(self):
        changed_eq = bytearray(self.eq)
        changed_eq[0] ^= 1
        with self.assertRaises(ValueError):
            common.apply(self.jug, bytes(changed_eq), self.plan)


if __name__ == "__main__":
    unittest.main(verbosity=2)
