from __future__ import annotations

from pathlib import Path
from typing import Iterable

MANAGED_KEYS = (
    "APP_ENV",
    "APP_DEBUG",
    "APP_URL",
    "DB_HOST",
    "DB_PORT",
    "DB_DATABASE",
    "DB_USERNAME",
    "DB_PASSWORD",
)


def select_env_template(site_root: Path) -> Path | None:
    for name in (".env.prod", ".env.production", ".env.example"):
        candidate = site_root / name
        if candidate.exists():
            return candidate
    return None


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        key, value = _parse_env_line(line)
        if key:
            values[key] = value
    return values


def update_env_contents(contents: str, updates: dict[str, str]) -> str:
    lines = contents.splitlines()
    managed = set(updates.keys())
    seen: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        key, _value = _parse_env_line(line)
        if key in updates:
            prefix = "export " if line.lstrip().startswith("export ") else ""
            new_lines.append(f"{prefix}{key}={updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)
    for key in managed - seen:
        new_lines.append(f"{key}={updates[key]}")
    return "\n".join(new_lines) + "\n"


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    contents = path.read_text()
    updated = update_env_contents(contents, updates)
    path.write_text(updated)


def ensure_keys(updates: dict[str, str], keys: Iterable[str] = MANAGED_KEYS) -> dict[str, str]:
    return {key: updates[key] for key in keys if key in updates}


def _parse_env_line(line: str) -> tuple[str | None, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None, ""
    if stripped.startswith("export "):
        stripped = stripped[len("export ") :]
    if "=" not in stripped:
        return None, ""
    key, value = stripped.split("=", 1)
    return key, value
