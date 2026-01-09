# cherve/server.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Union

import click
import typer

from cherve import system

# -----------------------------
# Data model (engine + specs)
# -----------------------------

Hook = Callable[["InstallContext"], None]


@dataclass
class InstallContext:
    """
    Shared mutable context for the installer run.
    Hooks can read/write values here (e.g. selected PHP version).
    """
    php_version: str | None = None
    verbose: bool = False
    dry_run: bool = False
    _apt_updated: bool = False  # internal: ensure apt-get update runs at most once


@dataclass(frozen=True)
class PackageSpec:
    """
    One installable component:
    - apt: list of apt package names (strings only)
    - service: optional systemd service to enable/start
    - pre/post hooks for custom behavior (PPA, templates, config, etc.)
    """
    name: str
    apt: tuple[str, ...] = ()
    default: bool | None = None  # None => no prompt, always included
    service: str | None = None
    pre_install: Optional[Hook] = None
    post_install: Optional[Hook] = None


@dataclass(frozen=True)
class GroupSpec:
    """
    Logical group of specs (can be nested).
    - one_of=True => prompt user to select exactly one child
    """
    name: str
    children: tuple["Spec", ...] = ()
    default: bool | None = None
    one_of: bool = False


Spec = Union[PackageSpec, GroupSpec]


# -----------------------------
# UI helper (high-level output)
# -----------------------------

class UI:
    def step(self, msg: str) -> None:
        typer.echo(msg)

    def status(self, msg: str) -> None:
        typer.echo(msg)

    def ok(self, msg: str = "Done") -> None:
        typer.echo(msg)

    def warn(self, msg: str) -> None:
        typer.echo(f"Warning: {msg}")

    def fail(self, msg: str) -> None:
        typer.echo(f"Error: {msg}", err=True)


ui = UI()


# -----------------------------
# Small utilities
# -----------------------------

