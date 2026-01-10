# AGENTS.md

This file is for AI agents (and humans) who will implement and maintain **cherve**.

## Mission

Build a sudo-first, interactive CLI called `cherve` that manages:

1) server prerequisites (`cherve server install`)
2) site provisioning (`cherve site create`)
3) code deployments (`cherve site deploy`)

…and (starting in **v2**) traffic + TLS lifecycle:

4) traffic switching (`cherve site activate` / `cherve site deactivate`)
5) TLS lifecycle (`cherve site tls enable`)

The CLI must be pleasant to use interactively and safe on production servers.

---

## v2 refactor: explicit changes (BREAKING)

Cherve **v1** exists and works (server install + site create + site deploy) but mixes responsibilities.
**v2 is a deliberate refactor** with these explicit changes:

### 1) Split responsibilities (deploy ≠ nginx ≠ TLS)
- **v1 behavior:** `site deploy` also wrote nginx config and optionally ran certbot.
- **v2 behavior (required):**
  - `cherve site deploy` does **only**: git clone/pull + env + composer + artisan (+ optional asset build).  
    ✅ **No nginx writes. No certbot. No HTTPS forcing.**
  - `cherve site create` sets up the site container only; domains and nginx configs are handled by `cherve domain add`.
  - `cherve site activate` switches nginx from landing → app.
  - `cherve site deactivate` switches nginx from app → landing.
  - `cherve site tls enable` handles certbot issuance and HTTPS redirect enforcement.

### 2) Avoid “domain folder is git repo”
- **v1 behavior:** repo cloned into `/var/www/<domain>` (site_root). This conflicts with having any landing content there.
- **v2 behavior (required):** create a managed layout under `_cherve`:
  - `site_root = /var/www/<site_name>/`
  - `site_app_root = /var/www/<site_name>/_cherve/app/`  ✅ git clone/pull happens here
  - `site_www_root = /var/www/<site_name>/_cherve/app/public` (Laravel default; configurable)
  - `site_landing_root = /var/www/<site_name>/_cherve/landing/` ✅ “under construction” page lives here
- Nginx points either to `site_landing_root` (landing) or to `site_www_root` (app).

### 3) TLS is not tied to deploy
- **v1 behavior:** “Request TLS?” prompt lived in deploy.
- **v2 behavior:** TLS is **separate**:
  - `site tls enable` runs certbot and records `tls_enabled=true` for the selected domain in site config.
  - `site activate/deactivate` (and landing/app templates) should respect domain TLS settings to enforce HTTPS redirects.

### 4) Site vs domains (future-proofing)
- v2 stores configs as `/etc/cherve/sites.d/<site_name>.toml`, but must treat:
  - “site” (container) as the thing being deployed/activated
  - “domain” as a routing identifier
- For v2, allow **multiple domains** per site, and ensure each domain has its own nginx config file.

---

## Implementation targets for v2 (what to build)

### Commands (v2)

#### `cherve server install`
Still installs packages and writes `/etc/cherve/server.toml`. (Mostly unchanged from v1.)

#### `cherve site create`
Provision a site container and wait for domains to be attached via `cherve domain add`.

Must:
- Create user (password disabled). v1 prompts for "Linux Username", v2 changes this to "Site name"
- Create directory layout under `/var/www/<site_name>/_cherve/`
- Generate deploy key
- Write site config `/etc/cherve/sites.d/<site_name>.toml`

#### `cherve site deploy [site_name]`
Only deploy code into `site_app_root`.

Must:
- Clone/pull repo into `site_app_root`
- Create/update `.env` in `site_app_root`
- Run composer/artisan
- **Must not** modify nginx or certbot

#### `cherve site activate [site_name]`
Switch nginx from landing → app for all domains.

Must:
- Render app nginx config pointing to `site_www_root`
- Use PHP-FPM sock from server config
- Validate nginx, reload
- Set `mode="app"` in site config

#### `cherve site deactivate [site_name]`
Switch nginx from app → landing for all domains.

Must:
- Render landing nginx config pointing to `site_landing_root`
- Validate nginx, reload
- Set `mode="landing"` in site config

#### `cherve site tls enable [site_name] [domain]`
Issue TLS cert via certbot and enforce redirects.

Must:
- Confirm DNS prerequisite (interactive confirmation)
- Use email from site config or prompt
- Run `certbot --nginx --redirect ...`
- Record TLS enabled in site config
- Write SSL file paths to config
- Reload nginx

#### `cherve domain add [site_name] [domain]`
Attach a domain to a site, create its nginx config, and optionally enable TLS for that domain.

Must:
- Prompt/select site + domain when arguments are omitted
- Ask whether to include www subdomain
- Render landing or app nginx config (depending on site mode)
- Validate nginx, reload
- Optionally run certbot and update TLS fields for that domain

---

## Non-negotiable behavior

### Sudo-first
All `cherve` actions require sudo. Fail early if not root.

### Template loading (pipx-safe)
Must load templates via `importlib.resources`.

### Site isolation
Each site has one dedicated Linux user (disabled password), used for:
- git operations
- composer
- artisan
  System-level (nginx/certbot/supervisor) runs as root.

