from pathlib import Path

ETC_DIR = Path("/etc/cherve")
SERVER_CONFIG_PATH = ETC_DIR / "server.toml"
SITES_DIR = ETC_DIR / "sites.d"

WWW_ROOT = Path("/var/www")

HOME_ROOT = Path("/home")
NGINX_SITES_AVAILABLE = Path("/etc/nginx/sites-available")
NGINX_SITES_ENABLED = Path("/etc/nginx/sites-enabled")
