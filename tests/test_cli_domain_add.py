from pathlib import Path
import subprocess

from typer.testing import CliRunner

from cherve import config, paths
from cherve.cli import app


def test_domain_add_writes_config_and_nginx(tmp_path: Path, monkeypatch) -> None:
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

    site_config = config.SiteConfig(
        site_name="example",
        site_user="example",
        site_root=str(tmp_path / "site"),
        site_app_root=str(tmp_path / "site" / "_cherve" / "app"),
        site_www_root=str(tmp_path / "site" / "_cherve" / "app" / "public"),
        site_landing_root=str(tmp_path / "site" / "_cherve" / "landing"),
        repo_ssh="",
        branch="main",
        email="",
        mode="landing",
        domains=[],
        db_service=None,
        db_name=None,
        db_owner_user=None,
    )
    paths.SITES_DIR.mkdir(parents=True, exist_ok=True)
    config.write_site_config(site_config, path=paths.SITES_DIR / "example.toml")

    result = CliRunner().invoke(app, ["domain", "add", "example", "example.com"], input="n\nn\n")
    assert result.exit_code == 0

    loaded = config.read_site_config("example", path=paths.SITES_DIR / "example.toml")
    assert loaded.domains[0].name == "example.com"
    assert loaded.domains[0].with_www is False

    rendered = (Path(server_config.nginx_sites_available) / "example.com.conf").read_text(encoding="utf-8")
    assert "server_name example.com;" in rendered
