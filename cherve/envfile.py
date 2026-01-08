from __future__ import annotations

from pathlib import Path


ENV_TEMPLATE_NAMES = [".env.prod", ".env.production", ".env.example"]


def select_env_template(site_root: Path) -> Path | None:
    for name in ENV_TEMPLATE_NAMES:
        candidate = site_root / name
        if candidate.exists():
            return candidate
    return None


def update_env_file(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text().splitlines()
    seen: set[str] = set()
    output: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            output.append(line)
            continue

        export_prefix = ""
        key_part = stripped
        if stripped.startswith("export "):
            export_prefix = "export "
            key_part = stripped[len("export ") :]

        if "=" not in key_part:
            output.append(line)
            continue

        key, _ = key_part.split("=", 1)
        if key in updates:
            output.append(f"{export_prefix}{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(line)

    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")

    path.write_text("\n".join(output) + "\n")


def has_env_key(path: Path, key: str) -> bool:
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[len("export ") :]
        if "=" not in stripped:
            continue
        current, value = stripped.split("=", 1)
        if current == key:
            return bool(value.strip())
    return False
