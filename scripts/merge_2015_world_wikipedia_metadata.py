#!/usr/bin/env python3
"""Merge exact MediaWiki season metadata into an all-carrier source candidate."""
from __future__ import annotations
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in __import__('sys').path:__import__('sys').path.insert(0,str(ROOT))
from scripts.capture_2015_world_wikipedia_season_metadata import canonical_json_bytes,SCHEMA as WIKI_SCHEMA

IDENTITY_SCHEMA = "pm99-world-2015-transfermarkt-footballsquads-identity-reconciliation-v1"
FIXTURE_SCHEMA = "pm99-world-2015-transfermarkt-opening-fixtures-v1"

class MergeError(ValueError):pass
def _reconciled_fixtures(identity: dict[str, Any] | None, fixtures: dict[str, Any] | None) -> tuple[dict[int, dict[str, Any]], list[int]]:
    if identity is None and fixtures is None: return {}, []
    if not isinstance(identity, dict) or identity.get("schema_version") != IDENTITY_SCHEMA: raise MergeError("identity reconciliation schema unsupported")
    if not isinstance(fixtures, dict) or fixtures.get("schema_version") != FIXTURE_SCHEMA: raise MergeError("opening fixtures schema unsupported")
    by_source_id = {int(row["source_club"]["id"]): row for row in fixtures.get("clubs", []) if isinstance(row, dict) and isinstance(row.get("source_club"), dict) and isinstance(row["source_club"].get("id"), int)}
    by_carrier: dict[int, list[dict[str, Any]]] = {}
    for mapping in identity.get("mappings", []):
        if not isinstance(mapping, dict): continue
        for cid in mapping.get("selected_source_draft_carrier_ids") or []:
            if isinstance(cid, int): by_carrier.setdefault(cid, []).append(mapping)
    conflicts = sorted(cid for cid, mappings in by_carrier.items() if len(mappings) != 1)
    result = {}
    for cid, mappings in by_carrier.items():
        if len(mappings) != 1: continue
        mapping = mappings[0]; source_id = mapping.get("transfermarkt_source_club", {}).get("id")
        fixture = by_source_id.get(source_id) if isinstance(source_id, int) else None
        if fixture is not None: result[cid] = {"mapping": mapping, "fixture": fixture}
    return result, conflicts


