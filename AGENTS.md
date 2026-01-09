# AGENTS.md

This file is for AI agents (and humans) who will implement and maintain **cherve**.

## Mission

Build a sudo-first, interactive CLI called `cherve` that manages:
1) server prerequisites (`cherve server install`)
2) site creation (`cherve site create`)
3) deployments (`cherve site deploy`)

The CLI must be pleasant to use interactively and safe on production servers.

---

## Non-negotiable behavior

### Sudo-first
All `cherve` actions require sudo. Commands should fail early with a clear message if not run as root.

### Simple repo layout
Apps are deployed directly into:

- `site_root = /var/www/<domain>`

The repository is cloned/pulled into `site_root` itself.

- `site_www_root` is typical `<site_root>/public`, but may vary.

### Template loading

Must load templates via `importlib.resources` (pipx-safe)

### Environment file creation happens on first deploy

On deploy, if `<site_root>/.env` is missing:
- copy from the first existing file in this order:
  1) `.env.prod`
  2) `.env.production`
  3) `.env.example`
- then modify the copied `.env` to be production-ready:
  - set `APP_ENV=production`
  - set `APP_DEBUG=false`
  - set `APP_URL` from the domain (prefer https once TLS is in place)
  - set DB vars (`DB_CONNECTION`, `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`) from site configuration

Secrets are stored in the app `.env`.

### Site isolation
Each site has one dedicated Linux user (disabled password), used for ownership and running app-level commands:
- git operations
- composer
- artisan

System-level operations (nginx/certbot/supervisor) run as root.

### DB user creation
During `site create`, create the DB owner user when DB is enabled (default Yes).
Do not store secrets, like DB password. Output secrets on terminal for system manager to copy and store it safely.
Where secrets are needed in later sessions, prompt for it.

---

## Commands to implement

### `cherve server install`
Interactive install wizard for packages commonly needed for PHP/Laravel hosting.

Default choices:

- Always install (no prompt)
  - Base tools:
    - git
    - ufw
      - configure: allow 22/tcp, 80/tcp, 443/tcp
      - safety: ensure 22/tcp is allowed before enabling ufw
      - enable ufw if not enabled
    - composer
    - software-properties-common
    - curl
    - wget
    - nano
    - zip
    - unzip
    - openssl
    - expect
    - ca-certificates
    - gnupg
    - lsb-release
    - jq
    - bc
    - python3-pip
  - Web stack:
    - nginx
      - post-install:
        - create systemd override file `/etc/systemd/system/nginx.service.d/override.conf` with:
          ```
          [Service]
          LimitNOFILE=65535
          ```
        - `systemctl daemon-reload` then restart nginx
        - ensure `server_tokens off;` is present inside `http { ... }` in `/etc/nginx/nginx.conf` (add if missing)
  - PHP (choose one):
    - php8.3 (default)
      - packages: php8.3, php8.3-fpm, php8.3-cli, php8.3-common, php8.3-curl, php8.3-bcmath,
        php8.3-mbstring, php8.3-mysql, php8.3-zip, php8.3-xml, php8.3-soap, php8.3-gd,
        php8.3-imagick, php8.3-intl, php8.3-opcache
      - post-install: copy templates `99-opcache.ini` and `99-php.ini` into `/etc/php/<ver>/fpm/conf.d/`
    - php8.4
      - pre-install: add `ppa:ondrej/php` and `apt-get update`
      - packages: same extensions list for 8.4
      - post-install: copy templates `99-opcache.ini` and `99-php.ini`
    - php8.2
      - pre-install: add `ppa:ondrej/php` and `apt-get update`
      - packages: same extensions list for 8.2
      - post-install: copy templates `99-opcache.ini` and `99-php.ini`
- Defaults to Yes (prompt, default yes)
  - fail2ban
    - post-install: copy template `jail.local` (do not overwrite if user modified; create if missing)
  - clamav
    - packages: clamav, clamav-daemon, clamav-freshclam
    - post-install:
      - stop clamav-daemon and clamav-freshclam (non-fatal if not running)
      - run `freshclam`
      - enable --now clamav-freshclam and clamav-daemon
  - mysql (mysql-server)
  - supervisor
  - certbot (certbot, python3-certbot-nginx)
