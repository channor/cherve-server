from __future__ import annotations

from pathlib import Path

import click
import typer

from cherve import config
from cherve import paths
from cherve import system


BASE_PACKAGES = [
    "git",
    "ufw",
    "composer",
    "software-properties-common",
    "curl",
    "wget",
    "nano",
    "zip",
    "unzip",
    "openssl",
    "openssh-client",
    "expect",
    "ca-certificates",
    "gnupg",
    "lsb-release",
    "jq",
    "bc",
    "python3-pip",
]

PHP_PACKAGES = [
    "php{ver}",
    "php{ver}-fpm",
    "php{ver}-cli",
    "php{ver}-common",
    "php{ver}-curl",
    "php{ver}-bcmath",
    "php{ver}-mbstring",
    "php{ver}-mysql",
    "php{ver}-zip",
    "php{ver}-xml",
    "php{ver}-soap",
    "php{ver}-gd",
    "php{ver}-imagick",
    "php{ver}-intl",
    "php{ver}-opcache",
]

OPTIONAL_DEFAULT_YES = {
    "fail2ban": ["fail2ban"],
    "clamav": ["clamav", "clamav-daemon", "clamav-freshclam"],
    "mysql": ["mysql-server"],
    "supervisor": ["supervisor"],
    "certbot": ["certbot", "python3-certbot-nginx"],
}

OPTIONAL_DEFAULT_NO = {"npm": ["npm"]}


def _install_packages(packages: list[str]) -> None:
    missing = [pkg for pkg in packages if not system.is_installed_apt(pkg)]
    if not missing:
        return
    system.run(["apt-get", "update"])
    system.run(["apt-get", "install", "-y", *missing])


def _ensure_ufw() -> None:
    system.run(["ufw", "allow", "22/tcp"])
    system.run(["ufw", "allow", "80/tcp"])
    system.run(["ufw", "allow", "443/tcp"])
    status = system.run(["ufw", "status"], capture=True, check=False)
    if status.stdout and "Status: active" in status.stdout:
        return
    system.run(["ufw", "--force", "enable"])


def _ensure_nginx_override() -> None:
    override_dir = Path("/etc/systemd/system/nginx.service.d")
    override_dir.mkdir(parents=True, exist_ok=True)
    override_path = override_dir / "override.conf"
    override_path.write_text("[Service]\nLimitNOFILE=65535\n")
    system.run(["systemctl", "daemon-reload"])
    system.run(["systemctl", "restart", "nginx"])


def _ensure_nginx_server_tokens() -> None:
    nginx_conf = Path("/etc/nginx/nginx.conf")
    if not nginx_conf.exists():
        return
    content = nginx_conf.read_text()
    if "server_tokens off;" in content:
        return
    if "http" not in content:
        return
    lines = content.splitlines()
    output: list[str] = []
    inserted = False
    for line in lines:
        output.append(line)
        if not inserted and line.strip().startswith("http") and "{" in line:
            output.append("    server_tokens off;")
            inserted = True
    nginx_conf.write_text("\n".join(output) + "\n")


def _copy_php_templates(version: str) -> None:
    target_dir = Path(f"/etc/php/{version}/fpm/conf.d")
    target_dir.mkdir(parents=True, exist_ok=True)
    for template in ["99-opcache.ini", "99-php.ini"]:
        src = Path(__file__).resolve().parent / "templates" / template
        dst = target_dir / template
        dst.write_text(src.read_text())


def _ensure_fail2ban() -> None:
    target = Path("/etc/fail2ban/jail.local")
    if target.exists():
        return
    template = Path(__file__).resolve().parent / "templates" / "jail.local"
    target.write_text(template.read_text())
    system.run(["systemctl", "enable", "--now", "fail2ban"], check=False)
    system.run(["systemctl", "restart", "fail2ban"], check=False)

def _ensure_clamav() -> None:
    system.run(["systemctl", "stop", "clamav-daemon"], check=False)
    system.run(["systemctl", "stop", "clamav-freshclam"], check=False)
    system.run(["freshclam"], check=False)
    system.run(["systemctl", "enable", "--now", "clamav-freshclam"])
    system.run(["systemctl", "enable", "--now", "clamav-daemon"])

POST_INSTALL = {
    "fail2ban": _ensure_fail2ban,
    "clamav": _ensure_clamav,
}


def install() -> None:
    system.require_root()

    system.require_cmd("apt-get")

    php_versions = ["8.3", "8.4", "8.2"]
    php_version = typer.prompt(
        "Select PHP version",
        default="8.3",
        type=click.Choice(php_versions, case_sensitive=False),
    )

    optional_selected: dict[str, bool] = {}
    for name in OPTIONAL_DEFAULT_YES:
        optional_selected[name] = typer.confirm(f"Install {name}?", default=True)
    for name in OPTIONAL_DEFAULT_NO:
        optional_selected[name] = typer.confirm(f"Install {name}?", default=False)

    base_packages = BASE_PACKAGES + ["nginx"]
    php_packages = [pkg.format(ver=php_version) for pkg in PHP_PACKAGES]
    selected_optional = [
        pkg for name, pkgs in OPTIONAL_DEFAULT_YES.items() if optional_selected.get(name) for pkg in pkgs
    ] + [pkg for name, pkgs in OPTIONAL_DEFAULT_NO.items() if optional_selected.get(name) for pkg in pkgs]

    typer.echo("Packages to install:")
    typer.echo(f"  Base: {', '.join(base_packages)}")
    typer.echo(f"  PHP {php_version}: {', '.join(php_packages)}")
    if selected_optional:
        typer.echo(f"  Optional: {', '.join(selected_optional)}")
    else:
        typer.echo("  Optional: (none)")

    if not typer.confirm("Ready to proceed?", default=True):
        raise typer.Exit(code=0)

    _install_packages(base_packages)
    if php_version in {"8.4", "8.2"}:
        system.run(["add-apt-repository", "-y", "ppa:ondrej/php"])
        system.run(["apt-get", "update"])
    _install_packages(php_packages)
    _ensure_ufw()

    _copy_php_templates(php_version)

    _ensure_nginx_override()
    _ensure_nginx_server_tokens()

    for name, pkgs in OPTIONAL_DEFAULT_YES.items():
        if optional_selected.get(name):
            _install_packages(pkgs)
            hook = POST_INSTALL.get(name)
            if hook:
                hook()

    for name, pkgs in OPTIONAL_DEFAULT_NO.items():
        if optional_selected.get(name):
            _install_packages(pkgs)

    system.run(["nginx", "-t"])
    system.run(["systemctl", "reload", "nginx"], check=False)

    server_config = config.ServerConfig(
        default_php_version=php_version,
        php={
            php_version: config.PHPConfig(
                fpm_service=f"php{php_version}-fpm",
                fpm_sock=f"/run/php/php{php_version}-fpm.sock",
            )
        },
        nginx=config.NginxConfig(
            sites_available=str(paths.NGINX_SITES_AVAILABLE),
            sites_enabled=str(paths.NGINX_SITES_ENABLED),
        ),
        features=config.FeatureConfig(
            mysql_installed=system.is_installed_apt("mysql-server"),
            certbot_installed=system.is_installed_apt("certbot"),
        ),
    )
    config.write_server_config(server_config)
