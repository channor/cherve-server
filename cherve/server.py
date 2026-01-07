from __future__ import annotations

from dataclasses import dataclass
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
    PackageChoice("npm", ("npm",), False),
)


def install() -> None:
    system.require_root()
    to_install: list[str] = []
    enabled_services: list[str] = []
    package_choices: list[dict[str, object]] = []

    for choice in ALWAYS_INSTALL:
        selected = True
        missing = [package for package in choice.packages if not system.is_installed_apt(package)]
        all_installed = not missing
        package_choices.append({"choice": choice, "selected": selected, "missing": missing})
        if missing:
            to_install.extend(missing)
        if choice.service and selected and (missing or all_installed):
            enabled_services.append(choice.service)

    for choice in OPTIONAL_INSTALL:
        default = choice.default if choice.default is not None else True
        selected = typer.confirm(f"Install {choice.name}?", default=default)
        missing = [package for package in choice.packages if not system.is_installed_apt(package)]
        all_installed = not missing
        package_choices.append({"choice": choice, "selected": selected, "missing": missing})
        if selected:
            if missing:
                to_install.extend(missing)
            if choice.service and (missing or all_installed):
                enabled_services.append(choice.service)

    if to_install:
        system.run(["apt-get", "update"])
        system.run(["apt-get", "install", "-y", *to_install])

    for service in enabled_services:
        if not system.service_enabled(service):
            system.run(["systemctl", "enable", "--now", service], check=False)

    server_config = config.ServerConfig(
        php_version="8.3",
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
