#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/channor/cherve.git"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This installer must be run as root. Try: sudo bash install_chevre.sh" >&2
  exit 1
fi

apt-get update
apt-get install -y python3 python3-pip pipx

pipx ensurepath
export PATH="/root/.local/bin:${PATH}"

if pipx list | grep -q "^package cherve"; then
  pipx upgrade cherve
else
  pipx install "git+${REPO_URL}"
fi

echo ""
echo "Cherve installed. Run:"
echo "  sudo cherve server install"
