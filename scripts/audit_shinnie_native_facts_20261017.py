"""Bound all-year Graeme Shinnie readback, without authorising any writes.

The ownership review is not a nationality or role approval. Reparse the exact
dated annual rows before reporting a secondary-fact or broad-role conflict.
"""
from datetime import UTC, datetime

from app.fdi_indexed import IndexedFDIFile
from scripts import season_pipeline_v2 as pipeline, season_release_registry_v1 as registry
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_package_compiler_v2 as compiler
from scripts.season_duplicate_ownership_plan_v1 import package_layers
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT = registry.ROOT / '.local/consolidated-audit-20261009/shinnie-native-facts-20261017-v1'


def binding(path):
    return dict(path=registry.relative_workspace_path(path), sha256=registry.sha256_file(path))


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    output = ROOT / 'all26-source-native-readback.json'
    if output.exists():
        raise ValueError('completed readback exists; inspect rather than repeat')
    rows = []
    for season in registry.supported_seasons():
        release = registry.load_preferred_release(season)
        people = [p for _, package, _ in package_layers(release) for p in package['players']
                  if roster.normalise(p.get('source_name') or p['name']) == 'graemeshinnie']
        if not people:
            continue
        raw = (release.game_path / 'DBDAT/JUG98030.FDI').read_bytes()
        entries = {e.record_id: e for e in IndexedFDIFile.from_bytes(raw).entries}
        codes = compiler._extract_country_codes_from_textos(release.game_path / 'DBDAT/TEXTOS.PKF')
        sources, _ = roster.load_sources(season)
        verifier = roster.SourceVerifier(season)
        for player in people:
            carrier = player['carrier_id']
            payload = entries[carrier].decode_payload(raw)
            native = roster.native_player(payload, carrier)
            candidates = []
            for source in sources:
                matches = [p for p in source['players']
                           if roster.normalise(p['name']) == 'graemeshinnie'
                           and p.get('birth_date') == player['facts'].get('birth_date')]
                if not matches:
                    continue
                proof = verifier.verify(source)
                if proof['status'] != 'raw-source-reparsed':
                    continue
                for fact in matches:
                    candidates.append(dict(club=source['club_name'], facts=fact, original_source=proof))
            nations = {c['facts']['nationality'] for c in candidates if c['facts'].get('nationality')}
            positions = {c['facts']['position'] for c in candidates if c['facts'].get('position')}
            observed_country = payload[native['name_end'] + 8] ^ 0x61
            expected_country = (compiler._country_code(next(iter(nations)), dict(codes))
                                if len(nations) == 1 else None)
            rows.append(dict(season=season, release_id=release.release_id,
                manifest_sha256=release.manifest_sha256, carrier_id=carrier,
                package=binding(release.package_path), native_file=binding(release.game_path / 'DBDAT/JUG98030.FDI'),
                recipe_facts=player['facts'], native=native,
                native_nationality_code=observed_country,
                source_nationality_values=sorted(nations), source_primary_positions=sorted(positions),
                confirmed_nationality_conflict=(expected_country is not None and observed_country != expected_country),
                primary_position_review=(len(positions) == 1 and native['position'] not in positions),
                source_rows=candidates, ownership_verified_by_this_audit=False))
        print(dict(season=season, matching_actors=len(people)), flush=True)
    retained(output, dict(utc=datetime.now(UTC).isoformat(), machine='joe-Vostro-3350',
        source_session='01a0592d-fcd5-7262-a637-743a8253d9b4', rows=rows,
        native_writes=0, confirmed_nationality_conflicts=sum(r['confirmed_nationality_conflict'] for r in rows),
        primary_position_reviews=sum(r['primary_position_review'] for r in rows),
        cross_club_cases_closed=0, not_global_player_fact_approval=True))


if __name__ == '__main__':
    main()
