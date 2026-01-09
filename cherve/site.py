from __future__ import annotations

import secrets
from importlib import resources
from pathlib import Path

import click
import shlex
import typer

from cherve import config, envfile, paths, system


def _random_suffix(length: int = 6) -> str:
    return secrets.token_hex(length // 2)


def _ensure_site_user(username: str) -> None:
    if system.user_exists(username):
        return
    system.run(["useradd", "-m", "-s", "/bin/bash", username])
    system.run(["passwd", "-l", username], check=False)


def _ensure_site_root(site_root: Path, site_user: str) -> None:
    site_root.mkdir(parents=True, exist_ok=True)
    system.run(["chown", "-R", f"{site_user}:{site_user}", str(site_root)])


def _ensure_deploy_key(site_user: str, key_path: Path) -> Path:
    ssh_dir = key_path.parent
    ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    system.run(["chown", "-R", f"{site_user}:{site_user}", str(ssh_dir)])
    if key_path.exists():
        return key_path
    command = f"ssh-keygen -t ed25519 -f {shlex.quote(str(key_path))} -N \"\""
    system.run_as_user(
        site_user,
        command,
        capture=True,
    )
    known_hosts = ssh_dir / "known_hosts"
    system.run_as_user(
        site_user,
        f"ssh-keyscan -H github.com >> {known_hosts}",
        check=False,
    )
    return key_path


def _git_env_for_key(key_path: Path) -> dict[str, str]:
    return {"GIT_SSH_COMMAND": f"ssh -i {key_path} -o IdentitiesOnly=yes"}


def _select_site_config(domain: str | None) -> config.SiteConfig:
    if domain:
        return config.read_site_config(domain)
    paths.SITES_DIR.mkdir(parents=True, exist_ok=True)
    options = [p.stem for p in paths.SITES_DIR.glob("*.toml")]
    if not options:
        raise RuntimeError("No sites found in /etc/cherve/sites.d/")
    choice = typer.prompt(
        "Select site",
        type=click.Choice(options, case_sensitive=False),
        default=options[0],
    )
    return config.read_site_config(choice)


def _create_mysql_db(db_name: str, db_user: str, db_password: str) -> None:
    create_db = f"CREATE DATABASE IF NOT EXISTS `{db_name}`;"
    create_user = (
        f"CREATE USER IF NOT EXISTS '{db_user}'@'localhost' IDENTIFIED BY '{db_password}';"
    )
    grant = f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{db_user}'@'localhost';"
    flush = "FLUSH PRIVILEGES;"
    system.run(["mysql", "-e", f"{create_db} {create_user} {grant} {flush}"])


def _write_env(site_root: Path, site_user: str, updates: dict[str, str]) -> None:
    env_path = site_root / ".env"
    envfile.update_env_file(env_path, updates)
    system.run(["chown", f"{site_user}:{site_user}", str(env_path)])
    env_path.chmod(0o640)


def create() -> None:
    system.require_root()
    server_config = config.read_server_config()
    username = typer.prompt("Linux username")
    domain = typer.prompt("Domain")
    email = typer.prompt("Email (optional)", default="")
    repo_ssh = typer.prompt("Repo SSH URL")
    branch = typer.prompt("Branch", default="main")
    with_www = typer.confirm("Include www subdomain?", default=True)

    db_services: list[str] = []
    if server_config.mysql_installed:
        db_services.append("mysql")
    if server_config.pqsql_installed:
        db_services.append("pgsql")
    if server_config.sqlite_installed:
        db_services.append("sqlite")
    default_db = bool(db_services)
    create_db = typer.confirm("Create database?", default=default_db)

    db_service = None
    db_name = None
    db_owner_user = None
    db_password = None
    if create_db and db_services:
        db_service = typer.prompt(
            "Database service",
            default="mysql" if "mysql" in db_services else db_services[0],
            type=click.Choice(db_services, case_sensitive=False),
        )
        db_name = typer.prompt("DB name", default=f"{username}_{_random_suffix()}")
        create_db_user = typer.confirm("Create DB owner user?", default=True)
        if create_db_user:
            db_owner_user = typer.prompt("DB owner username", default=f"{username}_db_owner")
            db_password = secrets.token_urlsafe(16)
            typer.echo(f"DB owner password: {db_password}")

    site_root = paths.WWW_ROOT / domain
    _ensure_site_user(username)
    _ensure_site_root(site_root, username)

    key_path = paths.HOME_ROOT / username / ".ssh" / "id_cherve_deploy"
    _ensure_deploy_key(username, key_path)
    pub_key = key_path.with_suffix(".pub").read_text(encoding="utf-8")
    typer.echo("Deploy key (add to GitHub):")
    typer.echo(pub_key)

    if typer.confirm("Have you added the deploy key to GitHub?", default=False):
        system.run_as_user(
            username,
            "ssh -T git@github.com",
            env=_git_env_for_key(key_path),
            check=False,
            capture=True,
        )

    if create_db and db_service == "mysql" and db_name and db_owner_user and db_password:
        _create_mysql_db(db_name, db_owner_user, db_password)

    site_www_root = site_root / "public"
    site_config = config.SiteConfig(
        domain=domain,
        site_user=username,
        site_root=str(site_root),
        site_www_root=str(site_www_root),
        repo_ssh=repo_ssh,
        branch=branch,
        with_www=with_www,
        email=email,
        db_service=db_service,
        db_name=db_name,
        db_owner_user=db_owner_user,
    )
    config.write_site_config(site_config)

    if typer.confirm("Deploy site now?", default=True):
        deploy(domain)


def deploy(domain: str | None = None) -> None:
    system.require_root()
    site_config = _select_site_config(domain)
    server_config = config.read_server_config()
    site_root = Path(site_config.site_root)
    key_path = paths.HOME_ROOT / site_config.site_user / ".ssh" / "id_cherve_deploy"
    git_env = _git_env_for_key(key_path)

    if not site_root.exists():
        site_root.mkdir(parents=True, exist_ok=True)

    if not (site_root / ".git").exists():
        system.run_as_user(
            site_config.site_user,
            ["git", "clone", "-b", site_config.branch, site_config.repo_ssh, str(site_root)],
            env=git_env,
        )
    else:
        system.run_as_user(
            site_config.site_user,
            ["git", "-C", str(site_root), "pull", "origin", site_config.branch],
            env=git_env,
        )

    env_path = site_root / ".env"
    if not env_path.exists():
        template = envfile.select_template(site_root)
        if template:
            env_path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
            system.run(["chown", f"{site_config.site_user}:{site_config.site_user}", str(env_path)])
        else:
            typer.echo("Warning: No .env template found.")

    tls_enabled = False
    if server_config.certbot_installed:
        tls_enabled = typer.confirm("Enable TLS with certbot?", default=True)

    if env_path.exists():
        scheme = "https" if tls_enabled else "http"
        updates = {
            "APP_ENV": "production",
            "APP_DEBUG": "false",
            "APP_URL": f"{scheme}://{site_config.domain}",
        }
        if site_config.db_service:
            updates.update(
                {
                    "DB_CONNECTION": site_config.db_service,
                    "DB_HOST": "127.0.0.1",
                    "DB_PORT": "3306" if site_config.db_service == "mysql" else "",
                    "DB_DATABASE": site_config.db_name or "",
                    "DB_USERNAME": site_config.db_owner_user or "",
                    "DB_PASSWORD": "",
                }
            )
        _write_env(site_root, site_config.site_user, updates)

    if (site_root / "composer.json").exists():
        system.run_as_user(
            site_config.site_user,
            ["composer", "--working-dir", str(site_root), "install", "--no-dev", "--optimize-autoloader"],
            capture=True,
        )

    artisan = site_root / "artisan"
    if artisan.exists():
        env_values = envfile.parse_env(env_path)
        if not env_values.get("APP_KEY"):
            system.run_as_user(
                site_config.site_user,
                ["php", "artisan", "key:generate"],
                cwd=str(site_root),
            )
        system.run_as_user(
            site_config.site_user,
            ["php", "artisan", "migrate", "--force"],
            cwd=str(site_root),
        )
        for cache_cmd in ("config:cache", "route:cache", "view:cache"):
            system.run_as_user(
                site_config.site_user,
                ["php", "artisan", cache_cmd],
                cwd=str(site_root),
                check=False,
            )

    _render_nginx_config(site_config, server_config)

    if tls_enabled:
        domains = [site_config.domain]
        if site_config.with_www:
            domains.append(f"www.{site_config.domain}")
        system.run(["certbot", "--nginx", "-d", ",".join(domains)], check=False)
        system.run(["nginx", "-t"], check=False)
        system.run(["systemctl", "reload", "nginx"], check=False)


def _render_nginx_config(
    site_config: config.SiteConfig,
    server_config: config.ServerConfig,
    client_max_body_size: str = "20m",
) -> None:
    template = resources.files("cherve.templates").joinpath("nginx_site.conf")
    server_names = [site_config.domain]
    if site_config.with_www:
        server_names.append(f"www.{site_config.domain}")
    rendered = template.read_text(encoding="utf-8").format(
        server_name=" ".join(server_names),
        root_path=site_config.site_www_root,
        php_fpm_sock=server_config.fpm_sock,
        client_max_body_size=client_max_body_size,
    )
    sites_available = Path(server_config.nginx_sites_available)
    sites_enabled = Path(server_config.nginx_sites_enabled)
    sites_available.mkdir(parents=True, exist_ok=True)
    sites_enabled.mkdir(parents=True, exist_ok=True)

    config_path = sites_available / f"{site_config.domain}.conf"
    if config_path.exists():
        backup = config_path.with_suffix(".conf.bak")
        config_path.replace(backup)
    config_path.write_text(rendered, encoding="utf-8")

    enabled_path = sites_enabled / f"{site_config.domain}.conf"
    if not enabled_path.exists():
        enabled_path.symlink_to(config_path)

    system.run(["nginx", "-t"], capture=True)
    system.run(["systemctl", "reload", "nginx"], capture=True)
