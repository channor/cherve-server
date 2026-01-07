from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Callable, Iterable, Optional

import typer

from cherve import config, paths, system


@dataclass(frozen=True)
class PackageChoice:
    name: str
    packages: tuple[str, ...]
    default: bool | None
    service: str | None = None
    post_install: Optional[Callable[[str], None]] = None  # receives php_version


ALWAYS_INSTALL: tuple[PackageChoice, ...] = (
    PackageChoice("software-properties-common", ("software-properties-common",), None),
    PackageChoice("curl", ("curl",), None),
    PackageChoice("wget", ("wget",), None),
    PackageChoice("nano", ("nano",), None),
    PackageChoice("zip", ("zip",), None),
    PackageChoice("unzip", ("unzip",), None),
    PackageChoice("openssl", ("openssl",), None),
    PackageChoice("expect", ("expect",), None),
    PackageChoice("ca-certificates", ("ca-certificates",), None),
    PackageChoice("gnupg", ("gnupg",), None),
    PackageChoice("lsb-release", ("lsb-release",), None),
    PackageChoice("jq", ("jq",), None),
    PackageChoice("bc", ("bc",), None),
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
        # Keep PHP-specific follow-ups near the PHP choice
        post_install=lambda php_version: _apply_php_fpm_ini_templates(php_version),
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

    for name in ("99-php.ini", "99-opcache.ini"):
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


def _missing_packages(packages: tuple[str, ...]) -> list[str]:
    missing = []
    for pkg in packages:
        typer.echo(f"Checking package {pkg}...")
        if not system.is_installed_apt(pkg):
            missing.append(pkg)
    return missing


def _install_packages(packages: list[str]) -> None:
    if not packages:
        return
    typer.echo("Updating package lists...")
    system.run(["apt-get", "update"])
    typer.echo(f"Installing package(s): {', '.join(packages)}")
    system.run(["apt-get", "install", "-y", *packages])


def _enable_services(services: list[str]) -> None:
    if services:
        typer.echo("Restarting service(s)...")
    for service in services:
        if not system.service_enabled(service):
            system.run(["systemctl", "enable", "--now", service], check=False)
        else:
            system.run(["systemctl", "restart", service], check=False)


def _write_server_config(*, php_version: str) -> None:
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


def _collect_plan(
    php_version: str,
    *,
    interactive: bool,
) -> tuple[list[str], list[str], list[Callable[[str], None]]]:
    to_install: list[str] = []
    enabled_services: list[str] = []
    post_steps: list[Callable[[str], None]] = []

    for choice in ALWAYS_INSTALL:
        to_install.extend(_missing_packages(choice.packages))
        if choice.service:
            enabled_services.append(choice.service)
        if choice.post_install:
            post_steps.append(choice.post_install)

    for choice in OPTIONAL_INSTALL:
        default = True if choice.default is None else choice.default
        if interactive:
            confirmed = typer.confirm(f"Install {choice.name}?", default=default)
        else:
            confirmed = default
        if confirmed:
            to_install.extend(_missing_packages(choice.packages))
            if choice.service:
                enabled_services.append(choice.service)
            if choice.post_install:
                post_steps.append(choice.post_install)

    return (
        _dedupe_keep_order(to_install),
        _dedupe_keep_order(enabled_services),
        post_steps,
    )


def install(*, interactive: bool = False) -> None:
    system.require_root()

    php_version = "8.3"

    to_install, enabled_services, post_steps = _collect_plan(php_version, interactive=interactive)

    _install_packages(to_install)
    _enable_services(enabled_services)

    for step in post_steps:
        try:
            step(php_version)
        except Exception as e:
            typer.echo(f"Warning: post-install step failed: {e}")

    _write_server_config(php_version=php_version)
    typer.echo("Server install complete. Config written to /etc/cherve/server.toml")
