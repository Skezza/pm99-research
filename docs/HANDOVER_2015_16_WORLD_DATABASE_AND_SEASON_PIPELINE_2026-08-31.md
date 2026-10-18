# Agent handover: PM99 2015/16 worldwide database and repeatable season pipeline

Date: 31 August 2026
Workspace: `/home/joe/pm99-research`
Current release: `.local/releases/pm99-2015-16-world`

## 1. Read this first

The 2015/16 consolidation milestone is complete. There is a playable worldwide
release, built from the approved English 2015/16 layer and a clean, fixed-size
foreign carrier projection. It has passed static auditing and remote Wine
runtime tests.

This does **not** mean every foreign record is historically perfect. The
release deliberately records source gaps and uses safe fallbacks. The finished
engineering milestone is the reproducible build and proof system; the ongoing
work is editorial improvement and creating the other seasons.

Do not restart format research or create another 2015 compiler. Start by
validating the existing workspace and receipts.

The user's real target is larger than one release:

- one database for each season from 2000/01 through 2025/26;
- the same compiler and validation gates for every season;
- hand-authored/editorial ratings where available;
- nearby-season editorial continuity, then FIFA as a fallback, then a
  deterministic contextual fallback;
- missing or unsafe portraits must use PM99's native no-photo state;
- corrections supplied as a plain list must become durable source data and
  survive clean rebuilds;
- fixed PM99 club and player capacity must be respected;
- the separate date/clock patch must not become part of the database editor.

## 2. Repository boundaries

This root repository is a research and integration workspace.

- Editor product code: `upstream/pm99-skezmod-db-editor/`
- Patcher product code: `upstream/pm99-skezmod-patcher/`
- Runtime automation: `upstream/pm99-runner/`
- Season research and orchestration: `scripts/`, `seasons/`, `docs/`
- Local game trees, caches and evidence: `.local/` and `artifacts/`

Do not put product editor code in a root `app/` or `tests/` directory. Never
commit proprietary PM99 binaries, game trees, downloaded artwork, backups or
local build outputs.

The worktree contains substantial pre-existing work in the root and upstream
submodules. Treat every unrelated change as user-owned. Do not run `git clean`,
`git reset --hard`, or broad checkout/revert commands. Inspect only the paths
you intend to touch, for example:

```bash
git status --short -- scripts seasons docs
git -C upstream/pm99-runner status --short
git -C upstream/pm99-skezmod-db-editor status --short
git submodule status --recursive
```

## 3. Current release

The stable local link is:

```text
.local/releases/pm99-2015-16-world
  -> .local/season-workspace-v1/2015-16-final-clean-game
```

Run it locally with:

```bash
cd /home/joe/pm99-research/.local/releases/pm99-2015-16-world
wine ./MANAGPRE.EXE
```

The release contains the separately qualified 2015 calendar executable. The
player, club and manager update itself is database work; the calendar change
is an executable/runtime layer and must remain a separate patcher concern.

### Release hashes

| File | SHA-256 |
| --- | --- |
| `DBDAT/JUG98030.FDI` | `e1c2f481c6eb000e4f5eb4702d7ae20afaf0cdc7fd9801f295bba4869dcc5ff0` |
| `DBDAT/EQ98030.FDI` | `cbf1d2ab077d4519ad9872027681f5bd5ee2d4857a51909f81517cf583bc7396` |
| `DBDAT/ENT98030.FDI` | `5ec1432d0a1de2800e6fc9a8d25b854fbe8e6eb263d05af8fd9ea2ba478f150a` |
| `DBDAT/MINIFOTO.PKF` | `57dda4b6ea713370a58406947db4b807c336e1eb1426cd8f2f2388ad71ac6ff9` |

The package hash is
`f8919640718fee998a5881ba6ad438298fb39fa6da21103dc444fe23ba81d400`.
The final clean-base audit hash is
`60a8f16c65bda97d9266106a6c48b1b53cbb06ae4096b0f8353f28bf15a71b72`.

Receipts are in:

```text
.local/season-workspace-v1/2015-16-final-build/
```

That directory should contain:

- `season-package.effective.json`
- `editorial-overrides.json`
- `editorial-application-receipt.json`
- `coverage-report.json`
- `missing-portraits.json`
- `database-compiler-receipt.json`
- `foreign-portrait-application-receipt.json`
- `foreign-kit-application-receipt.json`
- `clean-base-audit.json`