### DB user creation (no secret persistence)
- Create DB and DB owner user (default Yes when DB enabled).
- **Never store passwords** in TOML.
- Output generated secrets to terminal for the operator to store.

---

## Config files and schema

### Server config: `/etc/cherve/server.toml`
Written by `cherve server install`.

Must include:
- default PHP version
- per-version `fpm_service` and `fpm_sock`
- nginx paths (sites-available / sites-enabled)
- features installed: mysql/certbot/etc

### Site config: `/etc/cherve/sites.d/<site_name>.toml`
Written by `cherve site create`.

**v2 required keys (minimum):**
- `site_name`
- `site_user`
- `site_root`
- `site_app_root`
- `site_www_root`
- `site_landing_root`
- `repo_ssh` (optional at create-time; required at deploy-time)
- `branch` (default main)
- `email` (optional)
- `mode = "landing" | "app"`
- `domains` (list of domain entries)
  - `name`
  - `with_www`
  - `tls_enabled`
  - `ssl_certificate`
  - `ssl_certificate_key`
- `db.*` metadata (no passwords)

---

## Nginx templates (v2 required)

Maintain these templates:
- `nginx_landing.conf`
  - root = `{site_landing_root}`
  - renders a simple "not yet available" page
- `nginx_php_app.conf`
  - root = `{site_www_root}`
  - fastcgi to `{php_fpm_sock}`
  - Laravel-friendly defaults

Both templates must support:
- `server_name` (domain + optional www)
- optional HTTPS redirect behavior if `tls_enabled` is true (per domain)

Always:
- write config into sites-available
- symlink into sites-enabled
- `nginx -t` then reload

---

## `.env` rules (deploy-only)

On deploy, if `{site_app_root}/.env` is missing:
- copy from first existing (in `{site_app_root}`):
  1) `.env.prod`
  2) `.env.production`
  3) `.env.example`

Then set/overwrite managed keys:
- `APP_ENV=production`
- `APP_DEBUG=false`
- `APP_URL`:
  - `https://<primary-domain>` if `tls_enabled==true`
  - else `http://<primary-domain>`
- DB keys from site config (prompt for DB password if needed)

Permissions:
- owner: site user
- mode: 600

---

## CLI output requirements

### General
- Interactive UX.
- Do not stream raw install output by default (apt progress bars, long logs).
- Print high-level status lines per step.

### Required status vocabulary
Keep wording consistent:
- Checking <thing>...
- Already installed
- Preparing...
- Installing...
- Configuring...
- Done

### `system.run` contract
- `system.run(cmd, capture=True)` returns `.stdout`, `.stderr`, `.returncode`
- Default behavior: quiet (capture, don’t print)
- On failure: print which step failed + command + stderr (or last N lines)
- Optional `--verbose` prints underlying command output live

---

## Implementation guidance

### Language + libraries
- Python 3.11+
- Typer for CLI
- Rich optional
- Use argv arrays with `subprocess.run([...])` (avoid shell strings unless necessary)

### Centralize system operations
In `cherve/system.py`:
- `run(argv, check=True, capture=False, env=None, cwd=None)`
- `run_as_user(user, argv_or_bash)` using `sudo -iu <user> ...`
- `require_root()`, `require_cmd()`
- apt detection via `dpkg -s`
- service helpers via systemctl

### Idempotency
Safe re-run behavior:
- user exists → don’t recreate
- dirs exist → don’t fail
- nginx config exists → backup then replace
- validate nginx before reload

---

## v1 → v2 migration notes (agent must handle)

If an existing v1 site has repo directly in `/var/www/<domain>`:

- v2 must either:
  1) migrate automatically:
    - move current repo to `/var/www/<site_name>/_cherve/app`
    - set new roots in site config (site name may be derived from the old domain)
    - write landing dir + template
      **or**
  2) declare “manual migration required” and provide a command later (`cherve site migrate`).

Pick one strategy and document it. Prefer explicit and safe.

---

## Testing requirements

### Test goals
- Validate orchestration without touching real host.
- Unit test env editor, config schema, template renderers.
- Command tests for create/deploy/activate/deactivate/tls enable (all mocked subprocess).

### Rules
- Never touch real `/etc` or `/var/www`
- Use `tmp_path`
- Monkeypatch `paths.*`
- Mock `system.run` / `system.run_as_user`

### Acceptance checks (v2)

#### site create
- creates user + directories
- writes site config with app/landing roots
- does not write nginx until a domain is added
- mode defaults to landing

#### site deploy
- clones/pulls into app_root
- creates .env in app_root
- runs composer/artisan steps (mock)
- does not touch nginx/certbot

#### site activate/deactivate
- toggles nginx config root correctly for all domains
- updates site config mode
- validates + reloads nginx (mock)

#### site tls enable
- runs certbot with correct args (mock)
- sets tls_enabled=true for the selected domain
- reloads nginx (mock)

#### domain add
- adds domain entry to the site config
- writes nginx config for the domain (mocked reload)
- optional TLS enable flow

---
