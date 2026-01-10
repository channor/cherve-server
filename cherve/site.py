from __future__ import annotations

import secrets
import shlex
import shutil
from dataclasses import replace
from importlib import resources
from pathlib import Path

import click
import typer

from cherve import config, envfile, paths, system


def _random_suffix(length: int = 6) -> str:
    return secrets.token_hex(length // 2)


def _ensure_site_user(username: str) -> None:
    if system.user_exists(username):
        return
    system.run(["useradd", "-m", "-s", "/bin/bash", username])
    system.run(["passwd", "-l", username], check=False)


def _ensure_site_layout(site_root: Path, site_user: str) -> tuple[Path, Path, Path]:
    site_root.mkdir(parents=True, exist_ok=True)
    app_root = site_root / "_cherve" / "app"
    landing_root = site_root / "_cherve" / "landing"
    www_root = app_root / "public"
    app_root.mkdir(parents=True, exist_ok=True)
    landing_root.mkdir(parents=True, exist_ok=True)
    system.run(["chown", "-R", f"{site_user}:{site_user}", str(site_root)])
    return app_root, www_root, landing_root


def _ensure_landing_page(landing_root: Path, site_user: str) -> None:
    index_path = landing_root / "index.html"
    if index_path.exists():
        return
    index_path.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Coming soon</title>"
        "</head><body><h1>Coming soon</h1><p>This site is not yet available.</p></body></html>\n",
        encoding="utf-8",
    )
    system.run(["chown", f"{site_user}:{site_user}", str(index_path)])


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
    env_path.chmod(0o600)


def _server_names(site_config: config.SiteConfig) -> list[str]:
    names = [site_config.domain]
    if site_config.with_www:
        names.append(f"www.{site_config.domain}")
    return names


def _migrate_v1_repo(site_config: config.SiteConfig) -> config.SiteConfig:
    site_root = Path(site_config.site_root)
    app_root = Path(site_config.site_app_root)
    landing_root = Path(site_config.site_landing_root)
    if app_root.exists() or not (site_root / ".git").exists():
        return site_config

    typer.echo("Detected v1 layout, migrating repo into _cherve/app.")
    app_root.mkdir(parents=True, exist_ok=True)
    for entry in site_root.iterdir():
        if entry.name == "_cherve":
            continue
        shutil.move(str(entry), str(app_root / entry.name))
    _ensure_landing_page(landing_root, site_config.site_user)
    config.write_site_config(site_config)
    return site_config


def create() -> None:
    system.require_root()
    server_config = config.read_server_config()
    site_name = typer.prompt("Site name")
    domain = typer.prompt("Domain")
    email = typer.prompt("Email (optional)", default="")
    repo_ssh = typer.prompt("Repo SSH URL (optional)", default="")
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
        db_name = typer.prompt("DB name", default=f"{site_name}_{_random_suffix()}")
        create_db_user = typer.confirm("Create DB owner user?", default=True)
        if create_db_user:
            db_owner_user = typer.prompt("DB owner username", default=f"{site_name}_db_owner")
            db_password = secrets.token_urlsafe(16)
            typer.echo(f"DB owner password: {db_password}")

    site_root = paths.WWW_ROOT / domain
    _ensure_site_user(site_name)
    site_app_root, site_www_root, site_landing_root = _ensure_site_layout(site_root, site_name)
    _ensure_landing_page(site_landing_root, site_name)

    key_path = paths.HOME_ROOT / site_name / ".ssh" / "id_cherve_deploy"
    _ensure_deploy_key(site_name, key_path)
    pub_key = key_path.with_suffix(".pub").read_text(encoding="utf-8")
    typer.echo("Deploy key (add to GitHub):")
    typer.echo(pub_key)

    if typer.confirm("Have you added the deploy key to GitHub?", default=False):
        system.run_as_user(
            site_name,
            "ssh -T git@github.com",
            env=_git_env_for_key(key_path),
            check=False,
            capture=True,
        )

    if create_db and db_service == "mysql" and db_name and db_owner_user and db_password:
        _create_mysql_db(db_name, db_owner_user, db_password)

    site_config = config.SiteConfig(
        domain=domain,
        site_user=site_name,
        site_root=str(site_root),
        site_app_root=str(site_app_root),
        site_www_root=str(site_www_root),
        site_landing_root=str(site_landing_root),
        repo_ssh=repo_ssh,
        branch=branch,
        with_www=with_www,
        email=email,
        mode="landing",
        tls_enabled=False,
        ssl_certificate="",
        ssl_certificate_key="",
        db_service=db_service,
        db_name=db_name,
        db_owner_user=db_owner_user,
    )
    config.write_site_config(site_config)

    _render_nginx_config(
        site_config,
        server_config,
        template_name="nginx_landing.conf",
        root_path=site_config.site_landing_root,
    )

    if typer.confirm("Enable TLS now? (DNS must point to this server)", default=False):
        tls_enable(domain)


