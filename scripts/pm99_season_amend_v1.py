#!/usr/bin/env python3
"""Apply the workbook's staged cell edits to a registered season as a new, unpreferred playable candidate.

    ./pm99-season apply-amendments 2022-23 [--parent RELEASE_ID] [--dry-run] [--verify-reconstruction]

Input is the workbook's staged ``working.json`` (or a materialisation receipt plus the working.json it
hashes). Only fields the generic route can carry into the game are applied, as a byte-scoped delta over the
exact parent release; anything else is rejected with a reason. The parent, every other season and the
preferred catalogue are never changed. An edited candidate can itself be the parent of the next edit.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'upstream/pm99-skezmod-db-editor'), str(ROOT / 'upstream/pm99-skezmod-patcher')]
from scripts import season_pipeline_v2 as pipeline  # noqa: E402
from scripts import season_release_registry_v1 as registry  # noqa: E402
from scripts import season_disk_budget_v1 as disk_budget  # noqa: E402
from scripts import season_editorial_amendment_delta_v1 as editorial  # noqa: E402
from scripts import season_amendment_candidates_v1 as candidates  # noqa: E402
from tools import season_manifest_amendments as amendments  # noqa: E402

BUILDS_ROOT = candidates.BUILDS_ROOT
DEFAULT_SEASONS_ROOT = ROOT / 'seasons'


class AmendmentBuildError(ValueError):
    """The edit cannot be built; the message says what to change."""

    def __init__(self, message, *, status='rejected', details=None):
        super().__init__(message)
        self.status, self.details = status, details or {}


def recipe_manifest_id(release):
    """The workbook's manifest id for a registered release's recipe."""
    return f'preferred-release/{release.release_id}/season-package.json'


def default_working_path(season, seasons_root=DEFAULT_SEASONS_ROOT):
    return Path(seasons_root) / season / 'editorial-amendments' / 'working.json'


def load_document(season, *, amendments_path=None, receipt_path=None, seasons_root=DEFAULT_SEASONS_ROOT):
    """Return (document, origin). A receipt is accepted only with the exact document it hashes."""
    path = Path(amendments_path) if amendments_path else default_working_path(season, seasons_root)
    if not path.is_file():
        raise AmendmentBuildError(f'no staged amendments for {season}: {path} does not exist')
    try:
        document = amendments.load_or_empty(path, season=season)
    except amendments.AmendmentError as exc:
        raise AmendmentBuildError(f'amendment document is not usable: {exc}') from exc
    origin = 'workbook-staged-working-json'
    if receipt_path:
        receipt = json.loads(Path(receipt_path).read_text(encoding='utf-8'))
        if receipt.get('schema_version') != amendments.RECEIPT_SCHEMA or receipt.get('season') != season:
            raise AmendmentBuildError('materialisation receipt has the wrong schema or season')
        if receipt.get('amendment_sha256') != amendments.sha256_bytes(amendments.canonical_json_bytes(document)):
            raise AmendmentBuildError('materialisation receipt does not match the staged amendments (they changed after materialising)')
        origin = 'hash-bound-materialisation-receipt'
    return document, origin


def select_changes(document, parent):
    wanted = recipe_manifest_id(parent)
    recipe_sha = registry.sha256_file(parent.package_path)
    applied, ignored = [], []
    for change in document['changes']:
        if change['manifest_id'] != wanted:
            ignored.append(dict(id=change['id'], manifest_id=change['manifest_id'], json_pointer=change['json_pointer'],
                reason='targets a different manifest; only edits to the registered release recipe are built'))
        elif change['manifest_sha256'] != recipe_sha:
            raise AmendmentBuildError(
                f'stale edit {change["id"]}: it was staged against a different recipe revision than {parent.release_id}. '
                'Re-open the year in the workbook (or pick the right --parent) and re-stage it.', status='stale')
        else:
            applied.append(change)
    if not applied:
        raise AmendmentBuildError(f'no staged edits target {parent.release_id}; nothing to build. Staged against other manifests: '
                                  f'{sorted({r["manifest_id"] for r in ignored}) or "none"}. Pick the matching base release in the workbook and re-stage.',
                                  status='nothing-to-build',
                                  details=dict(ignored=ignored))
    return applied, ignored


def default_release_id(season, plan):
    return f'edited-{season}-{plan["transaction_id"][:12]}'


def disk_estimate(parent, plan, minimum_free_bytes):
    """Mirror the publisher's own planned-bytes formula so a blocked build is reported exactly."""
    game = parent.game_path / 'DBDAT'
    planned = (sum((game / n).stat().st_size for n in ('JUG98030.FDI', 'EQ98030.FDI')) + parent.package_path.stat().st_size
               + len(pipeline.canonical_json_bytes(plan)) + 32 * 1024 ** 2
               + ((game / 'ENT98030.FDI').stat().st_size if plan['manager_updates'] else 0))
    free = shutil.disk_usage(parent.game_path).free
    return dict(free_bytes=free, planned_bytes=planned, minimum_free_bytes=minimum_free_bytes,
                shortfall_bytes=max(0, minimum_free_bytes - (free - planned)), enough=free - planned >= minimum_free_bytes)


