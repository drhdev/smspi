from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MM_SMS_PATH_RE = re.compile(r"/org/freedesktop/ModemManager1/SMS/\d+")
MM_MODEM_PATH_RE = re.compile(r"/org/freedesktop/ModemManager1/Modem/(\d+)")


@dataclass(frozen=True)
class ModemInfo:
    index: int
    path: str
    stable_id: str
    imei: str | None
    iccid: str | None
    own_number: str | None
    manufacturer: str | None
    model: str | None
    operator_name: str | None
    usb_id: str | None
    state: str | None
    signal: float | None
    enabled: bool


@dataclass(frozen=True)
class SmsInfo:
    path: str
    index: int
    state: str | None
    sender_number: str | None
    sender_name: str | None
    smsc: str | None
    body: str | None
    timestamp: datetime | None
    raw: str


class MmcliError(RuntimeError):
    pass


class MmcliClient:
    def __init__(self, timeout_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, *args: str, retries: int = 2) -> str:
        cmd = ["mmcli", *args]
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
                output = (result.stdout or "") + (result.stderr or "")
                if result.returncode != 0:
                    raise MmcliError(
                        f"mmcli failed ({result.returncode}): {' '.join(cmd)}\n{output.strip()}"
                    )
                return output
            except (subprocess.TimeoutExpired, MmcliError) as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise
        raise last_error or MmcliError("mmcli unknown failure")

    @staticmethod
    def parse_key_values(text: str) -> dict[str, str]:
        data: dict[str, str] = {}
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if "|" in line:
                line = line.split("|", 1)[-1].strip()
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower().replace(" ", "_").replace(".", "")
            value = value.strip().strip("'")
            if key:
                data[key] = value
        return data

    def list_modem_paths(self) -> list[str]:
        text = self.run("-L")
        return [match.group(0) for match in MM_MODEM_PATH_RE.finditer(text)]

    def _modem_index(self, path: str) -> int:
        match = re.search(r"/Modem/(\d+)$", path)
        if not match:
            raise MmcliError(f"Invalid modem path: {path}")
        return int(match.group(1))

    def _read_sysfs_usb_id(self, device_path: str | None) -> str | None:
        if not device_path:
            return None
        sysfs = Path(device_path.replace("'", ""))
        if not sysfs.exists():
            return None
        vendor = (sysfs / "idVendor").read_text().strip() if (sysfs / "idVendor").exists() else ""
        product = (
            (sysfs / "idProduct").read_text().strip()
            if (sysfs / "idProduct").exists()
            else ""
        )
        if vendor and product:
            return f"{vendor}:{product}"
        return None

    def get_modem(self, path: str) -> ModemInfo:
        index = self._modem_index(path)
        merged = self.parse_key_values(self.run("-m", str(index)))
        imei = merged.get("equipment_identifier") or merged.get("imei")
        iccid = merged.get("sim_identifier") or merged.get("iccid")
        own = merged.get("own_numbers") or merged.get("own_number")
        if own and "," in own:
            own = own.split(",")[0].strip()

        manufacturer = merged.get("manufacturer")
        model = merged.get("model")
        operator = merged.get("operator_name") or merged.get("operator")
        state = merged.get("state")
        signal_raw = merged.get("signal_quality") or merged.get("signal")
        signal = None
        if signal_raw:
            try:
                signal = float(signal_raw.split()[0].replace("%", ""))
            except ValueError:
                signal = None

        device = merged.get("device") or merged.get("primary_port")
        usb_id = self._read_sysfs_usb_id(device)

        stable_id = imei or iccid or f"modem-{index}-{usb_id or 'unknown'}"
        enabled = merged.get("power_state", "").lower() == "on"

        return ModemInfo(
            index=index,
            path=path,
            stable_id=stable_id,
            imei=imei,
            iccid=iccid,
            own_number=own,
            manufacturer=manufacturer,
            model=model,
            operator_name=operator,
            usb_id=usb_id,
            state=state,
            signal=signal,
            enabled=enabled,
        )

    def enable_modem(self, index: int) -> None:
        self.run("-m", str(index), "-e")

    def list_sms_paths(self, index: int) -> list[str]:
        text = self.run("-m", str(index), "--messaging-list-sms")
        return MM_SMS_PATH_RE.findall(text)

    def get_sms(self, sms_path: str) -> SmsInfo:
        match = re.search(r"/SMS/(\d+)$", sms_path)
        sms_index = int(match.group(1)) if match else 0
        raw = self.run("-s", sms_path)
        data = self.parse_key_values(raw)

        state = data.get("state")
        number = data.get("number") or data.get("from")
        smsc = data.get("smsc")
        text_body = data.get("text") or data.get("content") or data.get("message")
        ts = self._parse_timestamp(data.get("timestamp") or data.get("date"))

        return SmsInfo(
            path=sms_path,
            index=sms_index,
            state=state,
            sender_number=number,
            sender_name=data.get("contact_name") or data.get("name"),
            smsc=smsc,
            body=text_body,
            timestamp=ts,
            raw=raw,
        )

    def delete_sms(self, modem_index: int, sms_path: str) -> None:
        self.run(
            "-m",
            str(modem_index),
            f"--messaging-delete-sms={sms_path}",
        )

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        value = value.strip()
        for fmt in (
            "%y/%m/%d %H:%M:%S %z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(value, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return None

    def wait_for_manager(self, max_wait_seconds: float = 120.0) -> None:
        deadline = time.monotonic() + max_wait_seconds
        while time.monotonic() < deadline:
            try:
                self.run("-L", retries=0)
                logger.info("ModemManager is reachable")
                return
            except Exception as exc:
                logger.warning("Waiting for ModemManager: %s", exc)
                time.sleep(3.0)
        raise MmcliError("ModemManager not available within timeout")
