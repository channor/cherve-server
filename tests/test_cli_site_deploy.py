from pathlib import Path

from typer.testing import CliRunner

from cherve import cli, config, envfile, paths, system


def test_site_deploy_creates_env_and_runs_commands(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    calls = []

    def fake_require_root() -> None:
        return None

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        class Result:
            returncode = 0
        return Result()

    def fake_run_as_user(user, cmd):
        calls.append(["run_as_user", user, cmd])
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(system, "require_root", fake_require_root)
    monkeypatch.setattr(system, "run", fake_run)
    monkeypatch.setattr(system, "run_as_user", fake_run_as_user)

    site_root = tmp_path / "www" / "example.com"
    site_root.mkdir(parents=True)
    (site_root / ".env.example").write_text("APP_ENV=local\n")
    (site_root / "artisan").write_text("#!/usr/bin/env php\n")

    site_cfg = config.SiteConfig(
        domain="example.com",
        site_user="example",
        site_root=str(site_root),
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
    server_cfg = config.ServerConfig(
        php_version="8.3",
        php_fpm_service="php8.3-fpm",
        php_fpm_sock="/run/php/php8.3-fpm.sock",
        nginx_sites_available=str(tmp_path / "nginx" / "sites-available"),
        nginx_sites_enabled=str(tmp_path / "nginx" / "sites-enabled"),
        mysql_installed=True,
        certbot_installed=False,
        client_max_body_size="20M",
    )

    monkeypatch.setattr(config, "read_server_config", lambda: server_cfg)
    monkeypatch.setattr(config, "read_site_config", lambda _path: site_cfg)
    monkeypatch.setattr(paths, "SITES_DIR", tmp_path / "etc" / "sites.d")

    site_cfg_path = paths.SITES_DIR / "example.com.toml"
    site_cfg_path.parent.mkdir(parents=True, exist_ok=True)
    site_cfg_path.write_text("domain = \"example.com\"\n")

    result = runner.invoke(cli.app, ["site", "deploy", "example.com"], input="n\n")
    assert result.exit_code == 0

    env_path = site_root / ".env"
    assert env_path.exists()
    values = envfile.load_env(env_path)
    assert values["APP_ENV"] == "production"
    assert values["APP_DEBUG"] == "false"
    assert values["DB_DATABASE"] == "example_db"

    run_as_user_calls = [call for call in calls if isinstance(call, list) and call[:1] == ["run_as_user"]]
    assert any("composer install" in call[2] for call in run_as_user_calls)
    assert any("php artisan migrate" in call[2] for call in run_as_user_calls)
