# Overnight scheduling

You no longer need to edit any paths. From the project folder run:

```bash
python run.py schedule install            # 3:00 AM daily
python run.py schedule install --at 02:30 # custom time
python run.py schedule install --dry-run  # preview, change nothing
python run.py schedule remove
```

The installer detects your OS, the Python interpreter you are using (your
virtualenv, if active) and the project folder, then sets up:

| OS | Mechanism |
|---|---|
| macOS | launchd agent in `~/Library/LaunchAgents/` |
| Linux | systemd user timer in `~/.config/systemd/user/` |
| Windows | Task Scheduler task `DreadEaterNight` |

Run `python run.py schedule install` from inside your activated virtualenv so
the job uses the same Python that has the dependencies installed.