def summarise(plan):
    rows = []
    for u in plan['updates']:
        rows.append(dict(player=u['name'], carrier_id=u['carrier_id'], club_id=u['club_id'],
            edits=[f'{f["field"]}: {f["before"]} -> {f["after"]}' for f in u['fields']],
            dependent=[f'{d["field"]}: {d["before"]} -> {d["after"]} ({d["reason"]})' for d in u['dependent_changes']],
            native_bytes_changed=len(u['native_bytes'])))
    for m in plan['manager_updates']:
        rows.append(dict(manager=m['before_name'], carrier_id=m['carrier_id'],
            edits=[f'name: {m["before_name"]} -> {m["after_name"]}'],
            dependent=[f'game short name: {m["before_native_names"]["surname"]} -> {m["after_native_names"]["surname"]}']))
    return rows


_write_json = candidates.write_json
_record_candidate = candidates.record_candidate
list_candidates = candidates.list_candidates
play_command = candidates.play_command


def apply_amendments(season, *, document=None, origin='workbook-staged-working-json', amendments_path=None, receipt_path=None,
                     seasons_root=DEFAULT_SEASONS_ROOT, parent_id=None, release_id=None, dry_run=False,
                     verify_reconstruction=False, minimum_free_bytes=None):
    """Plan (and unless ``dry_run`` build) a candidate. Returns a JSON-able report; raises AmendmentBuildError."""
    season = pipeline.normalise_season_id(season)
    if minimum_free_bytes is None:
        # Same guard as every build: at least 6 GiB; the default 8 GiB may be lowered only by explicit choice.
        minimum_free_bytes = int(os.environ.get('PM99_MINIMUM_FREE_BYTES', disk_budget.DEFAULT_RESERVE))
    disk_budget.validate_reserve(minimum_free_bytes)
    if document is None:
        document, origin = load_document(season, amendments_path=amendments_path, receipt_path=receipt_path, seasons_root=seasons_root)
    parent = registry.load_registered_release(season, parent_id) if parent_id else registry.load_preferred_release(season)
    preferred = registry.load_preferred_release(season)
    applied, ignored = select_changes(document, parent)
    request = editorial.make_request(document, applied, origin=origin)
    try:
        plan = editorial.prepare(parent, request)
    except ValueError as exc:
        raise AmendmentBuildError(str(exc), status='rejected', details=dict(ignored=ignored)) from exc
    release_id = release_id or default_release_id(season, plan)
    evidence = BUILDS_ROOT / season / plan['transaction_id']
    report = dict(schema='pm99-amendment-build-report-v1', season=season, parent_release_id=parent.release_id,
        preferred_release_id=preferred.release_id, candidate_release_id=release_id, transaction_id=plan['transaction_id'],
        amendment_sha256=request['amendment_sha256'], origin=origin, applied_change_ids=[c['id'] for c in applied], ignored_changes=ignored,
        summary=summarise(plan), scope=plan['scope'], provenance=plan['provenance'], dry_run=dry_run,
        preferred_changed=False, registered_as_preferred=False)
    disk = disk_estimate(parent, plan, minimum_free_bytes)
    report['disk'] = disk
    _write_json(evidence / 'plan.json', plan)
    _write_json(evidence / 'inert-descriptor.json', editorial.inert_descriptor(parent, plan))
    _write_json(evidence / 'request-document.json', document)
    existing = _already_built(season, release_id, plan)
    if existing:
        report.update(status='already-built', game=existing)
    elif dry_run:
        report.update(status='planned' if disk['enough'] else 'planned-blocked-by-disk')
    elif not disk['enough']:
        report['status'] = 'blocked-by-disk'
        _save_report(evidence, report)
        raise AmendmentBuildError(
            f'not enough free disk: need {disk["planned_bytes"]} bytes plus a {minimum_free_bytes}-byte reserve, short by '
            f'{disk["shortfall_bytes"]} bytes. Free space or pass --minimum-free-bytes (never below 6 GiB).',
            status='blocked-by-disk', details=report)
    else:
        from scripts import publish_historical_role_delta_v1 as publisher
        try:
            result = publisher.publish(season, evidence / 'inert-descriptor.json', release_id=release_id, source_release_id=parent.release_id,
                profile_assignment_plan_path=evidence / 'plan.json', minimum_free_bytes=minimum_free_bytes)
        except (ValueError, OSError, registry.RegistryError, pipeline.PipelineError) as exc:
            raise AmendmentBuildError(f'build failed: {exc}', status='build-failed', details=report) from exc
        report.update(status='built', game=result['game'], changed_players=result['changed_players'])
    report['built_this_run'] = report['status'] == 'built'
    if report['status'] in ('built', 'already-built'):
        candidate = registry.load_registered_release(season, release_id)
        report['validation'] = registry.validate_preferred_release(season, level='playable', release_id=release_id)
        try:
            assert_candidate_integrity(candidate)
        except (ValueError, OSError) as exc:
            report['status'] = 'validation-failed'
            _save_report(evidence, report)
            raise AmendmentBuildError(f'candidate integrity failed: {exc}',
                                      status='validation-failed', details=report) from exc
        report['native_files_changed'] = _changed_native_files(parent, candidate)
        report['preferred_after'] = registry.load_preferred_release(season).release_id
        if report['preferred_after'] != preferred.release_id:
            raise AmendmentBuildError('internal error: preferred catalogue changed', status='internal')
        if not report['validation']['valid']:
            # A registered candidate that fails playable validation is never offered as usable.
            report['status'] = 'validation-failed'
            _save_report(evidence, report)
            raise AmendmentBuildError(
                f'candidate {release_id} was registered but failed playable validation (missing: {report["validation"].get("missing")}); '
                'it is not usable. See the evidence report.', status='validation-failed', details=report)
        history = _verification_proofs(evidence)
        report['verification_history'] = [h['_file'] for h in history]
        report['verified_in_this_run'] = False
        if verify_reconstruction:
            check_id = release_id + '-src'
            try:
                result = (_compare_existing_check(season, candidate, check_id) if _registered(season, check_id)
                          else editorial.reconstruction(candidate, check_id, minimum_free_bytes=minimum_free_bytes))
            except (ValueError, OSError, registry.RegistryError, pipeline.PipelineError) as exc:
                result = dict(error=str(exc))
            report['source_reconstruction'] = result
            report['verified_in_this_run'] = True
            report['verification_history'].append(_store_proof(evidence, dict(result, requested_check_release_id=check_id)))
            if not _proof_passes(result):
                report['status'] = 'verification-failed'
                _save_report(evidence, report)
                raise AmendmentBuildError(
                    'SOURCE reconstruction verification FAILED: ' + str(result.get('error') or 'candidate and rebuild differ') +
                    '. The candidate is not offered as usable; evidence retained.', status='verification-failed', details=report)
        else:
            passing = [h for h in history if _proof_passes(h)]
            if passing:
                carried = {k: v for k, v in passing[-1].items() if k != '_file'}
                report['source_reconstruction'] = dict(carried, verified_in_this_run=False, carried_forward_from=passing[-1]['_file'])
            else:
                report['source_reconstruction'] = None
        report['play_command'] = play_command(season, release_id)
        _record_candidate(season, dict(release_id=release_id, parent_release_id=parent.release_id, transaction_id=plan['transaction_id'],
            amendment_sha256=request['amendment_sha256'], change_count=len(applied), play_command=report['play_command'],
            summary=report['summary']))
    return _save_report(evidence, report)


