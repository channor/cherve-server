from pathlib import Path
import subprocess

from typer.testing import CliRunner

from cherve import config, envfile, paths
from cherve.cli import app


def test_site_deploy_creates_env_and_runs_commands(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("cherve.system.require_root", lambda: None)
    run_calls: list[list[str]] = []
    run_as_user_calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        run_calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    def fake_run_as_user(user, argv_or_bash, **kwargs):
        argv = argv_or_bash if isinstance(argv_or_bash, (list, tuple)) else ["bash", "-c", argv_or_bash]
        run_as_user_calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr("cherve.system.run", fake_run)
    monkeypatch.setattr("cherve.system.run_as_user", fake_run_as_user)
    monkeypatch.setattr(paths, "SITES_DIR", tmp_path / "etc" / "sites.d")
    monkeypatch.setattr(paths, "HOME_ROOT", tmp_path / "home")

    site_root = tmp_path / "site" / "_cherve" / "app"
    site_root.mkdir(parents=True, exist_ok=True)
    (site_root / ".git").mkdir()
    (site_root / ".env.example").write_text("APP_NAME=Test\n", encoding="utf-8")
    (site_root / "composer.json").write_text("{}", encoding="utf-8")
    (site_root / "artisan").write_text("#!/usr/bin/env php\n", encoding="utf-8")

    site_config = config.SiteConfig(
        domain="example.com",
        site_user="example",
        site_root=str(tmp_path / "site"),
        site_app_root=str(site_root),
        site_www_root=str(site_root / "public"),
        site_landing_root=str(tmp_path / "site" / "_cherve" / "landing"),
        repo_ssh="git@github.com:ORG/REPO.git",
        branch="main",
        with_www=False,
        email="",
        mode="landing",
        tls_enabled=False,
        ssl_certificate="",
        ssl_certificate_key="",
        db_service="mysql",
        db_name="example_db",
        db_owner_user="example_user",
    )
    paths.SITES_DIR.mkdir(parents=True, exist_ok=True)
    config.write_site_config(site_config, path=paths.SITES_DIR / "example.com.toml")

    result = CliRunner().invoke(app, ["site", "deploy", "example.com"], input="secret-password\n")
    assert result.exit_code == 0

    env_path = site_root / ".env"
    assert env_path.exists()
    env_values = envfile.parse_env(env_path)
    assert env_values["APP_ENV"] == "production"
    assert env_values["DB_DATABASE"] == "example_db"
    assert env_values["DB_PASSWORD"] == "secret-password"
    assert any(cmd[:3] == ["git", "-C", str(site_root)] for cmd in run_as_user_calls)
    assert any(
        cmd
        == [
            "composer",
            "--working-dir",
            str(site_root),
            "install",
            "--no-dev",
            "--optimize-autoloader",
        ]
        for cmd in run_as_user_calls
    )
    assert any(cmd[:3] == ["php", "artisan", "key:generate"] for cmd in run_as_user_calls)
    assert not any(cmd[0] in {"nginx", "certbot"} for cmd in run_calls)
