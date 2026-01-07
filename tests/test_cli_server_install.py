from typer.testing import CliRunner

from cherve import cli, config, server, system


def test_server_install_skips_installed_packages(monkeypatch) -> None:
    runner = CliRunner()
    calls = []
    written = {}

    def fake_require_root() -> None:
        return None

    def fake_is_installed(pkg: str) -> bool:
        return pkg == "git"

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        class Result:
            returncode = 0
        return Result()

    def fake_write(cfg: config.ServerConfig) -> None:
        written["cfg"] = cfg

    monkeypatch.setattr(system, "require_root", fake_require_root)
    monkeypatch.setattr(system, "is_installed_apt", fake_is_installed)
    monkeypatch.setattr(system, "run", fake_run)
    monkeypatch.setattr(system, "service_enabled", lambda _name: False)
    monkeypatch.setattr(config, "write_server_config", fake_write)

    prompt_inputs = "\n" * 7
    result = runner.invoke(cli.app, ["server", "install"], input=prompt_inputs)

    assert result.exit_code == 0
    install_calls = [call for call in calls if call[:3] == ["apt-get", "install", "-y"]]
    assert install_calls
    assert written["cfg"].mysql_installed is False or isinstance(written["cfg"].mysql_installed, bool)
    assert all("git" not in call for call in install_calls)
