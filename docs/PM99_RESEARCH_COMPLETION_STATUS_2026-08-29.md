# PM99 research completion status — 29 August 2026

## Plain answer

The research is now **well bounded and documented**, but it is not honest to
call the whole database semantically editable yet.

The proven editor core is enough for a cautious, useful PM99 database editor:
existing-player core facts, photos, existing-club strings, manager association
and a constrained roster move.  The English season compiler has an additional
proved whole-club transaction.  The full international historical compiler is
**not** ready to be started: country/competition membership, foreign opening
state, fine roles and one player family are
still deliberately blocked.

The controlling detail is the machine-readable
[`PM99_WORLD_EDITABILITY_MATRIX_2026-08-28.json`](PM99_WORLD_EDITABILITY_MATRIX_2026-08-28.json),
with explanation and evidence links in
[`PM99_WORLD_RESEARCH_CLOSEOUT_2026-08-28.md`](PM99_WORLD_RESEARCH_CLOSEOUT_2026-08-28.md).

For the actual product boundary—what an English-managed game consumes rather
than what a database viewer can display—use
[`PM99_ENGLISH_SAVE_WORLD_SCOPE_2026-08-29.md`](PM99_ENGLISH_SAVE_WORLD_SCOPE_2026-08-29.md).
That scope milestone is closed; it is deliberately separate from the pending
competition-registry research and from the eventual world-content build.

## What is closed

| Area | What has actually been proved | Boundary |
| --- | --- | --- |
| Modern carrier inventory | 543 existing club carriers: 92 mode 0 and 451 mode 1; every carrier has a parsed roster and final manager link | Mode is a layout marker, never country, league or playability. |
| Club identity | Existing indexed club short name, full name and ground name can rebuild at variable length | Existing carriers only; unrelated bytes remain exact. |
| Mode-1 manager | Barcelona proves an existing final `EQ -> ENT` relink and variable-length surname rebuilds in both manager record forms | Do not insert manager links or edit the full-profile second display segment/biography. |
| Mode-1 roster membership | Barcelona/Real Madrid proves an existing player row can move only as a source-and-target transaction | Preserve count/flags; reject generated duplicate ids; loans/duplicates remain untraced. |
| Main foreign player family | Native `dd6360` nationality, date, height, weight and nine visible skills are runtime-proven for both cursor shapes; native-window player rename is visible in Kluivert's profile | Fine roles are not proved; ids 28453/29678 preserve their unusual birth-year encoding; a rename cannot grow past its old role cursor. |
| Portraits | Player-id keyed mini-photo replacement/addition/no-photo contract | Existing player IDs; an appropriate image or native no-photo, never a placeholder. |
| Compact kits | Each of the 543 carriers has `EQ96<id>.BMP` compact art in `MINIESC`, `NANOESC`, `RIDIESC`; patched Barcelona visibly changes in the real selector | No foreign `BIG*` record, 3D kit, or home/away distinction has been proved. |
| Mode-1 seated capacity | Barcelona’s fresh friendly panel visibly changes Camp Nou from 120,000 to 123,456 through the single signed EQ lane | Standing capacity and all other stadium metadata stay preserve-only. |
| Stars crash | The special Stars carrier is repaired entirely in DB data; ten profiles and an offer route work with the untouched EXE | Compiler-internal only; use opening-date free agents, not a new arbitrary club type. |
| English opening state | The native English carrier contract covers opening XI, shirts and tactics in a new game | This must not be copied to a mode-1 carrier. |

## Important things that are intentionally not closed

| Area | Why it stays blocked | Evidence needed before promotion |
| --- | --- | --- |
| Foreign competition topology | PM99 resolves a live Champions League draw to existing EQ 2151 Valletta and consumes that carrier's rebuilt name in both legs. A fresh trace sees its loaded EQ object before the draw and generated fixture copies afterward. The tempting raw 2151-ID sequence was mapped to Wine's `normnfc.nls` Unicode resource, not PM99 data; a hardware watch on 2151 was only a generic binary-search traversal for 2063, not selection. The candidate-pool source/writer remains unknown; an English save exposes no foreign domestic table. | Identify the pre-name-copy fixture slot, trace its population from `???`, then show a reversible membership transaction—or establish that it is generated/executable and preserve it. |
| Foreign opening XI/tactics | The mode-1 grid is live: DBASEPRE parses it, PM99 rejects an invalid full-grid cluster, and a bounded valid Barcelona 4-3-3 reaches a fresh match. The visible pitch mapping and opening-XI order are still unproved. | A reproducible foreign pitch/line-up capture or deeper final object-consumer trace for order, shirts, attack and defence coordinates. |
| Foreign starting finance | Mode-1 does not share the traced mode-0 finance data, and no foreign starting-budget screen has been identified | Preserve the baseline. Reopen only if a separate experiment proves that this field affects the AI simulation or another in-scope gameplay surface. |
| Fine/secondary player roles | Six native bytes are located, not yet tied to every role control and non-100% value in a foreign game | A controlled foreign player screen/tactics proof for each exposed editor concept. |
| Linked `dd6361` player | The release-mode generic writer changed decoded header/control bytes 0, 1 and 48 in the Marcus Bignot negative control | Trace those bytes, make a family-specific byte-preserving writer, then show the changed field in Bignot's profile. |
| Manager prose and second display name | There is no grammar or display route for those exact bytes | A field-specific screen and bounded mutation. |
| 3D / large foreign kits | The stock large kit archives have no mode-1 records | Separate renderer/asset research, if the game actually uses another surface. |

