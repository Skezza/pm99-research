# World 2015 portrait application

`scripts/apply_2015_world_portraits.py` is the isolated game-tree write stage
for the world portrait lane. It requires an allocation-remapped asset manifest
with globally unique final player carrier IDs and the exact hash-bound portrait
materialisation receipt.

Identity-bound successful conversions replace an existing `MINIFOTO.PKF`
payload when its shape matches, otherwise they use PM99's supported loose
`DBDAT/MINIFOTO/J96xxxxx.BMP` lookup. Every download/conversion failure and
every player without an identity-safe source is actively changed to PM99's
native no-photo state. An inherited 1999 face is never retained as fallback.

The stage verifies complete coverage before writing and emits one operation per
selected player. It does not edit the EXE, JUG, EQ or ENT files.
