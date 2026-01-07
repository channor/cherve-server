from pathlib import Path

from cherve import config


def test_server_config_roundtrip(tmp_path: Path) -> None:
    cfg = config.ServerConfig(
        php_version="8.3",
        php_fpm_service="php8.3-fpm",
        php_fpm_sock="/run/php/php8.3-fpm.sock",
        nginx_sites_available="/etc/nginx/sites-available",
        nginx_sites_enabled="/etc/nginx/sites-enabled",
        mysql_installed=True,
        certbot_installed=False,
        client_max_body_size="20m",
    )
    path = tmp_path / "server.toml"
    config.write_server_config(cfg, path)
    assert path.exists()
    reloaded = config.read_server_config(path)
    assert reloaded == cfg
    assert list(tmp_path.iterdir()) == [path]


def test_site_config_roundtrip(tmp_path: Path) -> None:
    cfg = config.SiteConfig(
        domain="example.com",
        site_user="example",
        site_root="/var/www/example.com",
        repo_ssh="git@github.com:org/repo.git",
        branch="main",
        with_www=True,
        email="",
        db_enabled=True,
        db_host="127.0.0.1",
        db_port=3306,
        db_name="example_db",
        db_owner_user="example_owner",
        db_owner_password="secret",
    )
    path = tmp_path / "example.com.toml"
    config.write_site_config(cfg, path)
    assert path.exists()
    reloaded = config.read_site_config(path)
    assert reloaded == cfg
