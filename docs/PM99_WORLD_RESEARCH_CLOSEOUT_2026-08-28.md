# PM99 world database research closeout ledger (2026-08-28)

## Purpose

This is the controlling research ledger before any full international 2015/16
content build. A green row is a contract that may be used by a compiler. An
amber row needs the stated proof. A red row is preserve-only.

For the short authority order and rules that prevent older English-only notes
from being applied to the world corpus, start with
[`PM99_WORLD_RESEARCH_AUTHORITY_2026-08-29.md`](PM99_WORLD_RESEARCH_AUTHORITY_2026-08-29.md).

The machine-readable companion is
[`PM99_WORLD_FIELD_MATRIX_2026-08-28.json`](PM99_WORLD_FIELD_MATRIX_2026-08-28.json).
It lists every carrier without guessing its country or competition.

The concise field-authority contract is
[`PM99_WORLD_EDITABILITY_MATRIX_2026-08-28.json`](PM99_WORLD_EDITABILITY_MATRIX_2026-08-28.json).

The read-only native-cursor receipt is
[`PM99_DD6360_NATIVE_CURSOR_AUDIT_2026-08-29.json`](PM99_DD6360_NATIVE_CURSOR_AUDIT_2026-08-29.json).
Its format, Ghidra evidence and implementation guardrails are in
[`PM99_DD6360_NATIVE_CURSOR_CONTRACT_2026-08-29.md`](HISTORY/Investigations/PM99_DD6360_NATIVE_CURSOR_CONTRACT_2026-08-29.md).

The mode-1 external-roster/current-club counterexample is documented in
[`PM99_MODE1_ROSTER_CROSS_FAMILY_CONTRACT_2026-08-29.md`](HISTORY/Investigations/PM99_MODE1_ROSTER_CROSS_FAMILY_CONTRACT_2026-08-29.md).

The mode-1 manager-link cursor was corrected and then proved with separate
Barcelona surname and relink mutations. The contract and its remaining name
limits are in
[`PM99_ENT_CROSS_CARRIER_PRESERVATION_2026-08-29.md`](HISTORY/Investigations/PM99_ENT_CROSS_CARRIER_PRESERVATION_2026-08-29.md).

## Fixed-corpus facts

| Fact | Result | Evidence |
| --- | --- | --- |
| Modern club carriers | 543: 92 mode 0 and 451 mode 1 | `audit_pm99_world_carriers.py` |
| Mode meaning | record layout, not country or playability | mixed historical English/foreign corpus |
| Linked rosters | all 543 have a parser-backed EQ→JUG roster | field matrix receipt |
| Linked managers | all 543 modern carriers parse an existing final EQ→ENT manager link; 451 mode-1 links structurally resolve to parsed ENT profiles | carrier inventory and mode-1 manager audit |
| Indexed players | 11,479 decode and syntactically parse | `player-indexed-directory-audit` |
| Mode-1 roster player layouts | 9,211 `dd6360`, 1 `dd6361` | carrier inventory: the sole mode-1 `dd6361` row is Marcus Bignot (JUG 10958, Kidderminster H.) |
| Manager profiles parsed | 556: 464 surname-only and 92 full-profile | direct indexed ENT audit |
| Active manager forms | mode 0: 66 surname-only and 26 full-profile; mode-1 links resolve to direct ENT profiles, with 451 structurally valid carriers | mode-1 manager audit and Barcelona controls |
| Mode-1 manager mapping | **proven:** Barcelona final EQ ID 1069 maps to Van Gaal; a same-length ENT rename displays `Test Mgr`, and a 1069→1641 EQ relink displays `Hiddink` | retained-overlay Barcelona mutation controls |
| Current portrait archive records | 1,352 | field matrix receipt |

“Syntactically parse” means the data shape can be read. It does not mean its
semantics, write spans, or runtime behaviour have been proved.

## Player-shape result

The current corpus has three parser-recognised JUG families:

| Family | Records | Important structural limit |
| --- | ---: | --- |
| `dd6360`, compact native strings | 9,353 | The generic marker is **not** the metadata cursor. The native cursor is the end of two XOR/u16 strings at byte 8. |
| `dd6361`, marker and indexed anchor | 1,673 | all reported core spans are structurally separable; one nationality row is rejected by the parser check. |
| `dd6361`, no marker, indexed anchor | 453 | all reported core spans are structurally separable. |

