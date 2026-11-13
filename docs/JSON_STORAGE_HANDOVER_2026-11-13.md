# Inline JSON storage and agent handover

Machine: `joe-Vostro-3350`. Source storage session:
`01a1c97b-1165-7fa0-a47f-2f9698bcb4a1`. Date: 2026-11-13 UTC.

Status: staged rollout running. Final measured scope and results will be added
here after the migration gates finish. Do not infer conversion scope from the
mechanical adapter inventory.

## Prompt to give the other agent

```text
Before continuing PM99 work, read AGENTS.md, CURRENT_WORK.md,
docs/JSON_STORAGE_HANDOVER_2026-11-13.md and
 docs/JSON_STORAGE_CONSUMER_AUDIT_2026-11-13.md.
Preserve the inline JSON storage implementation and its consumer adaptations.
It may coexist with unrelated reconstruction/submodule work: inspect the diff;
do not reset, clean, replace or revert it as incidental cleanup.

JSON input names are logical: name.json may be physically name.json.zst.
In scripts/tools, use scripts.json_storage_io_v1 for Path-like reads, writes,
existence checks, discovery, copying, linking and atomic replacement. Use
json_storage_v1 for explicit logical hashes/size/JSON operations. Do not add
permanent decompressed caches or patch Python's Path/builtins. Do not bypass
these helpers with open, os.replace, shutil.copy or direct imported Path
constants. The consumer regression guard must pass after changes.

Logical JSON hashes/sizes describe the original decoded bytes, including
whitespace and newlines. Game/tree/archive inventories describe physical stored
names and bytes. Explicit .json.zst paths in the generic adapter are physical:
never mix explicit frame names with logical JSON copy/link destinations.
A corrupt frame or simultaneous plain+compressed copies is an error; fail
closed and use the migration journal. Never update a receipt hash to the frame
hash, delete an ambiguous copy blindly, or swallow codec errors as missing data.

New automatic compression is limited by AUTO_ROOTS and the shared exclusion
policy. Existing compressed outputs retain their representation. Controls such
as current.json, *-current.json, working.json, candidates.json and locator.json
stay plain; game/binary trees, preferred input dependencies and the original
2015 backup are excluded from migration. Evidence no-overwrite rules remain.
A shared compressed inode is immutable: publish a new logical artifact rather
than overwriting one alias. Optional replay dedup skips compressed artifacts.
Never link a frame to .verified-link and rename it into a plain JSON filename.

Use batch manifests/journals to restore converted files. recover requires the
ORIGINAL batch journal and follows its recorded direction, including restore.
If new hardlink aliases exist, the old manifest must be expanded and reviewed
first; the tool refuses rather than dropping an alias. Keep every good copy.
Do not broaden root activation or migration just because a module was adapted.
Run the documented regressions and a concrete compressed build/SOURCE canary
for any newly supported family. NAS deployment is a separate filesystem gate.
Continue the user's research work while preserving this storage contract.
```

## Storage contract

`scripts/json_storage_v1.py` owns verified Zstd encoding/decoding, logical
resolution and POSIX directory locks. `scripts/json_storage_io_v1.py` dispatches
logical `.json` paths to it and delegates ordinary files and objects to native
Python behavior. No global monkeypatching is used. Plain copies and moves stay
native. Text decoding preserves Python's default encoding and newline handling.

Zstd level 1 is used for fast inline operation. Automatic new-output compression
requires at least 1 MiB and at least 10% saving, applies only in enabled families,
and preserves an existing file's representation. The decoded per-document limit
is 512 MiB. This is a decoded-size bound, **not** a total process RAM bound:
parsing JSON also allocates Python objects. Current large-document and real-shape
rehearsal evidence is in the rollout directory.

A logical JSON hash always covers original bytes; compression never reserializes
existing evidence. Both representations at once, corruption, unsafe symlinks and
missing codecs fail closed. Immutable writers refuse existing evidence. Ordinary
plain I/O remains available without the codec. Compressed writes and migration
are supported on the tested POSIX laptop filesystem.

`json_storage_policy_v2.py` shares exclusions between automatic writes and batch
migration. `data/json-storage-consumers-v2.json` and
`check_json_storage_io_v2.py` are mechanical regression guards. See the consumer
audit document for the separate physical/logical decisions and remaining scope.

## Migration, interruption and restore

