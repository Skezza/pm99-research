# PM99 Calendar Patcher: 2015/16 Proof

## Result

The first guarded profile is now a separate Calendar Patcher.  It makes a new
`MANAGPRE.EXE` beside the original; it is not part of the browser database
editor and it never writes to the supplied EXE.

Its known input is the No-CD `MANAGPRE.EXE` with SHA-256
`01b845f7dc728e3813968bed51ff24810fde556fab395e97ca7649c57ee53158`.
For that exact build, the patcher rebases the two calendar years hard-coded
into the opening schedule:

| Original schedule year | 2015/16 output |
| --- | --- |
| 1998 | 2015 |
| 1999 | 2016 |

This matters.  Changing only the first year puts the game clock and the
fixture list in disagreement; the PM Trophy draw then has no valid fixtures.
The complete validated profile changes 50 recognised 1998 operands and 803
recognised 1999 operands.  Raw byte searching is not used, because the same
two-byte values occur in unrelated instruction addresses.

## Runtime proof with the 2015 Stoke database

Fresh-game route `calendar_2015_two_year_probe_20260827` completed with
`success: true` and `crash_detected: false` on the PM99 runner.  The dashboard
shows **August 2015**:

- `upstream/pm99-runner/docs/artifacts/pm99_runner/calendar_2015_two_year_probe_20260827/screens/019_dashboard_select_squad.png`

The same new game opened real Stoke 2015 player records.  PM99's profile view
does not show a date of birth; it shows the resulting age.  The underlying
database dates and the visible results agree:

| Player | Database date of birth | Expected age in August 2015 | Visible profile |
| --- | --- | ---: | --- |
| Jack Butland | 10 March 1993 | 22 | `screens/026_profile_open_01.png` |
| Glen Johnson | 23 August 1984 | 31 after his birthday | `screens/029_profile_open_02.png` |
| Geoff Cameron | July 1985 | 30 | `screens/032_profile_open_03.png` |

All three profiles sit in
`upstream/pm99-runner/docs/artifacts/pm99_runner/calendar_2015_two_year_probe_20260827/`.

The original indexed player record for **Neville Southall** is record `9080`
with date of birth **16 September 1958**.  At the proven August 2015 clock he
is therefore **56**, and will turn 57 on 16 September.

That date was tested independently.  A clean copy of the 2015 Stoke database
changed only active Marko Arnautovic's DOB to Southall's DOB; it re-opened
cleanly in the editor and a complete fresh-game runner route passed
(`success: true`, `crash_detected: false`).  Its evidence is in
`upstream/pm99-runner/docs/artifacts/pm99_runner/calendar_2015_southall_dob_only_20260827/`.
The matching active-row profile capture is
`calendar_2015_southall_age_profile_20260827/screens/028_profile_open_01.png`.

It reveals an important PM99 rule: while the calendar says August 2015, the
profile shows **Age 57**, not a real-world age of 56.  PM99 computes this
field as `current calendar year - birth year`; it does not account for whether
the birthday has occurred.  So a 1958 player is accepted by new-game
initialisation, but their visible age is year-only.  This is inherent PM99
behaviour exposed by moving the clock, not a failed calendar patch.

There is not yet an honest PM99 profile screenshot titled "Neville Southall,
57".  Moving the genuine, unattached record into Stoke exposes a separate
roster-activation constraint, while an otherwise parser-safe player-name
rewrite hits PM99's pre-season error route.  The age-only carrier proves the
clock behaviour; a renamed profile would obscure that runtime name-write bug
and must not be presented as the original Southall record.

## Using the profile

```bash
python3 tools/pm99_calendar_patcher.py \
  /path/to/original/MANAGPRE.EXE \
  --year 2015 \
  --output /path/to/2015/MANAGPRE.EXE \
  --receipt /path/to/2015/calendar-receipt.json
```

The receipt records the input and output SHA-256 values, all changed virtual
addresses and the source operand counts.  For the 2015 proof it produces
output SHA-256
`de50fcb9b0572e720ac0167d2d66d26bc8c82f974ec97759341691fc10cd145e`.

## Guardrails

- Accept only years 2000 through 2026.
- Refuse a different source SHA-256.
- Refuse a profile with unexpected recognised 1998/1999 operand counts.
- Refuse in-place operation or overwriting an existing output file.
- Verify the written file by reading it back and record the result.

## Still needed before calling this a general release

The fresh-game 2015 proof is real, but the next hardening milestone remains:

1. start and play through the first fixture;
2. save and reload;
3. cross January 2016; and
4. trace the later `2000+` calendar operands before claiming a multi-season
   historical career is supported.

The Southall UI screenshot should be repeated after the roster carrier and
player-name runtime rules are solved, using his genuine record rather than a
renamed active player.  This is a roster/name-write research item, not a
reason to weaken the Calendar Patcher's EXE contract.