def deploy(domain: str | None = None, db_password: str | None = None) -> None:
    system.require_root()
    site_config = _select_site_config(domain)
    site_config = _migrate_v1_repo(site_config)
    site_root = Path(site_config.site_app_root)
    key_path = paths.HOME_ROOT / site_config.site_user / ".ssh" / "id_cherve_deploy"
    git_env = _git_env_for_key(key_path)

    if not site_config.repo_ssh:
        repo_ssh = typer.prompt("Repo SSH URL")
        site_config = replace(site_config, repo_ssh=repo_ssh)
        config.write_site_config(site_config)

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

    if env_path.exists():
        env_values = envfile.parse_env(env_path)
        scheme = "https" if site_config.tls_enabled else "http"
        updates = {
            "APP_ENV": "production",
            "APP_DEBUG": "false",
            "APP_URL": f"{scheme}://{site_config.domain}",
        }
        if site_config.db_service:
            resolved_password = db_password or env_values.get("DB_PASSWORD", "")
            if not resolved_password:
                user_label = site_config.db_owner_user or "database user"
                resolved_password = typer.prompt(
                    f"DB password for {user_label}",
                    hide_input=True,
                    confirmation_prompt=False,
                )
            updates.update(
                {
                    "DB_CONNECTION": site_config.db_service,
                    "DB_HOST": "127.0.0.1",
                    "DB_PORT": "3306" if site_config.db_service == "mysql" else "",
                    "DB_DATABASE": site_config.db_name or "",
                    "DB_USERNAME": site_config.db_owner_user or "",
                    "DB_PASSWORD": resolved_password,
                }
            )
        _write_env(site_root, site_config.site_user, updates)

    if (site_root / "composer.json").exists():
        system.run_as_user(
            site_config.site_user,
            ["composer", "--working-dir", str(site_root), "install", "--no-dev", "--optimize-autoloader"],
            cwd=str(site_root),
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


def activate(domain: str | None = None) -> None:
    system.require_root()
    site_config = _select_site_config(domain)
    server_config = config.read_server_config()
    site_config = _migrate_v1_repo(site_config)
    _render_nginx_config(
        site_config,
        server_config,
        template_name="nginx_php_app.conf",
        root_path=site_config.site_www_root,
        client_max_body_size="20m",
    )
    updated = replace(site_config, mode="app")
    config.write_site_config(updated)


def deactivate(domain: str | None = None) -> None:
    system.require_root()
    site_config = _select_site_config(domain)
    server_config = config.read_server_config()
    site_config = _migrate_v1_repo(site_config)
    _render_nginx_config(
        site_config,
        server_config,
        template_name="nginx_landing.conf",
        root_path=site_config.site_landing_root,
    )
    updated = replace(site_config, mode="landing")
    config.write_site_config(updated)


def tls_enable(domain: str | None = None) -> None:
    system.require_root()
    site_config = _select_site_config(domain)
    if not typer.confirm("Confirm DNS is pointed at this server", default=False):
        return
    email = site_config.email or typer.prompt("Email for Let's Encrypt")
    domains = _server_names(site_config)
    cert_paths = {
        "ssl_certificate": f"/etc/letsencrypt/live/{site_config.domain}/fullchain.pem",
        "ssl_certificate_key": f"/etc/letsencrypt/live/{site_config.domain}/privkey.pem",
    }
    system.run(
        [
            "certbot",
            "--nginx",
            "--redirect",
            "-m",
            email,
            "--agree-tos",
            *[value for domain_name in domains for value in ("-d", domain_name)],
        ],
        check=False,
    )
    updated = replace(
        site_config,
        email=email,
        tls_enabled=True,
        ssl_certificate=cert_paths["ssl_certificate"],
        ssl_certificate_key=cert_paths["ssl_certificate_key"],
    )
    config.write_site_config(updated)
    system.run(["nginx", "-t"], capture=True)
    system.run(["systemctl", "reload", "nginx"], capture=True)


def _render_nginx_config(
    site_config: config.SiteConfig,
    server_config: config.ServerConfig,
    template_name: str,
    root_path: str,
    client_max_body_size: str = "20m",
) -> None:
    template = resources.files("cherve.templates").joinpath(template_name)
    server_names = " ".join(_server_names(site_config))
    https_redirect = ""
    if site_config.tls_enabled:
        https_redirect = 'if ($scheme != "https") { return 301 https://$host$request_uri; }'
    ssl_block = ""
    if site_config.tls_enabled and site_config.ssl_certificate and site_config.ssl_certificate_key:
        ssl_block = (
            "server {{\n"
            "    listen 443 ssl http2;\n"
            f"    server_name {server_names};\n"
            f"    ssl_certificate {site_config.ssl_certificate};\n"
            f"    ssl_certificate_key {site_config.ssl_certificate_key};\n"
            f"    root {root_path};\n"
            "    index index.php index.html index.htm;\n"
            "    client_max_body_size {client_max_body_size};\n"
            "    {app_block}\n"
            "}}\n"
        )
    app_block = ""
    if "php" in template_name:
        app_block = (
            "    location / {\n"
            "        try_files $uri $uri/ /index.php?$query_string;\n"
            "    }\n"
            "    location ~ \\.php$ {\n"
            "        include snippets/fastcgi-php.conf;\n"
            f"        fastcgi_pass unix:{server_config.fpm_sock};\n"
            "    }\n"
        )
    safe_app_block = app_block.replace("{", "{{").replace("}", "}}")
    rendered = template.read_text(encoding="utf-8").format(
        server_name=server_names,
        root_path=root_path,
        php_fpm_sock=server_config.fpm_sock,
        client_max_body_size=client_max_body_size,
        https_redirect=https_redirect,
        ssl_block=ssl_block.format(
            server_name=server_names,
            root_path=root_path,
            client_max_body_size=client_max_body_size,
            app_block=safe_app_block,
        )
        if ssl_block
        else "",
        app_block=app_block,
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
