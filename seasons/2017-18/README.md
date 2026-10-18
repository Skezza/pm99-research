# PM99 2017/18 world-season intake

Status: **blocked intake; not a package, build, runtime-qualified database, or
delivery.**  This directory records the safe work completed for the 2017/18
worker stream and the remaining evidence gaps that prevent a source-backed
world-season ledger from being authored.

## Completed immutable-base intake

| Input | SHA-256 | Result |
| --- | --- | --- |
| `sources/footballsquads-2017-18.json` | `2550391d19362dff0e4c25f3132fe88561fddd05fd255aec3d3297bdc66d743c` | Canonical CC0 source capture: 563 club squads and 17,145 player rows; it retains one blocked source. |
| `fixed-carrier-registry.json` | `7476d4a59fc9d7ebbcf31c40268940f5a4399cc75db67ddf3e11e7b6db0a4375` | 451 native foreign carriers / 9,390 roster slots, read from the verified clean base. |
| `fixed-carrier-ledger.json` | `07377741d534315bf06815747ed622af41b0f45488fb91d5d469d87b841f935c` | Empty, hash-locked 2017/18 authoring ledger. |
| `fixed-carrier-intake-audit.json` | `0393247c0f459fdda22e23563a5f27296eb145cd58168f33d8b45a42ce379d80` | Audit records 451 unassigned carriers and 36 shared baseline player carriers. |

The registry pins the clean-base database files: `ENT98030.FDI`
`729e486b441131c07dcbd3f6ba962587333459d8639329249646a86dd9ee3238`,
`EQ98030.FDI`
`e095cb47ffdb6c8edf384983545124eb514d044fa4f0ce7d924b6bfe13252a5c`,
and `JUG98030.FDI`
`95641e9d7fc0adb673045d43223d0ce7cfca531cd451f2f33e43425b05452844`.
It is a capacity and binary-layout inventory only; it does not establish
2017/18 club membership, identities, or competition topology.

## Dated-source coverage and remaining source blocker

The local CC0-1.0 `footballcsv/cache.footballsquads` cache is pinned to
revision `187c963e76e2bd1d9a65e2f0f3b04d9b57ba3555`.  Its 2017/18 source
folder has 564 current-squad files across 21 country catalogues and 32
competition catalogues.  The canonical capture retains 563 usable squads
from that set.  It records 790 player rows with an unresolved physical or
shirt-number fact: 70 birth dates, 695 heights, 757 weights and 31 shirt
numbers.  Those facts remain editorial blockers, not permissive defaults.

The full capture is reproducible with:

```bash
python3 scripts/capture_footballsquads_season.py \
  --source-root .local/external-sources/cache.footballsquads \
  --season 2017-2018 \
  --output seasons/2017-18/sources/footballsquads-2017-18.json
```

The shared parser now accepts the cache's `2017/2018` title form while
normalising the package-season label to `2017/18`; it has not relabelled the
source files.

One source remains deliberately blocked in the capture:
`ger/2017-2018/bundes/mainz.txt` (SHA-256
`a29cee363057987ded4c2b6b015d0c5be8617e0fd3d6589c1fd72d54f188ebaa`) has a
current-squad CSV row with no player name.  The capture makes no identity
substitution.  It must be corrected from an identity-safe dated source before
the all-country scope can close.

The cached Stoke squad source is
`eng/2017-2018/faprem/stoke.txt`, SHA-256
`8992444eda754d335a0517becdbffc278a7c4347ac21f652ba8259787d49c66e`.
It is a squad-list source, not opening-XI or tactic evidence.

## Resolved shared-schema constraint

The shared ledger schema and validator now accept 2000s birth dates, which is
required by the dated Stoke squad (for example Josef Bursik).  This removes a
false technical rejection; it does not resolve any player identity, carrier,
rating, asset, kit, manager or lineup evidence.

## Candidate-only Spanish-host identity milestone

The coordinator derived a separate candidate-only proposal from the reviewed
Spanish host queue.  Its output is deliberately neither an approval nor a
replacement for `foreign-carrier-assignment.json`:

| Output | SHA-256 | Meaning |
| --- | --- | --- |
| `foreign-carrier-candidate-proposal.json` | `2fcf30df6300ff38d37f4335b4520c6611beb72fdf2edfd405f12b8fb1fd8697` | Five deterministic single, capacity-compatible name-token leads. |
| `foreign-carrier-assignment-candidates.json` | `04769b36522a6903b34d0aad77610b1548eaacfdb44fcde735b17fae8556223a` | Derived candidate ledger, separate from the zero-assignment base ledger. |
| `foreign-carrier-assignment-candidates-audit.json` | `d47983a38d9deeec664fae51473db7d58cff982ecb95d4fa260fc6de596b1c3a` | Candidate audit: five candidates and 446 unassigned foreign carriers. |

The five leads are carrier 2 / Deportivo La Coruña, 3 / Zaragoza, 4 / Real
Madrid, 5 / Athletic Bilbao, and 7 / Valencia.  They have status `candidate`
only and retain the required editorial, full-club-content and runtime gates.
No candidate writes PM99 data or establishes a division, membership, or draw
pool.

Carrier 1 is **intentionally absent** from the proposal.  The source queue
finds both Barcelona and Barcelona B as capacity-compatible Spanish name-token
matches.  That ambiguity is preserved for human identity review; it has not
been resolved by name similarity or current source catalogue membership.

Reproduce and validate the proposal:

```bash
python3 scripts/season_candidate_identity_milestone_v1.py \
  --season-dir seasons/2017-18 --replace

python3 scripts/foreign_carrier_candidate_proposal_v1.py \
  --registry seasons/2017-18/fixed-carrier-registry.json \
  --source-capture seasons/2017-18/sources/footballsquads-2017-18.json \
  --assignment seasons/2017-18/foreign-carrier-assignment.json \
  --queue seasons/2017-18/foreign-carrier-candidate-queue.json \
  --proposal seasons/2017-18/foreign-carrier-candidate-proposal.json
```

## Local calendar eligibility proof

The verified clean `MANAGPRE.EXE` (SHA-256
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`) can
be patched locally for target year 2017 and rollover 2018.  The local-only
receipt at `.local/builds/2017-18-calendar/calendar-receipt.json` records 853
patches; its SHA-256 is
`abc6748164a74ed2d144d6843b33d7ec0da5f8558fb4ddc1bbfc8911caed8ec5`, and the
patched executable SHA-256 is
`1e4018fd2f077e43f470b8b4f028d451771ea0bf6d32301e0685c78465ddaa82`.
Those proprietary local artifacts prove calendar eligibility only, not a
database build or runtime qualification.

## Delivery gate

No carrier has been assigned, no player identities or ratings have been
invented, and no kits, portraits, managers, or club metadata have been
applied.  There is no strict package, build, release hash, runtime execution,
or Stoke City lineup screenshot.  A screenshot before a source-complete,
runtime-qualified release would be misleading and is deliberately absent.

After the two shared blockers are fixed, the next safe sequence is: capture
and hash every dated squad source; reconcile source-backed club, manager and
person identities; resolve all 451 fixed carriers and 36 shared baseline
carriers; evidence ratings, kits, portraits/no-photo and opening lineups;
then make two clean matching builds and capture the runtime Stoke starting XI
from that exact release inventory.
