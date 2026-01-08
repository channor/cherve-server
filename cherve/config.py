from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import os

import tomllib

from cherve import paths


@dataclass(frozen=True)
class PHPConfig:
    fpm_service: str
    fpm_sock: str


@dataclass(frozen=True)
class NginxConfig:
    sites_available: str
    sites_enabled: str


@dataclass(frozen=True)
class FeatureConfig:
    mysql_installed: bool
    certbot_installed: bool


@dataclass(frozen=True)
class ServerConfig:
    default_php_version: str
    php: dict[str, PHPConfig]
    nginx: NginxConfig
    features: FeatureConfig


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
    db_name: str | None = None
    db_owner_user: str | None = None
    db_owner_password: str | None = None
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    extra_db_user: str | None = None
    extra_db_password: str | None = None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent)) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def _toml_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _dump_server_config(config: ServerConfig) -> str:
    lines = [f'default_php_version = "{_toml_escape(config.default_php_version)}"', ""]
    for version, php in config.php.items():
        lines.append(f'[php."{_toml_escape(version)}"]')
        lines.append(f'fpm_service = "{_toml_escape(php.fpm_service)}"')
        lines.append(f'fpm_sock = "{_toml_escape(php.fpm_sock)}"')
        lines.append("")
    lines.append("[nginx]")
    lines.append(f'sites_available = "{_toml_escape(config.nginx.sites_available)}"')
    lines.append(f'sites_enabled = "{_toml_escape(config.nginx.sites_enabled)}"')
    lines.append("")
    lines.append("[features]")
    lines.append(f"mysql_installed = {str(config.features.mysql_installed).lower()}")
    lines.append(f"certbot_installed = {str(config.features.certbot_installed).lower()}")
    lines.append("")
    return "\n".join(lines)


def _dump_site_config(config: SiteConfig) -> str:
    lines = [
        f'domain = "{_toml_escape(config.domain)}"',
        f'site_user = "{_toml_escape(config.site_user)}"',
        f'site_root = "{_toml_escape(config.site_root)}"',
        f'repo_ssh = "{_toml_escape(config.repo_ssh)}"',
        f'branch = "{_toml_escape(config.branch)}"',
        f"with_www = {str(config.with_www).lower()}",
        f'email = "{_toml_escape(config.email)}"',
        f"db_enabled = {str(config.db_enabled).lower()}",
    ]
    if config.db_name is not None:
        lines.append(f'db_name = "{_toml_escape(config.db_name)}"')
    if config.db_owner_user is not None:
        lines.append(f'db_owner_user = "{_toml_escape(config.db_owner_user)}"')
    if config.db_owner_password is not None:
        lines.append(f'db_owner_password = "{_toml_escape(config.db_owner_password)}"')
    lines.append(f'db_host = "{_toml_escape(config.db_host)}"')
    lines.append(f"db_port = {config.db_port}")
    if config.extra_db_user is not None:
        lines.append(f'extra_db_user = "{_toml_escape(config.extra_db_user)}"')
    if config.extra_db_password is not None:
        lines.append(f'extra_db_password = "{_toml_escape(config.extra_db_password)}"')
    lines.append("")
    return "\n".join(lines)


def write_server_config(config: ServerConfig, path: Path | None = None) -> None:
    target = path or paths.SERVER_CONFIG_PATH
    _atomic_write(target, _dump_server_config(config))


def write_site_config(config: SiteConfig, path: Path | None = None) -> None:
    if path is None:
        path = paths.SITES_DIR / f"{config.domain}.toml"
    _atomic_write(path, _dump_site_config(config))


def read_server_config(path: Path | None = None) -> ServerConfig | None:
    target = path or paths.SERVER_CONFIG_PATH
    if not target.exists():
        return None
    data = tomllib.loads(target.read_text())
    php_versions = {
        version: PHPConfig(
            fpm_service=details["fpm_service"],
            fpm_sock=details["fpm_sock"],
        )
        for version, details in data.get("php", {}).items()
    }
    nginx_data = data.get("nginx", {})
    features = data.get("features", {})
    return ServerConfig(
        default_php_version=data["default_php_version"],
        php=php_versions,
        nginx=NginxConfig(
            sites_available=nginx_data["sites_available"],
            sites_enabled=nginx_data["sites_enabled"],
        ),
        features=FeatureConfig(
            mysql_installed=features.get("mysql_installed", False),
            certbot_installed=features.get("certbot_installed", False),
        ),
    )


def read_site_config(domain: str | None = None, path: Path | None = None) -> SiteConfig:
    if path is None:
        if domain is None:
            raise ValueError("domain or path must be provided")
        path = paths.SITES_DIR / f"{domain}.toml"
    data = tomllib.loads(path.read_text())
    return SiteConfig(
        domain=data["domain"],
        site_user=data["site_user"],
        site_root=data["site_root"],
        repo_ssh=data["repo_ssh"],
        branch=data.get("branch", "main"),
        with_www=data.get("with_www", False),
        email=data.get("email", ""),
        db_enabled=data.get("db_enabled", False),
        db_name=data.get("db_name"),
        db_owner_user=data.get("db_owner_user"),
        db_owner_password=data.get("db_owner_password"),
        db_host=data.get("db_host", "127.0.0.1"),
        db_port=int(data.get("db_port", 3306)),
        extra_db_user=data.get("extra_db_user"),
        extra_db_password=data.get("extra_db_password"),
    )
