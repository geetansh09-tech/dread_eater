"""Path auto-detection and scheduler installer rendering."""
from pathlib import Path

import pytest

from backend import installer, paths


def test_project_root_is_detected_from_file_location():
    assert (paths.PROJECT_ROOT / "run.py").exists()
    assert paths.PROJECT_ROOT.is_absolute()


def test_relative_paths_anchor_to_project_root_not_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DREAD_EATER_DB", raising=False)
    p = Path(paths.db_path({"db": {"path": "./dread_eater.db"}}))
    assert p == paths.PROJECT_ROOT / "dread_eater.db"


def test_home_and_env_expansion(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("DE_TEST", "sub")
    assert paths.resolve_path("~/x.db") == (tmp_path / "x.db").resolve()
    assert paths.resolve_path("$DE_TEST/x.db") == (paths.PROJECT_ROOT / "sub" / "x.db").resolve()


def test_db_env_override_creates_parent(monkeypatch, tmp_path):
    target = tmp_path / "nested" / "d.db"
    monkeypatch.setenv("DREAD_EATER_DB", str(target))
    assert paths.db_path({"db": {"path": "ignored.db"}}) == str(target.resolve())
    assert target.parent.is_dir()


def test_data_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("DREAD_EATER_HOME", str(tmp_path / "logs"))
    assert paths.data_dir() == (tmp_path / "logs").resolve()


def test_detect_system_keys():
    info = paths.detect_system()
    assert info["os"] in {"linux", "macos", "windows"}
    assert Path(info["python"]).is_absolute()
    assert info["project_root"] == str(paths.PROJECT_ROOT)


def test_rendered_files_contain_real_paths_and_no_placeholders():
    py, root = "/opt/py/bin/python", "/work/Dread-Eater"
    for text in (
        installer.render_plist(py, root, "02:30", "/logs"),
        installer.render_service(py, root),
        installer.render_timer("02:30"),
        " ".join(installer.windows_command(py, root, "02:30")),
    ):
        assert "ABSOLUTE" not in text
    assert "<integer>2</integer>" in installer.render_plist(py, root, "02:30", "/logs")
    assert "02:30:00" in installer.render_timer("02:30")
    assert root in installer.render_service(py, root)


def test_bad_time_rejected():
    with pytest.raises(SystemExit):
        installer.render_timer("25:99")
