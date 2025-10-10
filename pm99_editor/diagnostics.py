"""Helpers for persisting diagnostic breadcrumbs to disk."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping

__all__ = ["record_pipeline_issue"]

_ENV_VAR = "PM99_DIAGNOSTICS_DIR"


def _resolve_base_dir() -> Path:
    """Return the directory where diagnostics should be written."""

    env_override = os.getenv(_ENV_VAR)
    base = Path(env_override) if env_override else Path("diagnostics")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _json_safe(value: Any) -> Any:
    """Convert values that aren't naturally JSON serialisable."""

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        # Hex preserves ordering and keeps files readable during reverse engineering.
        return value.hex()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "_asdict"):
        return _json_safe(value._asdict())  # type: ignore[attr-defined]
    return repr(value)


def record_pipeline_issue(kind: str, details: Mapping[str, Any]) -> Path:
    """Append a JSON line describing ``kind`` to the diagnostics log.

    Args:
        kind: Short identifier (e.g. ``"pkf_table_validation"``).
        details: Mapping describing the failure.  Values are serialised into a
            JSON-friendly form automatically.

    Returns:
        The :class:`~pathlib.Path` of the log file that received the entry.
    """

    base_dir = _resolve_base_dir()
    log_path = base_dir / f"{kind}.log"
    entry: MutableMapping[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "details": _json_safe(details),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        json.dump(entry, handle, ensure_ascii=False)
        handle.write("\n")
    return log_path
