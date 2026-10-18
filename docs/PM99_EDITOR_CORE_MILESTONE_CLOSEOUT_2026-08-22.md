# PM99 Core Database-Editor Research Closeout

**Closed:** 2026-08-22
**Fixture:** unmodified Stoke City / First Division data, copied for every run
**Runtime authority:** `upstream/pm99-runner` on the PM99 runner server

## What This Closes

This is the research closeout for the ordinary database-editor feature set:

- player name, date of birth, nationality, physical data, skills and primary
  position;
- player portrait bitmap replacement;
- club short name, stadium name, full club name, seated capacity and starting
  finance; and
- a clear decision on secondary positions, league names and club membership.

It does **not** claim that every byte in PM99 is semantically understood or
editable. Unknown player bytes, competition metadata, roster tails, bitmap
references and cross-family relationships remain preserve-only unless a
separate contract says otherwise.

## Evidence Standard

An `in-game proof` means all of the following happened on a disposable copy:

1. The writer changed only its defined target data.
2. The editor reopened and read the changed database.
3. PM99 started through the runner without a crash or Wine debugger.
4. A game screen showed the changed value when a relevant screen exists.

`Read/write mapped` is deliberately weaker: it means we can parse and write a
bounded field, but do not have enough game evidence to expose it to ordinary
users.

## Final Core-Feature Matrix

| User feature | Result | Evidence / limit |
| --- | --- | --- |
| Player variable-length name | **in-game proof** | Equal-length and shorter indexed names both reached the profile UI. The name-only path is byte-preserving; it no longer serialises the opaque player record. |
| DOB, nationality, height, weight, primary position, visible skills | **in-game proof** | The existing Richard Forsyth run changes and displays each of these in the profile UI. |
| Player bitmap / portrait | **in-game proof** | Graham Kavanagh's MINIFOTO pixel data was inverted while its headers, palette, archive length and offsets were retained. His altered image is visible in the profile UI. |
| Club short name | **in-game proof** | `Stoke C.` → `Skezton C.` is visible in Ground. |
| Stadium name | **in-game proof** | `Britannia Stadium` → `Skezza Ground` is visible in Ground. |
| Full club name | **read/write mapped** | The structured prefix writer changes and reopens it in the same release run. This PM99 route has no useful full-name display, so it is not presented as a visual proof. |
| Seated capacity | **in-game proof** | A direct, bounded four-byte indexed-EQ lane changed 24,054 → 40,001. Ground displays `40,001 seats`. |
| Starting finance | **in-game proof, mode-0 teams** | Both traced finance inputs are updated together in £5,000 units. Stoke's Finance UI displays £12,000,000 in the final fresh proof. |
| Standing capacity | **preserve-only** | The record exposes a value, but Stoke's direct 9,650 does not equal Ground's displayed 8,000. Its game relationship is not complete. |
| Car park and pitch | **derived/display-only** | Ground values are built by game facility/default logic, not proven independent EQ fields. They are not safe editor controls. |
| Chairman, sponsor, kit supplier | **read-only / investigation** | Conservative extractors exist only for parts of the corpus. The old printable-span writers and their claimed UI proof are not sufficient contracts. |
| Secondary positions | **read-only / investigation** | Six intrinsic role bytes and their player loader are mapped. The profile `ROL.` label is a tactical assignment, not the intrinsic secondary-role list. |
| League name | **not a database field** | English labels, including `PREMIER LEAGUE` and `FIRST DIVISION`, are executable strings in `MANAGPRE.EXE`. Rename belongs to the patcher workstream. |
| Club membership in a league | **preserve-only** | There is no dedicated field or safe write contract. The available bytes are country/competition-family candidates, not a proven placement record. |

## Runner Artifacts

All of these runs use an isolated database overlay and preserve their request,
write result, runner summary and screenshots.

| Feature | Runner tag | Visible evidence |
| --- | --- | --- |
| Player name, equal length | `stoke_player_name_byte_preserving_proof_20260822` | `screens/041_profile_open_06.png` (`SKEZZA FORSYTH`) |
| Player name, shorter | `stoke_player_name_shorter_proof_20260822` | `screens/041_profile_open_06.png` (`R. Forsyth`) |
| Portrait | `stoke_kavanagh_portrait_invert_proof_20260822` | `screens/053_profile_open_10.png` |
| Capacity | `stoke_capacity_release_proof_20260822` | `screens/023_ground_inspect_retry.png` |
| Finance | `stoke_finance_release_proof_20260822` | `screens/021_finance_inspect.png` |
| Finance, £12m repeat | `stoke_finance_12m_ui_proof_20260822` | `screens/021_finance_inspect.png` (`CASH £12,000,000`) |
| Club/stadium/full-name structured write | `stoke_club_strings_release_proof_20260822` | `screens/023_ground_inspect_retry.png` (`Skezton C.`, `Skezza Ground`) |