- Default No (prompt, default no)
  - npm
  - sqlite
  - pgsql

Implementation requirements:

- Check whether each package is already installed before installing.
- Persist detected config to `/etc/cherve/server.toml`:
  - PHP-FPM service name and socket path
  - nginx config paths
  - whether mysql/sqlite/pqsql/certbot are installed
- Prefer safe, minimal configuration changes:
  - validate nginx after changes (`nginx -t`)
  - enable services where appropriate

### `cherve site create`

Interactive wizard to create a site.
Prompts:

- Username (e.g. `microsoft`)
- Domain (e.g. `microsoft.com` or `localhost`)
- Email optional (used for certbot)
- Repo SSH URL
- Branch (default `main`)
- Include `www.<domain>` (default Yes)
- Create database (default Yes if a database service is installed)
  - DB service selection (mysql defaults if installed)
  - DB name default: `<username>_<random>`
- Create DB owner user (default Yes)
  - Username default: `<username>_db_owner` (append random suffix if exists)
  - Password default: random strong
- Create another DB user (default No)
- Pub key added to Github repo Deploy Key.
- Deploy site

Actions:

- Create linux user with disabled password
- Create `/var/www/<domain>` (SITE_ROOT)
- Ensure correct ownership/perms for site user
- Generate GitHub deploy key for the site user; print public key for Deploy Keys. Ensure right permissions for .ssh and files
- Test github connection (after key is added to Github Deploy Key)
- If DB enabled: create DB + owner user, grant privileges
- Write site config `/etc/cherve/sites.d/<domain>.toml`
- Synchronously deploys site (if chosen)
  

### `cherve site deploy [domain]`
Deploy or update the app into `site_root` (i.e. `/var/www/microsoft.com/`

Selection:
- If `domain` is provided: use `/etc/cherve/sites.d/<domain>.toml`
- Else: present an interactive selection list from `/etc/cherve/sites.d/*.toml`

Actions:
- Ensure repository exists in `site_root`:
  - If missing: clone as site user using deploy key
  - If present: pull latest as site user for configured branch
- Creates the app `.env` on first deploy by copying one of:
  1. `.env.prod*`
  2. `.env.example`
- If first time deploy:
  - Make .env production-ready:
  - APP_ENV=production
  - APP_DEBUG=false
  - APP_URL based on domain (https when TLS is enabled)
  - DB_* using the site DB config
- Run as site user:
  - `composer install --no-dev --optimize-autoloader`
  - If `artisan` exists:
    - `php artisan key:generate` if missing
    - `php artisan migrate --force`
    - caches/optimize (config/route/view) as desired
- Create nginx config using a bundled template:
  - root should be `site_root/public` for Laravel apps
  - use PHP-FPM socket from server config
  - enable site, `nginx -t`, reload
- If npm is installed and build assets does not exist in `site_root/public/build`, run `npm run build`
- TLS (prompt default Yes):
  - use certbot for domain (+ www if configured)
  - update nginx to force HTTPS, reload

---

## Package/Layout model (for `cherve server install`)

The server installer must be **data-driven**: define installable components as declarative “specs”, then run a generic installer engine that:
1) prompts for optional components,
2) checks if apt packages are already installed,
3) installs missing packages,
4) enables services,
5) runs pre/post hooks for package-specific configuration.

### Goals
- Keep installer logic generic and testable.
- Allow package-specific custom behavior (clamav restart flow, fail2ban templates, nginx tweaks, php template copies).
- Avoid mixing “grouping” logic with “apt package list” logic.

---

## Core concepts

### 1) `InstallContext`
A mutable object passed to hooks so they can access shared selections and services.

- Contains user selections (e.g. selected PHP version)
- Can contain common utilities (logger/UI, verbosity, dry_run, etc.)

Example fields:
- `php_version: str | None`
- `verbose: bool`
- `dry_run: bool`

### 2) `PackageSpec`
Represents one installable component that can map to:
- one or more apt packages
- an optional systemd service to enable
- optional `pre_install` / `post_install` hooks for custom behavior

Rules:
- `apt` contains only **strings** (apt package names).
- `pre_install` and `post_install` are optional hook functions.
- `default` controls prompt behavior:
  - `None` means “no prompt”: always install if reached
  - `True/False` means prompt with that default choice

