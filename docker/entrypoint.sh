#!/bin/sh
set -eu

: "${DBUS_SYSTEM_BUS_ADDRESS:=unix:path=/run/dbus/system_bus_socket}"

if [ ! -S /run/dbus/system_bus_socket ]; then
  echo "ERROR: D-Bus socket missing. Mount /run/dbus and run ModemManager on the host." >&2
  exit 1
fi

exec "$@"
