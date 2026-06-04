#!/usr/bin/env bash
# Install smspi as a systemd service (venv deployment only — not for Docker).
# Run from the project directory on the Pi, after Part 1–3 of the README deployment guide.
#
# Usage:
#   cd /home/pi/smspi
#   sudo bash scripts/install-systemd.sh
#   sudo bash scripts/install-systemd.sh /opt/smspi   # optional install path
set -euo pipefail

INSTALL_DIR="$(cd "${1:-$(cd "$(dirname "$0")/.." && pwd)}" && pwd)"
UNIT_SRC="$(dirname "$0")/../systemd/smspi.service"
UNIT_DST="/etc/systemd/system/smspi.service"
VENV_PYTHON="$INSTALL_DIR/.venv/bin/python"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash scripts/install-systemd.sh" >&2
  exit 1
fi

if [ ! -f "$UNIT_SRC" ]; then
  echo "Missing unit file: $UNIT_SRC" >&2
  exit 1
fi

if [ ! -x "$VENV_PYTHON" ]; then
  echo "venv not found at $VENV_PYTHON" >&2
  echo "Complete venv setup first (README Part 4B steps 1–5)." >&2
  exit 1
fi

if [ ! -f "$INSTALL_DIR/config/config.yaml" ]; then
  echo "Missing $INSTALL_DIR/config/config.yaml" >&2
  echo "Complete config setup first (README Part 3)." >&2
  exit 1
fi

echo "==> Ensuring ModemManager is installed and enabled at boot"
apt-get install -y modemmanager >/dev/null 2>&1 || true
systemctl enable ModemManager.service
systemctl start ModemManager.service
if ! systemctl is-active --quiet ModemManager.service; then
  echo "ERROR: ModemManager is not active. Run: sudo bash scripts/setup-host.sh" >&2
  exit 1
fi
echo "    ModemManager is active"

echo "==> Installing smspi unit (WorkingDirectory=$INSTALL_DIR)"
sed "s|WorkingDirectory=/opt/smspi|WorkingDirectory=$INSTALL_DIR|g; \
     s|SMSPI_CONFIG=/opt/smspi|SMSPI_CONFIG=$INSTALL_DIR/config/config.yaml|g; \
     s|PYTHONPATH=/opt/smspi|PYTHONPATH=$INSTALL_DIR/src|g; \
     s|ExecStart=/opt/smspi|ExecStart=$INSTALL_DIR|g" \
  "$UNIT_SRC" >"$UNIT_DST"

systemctl daemon-reload
systemctl enable smspi.service

echo "==> Boot order check (smspi must start after ModemManager)"
systemctl show smspi.service -p After -p Requires --no-pager

echo "==> Starting smspi"
systemctl start smspi.service
systemctl status smspi.service --no-pager || true

echo ""
echo "Done. Useful commands:"
echo "  sudo systemctl status ModemManager"
echo "  sudo systemctl status smspi"
echo "  journalctl -u smspi -f"