def _proof_passes(result):
    return bool(result) and not result.get('error') and result.get('complete_game_inventory_identical') is True \
        and result.get('complete_recipe_identical') is True


def _verification_proofs(evidence):
    legacy = evidence / 'build-report.json'
    if not (evidence / 'verifications').is_dir() and legacy.is_file():
        # Reports written before proofs were stored separately: keep their passing proof as history (not re-claimed).
        earlier = json.loads(legacy.read_text()).get('source_reconstruction')
        if _proof_passes(earlier) and not earlier.get('carried_forward_from'):
            _store_proof(evidence, dict(earlier, imported_from='earlier build-report.json'))
    rows = []
    for path in sorted((evidence / 'verifications').glob('*.json')) if (evidence / 'verifications').is_dir() else []:
        rows.append(dict(json.loads(path.read_text()), _file=path.name))
    return rows


def _store_proof(evidence, proof):
    """Immutable, content-named verification record; an existing identical record is kept, never rewritten."""
    import hashlib
    raw = pipeline.canonical_json_bytes(proof) + b'\n'
    name = f'{hashlib.sha256(raw).hexdigest()[:24]}.json'
    path = evidence / 'verifications' / name
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return name


def _save_report(evidence, report):
    """Write build-report.json; an earlier different report is archived by content hash, never lost."""
    import hashlib
    path = evidence / 'build-report.json'
    if path.is_file():
        old = path.read_bytes()
        archive = evidence / 'history' / f'build-report-{hashlib.sha256(old).hexdigest()[:24]}.json'
        if not archive.exists():
            archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(old)
    _write_json(path, report)
    try:
        report['evidence'] = registry.relative_workspace_path(path)
    except registry.RegistryError:
        report['evidence'] = str(path)
    return report


