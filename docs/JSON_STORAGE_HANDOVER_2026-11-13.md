# JSON storage pilot and agent handover

Machine: `joe-Vostro-3350`. Source storage session:
`01a1c97b-1165-7fa0-a47f-2f9698bcb4a1`. Date: 2026-11-13 UTC.

## Prompt to give the other agent

```text
Before continuing PM99 work, read AGENTS.md, CURRENT_WORK.md and
docs/JSON_STORAGE_HANDOVER_2026-11-13.md. A small inline Zstd storage pilot is
already implemented and six inactive qualification snapshots are compressed.
Preserve scripts/json_storage_v1.py, scripts/migrate_json_storage_v1.py, their
tests and the integrations in season_pipeline_v2.py, season_package_v2.py and
season_release_registry_v1.py. These may be uncommitted alongside my unrelated
work: inspect the diff and preserve it; do not reset, clean or replace it.

JSON input paths are logical: name.json may be physically name.json.zst.
Use json_storage_v1.read_json/read_bytes/is_file/iter_json_paths/sha256_file/
size/copy_json for those inputs. Compression/decompression happens inline;
do not create permanent plain copies to make direct read_text/read_bytes,
Path.exists, glob or shutil.copy calls work. Audit such callers before moving
additional files. Raw game files and physical game inventories stay unchanged.
Never change a receipt's original SHA-256 to the compressed-file hash.

Default writes remain plain. Compressed writes are opt-in; existing compressed
package writes retain that format. Keep immutable-evidence no-overwrite rules,
canonical encoding checks, corruption rejection and concurrency protections.
Do not blanket-compress .local or touch registered/current release inputs.
Only six manifest-listed inactive snapshots have been migrated. The workbook,
builder and arbitrary historical scripts are NOT all compression-aware yet.

Continue the user's current task while preserving this compatibility contract.
If a required historical caller lacks support, adapt that caller and test it,
or use the documented verified restore operation and report the rollback.
Run the documented storage/pipeline/package/registry regressions before
claiming compatibility. Keep existing 26 preferred games and original 2015
backup unchanged. Do not resume or broaden storage migration without scope.
```

## Implemented behavior and scope

The shared API lives in `scripts/json_storage_v1.py`. It accepts a logical
`name.json` and resolves exactly one representation: the ordinary file or
`name.json.zst`. The latter is read through the installed `zstd` command directly
into the calling process. It does not materialise a plain disk cache or patch
Python's Path/builtins. The Zstd command is required only for compressed data.
Compressed writes and conversion are supported on the POSIX laptop/Pi in v1.
Plain reads and the established plain package writer remain available elsewhere.

Supported entry points are:

- `season_pipeline_v2.read_json_file` and opt-in
  `write_canonical_json(..., compressed=True)`;
- pipeline external-artifact and canonical-document descriptors;
- `season_package_v2.read_canonical_package`, package hashes, legacy JSON loader,
  and opt-in `write_canonical_package(..., compressed=True)`;
- registry JSON reading, logical workspace input existence and input hashes.

`write_canonical_package` keeps an already compressed file compressed when the
caller omits the compression argument. Uncompressed callers retain their prior
plain-file behavior. The immutable pipeline writer refuses existing plain OR
compressed evidence. The physical `pipeline.sha256_file` and tree inventory
functions deliberately remain unchanged: compressed files in a physical tree
are fingerprinted as their actual stored bytes and names.

The pilot covers only `receipts/season-package.effective.json` in these six
folders under `.local/season-static-qualification-v1/`:

- `2005-06-20260904-r2`
- `2005-06-20260904-r3`
- `2005-06-20260904-r4`
- `2005-06-20260904-r5-a`
- `2005-06-20260904-r6-a`
- `2005-06-20260904-r6-b`

These six snapshots happen to contain identical original bytes, each with 9,177
players. They provide a narrow compatibility proof, not a representative estimate
for every JSON family. Each original was 17,016,877 bytes; each compressed frame
is approximately 0.86 MiB. The set shrank from 97.37 MiB logical to about 5.16 MiB
allocated. Initial measured allocation released was 96,755,712 bytes (92.27 MiB).
Rollback/reapply allocation receipts may vary by filesystem metadata allocation;
do not add initial conversion and final conversion savings together.

