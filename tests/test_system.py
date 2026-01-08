import sys

from cherve import system


def test_run_merges_env(monkeypatch):
    monkeypatch.setenv("CHERVE_BASE", "base")
    result = system.run(
        [
            sys.executable,
            "-c",
            "import os; print(os.environ.get('CHERVE_BASE'), os.environ.get('CHERVE_OVERRIDE'))",
        ],
        capture=True,
        env={"CHERVE_OVERRIDE": "override"},
    )
    assert result.stdout.strip() == "base override"
