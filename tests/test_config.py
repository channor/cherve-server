from cherve import config


def test_server_config_roundtrip(tmp_path):
    server = config.ServerConfig(
        default_php_version="8.3",
        php={
            "8.3": config.PHPConfig(
                fpm_service="php8.3-fpm",
                fpm_sock="/run/php/php8.3-fpm.sock",
            )
        },
        nginx=config.NginxConfig(
            sites_available="/etc/nginx/sites-available",
            sites_enabled="/etc/nginx/sites-enabled",
        ),
        features=config.FeatureConfig(mysql_installed=True, certbot_installed=False),
    )
    path = tmp_path / "server.toml"
    config.write_server_config(server, path=path)
    loaded = config.read_server_config(path=path)
    assert loaded == server


def test_site_config_roundtrip(tmp_path):
    site = config.SiteConfig(
        domain="example.com",
        site_user="example",
        site_root="/var/www/example.com",
        repo_ssh="git@github.com:org/repo.git",
        branch="main",
        with_www=True,
        email="ops@example.com",
        db_enabled=True,
        db_name="example_db",
        db_owner_user="example_owner",
        db_owner_password="secret",
        db_host="localhost",
        db_port=3306,
    )
    path = tmp_path / "site.toml"
    config.write_site_config(site, path=path)
    loaded = config.read_site_config(path=path)
    assert loaded == site