The last run was release-mode: `investigation_mode=false`, `release_mode=true`,
all three requested strings were applied, the writer emitted no warnings and
the game returned from Ground without a crash or debugger.

## Important Technical Findings

### Player names

The earlier indexed name-only route was unsafe because it serialised a parsed
record, normalising unknown player bytes. That could leave PM99 stuck on entry
to Squad Management. Name-only indexed edits now use the existing in-place,
byte-preserving name patch. The proof covers equal and shorter names. A longer
name must still meet the recorded payload/window rules; it is not silently
promised for every player family.

### Club strings

The real indexed EQ form has a structured `dd6361` prefix containing the short
name, stadium and full club name. The writer recalculates only its dependent
length words, retains its control/bridge bytes and the entire opaque tail, and
rebuilds the FDI directory when a record grows or shrinks. A structural test
also verifies that later entries are rebased and unchanged.

### Finance and capacity

Seated capacity is a direct signed 32-bit lane. Finance is not a single cash
number: in a mode-0 entry PM99 uses the larger of two raw 32-bit inputs and
multiplies it by £5,000. The safe operation writes both inputs together and
only accepts multiples of £5,000. Other team modes need their own contract.

### Leagues

Ghidra cross-references show `FIRST DIVISION` at `0x0072daec` and `PREMIER
LEAGUE` at `0x0072db0c` in `MANAGPRE.EXE`; each is referenced from multiple UI
sites. `DBASEPRE.EXE` does load the indexed team records, but its loader does
not reveal a dedicated league-placement record. The project’s current league
labels are selector/index fallbacks, not a database-edit contract.

Changing a club’s membership may require coordinated changes to entry ordering,
competition metadata, fixtures and other references. No speculative byte write
was made during this closeout.

## Deliberate Boundaries

This result corrects older broad claims in the product documents and registry:
they historically listed car park, pitch, chairman, sponsor, supplier, ground
size and generic team text spans as release-editable. The current evidence does
not justify that. The authoritative research classification is now the table
above; the next implementation milestone must bring the release contract and
UI into line with it before publishing an editor.

The ordinary editor can be designed around the proven fields. It should hide or
clearly label the investigation-only fields rather than offering a form which
pretends they are complete.

## Verification Performed in This Closeout

- Structural tests for direct capacity and finance lanes were run by importing
  their test functions in the available Python environment.
- The club-string unit test was run with its minimal test double and passed.
- Modified editor and runner Python compiled successfully; runner shell syntax
  validation passed.
- `python3 scripts/check_repo_boundary.py` passed.

The workstation system Python does not include `pytest`, so a full upstream
pytest invocation is still a release-engineering task, not a claim made here.

## Research Result

The research phase is complete for the editor scope above. It is complete
because each requested feature is either (a) proven in game, (b) bounded and
explicitly limited, or (c) rejected as unsuitable for the database editor.

It is not complete for a hypothetical 100% PM99 editor. The remaining unknown
data is intentionally outside this milestone.

## Product Contract Reconciliation: Complete

The product contract now exposes only the proven team surface: short name,
stadium name, full club name, seated capacity and mode-0 starting finance.
The registry marks team ID, car park, pitch, chairman, sponsor, supplier and
ground size as release preserve-only. The standard `team-edit` CLI no longer
offers setters for those fields, and the existing contract-driven GUI disables
their controls.

`upstream/pm99-skezmod-db-editor/app/data/editor_field_matrix.json` is the
machine-readable browser-facing contract. The normal suite was run in the
runner's temporary Python environment, which has `tkinter`: `465 passed, 47
skipped`.

## Next Milestone: Browser Editor Design and Implementation

Build the browser application around the machine-readable field matrix:

1. Local file input and in-browser parsing; no database upload is required.
2. Read-only field presentation for preserve-only and research-only surfaces.
3. Edit forms for the proven player and team fields, with variable-length and
   mode-specific validation shown before writing.
4. Download a patched database only after a clear change summary and a
   reopen-validation pass.
