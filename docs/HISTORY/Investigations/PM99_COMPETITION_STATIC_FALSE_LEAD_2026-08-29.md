# Competition static-analysis false lead: zlib tables (2026-08-29)

## Ruled out

`MANAGPRE.EXE` data at `0x0070d628`, `0x0070d6a8`, `0x0070d728` and
`0x0070d7a0` must **not** be used as a country, league, carrier or selector
mapping.

It initially looked plausible because `FUN_006bccb0` passes the latter two
addresses to `FUN_006bc800` and their 32-bit values form tidy numerical
sequences.  Ghidra's direct memory read at `0x0070d600` resolves the preceding
embedded text as:

```text
1.1.3 Copyright 1995-1998 Mark Adler
```

That is the zlib signature.  The surrounding numeric arrays are therefore
compression/inflater support data, not PM99 club data.  The Ghidra listing of
`FUN_006bccb0` confirms it passes `0x70d628`/`0x70d6a8` and then
`0x70d728`/`0x70d7a0` into the same helper, which is consistent with that
interpretation.

## Consequence

No static competition mapping has been found in this pass.  In particular,
do not use the observed numeric clustering of `EQ` record ids as a substitute
for a league table or a membership write contract.  `competition.membership`
remains preserve-only until a separate runtime country/competition route and
reversible membership test exist.

This is a negative result, but it is useful: it removes a false lead before a
world compiler can encode it as “research”.
