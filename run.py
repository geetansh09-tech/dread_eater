#!/usr/bin/env python3
"""Dread Eater launcher.

    python run.py            start the app and open it in your browser
    python run.py serve      same as above
    python run.py night      overnight draft prep (safe to schedule; exits 0 if Ollama is off)
    python run.py check      verify Ollama + model are ready
    python run.py test       run the test suite
    python run.py paths      show the auto-detected paths on this machine
    python run.py schedule install|remove [--at HH:MM] [--dry-run]
                             set up the 3 AM overnight job for this OS
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from backend.paths import PROJECT_ROOT, config_path, data_dir, db_path, detect_system, load_config  # noqa: E402


def _cfg() -> dict:
    return load_config()


def cmd_paths(_: argparse.Namespace) -> None:
    info = detect_system()
    print(f"OS            : {info['os']}")
    print(f"Python        : {info['python']}")
    print(f"Project folder: {PROJECT_ROOT}")
    print(f"Config file   : {config_path()}")
    print(f"Database      : {db_path()}")
    print(f"Log folder    : {data_dir()}")


def cmd_schedule(args: argparse.Namespace) -> None:
    from backend import installer

    if args.action == "install":
        installer.install(at=args.at, dry_run=args.dry_run)
    else:
        installer.uninstall(dry_run=args.dry_run)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    cfg = _cfg()
    host, port = cfg["server"]["host"], cfg["server"]["port"]
    if host not in ("127.0.0.1", "localhost", "::1"):
        sys.exit("Refusing to start: server.host must stay localhost-only.")
    if not args.no_browser:
        threading.Thread(
            target=lambda: (time.sleep(1.5), webbrowser.open(f"http://{host}:{port}")),
            daemon=True,
        ).start()
    print(f"🦥 Dread Eater is waking up at http://{host}:{port}  (Ctrl+C to nap)")
    uvicorn.run("backend.main:app", host=host, port=port, log_level="warning")


def cmd_night(_: argparse.Namespace) -> None:
    from backend.night_runner import main

    main()


def cmd_check(_: argparse.Namespace) -> None:
    import asyncio

    from backend.ollama_client import check_ollama_alive, list_models

    cfg = _cfg()
    base, model = cfg["ollama"]["base_url"], cfg["ollama"]["model"]

    async def go() -> int:
        if not await check_ollama_alive(base):
            print(f"✗ Ollama is not reachable at {base}. Start it with: ollama serve")
            return 1
        models = await list_models(base)
        if model not in models:
            print(f"✗ Model '{model}' not installed. Run: ollama pull {model}")
            print(f"  Installed: {', '.join(models) or 'none'}")
            return 1
        print(f"✓ Ollama is running and '{model}' is ready. Slow and steady!")
        return 0

    sys.exit(asyncio.run(go()))


def cmd_test(_: argparse.Namespace) -> None:
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT))


def main() -> None:
    p = argparse.ArgumentParser(prog="dread-eater", description="Tiny steps for big dreads.")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("serve", help="start the web app")
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_serve)
    sub.add_parser("night", help="pre-write drafts overnight").set_defaults(fn=cmd_night)
    sub.add_parser("check", help="verify Ollama and model").set_defaults(fn=cmd_check)
    sub.add_parser("test", help="run tests").set_defaults(fn=cmd_test)
    sub.add_parser("paths", help="show auto-detected paths").set_defaults(fn=cmd_paths)
    sc = sub.add_parser("schedule", help="install/remove the overnight job for this OS")
    sc.add_argument("action", choices=["install", "remove"])
    sc.add_argument("--at", default="03:00", help="time of day, HH:MM (default 03:00)")
    sc.add_argument("--dry-run", action="store_true")
    sc.set_defaults(fn=cmd_schedule)
    args = p.parse_args()
    if not args.cmd:
        args = p.parse_args(["serve"])
    args.fn(args)


if __name__ == "__main__":
    main()
