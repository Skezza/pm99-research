# Numeric display labels: narrow repair and replay

`season_numeric_name_format_only_v1` removes a leading shirt label such as
`#19 ` or the placeholder initial `#. ` from an existing player display name.
It supports both indexed player families and does not require a date of birth
or a new historical identity decision. Published spellings and aliases remain.

The writer retains the stored string lengths and fills the released display
bytes with trailing ASCII spaces. It verifies every byte outside that exact
window, including surname, biography, role, rating, startup and directory bytes.
Original recipe and native labels remain in the source-bound plan. A numeric
label in the separate protected surname component is rejected for review.

A source-name field is cleaned independently only when it has its own leading
label. This does not assert that source and display aliases are identical.
Missing source-name fields remain missing. The layer does not resolve ownership,
identity, dates, nationality or any other historical question.

The publisher binds the plan to the immutable baseline recipe and native file.
Independent replay regenerates and verifies the plan, descriptor, full recipe
and complete game inventory. Factory compilation rejects this layer rather than
silently dropping the repair. Publication and runner verification remain separate
steps; successful unit tests or an in-memory plan are not a delivered game fix.

Replay accepts the publisher's optional validated capacity reserve; its default
remains 8 GiB. The bounded serial pilot used the existing 7.5 GiB batch reserve
for both builds. A second actual build reproduced all 270 2023/24 display repairs
with identical recipe and complete game inventory. Runtime validation and
installation of that pilot remain separate pending steps.