### 3) `GroupSpec`
Represents a logical group of installable items (e.g. “base”, “php”, “optional tools”)
that contains `children` which are `PackageSpec` or nested `GroupSpec`.

Rules:
- GroupSpec does not represent apt packages itself (unless you explicitly create a PackageSpec for that).
- GroupSpec can be optional as a whole (`default=True/False`) or mandatory (`default=None`).
- `one_of=True` means: prompt user to select exactly **one** child by name (used for PHP version selection).

---

## Type definitions (reference)

```python
from dataclasses import dataclass
from typing import Callable, Optional

Hook = Callable[["InstallContext"], None]

@dataclass
class InstallContext:
  php_version: str | None = None
  verbose: bool = False
  dry_run: bool = False

@dataclass(frozen=True)
class PackageSpec:
  name: str
  apt: tuple[str, ...] = ()
  default: bool | None = None
  service: str | None = None
  pre_install: Optional[Hook] = None
  post_install: Optional[Hook] = None

@dataclass(frozen=True)
class GroupSpec:
  name: str
  children: tuple["PackageSpec | GroupSpec", ...] = ()
  default: bool | None = None
  one_of: bool = False
```

## Example: defining packages/groups

### Base group (always installed)
- Base tools (curl, git, etc.)
- UFW (with post-install configuration)

```python
def ensure_ufw_rules_and_enable(ctx: InstallContext) -> None:
  # Ensure SSH stays open before enabling ufw
  system.run(["ufw", "allow", "OpenSSH"], check=False)
  system.run(["ufw", "allow", "Nginx Full"], check=False)
  system.run(["ufw", "--force", "enable"], check=False)

BASE = GroupSpec(
  name="base",
  default=None,
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
    PackageSpec(
      "ufw",
      apt=("ufw",),
      post_install=ensure_ufw_rules_and_enable,
    ),
  ),
)
```

### PHP group (choose exactly one)

* php8.3 (default)
* php8.4 (requires ondrej PPA)
* php8.2 (requires ondrej PPA)

```python
def ensure_ondrej_php_ppa(ctx: InstallContext) -> None:
    system.run(["add-apt-repository", "-y", "ppa:ondrej/php"])
    system.run(["apt-get", "update"])

def set_php_and_copy_templates(version: str) -> Hook:
    def _hook(ctx: InstallContext) -> None:
        ctx.php_version = version
        apply_php_fpm_ini_templates(ctx)
    return _hook

def apply_php_fpm_ini_templates(ctx: InstallContext) -> None:
    assert ctx.php_version is not None
    # Copy packaged templates (99-php.ini, 99-opcache.ini) into:
    # /etc/php/<ver>/fpm/conf.d/
    # Must use importlib.resources for template loading.
    ...

PHP = GroupSpec(
    name="php",
    one_of=True,
    default=None,
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
            post_install=set_php_and_copy_templates("8.3"),
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
            post_install=set_php_and_copy_templates("8.4"),
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
            post_install=set_php_and_copy_templates("8.2"),
        ),
    ),
)
```

### Optional packages (prompted)

Each can have pre and/or post install hooks:

```python
def configure_fail2ban(ctx: InstallContext) -> None:
    # Copy jail.local template into /etc/fail2ban/jail.local if missing
    # Enable/restart fail2ban
    ...

def configure_clamav(ctx: InstallContext) -> None:
    system.run(["systemctl", "stop", "clamav-daemon"], check=False)
    system.run(["systemctl", "stop", "clamav-freshclam"], check=False)
    system.run(["freshclam"], check=False)
    system.run(["systemctl", "enable", "--now", "clamav-freshclam"], check=False)
    system.run(["systemctl", "enable", "--now", "clamav-daemon"], check=False)

OPTIONAL = GroupSpec(
    name="optional",
    default=None,
    children=(
        PackageSpec("fail2ban", apt=("fail2ban",), default=True, post_install=configure_fail2ban),
        PackageSpec("clamav", apt=("clamav","clamav-daemon","clamav-freshclam"), default=True, post_install=configure_clamav),
        PackageSpec("mysql", apt=("mysql-server",), default=True),
        PackageSpec("supervisor", apt=("supervisor",), default=True),
        PackageSpec("certbot", apt=("certbot","python3-certbot-nginx"), default=True),
        PackageSpec("npm", apt=("npm",), default=False),
    ),
)
```

