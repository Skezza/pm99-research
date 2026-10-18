"""Find country-byte disagreements against exact, reparsed period identities.

Read-only. No club-country defaults, current citizenship or approximate name
joins. Only complete multi-token published names plus literal matching DOBs;
all available period rows must agree on the nationality. Unsupported countries
are logged separately and never silently converted into a supported nation.
"""
import argparse
from collections import Counter,defaultdict
from datetime import date
from pathlib import Path
from app.fdi_indexed import IndexedFDIFile
from scripts import season_release_registry_v1 as registry,season_pipeline_v2 as pipeline
from scripts import season_historical_roster_audit_v1 as roster
from scripts import season_package_compiler_v2 as compiler
from scripts import season_duplicate_ownership_plan_v1 as layers
from scripts.build_savio_bobb_alias_reserve_20261011 import retained

ROOT=registry.ROOT/'.local/consolidated-audit-20261009/period-nationality-audit-20261016-v1'


def source_index(season):
    captures,_=roster.load_sources(season);verifier=roster.SourceVerifier(season)
    result=defaultdict(list);status=Counter()
    for capture in captures:
        proof=verifier.verify(capture);status[proof['status']]+=1
        if proof['status']!='raw-source-reparsed':continue
        for person in capture['players']:
            name=person['name'];born=person.get('birth_date');code=person.get('nationality')
            if not isinstance(born,str) or not isinstance(code,str) or not code:continue
            result[(roster.normalise(name),born)].append(dict(source_name=name,birth_date=born,
                nationality=code,source_club=capture['club_name'],source=proof))
    return result,dict(status)


def unanimous(rows):
    codes={r['nationality'] for r in rows}
    return next(iter(codes)) if len(codes)==1 else None


def audit(season):
    path=ROOT/(season+'.json')
    base=registry.load_preferred_release(season)
    if path.exists():
        saved=pipeline.read_json_file(path)
        if saved['release_id']!=base.release_id or saved['manifest_sha256']!=base.manifest_sha256:
            raise ValueError('completed nationality audit baseline changed; use a new version')
        print(dict(season=season,reused_completed_exact_audit=True,**saved['counts']),flush=True);return saved
    sources,status=source_index(season)
    data=(base.game_path/'DBDAT/JUG98030.FDI').read_bytes()
    index={e.record_id:e for e in IndexedFDIFile.from_bytes(data).entries}
    countries=compiler._extract_country_codes_from_textos(base.game_path/'DBDAT/TEXTOS.PKF')
    counts=Counter();candidates=[];unsupported=[];errors=[]
    for label,package,_ in layers.package_layers(base):
        for player in package['players']:
            if player.get('policy')=='preserve-existing-mode1':
                counts['whole_record_fallback_excluded']+=1;continue
            name=player.get('source_name') or player['name'];born=player['facts'].get('birth_date')
            words=name.split()
            if len(words)<2 or any(len(roster.normalise(w))<2 for w in words) or not isinstance(born,str):
                counts['incomplete_name_or_DOB_excluded']+=1;continue
            rows=sources.get((roster.normalise(name),born),[]);wanted=unanimous(rows)
            if wanted is None:
                counts['conflicting_period_nationalities' if rows else 'no_exact_period_nationality']+=1;continue
            try:
                raw=index[player['carrier_id']].decode_payload(data)
                person=roster.native_player(raw,player['carrier_id']);end=person['name_end']
                native_born=date(int.from_bytes(bytes(v^0x61 for v in raw[end+14:end+16]),'little'),
                    raw[end+13]^0x61,raw[end+12]^0x61).isoformat()
                if native_born!=born or roster.normalise(person['name'])!=roster.normalise(player['name']):
                    counts['native_identity_mismatch_rejected']+=1;continue
                code=compiler._country_code(wanted,dict(countries));before=raw[end+8]^0x61
            except (ValueError,KeyError) as exc:
                errors.append(dict(layer=label,carrier_id=player['carrier_id'],name=player['name'],error=str(exc)));continue
            row=dict(layer=label,player_id=player['id'],carrier_id=player['carrier_id'],name=player['name'],
                source_name=name,birth_date=born,recipe_nationality_before=player['facts'].get('nationality'),
                native_country_before=before,source_nationality=wanted,native_country_expected=code,
                original_period_rows=rows)
            if code==countries['XXX']:
                unsupported.append(row);counts['source_country_not_supported_by_native_table']+=1;continue
            if before!=code:
                candidates.append(row);counts['positive_source_native_disagreement']+=1
                counts['native_disagreement_'+label]+=1
            elif player['facts'].get('nationality')!=wanted:
                candidates.append(row);counts['declaration_only_disagreement']+=1
                counts['declaration_only_'+label]+=1
            else:counts['exact_period_native_and_recipe_match']+=1
    result=dict(schema='pm99-exact-period-name-DOB-country-readback-audit-v1',season=season,
        release_id=base.release_id,manifest_sha256=base.manifest_sha256,
        package_sha256=registry.sha256_file(base.package_path),JUG_sha256=registry.sha256_file(base.game_path/'DBDAT/JUG98030.FDI'),
        implementation=dict(path=registry.relative_workspace_path(Path(__file__)),sha256=registry.sha256_file(Path(__file__))),
        source_status=status,counts=dict(counts),candidates=candidates,unsupported_countries=unsupported,
        native_read_errors=errors,native_writes=0,recipes_modified=0,
        scope='Exact period nationality only; NOT roster ownership, historical positions or full identity certification. Missing/unsupported/ambiguous cases remain explicit.')
    ROOT.mkdir(parents=True,exist_ok=True);retained(path,result)
    print(dict(season=season,**result['counts'],native_read_errors=len(errors),native_writes=0),flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('seasons',nargs='*',default=['2021-22'])
    args=parser.parse_args()
    for season in registry.supported_seasons() if args.seasons==['all'] else args.seasons:audit(season)
