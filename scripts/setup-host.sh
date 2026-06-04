#!/usr/bin/env bash
# PART 1 of deployment (README): install ModemManager on the HOST.
# Required for BOTH Docker and venv. Run once on the Pi:
#   cd ~/smspi
#   sudo bash scripts/setup-host.sh
set -euo pipefail

echo "==> Installing host packages for Huawei USB modems + ModemManager"
apt-get update
apt-get install -y \
  modemmanager \
  usb-modeswitch \
  usb-modeswitch-data \
  udev

if ! grep -q 'HuaweiAltModeGlobal=1' /etc/usb_modeswitch.conf 2>/dev/null; then
  echo "==> Enabling HuaweiAltModeGlobal in /etc/usb_modeswitch.conf"
  if grep -q '^#*HuaweiAltModeGlobal=' /etc/usb_modeswitch.conf; then
    sed -i 's/^#*HuaweiAltModeGlobal=.*/HuaweiAltModeGlobal=1/' /etc/usb_modeswitch.conf
  else
    echo 'HuaweiAltModeGlobal=1' >> /etc/usb_modeswitch.conf
  fi
fi

echo "==> Enabling ModemManager"
systemctl enable --now ModemManager

echo "==> Optional: install udev rules for stable Huawei IDs"
if [ -f "$(dirname "$0")/99-huawei-modem.rules" ]; then
  cp "$(dirname "$0")/99-huawei-modem.rules" /etc/udev/rules.d/99-huawei-modem.rules
  udevadm control --reload-rules
  udevadm trigger
fi

echo ""
echo "==> VERIFY (copy/paste each command; all must succeed before starting smspi):"
echo "    systemctl is-active ModemManager    # must print: active"
echo "    mmcli -L                            # must list /org/.../Modem/N when stick is plugged in"
echo "    mmcli -m 0                          # must show modem details (use -m 1 if 0 fails)"
echo ""
echo "Host setup done. Next: README Part 2 (Telegram), Part 3 (config), then Part 4A Docker OR 4B venv."