def _registered(season, release_id):
    try:
        registry.load_registered_release(season, release_id)
    except (registry.RegistryError, OSError, ValueError):
        return False
    return True


def _compare_existing_check(season, candidate, check_id):
    """A previous SOURCE rebuild already exists: require it to equal the candidate exactly (never overwrite it)."""
    rebuilt = registry.load_registered_release(season, check_id)
    pipeline.assert_tree_matches_inventory(rebuilt.game_path, pipeline.read_json_file(candidate.inventory_path))
    if pipeline.read_json_file(rebuilt.package_path) != pipeline.read_json_file(candidate.package_path):
        raise ValueError('existing SOURCE verification recipe differs from the candidate')
    return dict(season=season, release_id=check_id, complete_game_inventory_identical=True, complete_recipe_identical=True,
                compilation_mode='source-bound-editorial-amendment-reconstruction-not-factory-compile', reused_existing_check_release=True)


def assert_candidate_integrity(candidate):
    """Check the entire candidate, including recipe and files beyond launch requirements."""
    pipeline.assert_tree_matches_inventory(candidate.game_path, pipeline.read_json_file(candidate.inventory_path))
    if registry.canonical_document_sha256(candidate.package_path) != candidate.locator.get('package_canonical_sha256'):
        raise ValueError('candidate recipe differs from its registered hash')


