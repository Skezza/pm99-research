# 2004/05 setup crash: fixed native player identities

## Outcome

The intermittent “Application cannot continue” during a new 2004/05 game was
isolated to cloned players retaining their template's internal player ID.
The normal play command now selects `native-player-identity-20261003-r10`.
The original executable, calendar, squads, names, abilities, kits and photos
are unchanged. Only the two native ID bytes of 161 appended players changed.

```sh
./pm99-season play 2004-05
./pm99-season validate 2004-05
```

Start a new game. This repair does not rewrite existing saved games.

## Cause and controlled evidence

The native player lookup returned null for ID 7952 during spare-player
nationality counting. `FUN_004b7840` then dereferenced it at `0x004b7867`.
Two independent native traces identified the same missing ID. A full linear
scan of the player map confirmed it was absent, rather than hidden by an
unsorted map. ID 7952 was the clone template (Dennis Bergkamp).

In the failing JUG file, 161 appended directory entries had fresh IDs but
their raw payload offsets 5–6 all still contained 7952. Native payloads have
their own uint16 ID; copying their names/body under a new directory key does
not change that ID automatically. Native player removal/replacement uses
these internal identities. The evidence establishes the defective identity
contract and its causal effect on this setup route, not every individual
cleanup operation that occurs during initialization.

The game calls `srand` twice during initialization. Disposable diagnostic
EXEs pinned both calls to `0x4ae9e66f`, giving a paired failure/success test.
No seeded or guarded executable was promoted to a release.

| Run tag | Difference | Result |
| --- | --- | --- |
| `crash04_seed_control_20261003_a` | Original JUG; fixed-seed EXE | Native access violation at `004b7867` |
| `crash04_identity_fixed_seed_20261003_a` | Corrected ID bytes; **same** fixed-seed EXE | Stoke Line-Up passed |
| `crash04_identity_original_exe_20261003_a` | Corrected IDs; unchanged release EXE | Stoke Line-Up passed |
| `crash04_identity_original_exe_20261003_b` | Independent fresh start; unchanged release EXE | Stoke Line-Up passed |
| `crash04_identity_release_20261003_a` | Registered r10; exact manifest/inventory binding | Stoke Line-Up passed and attested |

Artifacts are retained under `.local/runlogs/pm99_runner/<run-tag>/`.
The registered screenshot is
`.local/runlogs/pm99_runner/crash04_identity_release_20261003_a/screens/022_line_up_inspect.png`.
The runner independently OCR-matched “Stoke City”, not just the selector
coordinates. Registered release validation passed; full 2004/05 season QA
passed with zero blockers and four existing editorial warnings, recorded in
`.local/season-qa-v1/native-identity-r10/2004-05/qa-report.json`.

Earlier mixed-database, calendar and unused-player append controls sometimes
passed but also failed on repetition. They did not establish a cause. The
previous claim that moving the May calendar event fixed setup was withdrawn
from the patcher's explanatory comment. That existing calendar byte was
deliberately left unchanged during this controlled identity repair.

## Bounded repair and hashes

2004/05 JUG before:
`b47e17bc474bc38b9f017c11ae8c6f1a55f968f0a905e81a945cb49d46b041b9`

2004/05 JUG after:
`8d6688ef43faba31214a026f52ac623632b9c6e9503d42c17ce0d27343ded16f`

Unchanged executable:
`ffb2e87b85149ff50b0a8373ba631a49cdeb61faa3073512d8b86a972ae424fc`

Current release-manifest file SHA-256:
`76307a7795cfd3d7bdfd31c616ef1ea03bcbcaa53dc50eec4e74e0cedc62f7c9`

Current game inventory fingerprint:
`201eca7b29b8c579802af5205b873f2ef6b30a077cd31f066b7db24247879ae3`

The repair receipt records every old ID, new directory ID and exact byte
offset. Its byte contract binds unchanged EQ and ENT hashes. A full inventory
comparison permits only `DBDAT/JUG98030.FDI` to differ. Directory entries,
payload lengths, string/skill bytes and every artwork asset remain unchanged.
Old game directories are retained; unchanged files use hardlinks, while the
new JUG is atomically replaced to avoid writing into the old release.
Do not edit release binaries through those shared hardlinks.

## Cascade and prevention

All 25 non-2015 generated releases had this defect. Every mismatch matched
the exact append donor declared in its unchanged recipe. Across them, **4,204
player identities** were repaired and new r10 releases selected. The original
2015/16 release had no mismatch and remains unchanged.

All 26 preferred releases now pass the complete native player-ID audit and
the playable-file/hash check. The report is
`.local/season-identity-repairs-v1/cascade-audit.json`. New JUG storage totals
137,209,594 bytes (about 131 MiB); full game/artwork trees were not duplicated.
Old runtime attestations and QA results were not inherited into new releases.
Fresh captures are required before claiming all repaired seasons are
runner-verified. Identity/hash checks alone are not 26 new gameplay proofs.

Fresh, exact-r10 Stoke captures also passed and were attested for 2000/01
(`identity_release_2000_01_20261003_a`) and 2025/26
(`identity_release_2025_26_20261003_a`). Together with 2004/05, those are three
newly runner-verified repaired releases; the other 22 repaired releases still
need fresh r10 captures. The unchanged 2015/16 proof remains separate.

The compiler now rebinds IDs for explicit appends, implicit clones and
recycled compact players, then checks all native JUG entries at read-back.
Season QA independently checks the same contract and fails on a mismatch.
The shared implementation lives in upstream
`app/indexed_jug_identity.py`. Small native IDs are also no longer mistaken
for name-string lengths by the native prefix reader.

The bounded correction is re-runnable without rescraping or regeneration:

```sh
python3 scripts/repair_registered_player_identities_v1.py all --register
```

Already-correct seasons are skipped. Undeclared mismatches fail closed.
Receipts live beside each new game in
`.local/season-identity-repairs-v1/<season>/native-player-identity-20261003-r10/`.

## Regression checks and diagnostic limits

- Compiler, recipe repair and QA tests: 40 passed.
- Upstream deterministic lane: 454 passed, 4 skipped, 47 deselected with
  `--ignore=tests/test_gui_refresh_v1.py`. The unrestricted lane cannot collect
  that GUI test because this workstation's Python lacks `tkinter`; this is
  not reported as a fully clean unrestricted test run.
- Runner crash/debug targeted tests: 3 passed.
- Repository boundary and shell syntax checks passed.

Native tracing now reaches the gameplay container (`--wine-debug` previously
affected only an editor probe container). An opt-in diagnostic forwarding DLL
and forced-import EXE were used to inspect native state; a null-lookup guard
was tested as a control. **None** of the trace DLL, import patch, pinned random
seed or null guard is installed in the preferred games. Failed diagnostic
runs remain evidence, not supported playable versions.
