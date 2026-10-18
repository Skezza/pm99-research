"""Pure compact-player transfer primitive; not historical publication authority.

Copy the original person's proven native semantic fields onto another fixed
carrier, retaining that person's existing native display and all ten skills.
Unknown controls, native owner links and unproven shirt storage stay with the
destination. The caller must separately authorise dated ownership, consume all
source copies, clear stale portraits and reconcile complete owned startup order.
"""
from scripts import season_package_compiler_v2 as compiler
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_same_carrier_name_capacity_v1 as capacity
from scripts.prepare_duplicate_whole_club_native_v1 import preserve_other_records
from app.fdi_indexed import IndexedFDIFile


def read(payload, carrier):
    if payload[2:5] != b'\xdd\x63\x60':
        raise ValueError('retained transfer requires compact dd6360 carriers')
    native = roster.native_player(payload, carrier)
    fields = compiler._read_native_dd6360_fields(payload, native['name_end'])
    if any(v not in {*range(18), 98} for v in fields['fine_role_codes']):
        raise ValueError('retained fine roles outside proven native domain')
    if fields['parser_position_code'] != fields['visible_position_code']:
        raise ValueError('source broad-position fields disagree')
    return native, fields


def semantic(fields):
    return {key: value for key, value in fields.items() if key != 'unknown_9'}


def compile_moves(original, moves, *, capacity_bundle=None):
    if not moves or len({m['destination_carrier'] for m in moves}) != len(moves):
        raise ValueError('explicit unique destination carriers required')
    if len({m['source_carrier'] for m in moves}) != len(moves):
        raise ValueError('one source person cannot populate multiple destinations')
    entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(original).entries}
    prepared = original
    claims = {}
    for move in moves:
        if move.get('recover_destination_capacity'):
            if capacity_bundle is None:
                raise ValueError('capacity recovery requires existing verified runtime bundle')
            prepared, claim = capacity.recover_slot(prepared, move['destination_carrier'], capacity_bundle)
            claims[move['destination_carrier']] = claim
    targets = {e.record_id: e for e in IndexedFDIFile.from_bytes(prepared).entries}
    replacements = {}
    observations = []
    for move in moves:
        src, dest = move['source_carrier'], move['destination_carrier']
        if src == dest:
            raise ValueError('retained transfer must move to another carrier')
        source = entries[src].decode_payload(original)
        target = targets[dest].decode_payload(prepared)
        person, fields = read(source, src)
        before, _ = read(target, dest)
        original_destination, _ = read(entries[dest].decode_payload(original), dest)
        if (person['name'] != move['expected_source_display']
                or original_destination['name'] != move['expected_destination_display']):
            raise ValueError('retained transfer exact native name preimage differs')
        named, proof = compiler._patch_indexed_player_variable_name_payload(
            target, before['name'], person['name'])
        if proof.get('native_suffix_preserved_exactly') is not True:
            raise ValueError('name relocation did not prove exact native suffix preservation')
        end = proof['new_role_start']
        skills = dict(zip(compiler.SKILLS, fields['skills']))
        skills['handling'] = fields['handling']
        changed = bytearray(compiler._patch_dd6360_mode1_safe_fields(named,
            position=fields['visible_position_code'], nationality=fields['visible_nationality_code'],
            birth_day=fields['birth_day'], birth_month=fields['birth_month'], birth_year=fields['birth_year'],
            height=fields['height_cm'], weight=fields['weight_kg'], skills=skills,
            native_role_start=end, fine_roles=None))
        # Preserve all six source candidates, including native unassigned gaps;
        # do not compress or reinterpret their preference/storage ordering.
        changed[end + 2:end + 8] = source[person['name_end'] + 2:person['name_end'] + 8]
        allowed = set(range(end + 2, end + 9)) | set(range(end + 10, end + 28))
        if len(changed) != len(target) or any(a != b and i not in allowed for i, (a, b) in enumerate(zip(named, changed))):
            raise ValueError('retained transfer changed an unproven native field')
        actual, observed = read(bytes(changed), dest)
        if actual['name'] != person['name'] or semantic(observed) != semantic(fields):
            raise ValueError('retained native identity facts/roles/ten skills did not travel exactly')
        replacements[dest] = bytes(changed)
        observations.append(dict(source_carrier=src, destination_carrier=dest,
            native_display=actual['name'], original_semantics=semantic(fields),
            transferred_semantics=semantic(observed), all_ten_skills_exact=True,
            fine_role_slots_exact=True, unknown_destination_control_preserved=True,
            capacity_claim=claims.get(dest)))
    candidate = compiler._rebuild_indexed(prepared, IndexedFDIFile.from_bytes(prepared), replacements)
    preserve_other_records(original, candidate, set(replacements))
    return candidate, observations
