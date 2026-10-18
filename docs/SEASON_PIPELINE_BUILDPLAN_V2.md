# PM99 Season Build-Plan Runner V2

## Purpose

`scripts/season_pipeline_buildplan_v2.py` turns the metadata rules in
[Season Pipeline V2](SEASON_PIPELINE_V2.md) into an executable, fail-closed
materialisation flow.

It is deliberately generic. It does not call the existing 2015 compiler,
portrait pipeline, kit pipeline, or calendar patcher directly. Those scripts
were built as research/release tools before this interface existed and must not
be wrapped by guesswork. Each needs an explicit adapter with its own tested
contract first.

```text
canonical build plan + verified base + canonical season package + local adapters
                                      |
                                      v
                              new disposable game tree
                                      |
                         ordered reviewed adapter stages
                                      |
                                      v
                       V2 manifest + build-plan receipt outside game tree
```

## Build-plan contract

A plan is strict canonical JSON: sorted keys, compact separators, and one
trailing newline. It has no local paths. The runner rejects pretty-printed or
otherwise reformatted plan files even when their parsed JSON is equivalent.
That makes the plan's SHA-256 a meaningful review and release identifier.

The required top-level fields are:

```json
{
  "schema": "pm99-season-build-plan-v2",
  "season": "2015-16",
  "base": {
    "base_id": "pm99-gog-en-1.00",
    "inventory_fingerprint": "<sha256>"
  },
  "season_package": {
    "canonical_sha256": "<sha256>",
    "canonical_size": 123,
    "schema": "pm99-season-package-v1"
  },
  "external_artifacts": [],
  "forbidden_runtime_state_directories": [
    "CACHE", "RUNTIME", "SAVE", "SAVEGAME", "SAVEGAMES", "SAVES", "TEMP", "TMP"
  ],
  "stages": [],
  "expected_final_output_inventory": {}
}
```

Each stage is explicitly ordered and declares:

- a unique `id` and contiguous numeric `order`;
- one local command ID, the SHA-256 of that executable adapter, a list of
  literal arguments, and a timeout;
- a unique, sorted set of exact output **files**;
- the expected V2 stage receipt, locking both `base-tree` and
  `season-package` input hashes; and
- a complete expected inventory for exactly those output files.

Stage outputs can never overlap. A stage may alter only its declared files; a
changed base file, extra file, new undeclared directory, symlink, save/cache
directory, missing output, or output whose byte hash differs from the plan is
a hard failure. The plan also declares a complete final inventory, including
the unmodified base files, so a stage cannot simply produce plausible outputs
while leaving the overall tree wrong.

`SAVE`, `SAVES`, `SAVEGAME`, `SAVEGAMES`, `CACHE`, `RUNTIME`, `TEMP`, and
`TMP` are mandatory forbidden directory names. A plan may add stricter guards,
but may not omit these. Build from a base that already has such runtime state
is rejected as well.

## Local-command boundary

The plan names a local command by logical ID and hash, not by a machine path.
The invocation maps that ID to a regular, directly executable local file:

```bash
python3 scripts/season_pipeline_buildplan_v2.py \
  --plan seasons/2015-16/build-plan.json \
  --verified-base releases/bases/pm99-gog-en-1.00.json \
  --base-tree /secure/pm99-base \
  --season-package seasons/2015-16/season-package.json \
  --materialisation-tree work/2015-16-a/game \
  --metadata-dir releases/2015-16/r1 \
  --local-command database-adapter=/opt/pm99-tools/database-adapter \
  --local-command portrait-adapter=/opt/pm99-tools/portrait-adapter
```

The runner verifies that the supplied command IDs exactly match the plan and
that each supplied file hash matches the command hash and its V2 stage receipt.
It uses `subprocess.run([...], shell=False)`: no shell string, wildcard,
redirection, environment assignment, or unlisted command is interpreted.

Only these exact argument placeholders are allowed:

- `{base-tree}`
- `{materialisation-tree}`
- `{season-package}`
- `{external-artifact:<artifact-id>}` for an external artifact already
  declared and hash-verified in the build plan.

All other plan arguments must be relative/non-escaping literals. The adapter
is still trusted code—it runs on the local machine—but reviewed plans cannot
accidentally point it at an arbitrary absolute path or execute an undeclared
tool.

## Adapter boundary for the existing compiler stages

Do not claim V2 orchestration for a legacy stage until it has a purpose-built
adapter. An adapter must:

1. Accept only the three declared inputs plus reviewed relative options.
2. Write only the exact files declared by its stage.
3. Avoid saves, caches, logs, screenshots, temporary directories, and any
   mutable state inside the materialisation tree.
4. Produce the same file bytes for identical inputs.
5. Have a hashed, directly executable launcher suitable for both the target
   host and its documented runtime.
6. Be independently tested against its expected stage output inventory.

For example, a future database adapter may call the generic season schema
compiler and write the permitted `FDI` outputs. A portrait adapter may read an
already-hashed crop catalogue and write the declared archive files. A kit
adapter and calendar adapter follow the same pattern. Their parameters and
tool/source hashes belong in their V2 stage receipts. No prior generated game
folder is an adapter input.

The current 2015-specific scripts are not silently put behind these names. The
next work is to add real adapter contracts one at a time, starting with the
generic database compiler once its season schema is ready.

That database adapter now exists as
[`season_package_compiler_v2.py`](../scripts/season_package_compiler_v2.py).
Its exact write surface, review-overlay workflow and remaining binary limits
are documented in [Season-Package Compiler V2](SEASON_PACKAGE_COMPILER_V2.md).
It is the first adapter that has passed a real synthetic JUG/EQ/ENT build-plan
double materialisation. Portraits and kits remain separate adapters rather
than being silently folded into its contract.

The target-calendar boundary in
[`materialise_season_calendar_v1.py`](../scripts/materialise_season_calendar_v1.py)
also supports the explicit `--build-plan-adapter` mode. In that mode it accepts
the plan's package/tree placeholders plus four hash-verified external artifacts
(calendar-binding audit, patch receipt, executable, and verified-base
descriptor), changes only `MANAGPRE.EXE`, emits its full fail-closed receipt on
stdout, and writes no receipt into the game tree. Its focused integration test
executes the real adapter through this build-plan runner and verifies the final
manifest and inventory. Calendar runtime validation remains a separate,
pending gate.

## Reproducibility gate

For each season release:

1. Create the canonical plan after all expected stage and final inventories
   are known and reviewed.
2. Materialise clean tree A from the verified base; the runner writes
   `season-manifest.json`, both full inventories, and `build-plan-receipt.json`
   outside the game tree.
3. Materialise clean tree B with the identical plan and inputs.
4. Use `season_pipeline_v2.py double-build` on A and B. It must report equal.
5. Attach native-Windows and other runtime evidence afterwards through the
   separate V2 attestation flow.

The automated integration test uses a tiny fake adapter to prove this exact
flow. It deliberately avoids a false integration claim for portraits, kits,
or legacy database writers.