## 4. What is updated, preserved and missing

| Area | Release result | Important limit or fallback |
| --- | --- | --- |
| English clubs | Approved 92-club 2015/16 layer | This is a hash-locked legacy layer, not yet regenerated from a strict raw season package |
| Foreign club topology | 451 fixed carriers | No additions, country moves, league resizing or competition rewrites |
| Fully sourced foreign clubs | 395 | Remaining clubs use partial or preserved native data |
| Foreign player carriers | 9,177 native carriers | The carrier graph is fixed |
| Dated foreign player writes | 8,112 | Includes 48 partial-source rows |
| Source players omitted | 177 across 76 clubs | They do not fit the native squad capacity; omission is recorded, never hidden |
| Club writes | 395 | Other foreign club carriers remain preserved |
| Manager writes | 174 | 273 unidentified/shared manager entities remain preserved |
| Foreign portraits | 3,350 applied | 5,827 package players use named native no-photo outcomes |
| Portrait identity misses | 57 | Never guess by carrier number |
| Historical portrait download/conversion failures | 292 | Fail open to native no-photo |
| Foreign kits | 268 identity-bound club kits, 804 archive records | 127 sourced clubs retain a named native-kit fallback |
| Foreign grounds | Six dated writes | Most grounds/metadata remain source-gap or preserved |
| Competition structure | Preserved | Existing country and league topology continues to drive the game |

The foreign runtime screen can still reveal legacy names in a preserved or
source-gap slot. For example, the Barcelona route visibly included Víctor Baía
alongside the 2015 squad. Treat that as an editorial/source-coverage defect,
not evidence that the compiler failed or permission to expand a roster.

Foreign clubs are not selectable as the player's managed club. Prove them
through opponent, browser or competition screens while managing an English
club. Do not describe runtime proof as “playing as Barcelona”.

## 5. Rating policy

The fixed precedence is:

1. reviewed editorial value;
2. nearby-season editorial continuity;
3. FIFA nearest-edition fallback;
4. deterministic contextual fallback;
5. preserved native value when identity or role is uncertain.

Current foreign provenance:

| Source tier | Players |
| --- | ---: |
| FIFA nearest edition | 3,688 |
| Deterministic context | 4,374 |
| Deterministic goalkeeper handling guard | 5 |
| Partial dated source with preserved baseline ratings | 45 |
| Preserved baseline readback | 1,065 |

No foreign row is falsely labelled `reviewed-editorial`. The current foreign
layer is therefore usable but not the user's preferred final editorial mix.
Improve important players and clubs through the timeline rather than changing
the generated database directly.

Five visibly implausible goalkeeper records triggered a durable rule: handling
must not be more than 15 below overall keeper quality. Corrections were:

- Boyan Peykov: quality 69, handling 38 to 66;
- Máximo Banguera: quality 68, handling 16 to 65;
- Damián Lanza: quality 66, handling 18 to 63;
- Fábio: quality 73, handling 10 to 70;
- Milan Mitrovic: quality 67, handling 8 to 64.

The final audit has no remaining goalkeeper beyond that threshold.

## 6. Fixed-carrier rules

PM99's original graph is the capacity contract. These are release guards, not
optional preferences:

- Replace a club only within the same fixed country/league carrier family.
- Do not add clubs or enlarge a foreign league.
- Do not move a carrier from Spain to Germany or between unrelated families.
- Do not alter promotion/relegation machinery or continental draw pools.
- Do not append or recycle player records in the clean worldwide build.
- Preserve shared player references and every undeclared roster tail.
- If a historical squad is larger than native capacity, retain the most useful
  source-ordered players and record the omitted depth players.
- Variable-length names are supported only through the parser-proven alias and
  window rules. Never fall back to silent fixed-length corruption.

The clean audit proves 451 fixed foreign roster tails unchanged, zero tail
mismatches and zero append/recycle operations. Declared changes are exactly:

- 8,112 `JUG98030.FDI` player carriers;
- 395 `EQ98030.FDI` club carriers;
- 174 `ENT98030.FDI` manager carriers.

