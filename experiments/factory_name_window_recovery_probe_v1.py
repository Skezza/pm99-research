"""In-memory compact-name capacity experiment; never writes a game.

This establishes a reversible candidate within that SAME carrier's factory
window. It is not yet permission to publish: source names, writer-chain evidence
and a real runtime pilot are still required before any compiler integration.
"""
from scripts import season_package_compiler_v2 as compiler
from app.editor_actions import (_patch_indexed_dd6360_variable_name,
                                _indexed_variable_name_runtime_segments)


def _stored_case_display(payload: bytes) -> str:
    segments = _indexed_variable_name_runtime_segments(payload)
    surname = payload[segments['surname_start']:segments['surname_end']].decode('cp1252')
    full = payload[segments['full_name_start']:segments['full_name_end']].decode('cp1252')
    if not surname or not full.endswith(surname.upper()):
        raise ValueError('native name fields cannot reproduce the exact writer input casing')
    return (full[:-len(surname)] + surname).strip()


def recover_candidate(factory: bytes, current: bytes) -> tuple[bytes, dict]:
    if (factory[2:5] != b'\xdd\x63\x60' or current[2:5] != b'\xdd\x63\x60'
            or len(factory) != len(current) or factory[:8] != current[:8]):
        raise ValueError('capacity experiment requires the same compact carrier, prefix and fixed length')
    original_end = compiler._native_dd6360_role_start(factory)
    current_end = compiler._native_dd6360_role_start(current)
    gain = original_end - current_end
    if gain <= 0:
        raise ValueError('factory carrier offers no lost name capacity')
    if current[-gain:] != b'\x61' * gain:
        raise ValueError('candidate recovery would remove nonzero/unknown encoded suffix bytes')
    recovered = current[:8] + factory[8:original_end] + current[current_end:-gain]
    if len(recovered) != len(current):
        raise ValueError('candidate recovery changed the fixed native record length')
    # Display readers uppercase surnames; use both actual stored strings when
    # proving a byte-exact roundtrip, not that lossy display representation.
    old_name = _stored_case_display(factory)
    current_name = _stored_case_display(current)
    roundtrip, _ = _patch_indexed_dd6360_variable_name(recovered, old_name, current_name)
    if roundtrip != current:
        raise ValueError('candidate recovery does not exactly reverse the established shrinking writer')
    if (compiler._read_native_dd6360_fields(current, current_end)
            != compiler._read_native_dd6360_fields(recovered, original_end)):
        raise ValueError('candidate recovery altered native semantic field readback')
    return recovered, {'recovered_name_bytes': gain, 'original_suffix_cursor': original_end,
                       'current_suffix_cursor': current_end, 'fixed_length': len(current),
                       'exact_shrink_roundtrip': True, 'semantic_readback_unchanged': True,
                       'runtime_verified': False, 'publication_authorised': False}
