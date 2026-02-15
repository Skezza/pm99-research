# Suggested Follow-up Improvements

## 1. Ship or fetch safe fixtures for integration tests
Although the suite now skips integration cases when `DBDAT/*.FDI` assets are missing, that leaves important workflows untested. Bundle sanitized samples or provide a documented download script so CI can execute the end-to-end checks. An opt-in flag to fail when data is absent would also help.

## 2. Clarify CLI rename limitations
`app/cli.py` performs in-place renames by assigning `record.name = args.name` and writing via `FDIFile.save()`. Document padding requirements or add length validation before writes to avoid silent truncation/corruption when new names exceed original byte windows.

## 3. Automate documentation drift checks
The restored architecture, data format, and editor guides quickly fall out of sync when code changes. Add a lightweight checklist (for example in pull request templates) or automated lint that prompts contributors to update the canonical docs whenever relevant modules change.

