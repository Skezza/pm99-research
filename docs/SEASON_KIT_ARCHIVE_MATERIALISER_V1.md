# Generic seasonal kit-archive materialiser V1

`scripts/materialise_season_kit_archives_v1.py` is the write-once mechanical
stage between a verified render binding and a later disposable game
materialisation. It is deliberately not a release command.

It consumes only:

- a `pm99-season-kit-render-bindings-v1` file;
- its matching `pm99-season-kit-render-receipt-v1` file; and
- a clean `DBDAT` whose three compact-kit archive hashes exactly match the
  clean base recorded by that render receipt.

For every rendered carrier, the binding and receipt must agree byte-for-byte
on the three `kit-render` artifact declarations. Each artifact must be a
regular file below the bindings directory with its declared SHA-256, a valid
8-bit OS/2 bitmap, the exact base bitmap dimensions and layout, and unchanged
non-pixel bytes. The base records are checked again at write time.

The command writes a new directory containing only the copied-and-patched
`MINIESC.PKF`, `NANOESC.PKF`, and `RIDIESC.PKF` archives plus
`kit-archive-materialisation-receipt-v1.json`. It refuses an existing output
directory; the clean base, render artifacts, package, and game tree remain
untouched.

```bash
python3 scripts/materialise_season_kit_archives_v1.py \
  --kit-render-bindings .local/season-kit-renders-historical-backfill-v1/2000-01/kit-render-bindings-v1.json \
  --kit-render-receipt .local/season-kit-renders-historical-backfill-v1/2000-01/kit-render-receipt-v1.json \
  --clean-dbdat .local/season-workspace-v1/2015-16-final-clean-game/DBDAT \
  --output-dir .local/season-kit-archive-stages-v1/2000-01-r1
```

The receipt states `release_eligible: false`. A later orchestration step must
put these archives into a newly created complete game materialisation, apply
the other required asset stages, compile/audit the package, and collect
target-neutral runtime evidence. It must not treat this archive receipt as
proof of a playable database.

Fixture coverage is in
`scripts/test_materialise_season_kit_archives_v1.py`: matching fresh inputs
materialise three new archives; stale base provenance, unsupported bitmap
format, binding collision, and overwrite are rejected.
