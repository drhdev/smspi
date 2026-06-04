#!/usr/bin/env bash
# Quick operational checks for smspi on the host (run from project root).
# Exit 0 = all required checks passed; 1 = failure.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PASS=0
FAIL=0
WARN=0

ok()   { echo "[OK]   $*"; PASS=$((PASS + 1)); }
fail() { echo "[FAIL] $*"; FAIL=$((FAIL + 1)); }
warn() { echo "[WARN] $*"; WARN=$((WARN + 1)); }

echo "==> smspi smoke test (root: $ROOT)"
echo

# --- Host tools ---
if command -v mmcli >/dev/null 2>&1; then
  ok "mmcli found: $(command -v mmcli)"
else
  fail "mmcli not installed (install modemmanager on the host)"
fi

if [ -S /run/dbus/system_bus_socket ]; then
  ok "D-Bus system socket present"
else
  fail "D-Bus socket missing at /run/dbus/system_bus_socket"
fi

if systemctl is-active ModemManager >/dev/null 2>&1; then
  ok "ModemManager service is active"
else
  warn "ModemManager not active (sudo systemctl start ModemManager)"
fi

# --- USB modems ---
if command -v mmcli >/dev/null 2>&1; then
  if MM_LIST="$(mmcli -L 2>/dev/null)" && echo "$MM_LIST" | grep -q Modem; then
    COUNT="$(echo "$MM_LIST" | grep -c '/Modem/' || true)"
    ok "ModemManager reports $COUNT modem(s)"
    echo "$MM_LIST" | sed 's/^/       /'
  else
    warn "No modems in mmcli -L (plug sticks, check usb_modeswitch, wait for registration)"
  fi
fi

if command -v lsusb >/dev/null 2>&1; then
  if lsusb 2>/dev/null | grep -q '12d1:'; then
    ok "Huawei USB device(s) visible (12d1:…)"
    lsusb | grep '12d1:' | sed 's/^/       /'
  else
    warn "No Huawei vendor 12d1 in lsusb (other vendors may still work with ModemManager)"
  fi
fi

# --- Configuration ---
CONFIG="${SMSPI_CONFIG:-$ROOT/config/config.yaml}"
if [ -f "$CONFIG" ]; then
  ok "Config file exists: $CONFIG"
else
  fail "Config missing: $CONFIG (cp config.example.yaml config/config.yaml)"
fi

if [ -f "$ROOT/.env" ]; then
  ok ".env present (secrets for Docker / overrides)"
  # shellcheck disable=SC1091
  set -a && source "$ROOT/.env" && set +a
else
  warn ".env not found (optional; use for Telegram token/chat_id)"
fi

# --- Application data ---
DB="${SMSPI_DB_PATH:-$ROOT/data/smspi.db}"
if [ -f "$DB" ]; then
  ok "SQLite database exists: $DB"
  if command -v sqlite3 >/dev/null 2>&1; then
    PENDING="$(sqlite3 "$DB" "SELECT COUNT(*) FROM sms_messages WHERE telegram_status='pending';" 2>/dev/null || echo "?")"
    FAILED="$(sqlite3 "$DB" "SELECT COUNT(*) FROM sms_messages WHERE telegram_status='failed';" 2>/dev/null || echo "?")"
    echo "       pending=$PENDING failed=$FAILED"
    LAST_HEALTH="$(sqlite3 "$DB" "SELECT status, checked_at FROM health_checks ORDER BY id DESC LIMIT 1;" 2>/dev/null || true)"
    if [ -n "$LAST_HEALTH" ]; then
      echo "       last health: $LAST_HEALTH"
    fi
  else
    warn "sqlite3 CLI not installed (optional for DB inspection)"
  fi
else
  warn "Database not created yet (normal before first run): $DB"
fi

STAMP="${SMSPI_HEALTH_STAMP:-$ROOT/data/.health_ok}"
if [ -f "$STAMP" ]; then
  ok "Health stamp present: $STAMP ($(cat "$STAMP" 2>/dev/null || echo unknown time))"
else
  warn "Health stamp missing (service not healthy yet or not started): $STAMP"
fi

# --- Docker (optional) ---
if command -v docker >/dev/null 2>&1; then
  if docker compose -f "$ROOT/docker-compose.yml" ps --status running 2>/dev/null | grep -q smspi; then
    ok "Docker container smspi is running"
    if docker inspect smspi --format '{{.State.Health.Status}}' 2>/dev/null | grep -q healthy; then
      ok "Docker HEALTHCHECK status: healthy"
    else
      warn "Docker HEALTHCHECK not healthy yet (wait for bootstrap / modems)"
    fi
  else
    warn "Docker installed but smspi container not running"
  fi
fi

# --- Telegram token (optional) ---
if [ -n "${SMSPI_TELEGRAM_BOT_TOKEN:-}" ]; then
  if command -v curl >/dev/null 2>&1; then
    if curl -sf "https://api.telegram.org/bot${SMSPI_TELEGRAM_BOT_TOKEN}/getMe" | grep -q '"ok":true'; then
      ok "Telegram bot token valid (getMe)"
    else
      fail "Telegram getMe failed (check token)"
    fi
  else
    warn "curl not installed; skipping Telegram getMe"
  fi
else
  warn "SMSPI_TELEGRAM_BOT_TOKEN not set; skipping Telegram API check"
fi

# --- Python venv (optional) ---
if [ -x "$ROOT/.venv/bin/python" ]; then
  if "$ROOT/.venv/bin/python" -c "import smspi" 2>/dev/null; then
    ok "Python venv can import smspi"
  else
    warn "venv exists but smspi import failed (PYTHONPATH=src or pip install)"
  fi
fi

echo
echo "==> Summary: $PASS passed, $WARN warnings, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  echo "Smoke test FAILED. Fix [FAIL] items before relying on production traffic."
  exit 1
fi
echo "Smoke test passed (warnings are informational)."
exit 0
