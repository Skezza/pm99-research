# PM99 3D Player Appearance Contract Investigation (2026-08-28)

## Question

Can a seasonal database make the players in PM99's 3D match view look more
like their historical counterparts: especially skin tone and hair colour? Is
that data in the player record or in another file?

## Answer So Far

It is a two-layer system, with one important open link.

1. The 3D visual assets are not individual player models. `SIMULDAT` contains
   shared models, stadium resources, cameras, and a shared face-texture archive.
2. `SIMULDAT/Texturas/CARAS.pkf` is a concrete shared face-texture catalogue:
   it contains 108 indexed 64x64x8 BMP records. `MANAGPRE.EXE` contains the
   resource path prefix `simuldat\\texturas\\caras\\cara` and initialises that
   resource family in `FUN_005f2d3f` (`0x005f42fd` is the path callsite).
3. Indexed `JUG98030.FDI` player payloads have two low-cardinality bytes at
   the validated suffix anchor `+9` and `+10` (`indexed_unknown_9` and
   `indexed_unknown_10`). They are plausible *selectors* for the shared face
   family, but that link has not yet been proven. They remain preserve-only.
4. Player mini-photos are a separate, solved 2D asset contract in
   `DBDAT/MINIFOTO.PKF`; they do not determine the 3D match model.

Therefore the likely route to historically closer 3D players is to select from
PM99's fixed shared heads/palettes, not to store a full 3D model or a portrait
per player in `JUG98030.FDI`.

## What Is Definitely Not Appearance Data

The six suffix bytes at `anchor + 2 .. + 7` were previously named
`face_components` in parts of the tooling. That name is wrong.

They are PM99's fine-position sequence:

- each non-zero decoded byte maps to a role code `0..17`;
- `MANAGPRE.EXE` `FUN_004afd80` reads the sequence into player runtime role
  slots;
- the game exposes those slots through its tactics role chooser; and
- examples include `Inside Centre Left`, `Inside Centre Right`, `Centre
  Forward`, `Striker`, and `Defensive Midfielder`.

They must be preserved and handled by the position editor, never repurposed
for hair, skin, portraits, or 3D heads. The legacy parser/API name remains only
until a compatible rename can be planned.

## Evidence

### Shared 3D asset layer

- `scripts/probe_simuldat_pkf_layout.py` finds 108 records in `CARAS.pkf`.
- A repeatable 2026-08-28 run against the current 2015 test tree found all
  108 to be 64x64, 8-bit BMPs, with 99.09% byte coverage by the PKF table.
- `MANAGPRE.EXE` contains the literal
  `simuldat\\texturas\\caras\\cara` at `0x0073f4fc`; Ghidra cross-reference
  `0x005f42fd` shows its resource-loader callsite.
- The P3D corpus contains shared match scenery/models rather than player-keyed
  personal models. The 190 identified P3D records occur in `Modelos.pkf`,
  `Camaras.pkf`, `Cespedes.pkf`, and stadium archives; none is keyed by player
  record id.

### Candidate player-side selector data

- A current 11,479-player JUG corpus has 2,126 reliably anchored indexed
  payloads.
- Across that anchored subset, `(u9, u10)` has only 12 observed combinations.
  The largest are `(1,6)` with 874 rows, `(1,3)` with 570, `(1,1)` with 352,
  and `(2,3)` with 157. `u9` takes three observed values and `u10` takes six.
  That is categorical-selector-shaped data, not a normal stat. The `3 × 6`
  shape is suggestive beside CARAS's 108 assets, but it is not proof of an
  exact selector formula or a field meaning.
- Ghidra now shows the `MANAGPRE.EXE` player loader preserving the two bytes in
  its runtime player object. Immediately after its six-slot fine-position
  loop, `FUN_004afd80` stores the next metadata bytes at runtime offsets
  `+0x1A` and `+0x1B` (`0x004afe6f` and `0x004afe79`); the following byte goes
  to `+0x1C`, the known coarse-position field. Given the validated on-disk
  order, `+0x1A/+0x1B` are `u9/u10`. This proves they survive from JUG into
  live player state, but not yet which match-renderer routine consumes them.
- It is not yet acceptable to label `u9` as skin tone or `u10` as hair colour:
  the current correlations are inherited from carrier players in seasonal
  builds and static inspection does not prove the renderer consumes them.

## Feasibility

### Existing PM99-style choices: feasible, after a small research closure

The evidence makes an editor field such as **3D appearance preset** plausible.
It would select only existing PM99 shared face/head resources, retain the
original game's style, and require no new player geometry.

Before exposing it as writable, we must prove all of the following:

1. change one candidate selector byte on one disposable player record;
2. capture a controlled 3D match view on the runner;
3. show that only the intended visible trait changes and that tactics,
   positions, player bio and match startup remain sound;
4. repeat for every accepted selector value and for both sides of the match;
5. map the selector value(s) to the exact CARAS texture/palette resource(s);
6. reopen the data file and prove unrelated bytes are unchanged.

This is a bounded research task, likely a few focused experiments once the
runner's 3D capture route is connected to a DBDAT overlay. It is not an
executable rewrite.

### New historical faces/haircuts: a separate asset-pipeline project

Making a player look recognisably like a specific 2015 footballer needs new
face textures (and may need new or altered meshes). That is not a normal
database edit. It requires:

- decode the CARAS PKF descriptor/name table;
- build and test a byte-identical no-op repacker;
- prove same-size texture replacement first, then changed-size/reindexed
  resources if necessary;
- determine the head/texture selection algorithm and palette constraints;
- validate memory use and live 3D rendering on the runner.

That work should be a separately versioned graphics mod, optionally installed
alongside a season database. It must not block a faithful Core80 season release.

## Product Guardrails

- Keep `u9`, `u10`, and the six fine-position slots read-only/preserve-only in
  the database editor until the controlled runtime proof is complete.
- Keep `MINIFOTO.PKF` editing separate from match-view appearance. It is the
  player bio portrait pipeline.
- Do not infer a person's appearance from nationality or source-data guesses.
  When appearance fields are safe, the season manifest should carry explicit,
  reviewable preset choices.
- Do not change `SIMULDAT` in a season database release unless a graphics
  overlay is explicitly selected and has its own integrity checks.

## Next Experiment

Extend the runner's existing `--match-view-capture` path to accept a verified
`--dbdat-dir` overlay, then run a baseline-versus-one-byte experiment using an
unchanged first-fixture side. Capture the same camera frame after changing one
candidate `u9` or `u10` value. Fail closed if no stable visual delta can be
measured.
