# How the PKF/FDI safeguards help day-to-day modding

This note translates the stricter PKF validation, player scanning, and regression
checks into the concrete jobs you run when shipping a PC Fútbol data update.

## 1. Catching broken PKF archives before you ship

**Typical task:** You pull a community roster pack such as `EQPCPLUS.PKF`, tweak a
few teams, and plan to publish it.

1. Validate the table of contents before editing:
   ```bash
   python - <<'PY'
   from pathlib import Path
   from pm99_editor.pkf import PKFFile, PKFTableValidationError

   pkf_path = Path("EQPCPLUS.PKF")
   try:
       PKFFile.from_bytes(pkf_path.name, pkf_path.read_bytes(), strict=True)
   except PKFTableValidationError as exc:
       print("Validation failed:\n" + "\n".join(exc.issues))
   else:
       print("PKF TOC looks good ✔")
   PY
   ```
2. When validation fails, the parser now logs the exact offsets and reasons to
   `diagnostics/pkf_table_validation.log`. Open the latest entry to see which
   team slot needs reverse engineering:
   ```bash
   tail -n 40 diagnostics/pkf_table_validation.log
   ```
3. Because failures throw immediately you avoid exporting DBCs from a corrupted
   archive that would otherwise silently miss teams in game.

## 2. Proving every player made it into your build

**Typical task:** You batch-edit youth attributes in `JUG00022.FDI` and need to be
sure no records vanished.

1. Load the file in strict mode so malformed records raise a
   `PlayerScanError`:
   ```bash
   python - <<'PY'
   from pm99_editor.io import FDIFile
   from pm99_editor.scanner import PlayerScanError

   try:
       FDIFile("JUG00022.FDI").load(strict=True)
   except PlayerScanError as exc:
       print("Player scan failed")
       for issue in exc.issues:
           print(f"- offset 0x{issue.offset:x}: {issue.reason}")
   else:
       print("All player blobs decoded ✔")
   PY
   ```
2. When an issue is raised the scanner dumps a hex preview of the offending
   payload into the exception so you can fix the exact record instead of
   learning about the problem from missing players in the UI.

## 3. Trusting automated checks before distributing builds

**Typical task:** You maintain a fork with custom tooling and want CI to confirm
the guardrails stay intact.

1. The regression tests added for the stricter pipeline already encode the most
   common failure modes:
   ```bash
   pytest tests/test_pkf_parser.py tests/test_scanner.py
   ```
2. Add this command to your GitHub Actions (or local pre-release script) so any
   change that reintroduces silent PKF fallbacks or player-skip heuristics fails
   the build immediately.

By running these exact snippets you keep the deliverable safe: you know when a PKF
archive is malformed, you get explicit offsets for broken player blobs, and your
CI lights up red the moment a regression removes those guarantees.
