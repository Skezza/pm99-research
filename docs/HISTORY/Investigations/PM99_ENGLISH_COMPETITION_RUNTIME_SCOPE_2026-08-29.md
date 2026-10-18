# PM99 English-save competition runtime scope (2026-08-29)

## Decision

An English-managed PM99 game has an English league-table model and a separate
continental-competition draw model. It does **not** expose a foreign domestic
league table from which a browser editor could safely infer or rewrite Spanish,
German, Italian, French, or other club membership.

The correct remaining research target is the **live continental draw candidate
pool**: the point at which PM99 turns a scheduled `???` opposition slot into a
specific foreign club. It is not a generic country/division metadata field.

Until that pool and its source are traced, the world compiler must preserve
foreign country/competition topology exactly. It may only update existing
foreign carriers through already-green, game-facing transactions (club text,
ground, seated capacity, manager link/name, roster, supported player facts,
compact kit, and photo/no-photo decision).

## Fresh-game evidence

All captures use an untouched executable and a disposable runner game.

| Managed club | Actual PM99 surface | Result | Evidence |
| --- | --- | --- | --- |
| Arsenal | League Tables | The four selectable tables are Premier, First, Second and Third. The panel contains the expected 20 English Premier League clubs. | `.local/runlogs/pm99_runner/competition_english_baseline_20260829/screens/021_league_tables_inspect.png` |
| Arsenal | Fixtures calendar | The calendar contains PM competition event types alongside English league dates. Advancing the calendar is read-only; it does not simulate time. | `.local/runlogs/pm99_runner/competition_calendar_sweep_v2_20260829/screens/021_fixtures_next_month_01.png` |
| Arsenal | 15 October event | PM99 opens `ARSENAL - ???`, `PM League Trophy`, `Round 3`, `MATCH ON DATE 15/10/1998`. The opponent has not been drawn yet. | `.local/runlogs/pm99_runner/competition_calendar_oct15_20260829/screens/022_fixtures_calendar_click_01.png` |
| Manchester United | 12 August event | PM99 opens `MANCHESTER UTD. - ???`, `PM Champions League`, `Round 2`, `MATCH ON DATE 12/8/1998`. This is a real continental competition seed, but it still contains no club id/name before the draw. | `.local/runlogs/pm99_runner/competition_manutd_champions_seed_20260829/screens/023_fixtures_calendar_click_01.png` |
| Manchester United | Teams in Championships | PM99 explicitly seeds the English entrants: Manchester United and Arsenal (Champions League); Blackburn, Liverpool, Aston Villa and Leeds United (Euro Trophy); Newcastle and Chelsea (Cup-Winners). The only named foreign entrants on this surface are Real Madrid (European Super Trophy and World Club Trophy) and Vasco da Gama (World Club Trophy). | `.local/runlogs/pm99_runner/competition_manutd_champions_resolution_20260829/screens/030_startseason_continue_retry.png` |
| Manchester United | Draw | The `PM CH. LGE. ROUND 2` draw screen is live and has an initially empty match grid. | `.local/runlogs/pm99_runner/competition_manutd_champions_resolution_20260829/screens/033_championships_continue_retry.png` |
| Manchester United | Start of Season | The English-club season surface lists English objectives: Arsenal, Chelsea and Liverpool show `PM Euro Trophy`; Manchester United shows `Champion`. | `.local/runlogs/pm99_runner/competition_manutd_champions_resolution_20260829/screens/034_competition_round_continue.png` |
| Manchester United | Resolved opponent | After the live Round 2 draw, the calendar resolves the seeded `???` to `MANCHESTER UTD. - VALLETTA`; the return leg is also named Valletta. The parsed carrier is existing mode-1 EQ record 2151. | `.local/runlogs/pm99_runner/competition_manutd_postdraw_fixture_v2_20260829/screens/039_fixtures_calendar_click_01.png` |
| Manchester United | Reversible carrier identity proof | In a new disposable run, the released indexed-EQ team-name rebuild changed EQ 2151 from `Valletta` to `Test Valletta` (payload 1,957 -> 1,962 bytes). The fresh fixture and return leg both show `Test Valletta`. | `.local/runlogs/pm99_runner/competition_valletta_name_live_v2_20260829/screens/039_fixtures_calendar_click_01.png`; `team_apply/team_edit_probe_summary.json` |

