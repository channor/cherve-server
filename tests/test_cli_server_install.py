from pathlib import Path
import subprocess

from typer.testing import CliRunner

from cherve import config, paths, server
from cherve.cli import app


def test_server_install_skips_installed_packages(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("cherve.system.require_root", lambda: None)
    monkeypatch.setattr("cherve.system.run", fake_run)
    monkeypatch.setattr("cherve.system.is_installed_apt", lambda pkg: True)
    monkeypatch.setattr(server, "apply_php_fpm_ini_templates", lambda ctx: None)
    monkeypatch.setattr(server, "PLAN", (server.PHP,))
    monkeypatch.setattr(paths, "SERVER_CONFIG_PATH", tmp_path / "server.toml")

    input_data = "\n"
    result = CliRunner().invoke(app, ["server", "install"], input=input_data)
    assert result.exit_code == 0

    assert not any(cmd[:3] == ["apt-get", "install", "-y"] for cmd in calls)
    loaded = config.read_server_config(path=paths.SERVER_CONFIG_PATH)
    assert loaded.fpm_service == "php8.3-fpm"
