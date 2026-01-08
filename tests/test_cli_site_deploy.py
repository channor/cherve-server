from subprocess import CompletedProcess

from typer.testing import CliRunner

from cherve.cli import app
from cherve import config
from cherve import paths
from cherve import system


def test_site_deploy_creates_env_and_runs_commands(monkeypatch, temp_paths):
    calls = []

    def fake_run(argv, check=True, capture=False, env=None, cwd=None):
        calls.append(list(argv))
        return CompletedProcess(argv, 0, stdout="", stderr="")

    def fake_run_as_user(user, argv_or_bash, check=True, capture=False, env=None, cwd=None):
        calls.append(["run_as_user", user, argv_or_bash])
        return CompletedProcess(["sudo"], 0, stdout="", stderr="")

    monkeypatch.setattr(system, "run", fake_run)
    monkeypatch.setattr(system, "run_as_user", fake_run_as_user)
    monkeypatch.setattr(system, "require_root", lambda: None)

    server_config = config.ServerConfig(
        default_php_version="8.3",
        php={"8.3": config.PHPConfig(fpm_service="php8.3-fpm", fpm_sock="/run/php/php8.3-fpm.sock")},
        nginx=config.NginxConfig(
            sites_available=str(temp_paths["nginx_av"]),
            sites_enabled=str(temp_paths["nginx_en"]),
        ),
        features=config.FeatureConfig(mysql_installed=True, certbot_installed=False),
    )
    config.write_server_config(server_config, path=temp_paths["etc_dir"] / "server.toml")

    site_root = temp_paths["www_root"] / "example.com"
    site_root.mkdir(parents=True, exist_ok=True)
    (site_root / ".git").mkdir()
    (site_root / ".env.production").write_text("APP_ENV=local\n")
    (site_root / "artisan").write_text("#!/usr/bin/env php\n")

    site_config = config.SiteConfig(
        domain="example.com",
        site_user="example",
        site_root=str(site_root),
        repo_ssh="git@github.com:org/repo.git",
        branch="main",
        with_www=True,
        email="",
        db_enabled=True,
        db_name="example_db",
        db_owner_user="example_owner",
        db_owner_password="secret",
    )
    config.write_site_config(site_config, path=temp_paths["sites_dir"] / "example.com.toml")

    result = CliRunner().invoke(app, ["site", "deploy", "example.com"])
    assert result.exit_code == 0

    env_path = site_root / ".env"
    assert env_path.exists()
    content = env_path.read_text()
    assert "APP_ENV=production" in content
    assert "DB_DATABASE=example_db" in content

    composer_calls = [cmd for cmd in calls if cmd[:2] == ["run_as_user", "example"]]
    assert any("composer" in str(call) for call in composer_calls)
    assert any("artisan" in str(call) for call in composer_calls)

    nginx_conf = temp_paths["nginx_av"] / "example.com.conf"
    assert nginx_conf.exists()
    nginx_contents = nginx_conf.read_text()
    assert "server_name example.com www.example.com;" in nginx_contents
    assert str(site_root / "public") in nginx_contents
