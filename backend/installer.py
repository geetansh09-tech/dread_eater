"""
Dread Eater - overnight scheduler installer
===========================================
Detects the operating system, the Python interpreter and the project folder,
then writes (and optionally installs) the right 3 AM job:

    macOS    launchd agent   ~/Library/LaunchAgents/com.dreadeater.night.plist
    Linux    systemd timer   ~/.config/systemd/user/dread-eater-night.{service,timer}
    Windows  Task Scheduler  schtasks /Create ... /TN DreadEaterNight

No placeholder paths to edit by hand.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

from backend.paths import PROJECT_ROOT, data_dir, detect_system

LABEL = "com.dreadeater.night"
TASK_NAME = "DreadEaterNight"


def _hh_mm(at: str) -> tuple[int, int]:
    try:
        h, m = at.split(":")
        h, m = int(h), int(m)
        assert 0 <= h < 24 and 0 <= m < 60
        return h, m
    except Exception:
        raise SystemExit(f"--at must look like HH:MM (24h), got {at!r}")


def render_plist(python: str, root: str, at: str, log_dir: str) -> str:
    h, m = _hh_mm(at)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{escape(python)}</string>
    <string>{escape(str(Path(root) / "run.py"))}</string>
    <string>night</string>
  </array>
  <key>WorkingDirectory</key><string>{escape(root)}</string>
  <key>StandardOutPath</key><string>{escape(str(Path(log_dir) / "launchd.out.log"))}</string>
  <key>StandardErrorPath</key><string>{escape(str(Path(log_dir) / "launchd.err.log"))}</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>{h}</integer><key>Minute</key><integer>{m}</integer></dict>
</dict>
</plist>
"""


def render_service(python: str, root: str) -> str:
    return f"""[Unit]
Description=Dread Eater overnight draft prep

[Service]
Type=oneshot
WorkingDirectory={root}
ExecStart="{python}" "{Path(root) / 'run.py'}" night
"""


def render_timer(at: str) -> str:
    h, m = _hh_mm(at)
    return f"""[Unit]
Description=Run Dread Eater night prep daily at {h:02d}:{m:02d}

[Timer]
OnCalendar=*-*-* {h:02d}:{m:02d}:00
Persistent=true

[Install]
WantedBy=timers.target
"""


def windows_command(python: str, root: str, at: str) -> list[str]:
    h, m = _hh_mm(at)
    run = str(Path(root) / "run.py")
    return ["schtasks", "/Create", "/F", "/SC", "DAILY", "/ST", f"{h:02d}:{m:02d}",
            "/TN", TASK_NAME, "/TR", f'"{python}" "{run}" night']


def _run(cmd: list[str], dry: bool) -> None:
    print("  $", " ".join(cmd))
    if not dry:
        subprocess.run(cmd, check=False)


def install(at: str = "03:00", dry_run: bool = False) -> None:
    info = detect_system()
    py, root, osname = info["python"], info["project_root"], info["os"]
    log_dir = str(data_dir())
    print(f"Detected: {osname} | python={py}\n          project={root}")

    if osname == "macos":
        target = Path(info["home"]) / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        text = render_plist(py, root, at, log_dir)
        print(f"Writing {target}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        _run(["launchctl", "unload", str(target)], dry_run)
        _run(["launchctl", "load", str(target)], dry_run)
    elif osname == "linux":
        unit_dir = Path(info["home"]) / ".config" / "systemd" / "user"
        print(f"Writing units to {unit_dir}")
        if not dry_run:
            unit_dir.mkdir(parents=True, exist_ok=True)
            (unit_dir / "dread-eater-night.service").write_text(render_service(py, root), encoding="utf-8")
            (unit_dir / "dread-eater-night.timer").write_text(render_timer(at), encoding="utf-8")
        _run(["systemctl", "--user", "daemon-reload"], dry_run)
        _run(["systemctl", "--user", "enable", "--now", "dread-eater-night.timer"], dry_run)
    elif osname == "windows":
        _run(windows_command(py, root, at), dry_run)
    else:
        raise SystemExit(f"Unsupported OS: {osname}. Run `python run.py night` from cron instead.")
    print("Done." if not dry_run else "Dry run only - nothing was changed.")


def uninstall(dry_run: bool = False) -> None:
    info = detect_system()
    osname = info["os"]
    if osname == "macos":
        target = Path(info["home"]) / "Library" / "LaunchAgents" / f"{LABEL}.plist"
        _run(["launchctl", "unload", str(target)], dry_run)
        if not dry_run:
            target.unlink(missing_ok=True)
    elif osname == "linux":
        unit_dir = Path(info["home"]) / ".config" / "systemd" / "user"
        _run(["systemctl", "--user", "disable", "--now", "dread-eater-night.timer"], dry_run)
        if not dry_run:
            for n in ("dread-eater-night.service", "dread-eater-night.timer"):
                (unit_dir / n).unlink(missing_ok=True)
        _run(["systemctl", "--user", "daemon-reload"], dry_run)
    elif osname == "windows":
        _run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], dry_run)
    print("Removed." if not dry_run else "Dry run only - nothing was changed.")
