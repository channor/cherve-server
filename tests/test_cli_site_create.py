from pathlib import Path
import subprocess

from typer.testing import CliRunner

from cherve import config, paths, system
from cherve.cli import app
from cherve.site import _ensure_deploy_key


def test_site_create_writes_config_and_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("cherve.system.require_root", lambda: None)
    monkeypatch.setattr("cherve.system.run", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr("cherve.system.run_as_user", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(paths, "WWW_ROOT", tmp_path / "www")
    monkeypatch.setattr(paths, "SITES_DIR", tmp_path / "etc" / "sites.d")
    monkeypatch.setattr(paths, "HOME_ROOT", tmp_path / "home")

    server_config = config.ServerConfig(
        php_version="php8.3",
        fpm_service="php8.3-fpm",
        fpm_sock="/run/php/php8.3-fpm.sock",
        nginx_sites_available="/etc/nginx/sites-available",
        nginx_sites_enabled="/etc/nginx/sites-enabled",
        mysql_installed=True,
        pqsql_installed=False,
        sqlite_installed=False,
        certbot_installed=False,
    )
    monkeypatch.setattr("cherve.config.read_server_config", lambda: server_config)

    def fake_deploy_key(user, key_path):
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_text("PRIVATE", encoding="utf-8")
        key_path.with_suffix(".pub").write_text("PUBLIC", encoding="utf-8")
        return key_path

    monkeypatch.setattr("cherve.site._ensure_deploy_key", fake_deploy_key)

    input_data = "\n".join(
        [
            "microsoft",
            "microsoft.com",
            "",
            "git@github.com:ORG/REPO.git",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "n",
            "n",
        ]
    )
    result = CliRunner().invoke(app, ["site", "create"], input=input_data)
    assert result.exit_code == 0
    assert "Deploy key" in result.output
    assert "DB owner password" in result.output

    site_path = paths.SITES_DIR / "microsoft.com.toml"
    loaded = config.read_site_config("microsoft.com", path=site_path)
    assert loaded.domain == "microsoft.com"


def test_ensure_deploy_key_passes_empty_passphrase(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {"calls": []}

    def fake_run(argv, *args, **kwargs):
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_run_as_user(user, argv_or_bash, *args, **kwargs):
        captured["user"] = user
        captured["calls"].append(argv_or_bash)
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(system, "run", fake_run)
    monkeypatch.setattr(system, "run_as_user", fake_run_as_user)

    key_path = tmp_path / "home" / "amazon" / ".ssh" / "id_cherve_deploy"
    _ensure_deploy_key("amazon", key_path)

    assert captured["user"] == "amazon"
    assert all(isinstance(call, str) for call in captured["calls"])
    assert any('-N ""' in call for call in captured["calls"])
