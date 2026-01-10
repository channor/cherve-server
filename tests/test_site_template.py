from pathlib import Path

from cherve import config
from cherve.site import _render_nginx_config


def test_nginx_template_render(tmp_path: Path, monkeypatch) -> None:
    sites_available = tmp_path / "sites-available"
    sites_enabled = tmp_path / "sites-enabled"

    server_config = config.ServerConfig(
        php_version="php8.3",
        fpm_service="php8.3-fpm",
        fpm_sock="/run/php/php8.3-fpm.sock",
        nginx_sites_available=str(sites_available),
        nginx_sites_enabled=str(sites_enabled),
        mysql_installed=False,
        pqsql_installed=False,
        sqlite_installed=False,
        certbot_installed=False,
    )
    site_config = config.SiteConfig(
        site_name="example",
        site_user="example",
        site_root="/var/www/example",
        site_app_root="/var/www/example/_cherve/app",
        site_www_root="/var/www/example/public",
        site_landing_root="/var/www/example/_cherve/landing",
        repo_ssh="git@github.com:ORG/REPO.git",
        branch="main",
        email="",
        mode="landing",
        domains=[
            config.DomainConfig(
                name="example.com",
                with_www=True,
                tls_enabled=False,
                ssl_certificate="",
                ssl_certificate_key="",
            )
        ],
        db_service=None,
        db_name=None,
        db_owner_user=None,
    )

    monkeypatch.setattr("cherve.site.system.run", lambda *args, **kwargs: None)
    _render_nginx_config(
        site_config,
        site_config.domains[0],
        server_config,
        template_name="nginx_php_app.conf",
        root_path=site_config.site_www_root,
        client_max_body_size="32m",
    )

    config_path = sites_available / "example.com.conf"
    assert config_path.exists()
    text = config_path.read_text(encoding="utf-8")
    assert "server_name example.com www.example.com;" in text
    assert "root /var/www/example/public;" in text
    assert "fastcgi_pass unix:/run/php/php8.3-fpm.sock;" in text
    assert "client_max_body_size 32m;" in text