---

## Implementation guidance

### Language + libraries
- Python 3.11+
- Typer for CLI
- Rich for prompts/output (optional but recommended)
- Use `subprocess.run([...])` with argv arrays, not shell strings.

### System command runner
Centralize all command execution in `cherve/system.py`:
- `run(argv, check=True, capture=False, env=None)`
- `run_as_user(user, argv_or_bash)` via `sudo -iu <user> ...`
- `require_root()`
- `require_cmd()`
- `is_installed_apt(pkg)` using `dpkg -s`
- `service_enabled(name)` / `service_running(name)` using systemctl

### Idempotency
Prefer “safe re-run” behavior:
- user exists → don’t recreate
- directory exists → don’t fail
- config exists → update only the keys you own
- nginx site file exists → replace with regenerated version (after backup)
- validate before reload

### Config read/write
- Server config:
  - read: `/etc/cherve/server.toml`
  - write: overwrite with full known schema after install
- Site config:
  - write: `/etc/cherve/sites.d/<domain>.toml`
  - treat as source of truth for deploy
- TOML operations:
  - read whole file → modify keys → write atomically (tmp + move)

### `.env` mutation rules
Implement a small `.env` editor that:
- preserves unknown keys and comments when possible
- sets/overwrites specific keys deterministically
- ensures required keys exist
- writes with newline at end of file
- permissions: owned by site user, not world-readable

Suggested approach:
- Parse line-by-line and replace `KEY=...` for keys you manage.
- If key missing, append at end.

Keys managed during deploy:
- `APP_ENV`
- `APP_DEBUG`
- `APP_URL`
- `DB_HOST`
- `DB_PORT`
- `DB_DATABASE`
- `DB_USERNAME`
- `DB_PASSWORD`

### SSH deploy key usage
- key path: `/home/<site_user>/.ssh/id_cherve_deploy` (and `.pub`)
- ensure `github.com` is in known_hosts
- for git operations, run as site user with:
  - `GIT_SSH_COMMAND="ssh -i <key> -o IdentitiesOnly=yes"`

### Nginx template variables
A minimal template should accept:
- `server_name` (domain + optional www)
- `root_path` (`site_root/public` when Laravel)
- `php_fpm_sock`
- `client_max_body_size` (server config or prompt)

Always:
- write config into sites-available
- symlink into sites-enabled
- `nginx -t` then reload

---

## Repository hygiene

* Keep tests in tests/ mirroring module structure:
  * tests/test_envfile.py
  * tests/test_config.py
  * tests/test_cli_site_create.py
  * tests/test_cli_site_deploy.py
  * tests/test_cli_server_install.py
* Use fixtures for:
  * temporary filesystem roots
  * sample site configs
  * sample .env templates
  * captured subprocess calls

### Required docs
- `README.md`: user-facing usage and install
- `AGENTS.md`: this file for maintainers/agents

### Suggested testing approach
- Unit tests for:
  - `.env` editor (input → expected output)
  - domain selection logic
  - config read/write + atomic writes
- “Dry-run” mode can aid testing and review.

### Style
- Keep functions small and composable.
- Prefer explicit data models (dataclasses) for server and site config.
- Use clear, human-readable output. This tool is interactive-first.

---

## Acceptance checks (for each command)

### server install
- Running twice does not reinstall already installed packages.
- `/etc/cherve/server.toml` exists with expected keys.
- PHP-FPM socket/service values are stored.

### site create
- Linux user exists and owns `/var/www/<domain>`.
- Deploy key exists and public key is printed.
- Site config exists at `/etc/cherve/sites.d/<domain>.toml`.
- If DB enabled: DB + owner user exists.

### site deploy
- Clones or pulls repo into `site_root`.
- Creates `.env` from the correct template if missing.
- `.env` has production-ready values.
- Laravel deployments run composer and artisan steps.
- Nginx config is created/enabled and nginx reload succeeds.
- TLS can be requested and nginx forces HTTPS when enabled.

---

## CLI output requirements

### General
- Commands are interactive, but should not stream raw install output (e.g. `apt-get` progress bars, long logs).
- Instead, print high-level status lines for each step/package.

