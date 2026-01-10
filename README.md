# cherve

**cherve** is a sudo-first, interactive server management CLI for setting up and operating PHP/Laravel apps on Ubuntu servers.

- Package name: **cherve**
- Command: **cherve**
- Primary design goal: a simple, interactive CLI interface that can grow with more tasks over time.

---

## What cherve does

### `cherve server install`
Installs common server requirements for hosting PHP/Laravel apps and writes a server config file for later use.

### `cherve site create`
Creates a single isolated “site” on the server:

- One dedicated Linux user per site (for isolation and separation of concern)
- One site container root under `/var/www/<domain>`
- A GitHub deploy SSH key owned by the site user
- Optional database + DB owner user
- A default nginx site config for the domain that serves a simple “under construction” landing page

Writes a per-site config file under `/etc/cherve/sites.d/<domain>.toml`.

### `cherve site deploy`
Deploys or updates the app code into the site’s repo directory:

- Clones/pulls the repository into `<site_root>/app` (no release structure)
- Creates the app `.env` on first deploy by copying one of:
  1) `.env.prod`
  2) `.env.production`
  3) `.env.example`
- Makes `.env` production-ready (APP_ENV, APP_URL, APP_DEBUG, DB_* etc.)
- Runs composer and Laravel tasks

### `cherve site activate`
Switches the domain from the default landing page to the deployed app by rewriting the nginx site config to point at the app (and reloading nginx).

### `cherve site deactivate`
Switches the domain back to the default landing page by rewriting the nginx site config to point at the landing root (and reloading nginx).

### `cherve site tls`
Obtains (or renews) a TLS certificate for the site using certbot and configures nginx to serve HTTPS (and redirect HTTP → HTTPS).

All `cherve` actions require **sudo**.

---

## Installation

### Bootstrap installer (recommended)
This repo ships an `install_cherve.sh` intended for a one-liner install that:

- installs `python3` and `pipx` if needed
- installs `cherve` via `pipx` from this GitHub repo
- makes the `cherve` command available globally

Example:

```bash
curl -fsSL https://raw.githubusercontent.com/channor/cherve-server/main/install_cherve.sh | sudo bash
```

### Manual install (developer / testing)

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip pipx
pipx ensurepath

# from repo root:
pipx install -e .
```

Run:

```bash
sudo cherve --help
```

---

## Quick start

### 1. Install server requirements

```bash
sudo cherve server install
```

### 2. Create a site

```bash
sudo cherve site create
```

This will create the site user + directories, and immediately configure nginx to serve a simple landing page for the domain.

### 3. Deploy the app code

```bash
sudo cherve site deploy
```

If you have multiple sites, you can deploy a specific one:

```bash
sudo cherve site deploy microsoft.com
```

### 4. Activate the app (switch nginx to the app)

```bash
sudo cherve site activate
```

Or specify a domain:

```bash
sudo cherve site activate microsoft.com
```

### 5. Enable TLS (when DNS points to the server)

```bash
sudo cherve site tls
```

---

## Files and locations

### Global server config

- `/etc/cherve/server.toml` (root-owned)
- Written by: `cherve server install`
- Contains values cherve uses later, e.g. PHP-FPM socket/service, nginx paths, whether MySQL was installed

Example:

```toml
[php]
version = "php8.3"
fpm_service = "php8.3-fpm"
fpm_sock = "/run/php/php8.3-fpm.sock"

[nginx]
sites_available = "/etc/nginx/sites-available"
sites_enabled = "/etc/nginx/sites-enabled"

[features]
mysql_installed = true
pqsql_installed = false
sqlite_installed = false
certbot_installed = true
```

### Per-site config

- `/etc/cherve/sites.d/<domain>.toml` (root-owned)
- Written by: `cherve site create`

Example:

```toml
domain = "microsoft.com"
site_user = "microsoft"

# Site container root
site_root = "/var/www/microsoft.com"

# Repo working tree (what `cherve site deploy` targets)
repo_root = "/var/www/microsoft.com/app"

# Landing root used by the default nginx config (what `cherve site deactivate` targets)
landing_root = "/var/www/microsoft.com/_cherve/landing"

repo_ssh = "git@github.com:ORG/REPO.git"
branch = "main"
with_www = true
email = ""

