# Selected mode-0 shirt writes

The authored-country v2 writer can correct an explicitly sourced shirt number
for a selected indexed `dd6361` player in a mode-0 club. Permission comes from
the actual encoded EQ roster: exactly one matching visible row with flag zero,
plus the transaction's existing exclusive-ownership check. Club mode and row
flag are separate values.

The ordinary isolated player compiler still preserves club and startup bytes.
The extra write changes only encoded byte 7, after validating an integer shirt
number from 1 through 99. A preserve-existing policy writes nothing. Unknown
headers, directory records, startup controls and handling-tail checks remain.
Mode-1 callers and callers without the explicit scope keep their previous path.

The 2003 Doncaster canonical preparation exercised the actual integration on
three players, preserving every EQ/ENT byte and all startup orders. Its shirts
20 (Green), 9 (Barnes), and 25 (Burton) agree with the retained published squad.
This preparation is not a built, installed or runtime-verified release.