Manifest, original file hashes/modes/descriptors, conversion journal, inline
read verification, actual rollback proof and final reapply journal are under
`.local/json-compression-pilot-20261113/`. The preferred catalogue hash locked
in the manifest is unchanged. No preferred game or registered package input was
selected. No workbook/browser path has been broadly migrated or certified for
compressed inputs: existing plain workflows are tested separately.

## Invariants for further work

- Hash original decoded bytes, including the original whitespace/newline. Do
  not reserialise a document during compression or relax canonical validation.
- Logical input descriptors retain original sizes and hashes. Physical game
  inventories retain physical sizes and hashes. Do not conflate these contracts.
- Both plain and compressed representations at once are an error. Do not pick
  whichever is newer. A corrupt frame is an error, not an absent optional input.
- Migration verifies the compressed frame before retiring a raw file and
  refuses shared inodes, symlinks, changed sources and non-JSON game assets.
- Directory advisory locks serialize cooperating helper readers and writers.
  Legacy direct readers do not honor them: convert only inactive audited inputs.
- The compressed reader limit is 512 MiB per decoded document. Retain this
  bound until larger inputs have a separately reviewed streaming implementation.
- Copy logical JSON with `copy_json`; use `iter_json_paths` for logical JSON
  discovery. Copies preserve the source's compressed/plain format by default.
  Direct os.link/shutil.copy and glob('*.json') require an audit.
- Shared helper adoption is not universal support. Hundreds of old direct
  Path reads and existence checks remain. Do not convert their inputs first.

## Commands, regression and recovery

Run commands from `/home/joe/pm99-research`. Use the existing test environment;
system Python does not have pytest installed.

```bash
.local/venvs/season-pipeline/bin/python -m pytest -q \
  scripts/test_json_storage_v1.py scripts/test_season_pipeline_v2.py \
  scripts/test_season_package_v2.py scripts/test_season_release_registry_v1.py \
  scripts/test_season_delivery_status_v1.py

PYTHONPATH=upstream/pm99-skezmod-db-editor:upstream/pm99-skezmod-patcher \
  .local/venvs/season-pipeline/bin/python -m pytest -q \
  tools/test_season_preset_browser.py scripts/test_editorial_amendment_delta_v1.py

./pm99-season validate all
./pm99-season play 2015-16 --original --check
python3 scripts/check_repo_boundary.py
```

The final storage/pipeline/package/registry/status batch passed 73 tests. The
workbook/amendment batch passed 69 tests with one existing scenario-dependent
skip. All 26 preferred releases passed release validation, and the original
2015 backup passed its full inventory/playable check. These are regressions of
the existing plain workflows, not proof of a compressed active build route.
Logs and validation results are stored in the pilot evidence folder.

Dry run and full rollback of these six files:

```bash
.local/venvs/season-pipeline/bin/python scripts/migrate_json_storage_v1.py \
  .local/json-compression-pilot-20261113/manifest.json --restore

.local/venvs/season-pipeline/bin/python scripts/migrate_json_storage_v1.py \
  .local/json-compression-pilot-20261113/manifest.json --restore --apply \
  --receipt .local/json-compression-pilot-20261113/rollback-next.jsonl
```

Use a new receipt filename each time. The manifest locks original byte hashes
and the preferred catalogue hash. If the catalogue has changed, stop and review
the scope rather than blindly changing its expected hash. The tool excludes
paths directly referenced by any release locator, registry metadata, game
directories, paths outside `.local`, path escapes and symlinks. Indirect runtime
and source dependencies still require a human/agent audit before a new manifest.

An interrupted conversion can leave both representations. Keep both, verify
them against the manifest, and review the journal before removing either. The
reader rejects this ambiguous state. Never delete a frame to resolve a missing
raw-file error without proving a good original representation remains.

## Next bounded rollout

Audit one active end-to-end recipe route: workbook discovery/editing, amendment
materialisation, builder source replay, artifact copying, direct hashes and
existence checks. Test compressed fixtures and an isolated unpreferred build.
Only after that route passes should one of its actual inputs be migrated. The
rest of the 53 GiB JSON estate is not yet covered by this pilot. Do not start a
whole-project conversion or promise the earlier sample's saving across it.
