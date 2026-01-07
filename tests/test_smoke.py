from typer.testing import CliRunner
from cherve.cli import app

def test_cli_help():
    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "cherve" in r.output.lower() or "usage" in r.output.lower()