The old generic capability profiler can locate bytes, but it must no longer be
used as the semantic contract for `dd6360`. `MANAGPRE.EXE` reads the roles and
core fields immediately after the second compact string, while the generic
reader starts three or four bytes later. The new native audit proves that
cursor for all 9,353 `dd6360` records: 6,487 gap-3 and 2,866 gap-4 records,
with no structural failures. It also keeps two legacy birth-year encodings
(record ids 28453 and 29678) preserve-only rather than inventing a year.

This is an important correction, not a promotion to bulk-edit permission.
The native cursor gives the right structural spans for the six fine positions,
nationality, date, physicals and nine post-cursor skill bytes. Two foreign
runtime mutations now prove the named nationality/date/physical/visible-skill
lanes across both gap shapes; fine-position writes remain separate. In
particular, `attr0..2` are not semantic editor fields: they belong to the
obsolete generic interpretation and remain preserve-only until independently
traced.

### Concrete foreign-player check

Patrick Kluivert (Barcelona, JUG id 1802) is the regression fixture. The old
generic read claimed nationality `1`, birth month `184`, birth year `1975` and
height `175`. The native `dd6360` cursor reads nationality code `27`, 1 July
1976, 187 cm and 78 kg, followed by the expected role and skill stream. This
matches the player and proves the generic offset was wrong; it does not prove a
write until a disposable game run shows the changed field in the foreign-club
UI. That proof now exists for nationality/date/physicals/visible skills in
both gap shapes; it does not cover a fine-role mutation.

The mode-1 pilot should start with two `dd6360` foreign fixtures, one from
each native cursor gap, because they cover 9,211 of the 9,212 current
mode-1 roster links.  Barcelona's Patrick Kluivert (JUG 1802, gap 4) and
Josep Guardiola (JUG 34, gap 3) are the chosen fixtures.  The one remaining
mode-1 `dd6361` player is a separate, small-scope proof: Marcus Bignot
(JUG 10958) at Kidderminster Harriers.  This distinction is important: the
high level player-family totals include unlinked/free rows and must not be
misrepresented as the foreign-club write surface.

## Field and transaction status

| Surface | Status | Safe scope / rule | What closes it |
| --- | --- | --- | --- |
| Club short name, full name, ground name | Green | parser-backed variable-length indexed EQ rebuild; preserve all other bytes | already runtime-proven, including a foreign club profile |
| Seated capacity | Green for existing parsed mode 0 and mode 1 carriers | direct signed 32-bit lane and one-lane structural patch; preserve standing capacity and later bytes | Barcelona / Camp Nou visibly changes from 120,000 to 123,456 in a fresh foreign-opponent match |
| Standing capacity | Amber | direct signed 32-bit lane, no released writer | field-specific write and foreign-club runtime proof |
| Starting finance | Amber for mode 1 | mode-0 finance lane is traced and runtime-proven; mode 1 has a different metadata block | trace the mode-1 loader path and prove visible finance |
| Active manager link | Green, constrained | existing final EQ→ENT ID only; replacement target must exist, count and preceding IDs stay unchanged | mode-0 Coventry and mode-1 Barcelona direct runtime mutations |
| Manager surname | Green | indexed variable-length surname rebuild is proven for `dd6360` and `dd6361` profiles, preserving every unrelated payload and prose tail | Barcelona surname-only and full-profile controls |
| Full-profile display name | Red | dashboard consumes the first surname segment; the second name segment has no field-specific UI/write proof | direct screen consuming it and a bounded write proof |
| Manager biography and career prose | Red | preserve-only | no field grammar; never bulk rewrite |
| EQ→JUG roster reading | Green | use the indexed roster map, not player team-id guesses | already structurally complete |
| Mode-1 roster writes | Green, constrained transaction | existing external rows only; preserve counts/flags and update both clubs so every generated JUG id is unique | intentional duplicate/loan semantics, row-count changes and flag writes remain separate |
| `dd6360` nationality, date, physicals and visible skills | Green, family-scoped | use the native cursor; ids 28453/29678 preserve birth year; preserve control bytes | product must implement the same native writer before release |
| Player identity/name and fine/secondary positions | Mixed | `dd6360` native-window variable name rebuild is runtime-proven; fine roles and the separate `dd6361` layout remain gated | direct mode-1 fine-role proof and the one linked `dd6361` player proof; do not infer either from metadata/name proof |
| Unknown player bytes / short tails | Red | preserve byte-for-byte | only a field-by-field runtime and Ghidra contract can promote a span |
| Player mini-photo | Green | keyed by JUG record id; valid BMP or native no-photo disposition | individual replacement/add/no-photo runtime proof |
| League display name | Green, separate product | executable string, not a database field; belongs in SkezMod | keep it out of the browser database editor |
| Club kit | Mixed | compact UI art is direct carrier-keyed in `MINIESC`/`NANOESC`/`RIDIESC` and Barcelona's actual selector tile is runtime-proven; `BIG*` stock archives are English-only and other render surfaces are unproved | use only the three compact archives for foreign existing carriers; prove any 3D/large/home-away surface separately |
| Opening ordered XI | Amber | separate from roster order and squad number | mode-1 club fresh-game proof |
| Opening tactical coordinates | Amber | separate initial EQ state, not `TACTIC.*` library files | inspect/write/relaunch a foreign club, including defensive position coordinates |
| Foreign domestic topology / continental candidate pool | Red | preserve-only; the English game has no foreign domestic-table surface. A live draw resolves to EQ 2151 Valletta, consumes its rebuilt name and creates separate fixture copies, but pool membership remains untraced. The apparent raw 2151-id sequence is Wine `normnfc.nls` Unicode data, not a PM99 pool. | trace the resolution code path and prove a reversible pool transaction, or preserve a generated/executable pool |
| Continental/international structures | Red | preserve-only | separate engine/competition research |
| Stars special carrier | Green, compiler-internal | repaired id 9900→9899 and linked payloads >=80; ten exact profiles and one offer route pass with the untouched EXE | use only for sourced opening-date free agents after normal data/portrait gates |

