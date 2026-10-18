# 1990/91 single-run exploratory closeout

Date: 2026-09-07

## Outcome

The simplified front door proved that an arbitrary pre-1999 season can be
collected, normalised, rated and statically compiled in one invocation:

```bash
./pm99-season preview 1990-91
```

Cached evidence can be replayed without reacquisition with:

```bash
./pm99-season preview 1990-91 --offline
```

This is an exploratory partial build, not a playable or historically complete
1990/91 release. Its purpose was to measure how much the generic path obtains
before any season-specific corrections.

## Measured result

- 17 country catalogues and 306 clubs captured.
- 7,234 unique source player rows captured.
- 211 target-season foreign clubs and 4,608 target-season player rows authored.
- Stoke City source squad captured with 22 players.
- Deterministic editorial ratings applied.
- Calendar generated and static compilation completed.
- Clean-static audit passed with no appended/recycled carriers and no fixed
  roster-tail mismatch.

The immutable summary is
`.local/season-1990-91/simple-preview-v1/preview-report.json` with SHA-256
`603e68a0f52ef0dd39b66324e2ccee3fe90505c93c94931fac7bfa45f6b5de51`.
The clean-static audit SHA-256 is
`f1b2d01fbee42c1d60ecd198069d5c4d11032386cf8986f61f112d22d74b4eee`.

## Explicit gaps

V1 did not author the 48 captured English clubs into their fixed-league
carriers. It also acquired no opening lineups, target-season managers, kits or
portraits, and it did not launch the result in PM99. Native managers in this
tree are diagnostic fallbacks only and violate the agreed historical-manager
policy. The 1990/91 artifact therefore remains
`compiled-provisional-partial-not-runtime-validated`.

The experiment did establish the reusable intake/compiler front door. The
2001/02 milestone then supplied the missing English opening squad, manager,
formation, rating and kit layers and proved that richer path in the game.
