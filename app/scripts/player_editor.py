"""Deprecated player editor script.

This script is retained for backward compatibility. It emits a warning and
delegates to app.cli.main().
"""

import warnings
from app import cli as _cli

warnings.warn(
    "The 'player_editor' script is deprecated. Use 'python -m app.cli' instead.",
    DeprecationWarning,
    stacklevel=2,
)

def main(args: list[str] | None = None) -> None:
    """Delegate to app.cli.main()."""
    _cli.main(args)


if __name__ == "__main__":
    main()