## Stars decision

The Stars crash is a database defect: the hard-coded `0x26AC` special path
passes a null club-text pointer to `FUN_0066F1F0`, which dereferences it at
`0x0066F208`. The database-only contract is documented in
[`PM99_STARS_DB_ONLY_CONTRACT_2026-08-28.md`](HISTORY/Investigations/PM99_STARS_DB_ONLY_CONTRACT_2026-08-28.md).

The isolated untouched-executable proof now succeeds: all ten exact player
profiles and a Valderrama offer route pass. The historical build may re-use the
ten carrier slots for real opening-date free agents only after normal source
and portrait/no-photo decisions. The old EXE guard remains diagnostic
evidence, not a release dependency.

## Gates before the international build begins

1. The live named-draw carrier is now closed: it resolves to EQ 2151 Valletta
   and consumes a live variable-length name rebuild. The read-only runtime
   trace distinguishes that loaded carrier from generated fixture copies; the
   raw 2151-id block is a mixed-namespace false lead. Trace the exact
   **candidate-pool membership source** at the resolution code path next. The English game exposes no
   foreign domestic table, so do not substitute country-by-country viewer
   grouping for this proof. Never infer topology from record order or mode. See
   [`PM99_ENGLISH_COMPETITION_RUNTIME_SCOPE_2026-08-29.md`](HISTORY/Investigations/PM99_ENGLISH_COMPETITION_RUNTIME_SCOPE_2026-08-29.md).
2. Reconcile the product reader/writer to the native `dd6360` cursor, with
   record ids 1802, 28453 and 29678 as permanent regression fixtures. It must
   fail closed on the two legacy birth-year rows.
3. Use the constrained roster transaction for every generated player move:
   update the source and target rows together, preserve counts/flags, and
   reject a final duplicate JUG id. Intentional duplicate/loan semantics,
   row-count changes and flag writes remain preserve-only. Then run a
   mode-1 transaction pilot covering several player families and at least one
   non-European carrier: club text, manager name/link, a roster, player facts,
   compact kit, photo/no-photo, ordered XI and tactics.
4. Keep the mode-1 manager link to its narrow established contract. It is the
   final existing EQ→ENT ID. Variable-length surnames are proven in both ENT
   record families, but the separate full-profile display-name segment and
   biography/career prose remain preserve-only. Do not derive a prose or
   second-name allocation rule from the surname proof.
5. Promote only successful fields into the machine-readable matrix. Every
   other field remains preserve-only in both the browser editor and compiler.
6. Then source and compile the 2015/16 world data, with runtime proof by
   country and carrier sample.

This is deliberately stricter than the English 92 release. The English work
proved a complete mode-0 transaction. It is evidence and reusable tooling,
not a licence to assume the same write path is safe for all mode-1 carriers.

## Remaining research milestones and acceptance evidence

These are the remaining milestones.  They are deliberately phrased as
acceptance tests, so a later content-build cannot mark a field complete merely
because it has a plausible byte offset.