## Corrections recorded during this closeout

- `attr0..attr2` are not a delimiter or a normal editor field. They are an
  obsolete generic-parser interpretation and remain byte-preserved.
- The native player cursor begins after two compact XOR/u16 strings, not at
  the old generic marker. The old cursor gives believable but wrong foreign
  player facts.
- `mode 0` does not mean playable or English; it is the record layout.
- The mode-1 tactics-shaped region is now preserved by the season compiler.
  Earlier code called that write “proven” without a foreign runtime screen;
  that claim and the write have been removed.
- The apparent static competition tables around `MANAGPRE.EXE 0x70d728` are
  zlib 1.1.3 support data, not PM99 league data. See
  [`PM99_COMPETITION_STATIC_FALSE_LEAD_2026-08-29.md`](HISTORY/Investigations/PM99_COMPETITION_STATIC_FALSE_LEAD_2026-08-29.md).
- Foreign compact kit mapping is now closed. `BIGCAMP.PKF` and `BIGESC.PKF`
  are English-only stock archives; the three compact archives cover all 543
  carriers. See
  [`PM99_FOREIGN_KIT_ARCHIVE_CONTRACT_2026-08-29.md`](HISTORY/Investigations/PM99_FOREIGN_KIT_ARCHIVE_CONTRACT_2026-08-29.md).

## Rules for the editor and future season compiler

1. Make every field declaration carry its family/mode scope and evidence
   status. A broad “player edit” button is not a valid contract.
2. Rebuild indexed files after any variable-length name/string change, then
   prove every unrelated payload is byte-identical.
3. Treat a move as a transaction across both roster owners; never use a
   player-record club guess as its source of truth.
4. Keep the old foreign `dd6361` generic serializer disabled. It has a named
   negative-control receipt, not a safe fallback.
5. For a foreign compact kit, write the three existing bitmap extents together
   and no other archive bytes. Do not add a large-art record because a filename
   pattern happens to look regular.
6. Do not surface a competition/drop-down edit until the competition contract
   is green. The apparent raw 2151-id block is Wine Unicode-normalisation
   data, not a PM99 record table; it is never a club-membership candidate.
7. Keep unknown tails, manager prose and unproved role/metadata bytes exact.

## Remaining research sequence

1. Prove/disprove the mode-1 opening XI and tactics candidate with a real
   friendly/new-game screen or a loader trace. The normal half-time controls
   and pre-match `LINE-UPS` toggle are recorded false leads; until another
   surface is found, the candidate remains preserved. The loader result is
   documented in [`PM99_MODE1_INITIAL_TACTICS_LOADER_2026-08-29.md`](HISTORY/Investigations/PM99_MODE1_INITIAL_TACTICS_LOADER_2026-08-29.md).
2. Do a family-specific Marcus Bignot (`dd6361`) trace and bounded runtime
   proof, or keep that one linked player uneditable forever.
3. Trace the continental draw candidate-pool membership source at the code
   path that resolves `???` to a loaded EQ object. The named carrier-read
   portion is complete (EQ 2151 Valletta, variable name and live object
   proof); the bounded raw-ID block has been rejected as unrelated Wine NLS
   data. Prove a reversible membership transaction or formally retain
   the generated/executable pool. This is the large remaining gate for a full
   international 2015/16 database; it must not be replaced with a viewer-only
   foreign league grouping.
4. Reconcile the browser editor's released field registry with this matrix,
   fail closed on every amber/red row, and then start content sourcing.

That is the point at which “research complete” can truthfully mean the full
international world compiler, rather than merely a strong English/editor
foundation.