The fixture/capture runner records a normal `success: true` result for the
Manchester United draw route. The later live-name run also records the editor
write, backup and parser reopen as successful before PM99 reaches the changed
fixture. The wrapper's earlier final non-zero shell exit came from best-effort
archival of old permission-owned remote runs, after artifact sync; it is not a
PM99 crash or a failed game capture.

This confirms the practical gameplay hierarchy. The game seeds English
entrants into its continental competitions directly; it does not show a
foreign domestic season from which those entrants are calculated. The two
named foreign entries prove that some foreign club identities can be
competition-relevant, but they do not turn all 451 foreign carriers into a
foreign-league simulation model. The Valletta rename goes one step further:
the resolved draw holds an identity for existing EQ 2151 and reads that
carrier's database-backed, variable-length short name live. It still does not
reveal where PM99 stores or constructs candidate-pool membership.

## Read-only runtime object and raw-ID trace

A further fresh, disposable Manchester United run repeated the released
`Valletta` -> `Test Valletta` rebuild, completed one real fixture, and reached
the Round 2 calendar. The runner deliberately left Manchester United's opening
tactics untouched in this trace: this isolates the competition lookup from the
separate, UI-driven tactics experiment. The run succeeded (`success: true`,
one completed match) and its calendar reads `MANCHESTER UTD. - TEST VALLETTA`.

The named live-object trace is repeatable in that runtime snapshot:

| Evidence | Observation | Meaning |
| --- | --- | --- |
| Loaded carrier strings | `Test Valletta` is at `0x040ebfd0`; its adjacent decoded strings are Ta' Qali, Valletta F.C., Hibernians and other loaded foreign-carrier text. | This is the loaded EQ-carrier region, not merely OCR text. |
| Two references to the short-name pointer | Fields at `0x01899884` and `0x0189988c` point to `0x040ebfd0`. | A candidate loaded team object begins four bytes before the first field. |
| Candidate object values | In this snapshot: `+0x00` -> Ta' Qali, `+0x04` -> short name, `+0x08` -> full name, `+0x0c` -> duplicate short-name pointer, `+0x10` -> `0x867` (2151), `+0x14` -> `0x4268` (17,000). | This independently corroborates the EQ-2151 identity, stadium and capacity at runtime. It is an observed object layout, not a general write contract. |
| Fixture copies | Two additional `Test Valletta` strings appear in separately allocated calendar/fixture blocks with Manchester United and Round-2 labels. | PM99 copies the loaded carrier identity into generated fixture state. Editing either copy would not be a database edit. |

Artifacts: `.local/runlogs/pm99_runner/competition_valletta_id_table_v5_20260829/summary.json`,
`screens/036_fixtures_calendar_click_01.png`,
`memory/fixtures_calendar_click_01.json`, and
`memory/fixtures_calendar_click_01_hex.json`.

The same state was scanned read-only for the little-endian record-id bytes
`67 08` (2151). One hit lies inside an ordered run of small 16-bit values. A
host-process mapping check closes that lead conclusively: the address
`0x003dcf46` is inside Wine's mapped
`/usr/share/wine/nls/normnfc.nls` Unicode-normalisation resource, rather than
any PM99 executable, EQ, JUG or ENT allocation. The coincidence with record-id
values is therefore not merely untyped—it is unrelated locale data. A secondary
cross-check also finds overlapping values in **all three** indexed namespaces
(4 EQ entries, 22 JUG entries and 13 ENT entries), including JUG records for
Edgar Davids and Marc Overmars as well as EQ 2151 Valletta. This raw sequence
is not evidence of foreign-club membership and must never be patched as one.

