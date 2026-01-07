from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import typer

from cherve import config, paths, system


@dataclass(frozen=True)
class PackageChoice:
    name: str
    packages: tuple[str, ...]
    default: bool | None
    service: str | None = None


ALWAYS_INSTALL = (
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

OPTIONAL_INSTALL = (
    PackageChoice("fail2ban", ("fail2ban",), True, service="fail2ban"),
    PackageChoice("clamav", ("clamav", "clamav-freshclam"), True, service="clamav-freshclam"),
    PackageChoice("mysql", ("mysql-server",), True, service="mysql"),
    PackageChoice("supervisor", ("supervisor",), True, service="supervisor"),
    PackageChoice("certbot", ("certbot", "python3-certbot-nginx"), True),
    PackageChoice("awscli", ("awscli",), True),
    PackageChoice("npm", ("npm",), False),
)


def install() -> None:
    system.require_root()
    to_install: list[str] = []
    enabled_services: list[str] = []
    php_version = "8.3"

    for choice in ALWAYS_INSTALL:
        if not system.is_installed_apt(choice.packages[0]):
            to_install.extend(choice.packages)
        if choice.service:
            enabled_services.append(choice.service)

    for choice in OPTIONAL_INSTALL:
        default = choice.default if choice.default is not None else True
        if typer.confirm(f"Install {choice.name}?", default=default):
            if not system.is_installed_apt(choice.packages[0]):
                to_install.extend(choice.packages)
            if choice.service:
                enabled_services.append(choice.service)

    if to_install:
        system.run(["apt-get", "update"])
        system.run(["apt-get", "install", "-y", *to_install])

    for service in enabled_services:
        if not system.service_enabled(service):
            system.run(["systemctl", "enable", "--now", service], check=False)

    php_conf_dir = Path(f"/etc/php/{php_version}/fpm/conf.d")
    template_dir = Path(__file__).resolve().parent / "templates"
    if php_conf_dir.exists() and os.access(php_conf_dir, os.W_OK):
        for template_name in ("99-php.ini", "99-opcache.ini"):
            shutil.copy2(template_dir / template_name, php_conf_dir / template_name)
    elif not php_conf_dir.exists():
        typer.echo(f"Warning: PHP conf.d directory not found at {php_conf_dir}")
    else:
        typer.echo(f"Warning: PHP conf.d directory not writable at {php_conf_dir}")

    # Note: we intentionally apply these ini files to PHP-FPM only, not CLI.
    # CLI-specific overrides can differ for scripts or cron jobs.
    server_config = config.ServerConfig(
        php_version=php_version,
        php_fpm_service="php8.3-fpm",
        php_fpm_sock="/run/php/php8.3-fpm.sock",
        nginx_sites_available=str(paths.NGINX_SITES_AVAILABLE),
        nginx_sites_enabled=str(paths.NGINX_SITES_ENABLED),
        mysql_installed=system.is_installed_apt("mysql-server"),
        certbot_installed=system.is_installed_apt("certbot"),
        client_max_body_size="20m",
    )
    config.write_server_config(server_config)
    typer.echo("Server install complete. Config written to /etc/cherve/server.toml")
