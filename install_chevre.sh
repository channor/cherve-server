#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/channor/cherve-server.git"
BRANCH="${BRANCH:-main}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This installer must be run as root. Try: sudo bash install_chevre.sh" >&2
  exit 1
fi

apt-get update
apt-get install -y python3 python3-pip python3-venv pipx git

export PIPX_HOME="/opt/pipx"
export PIPX_BIN_DIR="/usr/local/bin"
mkdir -p "$PIPX_HOME" "$PIPX_BIN_DIR"

pipx install --force "git+${REPO_URL}@${BRANCH}"

echo ""
echo "Cherve installed from branch: ${BRANCH}"
echo "Run:"
echo "  sudo cherve server install"
