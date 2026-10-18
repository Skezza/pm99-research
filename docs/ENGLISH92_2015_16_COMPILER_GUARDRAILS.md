# 2015/16 English 92 compiler guardrails

This note records the rules discovered while compiling the first full
2015/16 English four-division candidate. It is deliberately a release
engineering note, not a claim that the candidate's artwork/source gates are
complete.

## Proven build baseline

- The only competition-safe placement is the exact 92-ID native registry
  emitted by `prepare_2015_english92_native_manifest.py`. Numeric blocks are
  not a safe substitute: mode-1 records `377` and `381` are excluded, while
  mode-0 carriers `3306` and `3311` are included.
- The 2015/16 source ledger provides 92 clubs. It gives 25 complete senior
  biographies for 91 clubs; Northampton Town has 24 rows with sourced name,
  date of birth, nationality, height and weight. Do not create an invented
  twenty-fifth physical profile to make the count look tidier.
- The EQ `mode-1` roster tail is a live foreign-club graph and is immutable
  for an English build. A selected player is rejected if it has an unselected
  mode-1 owner; the compiler also compares every count/flag/JUG tail byte
  after writing. A JUG's team-id alone is not sufficient evidence of safety.
- The legacy donor-removal approach was retired after it removed 177 players
  from foreign rosters (77 of the 451 foreign carriers changed, including
  Barcelona). It must not be revived, even with a nominal 20-player floor.
- The 2015 calendar is a version-checked `MANAGPRE.EXE` patch. It is not a
  database field and belongs beside, not inside, a historical database.

## Player families

`dd6361` is the complete historical-player carrier family.

- Use the suffix-anchored variable-name writer and accept only an **exact**
  post-write anchor proof.
- It supports full core metadata, the six saved fine-role slots, the
  runtime-proven shirt number and initial Line-Up order.
- Never locate its role/order window with a loose byte scan after fixed-field
  serialization. Retain the exact anchor returned by the name writer.

The verified base has 2,125 mode-0-only `dd6361` carriers for 2,300 English
2015/16 players. The missing 175 are now explicit **appended JUG records**.

- An appended ID must be unused in both JUG and every EQ roster, and must
  clone an existing mode-0-only `dd6361` template. The normal parser-backed
  name, metadata, fine-role, shirt-number and startup-order writers then run
  on the new payload before it is appended to the indexed JUG directory.
- The indexed append shifts old directory offsets but proves every existing
  decoded JUG payload is unchanged. It does not reuse, rename or remove a
  foreign player carrier.
- The bounded runner control added JUG `33191` to Stoke's live squad as
  `Append PROBE`; PM99 reached Squad Management without a crash or Wine
  debugger. Its 451-carrier foreign topology audit was `0 changed`.
- `dd6360` remains useful research data but is not a reserve fallback for an
  English release. Its unproven role/shirt fields must remain preserve-only
  in a browser editor.

## Team and manager fields

- Short club name, stadium name, full name, seated capacity, opening roster
  and linked active manager are parser-backed writes.
- Starting finance is proven only for **mode-0** EQ records and must remain a
  £5,000 multiple. Two English carriers in the original data are mode 1;
  their finance is intentionally preserved pending a distinct runtime/Ghidra
  contract. Never change their mode byte to bypass this guardrail.
- Manager display names can be replaced on the linked ENT records. Their
  biography/career prose and other opaque profile material remain preserve
  only.
- The opening-manager ledger resolves all 92 clubs to their manager on the
  opening date. A later in-season manager is not an acceptable substitution;
  the ledger cross-checks known first managerial changes before accepting a
  fallback row.

## Runtime validation requirements

- Use the runner's disposable `--dbdat-dir` and `--exe-file` overrides; both
  are hash-verified and leave the shared game untouched.
- The runner's original default selector points at Second Division. For the
  2015 Premier test, Stoke City on EQ 314 is selected using the Premier
  control and its fourth second-row slot. Capture the selector itself before
  accepting the later screens as club evidence.