db_service = "mysql"
db_name = "microsoft_sd73io"
db_owner_user = "microsoft_db_owner"
# Secrets are not stored in this file. They are printed during `site create` and applied to the app `.env` during deploy.
```

### App env file (secrets)

- `<repo_root>/.env`
- Created on first deploy by copying `.env.prod`, `.env.production`, or `.env.example`
- Updated to production-ready values during deploy

---

## Command behaviour (high level)

### `cherve server install`

- Interactive checklist of packages to install (with defaults)
- Checks whether each component is already installed before installing
- Writes `/etc/cherve/server.toml`

Default install choices:

- Always: git, ufw, nginx, php8.3 (+ extensions), composer, software-properties-common, curl, wget, nano, zip, unzip, openssl, openssh-client, expect, ca-certificates, gnupg, lsb-release, jq, bc, python3-pip
- Default Yes: fail2ban, clamav, mysql, supervisor, certbot (Let’s Encrypt)
- Default No: npm

### `cherve site create`

- Prompts for:
  - username, domain, email (optional)
  - repo SSH URL, branch, include www
  - DB options (db service (choices if multiple available), db name + owner user + password generation)
  - enable TLS now (DNS must already point to this server) (optional)
- Creates site Linux user with disabled password
- Creates site container root `/var/www/<domain>` and permissions
- Creates a landing directory at `<site_root>/_cherve/landing` with a simple under-construction page
- Generates deploy key under `/home/<site_user>/.ssh/` and prints the public key for GitHub Deploy Keys
- Writes `/etc/cherve/sites.d/<domain>.toml`
- Creates nginx site config for the domain pointing to the landing root and enables it (`nginx -t` + reload)
- If TLS was enabled during create, runs `cherve site tls` flow for this domain

### `cherve site deploy [domain]`

- Selects site (by domain argument or interactive list)
- Ensures repo present in `<repo_root>`:
  - clone or pull as the site user using the deploy key
- Creates `.env` if missing by copying the best available template from `<repo_root>`
- Makes `.env` production-ready:
  - `APP_ENV=production`
  - `APP_DEBUG=false`
  - `APP_URL` based on domain (https when TLS is enabled)
  - `DB_*` using the site DB config (prompt for DB password if not available in current session)
- Runs (as site user):
  - `composer install --no-dev --optimize-autoloader`
  - Laravel tasks when `artisan` exists (key generate, migrate, cache)

### `cherve site activate [domain]`

- Selects site (by domain argument or interactive list)
- Rewrites the nginx config for the domain to point to the app root:
  - Laravel default: `<repo_root>/public`
  - Uses PHP-FPM socket from server config
- Validates (`nginx -t`) and reloads nginx
- If TLS is enabled for the site, forces HTTPS redirect

### `cherve site deactivate [domain]`

- Selects site (by domain argument or interactive list)
- Rewrites the nginx config for the domain to point back to the landing root:
  - `<landing_root>`
- Validates (`nginx -t`) and reloads nginx

### `cherve site tls [domain]`

- Selects site (by domain argument or interactive list)
- Runs certbot for the domain (and optional www)
- Updates nginx config to serve HTTPS and redirect HTTP → HTTPS
- Reloads nginx

---

## Development

### Tech choices

- Python CLI with Typer (subcommands + prompts)
- Rich output (optional but recommended)
- TOML configs (tomllib on Python 3.11+, fallback dependency for older)
- System actions executed via subprocess.run() using argv arrays

### Suggested repository structure

```text
root/
  cherve/
    __init__.py
    cli.py          # Typer entry point
    server.py       # server install command
    site.py         # site commands (create/deploy/activate/deactivate/tls)
    config.py       # read/write TOML configs
    system.py       # command runner, checks, fs helpers
    templates/
      nginx_site.conf
      nginx_landing.conf
      landing.html
  install_cherve.sh
  pyproject.toml
  README.md
  AGENTS.md
```

### Local checks

```bash
cherve --help
cherve server --help
cherve site --help
```

---

## Testing

cherve is meant to run on real servers, so tests must be safe by default and avoid mutating the host system.

### Test goals

- Validate command logic and decisions (what would be installed, what files would be written, which commands run).
- Validate file generation and updates:
  - .env selection + productionization
  - TOML config read/write
  - nginx template rendering (landing + app templates)

### Recommended tooling

- pytest
- pytest-mock (or built-in monkeypatch) for mocking subprocess and filesystem calls
- Typer’s CliRunner (from Click) to test CLI behavior and prompts

### Running tests

```bash
python -m pip install -e ".[test]"
pytest -q
```

### Test types (recommended)

- Unit tests: .env editor, config serialization, template rendering.
- Command tests: run CLI commands with mocks to assert:
  - correct prompts and defaults
  - correct sequence of system calls (subprocess argv)
  - correct file writes to a temporary directory
- Golden file tests: nginx config output compared to expected text fixtures

---

## Safety and operational conventions

- Every command runs under sudo; file operations and repo/app operations are executed as the site user via `sudo -iu <user> ...` where appropriate.
- Prefer idempotent behavior:
  - check before installing packages
  - check before creating users/directories
  - check before writing configs
- Always validate nginx config (`nginx -t`) before reload.
- Keep `.env` readable only to the site user (and optionally a controlled group).

## License

TBD