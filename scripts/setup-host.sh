#!/usr/bin/env bash
# Run on Raspberry Pi OS (as root or with sudo) before first Docker start.
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

echo "==> Plug in Huawei sticks, then check:"
echo "    mmcli -L"
echo "    mmcli -m 0"
echo ""
echo "Host setup done. Configure config/config.yaml and run: docker compose up -d --build"
