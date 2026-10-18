import hashlib
import json

from scripts.capture_transfermarkt_historical_squads_v1 import canonical_bytes
from scripts.materialise_historical_squad_current_aliases_v1 import materialise
from scripts.season_historical_squad_backfill_batch_v1 import CURRENT_SCHEMA


def test_materialises_only_hash_verified_revision_artifacts(tmp_path) -> None:
    payload = canonical_bytes({"value": 1})
    revision = tmp_path / "revisions/rev-test/source.json"
    revision.parent.mkdir(parents=True)
    revision.write_bytes(payload)
    manifest = {
        "artifacts": {"source": {"path": "revisions/rev-test/source.json", "sha256": hashlib.sha256(payload).hexdigest()}},
        "revision_id": "rev-test", "schema_version": CURRENT_SCHEMA, "season": "2000-01",
    }
    (tmp_path / "current.json").write_bytes(canonical_bytes(manifest))
    receipt = materialise(tmp_path)
    assert (tmp_path / "source.json").read_bytes() == payload
    assert json.loads((tmp_path / "aliases-current.json").read_text()) == receipt
