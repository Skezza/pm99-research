# Factory kit pixels with compatible native BMP wrappers

Some original kit BMPs have two extra opaque bytes. Their visible geometry can
match another record even though their complete file lengths differ. The stock
kit writer correctly rejects a whole-BMP copy between these records.

`season_factory_bitmap_envelope_v1.py` uses the upstream pixel-row reader/writer
to put literal factory pixel indices into the target's existing BMP wrapper. It
preserves that wrapper's header, row padding, trailer and length. It creates a
separate source envelope; it never changes a playable game or original source.

PKF directory entries contain absolute offsets. The envelope preserves the
original source archive's allocation and every later offset, updates only the
selected source record's length, and leaves any now-unused trailing bytes exact.
All other source records and all bytes outside the bounded source patch remain
unchanged. Only identical lengths or a two-byte shorter target are admitted.

The existing stock-kit SDK remains unchanged. It receives a sealed, compatible
source envelope and still enforces its original size, country, approval, palette,
parent and unchanged-data checks. The caller must independently prove club
identity. This adapter does not establish identity or period-specific designs.

Proofs distinguish **literal original factory pixels** from **original raw BMP
bytes**: wrapped files are not claimed to have identical original headers. The
final game must preserve all unselected archive bytes and reproduce the original
factory pixel rows at every size. SOURCE replay and genuine runner pixel checks
remain required before release promotion.

Six tests cover opaque-byte preservation, incompatible geometry, header-offset
and trailing-byte variants, absolute PKF offsets, other records and refusal to
overwrite an existing envelope. A real 2002/03 source envelope has also passed
those native parser and pixel equivalence checks; its game build/runtime proof
is pending under `.local/consolidated-audit-20261009/parallel-rc-20261023/resume-qa/az-factory-identity-alias-v1/2002-03-source-identity-factory-r451-v1/`.