Do not use
`.local/season-pipeline-v2/world-2015-16-source-core-395-final-game-v11c`
as a compiler base. It is playable but cumulative and contains expanded
foreign roster tails and enlarged name windows.

The correct base is:

```text
.local/season-pipeline-v2/english92-clean-release-2015-16-20260830
```

## 7. Architecture and source of truth

```text
historical sources + editorial decisions
                |
                v
       strict season package
                +---- permanent cross-season editorial timeline
                +---- identity-bound portrait outcomes
                v
        year-neutral workspace
                |
        prepare + contract checks
                |
                v
       effective package + reports
                |
       clean fixed-carrier compiler
                |
       portrait stage + kit stage
                |
        clean static audit
                |
        runner runtime proof
                v
        immutable release tree
```

Durable inputs:

| Purpose | Path |
| --- | --- |
| Workspace | `seasons/2015-16/workspace.json` |
| Strict package | `seasons/2015-16/season-package.json` |
| Editorial timeline | `seasons/2015-16/editorial-timeline.json` |
| English base descriptor | `seasons/2015-16/english-layer/output-base.json` |
| Clean projection receipt | `seasons/2015-16/clean-base-projection-receipt-v2.json` |
| Portrait outcomes | `seasons/2015-16/portrait-results.json` |
| Portrait application manifest | `seasons/2015-16/assets/foreign-portrait-application-manifest.json` |
| Portrait materialisation | `seasons/2015-16/assets/foreign-portrait-materialisation.json` |
| Portrait rebind receipt | `seasons/2015-16/assets/foreign-portrait-rebind-receipt.json` |
| Kit application receipt | `seasons/2015-16/assets/foreign-kit-application-receipt.json` |
| Workspace schema | `schemas/pm99-season-workspace-v1.schema.json` |

Main implementation:

- `scripts/season_workspace_v1.py` — year-neutral `check`, `prepare`, `compile` entry point;
- `scripts/build_2015_world_strict_v2_package.py` — 2015 source adapter and native-roster fitting;
- `scripts/season_editorial_timeline_v1.py` — durable identity-bound corrections;
- `scripts/season_review_v2.py` — review/coverage normalization;
- `scripts/rebind_2015_world_portraits_to_clean_package.py` — **2015 migration bridge only**;
- `scripts/apply_2015_world_portraits.py` — reviewed portrait/no-photo binary boundary;
- `scripts/apply_2015_world_kits.py` — certified English and identity-bound foreign kit boundary;
- `scripts/audit_season_clean_base_v1.py` — final declared-change audit.

## 8. Normal validation and clean compile

From `/home/joe/pm99-research`:

```bash
python3 scripts/season_workspace_v1.py check \
  --workspace seasons/2015-16/workspace.json

python3 scripts/season_workspace_v1.py prepare \
  --workspace seasons/2015-16/workspace.json \
  --output-dir .local/builds/2015-16-prepared

python3 scripts/season_workspace_v1.py compile \
  --workspace seasons/2015-16/workspace.json \
  --base-tree .local/season-pipeline-v2/english92-clean-release-2015-16-20260830 \
  --materialisation-tree .local/builds/2015-16-game \
  --output-dir .local/builds/2015-16-receipts \
  --copy-base
```

Use new, non-existing materialisation and receipt directories for each clean
build. Never compile over a previous release.

The workspace compile covers database records. The 2015 asset stages are still
explicit:

```bash
python3 scripts/apply_2015_world_portraits.py \
  --asset-manifest seasons/2015-16/assets/foreign-portrait-application-manifest.json \
  --portrait-materialisation seasons/2015-16/assets/foreign-portrait-materialisation.json \
  --game-tree .local/builds/2015-16-game \
  --output .local/builds/2015-16-receipts/foreign-portrait-application-receipt.json

python3 scripts/apply_2015_world_kits.py \
  --materialisation .local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json \
  --english-kit-dbdat .local/season-pipeline-v2/english92-clean-release-2015-16-20260830/DBDAT \
  --english-kit-receipt .local/season-2015-16/english92-2015-16-build36-native-no-photo/kit-stage/2015-16-english-92-native-kit-receipt.json \
  --target-game-tree .local/builds/2015-16-game \
  --output .local/builds/2015-16-receipts/foreign-kit-application-receipt.json

python3 scripts/audit_season_clean_base_v1.py \
  --package .local/builds/2015-16-receipts/season-package.effective.json \
  --base-tree .local/season-pipeline-v2/english92-clean-release-2015-16-20260830 \
  --output-tree .local/builds/2015-16-game \
  --output .local/builds/2015-16-receipts/clean-base-audit.json
```

