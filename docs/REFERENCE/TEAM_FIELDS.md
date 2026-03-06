# Team Fields Reference

This is the authoritative team-record reference for the current codebase.

For container-level rules, use [../DATA_FORMATS.md](../DATA_FORMATS.md). For parser and loader behavior, cross-check [../../app/loaders.py](../../app/loaders.py), [../../app/models.py](../../app/models.py), and [../../app/eq_jug_linked.py](../../app/eq_jug_linked.py).

## Scope

This document describes the team and roster data the project can currently parse conservatively from `EQ98030.FDI`.

## Confirmed Team Sources

The project currently recognizes two main team-related paths:

1. `TeamRecord` parsing from `EQ98030.FDI` team subrecords
2. Parser-backed EQ-to-JUG linked roster extraction via `app/eq_jug_linked.py`
3. Authoritative same-entry roster runs from `scripts/probe_eq_team_roster_overlap_extract.py`
   when `preferred_roster_match.provenance == same_entry_authoritative`

These are related, but not identical.

The current desktop editor also carries a best-effort `league_source` provenance
on loaded team records:

- `team_id_range` when the legacy fixed range table resolves directly
- `competition_probe_contract` when a strong competition-signal probe is
  promoted into a read-only league assignment contract
- `sequence_fallback` when league/country are assigned from the recovered EQ
  team stream order
- `unknown` when neither path resolves

Loaded team records also now carry derived read-only cluster metadata for the
current `+0x00` competition-byte candidate:

- `competition_code_candidate`
  - the current strongest anchor-relative byte candidate
- `competition_code_cluster_kind`
  - heuristic classification (`competition-like`, `country-like`,
    `shared-family`, or `mixed`)
- `competition_code_cluster_team_count`
- `competition_code_cluster_competition_count`
- `competition_code_cluster_dominant_country`
- `competition_code_cluster_dominant_competition`
- `competition_secondary_signature`
  - read-only tuple built from bytes `+0x08` and `+0x0A` after the known-text anchor
- `competition_secondary_signature_display`
  - preformatted hex pair (for example, `68-73`)
- `competition_secondary_signature_kind`
  - heuristic split classification (`competition-splitting`, `strong`,
    `partial`, `weak`, `flat`, or `single-competition`)
- `competition_secondary_signature_count`
- `competition_secondary_signature_average_purity`
- `competition_secondary_signature_strong_groups`
- `competition_tertiary_offset`
  - the current best tested extra byte offset for this primary-code family
- `competition_tertiary_value`
  - the selected club's byte value at that extra offset
- `competition_tertiary_signature_display`
  - the current composite signature (`+0x08`, `+0x0A`, plus the tested extra byte)
- `competition_tertiary_signature_kind`
  - heuristic result (`refining`, `improving`, `marginal`, `no-gain`,
    `single-competition`, or `unresolved`)
- `competition_tertiary_signature_count`
- `competition_tertiary_signature_average_purity`
- `competition_tertiary_signature_strong_groups`
- `competition_family_metadata_offset`
  - the best current single-byte non-text candidate for this primary-code family
- `competition_family_metadata_value`
  - the selected club's byte value at that non-text family-candidate offset
- `competition_family_metadata_kind`
  - heuristic result (`promising`, `exploratory`, `weak`, `text-like`, or `unresolved`)
- `competition_family_metadata_non_text_ratio`
- `competition_family_metadata_average_purity`
- `competition_family_metadata_strong_groups`
- `competition_family_metadata_distinct_dominants`
- `competition_dominant_country_subgroup_offset`
  - the best current single-byte candidate after narrowing a `country-like`
    family to its dominant-country subset
- `competition_dominant_country_subgroup_value`
  - the selected club's byte value at that subgroup-candidate offset
- `competition_dominant_country_subgroup_kind`
  - heuristic result (`tentative`, `exploratory`, `weak`, `flat`,
    `single-competition`, or `unresolved`)
- `competition_dominant_country_subgroup_non_text_ratio`
- `competition_dominant_country_subgroup_average_purity`
- `competition_dominant_country_subgroup_strong_groups`
- `competition_dominant_country_subgroup_distinct_dominants`
- `league_probe_method`
- `league_probe_signal`
- `league_probe_signal_offset`
- `league_probe_signal_value`
- `league_probe_candidate_country`
- `league_probe_candidate_league`
- `league_probe_candidate_competition`
- `league_probe_purity`
- `league_probe_support`
- `league_probe_total`
- `league_probe_confidence`
- `league_probe_matches_assigned`
- `league_probe_matches_original_assigned`
- `league_assignment_confidence`
  - `high`, `medium`, `low`, `review`, or `unresolved`
