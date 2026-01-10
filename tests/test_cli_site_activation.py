from pathlib import Path
import subprocess

from typer.testing import CliRunner

from cherve import config, paths
from cherve.cli import app


def _site_config(base: Path, **overrides) -> config.SiteConfig:
    defaults = {
        "domain": "example.com",
        "site_user": "example",
        "site_root": str(base / "site"),
        "site_app_root": str(base / "site" / "_cherve" / "app"),
        "site_www_root": str(base / "site" / "_cherve" / "app" / "public"),
        "site_landing_root": str(base / "site" / "_cherve" / "landing"),
        "repo_ssh": "git@github.com:ORG/REPO.git",
        "branch": "main",
        "with_www": True,
        "email": "",
        "mode": "landing",
        "tls_enabled": False,
        "ssl_certificate": "",
        "ssl_certificate_key": "",
        "db_service": None,
        "db_name": None,
        "db_owner_user": None,
    }
    defaults.update(overrides)
    return config.SiteConfig(**defaults)


def test_site_activate_writes_app_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("cherve.system.require_root", lambda: None)
    monkeypatch.setattr("cherve.system.run", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(paths, "SITES_DIR", tmp_path / "etc" / "sites.d")

    server_config = config.ServerConfig(
        php_version="php8.3",
        fpm_service="php8.3-fpm",
        fpm_sock="/run/php/php8.3-fpm.sock",
        nginx_sites_available=str(tmp_path / "nginx" / "sites-available"),
        nginx_sites_enabled=str(tmp_path / "nginx" / "sites-enabled"),
        mysql_installed=False,
        pqsql_installed=False,
        sqlite_installed=False,
        certbot_installed=False,
    )
    monkeypatch.setattr("cherve.config.read_server_config", lambda: server_config)

    paths.SITES_DIR.mkdir(parents=True, exist_ok=True)
    config.write_site_config(_site_config(tmp_path), path=paths.SITES_DIR / "example.com.toml")

    result = CliRunner().invoke(app, ["site", "activate", "example.com"])
    assert result.exit_code == 0

    rendered = (Path(server_config.nginx_sites_available) / "example.com.conf").read_text(encoding="utf-8")
    assert "root " + str(tmp_path / "site" / "_cherve" / "app" / "public") in rendered
    assert config.read_site_config("example.com", path=paths.SITES_DIR / "example.com.toml").mode == "app"


def test_site_deactivate_writes_landing_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("cherve.system.require_root", lambda: None)
    monkeypatch.setattr("cherve.system.run", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(paths, "SITES_DIR", tmp_path / "etc" / "sites.d")

    server_config = config.ServerConfig(
        php_version="php8.3",
        fpm_service="php8.3-fpm",
        fpm_sock="/run/php/php8.3-fpm.sock",
        nginx_sites_available=str(tmp_path / "nginx" / "sites-available"),
        nginx_sites_enabled=str(tmp_path / "nginx" / "sites-enabled"),
        mysql_installed=False,
        pqsql_installed=False,
        sqlite_installed=False,
        certbot_installed=False,
    )
    monkeypatch.setattr("cherve.config.read_server_config", lambda: server_config)

    paths.SITES_DIR.mkdir(parents=True, exist_ok=True)
    config.write_site_config(
        _site_config(tmp_path, mode="app"),
        path=paths.SITES_DIR / "example.com.toml",
    )

    result = CliRunner().invoke(app, ["site", "deactivate", "example.com"])
    assert result.exit_code == 0

    rendered = (Path(server_config.nginx_sites_available) / "example.com.conf").read_text(encoding="utf-8")
    assert "root " + str(tmp_path / "site" / "_cherve" / "landing") in rendered
    assert config.read_site_config("example.com", path=paths.SITES_DIR / "example.com.toml").mode == "landing"


def test_site_tls_enable_updates_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("cherve.system.require_root", lambda: None)
    run_calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        run_calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("cherve.system.run", fake_run)
    monkeypatch.setattr(paths, "SITES_DIR", tmp_path / "etc" / "sites.d")
    paths.SITES_DIR.mkdir(parents=True, exist_ok=True)
    config.write_site_config(
        _site_config(tmp_path, with_www=True),
        path=paths.SITES_DIR / "example.com.toml",
    )

    input_data = "\n".join(["y", "admin@example.com"])
    result = CliRunner().invoke(app, ["site", "tls", "enable", "example.com"], input=input_data)
    assert result.exit_code == 0

    assert any(cmd[0] == "certbot" for cmd in run_calls)
    loaded = config.read_site_config("example.com", path=paths.SITES_DIR / "example.com.toml")
    assert loaded.tls_enabled is True
    assert loaded.ssl_certificate.endswith("/etc/letsencrypt/live/example.com/fullchain.pem")
