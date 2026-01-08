from subprocess import CompletedProcess

from typer.testing import CliRunner

from cherve.cli import app
from cherve import server as server_module
from cherve import system
from cherve import config


def test_server_install_skips_installed_packages(monkeypatch, temp_paths):
    calls = []

    def fake_run(argv, check=True, capture=False, env=None, cwd=None):
        calls.append(list(argv))
        stdout = ""
        if argv[:2] == ["ufw", "status"]:
            stdout = "Status: inactive"
        return CompletedProcess(argv, 0, stdout=stdout, stderr="")

    def fake_is_installed(pkg):
        return pkg == "git"

    monkeypatch.setattr(system, "run", fake_run)
    monkeypatch.setattr(system, "require_root", lambda: None)
    monkeypatch.setattr(system, "require_cmd", lambda cmd: None)
    monkeypatch.setattr(system, "is_installed_apt", fake_is_installed)
    monkeypatch.setattr(server_module, "_ensure_nginx_override", lambda: None)
    monkeypatch.setattr(server_module, "_ensure_nginx_server_tokens", lambda: None)
    monkeypatch.setattr(server_module, "_copy_php_templates", lambda version: None)
    monkeypatch.setattr(server_module, "_ensure_fail2ban", lambda: None)
    monkeypatch.setattr(server_module, "_ensure_clamav", lambda: None)

    result = CliRunner().invoke(app, ["server", "install"])
    assert result.exit_code == 0

    install_calls = [cmd for cmd in calls if cmd[:3] == ["apt-get", "install", "-y"]]
    assert install_calls
    assert not any("git" in call for call in install_calls)

    server_config = config.read_server_config(path=temp_paths["etc_dir"] / "server.toml")
    assert server_config is not None
    assert server_config.default_php_version == "8.3"
