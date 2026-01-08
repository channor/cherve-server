from __future__ import annotations

from pathlib import Path
import secrets
import shutil

import click
import typer

from cherve import config
from cherve import envfile
from cherve import paths
from cherve import system


ENV_MANAGED_KEYS = {
    "APP_ENV",
    "APP_DEBUG",
    "APP_URL",
    "DB_HOST",
    "DB_PORT",
    "DB_DATABASE",
    "DB_USERNAME",
    "DB_PASSWORD",
}


def _random_suffix(length: int = 6) -> str:
    return secrets.token_hex(length // 2)


def _random_password(length: int = 24) -> str:
    return secrets.token_urlsafe(length)[:length]


def _user_exists(username: str) -> bool:
    result = system.run(["id", "-u", username], check=False)
    return result.returncode == 0


def _ensure_user(username: str) -> None:
    if _user_exists(username):
        return
    system.run(["useradd", "-m", "-s", "/bin/bash", username])
    system.run(["passwd", "-l", username])


def _ensure_site_root(site_root: Path, username: str) -> None:
    site_root.mkdir(parents=True, exist_ok=True)
    system.run(["chown", "-R", f"{username}:{username}", str(site_root)])

def _ensure_ssh_dir(username: str) -> Path:
    ssh_dir = paths.HOME_ROOT / username / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)

    # Ensure correct ownership + permissions
    system.run(["chown", "-R", f"{username}:{username}", str(ssh_dir)])
    system.run(["chmod", "700", str(ssh_dir)])
    return ssh_dir


def _ensure_deploy_key(username: str) -> Path:
    ssh_dir = _ensure_ssh_dir(username)

    key_path = ssh_dir / "id_cherve_deploy"
    pub_path = ssh_dir / "id_cherve_deploy.pub"

    if not key_path.exists():
        # Use umask so key ends up 600-ish
        cmd = f"umask 077; ssh-keygen -t ed25519 -f {key_path} -N ''"
        system.run_as_user(username, cmd)

    if not pub_path.exists():
        raise RuntimeError("Deploy key public file missing after generation.")

    # Ensure perms are good (avoid SSH warnings later)
    system.run(["chown", f"{username}:{username}", str(key_path), str(pub_path)])
    system.run(["chmod", "600", str(key_path)])
    system.run(["chmod", "644", str(pub_path)])

    return pub_path


def _ensure_known_host(username: str, host: str = "github.com") -> None:
    ssh_dir = _ensure_ssh_dir(username)
    known_hosts = ssh_dir / "known_hosts"

    # Write known_hosts as the user so ownership stays consistent
    # (also avoids races with root-owned files)
    cmd = (
        f"touch {known_hosts} && "
        f"grep -q '{host}' {known_hosts} || ssh-keyscan -H {host} >> {known_hosts}"
    )
    system.run_as_user(username, cmd, check=False)


def _write_site_config(site: config.SiteConfig) -> None:
    config.write_site_config(site)


def _mysql_exec(sql: str) -> None:
    system.run(["mysql", "-e", sql])


def _ensure_database(site: config.SiteConfig, owner_user: str, owner_password: str) -> None:
    if not site.db_name:
        return
    db_name = site.db_name
    _mysql_exec(f"CREATE DATABASE IF NOT EXISTS `{db_name}`;")
    _mysql_exec(
        "\n".join(
            [
                f"CREATE USER IF NOT EXISTS '{owner_user}'@'localhost' IDENTIFIED BY '{owner_password}';",
                f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{owner_user}'@'localhost';",
                "FLUSH PRIVILEGES;",
            ]
        )
    )


def _ensure_extra_db_user(site: config.SiteConfig, username: str, password: str) -> None:
    if not site.db_name:
        return
    db_name = site.db_name
    _mysql_exec(
        "\n".join(
            [
                f"CREATE USER IF NOT EXISTS '{username}'@'localhost' IDENTIFIED BY '{password}';",
                f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{username}'@'localhost';",
                "FLUSH PRIVILEGES;",
            ]
        )
    )


