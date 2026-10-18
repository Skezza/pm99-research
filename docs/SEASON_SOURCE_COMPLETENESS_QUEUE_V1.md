# Season source-completeness queue V1

`scripts/season_source_completeness_queue_v1.py` is the repeatable planning
surface for the 25 target seasons (2000/01–2025/26, excluding the separately
evidenced 2015/16 release). It answers a narrow question: for the precise,
hash-bound PM99 fixed carriers selected by the current allocation, what
historical source work remains before generic authoring layers can run?

It is a reader. It does not fetch data, modify a manifest, promote a package,
compile a database, launch PM99, or call anything playable.

## Scope and policy

The source archive contains more real clubs than a fixed PM99 season can
hold. The queue counts only the carrier assignments pinned by each immutable
`.local/season-historical-squad-backfill-v1/<season>/current.json`, never all
captured clubs. It verifies the current pointer's source, intake and
allocation SHA-256 values before it reports an item.

The report encodes the agreed policy rather than quietly making editorial
decisions:

| Lane | Rule |
| --- | --- |
| Managers | Every assigned club needs one exact opening-date manager name with a dated, hash-backed source. Native/current-manager fallback is forbidden. |
| Squad | The source target is the opening/August squad and first league XI. Later arrivals are not required. A source pool with at least eleven players is sufficient; excess rows can be trimmed to fixed capacity. |
| Formation | A published opening formation is preferred. If the XI is reconciled and its G/D/M/F positions are sufficient, deterministic inference is authorised. |
| Secondary player facts | Missing height, weight, shirt number, nationality and similar fields remain logged non-blocking fallbacks, rather than preventing a source queue replay. |
| Portraits | No task is created: the declared `native-no-photo` fallback is valid. |
| Kits | A continuing carrier needs historical source plus a matching rendered receipt. Native kit fallback is only valid for a carrier explicitly declared exited. |

## Refresh

```bash
python3 scripts/season_source_completeness_queue_v1.py \
  --output-json .local/operations/season-source-completeness-queue.json \
  --output-markdown .local/operations/season-source-completeness-queue.md
```

For a single worker shard, keep the same semantics and select one season:

```bash
python3 scripts/season_source_completeness_queue_v1.py \
  --season 2000-01 \
  --output-json .local/operations/season-source-completeness-2000-01.json
```

The Markdown is the compact progress view. The JSON includes every manager,
opening-XI and kit item with a stable carrier ID, club selector, reason,
required resolution, and a concrete next command. This makes the work
batch-addressable without manually transcribing JSON into a browser.

## Forward-only manager overlays

The fixed-carrier manager capture uses the allocation rather than the smaller
opening-lineup selector. It retains any valid dated manager already present in
the supplied ledger and only fetches the unresolved assigned carriers. When a
frozen squad source records a historic path such as
`squad/2007/ALB1/12457.html`, the worker reuses that exact year, competition
and club ID; it does not require a new hand-written competition map.

The capture writes a new supplement path once. Compose it with the previous
overlay and materialise a new, hash-bound overlay directory; do not alter the
calendar-bound base or a prior overlay:

```bash
python3 scripts/season_manager_overlay_v1.py \
  --baseline-index .local/season-baselines-v1/calendar-bound-v2.json \
  --season 2007-08 \
  --source-capture .local/season-historical-squad-backfill-v1/2007-08/revisions/<revision>/world-squads-composed.json \
  --opening-lineups .local/transfermarkt-opening-plans-current-v1/2007-08/opening-lineups.json \
  --supplement .local/season-overlays-v1/2007-08/manager-v1/manager-supplement.composed.json \
  --supplement .local/operations/2007-08/opening-manager-supplement.allocated-transfermarkt-v2.json \
  --output-root .local/season-overlays-v1/2007-08/manager-v2
```

To measure that overlay rather than the earlier current ledger, select it
explicitly. The queue verifies the overlay audit's source and opening-lineup
hashes and the ledger output hash before accepting it.

```bash
python3 scripts/season_source_completeness_queue_v1.py \
  --season 2007-08 \
  --manager-overlay-root .local/season-overlays-v1 \
  --manager-overlay-id manager-v2 \
  --output-json .local/operations/2007-08/source-completeness-manager-v2.json
```

## Per-season manager-overlay index

A 25-season aggregate cannot accept a single `--manager-overlay-id`: repaired
seasons have different immutable versions.  Build an index from a manifest
that names **one exact `manager-vN` ID for every baseline season**.  The index
records the baseline, manifest, selected audit and selected ledger SHA-256
values.  It never scans a directory to choose a numerically newest version.

The checked local example selects the completed 2016/17–2025/26 repair
tranche as `manager-v2`, except 2020/21 as `manager-v3`; it also explicitly
retains the verified `manager-v2` for 2007/08.  All other baseline seasons are
spelled out as `manager-v1`.  To advance a selection, make a new manifest and
new index path; neither command overwrites an existing pointer.

```bash
python3 scripts/season_manager_overlay_index_v1.py \
  --selection-manifest \
    .local/season-overlay-selection-manifests-v1/calendar-bound-v2-manager-overlays-explicit-v1.json \
  --output \
    .local/season-overlay-index-v1/calendar-bound-v2-manager-overlays-explicit-v1.json

python3 scripts/season_source_completeness_queue_v1.py \
  --manager-overlay-index \
    .local/season-overlay-index-v1/calendar-bound-v2-manager-overlays-explicit-v1.json \
  --output-json .local/operations/season-source-completeness-explicit-manager-index-v1.json \
  --output-markdown .local/operations/season-source-completeness-explicit-manager-index-v1.md
```

