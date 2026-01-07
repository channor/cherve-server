from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable

import typer

from cherve import config, paths, system


@dataclass(frozen=True)
class PackageChoice:
    name: str
    packages: tuple[str, ...]
    default: bool | None
    service: str | None = None


ALWAYS_INSTALL: tuple[PackageChoice, ...] = (
    PackageChoice("git", ("git",), None),
    PackageChoice("ufw", ("ufw",), None),
    PackageChoice("nginx", ("nginx",), None, service="nginx"),
    PackageChoice(
        "php8.3",
        (
            "php8.3-fpm",
            "php8.3-cli",
            "php8.3-mysql",
            "php8.3-xml",
            "php8.3-mbstring",
            "php8.3-curl",
            "php8.3-zip",
        ),
        None,
        service="php8.3-fpm",
    ),
    PackageChoice("composer", ("composer",), None),
)

OPTIONAL_INSTALL: tuple[PackageChoice, ...] = (
    PackageChoice("fail2ban", ("fail2ban",), True, service="fail2ban"),
    PackageChoice("clamav", ("clamav", "clamav-freshclam"), True, service="clamav-freshclam"),
    PackageChoice("mysql", ("mysql-server",), True, service="mysql"),
    PackageChoice("supervisor", ("supervisor",), True, service="supervisor"),
    PackageChoice("certbot", ("certbot", "python3-certbot-nginx"), True),
    PackageChoice("npm", ("npm",), False),
)


def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _apply_php_fpm_ini_templates(php_version: str) -> None:
    """
    Copy packaged ini templates into /etc/php/<ver>/fpm/conf.d.
    Non-fatal: warns instead of crashing.
    """
    php_conf_dir = Path(f"/etc/php/{php_version}/fpm/conf.d")
    if not php_conf_dir.exists():
        typer.echo(f"Warning: PHP conf.d directory not found at {php_conf_dir}")
        return

    template_names = ("99-php.ini", "99-opcache.ini")

    # Templates are expected at: cherve/templates/<name>
    # and included via pyproject.toml [tool.setuptools.package-data].
    for name in template_names:
        try:
            src = resources.files("cherve").joinpath("templates", name)
            if not src.is_file():
                typer.echo(f"Warning: missing template file in package: cherve/templates/{name}")
                continue

            dst = php_conf_dir / name
            with src.open("rb") as fsrc, open(dst, "wb") as fdst:
                fdst.write(fsrc.read())
        except Exception as e:
            typer.echo(f"Warning: failed applying PHP ini template {name}: {e}")


def install() -> None:
    system.require_root()

    php_version = "8.3"

    to_install: list[str] = []
    enabled_services: list[str] = []

    # Always-install set
    for choice in ALWAYS_INSTALL:
        missing = [pkg for pkg in choice.packages if not system.is_installed_apt(pkg)]
        to_install.extend(missing)
        if choice.service:
            enabled_services.append(choice.service)

    # Optional set
    for choice in OPTIONAL_INSTALL:
        default = choice.default if choice.default is not None else True
        if typer.confirm(f"Install {choice.name}?", default=default):
            missing = [pkg for pkg in choice.packages if not system.is_installed_apt(pkg)]
            to_install.extend(missing)
            if choice.service:
                enabled_services.append(choice.service)

    to_install = _dedupe_keep_order(to_install)
    enabled_services = _dedupe_keep_order(enabled_services)

    if to_install:
        system.run(["apt-get", "update"])
        system.run(["apt-get", "install", "-y", *to_install])

    # Enable services (non-fatal if a service doesn't exist or can't be enabled)
    for service in enabled_services:
        if not system.service_enabled(service):
            system.run(["systemctl", "enable", "--now", service], check=False)

    # Apply PHP-FPM ini overrides (non-fatal)
    _apply_php_fpm_ini_templates(php_version)

    # Persist server config
    server_config = config.ServerConfig(
        php_version=php_version,
        php_fpm_service=f"php{php_version}-fpm",
        php_fpm_sock=f"/run/php/php{php_version}-fpm.sock",
        nginx_sites_available=str(paths.NGINX_SITES_AVAILABLE),
        nginx_sites_enabled=str(paths.NGINX_SITES_ENABLED),
        mysql_installed=system.is_installed_apt("mysql-server"),
        certbot_installed=system.is_installed_apt("certbot"),
        client_max_body_size="20M",
    )
    config.write_server_config(server_config)
    typer.echo("Server install complete. Config written to /etc/cherve/server.toml")