def _already_built(season, release_id, plan):
    try:
        existing = registry.load_registered_release(season, release_id)
    except (registry.RegistryError, OSError, ValueError):
        return None
    path = existing.locator.get('sourced_profile_assignment_plan_path')
    if path and pipeline.read_json_file(registry.ROOT / path) == plan:
        return str(existing.game_path)
    raise AmendmentBuildError(f'release {release_id} already exists with different content; choose another --release-id', status='exists')


def _changed_native_files(parent, candidate):
    changed = []
    for name in ('JUG98030.FDI', 'EQ98030.FDI', 'ENT98030.FDI', 'TEXTOS.PKF'):
        if registry.sha256_file(parent.game_path / 'DBDAT' / name) != registry.sha256_file(candidate.game_path / 'DBDAT' / name):
            changed.append(name)
    if registry.sha256_file(parent.game_path / 'MANAGPRE.EXE') != registry.sha256_file(candidate.game_path / 'MANAGPRE.EXE'):
        changed.append('MANAGPRE.EXE')
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('season', help='YYYY-YY')
    parser.add_argument('--amendments', type=Path, help='staged working.json (default: seasons/SEASON/editorial-amendments/working.json)')
    parser.add_argument('--receipt', type=Path, help='materialisation receipt; must match the working.json it hashes')
    parser.add_argument('--seasons-root', type=Path, default=DEFAULT_SEASONS_ROOT)
    parser.add_argument('--parent', help='registered release to edit (default: the preferred release; use a candidate to chain edits)')
    parser.add_argument('--release-id', help='candidate id (default: edited-SEASON-<transaction>)')
    parser.add_argument('--dry-run', action='store_true', help='validate and show exactly what would be written; build nothing')
    parser.add_argument('--verify-reconstruction', action='store_true', help='also rebuild the candidate from its parent and require equality')
    parser.add_argument('--minimum-free-bytes', type=int, default=None, help='free-space reserve to keep (default 8 GiB or $PM99_MINIMUM_FREE_BYTES; never below 6 GiB)')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        report = apply_amendments(args.season, amendments_path=args.amendments, receipt_path=args.receipt, seasons_root=args.seasons_root,
            parent_id=args.parent, release_id=args.release_id, dry_run=args.dry_run, verify_reconstruction=args.verify_reconstruction,
            minimum_free_bytes=args.minimum_free_bytes)
    except AmendmentBuildError as exc:
        if args.json:
            print(json.dumps(dict(status=exc.status, error=str(exc), details=exc.details), indent=2, sort_keys=True, default=str))
        else:
            print(f'{exc.status}: {exc}', file=sys.stderr)
        return 3 if exc.status == 'blocked-by-disk' else 2
    except (ValueError, registry.RegistryError, pipeline.PipelineError) as exc:
        print(f'rejected: {exc}', file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        return 0
    print(f'{report["status"]}: {report["season"]} candidate {report["candidate_release_id"]} (parent {report["parent_release_id"]})')
    for row in report['summary']:
        who = row.get('player') or row.get('manager')
        print(f'  {who}: ' + '; '.join(row['edits']) + ''.join(f'\n      also: {d}' for d in row['dependent']))
    for row in report['ignored_changes']:
        print(f'  ignored {row["id"]} ({row["manifest_id"]}): {row["reason"]}')
    if report.get('play_command'):
        print(f'  play: {report["play_command"]}')
        print(f'  playable validation: {"PASS" if report["validation"]["valid"] else "FAIL"}; preferred release unchanged ({report["preferred_after"]})')
    print(f'  evidence: {report.get("evidence")}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
