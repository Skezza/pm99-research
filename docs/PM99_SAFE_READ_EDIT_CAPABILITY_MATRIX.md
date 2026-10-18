# PM99 Safe Read/Edit Capability Matrix

Date: 2026-06-05

## Scope correction (2026-08-29)

This is a historical **English/product** reconciliation, not the authority for
an international database build.  It predates the native `dd6360` cursor
finding and must not be read as permission to write foreign-player metadata
through the old generic `PlayerRecord` offsets.

For all world-carrier work, use these documents instead, in this order:

1. [`PM99_WORLD_RESEARCH_CLOSEOUT_2026-08-28.md`](PM99_WORLD_RESEARCH_CLOSEOUT_2026-08-28.md)
2. [`PM99_WORLD_EDITABILITY_MATRIX_2026-08-28.json`](PM99_WORLD_EDITABILITY_MATRIX_2026-08-28.json)
3. [`PM99_DD6360_NATIVE_CURSOR_CONTRACT_2026-08-29.md`](HISTORY/Investigations/PM99_DD6360_NATIVE_CURSOR_CONTRACT_2026-08-29.md)
4. [`PM99_WORLD_FIELD_MATRIX_2026-08-28.json`](PM99_WORLD_FIELD_MATRIX_2026-08-28.json)

In particular, the older rows describing player core fields, team capacity,
finance, coach relinking and roster edits are release claims for the proven
English scope.  They do **not** promote the corresponding mode-1/foreign
surface.  Mode-1 player facts, manager links, roster writes, kits, opening
state and competition membership remain gated exactly as the world matrix
states.  The `attr0..attr2` entries remain preserve-only.

This is the PM99RE research-level reconciliation of what the current workspace can safely read, safely edit, or must preserve. It is intentionally broader than the upstream product `V2_GAME_READY_MATRIX.md`: it includes product contracts, research docs, runner proofs, tracked artifacts, local artifact references, and known uncommitted helper scripts. Local-only evidence is labelled as such and must not be treated as product truth by itself.

Structured source:

```text
docs/artifacts/pm99_safe_read_edit_capability_matrix_20260605.json
```

## Evidence Tiers

| Tier | Meaning |
| --- | --- |
| `T0_unsupported` | No safe parser, writer, or reliable proof path. |
| `T1_parsed_read` | Readable through parser, probe, or documented extraction path. |
| `T2_unit_tested_write` | Write path covered by unit/integration tests. |
| `T3_db_reopen_proven` | Write path followed by strict DB reopen/readback validation. |
| `T4_runtime_screenshot` | Edited value or affected surface shown in game/runtime screenshots or runner summaries. |
| `T5_release_ready` | Release-mode contract-backed surface with deterministic gate coverage. |

Status vocabulary follows the JSON source: `release_safe`, `parser_backed`, `heuristic`, `probe_only`, `release_editable`, `investigation_editable`, `db_reopen_proven`, `runtime_proven`, `preserve_only`, and `unsupported`.

## Current Answer

There is no single pre-existing exhaustive table that spans every safe read/edit surface, variable-length rewrite contract, and runtime proof level. The closest existing sources are:

- `upstream/pm99-skezmod-db-editor/docs/V2_GAME_READY_MATRIX.md`
- `upstream/pm99-skezmod-db-editor/app/data/game_ready_v2_contract.json`
- `upstream/pm99-skezmod-db-editor/docs/PLAYER_VARIABLE_NAME_EDITOR_CONTRACT.md`
- `upstream/pm99-skezmod-db-editor/docs/VARIABLE_STRING_EDITOR_CONTRACT.md`
- `docs/HISTORY/Investigations/VARIABLE_STRING_SURFACE_PROOF_2026-05-07.md`
- `docs/artifacts/variable_string_all_evidence_20260507/index.html`
- `docs/artifacts/full_game_variable_name_windows_20260503/index.html`

Those sources are strong but fragmented. This matrix is the reconciled research plan for what remains.

## Exhaustive Capability Matrix