The aggregate reader verifies the index's own baseline and selection-manifest
bindings, then for every season verifies the selected overlay audit and ledger
hash, the baseline hash, the current source capture hash and the current
opening-lineup hash.  A missing or stale pointer is a hard failure, never a
fallback to a different overlay.  This is still a source-completeness report,
not a release or playable-game claim.

Manager-history workers share `.local/external-sources/cache.transfermarkt-opening`.
Run source-fetching workers serially against that cache (or give a worker an
isolated cache and preserve its distinct receipt) so two processes never race
to create the same snapshot file. Pure validation, package and report stages
remain safe to parallelise.

For a re-runnable serial capture batch, use a new receipt path and select the
seasons deliberately. Existing versioned raw receipts are inspected and
skipped; they are not regenerated.

```bash
python3 scripts/run_allocated_manager_backfill_batch_v1.py \
  --season 2002-03 --season 2003-04 \
  --receipt .local/operations/allocated-manager-backfill-batch-v1/<new-receipt>.json
```

After it has completed, materialise the independent, non-fetching overlay
batch. It requires the raw receipts and similarly refuses to replace an
existing `manager-v1` directory.

```bash
python3 scripts/run_season_manager_overlay_batch_v1.py \
  --season 2002-03 --season 2003-04 \
  --receipt .local/operations/season-manager-overlay-batch-v1/<new-receipt>.json
```

## Forward-only opening-XI overlays

`capture_allocated_opening_lineups_v1.py` applies the same fixed-carrier,
historic-ID rule to opening lineups. It retains every selector already present
in the current reconciliation and fetches only the missing assigned clubs for
which the frozen squad source supplies an exact
`squad/<year>/<competition>/<club-id>.html` path. It never falls back to a
current club page or silently replaces an established receipt.

The source-fetching batch is serial because it shares the Transfermarkt
snapshot cache. Its result is an immutable raw receipt per season. The next
stage is local-only: it reconciles that receipt to the full hash-bound squad
source, then writes an `opening-xi-v1` overlay containing the original
reconciliation plus the non-overlapping new rows.

```bash
python3 scripts/run_allocated_opening_lineup_backfill_batch_v1.py \
  --season 2000-01 --season 2001-02 \
  --receipt .local/operations/allocated-opening-lineup-backfill-batch-v1/<new-receipt>.json

python3 scripts/run_season_opening_lineup_overlay_batch_v1.py \
  --season 2000-01 --season 2001-02 \
  --receipt .local/operations/season-opening-lineup-overlay-batch-v1/<new-receipt>.json
```

The second command refuses to replace an existing `opening-xi-v1` directory.
The queue must opt in to that exact overlay ID; it verifies the current source
SHA-256, the unchanged base-reconciliation SHA-256, and the overlay-output
SHA-256 before using it.

```bash
python3 scripts/season_source_completeness_queue_v1.py \
  --season 2000-01 \
  --manager-overlay-root .local/season-overlays-v1 \
  --manager-overlay-id manager-v1 \
  --opening-xi-overlay-root .local/season-overlays-v1 \
  --opening-xi-overlay-id opening-xi-v1 \
  --output-json .local/operations/2000-01/source-completeness-opening-xi-v1.json
```

## Using work items

The `manager` queue points to the exact league/club selector and (when it is
already known) the opening-fixture date. The per-season `commands` object
contains the reusable manager-history capture and ledger-rebuild command
templates. Each supplement must still be dated and hash-backed; a successful
command with unresolved rows is not an approval to fall back to a current or
native manager. Where an opening-lineup receipt declares both a full-source
hash and a selector-projection hash, the generated manager command supplies
both files. The capture refuses either mismatch and only considers clubs in
that exact projection; it cannot accidentally attach a valid manager page to
the wrong source snapshot.

The `opening_xi` queue divides source absence from reconciliation and formation
problems. It does not ask a worker to invent a formation when the player
positions cannot support the permitted deterministic inference.

The `secondary_player_facts` counters intentionally do not create work items.
They are retained so later editorial enrichment is measurable, without making
the database factory wait for optional facts.

After a queue is reduced, the next mechanically repeatable step is the
authoring-layer integrator, followed by the normal strict V2 package,
workspace/static audit, runtime route, and season-specific screenshot gates.
None of those gates is represented by this report as complete.

## Calendar binding batch

`scripts/season_calendar_batch_bind_v1.py` binds the independently verified
calendar receipt and patched `MANAGPRE.EXE` hash to one replayed draft per
season. It uses separate input and output roots and refuses to overwrite an
earlier output root. A bounded `--workers` value (1–8) may process independent
season directories concurrently; every worker still performs the same
per-package structural validation and receipt/hash verification.

```bash
python3 scripts/season_calendar_batch_bind_v1.py \
  --input-root .local/season-draft-replay-v2 \
  --output-root .local/season-calendar-bound-batch-v2 \
  --workers 4
```

A calendar-bound draft remains provisional: this command does not promote a
package, compile a database, run PM99, or satisfy the screenshot gate.

## Freezing the forward baseline

After a complete calendar batch has been independently checked, freeze it once
as an append-only selection index. This does not rebuild packages or re-fetch
sources; it records the batch's existing hashes for downstream overlays.

```bash
python3 scripts/season_baseline_index_v1.py \
  --calendar-bound-root .local/season-calendar-bound-batch-v2 \
  --baseline-id calendar-bound-v2 \
  --output .local/season-baselines-v1/calendar-bound-v2.json
```

The output path is write-once. A correction belongs in a new baseline or a
season-specific, hash-bound overlay; it must never mutate this selection in
place.
