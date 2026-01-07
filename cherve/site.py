from __future__ import annotations

from pathlib import Path
import pwd
import secrets
import shutil
import typer

from cherve import config, envfile, paths, system


def create() -> None:
    system.require_root()
    server_cfg = config.read_server_config() or config.ServerConfig(
        php_version="8.3",
        php_fpm_service="php8.3-fpm",
        php_fpm_sock="/run/php/php8.3-fpm.sock",
        nginx_sites_available=str(paths.NGINX_SITES_AVAILABLE),
        nginx_sites_enabled=str(paths.NGINX_SITES_ENABLED),
        mysql_installed=False,
        certbot_installed=False,
    )

    username = typer.prompt("Site Linux username")
    domain = typer.prompt("Domain")
    email = typer.prompt("Email (optional)", default="")
    repo_ssh = typer.prompt("Repo SSH URL")
    branch = typer.prompt("Branch", default="main")
    with_www = typer.confirm(f"Include www.{domain}?", default=True)

    db_enabled_default = server_cfg.mysql_installed
    db_enabled = typer.confirm("Create MySQL database?", default=db_enabled_default)
    db_name = ""
    db_owner_user = ""
    db_owner_password = ""
    if db_enabled:
        db_name_default = f"{username}_{_random_suffix()}"
        db_name = typer.prompt("Database name", default=db_name_default)
        db_owner_default = f"{username}_db_owner"
        db_owner_user = typer.prompt("DB owner username", default=db_owner_default)
        db_owner_password = typer.prompt("DB owner password", default=_random_password())

    site_user = username
    site_root = paths.WWW_ROOT / domain

    _ensure_user(site_user)
    system.ensure_dir(site_root)
    system.run(["chown", "-R", f"{site_user}:{site_user}", str(site_root)])

    deploy_key_path = _deploy_key_path(site_user)
    _generate_deploy_key(site_user, deploy_key_path)
    public_key_path = deploy_key_path.with_suffix(".pub")
    public_key = public_key_path.read_text().strip() if public_key_path.exists() else ""
    if public_key:
        typer.echo("Add this deploy key to your Git provider:")
        typer.echo(public_key)

    if db_enabled:
        _create_database(db_name, db_owner_user, db_owner_password)

    site_config = config.SiteConfig(
        domain=domain,
        site_user=site_user,
        site_root=str(site_root),
        repo_ssh=repo_ssh,
        branch=branch,
        with_www=with_www,
        email=email,
        db_enabled=db_enabled,
        db_host="127.0.0.1",
        db_port=3306,
        db_name=db_name,
        db_owner_user=db_owner_user,
        db_owner_password=db_owner_password,
    )
    config.write_site_config(site_config, paths.SITES_DIR / f"{domain}.toml")
    typer.echo(f"Site config written to {paths.SITES_DIR}/{domain}.toml")


def deploy(domain: str | None = None) -> None:
    system.require_root()
    site_cfg = _load_site_config(domain)
    server_cfg = config.read_server_config()
    if not server_cfg:
        raise SystemExit("Server config not found. Run `cherve server install` first.")

    site_root = Path(site_cfg.site_root)
    site_root.mkdir(parents=True, exist_ok=True)
    _ensure_repo(site_cfg, site_root)

    env_path = site_root / ".env"
    if not env_path.exists():
        template = envfile.select_env_template(site_root)
        if template is None:
            raise SystemExit("No .env template found (.env.prod, .env.production, .env.example).")
        shutil.copyfile(template, env_path)
        system.run(["chown", f"{site_cfg.site_user}:{site_cfg.site_user}", str(env_path)])
        system.run(["chmod", "640", str(env_path)])

    tls_enabled = typer.confirm("Enable TLS with certbot?", default=True)
    app_url = _app_url(site_cfg.domain, tls_enabled)

    updates = {
        "APP_ENV": "production",
        "APP_DEBUG": "false",
        "APP_URL": app_url,
        "DB_HOST": site_cfg.db_host,
        "DB_PORT": str(site_cfg.db_port),
        "DB_DATABASE": site_cfg.db_name,
        "DB_USERNAME": site_cfg.db_owner_user,
        "DB_PASSWORD": site_cfg.db_owner_password,
    }
    envfile.update_env_file(env_path, updates)

    system.run_as_user(
        site_cfg.site_user,
        f"cd {site_root} && composer install --no-dev --optimize-autoloader",
    )

    artisan_path = site_root / "artisan"
    if artisan_path.exists():
        env_values = envfile.load_env(env_path)
        if not env_values.get("APP_KEY"):
            system.run_as_user(site_cfg.site_user, f"cd {site_root} && php artisan key:generate")
        system.run_as_user(site_cfg.site_user, f"cd {site_root} && php artisan migrate --force")
        system.run_as_user(site_cfg.site_user, f"cd {site_root} && php artisan config:cache")
        system.run_as_user(site_cfg.site_user, f"cd {site_root} && php artisan route:cache")
        system.run_as_user(site_cfg.site_user, f"cd {site_root} && php artisan view:cache")

    _render_nginx(site_cfg, server_cfg)

    if tls_enabled and server_cfg.certbot_installed:
        _run_certbot(site_cfg)