| Row ID | Domain | Surface | Read status | Edit status | Tier | Release or research status | What remains |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `player-core-fields-release` | players | Position, nationality, DOB, age, height | `release_safe` | `release_editable` | `T5_release_ready` | Released editable core metadata | Keep runtime spot checks tied to release evidence. |
| `player-weight-parser-backed` | players | Weight | `parser_backed` | `release_editable` | `T5_release_ready` | Released only when indexed suffix or legacy marker-backed slot exists | Do not broaden legacy writes beyond parser-backed slot policy. |
| `player-visible-skills-attr3-attr11` | players | Visible skills: attr3..attr11 | `release_safe` | `release_editable` | `T5_release_ready` | Released editable skill window | Keep UI labels aligned with confirmed attr3..attr11 contract. |
| `player-tail-attr0-attr2` | players | Tail bytes attr0..attr2 | `probe_only` | `preserve_only` | `T5_release_ready` | Released preserve-only structural tail bytes | Need binary consumer identification before any naming/editing. |
| `player-fine-role-slots` | players | Six fine/secondary role bytes | `parser_backed` | `investigation_editable` | `T3_db_reopen_proven` | Intrinsic bytes and loader are mapped, but the visible `ROL.` control is tactical rather than the intrinsic list | Keep out of the ordinary editor unless a dedicated UI/behaviour proof is found. |
| `player-team-id-squad-number` | players | Team id and squad number helpers | `parser_backed` | `investigation_editable` | `T2_unit_tested_write` | Implemented/tested but not game-ready promoted | Decide if product surface or internal roster helper. |
| `player-indexed-probe-bytes` | players | Indexed unknowns, face components, post-weight byte, trail/sidecar | `probe_only` | `preserve_only` | `T1_parsed_read` | Read-only investigation probes | Identify consumers and semantics before edits. |
| `player-variable-names-dd6360` | players | `dd6360_native_stream_gap3/gap4`, mononyms | `release_safe` | `db_reopen_proven` | `T3_db_reopen_proven` | Product-safe through backend plan/apply; runtime proof representative only | Expand runtime proof by native club/context. |
| `player-variable-names-dd6361` | players | `dd6361_indexed_suffix` visible name prefix rewrite | `release_safe` | `db_reopen_proven` | `T4_runtime_screenshot` | Product-safe through backend plan/apply; native English runtime samples exist | Tie runtime evidence to the current product contract and helper scripts. |
| `player-variable-name-full-corpus` | players | Full indexed JUG variable-name plan/apply | `release_safe` | `db_reopen_proven` | `T3_db_reopen_proven` | Full editor proof: 11,479 ready/applied, 0 blocked, 0 post-write failures | Resolve full-corpus runtime carrier/crash-modal blocker. |
| `player-variable-name-api-web` | players | API plan/apply and web workbench | `release_safe` | `db_reopen_proven` | `T2_unit_tested_write` | Implemented in upstream editor worktree, pending migration commit/push | Commit/push editor worktree and keep status current. |
| `team-core-proven-fields` | teams | Indexed EQ short name, stadium name, full club name, seated capacity, mode-0 finance | `parser_backed` | `release_editable` | `T4_runtime_screenshot` | Short/stadium names, capacity and finance have fresh release-mode runner proof; full name reopens but has no useful UI route | Reconcile the historical release registry and UI with this narrower contract. |
| `team-derived-or-heuristic-metadata` | teams | Standing capacity, car park, pitch, chairman, sponsor, supplier, ground size | `heuristic` | `preserve_only` | `T1_parsed_read` | Old claims rely on derived displays or conservative printable-span parsing, not bounded game-proven writes | Do not expose as ordinary editable fields. |
| `team-competition-and-unknown-metadata` | teams | Competition bytes, league probes, cluster/unknown metadata | `probe_only` | `preserve_only` | `T5_release_ready` | Released preserve-only | Need binary consumers and runtime placement proof. |
| `coach-names-ent` | coaches | Indexed coach names, surname/full name | `release_safe` | `db_reopen_proven` | `T3_db_reopen_proven` | Released given/surname; variable full-name writer test-backed | Manager/coach UI screenshot route is still missing. |
| `coach-relink` | coaches | Coach/team relationship | `release_safe` | `release_editable` | `T5_release_ready` | Released editable | Need reliable staff/manager route proof for edited linked names. |
| `rosters-linked-and-same-entry` | rosters | Linked and supported same-entry roster edits, promote, batch edit | `release_safe` | `release_editable` | `T5_release_ready` | Released editable for parser-backed mappings | Expand runtime visibility proof beyond Stoke surrogate. |
| `rosters-unresolved-tail-columns` | rosters | Unresolved roster tails and fallback families | `probe_only` | `preserve_only` | `T5_release_ready` | Released preserve-only | Map semantics and prove consumers before editing. |
| `assets-bitmap-reference-contract` | assets | Bitmap references, MINIFOTO/profile image proof | `probe_only` | `preserve_only` | `T4_runtime_screenshot` | V2 preserve-only; separate asset replacement contracts exist | Decide if asset replacement needs a separate matrix. |
| `runtime-squad-and-profile-proof` | runtime | Squad tables, player profiles, selectors, profile club text | `runtime_runner` | `runtime_proven` | `T4_runtime_screenshot` | Proof infrastructure, not an editor write path | Formalize route reliability levels. |
| `runtime-weak-routes` | runtime | Weak/unstable dashboard routes and full all-route sweeps | `heuristic` | `unsupported` | `T1_parsed_read` | Weak proof routes | Repair route drift before using for promotion evidence. |
| `cross-family-interactions` | cross-family | Player/team/coach interactions outside supported operations | `probe_only` | `preserve_only` | `T5_release_ready` | Released preserve-only | New cross-family edits need parser contract and runtime closeout. |
| `validation-gates` | validation | Deterministic tests, game-ready audit, validate-database, runner proof | `release_safe` | `release_editable` | `T5_release_ready` | Required gate set | Keep migration validation notes current. |

