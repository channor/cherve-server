from subprocess import CompletedProcess

from typer.testing import CliRunner

from cherve.cli import app
from cherve import config
from cherve import paths
from cherve import system


def test_site_create_writes_config_and_db(monkeypatch, temp_paths, tmp_path):
    calls = []

    def fake_run(argv, check=True, capture=False, env=None, cwd=None):
        calls.append(list(argv))
        if argv[:2] == ["id", "-u"]:
            return CompletedProcess(argv, 1, stdout="", stderr="")
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

    user_home = temp_paths["home_root"] / "microsoft" / ".ssh"
    user_home.mkdir(parents=True, exist_ok=True)
    (user_home / "id_cherve_deploy").write_text("key")
    (user_home / "id_cherve_deploy.pub").write_text("ssh-ed25519 AAAA")
    (user_home / "known_hosts").write_text("github.com")

    input_data = "\n".join(
        [
            "microsoft",
            "microsoft.com",
            "ops@example.com",
            "git@github.com:org/repo.git",
            "main",
            "y",
            "y",
            "microsoft_db",
            "y",
            "microsoft_db_owner",
            "supersecret",
            "supersecret",
            "n",
        ]
    )
    result = CliRunner().invoke(app, ["site", "create"], input=input_data)
    assert result.exit_code == 0
    assert "ssh-ed25519" in result.output

    site_config = config.read_site_config(path=temp_paths["sites_dir"] / "microsoft.com.toml")
    assert site_config.domain == "microsoft.com"
    assert site_config.db_enabled is True
    assert site_config.db_name == "microsoft_db"

    mysql_calls = [cmd for cmd in calls if cmd and cmd[0] == "mysql"]
    assert mysql_calls
