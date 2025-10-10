"""Conservative save settings for PM99 editor.

This module exposes runtime flags to control the conservative "name-only" save behavior.
Environment variables:
  - PM99_SAVE_NAME_ONLY: enable safe name-only save mode (default: True)
  - PM99_ALLOW_FULL_REWRITE: opt-in override to allow full-record rewrite when expansion is required (default: False)
"""
import os

def _env_flag(name: str, default: bool):
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).lower() in ("1", "true", "yes", "on")

# Default to safe name-only save behaviour
SAVE_NAME_ONLY = _env_flag("PM99_SAVE_NAME_ONLY", True)

# Opt-in override: allow full-record rewrite if an expansion would be required.
ALLOW_FULL_RECORD_REWRITE_ON_EXPANSION = _env_flag("PM99_ALLOW_FULL_REWRITE", False)

__all__ = ["SAVE_NAME_ONLY", "ALLOW_FULL_RECORD_REWRITE_ON_EXPANSION"]