- `league_assignment_status`
  - loader-side audit status (`confirmed`, `probe-promoted`, `supported`,
    `weakly-supported`, `fallback`, `probe-mismatch`, `probe-only`,
    `probe-weak`, `unresolved`)
- `league_source_initial`
- `league_country_initial`
- `league_initial`
- `league_assignment_promoted`
- `league_assignment_promoted_from_source`
- `league_assignment_promoted_method`
- `league_assignment_promoted_probe_confidence`

## Team Subrecord Structure

The current `TeamRecord` loader is still partially heuristic. These elements are the confirmed parts:

- Team-like subrecords are commonly separated by `0x61 0xDD 0x63`.
- Team names are extracted from the first credible uppercase printable span.
- Stadium names are extracted from later printable spans and keyword-based heuristics.
- Team IDs are inferred by scanning for plausible 16-bit values in the expected range.

## Confirmed Team Fields

- `name`
  - Parsed from the first reliable name-like text region
- `stadium`
  - Parsed from later printable stadium-like text spans
- `team_id`
  - Heuristically detected from the decoded team payload
- `get_known_text_anchor()`
  - Conservative read-only probe anchor after the currently known name/stadium text
- `get_competition_probe_bytes(length=32)`
  - Fixed probe window after that anchor for reverse-engineering candidate fields
- `get_competition_probe_byte(relative_offset)`
  - One byte from that fixed probe window
- `get_competition_code_candidate()`
  - Current strongest read-only candidate: the first byte after the known-text anchor
- `get_competition_secondary_signature(offsets=(8, 10))`
  - Current second-stage read-only signature built from bytes `+0x08` and `+0x0A`
- `get_competition_tertiary_signature(tertiary_offset, secondary_offsets=(8, 10))`
  - The current second-stage signature extended by one extra family-specific byte
- stadium summary fields, when present in text
  - capacity
  - parking / car park
  - pitch quality

These fields are usable, but team parsing is still less exact than player parsing.

## Parser-Backed Linked Roster Data

`app/eq_jug_linked.py` provides the strongest current roster path for static team membership:

- teams are loaded from indexed `EQ98030.FDI` payloads
- large external-link records are parsed conservatively
- linked rows resolve player IDs against `JUG98030.FDI`

Confirmed roster row shape:

- one roster slot is 5 bytes
- byte `0`: `flag`
- bytes `1-4`: `player_record_id` (`uint32` little-endian)

Current parser-backed roster metadata includes:

- EQ record id
- short name
- stadium name
- full club name
- record size
- mode byte
- linked ENT count
- ordered roster rows

Parser-backed linked roster rows now also expose stable byte locations inside the
indexed EQ payload, which allows fixed-size in-place slot edits for this specific
roster table.

## Authoritative Same-Entry Roster Data

For teams whose `preferred_roster_match` resolves to `same_entry_authoritative`,
the project also has a partially decoded inline roster family inside the same EQ
entry as the team metadata.

Current confirmed row contract:

- roster rows are treated as 5-byte records inside the decoded EQ entry
- the leading 2 bytes are a `0x61`-XOR'd little-endian 16-bit PID candidate
- in the current authoritative dataset, the trailing 3 bytes are invariant filler:
  `0x61 0x61 0x61` (`tail_bytes_hex=616161`)

The same 5-byte tail shape is now also confirmed across the current preferred fallback
same-entry families surfaced by the probe (`known_lineup_anchor_assisted`,
`adjacent_pseudo_team_record_reassignment`, `anchor_interval_monotonic_same_entry`,
and `heuristic_circular_shift_candidate`). That proves the row shape is broader than
just `same_entry_authoritative`, even though the team-to-run mapping confidence is still
different across those provenance levels.

That means the current authoritative same-entry row shape is effectively:

- bytes `0-1`: XOR'd little-endian PID
- bytes `2-4`: constant filler `0x61 0x61 0x61`

The writer still preserves the observed tail bytes defensively, but this is now a
materially stronger contract than a blind 2-byte overlay.

## Write Safety Boundaries