def _dedupe_keep_order(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _apt_update_once(ctx: InstallContext) -> None:
    if ctx._apt_updated:
        return
    ui.status("Preparing...")
    system.run(["apt-get", "update"], capture=not ctx.verbose)
    ctx._apt_updated = True


def _install_apt_packages(ctx: InstallContext, pkgs: list[str]) -> None:
    if not pkgs:
        return
    _apt_update_once(ctx)
    ui.status("Installing...")
    system.run(["apt-get", "install", "-y", *pkgs], capture=not ctx.verbose)


def _enable_service(service: str, ctx: InstallContext) -> None:
    # Non-fatal enable/start is usually fine; services can vary by distro/package.
    system.run(["systemctl", "enable", "--now", service], check=False, capture=not ctx.verbose)


# -----------------------------
# Selection engine
# -----------------------------

def _select_specs(specs: tuple[Spec, ...]) -> list[PackageSpec]:
    """
    Expands a plan into a flat list of PackageSpec based on defaults and prompts.
    """
    selected: list[PackageSpec] = []

    def walk(node: Spec) -> None:
        if isinstance(node, PackageSpec):
            if node.default is None:
                selected.append(node)
                return
            if typer.confirm(f"Install {node.name}?", default=bool(node.default)):
                selected.append(node)
            return

        # GroupSpec
        if node.default is not None:
            if not typer.confirm(f"Include {node.name}?", default=bool(node.default)):
                return

        if node.one_of:
            choices = [c.name for c in node.children if isinstance(c, PackageSpec)]
            if not choices:
                raise RuntimeError(f"Group '{node.name}' is one_of but has no PackageSpec children.")
            choice = typer.prompt(
                f"Select {node.name}",
                default=choices[0],
                type=click.Choice(choices, case_sensitive=False),
            )
            for child in node.children:
                if isinstance(child, PackageSpec) and child.name == choice:
                    walk(child)
                    return
            raise RuntimeError(f"Invalid selection '{choice}' for group '{node.name}'.")
        else:
            for child in node.children:
                walk(child)

    for s in specs:
        walk(s)

    return selected


# -----------------------------
# Hooks (examples; fill out later)
# -----------------------------

def ensure_ondrej_php_ppa(ctx: InstallContext) -> None:
    ui.status("Preparing...")
    system.run(["add-apt-repository", "-y", "ppa:ondrej/php"], capture=not ctx.verbose)
    ctx._apt_updated = False  # force apt update after adding repo


def apply_php_fpm_ini_templates(ctx: InstallContext) -> None:
    """
    Copy packaged templates (99-php.ini, 99-opcache.ini) into:
    /etc/php/<ver>/fpm/conf.d/
    Implementation must use importlib.resources (pipx-safe).
    """
    # implemented later
    pass


def nginx_basics(ctx: InstallContext) -> None:
    """
    Nginx post-install:
    - systemd override LimitNOFILE
    - ensure server_tokens off
    - nginx -t
    - reload/restart
    """
    # implemented later
    pass


def clamav_post_install(ctx: InstallContext) -> None:
    ui.status("Configuring...")
    system.run(["systemctl", "stop", "clamav-daemon"], check=False, capture=not ctx.verbose)
    system.run(["systemctl", "stop", "clamav-freshclam"], check=False, capture=not ctx.verbose)
    system.run(["freshclam"], check=False, capture=not ctx.verbose)
    system.run(["systemctl", "enable", "--now", "clamav-freshclam"], check=False, capture=not ctx.verbose)
    system.run(["systemctl", "enable", "--now", "clamav-daemon"], check=False, capture=not ctx.verbose)


def set_php_version(version: str) -> Hook:
    def _hook(ctx: InstallContext) -> None:
        ctx.php_version = version
        apply_php_fpm_ini_templates(ctx)
    return _hook


# -----------------------------
# Plan definition (example)
# -----------------------------

BASE = GroupSpec(
    name="base",
    children=(
        PackageSpec(
            "base-tools",
            apt=(
                "software-properties-common",
                "curl",
                "wget",
                "nano",
                "zip",
                "unzip",
                "openssl",
                "expect",
                "ca-certificates",
                "gnupg",
                "lsb-release",
                "jq",
                "bc",
                "git",
                "openssh-client",
                "python3-pip",
            ),
        ),
        PackageSpec("ufw", apt=("ufw",)),
        PackageSpec("composer", apt=("composer",)),
    ),
)

PHP = GroupSpec(
    name="php",
    one_of=True,
    children=(
        PackageSpec(
            "php8.3",
            apt=(
                "php8.3",
                "php8.3-fpm",
                "php8.3-cli",
                "php8.3-common",
                "php8.3-curl",
                "php8.3-bcmath",
                "php8.3-mbstring",
                "php8.3-mysql",
                "php8.3-zip",
                "php8.3-xml",
                "php8.3-soap",
                "php8.3-gd",
                "php8.3-imagick",
                "php8.3-intl",
                "php8.3-opcache",
            ),
            service="php8.3-fpm",
            post_install=set_php_version("8.3"),
        ),
        PackageSpec(
            "php8.4",
            apt=(
                "php8.4",
                "php8.4-fpm",
                "php8.4-cli",
                "php8.4-common",
                "php8.4-curl",
                "php8.4-bcmath",
                "php8.4-mbstring",
                "php8.4-mysql",
                "php8.4-zip",
                "php8.4-xml",
                "php8.4-soap",
                "php8.4-gd",
                "php8.4-imagick",
                "php8.4-intl",
                "php8.4-opcache",
            ),
            service="php8.4-fpm",
            pre_install=ensure_ondrej_php_ppa,
            post_install=set_php_version("8.4"),
        ),
        PackageSpec(
            "php8.2",
            apt=(
                "php8.2",
                "php8.2-fpm",
                "php8.2-cli",
                "php8.2-common",
                "php8.2-curl",
                "php8.2-bcmath",
                "php8.2-mbstring",
                "php8.2-mysql",
                "php8.2-zip",
                "php8.2-xml",
                "php8.2-soap",
                "php8.2-gd",
                "php8.2-imagick",
                "php8.2-intl",
                "php8.2-opcache",
            ),
            service="php8.2-fpm",
            pre_install=ensure_ondrej_php_ppa,
            post_install=set_php_version("8.2"),
        ),
    ),
)

OPTIONAL = GroupSpec(
    name="optional",
    children=(
        PackageSpec("fail2ban", apt=("fail2ban",), default=True),
        PackageSpec(
            "clamav",
            apt=("clamav", "clamav-daemon", "clamav-freshclam"),
            default=True,
            post_install=clamav_post_install,
        ),
        PackageSpec("mysql", apt=("mysql-server",), default=True),
        PackageSpec("supervisor", apt=("supervisor",), default=True),
        PackageSpec("certbot", apt=("certbot", "python3-certbot-nginx"), default=True),
        PackageSpec("npm", apt=("npm",), default=False),
    ),
)

PLAN: tuple[Spec, ...] = (
    BASE,
    PackageSpec("nginx", apt=("nginx",), service="nginx", post_install=nginx_basics),
    PHP,
    OPTIONAL,
)