The named English kit receipt has byte SHA-256
`d23679fde80dee312f3cd16ebcaac1b996365a81b3c80280193656ca80220ba1`,
which is the hash required by the final application receipt. Several older
build folders contain the same bytes, but do not pick one by date alone. This
receipt should be promoted into `seasons/2015-16/english-layer/` and referenced
by hash before any cleanup of `.local/season-2015-16`. The final known-good
output and its complete application receipt are already preserved in
`2015-16-final-build`; rebuilding is only needed after source changes.

The old 2015 portrait conversions predate clean carrier binding. Their one-time
rebinding was done by exact normalized player identity plus fixed club, with
the original squad slot preferred. Never rebind by obsolete carrier ID. New
seasons must bind artwork directly to package identities and should not use the
2015 rebinder.

The following local cache inputs are still required to reproduce 2015 assets;
do not remove them during cleanup:

- `.local/season-pipeline-v2/world-2015-final-ownership-aware-portrait-materialisation-20260831.json`;
- the related portrait candidate and conversion cache directories;
- `.local/season-pipeline-v2/world-2015-combined-kit-materialisation-final.json`;
- the related kit candidate and conversion cache directories;
- the source candidate, disposition and ownership files under the same root.
- `.local/season-2015-16/english92-2015-16-build36-native-no-photo/kit-stage/2015-16-english-92-native-kit-receipt.json`
  until it is promoted into the durable English layer.

## 9. Tests and repository checks

The last consolidation run produced 250 passing PM99RE script tests:

```bash
PYTHONPATH=. /home/joe/ductor/.venv/bin/pytest -q scripts \
  --ignore=scripts/test_run_pm99_experiment_launcher.py
```

The complete script suite has 12 failures isolated to
`scripts/test_run_pm99_experiment_launcher.py`. Those tests expect the launcher
to proceed, while the launcher correctly refuses the currently dirty runner
checkout. This is an environment/fixture conflict, not a compiler or runtime
failure. Do not weaken the runner dirty-tree guard merely to turn those tests
green. The protected direct runner jobs succeeded.

Always also run:

```bash
python3 scripts/check_repo_boundary.py
git diff --check
```

For editor changes, use the upstream product lanes rather than root pytest:

```bash
./scripts/dev_editor.sh pytest -m deterministic -q
./scripts/dev_editor.sh pytest -q
```

## 10. Runtime proof

### Exact final guarded build: Stoke

```text
upstream/pm99-runner/docs/artifacts/pm99_runner/
  world2015_clean_final_guarded_stoke_20260831/
```

`summary.json` records:

- `success: true`;
- `crash_detected: false`;
- dashboard reached;
- squad screen matched;
- final phase `return_from_squad`;
- container exit code 0.

Summary SHA-256:
`21defbc8c88b31a426adbcbc42a9153efb25c27f11f8a92d992f29372b5c1a0c`.

Correct 2015 Stoke selection coordinates are:

```text
division: x=559, y=224
team:     x=395, y=360
```

The earlier run named `world2015_clean_final_stoke_20260831` used the old
Division 2 coordinates and selected Sheffield United. Do not cite it as Stoke
proof.

A representative direct runner command is:

```bash
upstream/pm99-runner/scripts/pm99_runner/run_stoke_route_capture.sh \
  --worker tiny-m73 \
  --division-select-x 559 --division-select-y 224 \
  --team-select-x 395 --team-select-y 360 \
  --dbdat-dir /home/joe/pm99-research/.local/releases/pm99-2015-16-world/DBDAT \
  --exe-file /home/joe/pm99-research/.local/releases/pm99-2015-16-world/MANAGPRE.EXE \
  --capture-route squad \
  --skip-setup --skip-build --skip-prepare
```

Check the runner script's current `--help` before reusing this command because
runner interfaces are upstream product code and may move.

### Foreign opponent: Barcelona

