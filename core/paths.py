"""Path helpers for PyInstaller bundling.

Two kinds of paths:
- **asset_path**: read-only files bundled inside the .exe (sounds, sprites).
  Resolves via sys._MEIPASS when frozen, or project root when running from source.
- **app_dir**: writable directory next to the .exe (settings, logs, replays, .env).
  When running from source this is just the project root.
"""
from __future__ import annotations

import os
import sys


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _project_root() -> str:
    """Project root when running from source."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset_path(*parts: str) -> str:
    """Return absolute path to a bundled read-only asset.

    Example::

        asset_path("sounds", "laser.mp3")
    """
    if _is_frozen():
        base = sys._MEIPASS  # type: ignore[attr-defined]
    else:
        base = _project_root()
    return os.path.join(base, *parts)


def app_dir() -> str:
    """Return the writable application directory.

    When frozen this is the folder containing the .exe.
    When running from source this is the project root.
    """
    if _is_frozen():
        return os.path.dirname(sys.executable)
    return _project_root()


def app_path(*parts: str) -> str:
    """Return absolute path to a writable file next to the .exe.

    Example::

        app_path(".env")
        app_path("logs", "crash.log")
    """
    return os.path.join(app_dir(), *parts)
