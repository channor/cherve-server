from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
from typing import Iterable, Sequence


def run(
    argv: Sequence[str],
    *,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        check=check,
        capture_output=capture,
        text=True,
        env=env,
        cwd=str(cwd) if cwd else None,
    )


def run_as_user(user: str, argv_or_bash: Iterable[str] | str) -> subprocess.CompletedProcess[str]:
    if isinstance(argv_or_bash, str):
        cmd = ["sudo", "-iu", user, "bash", "-lc", argv_or_bash]
        return run(cmd)
    cmd = ["sudo", "-iu", user] + list(argv_or_bash)
    return run(cmd)


def require_root() -> None:
    if os.geteuid() != 0:
        raise SystemExit("cherve must be run as root (sudo).")


def require_cmd(command: str) -> None:
    if shutil.which(command) is None:
        raise SystemExit(f"Required command not found: {command}")


def is_installed_apt(pkg: str) -> bool:
    result = run(["dpkg", "-s", pkg], check=False, capture=True)
    return result.returncode == 0


def service_enabled(name: str) -> bool:
    result = run(["systemctl", "is-enabled", name], check=False, capture=True)
    return result.returncode == 0


def service_running(name: str) -> bool:
    result = run(["systemctl", "is-active", name], check=False, capture=True)
    return result.returncode == 0


def ensure_dir(path: Path, mode: int | None = None) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if mode is not None:
        path.chmod(mode)