```text
artifacts/mode1_dashboard_route/
  world2015_clean_final_barcelona_opponent_20260831/
```

The route reaches the Arsenal-versus-Barcelona opponent screen and exits 0.
The useful screenshot is `screens/51_inspect_opponent.png`. This route predates
the final five-player goalkeeper guard, but none of those five players belongs
to Barcelona, so the displayed Barcelona records and assets are byte-identical
to the final release.

The runner warns that historical artifacts use about 44 GB against a configured
25 GB budget. Some old remote `game-work/work` directories are root-owned and
cannot be archived by the normal user. Current runs still work. Do not delete
broad runner history or change ownership without explicit authorization.

## 11. Portrait policy

Portraits must fail open:

- available, identity-safe, era-appropriate image: crop, convert and bind it;
- unavailable, failed download, unsafe conversion or uncertain identity:
  remove any inherited carrier photo and use native no-photo;
- record the player and reason in the machine-readable missing report;
- never substitute a random face;
- never preserve a carrier portrait after the player owning that carrier has
  changed unless an explicit identity receipt proves it is the same person.

Final 2015 clean rebinding selected 8,112 sourced foreign rows. It applied
3,350 reviewed conversions and set 4,762 to native no-photo. Across all 9,177
package players, the workspace report therefore contains 5,827 named no-photo
outcomes. Fifteen old “preserve native carrier portrait” decisions were
explicitly rejected after clean reassignment.

The user accepts missing photos for obscure players. Missing photos must still
be named so later manual review can target them quickly.

## 12. Editorial feedback workflow

The user is likely to say things such as:

- “Bojan shooting should be 86, not 82”;
- “that portrait is the wrong player”;
- “this goalkeeper's handling is too low”;
- “the starting lineup or formation is wrong”.

Translate that list into identity-bound timeline corrections. A correction
must include the season applicability, stable person/club identity, expected
old value where appropriate, new value, reason and provenance. Then rebuild
from the clean base and issue a new receipt.

Do not patch the release tree in place. Do not maintain a hand-edited binary
and a manifest separately. The timeline/package must remain the source of
truth, otherwise the 26-season programme becomes impossible to maintain.

Where the same judgment applies to several seasons, give the timeline a season
range. Where a person's identity is unresolved, stop at preserve-only until it
is identified; do not invent an identity simply to make the edit API accept it.

## 13. Formations, lineups and kits: lessons already learned

These defects have happened and must remain explicit review gates:

- A historically plausible squad can still produce a wrong opening XI if
  carrier order, role suitability and lineup seeds are not reconciled.
- Squad number does not determine the starting XI. Historic numbers and the
  opening XI are separate requirements.
- A formation can have the right players but wrong pitch coordinates. Validate
  both horizontal centering and vertical role bands in the actual tactics UI.
- A goalkeeper must be in the XI and a reserve goalkeeper should be available.
- Primary and fine/secondary roles affect automatic lineup placement. A player
  such as Bojan must not be interpreted as a centre-half merely because a raw
  role value was treated as a simple enum.
- Reusing a club carrier can leak the old club's kit. Stoke previously appeared
  in Newcastle/Wimbledon artwork. Kit identity must be bound and checked after
  the database is compiled, not inferred from the club name alone.
- `TACTIC.*` files are the global user-facing tactics library. A club's opening
  tactical state is a separate seed/derived state; do not overwrite the global
  library and claim the club formation is fixed.

For every public season, inspect at least representative title/new-game,
English squad, lineup, tactics, player profile, manager, ground, club kit and
foreign-opponent screens. Prefer automated screenshots plus DOM/window or
pixel-state assertions over visual claims alone.

## 14. Cleanup state

Superseded local build trees totalling about 1.9 GB were moved to the desktop
trash using `gio trash`; the operation was recoverable. Only these final
workspace outputs remain under `.local/season-workspace-v1/`:

```text
2015-16-final-build
2015-16-final-clean-game
```

Do not remove `.local/season-pipeline-v2` wholesale. It contains the approved
English clean base and still-required cached portrait/kit inputs. For future
cleanup, first create a file-level dependency manifest and compare every
candidate against durable receipt hashes.

## 15. What the next worker should do

### First 15 minutes