def merge(candidate:dict[str,Any],wiki:dict[str,Any], *, identity: dict[str, Any] | None = None, fixtures: dict[str, Any] | None = None)->dict[str,Any]:
    if candidate.get('schema_version')!='pm99-world-2015-editorial-fallback-ratings-v1': raise MergeError('candidate schema unsupported')
    if wiki.get('schema_version')!=WIKI_SCHEMA: raise MergeError('Wikipedia receipt schema unsupported')
    rows={int(r['carrier_id']):r for r in wiki.get('rows',[]) if isinstance(r,dict) and r.get('status')=='exact-season-infobox-match'}
    reconciled, selector_conflicts = _reconciled_fixtures(identity, fixtures)
    output=json.loads(json.dumps(candidate)); transfermarkt_applied=[]
    for carrier in output['carrier_drafts']:
        cid = int(carrier['carrier_id'])
        tm = reconciled.get(cid)
        if tm and carrier.get('opening_fixture', {}).get('status') == 'metadata-unavailable':
            mapping, fixture_club = tm['mapping'], tm['fixture']; fact = fixture_club.get('opening_fixture') or {}
            carrier['transfermarkt_reconciled_identity'] = {
                'identity_method': mapping.get('identity_method'), 'country_catalog': mapping.get('country_catalog'),
                'transfermarkt_source_club': mapping.get('transfermarkt_source_club'),
                'footballsquads_source_selector': mapping.get('footballsquads_source_selector'),
                'opening_fixture_source': mapping.get('opening_fixture_source'),
                'compiler_disposition': 'reviewed-source-identity-receipt-only; dated-fact-attachment; no-pm99-assignment-or-write',
            }
            carrier['manager'] = {'name': fact.get('declared_manager'), 'metadata_status': 'transfermarkt-reconciled-country-scoped-source-fact'}
            carrier['opening_fixture'] = {'status': fact.get('source_status'), 'date': fact.get('date'), 'formation': fact.get('declared_formation'), 'stadium': fact.get('reported_match_stadium')}
            if not carrier['club'].get('fixture_ground_evidence'): carrier['club']['fixture_ground_evidence'] = fixture_club.get('first_home_fixture_ground_evidence')
            blockers=set(carrier['blockers']); blockers.discard('2015-manager-source-required')
            if fact.get('source_status') != 'source-qualified': blockers.add('opening-fixture-source-incomplete')
            carrier['blockers']=sorted(blockers); transfermarkt_applied.append(cid)
        source=rows.get(cid)
        if not source: continue
        facts=source['facts']; page=source['page']
        if not facts.get('manager') and not facts.get('stadium'): continue
        carrier['wikipedia_season_metadata']={'status':'exact-season-infobox-match','facts':facts,'page':{key:page[key] for key in ('title','pageid','revid','timestamp','content_sha256')}}
        # Transfermarkt opening-fixture facts are the stronger dated fixture
        # source. Wikipedia fills only carrier metadata still unavailable.
        if carrier.get('manager', {}).get('metadata_status') == 'unavailable-no-dated-manager-source':
            if facts.get('manager'): carrier['manager']={'name':facts['manager'],'metadata_status':'wikipedia-exact-2015-16-season-infobox'}
            blockers=set(carrier['blockers']); blockers.discard('2015-manager-source-required'); carrier['blockers']=sorted(blockers)
        if facts.get('stadium'):
            carrier['club']['wikipedia_stadium_evidence']={'stadium':facts['stadium'],'interpretation':'exact season-page infobox fact; not a permanent ground/capacity claim'}
    counts=Counter(b for c in output['carrier_drafts'] for b in c['blockers']);output['sources']['wikipedia_season_metadata_sha256']=hashlib.sha256(canonical_json_bytes(wiki)).hexdigest()
    if identity is not None:
      output['sources']['transfermarkt_footballsquads_identity_reconciliation_sha256']=hashlib.sha256(canonical_json_bytes(identity)).hexdigest(); output['sources']['transfermarkt_opening_fixtures_sha256']=hashlib.sha256(canonical_json_bytes(fixtures)).hexdigest()
    output['coverage']['transfermarkt_reconciled_metadata_carrier_count']=len(transfermarkt_applied)
    output['coverage']['transfermarkt_reconciled_selector_conflict_carrier_ids']=selector_conflicts
    output['coverage']['wikipedia_exact_metadata_carrier_count']=sum('wikipedia_season_metadata' in c for c in output['carrier_drafts'])
    output['coverage']['blocker_counts']=dict(sorted(counts.items()));return output
def main()->int:
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',required=True,type=Path);p.add_argument('--wikipedia-receipt',required=True,type=Path);p.add_argument('--identity-reconciliation',type=Path);p.add_argument('--transfermarkt-fixtures',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();c=json.loads(a.candidate.read_text());w=json.loads(a.wikipedia_receipt.read_text())
 if bool(a.identity_reconciliation) != bool(a.transfermarkt_fixtures): p.error('--identity-reconciliation and --transfermarkt-fixtures must be supplied together')
 identity=json.loads(a.identity_reconciliation.read_text()) if a.identity_reconciliation else None; fixtures=json.loads(a.transfermarkt_fixtures.read_text()) if a.transfermarkt_fixtures else None
 try:o=merge(c,w,identity=identity,fixtures=fixtures)
 except MergeError as e:p.error(str(e))
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_bytes(canonical_json_bytes(o));print(json.dumps({'applied':o['coverage']['wikipedia_exact_metadata_carrier_count'],'blockers':o['coverage']['blocker_counts']},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