def create() -> None:
    system.require_root()

    server_config = config.read_server_config()
    mysql_installed = server_config.features.mysql_installed if server_config else False

    username = typer.prompt("Site username")
    domain = typer.prompt("Domain")
    email = typer.prompt("Email (optional)", default="")
    repo_ssh = typer.prompt("Repo SSH URL")
    branch = typer.prompt("Branch", default="main")
    with_www = typer.confirm(f"Include www.{domain}?", default=True)

    db_enabled = typer.confirm("Create MySQL database?", default=mysql_installed)

    db_name = None
    db_owner_user = None
    db_owner_password = None
    extra_db_user = None
    extra_db_password = None

    if db_enabled:
        db_name = typer.prompt("Database name", default=f"{username}_{_random_suffix()}")
        create_owner = typer.confirm("Create DB owner user?", default=True)
        if create_owner:
            db_owner_user = typer.prompt("DB owner username", default=f"{username}_db_owner")
            db_owner_password = typer.prompt(
                "DB owner password",
                default=_random_password(),
                hide_input=True,
                confirmation_prompt=True,
            )
        create_extra = typer.confirm("Create another DB user?", default=False)
        if create_extra:
            extra_db_user = typer.prompt("Extra DB username", default=f"{username}_app")
            extra_db_password = typer.prompt(
                "Extra DB password",
                default=_random_password(),
                hide_input=True,
                confirmation_prompt=True,
            )

    site_root = paths.WWW_ROOT / domain

    _ensure_user(username)
    _ensure_site_root(site_root, username)

    pub_key_path = _ensure_deploy_key(username)
    _ensure_known_host(username)

    if db_enabled and db_owner_user and db_owner_password:
        site_config = config.SiteConfig(
            domain=domain,
            site_user=username,
            site_root=str(site_root),
            repo_ssh=repo_ssh,
            branch=branch,
            with_www=with_www,
            email=email,
            db_enabled=db_enabled,
            db_name=db_name,
            db_owner_user=db_owner_user,
            db_owner_password=db_owner_password,
            extra_db_user=extra_db_user,
            extra_db_password=extra_db_password,
        )
        _ensure_database(site_config, db_owner_user, db_owner_password)
        if extra_db_user and extra_db_password:
            _ensure_extra_db_user(site_config, extra_db_user, extra_db_password)
    else:
        site_config = config.SiteConfig(
            domain=domain,
            site_user=username,
            site_root=str(site_root),
            repo_ssh=repo_ssh,
            branch=branch,
            with_www=with_www,
            email=email,
            db_enabled=False,
        )

    _write_site_config(site_config)
    typer.echo("Deploy key public content:")
    typer.echo(pub_key_path.read_text())


def _select_site_config(domain: str | None) -> config.SiteConfig:
    if domain:
        return config.read_site_config(domain=domain)

    configs = sorted(paths.SITES_DIR.glob("*.toml"))
    if not configs:
        raise RuntimeError("No sites found in /etc/cherve/sites.d")

    choices = [p.stem for p in configs]

    choice = typer.prompt(
        "Select site",
        default=choices[0],
        type=click.Choice(choices, case_sensitive=False),
    )
    return config.read_site_config(domain=choice)


def _env_updates(site: config.SiteConfig, use_https: bool) -> dict[str, str]:
    updates = {
        "APP_ENV": "production",
        "APP_DEBUG": "false",
        "APP_URL": f"{'https' if use_https else 'http'}://{site.domain}",
    }
    if site.db_enabled:
        updates.update(
            {
                "DB_HOST": site.db_host,
                "DB_PORT": str(site.db_port),
                "DB_DATABASE": site.db_name or "",
                "DB_USERNAME": site.db_owner_user or "",
                "DB_PASSWORD": site.db_owner_password or "",
            }
        )
    return updates


def _render_nginx_config(server_name: str, root_path: str, php_fpm_sock: str, client_max_body_size: str) -> str:
    template = (Path(__file__).resolve().parent / "templates" / "nginx_site.conf").read_text(
        encoding="utf-8"
    )
    return template.format(
        server_name=server_name,
        root_path=root_path,
        php_fpm_sock=php_fpm_sock,
        client_max_body_size=client_max_body_size,
    )