def _load_site_config(domain: str | None) -> config.SiteConfig:
    if domain:
        path = paths.SITES_DIR / f"{domain}.toml"
        if not path.exists():
            raise SystemExit(f"Site config not found: {path}")
        return config.read_site_config(path)

    configs = sorted(paths.SITES_DIR.glob("*.toml"))
    if not configs:
        raise SystemExit("No site configs found.")
    if len(configs) == 1:
        return config.read_site_config(configs[0])

    options = [cfg.stem for cfg in configs]
    choice = typer.prompt(f"Select site ({', '.join(options)})")
    path = paths.SITES_DIR / f"{choice}.toml"
    if not path.exists():
        raise SystemExit(f"Site config not found: {path}")
    return config.read_site_config(path)


def _ensure_user(username: str) -> None:
    if not _user_exists(username):
        system.run(["useradd", "-m", "-s", "/bin/bash", username])
        system.run(["passwd", "-l", username])


def _user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
    except KeyError:
        return False
    return True


def _deploy_key_path(username: str) -> Path:
    return paths.HOME_ROOT / username / ".ssh" / "id_cherve_deploy"


def _generate_deploy_key(username: str, key_path: Path) -> None:
    ssh_dir = key_path.parent
    system.ensure_dir(ssh_dir, mode=0o700)
    system.run_as_user(
        username,
        f'ssh-keygen -t ed25519 -N "" -f {key_path}',
    )
    system.run_as_user(
        username,
        'ssh-keyscan -H github.com >> ~/.ssh/known_hosts',
    )


def _create_database(name: str, owner: str, password: str) -> None:
    system.run(["mysql", "-e", f"CREATE DATABASE IF NOT EXISTS `{name}`;"])
    system.run(
        [
            "mysql",
            "-e",
            (
                "CREATE USER IF NOT EXISTS "
                f"'{owner}'@'localhost' IDENTIFIED BY '{password}';"
            ),
        ]
    )
    system.run(
        [
            "mysql",
            "-e",
            f"GRANT ALL PRIVILEGES ON `{name}`.* TO '{owner}'@'localhost';",
        ]
    )


def _ensure_repo(site_cfg: config.SiteConfig, site_root: Path) -> None:
    git_dir = site_root / ".git"
    git_ssh = _git_ssh_command(site_cfg.site_user)
    if not git_dir.exists():
        system.run_as_user(
            site_cfg.site_user,
            f'{git_ssh} git clone --branch {site_cfg.branch} {site_cfg.repo_ssh} {site_root}',
        )
    else:
        system.run_as_user(
            site_cfg.site_user,
            f"{git_ssh} git -C {site_root} fetch origin {site_cfg.branch}",
        )
        system.run_as_user(
            site_cfg.site_user,
            f"{git_ssh} git -C {site_root} checkout {site_cfg.branch}",
        )
        system.run_as_user(
            site_cfg.site_user,
            f"{git_ssh} git -C {site_root} pull origin {site_cfg.branch}",
        )


def _git_ssh_command(username: str) -> str:
    key_path = _deploy_key_path(username)
    return f'GIT_SSH_COMMAND="ssh -i {key_path} -o IdentitiesOnly=yes"'


def _render_nginx(site_cfg: config.SiteConfig, server_cfg: config.ServerConfig) -> None:
    template_path = Path(__file__).resolve().parent / "templates" / "nginx_site.conf"
    template = template_path.read_text()
    server_names = [site_cfg.domain]
    if site_cfg.with_www:
        server_names.append(f"www.{site_cfg.domain}")
    rendered = template.format(
        server_name=" ".join(server_names),
        root_path=f"{site_cfg.site_root}/public",
        php_fpm_sock=server_cfg.php_fpm_sock,
        client_max_body_size=server_cfg.client_max_body_size,
    )

    sites_available = Path(server_cfg.nginx_sites_available)
    sites_enabled = Path(server_cfg.nginx_sites_enabled)
    sites_available.mkdir(parents=True, exist_ok=True)
    sites_enabled.mkdir(parents=True, exist_ok=True)
    config_path = sites_available / f"{site_cfg.domain}.conf"
    backup_path = config_path.with_suffix(".conf.bak")
    if config_path.exists():
        shutil.copyfile(config_path, backup_path)
    config_path.write_text(rendered)
    enabled_path = sites_enabled / f"{site_cfg.domain}.conf"
    if enabled_path.exists() or enabled_path.is_symlink():
        enabled_path.unlink()
    enabled_path.symlink_to(config_path)
    system.run(["nginx", "-t"])
    system.run(["systemctl", "reload", "nginx"])


def _run_certbot(site_cfg: config.SiteConfig) -> None:
    domains = [site_cfg.domain]
    if site_cfg.with_www:
        domains.append(f"www.{site_cfg.domain}")
    args = ["certbot", "--nginx", "-d", domains[0]]
    for domain in domains[1:]:
        args.extend(["-d", domain])
    if site_cfg.email:
        args.extend(["--email", site_cfg.email])
    else:
        args.append("--register-unsafely-without-email")
    args.extend(["--agree-tos", "--no-eff-email"])
    system.run(args)
    system.run(["systemctl", "reload", "nginx"])


def _random_suffix(length: int = 6) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _random_password(length: int = 24) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _app_url(domain: str, tls_enabled: bool) -> str:
    scheme = "https" if tls_enabled else "http"
    return f"{scheme}://{domain}"