| Milestone | Current state | Minimum evidence needed to close it | Product/compiler rule until then |
| --- | --- | --- | --- |
| Native player writer reconciliation | Research contract is green; product implementation is not yet reconciled | Unit fixtures for native `dd6360` gap 3 and gap 4, legacy-year refusal, and a browser/CLI result whose bytes equal the native writer receipt | Do not enable these fields in the browser product through the legacy generic player parser |
| Foreign manager association/link | Closed for existing final IDs | Barcelona proves variable-length surname rebuilds in both ENT forms and a direct relink; corpus audit validates all mode-1 targets | Permit existing final-ID replacements only; preserve count/preceding IDs |
| Full-profile manager display name | Read-only | variable surnames are now runtime-proven in both ENT families, but the dashboard consumes the surname rather than this second segment | Find a screen that consumes it and prove a bounded write; preserve prose tails byte-for-byte |
| Foreign seated capacity | Closed for existing parsed carriers | Barcelona EQ 1 changes only the signed seated-capacity lane; a fresh Barcelona-versus-Arsenal half-time screen reads Camp Nou 123,456 rather than the 120,000 control | Permit only the parser-backed seated lane; standing capacity and every other stadium field stay read-only |
| Foreign starting finance | Preserve baseline | Mode-1 has no traced finance lane or foreign starting-budget screen, and there is no evidence it affects an in-scope simulation surface | Keep mode-1 finance read-only; reopen only after a targeted AI-economy impact experiment |
| Foreign compact kit | Closed for the compact UI surface | Barcelona `EQ960001.BMP` copied from Real Madrid `EQ960004.BMP` in `MINIESC`/`NANOESC`/`RIDIESC`, with a visible changed Barcelona preseason tile | Permit exact-shape existing-carrier compact-art transactions only. `BIG*`, home/away distinctions and 3D render surfaces remain separate/unproved. |
| Foreign opening XI and tactics | Unknown initial-state source | Fresh-game screenshots before/after a bounded write, covering XI order, shirt number, attack and defence pitch coordinates; prove another club is unchanged | Treat roster rows as membership only; keep opening lineup/tactics read-only |
| Foreign topology and continental draw pool | English competition surface mapped; live named carrier read proven; draw-pool membership unresolved | Trace the exact candidate membership source and show a reversible pool transaction in a fresh English game, or preserve a generated/executable pool | Preserve current foreign topology and never write a guessed division/country byte |
| `dd6360` names and fine roles | Name closed, roles open | Kluivert's compact variable rebuild is visible in his foreign profile. A role proof still needs all relevant slots and non-100% values if the UI exposes them | Allow only native-window name rebuilds; leave fine-role controls read-only |
| Mode-1 `dd6361` exception | Generic writer rejected by byte-diff control | Trace its header/control bytes, build a family-specific byte-preserving writer, then show Bignot's intended field in a fresh-game profile | Read-only. Do not use either the `dd6360` writer or generic `player-edit` serializer |
| Legacy duplicate roster semantics | Baseline has 35 duplicate player memberships | Reverse-engineered precedence plus a game route for an intentional duplicate/loan, or a conscious permanent preserve-only decision | Generated world databases must reject duplicates; preserve baseline duplicates verbatim |

### Important mode-1 UI boundary

The normal fresh-game selector can choose a foreign club as a pre-season
opponent, but not as the manager's club. The dashboard `GROUND` route therefore
still opens Arsenal’s data even while Barcelona is visibly the CPU opponent.
That is a negative control. A separate fresh Barcelona-versus-Arsenal
half-time panel does read Barcelona / Camp Nou, and proves the 120,000→123,456
seated-capacity mutation. Its `TACTICS` and `LINE-UP` controls do not expose a
foreign grid through native runner clicks, so opening state remains unproved.
See [`PM99_MODE1_MANAGED_CLUB_BOUNDARY_2026-08-29.md`](HISTORY/Investigations/PM99_MODE1_MANAGED_CLUB_BOUNDARY_2026-08-29.md).

No content phase may claim a complete international season until every row it
uses is green, or the scope has been explicitly reduced so that no amber/red
surface is touched.

## Runtime evidence guardrail

Never regard a runner exit code or a scripted final step as game proof by
itself. The UI can remain on a search dialog or open a similarly named player.
A profile proof must identify the requested record in the visible profile,
and a fresh-game proof must identify the expected club/competition in the
visible game screen. This guardrail applies to every later country and season
build.

## Static-analysis guardrail

The attractive numerical tables at `MANAGPRE.EXE` `0x70d628` through
`0x70d7a0` are zlib 1.1.3 support data, not a selector or competition table.
They are explicitly ruled out in
[`PM99_COMPETITION_STATIC_FALSE_LEAD_2026-08-29.md`](HISTORY/Investigations/PM99_COMPETITION_STATIC_FALSE_LEAD_2026-08-29.md).
This matters because a table-shaped byte sequence is not membership evidence.
