"""
Dread Eater - path resolution
=============================
Every path the app uses is worked out at runtime, so the project runs the same
way on Windows, macOS and Linux, from any folder, and no matter which working
directory launched it (a terminal, launchd, systemd or Task Scheduler).

Rules
-----
* PROJECT_ROOT is detected from this file's own location.
* Relative paths in ``config.yaml`` (e.g. ``./dread_eater.db``) are resolved
  against PROJECT_ROOT, never against the current working directory.
* ``~`` and environment variables (``$HOME``, ``%APPDATA%``) are expanded.
* Environment overrides:
    DREAD_EATER_CONFIG   path to an alternative config.yaml
    DREAD_EATER_DB       path to the SQLite file
    DREAD_EATER_HOME     folder for logs (default: ~/.dread_eater)
"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

import yaml

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"
DEFAULT_CONFIG: Path = PROJECT_ROOT / "config.yaml"


def resolve_path(value: str | os.PathLike, base: Path | None = None) -> Path:
    """Expand ``~``/env vars and anchor relative paths to ``base`` (default: project root)."""
    p = Path(os.path.expandvars(os.path.expanduser(str(value))))
    if not p.is_absolute():
        p = (base or PROJECT_ROOT) / p
    return p.resolve()


def config_path() -> Path:
    override = os.environ.get("DREAD_EATER_CONFIG")
    return resolve_path(override, Path.cwd()) if override else DEFAULT_CONFIG


def load_config() -> dict:
    with open(config_path(), encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def db_path(cfg: dict | None = None) -> str:
    """Absolute path to the SQLite file; parent folder is created if missing."""
    override = os.environ.get("DREAD_EATER_DB")
    if override:
        p = resolve_path(override, Path.cwd())
    else:
        cfg = cfg if cfg is not None else load_config()
        p = resolve_path(cfg.get("db", {}).get("path", "dread_eater.db"))
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def data_dir() -> Path:
    """Per-user folder for logs (``~/.dread_eater`` unless DREAD_EATER_HOME is set)."""
    override = os.environ.get("DREAD_EATER_HOME")
    d = resolve_path(override, Path.cwd()) if override else Path.home() / ".dread_eater"
    d.mkdir(parents=True, exist_ok=True)
    return d


def detect_system() -> dict:
    """What the installer needs to know about the machine it's running on."""
    name = platform.system()  # 'Windows' | 'Darwin' | 'Linux'
    return {
        "os": {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(name, name.lower()),
        "python": str(Path(sys.executable).resolve()),
        "project_root": str(PROJECT_ROOT),
        "home": str(Path.home()),
    }