## Pre-resolution boundary

At the deliberately paused `PM CH. LGE. ROUND 2` screen, before the runner
continues to the start-of-season action, PM99 has already loaded the rebuilt
EQ-2151 carrier into its in-memory carrier cache. In one fresh run its object
contained the same observed string-pointer shape as the later calendar result:
Ta' Qali, `Test Valletta`, Valletta F.C., duplicated short-name pointer, id
2151 and capacity 17,000. Manchester United's existing carrier object was
also present in a separate cache region. There was still no concrete
Manchester United–Valletta fixture object: the screen was the empty Round-2
draw state and the only `???` bytes were Wine code-page resource data.

This is an important boundary, not a membership contract. It proves that PM99
loads eligible-looking club carriers before fixture materialisation, while the
fixture copies are generated only after the draw action. Absolute heap
addresses vary per disposable run and are observational evidence only; no
pointer or adjacent-byte write is authorised by this trace.

## Hardware-watch lookup negative control

The runner can now place a bounded hardware read/watchpoint in its explicitly
debug-enabled disposable container and restore all thread debug registers on
exit. A fresh successful draw route watched EQ-2151's loaded `id` dword and
reported an access at `0x004b5c4b`. Static inspection shows that address is a
comparison inside `FUN_004b5c20`, a generic binary search over a sorted table
whose entry id is at offset `+0x10`.

The captured caller return address (`0x004b1386`) is equally important:
`FUN_004b1340` calls that lookup with the word at its own input `+0x18`. The
saved call argument was `0x080f` (2063), **not** 2151. In other words, the
search happened to inspect 2151 while looking up another id. This is not the
continental candidate resolver and must not be presented as proof that PM99
selected Valletta by a particular table or field. It is a second useful
negative control: a watchpoint on a carrier's id alone can observe a binary
search traversal rather than a selection.

Artifacts: `.local/runlogs/pm99_runner/competition_valletta_watch_id_v6_20260829/debug_watch_carrier_id.log` and
`.local/runlogs/pm99_runner/competition_valletta_watch_stack_v8_20260829/debug_watch_carrier_id.log`.

## Static cross-check

`MANAGPRE.EXE` owns the displayed competition labels. At `0x006f9420` through
`0x006f94b8` it contains the UI strings for PM League Trophy, PM Champions
League, PM Cup-Winners Trophy, PM Euro Trophy, PM European Super Trophy and PM
World Club Trophy. The confirmed cross-reference at `0x004536e6` is display
code. It is not a membership registry and must not be repurposed as one.

## Guardrails

- A `???` fixture is a competition seed, not evidence that a particular
  foreign club is missing or that an EQ record is safe to move.
- The English table proves the existing 92-carrier English contract only. It
  says nothing about a foreign domestic table.
- The country shown in the preseason opponent picker identifies an existing
  foreign carrier for that picker. It does not prove its domestic division.
- Do not add a generic “league” editor field for mode-1 teams.
- Do not claim a historically correct foreign domestic-league layout merely
  because a data viewer can group records by a plausible country or record id.

## Next acceptance test

The resolved-carrier portion is closed: PM99 resolves the draw to existing EQ
2151 and consumes its live indexed club identity. The remaining acceptance
test is narrower and more important: trace the **candidate-pool membership**
source, then demonstrate a reversible membership transaction (or establish
that the pool is executable/generated and must remain baseline-preserved).
The raw-ID scan above rules out a tempting but unrelated NLS-resource sequence,
and the first carrier-id hardware watch has ruled out a generic lookup traversal.
The next trace must identify the fixture-slot state that holds the selected id
*before* name-copying, then observe the code that populates it from the `???`
slot. Renaming a resolved carrier is deliberately not mislabelled as a pool
write. Only that next result can promote any foreign competition/topology field.

The runner's progress counter was corrected during this investigation: repeated
screenshots of a single Full Time page no longer count as multiple matches.
Future candidate-pool tests must use that edge-triggered counter, not an
unverified screenshot count.