- Team text edits are safest when they are same-size or preserve the surrounding container layout.
- Indexed container writes are more sensitive because payload-length changes can require rebuilding offsets.
- Linked roster parsing is stronger than general team-field parsing; treat those as separate confidence levels.
- Unknown bytes outside the targeted text or roster region should be preserved.
- The external EQ->JUG linked roster table can now be edited safely one slot at a time
  when the row shape stays `flag + player_record_id` (5 bytes, same-size overlay).
- Authoritative same-entry roster rows can now be edited safely one non-empty slot at a time
  by changing the PID field within the now-confirmed `xor_pid + 0x61 0x61 0x61` 5-byte shape.
- `team-roster-edit-same-entry` now also accepts the strongest confirmed fallback mapping,
  `known_lineup_anchor_assisted`, when the selected preferred rows still validate the
  same `xor_pid + 0x61 0x61 0x61` contract.
- Those two proven row contracts can also be batch-edited safely from one CSV plan through
  `team-roster-batch-edit`, which validates row-by-row but commits them as one fixed-size
  overlay write with one backup.
- The main team overlay can now edit a selected authoritative roster row directly from the
  roster panel for both of those safe contracts:
  - linked rows can change `flag` and/or `player_record_id`
  - same-entry authoritative rows can change the PID field while preserving the observed filler tail
- The GUI also exposes the same shared batch path through `Batch Edit Team Roster from CSV...`
  in the Tools menu for the current confirmed linked and same-entry authoritative contracts.
- Variable-length team payload rewrites are still unsafe outside those proven fixed-size overlays.

## Known / Partial / Unknown

## Known

- team subrecord separator pattern
- team name extraction
- stadium name extraction
- parser-backed linked roster rows (`flag + player_record_id`)
- safe in-place mutation of one parser-backed linked roster slot (`flag` / `player_record_id`)
- authoritative same-entry inline roster rows with the current stable `xor_pid + 0x61 0x61 0x61` shape
- the same `616161` tail shape across all currently selected preferred same-entry fallback families
- GUI selected-row editing for authoritative linked and same-entry roster slots
- CLI and GUI batch editing for the proven linked and supported same-entry roster slot contracts
- GUI inspection of the confirmed roster sources through `Inspect Team Roster Sources...`,
  which surfaces the same parser-backed linked rows and authoritative same-entry coverage
  that the CLI exposes through `team-roster-linked` / `team-roster-extract`
- GUI inspection of competition-field candidates through `Inspect Competition Candidates`,
  which anchors after the currently known text region and shows the trailing bytes / peer
  histograms for the selected club's assigned competition
- GUI inspection of one selected club's primary `+0x00` family through
  `Inspect Primary-Code Family`, which focuses on the clubs sharing that
  primary code, highlights the current best non-text family-byte candidate, and
  now shows the local probe window around that byte for the selected club
- GUI profiling of cross-league competition signatures through `Profile Competition Signatures`,
  which compares the same anchor-relative bytes across the currently assigned competitions
  and now reports both the current `+0x00` candidate-byte codebook and the
  current `+0x08/+0x0A` family-split evidence explicitly, plus the current best
  tested third-byte refinement per primary-code family and the best current
  non-text family-byte candidate
- GUI profiling of dominant-country subgroups through `Profile Country Subgroups`,
  which focuses on country-like primary-code families and reports the current
  subgroup offset candidates for splitting the dominant-country bucket
- CLI parity for those competition probes through:
  `team-competition-profile`, `team-primary-family`, and
  `team-country-subgroup-profile`
- CLI league-placement audit through `team-league-audit`, which summarizes
  source/confidence/status counts and flags probe-vs-assigned mismatches
- the `team-roster-profile-same-entry` CLI path, which now profiles the authoritative same-entry
  tail bytes directly and confirms whether they remain invariant across the current dataset

## Partial

- exact location and layout of many team metadata fields
- reliability of inferred team IDs outside strongly parsed cases
- exact dedicated competition/country field bytes inside the decoded team payload
- meaning of all larger team-payload regions

## Unknown or Not Yet Safe

- full synthetic team-record rebuilding
- broad team metadata rewriting beyond the proven text paths
- any “invented” structural writes to unresolved team regions
- structural rewrites for roster modes other than the proven external EQ->JUG link table
- whether non-authoritative / fallback same-entry families also share the same invariant tail
- broader write safety for provisional same-entry mappings beyond `known_lineup_anchor_assisted`
  (the row shape is now proven wider than `same_entry_authoritative`, but mapping confidence
  still needs to justify writes provenance-by-provenance)

