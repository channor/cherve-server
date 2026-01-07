from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import os

from cherve import paths

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for older Python
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass(frozen=True)
class ServerConfig:
    php_version: str
    php_fpm_service: str
    php_fpm_sock: str
    nginx_sites_available: str
    nginx_sites_enabled: str
    mysql_installed: bool
    certbot_installed: bool
    client_max_body_size: str = "20m"

    def to_dict(self) -> dict[str, object]:
        return {
            "php_version": self.php_version,
            "php_fpm_service": self.php_fpm_service,
            "php_fpm_sock": self.php_fpm_sock,
            "nginx_sites_available": self.nginx_sites_available,
            "nginx_sites_enabled": self.nginx_sites_enabled,
            "mysql_installed": self.mysql_installed,
            "certbot_installed": self.certbot_installed,
            "client_max_body_size": self.client_max_body_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ServerConfig":
        return cls(
            php_version=str(data["php_version"]),
            php_fpm_service=str(data["php_fpm_service"]),
            php_fpm_sock=str(data["php_fpm_sock"]),
            nginx_sites_available=str(data["nginx_sites_available"]),
            nginx_sites_enabled=str(data["nginx_sites_enabled"]),
            mysql_installed=bool(data.get("mysql_installed", False)),
            certbot_installed=bool(data.get("certbot_installed", False)),
            client_max_body_size=str(data.get("client_max_body_size", "20m")),
        )


@dataclass(frozen=True)
class SiteConfig:
    domain: str
    site_user: str
    site_root: str
    repo_ssh: str
    branch: str
    with_www: bool
    email: str
    db_enabled: bool
    db_host: str
    db_port: int
    db_name: str
    db_owner_user: str
    db_owner_password: str

    def to_dict(self) -> dict[str, object]:
        return {
            "domain": self.domain,
            "site_user": self.site_user,
            "site_root": self.site_root,
            "repo_ssh": self.repo_ssh,
            "branch": self.branch,
            "with_www": self.with_www,
            "email": self.email,
            "db_enabled": self.db_enabled,
            "db_host": self.db_host,
            "db_port": self.db_port,
            "db_name": self.db_name,
            "db_owner_user": self.db_owner_user,
            "db_owner_password": self.db_owner_password,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SiteConfig":
        return cls(
            domain=str(data["domain"]),
            site_user=str(data["site_user"]),
            site_root=str(data["site_root"]),
            repo_ssh=str(data["repo_ssh"]),
            branch=str(data["branch"]),
            with_www=bool(data.get("with_www", False)),
            email=str(data.get("email", "")),
            db_enabled=bool(data.get("db_enabled", False)),
            db_host=str(data.get("db_host", "127.0.0.1")),
            db_port=int(data.get("db_port", 3306)),
            db_name=str(data.get("db_name", "")),
            db_owner_user=str(data.get("db_owner_user", "")),
            db_owner_password=str(data.get("db_owner_password", "")),
        )


def read_server_config(path: Path = paths.SERVER_CONFIG_PATH) -> ServerConfig | None:
    if not path.exists():
        return None
    data = tomllib.loads(path.read_text())
    return ServerConfig.from_dict(data)


def read_site_config(path: Path) -> SiteConfig:
    data = tomllib.loads(path.read_text())
    return SiteConfig.from_dict(data)


def write_server_config(config: ServerConfig, path: Path = paths.SERVER_CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, _dump_toml(config.to_dict()))


def write_site_config(config: SiteConfig, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, _dump_toml(config.to_dict()))


def _dump_toml(data: dict[str, object]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def _toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    escaped = str(value).replace('"', '\\"')
    return f"\"{escaped}\""


def _atomic_write(path: Path, contents: str) -> None:
    with tempfile.NamedTemporaryFile("w", delete=False, dir=path.parent) as tmp:
        tmp.write(contents)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)
