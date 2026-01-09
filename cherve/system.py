from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from typing import Sequence

import typer


def _tail_stderr(stderr: str | None, limit: int = 50) -> str:
    if not stderr:
        return ""
    lines = stderr.splitlines()
    return "\n".join(lines[-limit:])


def run(
    argv: Sequence[str],
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    resolved_env = None
    if env is not None:
        resolved_env = os.environ.copy()
        resolved_env.update(env)
    kwargs = {
        "check": False,
        "text": True,
        "env": resolved_env,
        "cwd": cwd,
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
    result = subprocess.run(list(argv), **kwargs)
    if check and result.returncode != 0:
        if capture:
            typer.echo("Command failed: " + " ".join(argv), err=True)
            stderr_tail = _tail_stderr(result.stderr)
            if stderr_tail:
                typer.echo(stderr_tail, err=True)
        raise subprocess.CalledProcessError(
            result.returncode,
            list(argv),
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def run_as_user(
    user: str,
    argv_or_bash: Sequence[str] | str,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if isinstance(argv_or_bash, str):
        if env:
            env_prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
            command = f"{env_prefix} {argv_or_bash}"
        else:
            command = argv_or_bash
        argv = ["sudo", "-u", user, "--", "bash", "-c", command]
    else:
        if env:
            env_assignments = [f"{key}={value}" for key, value in env.items()]
            argv = ["sudo", "-u", user, "--", "env", *env_assignments, *argv_or_bash]
        else:
            argv = ["sudo", "-u", user, "--", *argv_or_bash]
    return run(argv, check=check, capture=capture, cwd=cwd)


def _is_root() -> bool:
    return os.geteuid() == 0


def require_root() -> None:
    if not _is_root():
        raise PermissionError("cherve must be run as root (sudo).")


def require_cmd(cmd: str) -> None:
    if shutil.which(cmd) is None:
        raise RuntimeError(f"Required command not found: {cmd}")


def is_installed_apt(pkg: str) -> bool:
    result = subprocess.run(["dpkg", "-s", pkg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def service_enabled(name: str) -> bool:
    result = subprocess.run(["systemctl", "is-enabled", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def service_running(name: str) -> bool:
    result = subprocess.run(["systemctl", "is-active", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def user_exists(username: str) -> bool:
    result = subprocess.run(["id", "-u", username], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0
