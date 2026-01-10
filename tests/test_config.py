from pathlib import Path

from cherve import config


def test_server_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "server.toml"
    original = config.ServerConfig(
        php_version="php8.3",
        fpm_service="php8.3-fpm",
        fpm_sock="/run/php/php8.3-fpm.sock",
        nginx_sites_available="/etc/nginx/sites-available",
        nginx_sites_enabled="/etc/nginx/sites-enabled",
        mysql_installed=True,
        pqsql_installed=False,
        sqlite_installed=False,
        certbot_installed=True,
    )
    config.write_server_config(original, path=path)
    assert path.exists()
    assert not path.with_suffix(".toml.tmp").exists()
    loaded = config.read_server_config(path=path)
    assert loaded == original


def test_site_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "site.toml"
    original = config.SiteConfig(
        site_name="example",
        site_user="example",
        site_root="/var/www/example",
        site_app_root="/var/www/example/_cherve/app",
        site_www_root="/var/www/example/public",
        site_landing_root="/var/www/example/_cherve/landing",
        repo_ssh="git@github.com:ORG/REPO.git",
        branch="main",
        email="admin@example.com",
        mode="landing",
        domains=[
            config.DomainConfig(
                name="example.com",
                with_www=True,
                tls_enabled=True,
                ssl_certificate="/etc/letsencrypt/live/example.com/fullchain.pem",
                ssl_certificate_key="/etc/letsencrypt/live/example.com/privkey.pem",
            )
        ],
        db_service="mysql",
        db_name="example_db",
        db_owner_user="example_db_owner",
    )
    config.write_site_config(original, path=path)
    loaded = config.read_site_config("example", path=path)
    assert loaded == original
