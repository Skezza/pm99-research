"""Focused coverage for per-season calendar-bound draft replay."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import season_draft_blocker_closure_v1 as closure  # noqa: E402


def _write(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = closure.package_v2.canonical_json_bytes(value)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def test_replay_uses_each_season_exact_calendar_bound_pair(tmp_path: Path, monkeypatch) -> None:
    season = "2000-01"
    current_root = tmp_path / "current"
    season_root = current_root / season
    source_sha = _write(season_root / "revisions/r1/source.json", {"source": True})
    intake_sha = _write(season_root / "revisions/r1/intake.json", {"registry_sha256": "registry"})
    allocation_sha = _write(season_root / "revisions/r1/allocation.json", {"allocation": True})
    _write(
        season_root / "current.json",
        {
            "schema_version": closure.CURRENT_SCHEMA,
            "season": season,
            "artifacts": {
                "source": {"path": "revisions/r1/source.json", "sha256": source_sha},
                "intake": {"path": "revisions/r1/intake.json", "sha256": intake_sha},
                "allocation": {"path": "revisions/r1/allocation.json", "sha256": allocation_sha},
            },
        },
    )
    opening_root = tmp_path / "opening"
    _write(opening_root / season / "opening-squad-preallocation.json", {"opening": True})
    registry_root = tmp_path / "registries"
    _write(registry_root / season / "fixed-carrier-registry.json", {"registry": True})

    calendar_root = tmp_path / "calendar-bound"
    template = {"schema_version": "pm99-season-package-v2", "season": {"start_year": 2000, "end_year": 2001}}
    template_path = calendar_root / season / "draft-season-package.calendar-bound.json"
    _write(template_path, template)
    template_sha = closure.builder._sha256_document(template)
    calendar_audit = {"season": {"label": "2000/01"}, "output_package_sha256": template_sha}
    _write(calendar_root / season / "calendar-binding-audit.json", calendar_audit)

    monkeypatch.setattr(closure.package_v2, "validate_package", lambda *args, **kwargs: None)

    def fake_document_sha(value):
        if value == template:
            return template_sha
        if value == {"registry": True}:
            return "registry"
        return "a" * 64

    monkeypatch.setattr(closure.builder, "_sha256_document", fake_document_sha)
    captured: dict[str, object] = {}

    def fake_build_draft(**kwargs):
        captured.update(kwargs)
        return {"package": True}, {
            "draft_package_sha256": "b" * 64,
            "release_eligible": False,
            "hard_blockers": [],
            "coverage": {},
        }

    monkeypatch.setattr(closure.builder, "build_draft", fake_build_draft)

    result = closure.replay(
        current_root=current_root,
        opening_root=opening_root,
        output_root=tmp_path / "output",
        template_path=tmp_path / "unused-template.json",
        registry_root=registry_root,
        calendar_binding_root=calendar_root,
    )

    assert captured["template"] == template
    assert captured["calendar_binding_audit"] == calendar_audit
    assert result["rows"][0]["inputs"]["template_package_sha256"] == template_sha
