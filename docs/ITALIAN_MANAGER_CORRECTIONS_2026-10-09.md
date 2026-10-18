# Italian opening-season manager corrections

## Both manager corrections current and runtime verified

Vostro (`joe-Vostro-3350`), source session
`01a0592d-fcd5-7262-a637-743a8253d9b4`, UTC2026-10-08 23:49
(October9 in the client's Europe/London timezone).

The two target managers are Palermo2005/06 Luigi Del Neri and Atalanta2006/07
Stefano Colantuono. Both previously inherited Roberto Mancini. Native manager208
is exclusively linked to club223 in each independent season. No other manager,
player, lineup, tactic, kit or portrait is changed by these corrections.

Source authority is retained in `.local/editorial-closeout-20261008/sources/`:

- [UEFA's dated Palermo appointment, May31 2005](https://www.uefa.com/news-media/news/01a9-0f84745a5c02-5fd4f2f4b599-1000--del-neri-to-push-palermo-on/).
- [UEFA's contemporary Atalanta report, November10 2006](https://www.uefa.com/news-media/news/01bb-0f848ead368c-a33b40753366-1000--atalanta-up-the-italian-ante/),
  combined with [the opening summer's Colantuono confirmation](https://it.wikipedia.org/wiki/Atalanta_Bergamasca_Calcio_2006-2007).

Preparation script `scripts/prepare_italian_manager_closeout_v1.py` checks
retained text anchors, source hashes, exclusive ownership and immutable current
recipe/native preimages. It does not invent a first-fixture manager-page reparse.
Direct download of the Lega August29 PDF failed DNS; it is not represented as a
retained downloaded source.

## Durable fixes and preservation

Canonical name edits now refresh existing `native_names` aliases, preventing
old-person display text surviving a correction. The original R56a candidate
exposed a separate provenance defect: a small update overwrote the season-wide
manager evidence reference. R56a was never made current.

Final candidates use `sourced-italian-manager-corrections-20261009-r56b` and
content-addressed manager-update filenames/proof IDs. They preserve all earlier
artifact/proof declarations and inherited evidence files, including318 Palermo
and320 Atalanta managers' prior manager-plan references. Tests prevent recurrence.
The raw receipt hash includes the JSON writer's trailing newline; the filename
uses the canonical content hash. Reconstruction explicitly verifies both forms.

`build_registered_quality_release_v1.py` supports exact manager-only replay on
the known-good R55 source. It checks source descriptor/package/compiler/chain,
whole source/current/rebuilt inventories and exact derived recipe equality.
Extra edits, mixed edit lanes, non-inert player updates and publication from an
explicit reconstruction source are refused. This is not a clean factory build
and does not relax its unrelated duplicate-person gate.

Whole-game normal reconstruction PASS for both R56b candidates, proof ID
`italian-manager-normal-replay-proof-20261009-r56q`. Both normal CLI build
`--resume` commands verify/reuse those outputs without regeneration. Expanded
test lane141 PASS/2 existing skips; tracked boundary and diff checks PASS.

## Exact-file runtime evidence

Both actual friendly runs returned run/sync/cleanup0. Root viewed the manager
introduction, full-time and post-match dashboard:

- [Palermo: Del Neri](/home/joe/pm99-research/.local/editorial-closeout-20261008/runtime/palermo_r56_manager_xi_20261009/screens/76_autocontinue_inspect_012.png), Arsenal1–2Palermo, August4 dashboard.
- [Atalanta: Colantuono](/home/joe/pm99-research/.local/editorial-closeout-20261008/runtime/atalanta_r56_manager_xi_20261009/screens/75_autocontinue_inspect_012.png), Arsenal0–0Atalanta, August4 dashboard.

The runs actually loaded R56a, not R56b. R56b changes only recipe/evidence
references relative to R56a: entire game inventories are identical. All ten
independently SSH-read runtime game inputs match R56b too. This exact-file
equivalence is explicit in `manager-r56-runtime-verification.json` and
`manager-r56b-prepublication-audit.json` under `.local/editorial-closeout-20261008/`.
The run tags include `xi`, but the optional statistics adapter flag was not set;
these are standard-driver full friendlies, not new foreign-XI statistics proofs.
Earlier source-XI preservation/evidence remains exact-byte valid for unchanged
JUG/EQ. Do not pretend new starting-XI screenshots were captured here.

Queued R56a normal captures were cancelled before acquiring the host or creating
a remote run root, after local process/remote state checks. R56b fresh normal
captures have new tags and exact manifest bindings; do not relabel old summaries.
No live Bash source was edited; local normal-capture source was updated only
after its old process group was confirmed terminal.

## Publication and scope

Fresh R56b normal startup/Line-Up captures passed for both seasons. Root viewed
Palermo capture024 and Atalanta capture022. Both R56b releases are now current,
normal-runtime attested and individually full-release valid. Normal play commands
select the corrected games:

```sh
./pm99-season play 2005-06
./pm99-season play 2006-07
```

Final all26 full-release integrity PASS after both promotions, other24 release
IDs unchanged. Original2015 whole inventory preserved;8GiB reserve PASS.
Receipt `.local/editorial-closeout-20261008/all26-post-manager-promotion-integrity.json`,
SHA256 `bdd23bd83fa262e8da8178425f71730e57afe4e23b34a5d6f8ae392ddfcb682f`.
Closed UTC2026-10-09 00:01 on Vostro; no live follow-up jobs remain.

Both clubs still display inherited red/black kits. This correction deliberately
does not fix them. The initial census listed792 inherited2015 manager proof
references outside2015; the final current census is790 after these corrections.
These are review candidates, not790 proven wrong managers. Preserved-kit
declarations can be overridden by separate asset layers and are not an error count.
Reserve, secondary-position and global historical-quality work remains separate.
Original2015/source preimages remain retained;8GiB disk reserve is required.