`json_storage_batches_v2.py` inventories >=1 MiB raw JSON inode groups. It follows
preferred/original JSON dependencies, release parents and directory references;
excludes control/game roots, recent outputs, readable open handles, inbound
symlinks, incomplete aliases and oversized documents. Only explicitly selected
roots enter a manifest; each batch is capped at 1 GiB actual allocated input.
Registered historical scope requires a separate explicit selection.

A complete alias group is hash/metadata checked under ordered directory locks.
One verified frame is published at every alias before raw aliases are retired.
The journal is flushed/fsynced at each transition. Modes, owner/group, mtime,
original bytes and inode sharing are preserved. The hard free-space reserve is
6 GiB; normal build reserve remains 8 GiB unless explicitly configured otherwise.
The live workbook's earlier explicit reserve setting is not a new default.

Typical commands, from `/home/joe/pm99-research`:

```bash
python3 scripts/json_storage_batches_v2.py inventory --output NEW-inventory.json
python3 scripts/json_storage_batches_v2.py apply BATCH-manifest.json --output NEW-apply.jsonl
python3 scripts/json_storage_batches_v2.py restore BATCH-manifest.json --output NEW-restore.jsonl
python3 scripts/json_storage_batches_v2.py recover ORIGINAL-interrupted-journal.jsonl --output NEW-recovery.jsonl
```

Inventory is read-only. Manifest selection is an API operation (`make_manifest`)
from reviewed roots, not a blanket recursive conversion. Use a new journal
filename every time. A manifest passed to `recover` is rejected. Recovery
verifies every surviving representation, consolidates aliases and removes only
verified reserved staging links left by interruption. Never remove raw or
compressed files manually to resolve ambiguity.

Later legitimate hardlinks change an alias group. Restore/recovery then refuses
until an expanded manifest is reviewed; an old journal is not authorization to
unlink new aliases. Preferred catalogue changes also require re-audit. Locks
coordinate cooperating helpers; they do not make direct external writers safe.
Use inactive inputs and a per-family consumer/shell audit. The dependency scan
can take time; it deduplicates inode contents, path references and queued nodes
and reports progress. Its cache lives only within the migration process.

## Verification

```bash
.local/venvs/season-pipeline/bin/python -m pytest -q \
  scripts/test_json_storage_v1.py scripts/test_json_storage_rollout_v2.py \
  scripts/test_season_pipeline_v2.py scripts/test_season_package_v2.py \
  scripts/test_season_release_registry_v1.py scripts/test_season_delivery_status_v1.py

PYTHONPATH=upstream/pm99-skezmod-db-editor:upstream/pm99-skezmod-patcher \
  .local/venvs/season-pipeline/bin/python -m pytest -q \
  tools/test_season_preset_browser.py scripts/test_editorial_amendment_delta_v1.py

python3 scripts/check_json_storage_io_v2.py
python3 scripts/check_repo_boundary.py
./pm99-season validate all
./pm99-season play 2015-16 --original --check
```

The new tests include native plain-file semantics, locale/UTF-8 mode, CRLF,
symlinks, no-clobber writes, corruption/missing codec, both restore directions,
source mutation, disk reserve, shared aliases and real SIGKILL recovery. An
unpreferred private canary must exercise the real workbook, two chained edits,
compressed recipe reads, complete SOURCE replay and a byte-identical plain
control before activation. It must not alter the preferred catalogue.

Local rollout evidence: `.local/json-storage-rollout-20261113/` (manifests,
journals, actual allocations/free space, tests, browser proof and ephemeral
Claude Sonnet QA sessions). Broader family regressions have 14 pre-existing
failures, reproduced exactly at baseline `6d9746e`; see
`family-failure-comparison.json` and `family-baseline-comparison-v2.log`. These
are not represented as passing tests and are outside storage repair scope.

## Earlier pilot

Baseline commit `6d9746e` compressed six inactive 2005/06 qualification
`receipts/season-package.effective.json` snapshots (r2, r3, r4, r5-a, r6-a,
r6-b). Original allocation was 97.37 MiB; final frame allocation about 5.16 MiB.
Initial measured saving was 92.27 MiB. Do not add rollback/reapply savings twice.
Evidence remains under `.local/json-compression-pilot-20261113/`.

That earlier six-file manifest still uses `scripts/migrate_json_storage_v1.py`:

```bash
python3 scripts/migrate_json_storage_v1.py .local/json-compression-pilot-20261113/manifest.json --restore
python3 scripts/migrate_json_storage_v1.py .local/json-compression-pilot-20261113/manifest.json --restore --apply --receipt NEW-pilot-restore.jsonl
```
