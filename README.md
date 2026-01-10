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
- One site container root under `/var/www/<site_name>`
- A GitHub deploy SSH key owned by the site user
- Optional database + DB owner user
- No nginx config is created until you attach domains via `cherve domain add`

Writes a per-site config file under `/etc/cherve/sites.d/<site_name>.toml`.

### `cherve domain add`
Attaches a domain to an existing site, writes its nginx config, and optionally enables TLS for
that domain. Each domain gets its own nginx config file to allow separate TLS certificates.

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
Switches all domains for a site from the default landing page to the deployed app by rewriting
each nginx site config to point at the app (and reloading nginx).

### `cherve site deactivate`
Switches all domains for a site back to the default landing page by rewriting each nginx site
config to point at the landing root (and reloading nginx).

### `cherve site tls`
Enables TLS for a specific domain belonging to a site using certbot and configures nginx to serve
HTTPS (and redirect HTTP → HTTPS).

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

This will create the site user + directories. Domains and nginx configuration come next.

### 3. Attach a domain

```bash
sudo cherve domain add
```

### 4. Deploy the app code

```bash
sudo cherve site deploy
```

If you have multiple sites, you can deploy a specific one:

```bash
sudo cherve site deploy microsoft
```

### 5. Activate the app (switch nginx to the app)

```bash
sudo cherve site activate
```

Or specify a site:

```bash
sudo cherve site activate microsoft
```

### 6. Enable TLS (when DNS points to the server)

```bash
sudo cherve site tls enable microsoft microsoft.com
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

- `/etc/cherve/sites.d/<site_name>.toml` (root-owned)
- Written by: `cherve site create`

Example:

```toml
site_name = "microsoft"
site_user = "microsoft"

# Site container root
site_root = "/var/www/microsoft"

# Repo working tree (what `cherve site deploy` targets)
site_app_root = "/var/www/microsoft/_cherve/app"
site_www_root = "/var/www/microsoft/_cherve/app/public"

# Landing root used by the nginx landing config (what `cherve site deactivate` targets)
site_landing_root = "/var/www/microsoft/_cherve/landing"

repo_ssh = "git@github.com:ORG/REPO.git"
branch = "main"
email = ""

[[domains]]
name = "microsoft.com"
with_www = true
tls_enabled = true
ssl_certificate = "/etc/letsencrypt/live/microsoft.com/fullchain.pem"
ssl_certificate_key = "/etc/letsencrypt/live/microsoft.com/privkey.pem"

db_service = "mysql"
db_name = "microsoft_sd73io"
db_owner_user = "microsoft_db_owner"
# Secrets are not stored in this file. They are printed during `site create` and applied to the app `.env` during deploy.
```

### App env file (secrets)

- `<site_app_root>/.env`
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
  - site name, email (optional)
  - repo SSH URL, branch
  - DB options (db service (choices if multiple available), db name + owner user + password generation)
- Creates site Linux user with disabled password
- Creates site container root `/var/www/<site_name>` and permissions
- Creates a landing directory at `<site_root>/_cherve/landing` with a simple under-construction page
- Generates deploy key under `/home/<site_user>/.ssh/` and prints the public key for GitHub Deploy Keys
- Writes `/etc/cherve/sites.d/<site_name>.toml`
- Domains and nginx configuration are handled via `cherve domain add`

### `cherve site deploy [site_name]`

- Selects site (by site name argument or interactive list)
- Ensures repo present in `<repo_root>`:
  - clone or pull as the site user using the deploy key
- Creates `.env` if missing by copying the best available template from `<repo_root>`
- Makes `.env` production-ready:
  - `APP_ENV=production`
  - `APP_DEBUG=false`
  - `APP_URL` based on the primary domain (https when TLS is enabled)
  - `DB_*` using the site DB config (prompt for DB password if not available in current session)
- Runs (as site user):
  - `composer install --no-dev --optimize-autoloader`
  - Laravel tasks when `artisan` exists (key generate, migrate, cache)

### `cherve site activate [site_name]`

- Selects site (by site name argument or interactive list)
- Rewrites the nginx config for each domain to point to the app root:
  - Laravel default: `<repo_root>/public`
  - Uses PHP-FPM socket from server config
- Validates (`nginx -t`) and reloads nginx
- If TLS is enabled for a domain, forces HTTPS redirect for that domain

### `cherve site deactivate [site_name]`

- Selects site (by site name argument or interactive list)
- Rewrites the nginx config for each domain to point back to the landing root:
  - `<landing_root>`
- Validates (`nginx -t`) and reloads nginx

### `cherve site tls enable [site_name] [domain]`

- Selects site and domain (by argument or interactive list)
- Runs certbot for the domain (and optional www)
- Updates nginx config to serve HTTPS and redirect HTTP → HTTPS
- Reloads nginx

### `cherve domain add [site_name] [domain]`

- Selects site and attaches a new domain (prompting when arguments are omitted)
- Writes nginx config for the domain using the site’s current mode (landing/app)
- Optionally enables TLS for that domain

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
