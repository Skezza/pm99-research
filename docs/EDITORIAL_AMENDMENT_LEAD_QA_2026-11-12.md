# Spreadsheet edits now reach a playable game

An actual Claude Sonnet 5.5 worker implemented the bridge. The lead independently reviewed it, returned concrete failures for correction, integrated the native writer into the canonical editor library and tested the final result. Claude session: `c238221e-62d2-4ec1-ae9e-9c4207203a62`. Machine: `joe-Vostro-3350`; Codex source session: `01a0592d-fcd5-7262-a637-743a8253d9b4`.

This closes the bounded spreadsheet-to-game engineering milestone. It does **not** close the historical 26-RC checklist or demonstrate fresh 1990 recipe generation.

## What was proved

The real browser staged three artificial 2022/23 test edits: Ackroyd from midfield to forward, passing 58 to 77, and manager Potter to Hudson. Native readback proved only that player's record and that manager's record changed. Every other game file, player, roster, tactic, kit and photo remained intact.

A second Playwright run selected that candidate, changed shooting 31 to 41, and built another game. Independent comparison found **exactly one changed game byte**. Passing 77, the forward/central-striker role and manager Hudson remained intact. A fresh reconstruction reproduced the complete second recipe and game inventory.

The lead personally inspected genuine local runner profiles for both candidates. They show passing 77 and the forward role; the second also shows shooting 41. Both runner transport and input checks passed, and canonical game inventories remained intact. The manager name was independently verified in Native ENT; it was **not** visually verified on a manager screen. A Stoke lineup capture also passed for the first candidate.

The worker additionally built and exactly reconstructed 2005/06 and 2018/19 demonstrations through the same generic code. No per-season amendment module was added.

These are deliberately artificial QA candidates, not historically approved corrections. None was made preferred.

## Failures caught and corrected

- An unrelated missing weight or preserved shirt incorrectly blocked rating edits. Real Sparrow and Casemiro probes now pass planning; a 2015/16 Varane compact-record rating edit also passes.
- Failed validation or requested reconstruction now returns failure, retains evidence and supplies no successful play result.
- Repeat requests retain earlier reports and immutable verification proofs, distinguishing previous evidence from checks performed now.
- The full-image cache is bounded and rechecks source hashes on every use.
- Record-specific restrictions appear as locked cells with reasons, and the server also refuses unsupported edits. Outfield choices omit goalkeeper conversions; a rejected selection restores the old displayed value.
- Existing candidates are checked against their entire game inventory and registered recipe hash before reuse.
- Native position/body writes use the canonical editor library, with identity, preimage, range, directory and exact-byte guards.

## Validation

Lead runs after final integration:

| Check | Result |
|---|---|
| Focused amendment, workbook, publisher/compiler and original-play tests | 185 passed, 2 skipped |
| Registry and play import-isolation tests | 9 passed |
| Upstream deterministic lane | 686 passed, 4 skipped |
| Upstream full suite | 690 passed, 47 skipped |
| Real Playwright staging, build, repeat-edit and capability checks | Passed, no page errors |
| Actual preferred games: playable checks and existing runtime-attestation checks | 26/26 passed |
| Original 2015 backup: playable hashes and complete inventory | Passed |
| Preferred catalog hash | Unchanged: `495789e1691b9c792ddd53e4fb1eedeb107593bef7776a20a1886b44c10efd2b` |
| Normal repository boundary and whitespace checks | Passed |

The full root repository suite is not claimed green: the worker reproduced 14 unrelated reconstruction-test failures at the starting HEAD. The stricter local boundary scan also finds an existing August-era `upstream/.local/season-2015-16` containing two source ledgers; these were preserved. Other workers' staged reconstruction submodule and existing dirty documentation/artifact deletions were preserved.

The first upstream test collection lacked tkinter. Genuine Ubuntu Python/Tk packages were extracted into the ignored QA directory, without changing the system; both upstream lanes then passed. No dependency or GUI stubs were used to fake a pass.

## Limits that remain visible

The bridge supports ratings, representable nationalities, supported scalar facts, full-record outfield positions and written-manager names. It does not support player names, club labels, roster/lineup ownership, manager links, direct fine-role editing or goalkeeper conversions. Some record formats and preserved fields remain read-only.

The legacy 2015/16 preferred main recipe contains 9,177 players and does not contain the Stoke English squad; its English sidecar is not yet supported by this amendment bridge. The successful Varane probe proves compact-record rating support, **not** complete 2015 editing coverage. The original 2015 backup remains separate and unchanged.

Current preferred releases remain installed exactly as before. Candidate captures have not been registered as formal runtime attestations or preferred releases. The historical checklist remains v298, with its original counts intact; the report's seven additional findings open or needing reading are not the complete remaining RC workload.

## Use

Start `python3 tools/season_preset_browser.py`, choose the year, edit supported cells, then use **Check edits** and **Build playable candidate**. No JSON upload or materialisation step is needed. The result provides the exact play command. Choose a built candidate as the next edit base to preserve earlier edits.

Default disk reserve is 8 GiB. The supported `--minimum-free-bytes` option allows an explicit reserve, never below 6 GiB. The lead's bounded browser test used 6.25 GiB after measuring capacity; no hard guard was removed.

`./pm99-season report` regenerates current status from the catalog and checklist, separating actual checks, cached declarations, confirmed findings and unreviewed candidates. See `docs/EDITORIAL_AMENDMENT_BUILD_ROUTE_2026-11-12.md` for the field contract and CLI examples.

## Local evidence

All files below `.local/claude-implementation-20261112/`:

- `events.jsonl`, `events-round1.jsonl`, `first-report.md`, `corrected-worker-report.md`: actual worker activity and responses.
- `browser-initial.json`, `browser-chain-proof.json`, `browser-final-proof.json`: real browser checks.
- `workbook-real-chained-build.png`, `workbook-child-values.png`: genuine Playwright screenshots.
- `lead-native-proof.json`, `lead-chain-native-proof.json`, `lead-chain-source.json`: independent byte scope and reconstruction.
- `lead-runtime-review.json`: personal review bound to actual screenshot hashes.
- `lead-final-tests.log`, `lead-final-import-registry-tests.log`, `upstream-deterministic-with-deps.log`, `upstream-full.log`: test results.
- `all-season-status-final/`, `original-2015-final-check.json`: preserved release checks.
- Cleanup ledgers preserve the exact scope of lossless dedup and removal of completed, regenerable pytest fixtures and this run's inactive RAM game. No source/game release was deleted.

Genuine runner frames:

- `.local/runlogs/pm99_runner/local_editorial_bridge_ackroyd_20261112_v1/screens/49_inspect_ackroyd_profile.png`
- `.local/runlogs/pm99_runner/local_editorial_bridge_child_ackroyd_20261112_v1/screens/49_inspect_ackroyd_profile.png`

The daily workbook is running at `http://127.0.0.1:8765/` against the normal owner workspace. QA drafts stayed in a separate root. Artificial QA candidates were removed only from its daily menu, with exact menu backups and a retirement ledger; all registered demo games and evidence remain intact.
