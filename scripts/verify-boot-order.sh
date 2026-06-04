#!/usr/bin/env bash
# Verify ModemManager and (optionally) smspi systemd ordering. Run on the Pi.
set -euo pipefail

fail() { echo "[FAIL] $*"; exit 1; }
ok()   { echo "[OK]   $*"; }

echo "==> ModemManager"
systemctl is-enabled ModemManager.service >/dev/null 2>&1 \
  && ok "ModemManager enabled at boot" \
  || fail "ModemManager NOT enabled — run: sudo systemctl enable --now ModemManager"

systemctl is-active --quiet ModemManager.service \
  && ok "ModemManager is running now" \
  || fail "ModemManager NOT running — run: sudo systemctl start ModemManager"

command -v mmcli >/dev/null 2>&1 && ok "mmcli installed" || fail "mmcli missing — run: sudo bash scripts/setup-host.sh"

mmcli -L >/dev/null 2>&1 && ok "mmcli -L works" || fail "mmcli -L failed — check D-Bus / ModemManager"

if systemctl list-unit-files smspi.service >/dev/null 2>&1; then
  echo ""
  echo "==> smspi (venv / systemd deployment)"
  systemctl is-enabled smspi.service >/dev/null 2>&1 \
    && ok "smspi enabled at boot" \
    || echo "[WARN] smspi not enabled — run: sudo bash scripts/install-systemd.sh"

  REQUIRES="$(systemctl show smspi.service -p Requires --value 2>/dev/null || true)"
  AFTER="$(systemctl show smspi.service -p After --value 2>/dev/null || true)"
  echo "       Requires: $REQUIRES"
  echo "       After:    $AFTER"
  echo "$REQUIRES" | grep -q ModemManager.service \
    && ok "smspi Requires ModemManager.service" \
    || fail "smspi does not Require ModemManager — reinstall unit via scripts/install-systemd.sh"
  echo "$AFTER" | grep -q ModemManager.service \
    && ok "smspi After ModemManager.service" \
    || fail "smspi does not start After ModemManager — reinstall unit"
else
  echo ""
  echo "[INFO] smspi.service not installed (OK if you use Docker only)"
  if command -v docker >/dev/null 2>&1; then
    systemctl is-enabled docker >/dev/null 2>&1 \
      && ok "docker enabled at boot (container uses host ModemManager)" \
      || echo "[WARN] docker not enabled at boot — run: sudo systemctl enable docker"
  fi
fi

echo ""
echo "All checks passed."
