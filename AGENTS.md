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

### Environment file creation happens on first deploy
`cherve site create` does not create `.env`.

On first deploy, if `<site_root>/.env` is missing:
- copy from the first existing file in this order:
  1) `.env.prod`
  2) `.env.production`
  3) `.env.example`
- then modify the copied `.env` to be production-ready:
  - set `APP_ENV=production`
  - set `APP_DEBUG=false`
  - set `APP_URL` from the domain (prefer https once TLS is in place)
  - set DB vars (`DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`) from site configuration

Secrets are stored in the app `.env`.

### Site isolation
Each site has one dedicated Linux user (disabled password), used for ownership and running app-level commands:
- git operations
- composer
- artisan

System-level operations (nginx/certbot/supervisor) run as root.

### DB user creation
During `site create`, create the DB owner user when DB is enabled (default Yes).
Store DB identity values in the site config so deploy can populate `.env`.

---

## Commands to implement

### `cherve server install`
Interactive install wizard for packages commonly needed for PHP/Laravel hosting.

Default choices:
- Always install: `git`, `ufw`, `nginx`, `php8.3` (+ extensions), `composer`
- Defaults to Yes: `fail2ban`, `clamav`, `mysql`, `supervisor`, `certbot`, `awscli`
- Default No: `npm`

Implementation requirements:
- Check each component is already installed before installing.
- Persist detected config to `/etc/cherve/server.toml`:
  - PHP-FPM service name and socket path
  - nginx config paths
  - whether mysql/certbot installed
- Prefer safe, minimal configuration changes:
  - validate nginx after changes
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
- Create MySQL database (default Yes when mysql installed)
  - DB name default: `<username>_<random>`
- Create DB owner user (default Yes)
  - Username default: `<username>_db_owner` (append random suffix if exists)
  - Password default: random strong
- Create another DB user (default No)

Actions:
- Create linux user with disabled password
- Create `/var/www/<domain>`
- Ensure correct ownership/perms for site user
- Generate GitHub deploy key for the site user; print public key for Deploy Keys
- If DB enabled: create DB + owner user, grant privileges
- Write site config `/etc/cherve/sites.d/<domain>.toml`

### `cherve site deploy [domain]`
Deploy or update the app into `site_root`.

Selection:
- If `domain` is provided: use `/etc/cherve/sites.d/<domain>.toml`
- Else: present an interactive selection list from `/etc/cherve/sites.d/*.toml`

Actions:
- Ensure repository exists in `site_root`:
  - If missing: clone as site user using deploy key
  - If present: pull latest for configured branch
- Create `.env` on first deploy using the template selection order, then productionize it.
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
- TLS (prompt default Yes):
  - use certbot for domain (+ www if configured)
  - update nginx to force HTTPS, reload

---

## Implementation guidance

### Language + libraries
- Python 3.10+ (3.11+ preferred for built-in `tomllib`)
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