1. Read this file, `docs/SEASON_COMPILER_CONSOLIDATION_V1.md` and
   `docs/2015_16_WORLD_CONSOLIDATED_RELEASE_CLOSEOUT_2026-08-31.md`.
2. Run `season_workspace_v1.py check`.
3. Confirm the stable release link and the four release hashes above.
4. Read the final clean audit and both final asset receipts.
5. Inspect scoped git status; do not try to make the whole workspace clean.
6. Open the exact final Stoke runner summary and screenshots.

### Recommended next milestone

Create the first truly native next-season package, preferably 2000/01, using
the same workspace schema and compiler. This will prove that the consolidation
is genuinely reusable rather than merely a repaired 2015 build.

Before compiling 2000/01:

1. Create season historical sources and stable identities.
2. Bind English and foreign clubs to fixed same-country carriers.
3. Author editorial ratings for important players; use FIFA and deterministic
   fallback only when needed and record the tier.
4. Bind portraits and kits directly to package identities.
5. Add opening XI, squad number, role and formation review data as explicit
   package/editorial facts rather than post-build binary tweaks.
6. Prepare and compile twice from the clean base and compare hashes.
7. Run the static audit and the representative runner matrix.

An optional engineering improvement, before or alongside 2000/01, is to add a
year-neutral asset orchestration command so database compile, portrait apply,
kit apply and final audit produce one top-level release receipt. Preserve the
existing individual receipts; orchestration must compose them, not hide them.

### Definition of done for each new season

- Workspace, package, timeline and every declared input hash validate.
- Base inventory matches exactly.
- Club country/league carrier topology and all roster tails are unchanged.
- Every player has a rating provenance tier.
- Every package player has either an identity-safe portrait or a named
  native-no-photo result.
- Every historical kit write is identity-bound; fallbacks are named.
- Two clean builds produce identical database hashes.
- Static audit shows only declared carriers changed.
- Runtime smoke reaches an English new game and representative squad, lineup,
  tactics, manager, profile, ground, kit and foreign-opponent screens without
  a crash.
- A machine-readable release receipt and human closeout document are written.

Native Windows qualification is not a per-season data gate. If the executable,
DirectDraw wrapper or runtime packaging changes, test Windows separately. A
pure season-data rebuild that starts cleanly under the qualified Wine runner
does not need a new Windows engineering programme.

## 16. Known gaps worth improving, not re-researching

- Editorial ratings for prominent foreign players and teams are much thinner
  than the English layer.
- The 177 omitted depth players can only be changed by choosing different
  occupants for fixed slots; do not expand capacity.
- Fifty-seven portrait identities need manual reconciliation.
- The 127 kit fallbacks can be improved as identity-safe artwork is sourced.
- Preserve-only managers need real identities before safe editing.
- Foreign grounds and some club metadata need dated sources.
- The English 2015 layer is an approved cached legacy layer; converting it to a
  strict raw native package would improve provenance, but is not required to
  play or review the release.
- Asset application is separate from the year-neutral workspace compile and
  should eventually be composed by one release orchestrator.
- Repeated JSON/schema validation currently makes prepare/compile take roughly
  two to three minutes. Optimize only after preserving identical receipts.

These are visible, measurable queues. They are not reasons to abandon the
fixed-carrier model or reopen the competition format.

## 17. Key documents

- `docs/SEASON_COMPILER_CONSOLIDATION_V1.md` — architecture and release gates.
- `docs/2015_16_WORLD_CONSOLIDATED_RELEASE_CLOSEOUT_2026-08-31.md` — concise final closeout.
- `docs/2015_16_WORLD_UPDATE_PROGRAMME.md` — wider programme context.
- `docs/WORLD_2015_RELEASE_CAPABILITY_MATRIX.md` — field/research capability.
- `docs/ENGLISH92_2015_16_COMPILER_GUARDRAILS.md` — English release guardrails.
- `docs/HANDOVER_FINE_POSITIONS_2026-04-08.md` — fine/secondary position work.
- `docs/HANDOVER_FINE_ROLE_SLOT_FORENSICS_2026-04-09.md` — role-slot research.
- `scripts/README.md` — script routing and operational notes.

The correct posture for the next worker is: preserve the proven compiler and
carrier contracts, improve data through durable identities and editorial
facts, and make every season a clean deterministic build rather than a binary
editing session.