## Confidence Guidance

- If you need the most trustworthy team membership view, use the parser-backed EQ-to-JUG linked roster path.
- If you need the safest current roster write path, use the parser-backed `team-roster-edit-linked`
  flow and keep the edit to one fixed-size linked slot at a time.
- If a team has `same_entry_authoritative` coverage, `team-roster-edit-same-entry` is also safe
  for replacing the PID in one visible non-empty slot. The same command also supports
  `known_lineup_anchor_assisted` when that preferred fallback is present (for example, the
  current Manchester Utd path), but it still refuses weaker provisional provenances.
- `team-roster-profile-same-entry --include-fallbacks` now profiles all preferred same-entry
  provenances together and currently confirms the same `616161` tail across every selected
  preferred family in the real dataset.
- In the GUI, the same safe contracts are now available from the Team overlay roster panel
  through `Edit Selected Slot...` or by double-clicking a loaded supported same-entry roster row.
- If you need to apply many proven slot edits at once, use `team-roster-batch-edit` (CLI) or
  `Batch Edit Team Roster from CSV...` (GUI). Use `team-roster-export-template` (CLI) or
  `Export Roster CSV` (GUI) to generate an import-ready full-squad template first.
- If you want a one-shot full linked squad swap (for example replace Stoke slots with another club),
  use `team-roster-clone-linked`.
- If you want one target promoted name across an entire linked squad, use
  `team-roster-promote-bulk-name` (generic command; not team/name-specific).
- The current CSV plan supports:
  - `team`, `slot`
  - optional `source` (`linked` or `same_entry`)
  - optional `eq_record_id` / `team_offset` for disambiguation
  - linked edits: `player_id` and/or `flag`
  - same-entry edits: `pid`
- `team-roster-batch-edit --json` now includes a row-level `plan_preview`
  payload with `change` / `no_change` / `warning` states so GUI and CLI can
  render the same pre-apply diff surface.
- In the GUI, the confirmed read-side roster sources are also available from
  `Inspect Team Roster Sources...`, which is a structured Advanced Workspace counterpart to the
  current stable CLI roster reporting paths, including preferred fallback same-entry provenance
  when one exists.
- The same Advanced Workspace now also exposes `Inspect Competition Candidates...`, which is the
  current read-only RE surface for replacing the file-order league fallback with a true decoded
  competition field.
- `Profile Competition Signatures...` is the broader companion view when you need cross-league
  evidence for which anchor-relative bytes are most likely to encode competition placement.
- `Inspect Primary-Code Family...` is the narrower companion view when you need
  to study one selected club's current `+0x00` family directly and compare the
  family-byte values across the clubs that share it. It now also shows a small
  local probe window and adjacent `u16` interpretations around the selected
  club's current best non-text family-byte candidate, and when available it
  also shows the dominant-country subgroup candidate for country-like families.
- `Profile Country Subgroups...` is the broader companion when you need a
  per-cluster summary of those dominant-country subgroup candidates and a
  focused by-league breakdown for the current leading country-like family.
- On the current real corpus, the broad `0x7F` cluster is now classified as
  `country-like` and is strongly England-heavy, so the current leading hypothesis
  is that `+0x00` is at least partly a country/family discriminator rather than
  a fully direct league code.
- The newer `+0x08/+0x0A` secondary signature is useful, but still read-only:
  on the current real corpus it classifies `48` of `102` primary-code clusters
  as `competition-splitting`, while the dominant `0x7F` family remains `weak`
  at about `50.6%` average within-competition purity.
- The first tertiary pass is also read-only and currently negative: the best
  tested extra byte is `+0x01`, but the dominant `0x7F` family still profiles
  as `no-gain`, so that third byte is not yet a meaningful separator for the
  hardest remaining cluster.
- The best current non-text family-byte signal is stronger for that same hard
  cluster: after excluding text-like spill bytes, the dominant `0x7F` family
  currently points to `+0x16` as an `exploratory` candidate at about `64.2%`
  average within-competition purity. It is still read-only evidence, not a
  decoded dedicated field.
- The next narrower read-only lead inside that same `0x7F` family is now the
  dominant-country subgroup scan. For the England-heavy subset, the current
  subgroup candidate is `+0x19`, classified as `tentative` at about `42.9%`
  average within-league purity with `3` dominant values across the English
  league buckets.
- If you need general team metadata outside confirmed fields, treat it as heuristic unless the code explicitly models it.