### Required status vocabulary
Use these statuses (exact wording optional, but keep them consistent):
- Checking <thing>...
- Already installed
- Preparing...
- Installing...
- Configuring...
- Done

### Per-package behavior (example)
For each package (or package group), output:
1. Checking <package>...
2. If installed: Already installed
3. If not installed:
  - Preparing... (optional; use when adding repo/keys or updating apt)
  - Installing...
  - Configuring... (only when there are post-install actions)
  - Done

### Implementation rules
- `system.run(...)` should support a “quiet mode”:
  - By default, capture stdout/stderr and do not print them.
  - On failure, print a short error summary and the captured stderr (or last N lines, e.g. 50).
- Provide a `--verbose` flag to show underlying command output live (optional but recommended).
- All user-facing output should be done via `typer.echo()` (or Rich console), not `print()`.

### Error handling
- If a step fails, print:
  - which step/package failed
  - the command that failed
  - the captured stderr snippet (or last N lines)
- Then exit non-zero.

### Logging helper (recommended)
- Implement a helper for step logging, e.g.:
  - `ui.step("Checking nginx...")`
  - `ui.ok("Already installed")`
  - `ui.warn("Skipped")`
  - `ui.fail("Install failed")`

### `system.run` contract
- `system.run(cmd, capture=True)` returns an object with `.stdout`, `.stderr`, `.returncode`
- In non-verbose mode, do not print stdout/stderr unless the command fails.

---

## Testing requirements (agent must implement tests)

cherve runs privileged operations, so testing must be designed to be safe, deterministic, and fast.

### Test tools
Add a test dependency group in `pyproject.toml`:
- `pytest`
- `pytest-mock` (or rely on `monkeypatch`)
- `coverage` (optional)
  Use Typer/Click testing tools:
- `from typer.testing import CliRunner`

### Test strategy overview
Implement tests in three layers:

#### 1) Unit tests (pure functions)
Focus on logic that must not depend on the host system:
- `.env` template selection order:
  - chooses `.env.prod` over `.env.production` over `.env.example`
- `.env` productionization:
  - sets/overwrites managed keys correctly
  - appends missing keys
  - keeps unrelated keys intact
- TOML config read/write:
  - round-trip (write then read) preserves schema
  - atomic write behavior (write to temp then move)
- nginx template renderer:
  - render output matches expected fixture (“golden” test)

#### 2) Command tests (CLI behavior + orchestration)
Run CLI commands with mocks and a temporary filesystem:
- Use `CliRunner()` to invoke commands and simulate prompts.
- Mock `system.run`, `system.run_as_user`, and package/service detection functions.
- Assert:
  - prompts appear and defaults are applied
  - correct subprocess argv sequences are constructed
  - correct config files are written to expected paths
  - correct `.env` is created and updated during deploy

Use `tmp_path` fixtures for a fake filesystem and monkeypatch paths so tests never touch `/etc` or `/var/www`.

#### 3) Integration-style tests (still safe)
Build a fake “site_root” repo in a temp dir:
- create `.env.example` and a fake `artisan`
- simulate a git repo structure (or mock git commands)
- invoke `cherve site deploy` and assert:
  - `.env` created and productionized
  - expected command calls were scheduled

Integration tests should still mock subprocess calls; they validate filesystem outputs and orchestration.

### Sudo requirement in tests
Make `require_root()` testable:
- implement it in a way that can be monkeypatched in tests (e.g., check via a function in `system.py`)
- tests should patch the root check to pass

### Acceptance tests per command (must exist)

#### server install
- When a package is reported installed, the installer does not attempt to install it.
- `/etc/cherve/server.toml` content contains expected keys after run.

#### site create
- Creates site config `/etc/cherve/sites.d/<domain>.toml` with correct values.
- Generates a deploy key (simulated) and prints the public key content (assert in CLI output).
- When DB enabled, emits calls to create DB and DB user with expected names.

#### site deploy
- Selects the correct env template and creates `.env`.
- `.env` contains production-ready values (APP_ENV, APP_DEBUG, APP_URL, DB_*).
- Laravel detection triggers artisan steps.
- nginx config rendering is invoked with correct `server_name`, `root_path`, and `php_fpm_sock`.

### Running tests
Provide a standard command in README:
```bash
python -m pip install -e ".[test]"
pytest -q
```