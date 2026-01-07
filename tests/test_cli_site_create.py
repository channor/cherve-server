from pathlib import Path

from typer.testing import CliRunner

from cherve import cli, config, paths, site, system


def test_site_create_writes_config_and_prints_key(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    calls = []
    written = {}

    def fake_require_root() -> None:
        return None

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        class Result:
            returncode = 0
        return Result()

    def fake_run_as_user(_user, _cmd):
        calls.append(["run_as_user", _user, _cmd])
        class Result:
            returncode = 0
        return Result()

    def fake_write(cfg: config.SiteConfig, path: Path) -> None:
        written["cfg"] = cfg
        written["path"] = path

    monkeypatch.setattr(system, "require_root", fake_require_root)
    monkeypatch.setattr(system, "run", fake_run)
    monkeypatch.setattr(system, "run_as_user", fake_run_as_user)
    monkeypatch.setattr(config, "write_site_config", fake_write)
    monkeypatch.setattr(site, "_random_suffix", lambda: "abc123")
    monkeypatch.setattr(site, "_random_password", lambda: "secret-pass")
    monkeypatch.setattr(site, "_user_exists", lambda _user: False)

    fake_server_cfg = config.ServerConfig(
        php_version="8.3",
        php_fpm_service="php8.3-fpm",
        php_fpm_sock="/run/php/php8.3-fpm.sock",
        nginx_sites_available="/etc/nginx/sites-available",
        nginx_sites_enabled="/etc/nginx/sites-enabled",
        mysql_installed=True,
        certbot_installed=False,
    )
    monkeypatch.setattr(config, "read_server_config", lambda: fake_server_cfg)

    monkeypatch.setattr(paths, "ETC_DIR", tmp_path / "etc")
    monkeypatch.setattr(paths, "SITES_DIR", tmp_path / "etc" / "sites.d")
    monkeypatch.setattr(paths, "WWW_ROOT", tmp_path / "www")
    monkeypatch.setattr(paths, "HOME_ROOT", tmp_path / "home")

    key_path = paths.HOME_ROOT / "microsoft" / ".ssh" / "id_cherve_deploy.pub"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text("ssh-ed25519 AAAATEST")

    inputs = "\n".join(
        [
            "microsoft",
            "microsoft.com",
            "",
            "git@github.com:org/repo.git",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
    )

    result = runner.invoke(cli.app, ["site", "create"], input=inputs + "\n")
    assert result.exit_code == 0
    assert "ssh-ed25519 AAAATEST" in result.output
    assert written["cfg"].domain == "microsoft.com"
    assert written["cfg"].db_enabled is True
    assert any("mysql" in call for call in calls if isinstance(call, list))
