# Correct a person while preserving an opaque opening

A source-backed identity correction may affect an existing starter whose club
has only the original native opening policy. It must not require an invented
fixture date, starting XI or tactical coordinates.

The reviewed-country v2 `players-only` transaction accepts an optional
`static_native_openings` witness keyed by the existing club carrier. Generate it
with `static_native_opening_snapshot(eq_bytes, jug_bytes, club_carrier)`.
The input already pins the complete immutable parent recipe and native hashes.

The witness covers the exact encoded EQ payload and every mode-1 roster member's
startup order, all six fine roles and primary position. Nonzero row flags and
repeated carriers are refused. Selected actors must remain exclusively owned.
All club recipe rows, including opening policy and roster links, stay exact.
No complete-order writer, EQ writer or manager writer runs on this path.

A parent's explicit fine roles must match native readback; the existing opaque
preserve policy is also accepted because the witness reads the real bytes.
The replacement must declare the same concrete roles and primary position.
After compilation the complete witness must still match. Changing a forward
into a defender slot, or changing a left-back into a centre-back, is refused.
Such a change needs a separately reviewed role/opening correction.

This records preserved native controls, not a claim that the inherited lineup
or formation matches a historical fixture. Source evidence for the new person
remains bound separately in the authoring receipt. Missing secondary facts and
portraits keep the existing documented fallback rules.

Publication input copies are also validated during preparation: each new recipe
artifact needs a bound source path, confined unique destination and matching
recipe hash. These source hashes are rechecked on cache hits. A malformed copy
request fails before native staging, rather than leaving a partial unpublished
game. Existing inputs without new artifacts retain their previous path.