## Product-Safe Today

These can be treated as current release/product-safe surfaces when used through the upstream editor APIs and release-mode guardrails:

- Player core metadata: position, nationality, DOB/year/age, height.
- Player weight only where the parser-backed slot policy permits it.
- Player visible skill attributes `attr3..attr11`.
- The narrowly proven team fields in the core closeout: short name, stadium name,
  full club name with a UI-proof caveat, seated capacity, and mode-0 finance.
- Coach `given_name` and `surname`.
- Coach relink and supported roster operations.
- Preserve-only classifications for attr0..2, team unknowns, competition bytes, unresolved roster tails, cross-family interactions, and asset bitmap references.

## Product-Safe Backend, Runtime Proof Still Partial

Player variable-length name rewriting is the strongest challenging contract:

- `dd6360_native_stream_gap3/gap4` is fixed-window. It preserves total payload length and blocks growth beyond the original role start.
- Tiny `dd6360` mononym windows remain editable only to another tiny mononym.
- `dd6361_indexed_suffix` can resize because the indexed FDI directory is rebuilt and revalidated.
- Full indexed JUG editor proof reports `11,479` parser-backed rows, `0` preserve-only rows, `0` blocked rows, and `0` post-write failures.

The remaining gap is runtime breadth, not DB safety. Native English30 and English80 give strong visual evidence for slices of the problem. Older full-corpus carrier evidence had crash-modal detections and must remain a blocker.

## Investigation-Mode Only

These have real implementation/evidence but are not release-mode product writes:

- ENT full-name variable writer beyond the released given/surname framing.
- Player fine/secondary role bytes.
- Player `team_id` and `squad_number` helper-level edits.

EQ strings now have a dedicated release-mode Stoke run: short name and stadium
name are visible in Ground, while full club name is write/reopen-proven but has
no suitable UI route in that run.

## Preserve-Only Or Probe-Only

Do not edit these without a new contract:

- Player attr0..2.
- Player indexed unknown bytes, face components, post-weight byte, trail, and sidecar bytes.
- Team competition bytes and unknown metadata regions.
- Standing capacity, car park, pitch, chairman, sponsor, supplier and ground
  size until each has an independent bounded contract.
- Roster unresolved tail columns and fallback same-entry families.
- Cross-family relationships outside released roster/coach operations.
- Bitmap reference surfaces unless using a separate asset replacement contract.

## Runtime Proof State

Strong proof routes:

- Startup/new-game/configuration flow.
- Squad management and current squad tables in focused routes.
- Player profiles through guided profile or offer flows.
- Transfer market/offers/search/profile for the Barcelona variable string proof.
- Staff screen extraction for read-only proof.
- Selector discovery after native-click geometry fixes.

Weak routes:

- Full all-route dashboard sweeps.
- `results`, `opponent`, `tactics`, and `board_room` when only route-signal OCR passes.
- Screenshot-only matrix runs without crash-modal pixel checks.
- Stoke-surrogate visibility for arbitrary linked players.

## Validation Notes From Current Workspace

The current closeout reran targeted structural tests, compiled the changed
Python, validated runner shell syntax, and passed the root boundary check. The
system Python available here has no `pytest`, so historic suite counts must not
be treated as a new full-suite result. A normal-environment pytest run is part
of the contract-reconciliation milestone below.

## Remaining Work

1. Reconcile the upstream team-field registry, game-ready contracts and GUI with
   the narrower core-field matrix in the closeout document.
2. Run the full normal-environment test suite and add a release-mode test for
   the structured EQ string writer.
3. Build the browser editor only from the reconciled machine-readable field
   matrix; show all other data as read-only or omit it.
4. Treat club membership as a separate cross-family research project if it is
   ever required; it is not an unfinished detail of the core editor.
