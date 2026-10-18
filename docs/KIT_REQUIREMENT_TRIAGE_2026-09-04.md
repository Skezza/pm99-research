# Historical kit requirement triage

## Result

The 25 historical kit capture/render directories are **not current release
inputs**.  Every one is bound to an older historical allocation revision than
the season's current pointer.  Consequently all 10,351 current fixed-carrier
kit requirements are fail-closed as `conflicting`, and there is no safe
automated kit integration tranche.

This is a provenance result, not an instruction to discard the old artifacts.
The retained artifacts are useful, hash-bound diagnostic evidence after the
current allocation has been recaptured, but must not be joined into an
authoring package or written into a game tree today.

The read-only ledger is
`.local/season-kit-requirement-triage-v1/20260904/kit-requirement-triage.json`
(SHA-256 `84a0c105b09442c5b0ed1c7f0fb88aaccb62be1cab35f3687c0e799864794a91`).
It binds every input file SHA-256, every current pointer/allocation SHA-256,
and every fixed-carrier requirement.  No bitmap, package, kit binding or
fallback was changed to produce it.

## Current classification

| Classification | Requirements |
| --- | ---: |
| `conflicting` | 10,351 |
| `captured-but-unrendered` | 0 |
| `renderable-but-unbound` | 0 |
| `genuinely-uncaptured` | 0 |
| `rendered-and-bound` | 0 |

All 25 capture documents disagree with the corresponding `current.json` on
the historical revision ID, current-pointer SHA-256 and allocation SHA-256.
That deliberately blocks every otherwise promising row: a stale kit for a
recycled carrier is not historically safe merely because its old artifact is
still present.

## Retained-artifact diagnostic

The following is explicitly non-release diagnostic coverage: it answers what
the old artifacts appear to contain, after ignoring their stale allocation
provenance.  It must be regenerated against the current allocation before any
row can move into the current classification.

| Stale-artifact diagnostic | Requirements |
| --- | ---: |
| `genuinely-uncaptured` | 8,257 |
| `captured-but-unrendered` | 1,632 |
| `conflicting` | 365 |
| `renderable-but-unbound` | 0 |
| `rendered-and-bound` | 97 |

The 1,632 captured-but-unrendered rows have a source-ready catalogue entry but
the renderer receipt records an unavailable exact render prerequisite.  The
97 rendered-and-bound rows have matching retained artifact bytes and binding
records, but remain ineligible solely because the capture was made for an old
allocation.  There are no renderer receipts that prove a render while lacking
the corresponding binding; this rules out a mechanical "bind existing images"
tranche.

The 365 diagnostic conflicts are carrier identity disagreements between the
old allocation/capture/catalogue/receipt chain.  They are not safe aliases:
the report records the exact carrier rows rather than normalising their club
names or guessing an ownership mapping.

| Season | Allocated | Rendered + bound* | Captured, unrendered* | Uncaptured* | Artifact conflict* |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2000/01 | 383 | 36 | 1 | 340 | 6 |
| 2001/02 | 382 | 26 | 13 | 343 | 0 |
| 2002/03 | 392 | 2 | 36 | 352 | 2 |
| 2003/04 | 401 | 1 | 36 | 363 | 1 |
| 2004/05 | 410 | 1 | 34 | 373 | 2 |
| 2005/06 | 416 | 2 | 28 | 385 | 1 |
| 2006/07 | 423 | 1 | 35 | 386 | 1 |
| 2007/08 | 427 | 1 | 30 | 376 | 20 |
| 2008/09 | 427 | 1 | 37 | 371 | 18 |
| 2009/10 | 424 | 2 | 39 | 365 | 18 |
| 2010/11 | 423 | 4 | 61 | 340 | 18 |
| 2011/12 | 429 | 1 | 70 | 340 | 18 |
| 2012/13 | 428 | 4 | 77 | 329 | 18 |
| 2013/14 | 425 | 2 | 77 | 326 | 20 |
| 2014/15 | 412 | 4 | 76 | 314 | 18 |
| 2016/17 | 431 | 2 | 85 | 321 | 23 |
| 2017/18 | 412 | 1 | 78 | 312 | 21 |
| 2018/19 | 412 | 2 | 89 | 301 | 20 |
| 2019/20 | 413 | 1 | 95 | 298 | 19 |
| 2020/21 | 400 | 1 | 137 | 242 | 20 |
| 2021/22 | 407 | 1 | 121 | 265 | 20 |
| 2022/23 | 409 | 0 | 104 | 284 | 21 |
| 2023/24 | 406 | 1 | 99 | 286 | 20 |
| 2024/25 | 434 | 0 | 107 | 306 | 21 |
| 2025/26 | 425 | 0 | 67 | 339 | 19 |

\* Diagnostic only; none may be materialised without a current recapture.

## Reproducible audit

```bash
python3 scripts/season_kit_requirement_triage_v1.py \
  --historical-root .local/season-historical-squad-backfill-v1 \
  --catalogue-root .local/season-kit-sources-historical-backfill-v1 \
  --render-root .local/season-kit-renders-historical-backfill-v1 \
  --output .local/season-kit-requirement-triage-v1/20260904/kit-requirement-triage.json
```

`season_kit_requirement_triage_v1.py` is intentionally read-only.  Its
fixture test covers the five exclusive states (`rendered-and-bound`,
`captured-but-unrendered`, `renderable-but-unbound`, `genuinely-uncaptured`,
and `conflicting`) and proves that changing only a `current.json` pointer
invalidates otherwise healthy prior artifacts.

## Safe next sequence

1. Freeze each selected current allocation revision; do not mutate a prior
   kit directory.
2. Replay the existing capture/cache process into a **new revision-named kit
   source directory**, checking its provenance against that exact current
   pointer.
3. Render source-ready rows into a matching new render directory.  Preserve
   unresolved rows as explicit kit gaps; do not apply a native fallback for a
   continuing club.
4. Re-run this triage.  Only `rendered-and-bound` rows from a current clean
   season are admissible input candidates.
5. Implement and test the separate generic kit-archive materialiser, which
   must consume only those bindings and issue a package/base/output-bound
   receipt.  It does not exist yet, so even a future current binding is not by
   itself a game-tree integration command.

This splits an actual source recapture/render queue from the missing archive
write adapter.  Neither task requires re-researching PM99 bitmap mechanics,
and neither authorises using the defective legacy 2015 foreign-kit output.