- Fresh-game proof must include division selection, club dashboard, squad
  (including a scroll page), Line-Up, tactics, finance, ground, manager and
  representative player profiles. A navigation failure is not proof of a
  field failure; recapture that route.
- The source squad pages describe a season-level roster, not a date-proven
  opening XI. The compiler's balanced 4-4-2 is an operational baseline.
  A historically exact opening XI/formation requires a separate, dated match
  lineup source for each club.

## Corrected English materialisation (2026-08-30)

The corrected full-tree build is local-only at
`.local/season-pipeline-v2/english92-mode0-append-2015-16-20260830-b/game`.
It is a legacy-source-adapter materialisation, not a strict source-native V2
release package: its legacy artwork/provenance gaps still need a dedicated V2
source migration. It is nevertheless the only current 92-club English build
eligible for world composition because it has all of the following static
facts:

- 92 linked English rosters, all 25 parser-readable players;
- 2,300 `dd6361` records, of which 175 are fresh mode-0-only appended IDs;
- `foreign-topology-audit.json`: 451 fixed mode-1 carriers, 0 changed; and
- no foreign donor removal or compact-carrier fallback.

The earlier cached `english92-clean-release-2015-16-20260830` tree is
quarantined. It changed 77 foreign mode-1 roster tails and must never be
described as clean, composed into a world build, or used as a release base.

## Artwork release gates

- Kit pixels are addressed by carrier EQ id in five PKF archives. Renaming or
  moving a club never changes its kit automatically.
- A historical kit must be imported or rendered from an attributed 2015/16
  reference and validated in the game. Copying a 1999 carrier bitmap is not a
  historical kit update.
- A minifoto must be an era-appropriate player image, face-cropped and
  palette-converted. Existing archive entries can be replaced; missing player
  entries must be delivered as `DBDAT/MINIFOTO/J96<player-id>.BMP` loose
  bitmaps. Never retain an unrelated 1999 carrier portrait as a substitute.
- Home kits are a separate five-archive render, addressed by the carrier EQ
  id. The canonical `MINIESC.PKF` archive has all 92 carrier records; the
  legacy BIGCAMP family has 79 because 13 records simply do not exist in the
  original archive. Their absence must be recorded, never filled by changing
  a bitmap container's dimensions.
- The 2015/16 kit renderer works from a season, carrier-id and simple
  colour/pattern ledger. It is a PM99-scale visual rendering, not a claim to
  reproduce sponsor artwork or redistribute a third-party kit image.

## Data-source grades and hard release gates

The 2015 source is deliberately graded rather than flattened into a false
"complete" flag.

- **FIFA 16 individual attributes**: individual PM99 core skills can be
  derived from a dated FIFA 16 record.
- **FIFA 16 FUT aggregate rating**: a dated player identity and overall
  quality are proven, but individual PM99 skills remain a declared conversion
  baseline until an individual-attribute record is matched.
- **Declared PM99 tier/position fallback**: the player has a dated name,
  roster/club placement and biography fields but no safe FIFA 16 identity
  match. It must not receive an unverified photograph or be described as
  source-rated.

The release compiler writes the grade for every player. A public release must
either resolve all fallback rows through an attributed manual ledger or state
that it is a beta with those rows excluded from its source-complete claim.

Likewise, the compiler creates a balanced team-state baseline. It is not a
date-certified starting XI or historic formation. Exact opening lineups need
a date-specific match-sheet/line-up ledger for each club and must be stored as
their own source field.

## Browser editor implications

- Keep source/proof status with each editable field and asset. A green
  "written" state should mean both parser acceptance and runtime proof, not
  merely a byte change.
- Treat minifoto replacement as a two-part transaction: image crop/convert,
  then PKF replacement or loose-file fallback. Show the actual storage target
  and preserve the original bytes until the user generates a new database.
- Let a season manifest carry manager, roster order, opening XI and kit
  references. Do not make a user infer those relationships from a player’s
  team id alone.
- `dd6360` reserve rows must render their fine-role and shirt-number controls
  read-only/preserve-only; only `dd6361` currently has runtime proof for the
  full saved role set and shirt number.