def _write_nginx_config(
    server_config: config.ServerConfig,
    site: config.SiteConfig,
    root_path: Path,
    php_fpm_sock: str,
) -> Path:
    server_names = [site.domain]
    if site.with_www:
        server_names.append(f"www.{site.domain}")
    server_name = " ".join(server_names)
    config_text = _render_nginx_config(
        server_name=server_name,
        root_path=str(root_path),
        php_fpm_sock=php_fpm_sock,
        client_max_body_size="64M",
    )
    available_dir = Path(server_config.nginx.sites_available)
    enabled_dir = Path(server_config.nginx.sites_enabled)
    available_dir.mkdir(parents=True, exist_ok=True)
    enabled_dir.mkdir(parents=True, exist_ok=True)
    site_conf = available_dir / f"{site.domain}.conf"
    if site_conf.exists():
        backup = site_conf.with_suffix(".conf.bak")
        shutil.copy(site_conf, backup)
    site_conf.write_text(config_text)

    enabled_link = enabled_dir / site_conf.name
    if enabled_link.exists() or enabled_link.is_symlink():
        enabled_link.unlink()
    enabled_link.symlink_to(site_conf)
    system.run(["nginx", "-t"])
    system.run(["systemctl", "reload", "nginx"])
    return site_conf


def deploy(domain: str | None) -> None:
    system.require_root()

    site = _select_site_config(domain)
    server_config = config.read_server_config()
    if not server_config:
        raise RuntimeError("Server config missing. Run `cherve server install` first.")

    php_config = server_config.php.get(server_config.default_php_version)
    if not php_config:
        raise RuntimeError("PHP configuration missing in server config.")

    site_root = Path(site.site_root)
    repo_dir = site_root / ".git"
    key_path = paths.HOME_ROOT / site.site_user / ".ssh" / "id_cherve_deploy"
    git_env = {
        "GIT_SSH_COMMAND": f"ssh -i {key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes"
    }

    if not repo_dir.exists():
        site_root.mkdir(parents=True, exist_ok=True)
        system.run_as_user(
            site.site_user,
            ["git", "clone", "-b", site.branch, site.repo_ssh, str(site_root)],
            env=git_env,
        )
    else:
        system.run_as_user(
            site.site_user,
            ["git", "-C", str(site_root), "pull", "origin", site.branch],
            env=git_env,
        )

    env_path = site_root / ".env"
    if not env_path.exists():
        template = envfile.select_env_template(site_root)
        if not template:
            raise RuntimeError("No .env template found in site root.")
        shutil.copy(template, env_path)

    tls_enabled = False
    if server_config.features.certbot_installed:
        tls_enabled = typer.confirm("Request TLS with certbot?", default=True)
    updates = _env_updates(site, use_https=tls_enabled)
    envfile.update_env_file(env_path, updates)
    system.run(["chmod", "600", str(env_path)])
    system.run(["chown", f"{site.site_user}:{site.site_user}", str(env_path)])

    system.run_as_user(
        site.site_user,
        ["composer", "install", "--no-dev", "--optimize-autoloader"],
        cwd=str(site_root),
    )

    artisan = site_root / "artisan"
    if artisan.exists():
        if not envfile.has_env_key(env_path, "APP_KEY"):
            system.run_as_user(
                site.site_user,
                ["php", "artisan", "key:generate"],
                cwd=str(site_root),
            )
        system.run_as_user(
            site.site_user,
            ["php", "artisan", "migrate", "--force"],
            cwd=str(site_root),
        )
        for command in ["config:cache", "route:cache", "view:cache"]:
            system.run_as_user(
                site.site_user,
                ["php", "artisan", command],
                cwd=str(site_root),
                check=False,
            )

    root_path = site_root / "public"
    _write_nginx_config(server_config, site, root_path, php_config.fpm_sock)

    if tls_enabled:
        domains = ["-d", site.domain]
        if site.with_www:
            domains.extend(["-d", f"www.{site.domain}"])
        certbot_cmd = ["certbot", "--nginx", "--redirect", *domains]
        if site.email:
            certbot_cmd.extend(["--email", site.email, "--agree-tos", "--no-eff-email"])
        else:
            certbot_cmd.append("--register-unsafely-without-email")
        system.run(certbot_cmd)
        system.run(["systemctl", "reload", "nginx"])
