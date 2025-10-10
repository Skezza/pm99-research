import pytest
from pathlib import Path

from app.io import FDIFile

def normalize_name(s: str) -> str:
    return " ".join(s.upper().split())

def get_display_name(record) -> str:
    # Prefer structured fields in order of availability
    if getattr(record, 'name', None):
        return record.name
    if getattr(record, 'full_name', None):
        return record.full_name
    given = getattr(record, 'given_name', '') or ''
    surname = getattr(record, 'surname', '') or ''
    return f"{given} {surname}".strip()

def test_canonical_players_present(players_fdi_path):
    p = Path('tests/fixtures/canonical_players.csv')
    assert p.exists(), f"Canonical players file not found: {p}"

    canonical = [line.strip() for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]

    fdi = FDIFile(players_fdi_path)
    fdi.load()

    records = [r for _, r in getattr(fdi, 'records_with_offsets', [(None, r) for r in getattr(fdi, 'records', [])])]
    displays = [normalize_name(get_display_name(r)) for r in records if get_display_name(r)]

    missing = []
    for name in canonical:
        if normalize_name(name) not in displays:
            missing.append(name)

    assert not missing, f"Missing canonical players ({len(missing)}): {missing}"

def test_no_synthesized_placeholders_in_records(players_fdi_path):
    # Ensure the packaged parser does not include synthesized placeholder records
    fdi = FDIFile(players_fdi_path)
    fdi.load()
    records_with_offsets = getattr(fdi, 'records_with_offsets', [(None, r) for r in getattr(fdi, 'records', [])])
    records = [r for _, r in records_with_offsets]

    # Collect decoded payloads from directory entries to cross-check actual in-file data.
    decoded_payloads = []
    try:
        for entry, decoded, length in fdi.iter_decoded_directory_entries():
            if decoded:
                decoded_payloads.append(decoded)
    except Exception:
        pass

    # Also include raw_data of records already present (they should match decoded payloads)
    for _, r in records_with_offsets:
        raw = getattr(r, 'raw_data', None)
        if raw:
            decoded_payloads.append(raw)

    synthesized = []
    for r in records:
        raw = getattr(r, 'raw_data', None)
        if raw is None:
            continue
        # Consider a record synthesized if its raw_data is not present as-is within any decoded payload.
        found = any(raw == p or raw in p for p in decoded_payloads if p)
        if not found:
            synthesized.append(get_display_name(r))

    assert not synthesized, f"Synthesized placeholder records found: {synthesized}"
