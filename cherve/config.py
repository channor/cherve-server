from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py311+
    import tomli as tomllib

from cherve import paths


@dataclass(frozen=True)
class ServerConfig:
    php_version: str
    fpm_service: str
    fpm_sock: str
    nginx_sites_available: str
    nginx_sites_enabled: str
    mysql_installed: bool
    pqsql_installed: bool
    sqlite_installed: bool
    certbot_installed: bool


@dataclass(frozen=True)
class DomainConfig:
    name: str
    with_www: bool
    tls_enabled: bool
    ssl_certificate: str
    ssl_certificate_key: str


@dataclass(frozen=True)
class SiteConfig:
    site_name: str
    site_user: str
    site_root: str
    site_app_root: str
    site_www_root: str
    site_landing_root: str
    repo_ssh: str
    branch: str
    email: str
    mode: str
    domains: list[DomainConfig]
    db_service: str | None
    db_name: str | None
    db_owner_user: str | None


def _serialize_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return f"[{', '.join(_serialize_value(item) for item in value)}]"
    if value is None:
        return '""'
    return f'"{value}"'


def _toml_dumps(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            for entry in value:
                lines.append(f"[[{key}]]")
                for nested_key, nested_value in entry.items():
                    lines.append(f"{nested_key} = {_serialize_value(nested_value)}")
                lines.append("")
            continue
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for nested_key, nested_value in value.items():
                lines.append(f"{nested_key} = {_serialize_value(nested_value)}")
            lines.append("")
        else:
            lines.append(f"{key} = {_serialize_value(value)}")
    return "\n".join(lines).rstrip() + "\n"


def _atomic_write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(contents, encoding="utf-8")
    tmp_path.replace(path)


def write_server_config(config: ServerConfig, path: Path | None = None) -> None:
    if path is None:
        path = paths.SERVER_CONFIG_PATH
    data = {
        "php": {
            "version": config.php_version,
            "fpm_service": config.fpm_service,
            "fpm_sock": config.fpm_sock,
        },
        "nginx": {
            "sites_available": config.nginx_sites_available,
            "sites_enabled": config.nginx_sites_enabled,
        },
        "features": {
            "mysql_installed": config.mysql_installed,
            "pqsql_installed": config.pqsql_installed,
            "sqlite_installed": config.sqlite_installed,
            "certbot_installed": config.certbot_installed,
        },
    }
    _atomic_write(path, _toml_dumps(data))


def read_server_config(path: Path | None = None) -> ServerConfig:
    if path is None:
        path = paths.SERVER_CONFIG_PATH
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    return ServerConfig(
        php_version=raw["php"]["version"],
        fpm_service=raw["php"]["fpm_service"],
        fpm_sock=raw["php"]["fpm_sock"],
        nginx_sites_available=raw["nginx"]["sites_available"],
        nginx_sites_enabled=raw["nginx"]["sites_enabled"],
        mysql_installed=raw["features"]["mysql_installed"],
        pqsql_installed=raw["features"]["pqsql_installed"],
        sqlite_installed=raw["features"]["sqlite_installed"],
        certbot_installed=raw["features"]["certbot_installed"],
    )


def write_site_config(config: SiteConfig, path: Path | None = None) -> None:
    if path is None:
        path = paths.SITES_DIR / f"{config.site_name}.toml"
    data = asdict(config)
    domains = data.pop("domains")
    ordered = {**data, "domains": domains}
    _atomic_write(path, _toml_dumps(ordered))


def _domain_from_legacy(raw: dict[str, Any]) -> list[DomainConfig]:
    if "domains" in raw:
        domains_raw = raw["domains"]
        if isinstance(domains_raw, list):
            domains: list[DomainConfig] = []
            for entry in domains_raw:
                if isinstance(entry, str):
                    domains.append(
                        DomainConfig(
                            name=entry,
                            with_www=False,
                            tls_enabled=False,
                            ssl_certificate="",
                            ssl_certificate_key="",
                        )
                    )
                elif isinstance(entry, dict):
                    domains.append(
                        DomainConfig(
                            name=entry.get("name", entry.get("domain", "")),
                            with_www=entry.get("with_www", False),
                            tls_enabled=entry.get("tls_enabled", False),
                            ssl_certificate=entry.get("ssl_certificate", ""),
                            ssl_certificate_key=entry.get("ssl_certificate_key", ""),
                        )
                    )
            return [domain for domain in domains if domain.name]
    if "domain" in raw:
        tls_raw = raw.get("tls", {})
        return [
            DomainConfig(
                name=raw["domain"],
                with_www=raw.get("with_www", False),
                tls_enabled=tls_raw.get("enabled", False),
                ssl_certificate=tls_raw.get("ssl_certificate", ""),
                ssl_certificate_key=tls_raw.get("ssl_certificate_key", ""),
            )
        ]
    return []


def read_site_config(site_name: str, path: Path | None = None) -> SiteConfig:
    if path is None:
        path = paths.SITES_DIR / f"{site_name}.toml"
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    resolved_site_name = raw.get("site_name") or raw.get("site_user") or raw.get("domain") or site_name
    site_root = raw.get("site_root") or str(paths.WWW_ROOT / resolved_site_name)
    app_root = raw.get("site_app_root") or str(Path(site_root) / "_cherve" / "app")
    landing_root = raw.get("site_landing_root") or str(Path(site_root) / "_cherve" / "landing")
    www_root = raw.get("site_www_root") or str(Path(app_root) / "public")
    domains = _domain_from_legacy(raw)
    return SiteConfig(
        site_name=resolved_site_name,
        site_user=raw["site_user"],
        site_root=site_root,
        site_app_root=app_root,
        site_www_root=www_root,
        site_landing_root=landing_root,
        repo_ssh=raw.get("repo_ssh", ""),
        branch=raw.get("branch", "main"),
        email=raw.get("email", ""),
        mode=raw.get("mode", "landing"),
        domains=domains,
        db_service=raw.get("db_service"),
        db_name=raw.get("db_name"),
        db_owner_user=raw.get("db_owner_user"),
    )
